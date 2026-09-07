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

Addendum 2026-09-07 — full serving-config census (same host, measured by nvidia-smi delta
after load + one real inference each: a session clip for whisper, a real translation/completion
for the LLMs, a 720p frame for YOLO). Key finding: llama-server DEFAULTS allocate 4 parallel
slots x 4096-ctx KV; the 2026-09-02 census rows above carry that overhead. "Lean" = -c 512
(dicta/tgemma) or -c 2048 (qwen), 1 slot. Identical outputs at default vs lean everywhere.

| model | defaults | lean |
|---|---|---|
| Qwen3-VL-4B Q4 + mmproj (prod flags: fa + q4 KV) | 3,821 MiB | 3,738 MiB |
| TranslateGemma-4B Q4_K_M | 3,029 MiB | 2,552 MiB (q8 KV: 2,521) |
| DictaLM-1.7B Q4 | 1,583 MiB | 1,187 MiB |
| whisper ivrit large-v3-turbo fp16 | 1,841 MiB | - |
| whisper q6_k | 940 MiB | - |
| whisper q5_k (desk-test default) | 838 MiB | - |
| whisper q4_k / q4_0 | 743 MiB both | - |
| yolo26n-seg (720p inference) | 286 MiB | - |

This SUPERSEDES the 2026-09-06 owner-ruled whisper estimate ("about the file size, ~550 MiB"):
measured overhead is ~+290 MiB over file size on every whisper quant.
Planner prompt + shots tokenize to 779 tokens, so -c 2048 holds the text path; the image-token
cost of a VLM gate call at -c 2048 is UNMEASURED — verify before pinning the lean qwen config.

End-stack scenarios against the REAL free ceiling, 7,598 MiB (8,151 total minus the ~440 MiB
driver/display carve-out measured idle; the carve-out can move with display load):

| scenario (all lean) | sum | verdict |
|---|---|---|
| qwen 3,738 + tgemma 2,552 + whisper q4_k 743 + SAM3 nf4 886 + yolo 286 | 8,205 | over by 607 |
| same, whisper on CPU | 7,462 | +136 — paper-thin |
| same, tgemma Q3_K_M (~2,050 est, quality unverified) + whisper q4_k on GPU | 7,703 | over by 105 |
| tgemma Q3_K_M est + whisper on CPU | 6,960 | +638 — fits |
| tgemma on CPU (measured p50 624 ms short cmds), whisper q5_k on GPU | 5,748 | +1,850 — roomy |

Unmeasured items in every scenario: SAM3 numbers are the 2026-09-04 isolated peaks (not
re-measured co-resident), mmproj image-encode spikes, whisper.cpp CPU real-time factor,
tgemma Q3 size and quality. Conclusion unchanged in direction, now with numbers: everything-
on-GPU does not fit at Q4; one of tgemma or whisper moves to CPU, or tgemma drops to Q3.

Real-node + co-resident census (2026-09-07 night, owner-directed). ASR measured via the ACTUAL
llm_to_action_asr_server node (whisper-whisper backend, --fa, -l he, threads 1), NOT whisper-server.
VLM image cost measured with the production vlm_client path (1280x720 frame, JPEG q80, real ask).

| item | setting | measured |
|---|---|---|
| ASR node, whisper q4_k | asr_server --fa --language=he --threads=1 | 734 MiB |
| ASR node, whisper q5_k | same | 829 MiB |
| Qwen3-VL text-only resident | prod flags, -c 2048 -np 1 | 3,738 MiB |
| Qwen3-VL +1 real 1280x720 q80 image ask | prompt=1,236 tok, completion=106, e2e 2,911 ms | +89 MiB (peak 3,827) |
| tgemma Q4_K_M, -c 256 -np 1, GPU | 20 real perception sents: p50 242, p95 346 ms | 2,479 MiB |
| tgemma Q4_K_M, -c 256, CPU -ngl0 t16 | same 20 sents: p50 1,599, p95 2,111 ms | 0 GPU |
| tgemma system-prompt (TGEMMA_PROMPT template) | tokenized | 74 tok; +longest perception sent = 115 tok |
| DictaLM Q4, CPU -ngl0 t16 -c512 | warm translate ok | 0 GPU |
| YOLO26n-seg | 720p predict, device 0 | 286 MiB |

FULL OWNER TOPOLOGY, loaded co-resident and measured together (Qwen prod + tgemma -c256 GPU +
whisper q5_k node GPU + YOLO GPU + DictaLM on CPU): resident 7,505 MiB, free 93 MiB of 8,151.
SAM3-nf4 (886) does NOT fit on top -- over by ~793 MiB. Real number, not arithmetic.
To seat SAM3-nf4: move tgemma to CPU (frees 2,479, costs p50 1.6 s perception) OR whisper to CPU
(frees 829, hot-loop latency unmeasured) OR both off-GPU. Qwen image ask adds only +89 MiB
transiently, so the image path is NOT a residency risk. The earlier ~440 MiB driver carve-out note
was wrong: at full load used reached 8,058 of 8,151, so ~93 MiB is the true floor.

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
   SUPERSEDED 2026-09-04: the updated whisper.cpp build (ggml 0.18) DOES accept k-quants
   (q2_k q3_k q4_k q5_k q6_k; the M/S mixture suffixes remain llama.cpp-only). q4_k/q5_k/q6_k
   of ivrit whisper-large-v3-turbo were produced and q5_k (547.4 MB) is the desk-test default.
   Whisper VRAM measured 2026-09-07 (supersedes the file-size estimate): q4_0/q4_k 743,
   q5_k 838, q6_k 940, fp16 1,841 MiB resident — about +290 MiB over file size each.
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
