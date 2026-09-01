#!/usr/bin/env python3
"""Hebrew command-planning bench -- STRICTLY SEQUENTIAL (one model in GPU memory at a time),
GBNF-constrained, statistically reported.

Determinism: verified empirically 2026-09-01 -- 10 identical temp-0 requests produced 1 distinct
output, so each case runs ONCE; accuracy confidence comes from case count (Wilson 95% CI +
10k-case bootstrap), latency percentiles from the per-case samples.

Grammar: every PLANNING call (Qwen rows AND dicta-direct) carries a GBNF grammar that makes
malformed mission JSON structurally impossible -- same philosophy as llm_to_action's constrained
VLM output. DictaLM TRANSLATION gets a single-line grammar + 2-shot examples (grammar alone was
probed and does NOT remove preamble; the few-shot does). The seq2seq translators (opus/nllb)
cannot take few-shot -- each model runs at its best usable configuration, disclosed.

Phases: T) each translator alone on GPU, translate all cases, unload. P) Qwen alone, plan the
EN ceiling, raw-HE control, and each cached translation set.
Usage: python3 run_bench.py    -> results/<date>-sequential-results.json + stats tables."""
import gc, json, math, os, random, subprocess, sys, time, urllib.request, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cases import CASES, SYSTEM, parse, score

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BIN = os.path.join(ROOT, "build", "release", "shared", "dji", "bin")
QWEN_PORT, DICTA_PORT = 18090, 18091

PLANNER_GRAMMAR = r'''
root ::= "[" ws (action (ws "," ws action)*)? ws "]"
action ::= takeoff | land | flyby | spinby | delay
takeoff ::= "{" ws "\"type\"" ws ":" ws "\"takeoff\"" ws "}"
land ::= "{" ws "\"type\"" ws ":" ws "\"land\"" ws "}"
flyby ::= "{" ws "\"type\"" ws ":" ws "\"fly_by\"" (ws "," ws axis)+ ws "}"
axis ::= ("\"x\"" | "\"y\"" | "\"z\"") ws ":" ws num
spinby ::= "{" ws "\"type\"" ws ":" ws "\"spin_by\"" ws "," ws "\"degrees\"" ws ":" ws num ws "}"
delay ::= "{" ws "\"type\"" ws ":" ws "\"delay\"" ws "," ws "\"seconds\"" ws ":" ws num ws "}"
num ::= "-"? [0-9]+ ("." [0-9]+)?
ws ::= [ \t\n]*
'''
LINE_GRAMMAR = r'root ::= [^\n\r]+'
TRANSLATE_SYS = ("You are a translation engine. Translate the user's Hebrew drone command to "
                 "English. Output ONLY the English translation, nothing else.")
TRANSLATE_SHOTS = [("טוס שמאלה שישה מטרים", "Fly left six meters"),
                   ("עצור במקום", "Stop in place")]
PLANNER_SHOTS = [
    ("fly left 12 meters", '[{"type":"fly_by","y":-12}]'),
    ("go down 2 meters then fly forward 6 meters", '[{"type":"fly_by","z":-2},{"type":"fly_by","x":6}]'),
    ("do not fly up", "[]"),
    ("what's your altitude", "[]"),
    ("take off, rise 4 meters, turn 90 degrees clockwise, fly forward 6 meters, and land",
     '[{"type":"takeoff"},{"type":"fly_by","z":4},{"type":"spin_by","degrees":90},{"type":"fly_by","x":6},{"type":"land"}]'),
]
PLANNER_SHOTS_HE = [
    ("טוס שמאלה שנים עשר מטרים", '[{"type":"fly_by","y":-12}]'),
    ("רד שני מטרים ואז טוס קדימה שישה מטרים", '[{"type":"fly_by","z":-2},{"type":"fly_by","x":6}]'),
    ("אל תטוס למעלה", "[]"),
    ("מה הגובה שלך", "[]"),
    ("המראה, עלה ארבעה מטרים, הסתובב תשעים מעלות עם כיוון השעון, טוס קדימה שישה מטרים ונחת",
     '[{"type":"takeoff"},{"type":"fly_by","z":4},{"type":"spin_by","degrees":90},{"type":"fly_by","x":6},{"type":"land"}]'),
]

