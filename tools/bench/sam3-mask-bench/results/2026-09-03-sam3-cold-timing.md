# SAM3 COLD end-to-end timing per quantization (RTX 5070, sm120)

Inductor + Triton caches WIPED before every mode -- the true fresh-container cold start.
Fixed input street-crowd-0.jpg + concept 'person', 12 warm reps. `cold first` = the first
detect(), i.e. the cold torch.compile build for compiled modes. `to first result` = load + cold
first. `warm detect` = steady end-to-end detect() p50 after compile.

| mode | load s | COLD first detect s | to first result s | warm detect p50 ms | VRAM MiB | dets |
|------|-------:|--------------------:|------------------:|-------------------:|---------:|-----:|
| nf4 | 5.3 | 1.2 | 6.5 | 639.3 | 995 | 8 |
| bf16 | 5.2 | 1.1 | 6.3 | 627.3 | 2156 | 8 |
| fp8 | 5.5 | 1.3 | 6.8 | 785.5 | 1710 | 8 |
| bf16+compile | 4.7 | 49.2 | 53.9 | 437.1 | 2505 | 8 |
| fp8+compile | 5.3 | 313.6 | 318.9 | 441.2 | 1710 | 8 |

## Analysis (the crux)

1. Eager modes are cold-ready in ~6-7 s. No compile, so a fresh container serves almost immediately.
2. Cold compile is the whole cost of the compiled modes: bf16+compile 54 s, fp8+compile 319 s.
   These are the real fresh-container numbers (earlier 18 s / 78 s were polluted by a warm /tmp cache).
3. fp8+compile is DOMINATED by bf16+compile. Warm inference is a tie (441 vs 437 ms), because the
   fp8 forward win is swamped by the ~190 ms preprocessing shared by every mode. But fp8's cold
   compile is 6x longer (319 vs 54 s). Same speed, far worse startup, more fragile. Do not use fp8.
4. The real trade is compile vs eager: compile buys ~190 ms of inference (630 -> 440 ms) for a 48 s
   cold-start penalty (6 -> 54 s, bf16). Worth it only for a long-running service that starts rarely.
5. Detection parity holds (8 dets everywhere). VRAM all fits 8 GiB.

## Can fp8 + compile be cached to ~eager load time? NO (measured)

Priorities are VRAM first, then inference speed. fp8 is the VRAM choice (1710 MiB vs bf16-compile
2505 MiB), so the real question is whether its compile can be cached away. Three mechanisms tested:

| mechanism | cold | cached restart | result |
|-----------|-----:|---------------:|--------|
| inductor + Triton disk cache | 326 s | ~80-125 s | far above 10 s |
| mega-cache (save/load_cache_artifacts, 57 MB bundle) | 326 s | 178 s | still re-traces + partial autotune |
| AOTInductor (prebuilt .so, the only true ~10 s path) | - | - | FAILS on this model + GPU |

AOTInductor is the only mechanism that removes the runtime compile entirely. It fails OUT OF THE BOX
for two reasons, both measured -- but BOTH are workaroundable (see below):
1. The DETR decoder reads the vision grid size from a runtime TENSOR:
   `spatial_shape = (spatial_shapes[0,0], spatial_shapes[0,1])` -> `_get_rpb_matrix` (modeling_sam3.py
   ~line 1795). That product is the unbacked symint `u0*u1`. It is NOT a real data dependency (no
   nonzero/topk); it is the image grid H*W, which is CONSTANT for the fixed processor input size (the
   concrete 5184 = 72x72 appears next to it). `torch.export` traces (23 s) but cannot lower it because
   the constant is carried as a tensor. FIX: specialize `spatial_shapes` to Python ints (a small patch
   to the vendored model, or a wrapper) -> the attention shape goes static.
2. The fp8 AOT compile OOMs the 8 GiB GPU (dmesg NV_ERR_NO_MEMORY). FIX: AOTInductor compiles ONCE,
   anywhere -- compile on a bigger Blackwell GPU (or autotune-off) and ship the .so; runtime needs only
   the 1710 MiB model, no compile workspace.

Verdict: OUT OF THE BOX, fp8 + compile cannot reach ~10 s startup here; the best is 178 s (mega-cache).
But AOTInductor is NOT a permanent wall -- with the spatial_shapes specialization + an off-box compile
it could give the ~10 s fp8 load. That is an engineering task (patch, re-export, compile elsewhere,
re-verify detection parity), deferred to a future session -- UNVERIFIED until executed.

## Conclusion

- fp8 is the VRAM choice (1710 MiB) at every setting -- keep it. VRAM is priority #1.
- fp8 + compile: 441 ms inference, but 319 s cold / 178 s cached startup that cannot be cut to ~10 s.
  Use it for a long-running service that starts once and stays up. Eat the compile at launch.
- fp8 eager: 1710 MiB, ~7 s startup, 786 ms inference. Use it when restarts are frequent. Detection is
  on-demand (the "highlight" keyword), so 786 ms per call is acceptable and avoids the compile entirely.
- The ~190 ms preprocessing is the shared floor and the next real optimization.
