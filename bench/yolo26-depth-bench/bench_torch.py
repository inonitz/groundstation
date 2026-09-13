#!/usr/bin/env python3
"""PyTorch depth benchmark for yolo26n-depth.pt. Sweeps device (cpu/gpu) and CPU thread count.
Measures the raw DepthModel forward. Numbers only -- no conclusions.
Metrics: load time, inference latency percentiles (ms) + Hz, memory (CPU RSS / GPU VRAM reserved)."""
import time, json, resource
import numpy as np, torch
from ultralytics import YOLO

MODEL = "/root/models/vision/yolo26n-depth.pt"
RES = [384, 480, 640]
CPU_THREADS = [1, 2, 4, 8, 16]
ITERS = 100

def rss_mb(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
def pcts(a):
    return {k: round(float(np.percentile(a, q)), 2) for k, q in
            [("min",0),("p25",25),("p50",50),("p75",75),("p95",95),("p99",99),("max",100)]}

def load_model():
    m = YOLO(MODEL).model.eval()
    for p in m.parameters(): p.requires_grad_(False)
    return m

def bench(m, device, res, threads):
    r = {"device": device, "threads": (threads if device == "cpu" else "-"), "res": res, "iters": ITERS}
    try:
        if device == "cpu": torch.set_num_threads(threads)
        m = m.to(device)
        x = torch.rand(1, 3, res, res, device=device)
        warm = 20 if device == "cuda" else 10
        with torch.no_grad():
            if device == "cuda":
                torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize()
            for _ in range(warm): m(x)
            if device == "cuda": torch.cuda.synchronize()
            lat = np.empty(ITERS)
            for i in range(ITERS):
                t = time.perf_counter(); m(x)
                if device == "cuda": torch.cuda.synchronize()
                lat[i] = (time.perf_counter() - t) * 1000
        p = pcts(lat); r.update({k + "_ms": v for k, v in p.items()})
        r["mean_ms"] = round(float(lat.mean()), 2)
        r["hz_p50"] = round(1000.0 / p["p50"], 1) if p["p50"] else 0
        if device == "cuda":
            r["vram_reserved_mb"] = round(torch.cuda.max_memory_reserved() / 1e6, 1)
            r["vram_alloc_mb"] = round(torch.cuda.max_memory_allocated() / 1e6, 1)
        else:
            r["rss_peak_mb"] = round(rss_mb(), 1)
    except Exception as e:
        r["error"] = repr(e)[:200]
    return r

def main():
    t = time.perf_counter(); m = load_model(); load_ms = round((time.perf_counter() - t) * 1000, 1)
    rows = []
    for res in RES:
        for th in CPU_THREADS:
            rows.append(bench(m, "cpu", res, th))
    if torch.cuda.is_available():
        for res in RES:
            rows.append(bench(m, "cuda", res, None))
    print(json.dumps({"model": "yolo26n-depth.pt", "torch": torch.__version__,
                      "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                      "load_ms": load_ms, "rows": rows}, indent=None))

if __name__ == "__main__": main()
