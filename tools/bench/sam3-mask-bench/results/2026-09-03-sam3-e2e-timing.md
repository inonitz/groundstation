# SAM3 end-to-end timing per quantization (RTX 5070, sm120), via Sam3Backend

Fixed input street-crowd-0.jpg + concept 'person', 15 warm reps. `load` = model ready.
`compile/first` = first detect() (the torch.compile build for compiled modes). `warm detect`
= end-to-end detect() p50 (PIL + processor + forward + post_process). `to first result` =
load + first detect.

| mode | load s | compile/first s | to first result s | warm detect p50 ms | p90 ms | VRAM MiB | dets |
|------|-------:|----------------:|------------------:|-------------------:|-------:|---------:|-----:|
| nf4 | 8.3 | 1.3 | 9.6 | 640.4 | 672.8 | 995 | 8 |
| bf16 | 6.8 | 1.5 | 8.3 | 658.6 | 695.4 | 2156 | 8 |
| fp8 | 5.7 | 1.3 | 7.0 | 741.5 | 827.0 | 1710 | 8 |
| bf16+compile | 4.9 | 18.4 | 23.3 | 490.8 | 605.0 | 2505 | 8 |
| fp8+compile | 5.6 | 78.2 | 83.8 | 435.9 | 451.3 | 1710 | 8 |

## Analysis

1. Load to ready is 5-8 s for every mode (weights + quantize). nf4 is slowest to load (8.3 s, the
   bitsandbytes 4-bit pack). Compiled modes load fast because the compile happens on the first detect.
2. Warm end-to-end detect() (the number production feels):
   - fp8+compile 436 ms (fastest), bf16+compile 491 ms, nf4 640 ms, bf16 659 ms, fp8 742 ms.
   - Eager fp8 is the SLOWEST (742 ms). fp8 only wins once compiled. Do not run fp8 eager.
   - Compile is worth ~200 ms end-to-end (640 -> 436 best-to-best), even though ~190 ms of each call
     is preprocessing the compile does not touch.
3. Compiled fp8 (436) beats compiled bf16 (491) by 55 ms, but its compile is 4x longer (78 vs 18 s
   warm; and far worse cold -- see the caveat). The 55 ms rarely pays for that. bf16+compile is the
   better compiled choice.
4. Detection parity holds: 8 dets in every mode.
5. VRAM: nf4 995 MiB (smallest), fp8 1710, bf16 2156, bf16+compile 2505 (compile workspace). All fit
   8 GiB.

## CAVEAT: the compile numbers here are WARM

`compile/first` (18.4 s bf16, 78.2 s fp8) used the default `/tmp` inductor cache, already populated
by earlier compiles in this session. A fresh container wipes `/tmp`, so a COLD first compile is much
higher -- measured separately at 307 s for fp8 (see 2026-09-03-sam3-quant-latency.md). So
`to first result` is 84 s here but would be ~load + 307 s cold for fp8, ~load + 90 s cold for bf16.
For a fresh-container cold start, persist the cache on a mounted path or use save_cache_artifacts.

## Recommendation

- Robust default: nf4, no compile. Ready in ~10 s, 640 ms detect, smallest VRAM.
- Long-running service that wants speed: bf16 + compile. 491 ms detect, only ~18 s warm compile,
  lossless, robust. Prefer it over fp8+compile.
- fp8 + compile only if 55 ms matters more than a 4x-longer, fragile compile.
- The dominant remaining cost is the ~190 ms image preprocessing, shared by every mode. That is the
  next real lever, not the weight format.
