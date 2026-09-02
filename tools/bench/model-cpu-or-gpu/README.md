# where-models-run

Measures where each model can run. Three questions, three measurements: how much GPU memory
each model actually uses (census), which models fit on the GPU together (pair loading), and
how fast a model runs on the CPU instead (offload latency). Composed of one script
(`census.py`, rerunnable on any machine) and its results. The planned ASR engine comparison
will live here too — DEFERRED until the Recognizer reaches an alpha (owner ruling 2026-09-02).

## Sections

| section | what is in it |
|---|---|
| [Contents](#contents) | the files |
| [Census](#census--2026-09-02-rtx-5070-laptop-8151-mib-vram-32-thread-cpu) | measured VRAM and CPU-offload numbers |
| [Interpretation](#interpretation) | the resulting deployment topology |
| [ASR round](#asr-round--planned-lanes) | the planned ASR lanes and their status |

## Contents

| file | role |
|---|---|
| `census.py` | VRAM census + CPU-offload probe; rerunnable on any host |
| `RECORDING-SPEC.md` | recording protocol + the 65-sentence script |
| `results/` | date-stamped JSON per census run |

Safety properties of `census.py`: a model is loaded only if free VRAM exceeds its measured solo
cost plus a 1 GiB margin; CPU runs are gated on available RAM; models are never all loaded
simultaneously. A skipped load is reported as a result ("does not fit"), not an error.

## Census — 2026-09-02, RTX 5070 Laptop (8151 MiB VRAM), 32-thread CPU

Solo residency, measured by nvidia-smi after load plus one warm request:

| model | VRAM resident | free remaining |
|---|---|---|
| DictaLM-1.7B Q4 | 1,582 MiB | 6,015 MiB |
| TranslateGemma-4B Q4 | 3,035 MiB | 4,563 MiB |
| Qwen3-VL-4B Q4 + mmproj + q4 KV | 3,821 MiB | 3,777 MiB |

Pair loading:

- qwen3vl + dicta: fits. Combined 5,401 MiB, 2,196 MiB free.
- qwen3vl + tgemma: does not fit (3,777 MiB free < 3,035 + 1,024 margin). The round-6 split
  configuration cannot co-reside with the VLM on this GPU.

CPU offload, llama.cpp with -ngl 0, 16 threads, 20 command translations:

| model | p50 | p95 | max |
|---|---|---|---|
| DictaLM | 199 ms | 430 ms | 502 ms |
| TranslateGemma | 624 ms | 1,228 ms | 1,348 ms |

## Interpretation

- DictaLM on CPU meets any realistic voice-loop budget (p50 199 ms, ~80 ms above its GPU
  figure). The command-translation stage does not require GPU residency.
- TranslateGemma on CPU is marginal (p50 624 ms, p95 1.2 s). Perception commands are outside
  the tight control loop, so this may be acceptable; alternatives are DictaLM-everywhere
  (perception accuracy drops 78% → 56%) or the direct-Hebrew planning lane, which removes
  translation from the command path entirely.
- Candidate topology for the 8 GiB host: GPU holds Qwen3-VL plus the vision stack; CPU holds
  ASR and both translators, all of which are burst workloads. The three CPU models total
  roughly 5 GiB of RAM against ~9 GiB available.
- Census part 2 (2026-09-02, `census.py --stack`): the full demo stack co-resident, one real
  inference per component before each measurement:

| component | VRAM delta | running total | free |
|---|---|---|---|
| Qwen3-VL-4B (llama-server) | 3,822 MiB | 3,822 | 3,777 |
| OmDet-Turbo swin-tiny | 863 MiB | 4,685 | 2,913 |
| SAM2.1-base (ultralytics) | 728 MiB | 5,413 | 2,185 |
| wav2vec2-300M fp16 (ASR) | 104 MiB | 5,517 | 2,081 |

  The full stack fits with 2,081 MiB headroom. Adding DictaLM on GPU (1,582 MiB) would leave
  ~500 MiB, below the 1 GiB safety margin; it stays on CPU (measured p50 199 ms). Measured
  topology: GPU = Qwen3-VL + OmDet + SAM2.1 + ASR; CPU = translators. whisper-CT2 remains
  unmeasured (its ~0.9 GiB estimate fits the headroom if the ASR round selects it).
- Not yet measured: whisper serving stacks (ASR round), production hardware. Both census
  scripts rerun unchanged on any host.

## ASR round — planned lanes

1. ivrit-ai whisper-large-v3-turbo via faster-whisper/CT2 with VAD, GPU and CPU int8.
2. The same model in whisper.cpp via the project's asr_server. Quantized 2026-09-02:
   q4_0 (474 MB), q5_1 (624 MB), q8_0 (874 MB) alongside the fp16 ggml (1,625 MB), all
   load-tested with whisper-cli. Note: this whisper.cpp build supports classic quant types
   only; k-quants (Q4_K_M) are not available for whisper models.
3. sherpa-onnx (onnxruntime), GPU and CPU.
4. imvladikon/wav2vec2-xls-r-300m-lm-hebrew: 300M CTC model with a swappable n-gram language
   model, Apache-2.0, trained on ~518 h of Hebrew (2022). Hypothesis, stated in advance: with a
   KenLM built over this project's command corpus it outperforms whisper on in-domain command
   WER under noise and on latency, cannot hallucinate fluent text on wind or silence (a known
   whisper failure mode; CTC degrades to character noise instead), and underperforms on open
   text — which would argue for a per-path ASR split mirroring the translator split.
   Dependencies: pyctcdecode + kenlm (scripted install; not yet approved).

Evaluation set for all lanes: the team recordings per RECORDING-SPEC.md, plus the public
ivrit-ai evaluation set for open-text reference. Metrics: WER/CER per sentence class and per
environment, latency, peak memory, and hallucination-on-noise rate.
