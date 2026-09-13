#!/usr/bin/env python3
import sys, json
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
threads = sys.argv[2] if len(sys.argv) > 2 else "?"
print(f"# yolo26n-depth ONNX inference benchmark\n")
print(f"Runtime: onnxruntime {rows[0].get('ort','?')} CPU EP, intra_op_threads={threads}, "
      f"iters={rows[0].get('iters','?')} after 20 warmup. VRAM: N/A (CPU-only build). RSS is process peak.\n")
h = ["model","input","load ms","p50 ms","hz@p50","p25","p75","p95","p99","min","max","mean","RSS peak MB"]
print("| " + " | ".join(h) + " |")
print("|" + "|".join(["---"]*len(h)) + "|")
for r in rows:
    if "error" in r:
        print(f"| `{r['model']}` | | | ERROR: {r['error']} |" + " |"*(len(h)-4)); continue
    print("| `{model}` | {input_shape} | {load_ms} | {p50_ms} | {hz_p50} | {p25_ms} | {p75_ms} | "
          "{p95_ms} | {p99_ms} | {min_ms} | {max_ms} | {mean_ms} | {rss_peak_mb} |".format(**r))
