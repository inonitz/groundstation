#!/usr/bin/env python3
"""Round 6 -- full pipeline: commands AND perception, six arms.

Case sets:
  COMMANDS   = the 190 standard movement cases (cases.py).
               Flow: text -> [translator] -> revised prompt on Qwen3-VL -> mission JSON -> scorer.
  PERCEPTION = 100 multi-hop cases (cases_perception100.py), with hand-written EN references.
               Flow: Hebrew -> [translator] -> English -> keyword scorer. No planner: these
               route to the VLM in the real system.

Arms (plain dataflow names):
  control-perfect-english   commands: hand-written EN -> planner. perception: the hand-written
                            EN reference scored directly (0 model calls; audits the scorer).
  dictalm-alone             both halves translated by DictaLM (2-shot + line grammar).
  translategemma-alone      both halves by TranslateGemma (native template on /completion).
  qwen3vl-alone             both halves translated by Qwen3-VL (same 2-shot setup as DictaLM),
                            then its command translations go to the planner (same loaded model).
  split-dictalm-commands+translategemma-perception
                            commands = dictalm-alone rows, perception = translategemma-alone rows.
                            Re-aggregation of cached rows, ZERO new compute; routing by known
                            case type (production would route via the existing tier router).
  refine-dictalm-draft->translategemma-final
                            commands = dictalm-alone rows. perception: TranslateGemma receives
                            the Hebrew as ground truth + DictaLM's draft, finalizes. Perception
                            latency = draft + refine (sequential in production).

Strictly sequential: 3 model loads total (dicta, tgemma, qwen3vl). Every planning call carries
the dx/dy/dz GBNF grammar. Temp 0, one pass per case (determinism proven round 1)."""
import json, math, os, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_bench as rb
import round4
from cases import CASES as CMD_CASES, score
from cases_perception import score_perception
from cases_perception100 import PERC100, check_refs

SMOKE = os.environ.get("ROUND6_SMOKE") == "1"
CMD = CMD_CASES[:6] if SMOKE else CMD_CASES
PERC = PERC100[:6] if SMOKE else PERC100
PORT = round4.PORT

TGEMMA_REFINE = ("<start_of_turn>user\n"
 "You are a professional Hebrew (he) to English (en) translator.\n"
 "The Hebrew text below is the ground truth. The draft English translation below it was produced "
 "by another system and may contain errors or omissions. Correct and finalize the translation "
 "against the Hebrew ground truth. Produce only the final English translation, without any "
 "additional explanations or commentary.\n\n"
 "Hebrew ground truth:\n{he}\n\n"
 "Draft translation:\n{draft}<end_of_turn>\n<start_of_turn>model\n")

def perc_summarize(arm, translations):
    rows, by = [], {c[0]: c for c in PERC}
    for name, en, dt in translations:
        _, he, ref, groups, hops = by[name]
        missed = score_perception(en, groups)
        rows.append({"case": name, "hops": hops, "he": he, "en": en, "t_ms": round(dt*1000),
                     "missed": ["|".join(g) for g in missed], "ok": not missed,
                     "groups_total": len(groups), "groups_kept": len(groups) - len(missed)})
    n, ok = len(rows), sum(1 for r in rows if r["ok"])
    lo, hi = rb.wilson(ok, n)
    gt = sum(r["groups_total"] for r in rows); gk = sum(r["groups_kept"] for r in rows)
    lat = [r["t_ms"] for r in rows]
    pcts = {f"p{p}": round(rb.pct(lat, p)) for p in (25, 50, 75, 95, 99)}; pcts["max"] = max(lat)
    by_hops = {h: {"n": len(hr), "ok": sum(1 for r in hr if r["ok"])}
               for h in sorted({r["hops"] for r in rows})
               for hr in [[r for r in rows if r["hops"] == h]]}
    print(f"  perception {arm}: {ok}/{n} ({ok/n:.0%}) wilson95 [{lo:.0%},{hi:.0%}] "
          f"groups {gk}/{gt} ({gk/gt:.0%}) depth " +
          " ".join(f"d{h}:{s['ok']}/{s['n']}" for h, s in by_hops.items()), flush=True)
    return {"ok": ok, "n": n, "wilson95": [round(lo,3), round(hi,3)],
            "groups_kept": gk, "groups_total": gt, "latency_ms": pcts,
            "by_depth": by_hops, "cases": rows}

