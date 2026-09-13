#!/usr/bin/env python3
"""Benchmark ONE SOTA monocular-depth model on cpu OR cuda (isolated process). Prints one JSON line.
Usage: bench_one_sota.py <key> <device>
  key: depthpro | da3mono-large | da3-small | metric3d-small | metric3d-large ; device: cpu | cuda"""
import sys, time, json, resource
import numpy as np, torch
from PIL import Image

KEY, DEV = sys.argv[1], sys.argv[2]
WARM, ITERS = (5, 20) if DEV == "cuda" else (1, 3)   # cpu models are heavy -> few iters
def pil(res): return Image.fromarray(np.full((res, res, 3), 128, dtype='uint8'))
def rss_mb(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

def time_fn(fn):
    with torch.no_grad():
        for _ in range(WARM): fn()
        if DEV == "cuda": torch.cuda.synchronize(); torch.cuda.reset_peak_memory_stats()
        lat = []
        for _ in range(ITERS):
            t = time.perf_counter(); fn()
            if DEV == "cuda": torch.cuda.synchronize()
            lat.append((time.perf_counter()-t)*1000)
    lat = np.array(lat)
    r = {"p50": round(float(np.percentile(lat,50)),1), "p95": round(float(np.percentile(lat,95)),1),
         "hz": round(1000/float(np.percentile(lat,50)),1), "iters": ITERS}
    r["mem_mb"] = round(torch.cuda.max_memory_allocated()/1e6) if DEV == "cuda" else round(rss_mb())
    return r

out = {"model": KEY, "device": DEV}
try:
    if KEY == "depthpro":
        from transformers import DepthProForDepthEstimation
        t = time.perf_counter(); model = DepthProForDepthEstimation.from_pretrained("apple/DepthPro-hf").to(DEV).eval()
        out["load_ms"] = round((time.perf_counter()-t)*1000)
        x = torch.rand(1, 3, 1536, 1536, device=DEV); out["res"] = "1536x1536"
        out.update(time_fn(lambda: model(pixel_values=x)))
    elif KEY.startswith("da3"):
        from depth_anything_3.api import DepthAnything3
        ckpt = {"da3mono-large":"depth-anything/DA3MONO-LARGE","da3-small":"depth-anything/DA3-SMALL"}[KEY]
        t = time.perf_counter(); model = DepthAnything3.from_pretrained(ckpt).to(DEV).eval()
        out["load_ms"] = round((time.perf_counter()-t)*1000)
        p = "/tmp/da3_in.png"; pil(1024).save(p)
        pred = model.inference([p]); out["res"] = "x".join(str(s) for s in np.asarray(pred.depth).shape[-2:])
        out.update(time_fn(lambda: model.inference([p])))
    elif KEY.startswith("metric3d"):
        name = {"metric3d-small":"metric3d_vit_small","metric3d-large":"metric3d_vit_large"}[KEY]
        t = time.perf_counter(); model = torch.hub.load('yvanyin/metric3d', name, pretrain=True, trust_repo=True).to(DEV).eval()
        out["load_ms"] = round((time.perf_counter()-t)*1000)
        H, W = 616, 1064; out["res"] = f"{H}x{W}"; x = torch.rand(1,3,H,W, device=DEV)
        out.update(time_fn(lambda: model.inference({'input': x})))  # xformers removed -> vanilla attn
    else:
        raise ValueError("unknown key")
except Exception as e:
    out["error"] = repr(e)[:200]
print(json.dumps(out))
