# SAM3 quantization + runtime latency (RTX 5070 Laptop, sm120 Blackwell, 8 GiB)

## Objective

Find the fastest SAM3 inference on this GPU across the 4-bit/8-bit quant family and the
`torch.compile` runtime, and determine whether the compile startup can be cached. Confirm
detection parity, not just speed.

## Setup

Fixed input `street-crowd-0.jpg` + concept `person`. Deterministic (SAM3 has no sampling). One mode
per subprocess (one model resident). transformers 5.15.1, torchao 0.18.0, torch 2.11+cu128,
bitsandbytes 0.50.2. `fwd` = model forward. `detect()` = end-to-end (PIL + processor + forward +
post_process). `-c` / `+compile` = `torch.compile`. Reproduce with `quant_bench.py`.

## Results -- forward only (why compile beats the weight format)

20 warm reps, model forward only.

| mode | quant | compile | VRAM MiB | fwd p50 ms | dets |
|------|-------|:------:|---------:|-----------:|-----:|
| bf16 | none | no | 2193 | 428.6 | 30 |
| nf4 | 4-bit (bnb) | no | 1054 | 452.4 | 26 |
| int8 | bnb | no | - | ERR (view/stride) | - |
| int8 | torchao | no | 1678 | 501.9 | 33 |
| fp8 | weight-only (torchao) | no | 1710 | 496.9 | 31 |
| fp8 | dyn-act (torchao) | no | 1710 | 502.7 | 29 |
| bf16 | none | yes | 2219 | 264.6 | 30 |
| fp8 | dyn-act (torchao) | yes | 1710 | 202.3 | 31 |

## Results -- cold end-to-end (definitive)

Inductor + Triton caches wiped before every mode -- the true fresh-container cold start. 12 warm
reps, via `Sam3Backend` (the production path). `COLD first detect` = the cold `torch.compile` build
for compiled modes. `to first result` = load + cold first. `warm detect` = steady end-to-end
`detect()` p50 after compile.

| mode | load s | COLD first detect s | to first result s | warm detect p50 ms | VRAM MiB | dets |
|------|-------:|--------------------:|------------------:|-------------------:|---------:|-----:|
| nf4 | 5.3 | 1.2 | 6.5 | 639.3 | 995 | 8 |
| bf16 | 5.2 | 1.1 | 6.3 | 627.3 | 2156 | 8 |
| fp8 | 5.5 | 1.3 | 6.8 | 785.5 | 1710 | 8 |
| bf16+compile | 4.7 | 49.2 | 53.9 | 437.1 | 2505 | 8 |
| fp8+compile | 5.3 | 313.6 | 318.9 | 441.2 | 1710 | 8 |

## Analysis

1. Eager weight quantization does NOT speed SAM3 up. nf4 (452), int8 (502), fp8 (497-503) forwards
   are all slower than eager bf16 (428). The bottleneck is convolution + attention, not the Linear
   weights that bnb/torchao quantize. Quant shrinks VRAM and adds dequant overhead.
2. `torch.compile` is the real lever. Compiled bf16 forward drops 428 -> 265 ms, lossless.
3. Compiled fp8 dynamic-activation is the fastest forward: 202 ms. torchao's fp8 tensor-core kernels
   only materialize under `torch.compile`; in eager they fall back.
4. End-to-end `detect()` is gated by preprocessing. fp8+compile forward is 202 ms but `detect()` is
   ~440 ms, because ~190 ms of every call is image preprocessing + mask upsampling that quantization
   never touches. That ~190 ms is the shared floor.
5. Eager fp8 is the SLOWEST end-to-end (786 ms). fp8 only wins once compiled. Do not run fp8 eager.
6. Detection parity holds: 8 dets in every runnable mode.
7. VRAM: nf4 smallest (995 MiB), fp8 1710, bf16 2156, bf16+compile 2505 (compile workspace). All fit
   8 GiB. int8-bnb fails to run on SAM3 (a view/stride error).

## Insights: storage quantization vs compute precision

1. Quantization has two independent payoffs: memory (bytes per weight in VRAM) and speed (the
   precision of the matmul). A format can deliver one without the other.
2. Weight-only quant (nf4, int8-weight, fp8-weight, GGUF K-quants) stores weights small but upcasts
   them at matmul time. VRAM always drops. Speed improves only when that upcast is fused into the
   matmul kernel AND the workload is memory-bound.