def port_up(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
        return True
    except Exception:
        return False

def chat(port, system, user, max_tokens=300, grammar=None, shots=(), retries=90):
    msgs = [{"role": "system", "content": system}]
    for u, a in shots:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    msgs.append({"role": "user", "content": user})
    payload = {"messages": msgs, "max_tokens": max_tokens, "temperature": 0.0}
    if grammar: payload["grammar"] = grammar
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 json.dumps(payload).encode(), {"Content-Type": "application/json"})
    for i in range(retries):                       # 503 while the model loads
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)["choices"][0]["message"]["content"], time.time() - t0
        except urllib.error.HTTPError as e:
            if e.code == 503 and i < retries - 1: time.sleep(1); continue
            raise
    raise RuntimeError("server never ready")

class LlamaServer:
    def __init__(self, model, port, extra=()):
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

def torch_translate_all(kind):
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    assert torch.cuda.is_available(), "GPU required -- no CPU fallbacks in this bench"
    path = {"opus": "/root/models/translate/opus-mt-tc-big-he-en",
            "nllb": "/root/models/translate/nllb-200-distilled-600M"}[kind]
    tok = AutoTokenizer.from_pretrained(path)
    mod = AutoModelForSeq2SeqLM.from_pretrained(path).to("cuda").eval()
    kw = {}
    if kind == "nllb":
        tok.src_lang = "heb_Hebr"
        kw["forced_bos_token_id"] = tok.convert_tokens_to_ids("eng_Latn")
    out = []
    for name, he, en, exp in CASES:
        t0 = time.time()
        ids = tok(he, return_tensors="pt").to("cuda")
        with torch.no_grad():
            gen = mod.generate(**ids, max_new_tokens=80, num_beams=1, **kw)
        out.append((name, tok.decode(gen[0], skip_special_tokens=True), time.time() - t0))
    vram = torch.cuda.memory_allocated() / 2**20
    del mod, tok
    gc.collect(); torch.cuda.empty_cache()
    return out, vram

def completion(port, prompt, max_tokens=80, grammar=None, retries=90):
    payload = {"prompt": prompt, "n_predict": max_tokens, "temperature": 0.0}
    if grammar: payload["grammar"] = grammar
    req = urllib.request.Request(f"http://127.0.0.1:{port}/completion",
                                 json.dumps(payload).encode(), {"Content-Type": "application/json"})
    for i in range(retries):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)["content"], time.time() - t0
        except urllib.error.HTTPError as e:
            if e.code == 503 and i < retries - 1: time.sleep(1); continue
            raise
    raise RuntimeError("server never ready")

def plan_all(port, texts, shots=()):
    rows, by_name = [], {c[0]: c for c in CASES}
    for name, text, t_tr in texts:
        out, t_plan = chat(port, SYSTEM, text, grammar=PLANNER_GRAMMAR, shots=shots)
        rows.append({"case": name, "score": score(parse(out), by_name[name][3]), "input": text,
                     "t_translate_ms": round(t_tr * 1000), "t_plan_ms": round(t_plan * 1000),
                     "out": (out or "")[:200]})
    return rows

