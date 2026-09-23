# sam3-concurrency-bench

Measures how SAM3 behaves under concurrent and batched requests on one GPU. It answers two
questions: can concurrent threads speed SAM3 up, and can several prompts share one forward.

## Sections

| section | what is in it |
|---|---|
| Objective | the two questions |
| Caveat | SAM3 runs alone, so every number is optimistic |
| How to run | one command and a duration estimate |
| Results | the scorecard file |

## Objective

1. Concurrency. Do N threads calling detect() finish faster than N serial calls? The expectation is
   no: one GPU, one model, and the backend lock serializes forwards.
2. Batching. Can K (frame, concept) pairs run in ONE forward, and is that sub-linear against K
   separate forwards? This is the real lever for parallelism if it holds.

## Caveat

This loads SAM3 alone. The live system also runs Gemma and whisper on the same GPU and VRAM. So
every number here is an OPTIMISTIC upper bound. Real contention makes it worse.

## How to run

Estimated ~2 to 3 min, including model load. One model on the GPU at a time.

    cd /root/groundstation/projects/integration_harden2
    python3 /root/groundstation/bench/sam3-concurrency-bench/concurrency.py

## Results

RESULTS.md holds the scorecard, updated in place. raw.json holds the per-run numbers.
