# yolo26n-depth inference benchmark

Measures load time, inference latency (ms + Hz, full percentiles), and process memory for every
`yolo26n-depth` ONNX variant. Isolated from `integration_harden` on purpose.

VRAM is N/A: the FMU's bundled ONNX Runtime is the CPU-only package (no CUDA provider), so depth
runs on the CPU and uses no VRAM. RSS (process peak) is the memory metric instead.

| File | What it is |
|---|---|
| `setup.sh` | Creates `.venv`, installs `onnxruntime==1.20.1` (matches the bundled runtime) + numpy |
| `bench_one.py` | Benchmarks one model in an isolated process; prints one JSON line |
| `run.sh` | Loops all variants, writes `results.md` |
| `make_table.py` | Formats the JSONL into a markdown table |
| `results.md` | Current results |

## Run

```bash
./setup.sh          # once
./run.sh            # THREADS=2 WARMUP=20 ITERS=200 by default
```

Config matches production: CPU EP, `intra_op_num_threads=2` (== `kVisionDepthThreads`).