def pct(xs, p):
    xs = sorted(xs); k = (len(xs) - 1) * p / 100.0
    f = math.floor(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

def wilson(ok, n, z=1.96):
    p = ok / n; d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return centre - half, centre + half

def summarize(name, rows):
    n = len(rows)
    oks = [1 if r["score"].startswith(("CORRECT", "valid")) else 0 for r in rows]
    ok = sum(oks)
    lo, hi = wilson(ok, n)
    rng = random.Random(42)
    boots = sorted(sum(rng.choices(oks, k=n)) / n for _ in range(10000))
    e2e = [r["t_translate_ms"] + r["t_plan_ms"] for r in rows]
    lat = {f"p{p}": round(pct(e2e, p)) for p in (25, 50, 75, 95, 99)}
    lat["max"] = max(e2e)
    tr = [r["t_translate_ms"] for r in rows]
    lat_tr = {f"p{p}": round(pct(tr, p)) for p in (25, 50, 75, 95, 99)}; lat_tr["max"] = max(tr)
    print(f"{name}: {ok}/{n} = {ok/n:.1%}  wilson95 [{lo:.1%}, {hi:.1%}]  "
          f"boot95 [{boots[249]:.1%}, {boots[9749]:.1%}]", flush=True)
    print(f"  e2e ms: " + "  ".join(f"{k}={v}" for k, v in lat.items()), flush=True)
    fails = [r for r in rows if not r["score"].startswith(("CORRECT", "valid"))]
    for r in fails[:14]:
        print(f"    FAIL {r['case']:14s} {r['score']:24s} in={r['input'][:55]!r}", flush=True)
    if len(fails) > 14: print(f"    ... +{len(fails)-14} more fails (see json)", flush=True)
    return {"pipeline": name, "ok": ok, "n": n, "acc": ok / n,
            "wilson95": [round(lo, 3), round(hi, 3)],
            "bootstrap95": [round(boots[249], 3), round(boots[9749], 3)],
            "latency_e2e_ms": lat, "latency_translate_ms": lat_tr, "cases": rows}

def main():
    assert not port_up(QWEN_PORT) and not port_up(DICTA_PORT), \
        "a llama-server is already running -- stop it first; this bench is strictly sequential"
    results, cache = [], {}

    for kind in ("opus", "nllb"):
        print(f"== translate: {kind} (alone on GPU) ==", flush=True)
        cache[kind], vram = torch_translate_all(kind)
        print(f"  {kind}: {len(cache[kind])} translations, VRAM {vram:.0f} MiB", flush=True)

    print("== translate: madlad400-3b (alone on GPU, /completion + <2en>) ==", flush=True)
    with LlamaServer("/root/models/translate/madlad400-3b-mt-gguf/madlad400-3b-mt-q4_k_m.gguf", DICTA_PORT):
        tr = []
        for name, he, en, exp in CASES:
            t, dt = completion(DICTA_PORT, f"<2en> {he}", grammar=LINE_GRAMMAR)
            tr.append((name, t.strip(), dt))
        cache["madlad"] = tr

    print("== translate (few-shot + line grammar) + direct-plan-fs (grammar): dicta ==", flush=True)
    with LlamaServer("/root/models/asr/dictalm-3-1.7b/dictalm-3.0-1.7b-instruct-q4_k_m.gguf", DICTA_PORT):
        tr = []
        for name, he, en, exp in CASES:
            t, dt = chat(DICTA_PORT, TRANSLATE_SYS, he, max_tokens=80,
                         grammar=LINE_GRAMMAR, shots=TRANSLATE_SHOTS)
            tr.append((name, t.strip(), dt))
        cache["dicta"] = tr
        results.append(summarize("dicta-direct-fs",
                                 plan_all(DICTA_PORT, [(n, he, 0.0) for n, he, _, _ in CASES],
                                          shots=PLANNER_SHOTS_HE)))

    print("== plan: qwen (alone on GPU, grammar-constrained) ==", flush=True)
    with LlamaServer("/root/models/vlm/Qwen3-VL-4B-Instruct/Qwen3-VL-4B-Instruct-Q4_K_M.gguf",
                     QWEN_PORT, extra=("--mmproj", "/root/models/vlm/Qwen3-VL-4B-Instruct/mmproj-BF16.gguf",
                                       "--flash-attn", "on", "--cache-type-k", "q4_0", "--cache-type-v", "q4_0")):
        results.append(summarize("qwen-en", plan_all(QWEN_PORT, [(n, en, 0.0) for n, he, en, _ in CASES])))
        results.append(summarize("qwen-en-fs", plan_all(QWEN_PORT, [(n, en, 0.0) for n, he, en, _ in CASES],
                                                        shots=PLANNER_SHOTS)))
        for kind in ("opus", "nllb", "madlad", "dicta"):
            results.append(summarize(f"{kind}->qwen", plan_all(QWEN_PORT, cache[kind])))
        results.append(summarize("dicta->qwen-fs", plan_all(QWEN_PORT, cache["dicta"], shots=PLANNER_SHOTS)))

    stamp = datetime.date.today().isoformat()
    out = os.path.join(HERE, "results", f"{stamp}-sequential-results.json")
    json.dump(results, open(out, "w"), ensure_ascii=False, indent=1)
    print("\n| pipeline | acc | wilson95 | p25 | p50 | p75 | p95 | p99 | max |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(results, key=lambda r: -r["acc"]):
        L = r["latency_e2e_ms"]
        print(f"| {r['pipeline']} | {r['ok']}/{r['n']} ({r['acc']:.0%}) "
              f"| [{r['wilson95'][0]:.0%}, {r['wilson95'][1]:.0%}] "
              f"| {L['p25']} | {L['p50']} | {L['p75']} | {L['p95']} | {L['p99']} | {L['max']} |")
    print(f"\nresults -> {out}", flush=True)

if __name__ == "__main__":
    main()
