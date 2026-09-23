# sam3-concurrency-bench RESULTS

GPU NVIDIA GeForce RTX 5070 Laptop GPU, SAM3 nf4, frame synthetic-720p. SAM3 loaded ALONE.
These numbers are an optimistic upper bound. The live system shares this GPU with Gemma and whisper.

## Single forward latency

| metric | ms |
|---|---|
| p50 | 409.2 |
| p95 | 437.8 |
| min | 385.2 |
| max | 447.6 |

## N concurrent detect() vs N serial

| N | serial ms | concurrent ms | speedup |
|---|---|---|---|
| 2 | 812.7 | 834.4 | 0.97x |
| 4 | 1643.4 | 1656.0 | 0.99x |
| 8 | 3287.8 | 3325.1 | 0.99x |

## K prompts batched into one forward vs K separate

| K | separate ms | batched ms | speedup | peak MiB | returned |
|---|---|---|---|---|---|
| 2 | 808.4 | 780.2 | 1.04x | 1231 | 2 |
| 4 | 1595.1 | 1538.0 | 1.04x | 1991 | 4 |
| 8 | 3223.0 | 3161.6 | 1.02x | 3457 | 8 |

## Findings

- Single detect is about 409.2 ms. The ceiling is about 2.4 forwards/s if SAM3 owns the GPU alone.
- Concurrency gives up to 0.99x. Threads do not help. One GPU, one model, forwards serialize.
- Batching works and returns K results. Best speedup 1.04x, so no real throughput win.
- Batching costs VRAM: peak grows to 3457 MiB at the largest K.
- Levers left: fp8+compile (about 0.2 s in the quant bench), a lower per-highlight rate, or a dedicated GPU.
- SAM3 ran ALONE here. With Gemma and whisper on the same GPU, expect worse.

