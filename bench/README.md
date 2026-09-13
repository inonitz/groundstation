# Benchmarks

Every measured component has a benchmark here. This file is the prologue: why the benchmarks
exist, the measurement procedure they all follow, and an index. **Each benchmark has its OWN
README** with the full per-bench detail (why it exists, how to run start-to-finish, results over
runs). If you are about to benchmark something and it has no README, FLAG that first and write one.

## The measurement procedure (every benchmark follows this)

A LOCAL measure -> fix -> improve loop for one component; not a global rule.

1. Run the measurement. Attribute every failure to a stage and a cause; keep the raw per-case
   input/output (the JSON dumps) so a change is gated by the cases that FLIPPED.
2. Determinism: temperature 0, one pass per case (prove determinism once). One model on the GPU at
   a time. State a duration estimate BEFORE every GPU run.
3. A new deterministic guard/rewrite rule ships only with: measured evidence (>= 2 real failures),
   positive cases, adversarial negatives (lookalikes it must NOT touch), and a clean self-test.
   Zero false fires is the gate.
4. Amend, then RE-RUN THE FULL measurement and compare per-set counts to the previous run. At
   temp 0, unchanged code reproduces exactly; any diff is your change. A summary claim without a
   re-run is unverified -- a prompt "fix" once looked good in the summary and had fixed nothing.
5. Record: update the bench's RESULTS.md scorecard IN PLACE; keep the run history in HISTORY.md.
   Full result tables, never abbreviated. Wilson 95% intervals for rates, exact McNemar for paired
   A/B, latency as percentile columns (p50/p95/...).

## The benchmarks

| bench | measures | status |
|---|---|---|
| hebrew-command-bench | recognizer + Gemma intent/plan accuracy, 487 Hebrew commands (text; no ASR/vision) | LIVE, 410/487 |
| whole-system | end-to-end text + audio replay through the live stack | campaign |
| sam3-mask-bench | SAM3 open-vocab detect+mask engine (latency, quant, engine A/B) | campaign (adopted) |
| hebrew_asr | whisper Hebrew quantization WER/CER + latency | campaign |
| yolo26-depth-bench | YOLO26 + depth model ladder | campaign |
| depth-sota-bench | depth SOTA comparison (see DEPTH-BENCHMARKS.md) | campaign |
| model-cpu-or-gpu | CPU-vs-GPU placement census | campaign |
