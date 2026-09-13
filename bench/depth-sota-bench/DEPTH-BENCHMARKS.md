# Depth model benchmarks — COMPLETE (2026-09-06)
Owner: groundstation-13 [8501ec] (llm_to_action presentation agent). See docs/active/2026-09-06-llm-to-action-and-depth-handoff.md.
Machine: RTX 5070 Laptop (Vulkan; no CUDA toolkit) + 16-core CPU. Latency = per-forward, p50 = median.
CPU mem = process RSS; GPU mem = peak VRAM. Quality column is knowledge-based, UNVERIFIED here.

## Objective

Choose the depth model and runtime for the perception stack. Depth = monocular depth from one
RGB frame. Compare the production yolo26n-depth against Depth Anything (DA2 and DA3) across
engines, precisions, sizes, and CPU vs GPU. Primary metric: per-forward latency (p50). Secondary:
memory, and whether the model runs at all on each backend.

## Setup

- Engines: ONNX Runtime (yolo26n-depth), ggml via depth-anything.cpp (DA2/DA3), PyTorch (SOTA reference).
- Backends: CPU (2/8/16 threads) and GPU. ggml uses Vulkan (no CUDA toolkit on this host); PyTorch uses CUDA.
- Runs: 15 timed forwards per configuration. The tables report the median (p50); min, max, and p90
  are in the raw txt files.
- Hardware: RTX 5070 Laptop GPU, 16-core CPU.
- Raw data: `results_da3_full.txt` and `results_da3cpp.txt` (ggml per-config medians),
  `results_sota.jsonl` (PyTorch SOTA), `sota_errors.log` (failures). The depth-anything.cpp build
  and the gguf weights are archived at freeze; the numbers below stand alone.


## 1. yolo26n-depth — ONNX runtime (CPU, 2 threads) — CURRENT production depth
| Variant | Prec | Res | p50 ms | Hz | RSS MB | Note |
|---|---|---|---|---|---|---|
| depth-384 | fp32 | 384² | 44.4 | 22.5 | 137 | deployed today |
| depth-480 | fp32 | 480² | 68.4 | 14.6 | 178 | |
| depth (base) | fp32 | 640² | 123.9 | 8.1 | 197 | |
| depth.int4 | int4 | 640² | 124.9 | 8.0 | 197 | no speedup |
| depth.int8 | int8 | — | FAIL | — | — | no CPU ConvInteger kernel |

## 2. yolo26-depth ladder — PyTorch (p50 ms / Hz)
| Size | GPU 384² | GPU 640² | CPU384 2t | 8t | 16t | VRAM MB |
|---|---|---|---|---|---|---|
| n | 4.2/237 | 5.7/175 | 51/20 | 19/53 | 20/51 | 84–129 |
| s | 4.3/234 | 6.6/152 | 72/14 | 26/39 | 28/36 | 115–165 |
| m | 4.8/208 | 11.9/84 | 147/7 | 56/18 | 72/14 | 168–240 |
| l | 7.4/135 | 14.0/71 | 203/5 | 80/12 | 86/12 | 191–272 |

## 3. Depth Anything (ggml / depth-anything.cpp) — the C++ INTEGRATION path
Output 504² (DA3) / 518² (DA2). p50 median ms/iter. "rel" = relative depth, "metric" = metric.
| Model | Prec | Size | CPU 16t | GPU Vulkan | Kind |
|---|---|---|---|---|---|
| DA3 base | q4_k | 99 MB | 581 | CRASH | rel |
| DA3 base | q8_0 | 141 MB | 494 | CRASH | rel |
| DA3 base | f16 | 221 MB | 494 | CRASH | rel |
| DA3 large | f32 | 1382 MB | 1578 | CRASH | rel |
| DA3 metric-large | f32 | 1274 MB | 1514 | 191 | metric |
| DA3 metric-large | q8_0 | 428 MB | 1237 | 176 | metric |
| DA3 metric-large | q4_k | 284 MB | 1503 | 184 | metric |
| DA2 base | q8_0 | 140 MB | 461 | (CPU only run) | rel |
| DA2 large | q8_0 | 454 MB | 1326 | 183 | rel |
| DA2 metric-large | q4_k | 303 MB | 1597 | 191 | metric |
| DA2 metric-large | q8_0 | 454 MB | 1304 | 186 | metric |

CRASH = DA3 **relative** models (base + large) segfault on the Vulkan forward. DA3 **metric** and all DA2
run fine on Vulkan. On Vulkan every ViT-L lands ~176–191 ms regardless of quant (compute-bound); quant
only changes load time + memory. On CPU, q8_0 is the sweet spot.

## 4. PyTorch SOTA reference (Path B — would need a Python service, not our C++ stack)
| Model | Device | Res | p50 ms | Hz | Mem | Note |
|---|---|---|---|---|---|---|
| DA3-small (0.08B) | GPU | 504² | 38.5 | 26.0 | 340 MB VRAM | rel |
| DA3-small | CPU | 504² | 241 | 4.1 | 1274 MB RSS | rel |
| DA3-mono-large (0.35B) | GPU | 504² | 95.3 | 10.5 | 1762 MB VRAM | rel |
| DA3-mono-large | CPU | 504² | 1047 | 1.0 | 3356 MB RSS | rel |
| Depth Pro | GPU | 1536² | 1086 | 0.9 | 3959 MB VRAM | metric, sharp |
| Depth Pro | CPU | 1536² | impractical (>2 min) | — | — | metric |
| Metric3D-small | GPU | 616×1064 | 182 | 5.5 | 744 MB VRAM | metric |
| Metric3D-large | GPU | 616×1064 | 1207 | 0.8 | 3205 MB VRAM | metric |
| Metric3D (small/large) | CPU | — | FAIL | — | — | code pins cuda device |

## Notes
- ggml (§3) is bit-exact vs PyTorch DA3, so §3 quality == §4 DA3 quality with no Python/PyTorch.
- Real world (metric): DA3 metric-large q8_0 → CPU 1237 ms @16t or Vulkan 176 ms, 428 MB file.
- Simulator (relative): DA3 relative crashes on Vulkan → CPU only (base q8_0 494 ms), OR DA2 relative
  runs on Vulkan (large q8_0 183 ms). Relative gets calibrated to the sim regardless.
- The DA3-relative Vulkan segfault is a genuine bug in the port's Vulkan path (no GGML_ASSERT).

## Open decision (post-meeting) — perception architecture fork
- Path A (C++/ggml drop-in): depth-anything.cpp integrates like the VLM (llama.cpp) + ASR (whisper.cpp).
  Metric-large q8_0 = 176 ms Vulkan / 1237 ms CPU-16t. DA3 relative crashes on Vulkan (CPU-only or use DA2).
- Path B (Python perception service publishing to the ROS topic): opens Depth Pro / Metric3D as options,
  but adds a process + boundary. Only worth it if a PyTorch-only model wins on quality (unmeasured here).
- Not decided. Quality needs a ground-truth test (Gazebo can give GT depth).

## Status (archival, 2026-09-13)

- The benchmark is complete and retired. This document is its standalone record.
- Direction on the fork: the C++/ggml path (depth-anything.cpp) was identified as the intended
  embedded depth path for llm_to_action (see the 2026-09-06 depth handoff). Final integration is
  the llm_to_action owner's call. The PyTorch-service path (Depth Pro, Metric3D) was not adopted.
- Open, deferred: a ground-truth quality test (for example Gazebo GT depth) to rank accuracy, not
  only latency. The quality columns here are knowledge-based, not measured.
