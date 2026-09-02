#!/usr/bin/env python3
"""Serving census: where does the VRAM go, and what can move to CPU?

Machine truth (owner 2026-09-02): 8 GiB VRAM (RTX 5070 Laptop), 16 GiB RAM. The desktop session
must survive, so this NEVER loads everything at once:
  1. Each model alone on GPU: load -> one warm request (forces compute buffers) -> read
     nvidia-smi -> unload. Per-component resident cost.
  2. Pairs, guarded: a second model loads ONLY if free VRAM >= its measured solo cost + 1 GiB
     margin. Skipped pairs are reported as "would not fit", which is itself the answer.
  3. CPU offload: DictaLM and TranslateGemma with -ngl 0, 20 real command translations each,
     p50/p95 vs the known GPU numbers. RAM-guarded (needs >= model size + 2 GiB available).
Not covered yet: OmDet+SAM2.1 vision pair (needs the smart-scene python env), whisper CT2
(faster-whisper not installed; lands with the ASR round). Reruns as-is on production hardware.
Usage: python3 census.py -> prints tables, writes results/<date>-census.json"""
import json, os, subprocess, sys, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.abspath(os.path.join(HERE, "..", "hebrew-command-bench"))
sys.path.insert(0, BENCH)
from bench import LlamaServer, chat, completion, translate_all, tgemma_translate_all, MODELS, QWEN3VL_EXTRA, PORT, pct, port_up
from prompts import TRANSLATE_SYS, TRANSLATE_SHOTS, LINE_GRAMMAR, TGEMMA_PROMPT
from cases_commands import CASES

MARGIN_MB = 1024

def vram():
    out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.total,memory.used,memory.free",
                                   "--format=csv,noheader,nounits"], text=True).strip()
    t, u, f = [int(x) for x in out.split(",")]
    return {"total": t, "used": u, "free": f}

def ram_avail_mb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"): return int(line.split()[1]) // 1024
    return 0

def warm(kind):
    if kind == "tgemma":
        completion(PORT, TGEMMA_PROMPT.format(he="טוס קדימה חמישה מטרים"), max_tokens=40, grammar=LINE_GRAMMAR)
    else:
        chat(PORT, TRANSLATE_SYS, "טוס קדימה חמישה מטרים", max_tokens=40,
             grammar=LINE_GRAMMAR, shots=TRANSLATE_SHOTS)

SPECS = {"dicta": (MODELS["dicta"], ()), "tgemma": (MODELS["tgemma"], ("--chat-template", "gemma")),
         "qwen3vl": (MODELS["qwen3vl"], QWEN3VL_EXTRA)}

def main():
    assert not port_up(PORT), "llama-server already running"
    res = {"gpu": subprocess.check_output(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True).strip(),
           "baseline": vram(), "solo": {}, "pairs": {}, "cpu": {}}
    print(f"GPU: {res['gpu']}  baseline: {res['baseline']}", flush=True)

    print("== solo residency (load -> warm request -> measure -> unload) ==", flush=True)
    for kind, (model, extra) in SPECS.items():
        with LlamaServer(model, extra=extra):
            warm(kind)
            time.sleep(1)
            v = vram()
            cost = v["used"] - res["baseline"]["used"]
            res["solo"][kind] = {"resident_mb": cost, "free_after_mb": v["free"]}
            print(f"  {kind:8s} resident {cost} MiB, free {v['free']} MiB", flush=True)
        time.sleep(2)

    print("== guarded pairs (second model loads only if free >= solo cost + margin) ==", flush=True)
    for pair in (("qwen3vl", "dicta"), ("qwen3vl", "tgemma")):
        a, b = pair
        with LlamaServer(*[SPECS[a][0]], extra=SPECS[a][1]):
            warm(a); time.sleep(1)
            free = vram()["free"]
            need = res["solo"][b]["resident_mb"] + MARGIN_MB
            if free < need:
                res["pairs"]["+".join(pair)] = {"fits": False, "free_mb": free, "need_mb": need}
                print(f"  {a}+{b}: SKIPPED, would not fit (free {free} < need {need})", flush=True)
                continue
            with LlamaServer(SPECS[b][0], port=PORT + 1, extra=SPECS[b][1]):
                time.sleep(1)
                v = vram()
                res["pairs"]["+".join(pair)] = {"fits": True, "used_mb": v["used"] - res["baseline"]["used"],
                                                "free_mb": v["free"]}
                print(f"  {a}+{b}: fits, combined {v['used']-res['baseline']['used']} MiB, free {v['free']} MiB", flush=True)
        time.sleep(2)

    print("== CPU offload latency (-ngl 0, 20 real command translations) ==", flush=True)
    sub = CASES[:20]
    for kind in ("dicta", "tgemma"):
        need_mb = os.path.getsize(SPECS[kind][0]) // 2**20 + 2048
        if ram_avail_mb() < need_mb:
            res["cpu"][kind] = {"skipped": f"RAM guard: available {ram_avail_mb()} < {need_mb} MiB"}
            print(f"  {kind}: SKIPPED by RAM guard", flush=True)
            continue
        model, extra = SPECS[kind]
        srv = LlamaServer(model, extra=extra)
        srv.args = [a for a in srv.args]
        i = srv.args.index("-ngl"); srv.args[i+1] = "0"
        i = srv.args.index("-dev"); del srv.args[i:i+2]
        threads = str(max(4, os.cpu_count() // 2))
        i = srv.args.index("--threads"); srv.args[i+1] = threads
        with srv:
            tr = tgemma_translate_all(PORT, sub) if kind == "tgemma" else translate_all(PORT, sub)
            lats = [round(dt*1000) for _, _, dt in tr]
            res["cpu"][kind] = {"threads": int(threads), "n": len(lats),
                                "p50_ms": round(pct(lats, 50)), "p95_ms": round(pct(lats, 95)),
                                "max_ms": max(lats), "ram_after_avail_mb": ram_avail_mb()}
            print(f"  {kind} CPU x{threads}t: p50 {res['cpu'][kind]['p50_ms']} p95 {res['cpu'][kind]['p95_ms']} max {max(lats)} ms", flush=True)
        time.sleep(2)

    stamp = datetime.date.today().isoformat()
    out = os.path.join(HERE, "results", f"{stamp}-census.json")
    json.dump(res, open(out, "w"), indent=1)
    print(f"\nresults -> {out}", flush=True)

if __name__ == "__main__":
    main()
