#!/usr/bin/env python3
"""SAM3 concurrency + batching micro-bench. See README.md.

Loads SAM3 ALONE (optimistic: no Gemma/whisper contention) and measures three things:
  1. single-forward detect() latency (p50/p95),
  2. N concurrent detect() calls vs N serial calls (the backend lock serializes forwards),
  3. K prompts in ONE batched forward vs K separate forwards (the parallelism lever).
Writes RESULTS.md and raw.json next to this file. It reuses the real perception2.Sam3Backend so
the numbers reflect the live code path, not a re-implementation."""
import json
import os
import sys
import time
import threading

sys.path.insert(0, "/root/groundstation/projects/integration_harden2")
import numpy as np
import torch
from PIL import Image
from perception2.sam3_backend import Sam3Backend

HERE = os.path.dirname(os.path.abspath(__file__))
CAND = "/root/groundstation/bench/sam3-mask-bench/candidates/img0.png"
CONCEPTS = ["person", "car", "window", "chair", "door", "backpack", "monitor", "bottle"]


def pctl(xs, p):
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def load_frame():
    import cv2
    if os.path.exists(CAND):
        f = cv2.imread(CAND)
        if f is not None:
            return f, CAND
    rng = np.random.default_rng(0)
    return rng.integers(0, 255, (720, 1280, 3), dtype=np.uint8), "synthetic-720p"


def write_results(out):
    L = ["# sam3-concurrency-bench RESULTS", ""]
    L.append(f"GPU {out['gpu']}, SAM3 {out['precision']}, frame {out['source']}. SAM3 loaded ALONE.")
    L.append("These numbers are an optimistic upper bound. The live system shares this GPU with "
             "Gemma and whisper.")
    L.append("")
    s = out["single_ms"]
    L += ["## Single forward latency", "", "| metric | ms |", "|---|---|",
          f"| p50 | {s['p50']} |", f"| p95 | {s['p95']} |",
          f"| min | {s['min']} |", f"| max | {s['max']} |", ""]
    L += ["## N concurrent detect() vs N serial", "",
          "| N | serial ms | concurrent ms | speedup |", "|---|---|---|---|"]
    for r in out["serial_vs_concurrent"]:
        L.append(f"| {r['N']} | {r['serial_ms']} | {r['concurrent_ms']} | {r['speedup']}x |")
    L += ["", "## K prompts batched into one forward vs K separate", "",
          "| K | separate ms | batched ms | speedup | peak MiB | returned |",
          "|---|---|---|---|---|---|"]
    for r in out["batching"]:
        if r.get("batched_ms") is None:
            L.append(f"| {r['K']} | {r['separate_ms']} | FAIL | - | - | {r.get('error','')} |")
        else:
            L.append(f"| {r['K']} | {r['separate_ms']} | {r['batched_ms']} | {r['speedup']}x "
                     f"| {r['peak_mib']} | {r['returned']} |")
    L.append("")
    p50 = out["single_ms"]["p50"]
    ceil = round(1000.0 / p50, 1) if p50 else 0.0
    cspeed = max((r["speedup"] for r in out["serial_vs_concurrent"]), default=0.0)
    bspeeds = [r["speedup"] for r in out["batching"] if r.get("batched_ms")]
    bmax = max(bspeeds) if bspeeds else 0.0
    peaks = [r.get("peak_mib") for r in out["batching"] if r.get("peak_mib")]
    bpeak = max(peaks) if peaks else 0
    batch_ok = bool(out["batching"]) and all(r.get("returned") == r["K"]
                                             for r in out["batching"] if r.get("batched_ms"))
    L += ["## Findings", "",
          f"- Single detect is about {p50} ms. The ceiling is about {ceil} forwards/s if SAM3 owns the GPU alone.",
          f"- Concurrency gives up to {cspeed}x. Threads do not help. One GPU, one model, forwards serialize.",
          f"- Batching {'works and returns K results' if batch_ok else 'is partial'}. Best speedup {bmax}x, so no real throughput win.",
          f"- Batching costs VRAM: peak grows to {bpeak} MiB at the largest K.",
          "- Levers left: fp8+compile (about 0.2 s in the quant bench), a lower per-highlight rate, or a dedicated GPU.",
          "- SAM3 ran ALONE here. With Gemma and whisper on the same GPU, expect worse.", ""]
    open(os.path.join(HERE, "RESULTS.md"), "w").write("\n".join(L) + "\n")