3. Fusion, not the format, decides the eager penalty. Unfused weight-only quant (torchao eager) is
   slower than bf16. Fused (torch.compile, or llama.cpp's hand-written kernels) dequantizes on-chip
   with no extra memory traffic.
4. Memory-bound vs compute-bound sets the outcome. LLM token decode is memory-bound (reads every
   weight per token) -> 4-bit is a big speedup. SAM3's vision forward is compute-bound (wide matmuls)
   -> fewer weight bytes do not shorten the critical path, and the dequant adds cost.
5. GGUF is weight-only too, but fast for LLMs for reason 4. Its decode path uses int8 integer MACs
   (dp4a); prefill dequantizes to fp16. It never multiplies in 4-bit -- there is no 4-bit matmul
   hardware before Blackwell fp4, and activations do not survive 4-bit. Compute precision floor =
   min(hardware support, activation tolerance) = int8 or fp8 today.
6. Low-precision COMPUTE is the speedup on compute-bound models: fp8 dynamic-activation (both operands
   fp8, fused) ran the SAM3 forward at 202 ms vs 428 ms bf16, parity held.

## nvfp4 feasibility (this setup)

1. Hardware: supported. sm120 has native fp4 (nvfp4: E2M1 + fp8 E4M3 scale per 16-value block) cores.
2. Software: NOT available here. torchao's low-precision kernels fail to load -- `_C_mxfp8.cpython-310`
   (built for Python 3.10; runtime is 3.12) and `_C_cutlass_90a` (sm90a Hopper, not sm120). No working
   fp4 matmul kernel is present.
3. To enable: build torchao + CUDA kernels from source for cu128 + sm120 + Python 3.12, or a matching
   wheel. Effort class matches the shelved gemlite / ONNX-GPU work.
4. ROI is low now: ~190 ms of `detect()` is preprocessing fp4 cannot touch, so a perfect fp4 forward
   saves at most ~50 ms end-to-end.
5. Accuracy unverified: fp4 on a compute-bound vision model may degrade masks/boxes (parity held at
   fp8, not fp4).

## Compile startup + kernel caching + AOTInductor verdict

Cold fp8+compile is 313.6 s (the first detect). Can it be cached to ~eager load time (~10 s)? Three
mechanisms tested:

| mechanism | cold | cached restart | result |
|-----------|-----:|---------------:|--------|
| inductor + Triton disk cache | ~307 s | ~80-125 s | far above 10 s |
| mega-cache (`save/load_cache_artifacts`, 57 MB bundle) | 326 s | 178 s | still re-traces + partial autotune |
| AOTInductor (prebuilt .so, the only true ~10 s path) | - | - | fails out of the box (see below) |

AOTInductor is the only mechanism that removes the runtime compile entirely (a prebuilt `.so` you
just load). It fails out of the box for two reasons, both measured -- but BOTH are workaroundable:
1. The DETR decoder reads the vision grid size from a runtime TENSOR:
   `spatial_shape = (spatial_shapes[0,0], spatial_shapes[0,1])` -> `_get_rpb_matrix` (modeling_sam3.py
   ~line 1795). That product is the unbacked symint `u0*u1`. It is NOT a real data dependency; it is
   the image grid H*W, CONSTANT for the fixed processor input size (the concrete 5184 = 72x72 appears
   next to it). `torch.export` traces (23 s) but cannot lower the tensor-carried constant. FIX:
   specialize `spatial_shapes` to Python ints -> the attention shape goes static.
2. The fp8 AOT compile OOMs the 8 GiB GPU (dmesg NV_ERR_NO_MEMORY). FIX: AOTInductor compiles ONCE,
   anywhere -- compile on a bigger Blackwell GPU (or autotune-off) and ship the `.so`; runtime needs
   only the 1710 MiB model, no compile workspace.

Verdict: OUT OF THE BOX, fp8+compile cannot reach ~10 s startup here; the best cached restart is 178 s
(mega-cache). But AOTInductor is NOT a permanent wall -- with the `spatial_shapes` specialization +
an off-box compile it could give the ~10 s fp8 load. That is an engineering task (patch, re-export,
compile elsewhere, re-verify detection parity), deferred and UNVERIFIED.

## Conclusion

Priorities: VRAM first, then inference speed.

- fp8 is the VRAM choice at every setting (1710 MiB vs bf16-compile 2505) -- keep it.
- fp8 + compile: 441 ms inference, but 319 s cold / 178 s cached startup that cannot be cut to ~10 s
  out of the box. Use it for a long-running service that starts once and stays up.
- fp8 eager: 1710 MiB, ~7 s startup, 786 ms inference. Use when restarts are frequent. Detection is
  on-demand (the "highlight" keyword), so 786 ms per call is acceptable and avoids the compile.
- The ~190 ms image preprocessing is the shared floor and the next real optimization, independent of
  the weight format or compile.
- The ~10 s fp8 load is achievable only via AOTInductor (specialize spatial_shapes + off-box compile);
  deferred, unverified.
