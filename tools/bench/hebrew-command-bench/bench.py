#!/usr/bin/env python3
"""The Hebrew command-and-perception benchmark. One file, one command:

    python3 bench.py            full run, ~6 min: prints the table, writes
                                results/<date>-bench-results.json + -bench-dump.md
    python3 bench.py --smoke    ~30 s plumbing check on a 6+6 case slice
    python3 bench.py --refine   adds the refine arm (measured worse in round 6; kept for reruns)
    python3 bench.py --audit    offline scorer audit only (no GPU): every hand-written English
                                reference must satisfy its own keyword groups

What it measures (the round-6 design; earlier rounds live in git history + results/):
  COMMANDS   the 190 movement cases (cases_commands.py).
             Flow: text -> [translator] -> REVISED_PROMPT on Qwen3-VL -> mission JSON -> scorer.
  PERCEPTION the 100 multi-hop cases (cases_perception.py).
             Flow: Hebrew -> [translator] -> English -> keyword-group scorer.
             No planner: these route to the VLM in the real system.

Arms: control-perfect-english (hand-written EN into the planner; reference text for perception),
dictalm-alone, translategemma-alone, qwen3vl-alone, split-dictalm-commands+translategemma-
perception (re-aggregation of cached rows, zero new compute), and optionally refine.

Method invariants (established rounds 1-6): temp 0, one pass per case (determinism proven:
10 identical requests -> 1 output), GBNF on every planning call, strictly sequential GPU
(3 model loads: DictaLM, TranslateGemma, Qwen3-VL), Wilson 95% + exact McNemar, latency
percentiles as columns. Prompts and grammars live in prompts.py."""
import argparse, datetime, json, math, os, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from prompts import (REVISED_PROMPT, PLANNER_SHOTS_D, PLANNER_SHOTS_D_HE, HE_SIGN_ADDENDUM, WIRE_GRAMMAR, LINE_GRAMMAR,
                     TRANSLATE_SYS, TRANSLATE_SHOTS, TGEMMA_PROMPT, TGEMMA_REFINE)
from cases_commands import CASES as CMD_CASES, score
from cases_perception import PERC100, SLANG20, score_perception, check_refs

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BIN = os.path.join(ROOT, "build", "release", "shared", "dji", "bin")
PORT, PORT2 = 18091, 18090
MODELS = {
 "dicta":   "/root/models/asr/dictalm-3-1.7b/dictalm-3.0-1.7b-instruct-q4_k_m.gguf",
 "tgemma":  "/root/models/translate/translategemma-4b-it-gguf/translategemma-4b-it.Q4_K_M.gguf",
 "qwen3vl": "/root/models/vlm/Qwen3-VL-4B-Instruct/Qwen3-VL-4B-Instruct-Q4_K_M.gguf",
}
QWEN3VL_EXTRA = ("--mmproj", "/root/models/vlm/Qwen3-VL-4B-Instruct/mmproj-BF16.gguf",
                 "--flash-attn", "on", "--cache-type-k", "q4_0", "--cache-type-v", "q4_0")

