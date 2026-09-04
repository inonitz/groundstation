#!/usr/bin/env python3
"""End-to-end per-quantization timing through the real Sam3Backend.

Reports, per mode: model load (ready to infer), first detect() (= compile for compiled modes),
and warm end-to-end detect() p50 (PIL + processor + forward + post_process -- what production feels).
One mode per subprocess (one model resident). Fixed input street-crowd-0.jpg + concept 'person'.

    python3 quant_e2e.py                 # run all modes, write the table
    python3 quant_e2e.py <mode> <out>    # worker
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "candidates", "street-crowd-0.jpg")
sys.path.insert(0, "/root/groundstation/projects/integration_harden")
# (name, precision, compile)
MODES = [("nf4", "nf4", False), ("bf16", "bf16", False), ("fp8", "fp8", False),
         ("bf16+compile", "bf16", True), ("fp8+compile", "fp8", True)]
REPS = 15


def worker(name, out):
    import cv2, numpy as np, torch
    from perception2 import Sam3Backend
    prec, comp = {m[0]: (m[1], m[2]) for m in MODES}[name]
    res = {"name": name}
    try:
        frame = cv2.imread(IMG)
        t = time.time()
        be = Sam3Backend(precision=prec, compile=comp)   # load + quantize (+ compile wrap)
        res["load_s"] = round(time.time() - t, 1)
        t = time.time()
        be.detect(frame, "person", conf=0.30)            # first call: compiles if compile=True
        res["first_detect_s"] = round(time.time() - t, 1)
        for _ in range(2):
            be.detect(frame, "person", conf=0.30)        # settle
        ms = []
        for _ in range(REPS):
            t = time.time(); d = be.detect(frame, "person", conf=0.30); ms.append((time.time()-t)*1000)
        res["warm_detect_p50_ms"] = round(float(np.percentile(ms, 50)), 1)
        res["warm_detect_p90_ms"] = round(float(np.percentile(ms, 90)), 1)
        res["vram_mib"] = round(torch.cuda.max_memory_allocated()/2**20)
        res["dets"] = len(d)
        res["time_to_first_result_s"] = round(res["load_s"] + res["first_detect_s"], 1)
    except Exception as e:
        res["error"] = repr(e)[:150]
    json.dump(res, open(out, "w"))
    print(f"[{name}] load {res.get('load_s','?')}s compile/first {res.get('first_detect_s','?')}s "
          f"warm {res.get('warm_detect_p50_ms','ERR')}ms {res.get('error','')}", flush=True)


def main():
    import subprocess
    if len(sys.argv) == 3:
        worker(sys.argv[1], sys.argv[2]); return
    rows = []
    for name, _, _ in MODES:
        out = os.path.join(HERE, "results", f"_e2e_{name.replace('+','_')}.json")
        print(f"=== {name} ===", flush=True)
        subprocess.run([sys.executable, __file__, name, out], check=False, env=dict(os.environ))
        if os.path.exists(out):
            rows.append(json.load(open(out))); os.remove(out)
    L = ["# SAM3 end-to-end timing per quantization (RTX 5070, sm120), via Sam3Backend", "",
         f"Fixed input street-crowd-0.jpg + concept 'person', {REPS} warm reps. `load` = model ready.",
         "`compile/first` = first detect() (the torch.compile build for compiled modes). `warm detect`",
         "= end-to-end detect() p50 (PIL + processor + forward + post_process). `to first result` =",
         "load + first detect.", "",
         "| mode | load s | compile/first s | to first result s | warm detect p50 ms | p90 ms | VRAM MiB | dets |",
         "|------|-------:|----------------:|------------------:|-------------------:|-------:|---------:|-----:|"]
    for r in rows:
        if "error" in r:
            L.append(f"| {r['name']} | - | - | - | ERR | - | - | {r['error'][:50]} |")
        else:
            L.append(f"| {r['name']} | {r['load_s']} | {r['first_detect_s']} | {r['time_to_first_result_s']} "
                     f"| {r['warm_detect_p50_ms']} | {r['warm_detect_p90_ms']} | {r['vram_mib']} | {r['dets']} |")
    rep = "\n".join(L) + "\n"
    rp = os.path.join(HERE, "results", "2026-09-03-sam3-e2e-timing.md")
    open(rp, "w").write(rep)
    print("\n" + rep + f"\n(written to {rp})")


if __name__ == "__main__":
    main()