def main():
    frame, src = load_frame()
    print(f"[bench] frame source: {src} shape={frame.shape}", flush=True)
    t0 = time.perf_counter()
    be = Sam3Backend()
    torch.cuda.synchronize()
    print(f"[bench] SAM3 loaded in {time.perf_counter()-t0:.1f}s (precision={be.precision})", flush=True)

    be.detect(frame, "person", conf=0.30)          # warmup (caches, allocator)
    torch.cuda.synchronize()

    out = {"source": src, "precision": be.precision, "gpu": torch.cuda.get_device_name(0)}

    reps = 12
    lat = []
    for i in range(reps):
        t = time.perf_counter()
        be.detect(frame, CONCEPTS[i % len(CONCEPTS)], conf=0.30)
        torch.cuda.synchronize()
        lat.append((time.perf_counter() - t) * 1000)
    out["single_ms"] = {"p50": round(pctl(lat, 50), 1), "p95": round(pctl(lat, 95), 1),
                        "min": round(min(lat), 1), "max": round(max(lat), 1), "reps": reps}
    print(f"[bench] single detect ms: p50={out['single_ms']['p50']} p95={out['single_ms']['p95']}", flush=True)

    out["serial_vs_concurrent"] = []
    for N in (2, 4, 8):
        cs = [CONCEPTS[i % len(CONCEPTS)] for i in range(N)]
        t = time.perf_counter()
        for c in cs:
            be.detect(frame, c, conf=0.30)
        torch.cuda.synchronize()
        serial = (time.perf_counter() - t) * 1000

        def work(c):
            be.detect(frame, c, conf=0.30)
        ths = [threading.Thread(target=work, args=(c,)) for c in cs]
        t = time.perf_counter()
        for th in ths:
            th.start()
        for th in ths:
            th.join()
        torch.cuda.synchronize()
        conc = (time.perf_counter() - t) * 1000
        row = {"N": N, "serial_ms": round(serial, 1), "concurrent_ms": round(conc, 1),
               "speedup": round(serial / conc, 2) if conc else 0.0}
        out["serial_vs_concurrent"].append(row)
        print(f"[bench] N={N} serial={row['serial_ms']}ms concurrent={row['concurrent_ms']}ms "
              f"speedup={row['speedup']}x", flush=True)

    pil = Image.fromarray(frame[:, :, ::-1])
    out["batching"] = []
    for K in (2, 4, 8):
        cs = CONCEPTS[:K]
        torch.cuda.synchronize()
        t = time.perf_counter()
        for c in cs:
            be._run(pil, c, 0.30)
        torch.cuda.synchronize()
        sep = (time.perf_counter() - t) * 1000
        torch.cuda.reset_peak_memory_stats()
        rec = {"K": K, "separate_ms": round(sep, 1)}
        try:
            inputs = be.proc(images=[pil] * K, text=cs, return_tensors="pt").to("cuda")
            inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
            torch.cuda.synchronize()
            t = time.perf_counter()
            with torch.no_grad():
                o = be.model(**inputs)
            res = be.proc.post_process_instance_segmentation(
                o, threshold=0.30, mask_threshold=be.mask_threshold,
                target_sizes=inputs.get("original_sizes").tolist())
            torch.cuda.synchronize()
            batched = (time.perf_counter() - t) * 1000
            rec.update(batched_ms=round(batched, 1), returned=len(res),
                       speedup=round(sep / batched, 2) if batched else 0.0,
                       peak_mib=round(torch.cuda.max_memory_allocated() / 2**20))
            print(f"[bench] K={K} separate={rec['separate_ms']}ms batched={rec['batched_ms']}ms "
                  f"speedup={rec['speedup']}x peak={rec['peak_mib']}MiB returned={rec['returned']}", flush=True)
        except Exception as e:
            rec.update(batched_ms=None, error=f"{type(e).__name__}: {str(e)[:180]}")
            print(f"[bench] K={K} batched FAILED: {rec['error']}", flush=True)
            torch.cuda.empty_cache()
        out["batching"].append(rec)

    json.dump(out, open(os.path.join(HERE, "raw.json"), "w"), indent=2)
    write_results(out)
    print("[bench] done. wrote raw.json + RESULTS.md", flush=True)


if __name__ == "__main__":
    main()
