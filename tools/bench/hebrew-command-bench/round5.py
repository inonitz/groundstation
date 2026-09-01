#!/usr/bin/env python3
"""Round 5 -- multi-hop perception commands through three Hebrew->English readers.

What runs: 45 hand-authored Hebrew commands (cases_indirect.py). Every target is reached through
attribute + relation links ("the car adjacent to the person with the red attire"). No planner
runs in this round -- these commands route to the VLM in the real system, so the measured stage
is Hebrew -> English only.

Flow per arm: one Hebrew sentence -> the model below -> one English sentence -> keyword scorer.
Each sentence passes exactly ONCE per arm (temp-0 determinism proven round 1). One model on GPU
at a time.

  hebrew->dictalm->english         DictaLM-3.0-1.7B, 2-shot + one-line grammar (round-4 config)
  hebrew->translategemma->english  TranslateGemma-4b-it, its native template on /completion
  hebrew->qwen3vl->english         Qwen3-VL-4B given the IDENTICAL 2-shot setup as DictaLM.
                                   Answers: does the VLM path need a separate translator at all?
                                   Proxy disclosed: scores restatement, not detection on images.

Scoring: keyword-group preservation (score_perception), reported overall and split by reference
depth (hops). Keyword presence cannot catch relation INVERSION -- the dump table is the ground
truth for that. Full dump: results/<date>-round5-dump.md."""
import json, os, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_bench as rb
import round4
from cases_indirect import INDIRECT_CASES
from cases_perception import score_perception

SMOKE = os.environ.get("ROUND5_SMOKE") == "1"
CASES = INDIRECT_CASES[:4] if SMOKE else INDIRECT_CASES
PORT = round4.PORT

def summarize(arm, translations):
    rows, by = [], {c[0]: c for c in CASES}
    for name, en, dt in translations:
        _, he, groups, hops = by[name]
        missed = score_perception(en, groups)
        rows.append({"case": name, "hops": hops, "he": he, "en": en, "t_ms": round(dt*1000),
                     "missed": ["|".join(g) for g in missed], "ok": not missed,
                     "groups_total": len(groups), "groups_kept": len(groups) - len(missed)})
    n, ok = len(rows), sum(1 for r in rows if r["ok"])
    lo, hi = rb.wilson(ok, n)
    gt = sum(r["groups_total"] for r in rows); gk = sum(r["groups_kept"] for r in rows)
    lat = [r["t_ms"] for r in rows]
    pcts = {f"p{p}": round(rb.pct(lat, p)) for p in (25, 50, 75, 95, 99)}; pcts["max"] = max(lat)
    by_hops = {}
    for h in sorted({r["hops"] for r in rows}):
        hr = [r for r in rows if r["hops"] == h]
        hgt = sum(r["groups_total"] for r in hr); hgk = sum(r["groups_kept"] for r in hr)
        by_hops[h] = {"n": len(hr), "ok": sum(1 for r in hr if r["ok"]),
                      "groups_kept": hgk, "groups_total": hgt}
    print(f"{arm}: {ok}/{n} all-groups ({ok/n:.0%}) wilson95 [{lo:.0%},{hi:.0%}]  "
          f"groups kept {gk}/{gt} ({gk/gt:.0%})", flush=True)
    print(f"  ms: " + "  ".join(f"{k}={v}" for k, v in pcts.items()), flush=True)
    for h, s in by_hops.items():
        print(f"  depth {h}: {s['ok']}/{s['n']} cases, groups {s['groups_kept']}/{s['groups_total']}", flush=True)
    return {"arm": arm, "ok": ok, "n": n, "wilson95": [round(lo,3), round(hi,3)],
            "groups_kept": gk, "groups_total": gt, "latency_ms": pcts,
            "by_depth": by_hops, "cases": rows}

def main():
    assert not rb.port_up(PORT) and not rb.port_up(rb.QWEN_PORT), "llama-server already running"
    t0 = time.time()
    results = []

    print(f"== [1/3] hebrew->dictalm->english: {len(CASES)} sentences, once each ==", flush=True)
    with rb.LlamaServer(round4.MODELS["dicta"], PORT):
        results.append(summarize("hebrew->dictalm->english", round4.translate_all(PORT, CASES)))

    print(f"== [2/3] hebrew->translategemma->english: {len(CASES)} sentences, once each ==", flush=True)
    with rb.LlamaServer(round4.MODELS["tgemma"], PORT, extra=("--chat-template", "gemma")):
        results.append(summarize("hebrew->translategemma->english", round4.tgemma_translate_all(PORT, CASES)))

    print(f"== [3/3] hebrew->qwen3vl->english: {len(CASES)} sentences, once each ==", flush=True)
    with rb.LlamaServer(round4.MODELS["qwen3vl"], PORT, extra=round4.QWEN3VL_EXTRA):
        results.append(summarize("hebrew->qwen3vl->english", round4.translate_all(PORT, CASES)))

    stamp = datetime.date.today().isoformat()
    out = os.path.join(HERE, "results", f"{stamp}-round5-results.json")
    json.dump({"arms": results, "smoke": SMOKE, "wall_s": round(time.time()-t0)},
              open(out, "w"), ensure_ascii=False, indent=1)

    dump = os.path.join(HERE, "results", f"{stamp}-round5-dump.md")
    with open(dump, "w") as f:
        f.write("# Round-5 multi-hop translations -- full dump for owner review\n\n")
        f.write("Check for relation INVERSION here; the keyword scorer cannot see it.\n\n")
        f.write("| case | depth | Hebrew | dictalm | qwen3vl | translategemma | missed (dictalm) | missed (qwen3vl) | missed (tgemma) |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        byarm = {r["arm"]: {c["case"]: c for c in r["cases"]} for r in results}
        d, q, g = byarm["hebrew->dictalm->english"], byarm["hebrew->qwen3vl->english"], byarm["hebrew->translategemma->english"]
        for name, he, groups, hops in CASES:
            f.write(f"| {name} | {hops} | {he} | {d[name]['en']} | {q[name]['en']} | {g[name]['en']} "
                    f"| {', '.join(d[name]['missed']) or '-'} | {', '.join(q[name]['missed']) or '-'} | {', '.join(g[name]['missed']) or '-'} |\n")

    print("\n| arm | all-groups kept | groups kept | p50 ms | p95 ms |")
    print("|---|---|---|---|---|")
    for r in sorted(results, key=lambda r: -r["ok"]):
        print(f"| {r['arm']} | {r['ok']}/{r['n']} ({r['ok']/r['n']:.0%}) "
              f"| {r['groups_kept']}/{r['groups_total']} ({r['groups_kept']/r['groups_total']:.0%}) "
              f"| {r['latency_ms']['p50']} | {r['latency_ms']['p95']} |")
    print(f"\nresults -> {out}\ndump -> {dump}\nwall {round(time.time()-t0)}s", flush=True)

if __name__ == "__main__":
    main()
