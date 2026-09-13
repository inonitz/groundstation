#!/usr/bin/env python3
"""Benchmark ONE onnx depth model in an isolated process (clean RSS). Prints one JSON line.
CPU EP only -- the bundled ONNX Runtime has no CUDA provider, so VRAM is N/A; RSS is the memory metric.
Usage: bench_one.py <model.onnx> <intra_op_threads> <warmup> <iters>"""
import sys, json, time, os, resource
import numpy as np
import onnxruntime as ort

def peak_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # ru_maxrss is kB on Linux

def make_session(path, threads):
    so = ort.SessionOptions()
    so.intra_op_num_threads = threads
    so.inter_op_num_threads = 1
    return ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])

def main():
    model, threads, warmup, iters = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    res = {"model": os.path.basename(model), "threads": threads, "ort": ort.__version__, "iters": iters}
    base_mb = peak_mb()  # python+ort+numpy baseline
    try:
        loads = []
        for _ in range(3):
            t = time.perf_counter(); s = make_session(model, threads); loads.append((time.perf_counter()-t)*1000); del s
        res["load_ms"] = round(float(np.median(loads)), 1)
        sess = make_session(model, threads)
    except Exception as e:
        res["error"] = f"load: {e}"; print(json.dumps(res)); return
    inp = sess.get_inputs()[0]
    dims = []
    for i, d in enumerate(inp.shape):
        dims.append(d if isinstance(d, int) and d > 0 else (1 if i == 0 else 3 if i == 1 else 640))
    res["input_shape"] = "x".join(map(str, dims))
    x = np.random.default_rng(0).random(dims, dtype=np.float32)
    outs = [o.name for o in sess.get_outputs()]
    try:
        for _ in range(warmup): sess.run(outs, {inp.name: x})
        lat = np.empty(iters)
        for i in range(iters):
            t = time.perf_counter(); sess.run(outs, {inp.name: x}); lat[i] = (time.perf_counter()-t)*1000
    except Exception as e:
        res["error"] = f"infer: {e}"; print(json.dumps(res)); return
    for k, q in [("min",0),("p25",25),("p50",50),("p75",75),("p95",95),("p99",99),("max",100)]:
        res[k+"_ms"] = round(float(np.percentile(lat, q)), 2)
    res["mean_ms"] = round(float(lat.mean()), 2)
    res["hz_p50"] = round(1000.0/res["p50_ms"], 1) if res["p50_ms"] else 0
    res["rss_peak_mb"] = round(peak_mb(), 1)
    res["rss_over_base_mb"] = round(peak_mb()-base_mb, 1)
    print(json.dumps(res))

if __name__ == "__main__": main()
