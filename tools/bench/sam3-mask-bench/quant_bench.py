#!/usr/bin/env python3
"""COLD end-to-end timing per quantization. Every mode runs with EMPTY torch.compile caches
(inductor + Triton), so the first detect() is a true cold compile -- the fresh-container number.

The orchestrator wipes and isolates the caches before each subprocess:
  TORCHINDUCTOR_CACHE_DIR + TRITON_CACHE_DIR -> fresh empty dirs, removed before each run.

    python3 quant_bench.py                # run all modes cold, write the table
    python3 quant_bench.py <mode> <out>   # worker (caches set by the orchestrator)
"""
import os, sys, json, time, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "candidates", "street-crowd-0.jpg")
sys.path.insert(0, "/root/groundstation/projects/integration_harden")
MODES = [("nf4", "nf4", False), ("bf16", "bf16", False), ("fp8", "fp8", False),
         ("bf16+compile", "bf16", True), ("fp8+compile", "fp8", True)]
REPS = 12
IND = "/tmp/cold_inductor"
TRI = "/tmp/cold_triton"


def worker(name, out):
    import cv2, numpy as np, torch
    from perception2 import Sam3Backend
    prec, comp = {m[0]: (m[1], m[2]) for m in MODES}[name]
    res = {"name": name}
    try:
        frame = cv2.imread(IMG)
        t = time.time()
        be = Sam3Backend(precision=prec, compile=comp)
        res["load_s"] = round(time.time() - t, 1)
        t = time.time()
        be.detect(frame, "person", conf=0.30)            # COLD first call (compiles if compile=True)
        res["cold_first_s"] = round(time.time() - t, 1)
        for _ in range(2):
            be.detect(frame, "person", conf=0.30)
        ms = []
        for _ in range(REPS):
            t = time.time(); d = be.detect(frame, "person", conf=0.30); ms.append((time.time()-t)*1000)
        res["warm_detect_p50_ms"] = round(float(np.percentile(ms, 50)), 1)
        res["vram_mib"] = round(torch.cuda.max_memory_allocated()/2**20)
        res["dets"] = len(d)
        res["to_first_result_s"] = round(res["load_s"] + res["cold_first_s"], 1)
    except Exception as e:
        res["error"] = repr(e)[:150]
    json.dump(res, open(out, "w"))
    print(f"[{name}] load {res.get('load_s','?')}s COLD-first {res.get('cold_first_s','?')}s "
          f"warm {res.get('warm_detect_p50_ms','ERR')}ms {res.get('error','')}", flush=True)


def main():
    import subprocess
    if len(sys.argv) == 3:
        worker(sys.argv[1], sys.argv[2]); return
    rows = []
    for name, _, _ in MODES:
        for d in (IND, TRI):
            shutil.rmtree(d, ignore_errors=True)          # wipe -> genuine cold compile
        env = dict(os.environ, TORCHINDUCTOR_CACHE_DIR=IND, TRITON_CACHE_DIR=TRI,
                   TORCHINDUCTOR_FX_GRAPH_CACHE="0")
        out = os.path.join(HERE, "results", f"_cold_{name.replace('+','_')}.json")
        print(f"=== {name} (caches wiped) ===", flush=True)
        subprocess.run([sys.executable, __file__, name, out], check=False, env=env)
        if os.path.exists(out):
            rows.append(json.load(open(out))); os.remove(out)
    for d in (IND, TRI):
        shutil.rmtree(d, ignore_errors=True)
    L = ["# SAM3 COLD end-to-end timing per quantization (RTX 5070, sm120)", "",
         "Inductor + Triton caches WIPED before every mode -- the true fresh-container cold start.",
         f"Fixed input street-crowd-0.jpg + concept 'person', {REPS} warm reps. `cold first` = the first",
         "detect(), i.e. the cold torch.compile build for compiled modes. `to first result` = load + cold",
         "first. `warm detect` = steady end-to-end detect() p50 after compile.", "",
         "| mode | load s | COLD first detect s | to first result s | warm detect p50 ms | VRAM MiB | dets |",
         "|------|-------:|--------------------:|------------------:|-------------------:|---------:|-----:|"]
    for r in rows:
        if "error" in r:
            L.append(f"| {r['name']} | - | - | - | ERR | - | {r['error'][:50]} |")
        else:
            L.append(f"| {r['name']} | {r['load_s']} | {r['cold_first_s']} | {r['to_first_result_s']} "
                     f"| {r['warm_detect_p50_ms']} | {r['vram_mib']} | {r['dets']} |")
    rep = "\n".join(L) + "\n"
    rp = os.path.join(HERE, "results", "quant-bench-latest.md")
    open(rp, "w").write(rep)
    print("\n" + rep + f"\n(written to {rp})")


if __name__ == "__main__":
    main()
