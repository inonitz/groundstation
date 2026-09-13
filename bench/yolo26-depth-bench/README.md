# yolo26n-depth inference benchmark — archival record

Retired benchmark. This document is the standalone record. It states the objective, the
procedure, the numbers, the run counts, and the verdict. The scripts and model weights are
archived at freeze; the numbers below do not depend on them.

| section | content |
|---|---|
| [Objective](#objective) | what was measured and why |
| [Setup](#setup) | runtimes, configs, run counts, hardware |
| [Results](#results) | the measured tables |
| [Analysis](#analysis) | numbered findings |
| [Conclusion](#conclusion) | the production choice |
| Raw data | `results.md` (ONNX CPU), `results_torch.md` (PyTorch full percentiles), `results_ladder.md` (size ladder), `results.jsonl` |

## Objective

Choose the depth configuration for production. Depth here = monocular depth from one RGB frame,
produced by the `yolo26n-depth` network. Measure load time, inference latency (p50 ms and Hz),
and process memory for every ONNX variant, then compare against the PyTorch path and a size
ladder. The production runtime is the FMU's bundled ONNX Runtime, so the ONNX CPU numbers decide.

## Setup

- Model: `yolo26n-depth` (nano). The ladder also runs the s, m, and l sizes.
- Inputs: 384x384, 480x480, 640x640.
- ONNX lane: onnxruntime 1.20.1, CPU execution provider, `intra_op_num_threads=2`. This matches
  production (`kVisionDepthThreads=2`). The FMU bundles the CPU-only ONNX Runtime, so there is no
  CUDA provider and VRAM is N/A on this lane. 200 timed iters after 20 warmup. RSS is process peak.
- PyTorch lane: torch 2.11.0+cu128. CPU sweeps 1/2/4/8/16 threads. CUDA runs on the GPU. 100 timed
  forwards. GPU memory = peak VRAM allocated; CPU memory = process RSS peak.
- Runs: one measured pass per configuration. Latency variance is low, so one pass is enough
  (p99 within about 15% of p50 on every model).
- Hardware: RTX 5070 Laptop GPU, 32-thread CPU.

## Results

### ONNX Runtime, CPU EP, 2 threads (the production runtime)

200 iters after 20 warmup. VRAM N/A (CPU-only build). RSS is process peak.

| model | input | load ms | p50 ms | hz@p50 | p95 | p99 | RSS peak MB |
|---|---|---|---|---|---|---|---|
| `yolo26n-depth.onnx` | 640x640 | 53.6 | 123.9 | 8.1 | 138.9 | 142.6 | 197.4 |
| `yolo26n-depth-384.onnx` | 384x384 | 33.7 | 44.35 | 22.5 | 45.71 | 46.32 | 137.4 |
| `yolo26n-depth-480.onnx` | 480x480 | 37.8 | 68.38 | 14.6 | 69.89 | 70.71 | 178.4 |
| `yolo26n-depth.int8.onnx` | 640x640 | ERROR | - | - | - | - | - |
| `yolo26n-depth.int4.onnx` | 640x640 | 34.1 | 124.93 | 8.0 | 130.04 | 137.52 | 197.5 |

int8 load error: `NOT_IMPLEMENTED : Could not find an implementation for ConvInteger(10)`.

### PyTorch, CPU threads vs CUDA (headline rows)

torch 2.11.0+cu128, RTX 5070 Laptop. 100 timed forwards. Full percentiles in `results_torch.md`.

| device | threads | res | p50 ms | hz@p50 | mem MB |
|---|---|---|---|---|---|
| cpu | 8 | 384 | 29.87 | 33.5 | 632.1 |
| cpu | 16 | 384 | 26.66 | 37.5 | 638.2 |
| cpu | 8 | 640 | 57.17 | 17.5 | 751.5 |
| cuda | - | 384 | 4.35 | 229.9 | 92.3 |
| cuda | - | 480 | 4.86 | 205.8 | 117.4 |
| cuda | - | 640 | 5.72 | 174.8 | 172.0 |

### Size ladder, PyTorch (p50 ms / Hz)

GPU peak VRAM in MB. Full ladder in `results_ladder.md`.

| size | GPU 384 | GPU 640 | CPU 384 8t | VRAM MB |
|---|---|---|---|---|
| n | 4.2 / 237 | 5.7 / 175 | 18.7 / 53 | 84-129 |
| s | 4.3 / 234 | 6.6 / 152 | 26.0 / 39 | 115-165 |
| m | 4.8 / 208 | 11.9 / 84 | 55.7 / 18 | 168-240 |
| l | 7.4 / 135 | 14.0 / 71 | 80.1 / 12 | 191-272 |

## Analysis

1. On the CPU runtime, input resolution sets latency. 384 = 44 ms (22.5 Hz), 480 = 68 ms
   (14.6 Hz), 640 = 124 ms (8 Hz). Production uses the 384 model. The FMU paces depth to about
   12 Hz (`kVisionDepthLoopMs=80`), which is below what the 384 model can sustain.
2. int8 does not run. The CPU execution provider has no `ConvInteger` kernel for this
   quantization, so the model fails to load. It is unusable on this runtime.
3. int4 gives no benefit. It runs 640 in 125 ms, the same as fp32 640 (124 ms), with the same
   about 197 MB RSS. The int4 weights dequantize at runtime, so there is no CPU compute or
   memory saving.
4. The GPU is far faster. PyTorch CUDA runs the n model at 4.35 ms (230 Hz) at 384 and 5.72 ms
   (175 Hz) at 640. The production ONNX Runtime is CPU-only, so using the GPU needs ORT-GPU with
   CUDA. That is a separate, deferred infra task.
5. CPU thread scaling saturates near 8 threads. PyTorch n at 384 goes 97.7 ms (1t) to 29.9 ms
   (8t) to 26.7 ms (16t). Past 8 threads the gain is small.
6. The size ladder is cheap on the GPU and expensive on the CPU. n and s are close on the GPU
   (about 4-7 ms). m and l cost up to 14 ms on the GPU and 56-80 ms on the CPU at 8 threads.
   For CPU real-time, n is the right size.
7. Latency variance is low. p99 is within about 15% of p50 on every ONNX model, so the medians
   are reliable.

## Conclusion

- Production choice: `yolo26n-depth-384.onnx`, ONNX CPU EP, 2 threads. p50 44 ms, 22.5 Hz,
  137 MB RSS. It meets the FMU's about 12 Hz depth pace with margin.
- int8 is unusable on the CPU EP (no `ConvInteger` kernel). int4 is pointless on the CPU
  (runtime dequant, no saving).
- Bigger models or genuine quantization need the GPU path (ORT-GPU + CUDA), which is deferred.
