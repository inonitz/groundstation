# serving-bench

Where do the models RUN — which fit co-resident on the 8 GiB GPU, which move to CPU, and what
does each choice cost? Sibling of hebrew-command-bench (which asks what the models GET RIGHT).
This is also the future home of the ASR serving comparison (CT2 vs whisper.cpp quants vs
sherpa-onnx/onnxruntime) once the team delivers the recordings (RECORDING-SPEC.md).

## Files

- `census.py` — VRAM census + CPU-offload probe. Guarded: a model loads only if free VRAM >=
  its measured cost + 1 GiB, RAM-guarded on CPU runs, never everything at once.
- `RECORDING-SPEC.md` / `RECORDING-SCRIPT.md` — what the team records for the ASR round.
- `results/` — date-stamped JSONs.

## Census results — 2026-09-02, RTX 5070 Laptop 8151 MiB, 32-thread CPU

Solo residency (loaded + one warm request, measured by nvidia-smi):

| model | VRAM resident | free left |
|---|---|---|
| DictaLM-1.7B Q4 | 1,582 MiB | 6,015 MiB |
| TranslateGemma-4B Q4 | 3,035 MiB | 4,563 MiB |
| Qwen3-VL-4B Q4 + mmproj + q4 KV | 3,821 MiB | 3,777 MiB |

Pairs (guard skips what cannot fit — the skip is itself the answer):

- qwen3vl + dicta: fits — 5,401 MiB combined, 2,196 MiB free.
- qwen3vl + tgemma: DOES NOT FIT (3,777 free < 3,035 + 1,024 margin). The round-6 split cannot
  co-reside with the VLM on this card.

CPU offload (-ngl 0, 16 threads, 20 real command translations):

| model | p50 | p95 | max |
|---|---|---|---|
| DictaLM CPU | 199 ms | 430 ms | 502 ms |
| TranslateGemma CPU | 624 ms | 1,228 ms | 1,348 ms |

## Reading (recommendation, owner rules)

- DictaLM passes the CPU budget (p50 199 ms < 500 ms): the command-translation stage can leave
  the GPU entirely, at roughly +80 ms p50 vs GPU.
- TranslateGemma fails the tight budget on CPU (p50 624, p95 1,228) and cannot share the GPU
  with the VLM. Perception commands are rarer and not inner-loop, so ~0.6–1.2 s MAY be
  acceptable there — owner call. Alternatives: dicta-everywhere (perception drops 78%→56%),
  or the Hebrew intent-parser lane (docs/research/2026-09-02-hebrew-intent-parsing.md), which
  deletes translation from the command path and frees 2.5 GiB of the VLM's company.
- Likely 8 GiB topology: GPU = Qwen3-VL + vision stack (OmDet+SAM2.1 — NOT yet measured, needs
  the smart-scene env; next census item). CPU = whisper CT2-int8 (ASR round) + DictaLM +
  TranslateGemma bursty. RAM: those three CPU models total ~5 GiB of the ~9 GiB available.
- Not measured: vision pair, whisper (faster-whisper not installed — scripted install lands
  with the ASR round), production hardware (rerun census.py there as-is).
