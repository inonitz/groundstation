# SAM3 quantization + runtime latency (RTX 5070 Laptop, sm120 Blackwell, 8 GiB)

## Objective

Find the fastest SAM3 inference on this GPU across the 4-bit/8-bit quant family and the
`torch.compile` runtime. Confirm detection parity, not just speed.

## Setup

Fixed input `street-crowd-0.jpg` + concept `person`. 20 warm reps, deterministic (SAM3 has
no sampling). One mode per subprocess (one model resident). `fwd` = model forward. `full` =
forward + post_process (mask upsample to original resolution; ~2 ms). `-c` = `torch.compile`.
transformers 5.15.1, torchao 0.18.0, torch 2.11+cu128, bitsandbytes 0.50.2.

## Results

| mode | quant | compile | load s | VRAM MiB | fwd p50 ms | fwd p90 ms | dets |
|------|-------|:------:|-------:|---------:|-----------:|-----------:|-----:|
| bf16 | bf16 (none) | no | 6.5 | 2193 | 428.6 | 429.7 | 30 |
| nf4 | nf4 4-bit (bnb) | no | 5.3 | 1054 | 452.4 | 455.3 | 26 |
| int8-bnb | int8 (bnb) | no | - | - | ERR | - | RuntimeError("view size is not compatible with input tensor' |
| int8-ao | int8 (torchao) | no | 4.9 | 1678 | 501.9 | 503.9 | 33 |
| fp8-wo | fp8 weight-only (torchao) | no | 5.1 | 1710 | 496.9 | 498.2 | 31 |
| fp8-dyn | fp8 dyn-act (torchao) | no | 4.5 | 1710 | 502.7 | 507.6 | 29 |
| bf16-c | bf16 (none) | yes | 4.6 | 2219 | 264.6 | 269.1 | 30 |
| fp8-dyn-c | fp8 dyn-act (torchao) | yes | 4.7 | 1710 | 202.3 | 214.7 | 31 |

## Analysis

1. Eager weight quantization does NOT speed SAM3 up. nf4 (452), int8 (502), fp8 (497-503)
   are all slower than eager bf16 (428). The bottleneck is convolution + attention, not the
   Linear weights that bnb/torchao quantize. Quant shrinks VRAM and adds dequant overhead.
2. `torch.compile` is the real lever. Compiled bf16 drops 428 -> 265 ms, lossless (30 dets).
3. Compiled fp8 dynamic-activation is the fastest: 202 ms fwd, 1710 MiB, 31 dets. torchao's
   fp8 tensor-core kernels only materialize under `torch.compile`; in eager they fall back.
4. Detection parity holds: fp8-dyn-c 31 dets vs bf16 30 -- fp8 does not degrade detection.
5. VRAM: every mode fits 8 GiB with room. nf4 is smallest (1054) but slowest; not worth it
   here since VRAM is not the constraint.
6. int8-bnb fails to run on SAM3 (a view/stride error in the bnb int8 path).

## Backend-level (end-to-end detect, not forward-only)

The table above times the model forward. The perception2 `Sam3Backend.detect()` also runs the image
processor (resize + normalize) and mask upsampling on every call. Measured on the same input, warm:

| path | fp8 + compile |
|------|--------------:|
| forward only (bench) | 202 ms |
| full `detect()` (processor + forward + post_process) | 398 ms |
| first call (one-time torch.compile) | 134 s |

7. The forward speedup is real, but ~190 ms of `detect()` is image preprocessing + mask upsampling,
   which quantization does not touch. So end-to-end a highlight is ~398 ms with fp8+compile, not
   202 ms. The next latency lever is the processor (GPU-side preprocessing or caching), not the
   weight format. Detection is on-demand, so 398 ms is acceptable today.

## Insights: storage quantization vs compute precision

Applies to this GPU (RTX 5070 Laptop, sm120 Blackwell) and these libraries.

1. Quantization has two independent payoffs: memory (bytes per weight in VRAM) and speed (the
   precision of the matmul). A format can deliver one without the other.
2. Weight-only quantization (nf4, int8-weight, fp8-weight, GGUF K-quants) stores weights small but
   multiplies in higher precision. The weight is upcast at matmul time. VRAM always drops. Speed
   improves only when that upcast is fused into the matmul kernel AND the workload is memory-bound.
3. Fusion, not the format, decides the eager penalty. Unfused weight-only quant (torchao eager here)
   writes a dequantized temporary and runs slower than bf16. Fused weight-only quant (torch.compile,
   or llama.cpp's hand-written kernels) dequantizes on-chip with no extra memory traffic. Same
   format, opposite speed.
4. Memory-bound vs compute-bound sets the outcome:
   - LLM token decode (batch 1) is memory-bound. Every weight is read once per token; arithmetic
     intensity is low. Cutting weights to 4-bit cuts the dominant cost (memory reads) roughly in
     proportion. Large speedup.
   - The SAM3 vision forward is compute-bound. Wide matmuls, high arithmetic intensity. Fewer weight
     bytes do not shorten the critical path, and the dequant adds cost. nf4 measured slower than
     bf16 (452 vs 428 ms).
5. GGUF (llama.cpp) compute precision depends on the path:
   - Decode: the activation is quantized to int8 on the fly; the dot product uses an integer MAC
     (dp4a, int8xint8 -> int32). Low-precision integer compute, not 4-bit.
   - Prefill: the 4-bit weight is dequantized to fp16 and run through an fp16 tensor-core GEMM. 4-bit
     is storage only on this path.
   - GGUF never multiplies in 4-bit.
6. Why compute does not go to 4-bit:
   - No 4-bit matmul hardware before Blackwell fp4. A 4-bit weight must pair with a supported operand
     (int8).
   - Activations carry outliers and do not survive 4-bit; int8 or fp8 is the floor.
   - Matmul precision is set by min(hardware support, activation tolerance) = int8 or fp8 today.
7. Low-precision COMPUTE is the speedup on compute-bound models. fp8 dynamic-activation (both operands
   fp8, fused via torch.compile) ran the SAM3 forward at 202 ms vs 428 ms bf16, with detection parity
   (31 vs 30 dets). Weight-only quant cannot reach this; it needs the activation quantized too.

## nvfp4 feasibility (this setup)

1. Hardware: supported. sm120 has native fp4 (nvfp4: E2M1 plus an fp8 E4M3 scale per 16-value block)
   tensor cores.
2. Software: not available in this environment. The torchao low-precision kernels fail to load --
   `_C_mxfp8.cpython-310...so` (built for Python 3.10; the runtime is 3.12) and `_C_cutlass_90a...so`
   (sm90a Hopper, not sm120). No working fp4 matmul kernel is present, so an nvfp4 model would have
   nothing to run on.
3. To enable: build torchao and its CUDA kernels from source for cu128 + sm120 + Python 3.12, or
   obtain a matching wheel. Effort class matches the shelved gemlite / ONNX-GPU work.
4. ROI is low now. End-to-end `detect()` is 398 ms; about 190 ms is image preprocessing plus mask
   upsampling, which fp4 does not touch. A perfect fp4 forward would save at most ~50 ms end-to-end.
   The bottleneck has moved from the matmul to the processor.
5. Accuracy is unverified. fp4 on a compute-bound vision model may degrade mask and box quality.
   Parity held at fp8; it is not established at fp4.

## Compile startup cost + kernel caching

torch.compile pays a one-time build on the first call. Measured for fp8-dynamic (RESULT = time of
the first detect, which triggers the compile):

| kernel cache | first-call compile | note |
|--------------|-------------------:|------|
| cold (empty `TORCHINDUCTOR_CACHE_DIR`) | 307 s | full trace + codegen + fp8 autotune |
| warm (561 MB on disk, FX graph cache on) | 124 s | codegen reused; fp8 autotune not fully cached |

1. A persistent inductor cache (`TORCHINDUCTOR_CACHE_DIR` on a mounted path + `TORCHINDUCTOR_FX_GRAPH_CACHE=1`)
   cuts the warm restart 307 -> 124 s. Necessary, but not sufficient: 124 s is still too long for a
   snappy service restart. The residual is fp8 GEMM autotuning the inductor cache does not persist,
   made worse because the fp8 cutlass kernels (`_C_mxfp8`, `_C_cutlass_90a`) do not load in this env.
2. To drive startup near zero, use `torch.compiler.save_cache_artifacts()` / `load_cache_artifacts()`
   (bundles autotune into one portable blob, saved at build time, loaded at startup) or AOTInductor
   (`torch.export` + `aot_compile` -> a standalone .so loaded in seconds; SAM3 may not export cleanly).
3. The cache dir must live on a mounted path, not /tmp (the container wipes it), and is invalidated by
   any change to the torch version, GPU arch, CUDA version, or quant config.

## Conclusion

- Fastest forward: fp8 dynamic-activation + `torch.compile` = 202 ms, 1710 MiB, parity. But its
  compile is fragile and slow to warm (124 s even cached), and the forward is NOT the end-to-end
  bottleneck (preprocessing is), so its ~60 ms edge over bf16 rarely pays for the compile pain.
- Pragmatic compiled choice: bf16 + `torch.compile` = 265 ms, 2219 MiB, lossless, more robust compile.
- Safe default today: nf4, no compile -- until the compile startup (mega-cache / AOTInductor) or the
  image preprocessing is solved.
- Cost: `torch.compile` builds on the first call (~1-3 min, one-time per process). Fine for a
  long-running service that compiles once at startup; not for short-lived CLI runs.
- The earlier ~230 ms fp8 memory is confirmed and beaten (202 ms), on the transformers +
  torchao + torch.compile runtime -- no ONNX/TensorRT needed. onnxruntime here has no CUDA
  provider, so the ONNX-GPU path is unavailable regardless.
- Next latency lever is the image processor (GPU-side preprocessing or caching), not a smaller weight
  format: ~190 ms of the 398 ms end-to-end detect is preprocessing, which quantization does not touch.
- nvfp4 is deferred: the hardware supports it but the torchao fp4 kernels do not build in this setup,
  and the end-to-end payoff is small while preprocessing dominates.

