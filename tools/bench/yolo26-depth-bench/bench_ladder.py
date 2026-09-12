#!/usr/bin/env python3
"""yolo26-depth size ladder (n/s/m/l): GPU + CPU thread sweep. Numbers only, readable output."""
import time, json, os
import numpy as np, torch
from ultralytics import YOLO

MODELS = [("n","models/yolo26n-depth.pt"), ("s","models/yolo26s-depth.pt"),
          ("m","models/yolo26m-depth.pt"), ("l","models/yolo26l-depth.pt")]
GPU_RES = [384, 640]; CPU_THREADS = [2, 8, 16]; ITERS_G = 100; ITERS_C = 50

def load(path):
    t = time.perf_counter(); m = YOLO(path).model.eval()
    for p in m.parameters(): p.requires_grad_(False)
    return m, (time.perf_counter()-t)*1000

def bench(m, device, res, threads, iters):
    try:
        if device == "cpu": torch.set_num_threads(threads)
        m = m.to(device); x = torch.rand(1,3,res,res, device=device)
        warm = 20 if device == "cuda" else 8
        with torch.no_grad():
            if device == "cuda":
                torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize()
            for _ in range(warm): m(x)
            if device == "cuda": torch.cuda.synchronize()
            lat = np.empty(iters)
            for i in range(iters):
                t = time.perf_counter(); m(x)
                if device == "cuda": torch.cuda.synchronize()
                lat[i] = (time.perf_counter()-t)*1000
        p50 = float(np.percentile(lat,50))
        mem = round(torch.cuda.max_memory_allocated()/1e6) if device=="cuda" else None
        return {"p50": round(p50,1), "hz": round(1000/p50) if p50 else 0,
                "p95": round(float(np.percentile(lat,95)),1), "mem": mem}
    except Exception as e:
        return {"error": repr(e)[:100]}

out = {}; lines = [f"# yolo26-depth size ladder", 
    f"torch {torch.__version__} · {torch.cuda.get_device_name(0)} · GPU mem = peak VRAM allocated · p50 ms (Hz)"]
for lbl, path in MODELS:
    torch.cuda.empty_cache()
    m, load_ms = load(path); sz = round(os.path.getsize(path)/1e6)
    o = {"load_ms": round(load_ms), "size_mb": sz, "gpu": {}, "cpu": {}}
    for res in GPU_RES: o["gpu"][res] = bench(m, "cuda", res, None, ITERS_G)
    for th in CPU_THREADS: o["cpu"][th] = bench(m, "cpu", 384, th, ITERS_C)
    m.to("cpu"); del m; torch.cuda.empty_cache(); out[lbl] = o
    g, c = o["gpu"], o["cpu"]
    lines.append(f"\n**yolo26{lbl}-depth**  ({sz} MB, load {int(load_ms)} ms)")
    lines.append(f"- GPU  384²: {g[384]['p50']} ms ({int(g[384]['hz'])} Hz), {g[384]['mem']} MB   |   640²: {g[640]['p50']} ms ({int(g[640]['hz'])} Hz), {g[640]['mem']} MB")
    lines.append(f"- CPU  384²: 2t {c[2]['p50']} ms ({int(c[2]['hz'])} Hz)  |  8t {c[8]['p50']} ms ({int(c[8]['hz'])} Hz)  |  16t {c[16]['p50']} ms ({int(c[16]['hz'])} Hz)")
report = "\n".join(lines) + "\n"
open("results_ladder.md","w").write(report); print(report)