def cmd_summarize(arm, rows):
    s = rb.summarize(f"commands {arm}", rows)
    s.pop("pipeline", None)
    return s

def mcnemar(rows_a, rows_b, okfn):
    a = {r["case"]: okfn(r) for r in rows_a}; b = {r["case"]: okfn(r) for r in rows_b}
    n01 = sum(1 for c in a if a[c] and not b[c]); n10 = sum(1 for c in a if not a[c] and b[c])
    n = n01 + n10
    p = 1.0 if n == 0 else min(1.0, sum(math.comb(n, k) for k in range(min(n01, n10)+1)) / 2**n * 2)
    return {"only_a": n01, "only_b": n10, "p": round(p, 6)}

def main():
    assert not rb.port_up(PORT) and not rb.port_up(rb.QWEN_PORT), "llama-server already running"
    assert not check_refs(), "reference/group mismatch -- fix cases_perception100 first"
    t0 = time.time()

    print(f"== [1/3] DictaLM: translate {len(CMD)} commands + {len(PERC)} perception ==", flush=True)
    with rb.LlamaServer(round4.MODELS["dicta"], PORT):
        cmd_dicta = round4.translate_all(PORT, CMD)
        perc_dicta = round4.translate_all(PORT, PERC)

    print(f"== [2/3] TranslateGemma: translate {len(CMD)}+{len(PERC)}, refine {len(PERC)} drafts ==", flush=True)
    draft_by = {n: en for n, en, dt in perc_dicta}
    draft_t = {n: dt for n, en, dt in perc_dicta}
    with rb.LlamaServer(round4.MODELS["tgemma"], PORT, extra=("--chat-template", "gemma")):
        cmd_tg = round4.tgemma_translate_all(PORT, CMD)
        perc_tg = round4.tgemma_translate_all(PORT, PERC)
        perc_refine = []
        for name, he, ref, groups, hops in PERC:
            t, dt = rb.completion(PORT, TGEMMA_REFINE.format(he=he, draft=draft_by[name]),
                                  max_tokens=100, grammar=rb.LINE_GRAMMAR)
            perc_refine.append((name, t.strip(), dt + draft_t[name]))   # latency: draft + refine

    print(f"== [3/3] Qwen3-VL: translate {len(CMD)}+{len(PERC)}, then plan 4 command sets ==", flush=True)
    arms = {}
    with rb.LlamaServer(round4.MODELS["qwen3vl"], PORT, extra=round4.QWEN3VL_EXTRA):
        cmd_qw = round4.translate_all(PORT, CMD)
        perc_qw = round4.translate_all(PORT, PERC)
        en_ref = [(c[0], c[2], 0.0) for c in CMD]
        plan = lambda texts: round4.plan_all_d(PORT, texts, round4.REVISED_PROMPT, shots=round4.PLANNER_SHOTS_D)
        print("-- arm control-perfect-english", flush=True)
        arms["control-perfect-english"] = {
            "commands": cmd_summarize("control", plan(en_ref)),
            "perception": perc_summarize("control(reference text, no model)",
                                         [(c[0], c[2], 0.0) for c in PERC])}
        print("-- arm dictalm-alone", flush=True)
        arms["dictalm-alone"] = {
            "commands": cmd_summarize("dictalm", plan(cmd_dicta)),
            "perception": perc_summarize("dictalm", perc_dicta)}
        print("-- arm translategemma-alone", flush=True)
        arms["translategemma-alone"] = {
            "commands": cmd_summarize("translategemma", plan(cmd_tg)),
            "perception": perc_summarize("translategemma", perc_tg)}
        print("-- arm qwen3vl-alone", flush=True)
        arms["qwen3vl-alone"] = {
            "commands": cmd_summarize("qwen3vl-translated", plan(cmd_qw)),
            "perception": perc_summarize("qwen3vl", perc_qw)}
        print("-- arm refine (perception only new)", flush=True)
        arms["refine-dictalm-draft->translategemma-final"] = {
            "commands": arms["dictalm-alone"]["commands"],
            "perception": perc_summarize("refine", perc_refine),
            "note": "commands shared with dictalm-alone"}
        arms["split-dictalm-commands+translategemma-perception"] = {
            "commands": arms["dictalm-alone"]["commands"],
            "perception": arms["translategemma-alone"]["perception"],
            "note": "re-aggregation of cached rows, zero new compute"}

    ok_cmd = lambda r: r["score"].startswith(("CORRECT", "valid"))
    ok_perc = lambda r: r["ok"]
    mn = {
     "commands control vs dictalm": mcnemar(arms["control-perfect-english"]["commands"]["cases"],
                                            arms["dictalm-alone"]["commands"]["cases"], ok_cmd),
     "commands dictalm vs translategemma": mcnemar(arms["dictalm-alone"]["commands"]["cases"],
                                                   arms["translategemma-alone"]["commands"]["cases"], ok_cmd),
     "commands dictalm vs qwen3vl": mcnemar(arms["dictalm-alone"]["commands"]["cases"],
                                            arms["qwen3vl-alone"]["commands"]["cases"], ok_cmd),
     "perception translategemma vs dictalm": mcnemar(arms["translategemma-alone"]["perception"]["cases"],
                                                     arms["dictalm-alone"]["perception"]["cases"], ok_perc),
     "perception refine vs translategemma": mcnemar(arms["refine-dictalm-draft->translategemma-final"]["perception"]["cases"],
                                                    arms["translategemma-alone"]["perception"]["cases"], ok_perc),
     "perception refine vs dictalm": mcnemar(arms["refine-dictalm-draft->translategemma-final"]["perception"]["cases"],
                                             arms["dictalm-alone"]["perception"]["cases"], ok_perc),
    }
    for k, v in mn.items(): print(f"McNemar {k}: {v}", flush=True)

    stamp = datetime.date.today().isoformat()
    out = os.path.join(HERE, "results", f"{stamp}-round6-results.json")
    json.dump({"arms": arms, "mcnemar": mn, "smoke": SMOKE, "wall_s": round(time.time()-t0)},
              open(out, "w"), ensure_ascii=False, indent=1)

    dump = os.path.join(HERE, "results", f"{stamp}-round6-dump.md")
    with open(dump, "w") as f:
        f.write("# Round-6 perception translations -- full dump for owner review\n\n")
        f.write("Check relation inversions here; the keyword scorer cannot see them.\n\n")
        f.write("| case | depth | Hebrew | reference | dictalm | translategemma | refined | qwen3vl | missed d/t/r/q |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        P = {arm: {c["case"]: c for c in arms[arm]["perception"]["cases"]}
             for arm in ("dictalm-alone", "translategemma-alone",
                         "refine-dictalm-draft->translategemma-final", "qwen3vl-alone")}
        for name, he, ref, groups, hops in PERC:
            d = P["dictalm-alone"][name]; t = P["translategemma-alone"][name]
            r = P["refine-dictalm-draft->translategemma-final"][name]; q = P["qwen3vl-alone"][name]
            miss = " / ".join((", ".join(x["missed"]) or "-") for x in (d, t, r, q))
            f.write(f"| {name} | {hops} | {he} | {ref} | {d['en']} | {t['en']} | {r['en']} | {q['en']} | {miss} |\n")

    print("\n| arm | commands acc | perception all-groups | perception groups kept | cmd p50 | perc p50 (ms) |")
    print("|---|---|---|---|---|---|")
    for name, a in arms.items():
        c, p = a["commands"], a["perception"]
        print(f"| {name} | {c['ok']}/{c['n']} ({c['acc']:.0%}) | {p['ok']}/{p['n']} ({p['ok']/p['n']:.0%}) "
              f"| {p['groups_kept']}/{p['groups_total']} ({p['groups_kept']/p['groups_total']:.0%}) "
              f"| {c['latency_e2e_ms']['p50']} | {p['latency_ms']['p50']} |")
    print(f"\nresults -> {out}\ndump -> {dump}\nwall {round(time.time()-t0)}s", flush=True)

if __name__ == "__main__":
    main()
