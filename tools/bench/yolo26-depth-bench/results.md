# yolo26n-depth ONNX inference benchmark

Runtime: onnxruntime 1.20.1 CPU EP, intra_op_threads=2, iters=200 after 20 warmup. VRAM: N/A (CPU-only build). RSS is process peak.

| model | input | load ms | p50 ms | hz@p50 | p25 | p75 | p95 | p99 | min | max | mean | RSS peak MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `yolo26n-depth.onnx` | 1x3x640x640 | 53.6 | 123.9 | 8.1 | 122.87 | 126.04 | 138.91 | 142.59 | 121.11 | 145.16 | 126.14 | 197.4 |
| `yolo26n-depth-384.onnx` | 1x3x384x384 | 33.7 | 44.35 | 22.5 | 44.11 | 44.68 | 45.71 | 46.32 | 43.78 | 47.8 | 44.52 | 137.4 |
| `yolo26n-depth-480.onnx` | 1x3x480x480 | 37.8 | 68.38 | 14.6 | 68.11 | 68.81 | 69.89 | 70.71 | 67.5 | 74.33 | 68.54 | 178.4 |
| `yolo26n-depth.int8.onnx` | | | ERROR: load: [ONNXRuntimeError] : 9 : NOT_IMPLEMENTED : Could not find an implementation for ConvInteger(10) node with name '/model.0/conv/Conv_quant' | | | | | | | | | |
| `yolo26n-depth.int4.onnx` | 1x3x640x640 | 34.1 | 124.93 | 8.0 | 124.49 | 125.78 | 130.04 | 137.52 | 123.55 | 141.21 | 125.63 | 197.5 |

## Analysis

1. On the CPU runtime, input resolution sets latency. 384x384 = 44 ms (22.5 Hz), 480x480 = 68 ms
   (14.6 Hz), 640x640 = 124 ms (8 Hz). Production uses the 384 model; the FMU paces depth to ~12 Hz
   (kVisionDepthLoopMs=80), below what the model can sustain.
2. int8 does not run. The CPU execution provider has no `ConvInteger` kernel for this quantization,
   so the model fails to load. It is unusable on the current runtime.
3. int4 gives no benefit. It runs 640x640 in 125 ms, the same as the fp32 640 model (124 ms), with
   the same ~197 MB RSS. The int4 weights are dequantized at runtime, so there is no CPU compute or
   memory saving here.
4. Latency variance is low. p99 sits within ~15% of p50 on every model, so the medians are reliable.
5. VRAM is N/A. The bundled ONNX Runtime is the CPU-only package. A bigger model (e.g. yolo26m) would
   be several times slower on the CPU. Bigger or genuinely-quantized models need the GPU path
   (ORT-GPU + CUDA), which is a separate, deferred infra task.