# ---------- server + request plumbing ----------
def port_up(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
        return True
    except Exception:
        return False

class LlamaServer:
    def __init__(self, model, port=PORT, extra=()):
        self.args = [os.path.join(BIN, "llama-server"), "-m", model,
                     "-dev", "Vulkan0", "-ngl", "99", "-c", "4096", "--temp", "0.0",
                     "--host", "127.0.0.1", "--port", str(port), "--threads", "1", *extra]
        self.port, self.proc = port, None
    def __enter__(self):
        env = dict(os.environ, LD_LIBRARY_PATH=BIN + ":" + os.environ.get("LD_LIBRARY_PATH", ""))
        self.proc = subprocess.Popen(self.args, env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            if port_up(self.port): return self
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server died on startup (port {self.port})")
            time.sleep(1)
        raise RuntimeError(f"llama-server not healthy after 120s (port {self.port})")
    def __exit__(self, *a):
        self.proc.terminate()
        try: self.proc.wait(timeout=15)
        except Exception: self.proc.kill(); self.proc.wait()
        for _ in range(20):
            if not port_up(self.port): break
            time.sleep(0.5)
        time.sleep(1)

def _request(url, payload, retries=90):
    req = urllib.request.Request(url, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    for i in range(retries):                       # 503 while the model loads
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r), time.time() - t0
        except urllib.error.HTTPError as e:
            if e.code == 503 and i < retries - 1: time.sleep(1); continue
            raise
    raise RuntimeError("server never ready")

def chat(port, system, user, max_tokens=300, grammar=None, shots=()):
    msgs = [{"role": "system", "content": system}]
    for u, a in shots:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    msgs.append({"role": "user", "content": user})
    payload = {"messages": msgs, "max_tokens": max_tokens, "temperature": 0.0}
    if grammar: payload["grammar"] = grammar
    out, dt = _request(f"http://127.0.0.1:{port}/v1/chat/completions", payload)
    return out["choices"][0]["message"]["content"], dt

def completion(port, prompt, max_tokens=80, grammar=None):
    payload = {"prompt": prompt, "n_predict": max_tokens, "temperature": 0.0}
    if grammar: payload["grammar"] = grammar
    out, dt = _request(f"http://127.0.0.1:{port}/completion", payload)
    return out["content"], dt

# ---------- stages ----------
def translate_all(port, cases):
    out = []
    for c in cases:
        t, dt = chat(port, TRANSLATE_SYS, c[1], max_tokens=80,
                     grammar=LINE_GRAMMAR, shots=TRANSLATE_SHOTS)
        out.append((c[0], t.strip(), dt))
    return out

def tgemma_translate_all(port, cases):
    out = []
    for c in cases:
        t, dt = completion(port, TGEMMA_PROMPT.format(he=c[1]), max_tokens=80, grammar=LINE_GRAMMAR)
        out.append((c[0], t.strip(), dt))
    return out

ALLOWED_D = {"takeoff": set(), "land": set(), "fly_by": {"dx","dy","dz","velocity"},
             "spin_by": {"degrees"}, "delay": {"seconds"}}
import re
def parse_d(out):
    m = re.search(r"\[.*\]", out or "", re.S)
    if not m: return None
    try: arr = json.loads(m.group(0))
    except Exception: return None
    if not isinstance(arr, list): return None
    norm = []
    for a in arr:
        if not isinstance(a, dict) or a.get("type") not in ALLOWED_D: return None
        if any(k != "type" and k not in ALLOWED_D[a["type"]] for k in a): return None
        b = {"type": a["type"]}
        for src, dst in (("dx","x"), ("dy","y"), ("dz","z"), ("degrees","degrees"), ("seconds","seconds")):
            if src in a: b[dst] = a[src]
        norm.append(b)          # velocity dropped: scorer judges geometry, the app clamps velocity
    return norm

def plan_all(port, texts, cmd_cases):
    rows, by_name = [], {c[0]: c for c in cmd_cases}
    for name, text, t_tr in texts:
        out, t_plan = chat(port, REVISED_PROMPT, text, grammar=WIRE_GRAMMAR, shots=PLANNER_SHOTS_D)
        rows.append({"case": name, "score": score(parse_d(out), by_name[name][3]), "input": text,
                     "t_translate_ms": round(t_tr * 1000), "t_plan_ms": round(t_plan * 1000),
                     "out": (out or "")[:200]})
    return rows

# ---------- stats ----------
def pct(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p / 100.0
    f = math.floor(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

def wilson(ok, n, z=1.96):
    p = ok / n; d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half

def mcnemar(rows_a, rows_b, okfn):
    a = {r["case"]: okfn(r) for r in rows_a}; b = {r["case"]: okfn(r) for r in rows_b}
    n01 = sum(1 for c in a if a[c] and not b[c]); n10 = sum(1 for c in a if not a[c] and b[c])
    n = n01 + n10
    p = 1.0 if n == 0 else min(1.0, sum(math.comb(n, k) for k in range(min(n01, n10)+1)) / 2**n * 2)
    return {"only_a": n01, "only_b": n10, "p": round(p, 6)}

def cmd_summarize(arm, rows):
    n = len(rows)
    ok = sum(1 for r in rows if r["score"].startswith(("CORRECT", "valid")))
    lo, hi = wilson(ok, n)
    e2e = [r["t_translate_ms"] + r["t_plan_ms"] for r in rows]
    lat = {f"p{p}": round(pct(e2e, p)) for p in (25, 50, 75, 95, 99)}; lat["max"] = max(e2e)
    print(f"  commands {arm}: {ok}/{n} ({ok/n:.1%}) wilson95 [{lo:.1%},{hi:.1%}]  "
          + "  ".join(f"{k}={v}" for k, v in lat.items()), flush=True)
    fails = [r for r in rows if not r["score"].startswith(("CORRECT", "valid"))]
    for r in fails[:12]:
        print(f"    FAIL {r['case']:14s} {r['score']:24s} in={r['input'][:55]!r}", flush=True)
    if len(fails) > 12: print(f"    ... +{len(fails)-12} more fails (see json)", flush=True)
    return {"ok": ok, "n": n, "acc": ok / n, "wilson95": [round(lo,3), round(hi,3)],
            "latency_e2e_ms": lat, "cases": rows}

def perc_summarize(arm, translations, perc_cases):
    rows, by = [], {c[0]: c for c in perc_cases}
    for name, en, dt in translations:
        _, he, ref, groups, hops = by[name]
        missed = score_perception(en, groups)
        rows.append({"case": name, "hops": hops, "he": he, "en": en, "t_ms": round(dt*1000),
                     "missed": ["|".join(g) for g in missed], "ok": not missed,
                     "groups_total": len(groups), "groups_kept": len(groups) - len(missed)})
    n, ok = len(rows), sum(1 for r in rows if r["ok"])
    lo, hi = wilson(ok, n)
    gt = sum(r["groups_total"] for r in rows); gk = sum(r["groups_kept"] for r in rows)
    lat = [r["t_ms"] for r in rows]
    pcts = {f"p{p}": round(pct(lat, p)) for p in (25, 50, 75, 95, 99)}; pcts["max"] = max(lat)
    by_hops = {h: {"n": len(hr), "ok": sum(1 for r in hr if r["ok"])}
               for h in sorted({r["hops"] for r in rows})
               for hr in [[r for r in rows if r["hops"] == h]]}
    print(f"  perception {arm}: {ok}/{n} ({ok/n:.0%}) wilson95 [{lo:.0%},{hi:.0%}] "
          f"groups {gk}/{gt} ({gk/gt:.0%}) depth " +
          " ".join(f"d{h}:{s['ok']}/{s['n']}" for h, s in by_hops.items()), flush=True)
    return {"ok": ok, "n": n, "wilson95": [round(lo,3), round(hi,3)],
            "groups_kept": gk, "groups_total": gt, "latency_ms": pcts,
            "by_depth": by_hops, "cases": rows}

def direct_probe():
    """Hebrew text straight into DictaLM as the PLANNER (no translation, no Qwen). The
    intent-parser lane's step 1: round 3 scored 80% with the old prompt; this is the revised
    prompt + Hebrew shots + dx grammar. Paired against the stored round-6 command rows."""
    t0 = time.time()
    print(f"== direct-Hebrew planning on DictaLM: {len(CMD_CASES)} commands ==", flush=True)
    rows, by_name = [], {c[0]: c for c in CMD_CASES}
    with LlamaServer(MODELS["dicta"]):
        for name, he, en, exp in CMD_CASES:
            out, dt = chat(PORT, REVISED_PROMPT + HE_SIGN_ADDENDUM, he, grammar=WIRE_GRAMMAR, shots=PLANNER_SHOTS_D_HE)
            rows.append({"case": name, "score": score(parse_d(out), exp), "input": he,
                         "t_translate_ms": 0, "t_plan_ms": round(dt*1000), "out": (out or "")[:200]})
    s = cmd_summarize("dictalm-direct-plan", rows)
    ref = None
    for f in sorted(os.listdir(os.path.join(HERE, "results"))):
        if f.endswith("-bench-results.json"): ref = os.path.join(HERE, "results", f)
    ok_cmd = lambda r: r["score"].startswith(("CORRECT", "valid"))
    mn = {}
    if ref:
        R = json.load(open(ref))["arms"]
        for base in ("dictalm-alone", "control-perfect-english"):
            mn[f"direct vs {base}"] = mcnemar(rows, R[base]["commands"]["cases"], ok_cmd)
            print(f"McNemar direct vs {base}: {mn[f'direct vs {base}']}", flush=True)
    stamp = datetime.date.today().isoformat()
    out = os.path.join(HERE, "results", f"{stamp}-direct-results.json")
    json.dump({"arm": s, "mcnemar": mn, "vs": ref, "wall_s": round(time.time()-t0)},
              open(out, "w"), ensure_ascii=False, indent=1)
    print(f"results -> {out}\nwall {round(time.time()-t0)}s", flush=True)

def slang_probe():
    """Hebrew military phraseology -> each translator once -> keyword scorer, split by class."""
    t0 = time.time()
    out = {}
    print(f"== slang probe: {len(SLANG20)} sentences x 3 translators ==", flush=True)
    with LlamaServer(MODELS["dicta"]):
        out["hebrew->dictalm->english"] = translate_all(PORT, SLANG20)
    with LlamaServer(MODELS["tgemma"], extra=("--chat-template", "gemma")):
        out["hebrew->translategemma->english"] = tgemma_translate_all(PORT, SLANG20)
    with LlamaServer(MODELS["qwen3vl"], extra=QWEN3VL_EXTRA):
        out["hebrew->qwen3vl->english"] = translate_all(PORT, SLANG20)

    by = {c[0]: c for c in SLANG20}
    arms = {}
    for arm, tr in out.items():
        rows = []
        for name, en, dt in tr:
            _, he, ref, groups, klass = by[name]
            missed = score_perception(en, groups)
            rows.append({"case": name, "class": klass, "he": he, "en": en, "t_ms": round(dt*1000),
                         "missed": ["|".join(g) for g in missed], "ok": not missed})
        n, ok = len(rows), sum(1 for r in rows if r["ok"])
        byc = {k: (sum(1 for r in rows if r["class"] == k and r["ok"]),
                   sum(1 for r in rows if r["class"] == k)) for k in ("idiom", "acronym")}
        print(f"  {arm}: {ok}/{n}  idiom {byc['idiom'][0]}/{byc['idiom'][1]}  "
              f"acronym {byc['acronym'][0]}/{byc['acronym'][1]}", flush=True)
        arms[arm] = {"ok": ok, "n": n, "by_class": byc, "cases": rows}

    stamp = datetime.date.today().isoformat()
    outp = os.path.join(HERE, "results", f"{stamp}-slang-results.json")
    json.dump({"arms": arms, "wall_s": round(time.time()-t0)}, open(outp, "w"),
              ensure_ascii=False, indent=1)
    dump = os.path.join(HERE, "results", f"{stamp}-slang-dump.md")
    with open(dump, "w") as f:
        f.write("# Military-phraseology translations -- full dump for owner review\n\n")
        f.write("| case | class | Hebrew | reference | dictalm | translategemma | qwen3vl | missed d/t/q |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        P = {a: {r["case"]: r for r in arms[a]["cases"]} for a in arms}
        d, t, q = (P[a] for a in ("hebrew->dictalm->english", "hebrew->translategemma->english",
                                  "hebrew->qwen3vl->english"))
        for name, he, ref, groups, klass in SLANG20:
            miss = " / ".join((", ".join(x[name]["missed"]) or "-") for x in (d, t, q))
            f.write(f"| {name} | {klass} | {he} | {ref} | {d[name]['en']} | {t[name]['en']} | {q[name]['en']} | {miss} |\n")
    print(f"\nresults -> {outp}\ndump -> {dump}\nwall {round(time.time()-t0)}s", flush=True)

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="6+6 case slice, ~30 s")
    ap.add_argument("--refine", action="store_true", help="add the refine arm (rejected round 6)")
    ap.add_argument("--audit", action="store_true", help="offline scorer audit, no GPU")
    ap.add_argument("--direct", action="store_true", help="direct-Hebrew planning on DictaLM "
                    "(revised prompt + Hebrew shots, no translation) vs stored round-6 rows")
    ap.add_argument("--slang", action="store_true", help="military-phraseology probe only (~3 min): "
                    "SLANG20 through the three translators, split idiom vs acronym class")
    args = ap.parse_args()

    bad = check_refs()
    assert not bad, f"reference/group mismatch: {bad}"
    if args.audit:
        print("scorer audit CLEAN: all 100 references satisfy their own keyword groups")
        return
    assert not port_up(PORT) and not port_up(PORT2), \
        "a llama-server is already running -- stop it first; this bench is strictly sequential"
    if args.slang:
        return slang_probe()
    if args.direct:
        return direct_probe()
    CMD = CMD_CASES[:6] if args.smoke else CMD_CASES
    PERC = PERC100[:6] if args.smoke else PERC100
    t0 = time.time()

    print(f"== [1/3] DictaLM: translate {len(CMD)} commands + {len(PERC)} perception ==", flush=True)
    with LlamaServer(MODELS["dicta"]):
        cmd_dicta = translate_all(PORT, CMD)
        perc_dicta = translate_all(PORT, PERC)

    print(f"== [2/3] TranslateGemma: translate {len(CMD)}+{len(PERC)}"
          + (f", refine {len(PERC)} drafts" if args.refine else "") + " ==", flush=True)
    with LlamaServer(MODELS["tgemma"], extra=("--chat-template", "gemma")):
        cmd_tg = tgemma_translate_all(PORT, CMD)
        perc_tg = tgemma_translate_all(PORT, PERC)
        perc_refine = []
        if args.refine:
            draft = {n: (en, dt) for n, en, dt in perc_dicta}
            for name, he, ref, groups, hops in PERC:
                t, dt = completion(PORT, TGEMMA_REFINE.format(he=he, draft=draft[name][0]),
                                   max_tokens=100, grammar=LINE_GRAMMAR)
                perc_refine.append((name, t.strip(), dt + draft[name][1]))  # latency: draft + refine

    print(f"== [3/3] Qwen3-VL: translate {len(CMD)}+{len(PERC)}, then plan the command sets ==", flush=True)
    arms = {}
    with LlamaServer(MODELS["qwen3vl"], extra=QWEN3VL_EXTRA):
        cmd_qw = translate_all(PORT, CMD)
        perc_qw = translate_all(PORT, PERC)
        en_ref = [(c[0], c[2], 0.0) for c in CMD]
        for arm, cmd_texts, perc_rows in (
                ("control-perfect-english", en_ref, [(c[0], c[2], 0.0) for c in PERC]),
                ("dictalm-alone", cmd_dicta, perc_dicta),
                ("translategemma-alone", cmd_tg, perc_tg),
                ("qwen3vl-alone", cmd_qw, perc_qw)):
            print(f"-- arm {arm}", flush=True)
            arms[arm] = {"commands": cmd_summarize(arm, plan_all(PORT, cmd_texts, CMD)),
                         "perception": perc_summarize(arm, perc_rows, PERC)}
        if args.refine:
            print("-- arm refine (perception only new; commands shared with dictalm-alone)", flush=True)
            arms["refine-dictalm-draft->translategemma-final"] = {
                "commands": arms["dictalm-alone"]["commands"],
                "perception": perc_summarize("refine", perc_refine, PERC),
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
    }
    if args.refine:
        R = arms["refine-dictalm-draft->translategemma-final"]["perception"]["cases"]
        mn["perception refine vs translategemma"] = mcnemar(R, arms["translategemma-alone"]["perception"]["cases"], ok_perc)
        mn["perception refine vs dictalm"] = mcnemar(R, arms["dictalm-alone"]["perception"]["cases"], ok_perc)
    for k, v in mn.items(): print(f"McNemar {k}: {v}", flush=True)

    stamp = datetime.date.today().isoformat()
    out = os.path.join(HERE, "results", f"{stamp}-bench-results.json")
    json.dump({"arms": arms, "mcnemar": mn, "smoke": args.smoke, "wall_s": round(time.time()-t0)},
              open(out, "w"), ensure_ascii=False, indent=1)

    dump = os.path.join(HERE, "results", f"{stamp}-bench-dump.md")
    with open(dump, "w") as f:
        f.write("# Perception translations -- full dump for owner review\n\n")
        f.write("Check relation inversions here; the keyword scorer cannot see them.\n\n")
        cols = ["dictalm-alone", "translategemma-alone", "qwen3vl-alone"] + \
               (["refine-dictalm-draft->translategemma-final"] if args.refine else [])
        f.write("| case | depth | Hebrew | reference | " + " | ".join(cols) + " | missed |\n")
        f.write("|" + "---|" * (5 + len(cols)) + "\n")
        P = {a: {c["case"]: c for c in arms[a]["perception"]["cases"]} for a in cols}
        for name, he, ref, groups, hops in PERC:
            ens = " | ".join(P[a][name]["en"] for a in cols)
            miss = " / ".join((", ".join(P[a][name]["missed"]) or "-") for a in cols)
            f.write(f"| {name} | {hops} | {he} | {ref} | {ens} | {miss} |\n")

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
