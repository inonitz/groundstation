# sam3-mask-bench

Measures SAM 3.x against the resident SAM 2.1 on mask quality, latency, and VRAM.
Also tests whether SAM 3.x text-prompt mode could cover OmDet's detector role.
Status 2026-09-03: facebook/sam3 measured bf16-native on GPU; it FITS the budget as a unified
OmDet+SAM2.1 replacement -- overturning the earlier FP32-ONNX cost verdict.

## Sections

| section | what is in it |
|---|---|
| [Objective](#objective) | the one question this bench answers |
| [Environment audit](#environment-audit-2026-09-03) | what is present on this machine, measured |
| [Results so far](#results-so-far) | harness, CPU latency, and the GPU-ONNX block |
| [Preliminary cost verdict](#preliminary-cost-verdict) | the evidence on VRAM, honestly labeled |
| [Open decisions](#open-decisions) | the blockers and rulings that gate the run |
| [Method](#method-planned) | how each remaining number will be produced |
| [Files](#files) | what each file is |

## Objective

Answer, with measured evidence: does SAM 3.x give better masks than SAM 2.1 at equal or lower
cost (VRAM, latency)? Can its text-prompt mode also replace OmDet? The owner decides; this bench
only measures. No integration. The swap point is the injected `mask_for_box` callable in
`perception/engine.py`, which this bench never edits.

## Environment audit (2026-09-03)

All rows below are measured on this machine, not quoted.

| item | state | detail |
|---|---|---|
| GPU | present | RTX 5070, 8151 MiB total, driver CUDA 13.2. Shared with the manager session. |
| SAM 2.1 baseline | present | `/root/models/vision/sam2.1_b.pt` (154 MiB) |
| OmDet detector | present | `/root/models/vision/omdet-turbo-swin-tiny/` |
| SAM 3 port: vietanhdev | DOWNLOADED | FP32 ONNX ViT-H, ungated. `/root/models/vision/sam3-onnx-vietanhdev/` |
| SAM 3 port: embedl (quantized) | GATED | page public, weights access-restricted; needs owner download |
| Official SAM 3.1 | GATED | raw `.pt`, no transformers integration; needs GitHub inference code to run |
| torch | 2.11.0+cu128, CUDA True | CUDA 12.8 runtime libs bundled; torch GPU path works |
| onnxruntime | 1.29.0, CPU only | onnxruntime-gpu needs CUDA-13 libs that do not build here (see Results) |
| Real footage | ABSENT | repo holds only synthetic Gazebo renders; no recorded desk/drone frames |
| Webcam | works | `/dev/video0` reads real 640x480 frames |

### vietanhdev port contents (the runnable SAM 3)

| graph | weights | needed for |
|---|---|---|
| sam3_image_encoder | 1828 MB | box->mask AND text roles |
| sam3_language_encoder | 1615 MB | text (open-vocab) role only |
| sam3_decoder | 117 MB | all roles |

License of the downloaded port: Meta SAM License (weights), MIT (conversion tooling). Internal
measurement, not redistribution, is permitted.

## Results so far

The harness runs end to end. It reuses the MIT-licensed `samexporter.SegmentAnything3ONNX`
runtime class, so the prompt encoding is the reference code, not a reimplementation. The
box->mask path loads only the image encoder and decoder; the language encoder stays unloaded.
SAM 3 returns valid original-resolution masks, shape (N, 1, H, W), dtype bool -- the same shape
SAM 2.1 produces.

### CPU latency (one frame, box->mask, CPUExecutionProvider)

| stage | CPU time | note |
|---|---|---|
| session load | 3.5 s | one-time |
| image encode | 9-11 s | ViT-H image encoder; dominates |
| decode | 2.0 s | per box |

CPU is unusable for live use. Raw: results/2026-09-03-smoke-cpu.json.

### GPU-ONNX is blocked on this machine

The vietanhdev graphs use ONNX opset 21. Three facts collide:

1. ORT 1.29 (onnxruntime-gpu) supports opset 21 but requires CUDA-13 runtime libs. The cu13
   pip wheels do not build on this box, so its CUDAExecutionProvider fails to load
   (`libcublasLt.so.13` missing).
2. ORT 1.22 (onnxruntime-gpu, CUDA-12, matches torch's bundled libs) has no opset-21 Squeeze
   CUDA kernel; session init fails in the memcpy transformer.
3. Forcing ORT 1.22 with graph optimizations disabled runs on GPU but adds 938 memcpy nodes and
   OOMs on a single 1.72 GB attention buffer.

No ONNX-on-GPU number was obtained. The environment was reverted to onnxruntime CPU 1.29.0
afterward. A clean GPU measurement needs either a CUDA-13 base image, or the embedl `.pt2` torch
export, which runs on torch/CUDA (already working here) and sidesteps the ONNX opset trap.

## Results (measured): facebook/sam3, bf16 native, RTX 5070

Run via transformers `Sam3Model`/`Sam3Processor` on torch/CUDA. Frames: recorded desk set
(static single scene -- honest limitation). Raw: results/2026-09-03-native-gpu.json.

### VRAM (bf16)

| quantity | value |
|---|---|
| weights (torch alloc) | 1645 MiB |
| peak incl. activations | 2006 MiB |
| process total (nvidia-smi, incl. CUDA context) | 2348 MiB |
| load time | 1.9 s |

### Latency (text -> detect + mask, per frame)

| p25 | p50 | p75 | p95 | max |
|---|---|---|---|---|
| 434.2 | 434.9 | 435.6 | 438.5 | 441.2 ms |

Single frame, per-call image encode (no embedding cache). ~2.3 fps as measured.

### Open-vocab detection (3 frames; adversarial absent-concept negatives)

| prompt | class | dets/frame | top score |
|---|---|---|---|
| chair | present | 2, 2, 2 | 0.81 / 0.75 / 0.72 |
| keyboard, monitor, cup, hand, person, laptop | (absent from scene) | 0 | 0 |
| elephant, airplane, zebra, giraffe | ADVERSARIAL absent | 0 | 0 |

The model detected the real object (chair) with high confidence and fired ZERO on all four
adversarial absent concepts -- clean presence behavior, the exact failure the VLM presence gate
guards against. Overlay for human review: overlays/desk_chair_overlay.png.

## Demo suite (real images)

9 owner-supplied images with prompts generalized from the recognize.py logs (tests/manifest.json).
SAM3 bf16 vs the current Qwen3-VL pipeline (the logs are the reference). Overlays in overlays/;
raw in results/2026-09-03-suite.json.

KEY FINDING: SAM3 is a concept segmenter, not an instruction follower.

| image | instruction prompt (from logs) | bare concept | current pipeline (log) |
|---|---|---|---|
| damaged tower | 0 | window: 47 @0.92 | 1 window |
| cinema audience | 0 | person: 17 @0.97 | ~15 (one whole-image box) |
| convoy | 0 | person: 30 @0.95 | -- |
| truck, armed | 0 | person: 10 @0.96 | 8 |
| two buildings | 0 | person: 4 @0.94 | 3 |
| camouflaged man | 0 | person: 1 @0.98 | 1 |
| building render | leftmost top window: 1 @0.84 | -- | 1 |
| overhead RPG | person aiming the weapon: 1 @0.77 | -- | 1 |
| street | all cars: 7 @0.91 | -- | OmDet |
| truck | a person holding a weapon: 7 @0.80 | -- | notify 2/6 |

Findings, numbered:
1. Instruction-style prompts ("Highlight all the people in the scene in great detail") return 0.
   SAM3 needs a bare concept ("person", "window").
2. With concepts, SAM3 exhaustively segments every instance at 0.92-0.98, beating the current
   pipeline on count and confidence (47 vs 1 window; 17 instances vs a single whole-image box).
3. It found the camouflaged man and all damaged-tower windows that the instruction prompts missed.
4. One adversarial-absent miss: "boilers" (absent) grounded 1 @0.63 -- a presence-gate case; a
   score threshold or the existing VLM presence gate filters it.
5. Implication: SAM3 is NOT a drop-in for the instruction pipeline. Paired with the resident VLM
   as a concept-extraction front-end (instruction -> concept -> SAM3), it exhaustively segments
   better than the OmDet-box + SAM2 approach. That is the integration shape to evaluate next.

## Quantization (measured, bitsandbytes via transformers)

Each config isolated in its own process. Frame set: recorded desk (one static scene).
Raw: results/2026-09-03-quant.jsonl.

| config | weights | peak | process total | latency p50 | chair (present) | elephant (adversarial) |
|---|---|---|---|---|---|---|
| bf16 | 1645 MiB | 2006 MiB | 2348 MiB | 333 ms | 2 @ 0.812 | 0 |
| int8 (bnb LLM.int8) | -- | -- | -- | -- | FAILED | -- |
| int4 nf4 | 526 MiB | 886 MiB | 1152 MiB | 459 ms | 2 @ 0.812 | 0 |
| int4 fp4 | 526 MiB | 886 MiB | 1152 MiB | 459 ms | 2 @ 0.727 | 0 |

Findings, numbered:
1. int4-nf4 cuts weights 3.1x (1645 -> 526 MiB) and process VRAM ~2x (2348 -> 1152 MiB), with
   detection unchanged from bf16 (chair 0.812, adversarial elephant 0). nf4 is the pick.
2. int4-fp4 gives the same VRAM but slightly lower confidence (0.727). Prefer nf4.
3. int8 via bitsandbytes FAILS on this stack: a bnb 0.50.2 + torch 2.11 bug in the LLM.int8
   outlier path (a `.view()` stride error). Not our code; and int4 compresses more anyway.
4. bitsandbytes quantization cuts VRAM but ADDS latency (333 -> 459 ms, +38%): its 4-bit path
   dequantizes on the fly. bnb is a VRAM tool, not a speed tool.
5. For LATENCY on this Blackwell GPU (sm_120, fp8/fp4-capable in hardware), the path is TensorRT
   INT8/FP8, not bitsandbytes. That is the embedl port's target and a separate, heavier lane.
6. Q4_K_M / GGUF does NOT apply here. GGUF is llama.cpp's format for LLMs. SAM3 is a vision
   segmentation model with no llama.cpp support, so there is no GGUF/Q4_K_M path for it.

### Precise benchmark (GPU clocks pinned 3090 MHz, N=50, no background load)

| config | weights | peak | process | cold | p50 | p95 | max | std |
|---|---|---|---|---|---|---|---|---|
| bf16 | 1645 MiB | 2006 MiB | 2350 MiB | 788 ms | 345.3 ms | 353.6 | 370.8 | 6.8 |
| int4-nf4 | 526 MiB | 886 MiB | 1200 MiB | 777 ms | 366.4 ms | 372.8 | 380.5 | 4.5 |

CORRECTION: the earlier "+38% latency" for nf4 came from noisy 10-iteration runs and a run
polluted by a background pip install. Pinned and clean, int4-nf4 is only +21 ms (+6%) over bf16
at p50 (366.4 vs 345.3), and more stable (std 4.5 vs 6.8). nf4 halves process VRAM (2350 ->
1200 MiB) with detection unchanged. It is the recommended config: near-identical latency, half
the VRAM.

Budget with int4-nf4: Qwen3-VL 3.8 + SAM3-nf4 1.2 + ASR 0.1 = 5.1 GiB -- LESS than the current
OmDet+SAM2.1 topology (5.5 GiB), while adding open-vocab breadth and tracking.

### TensorRT (embedl QDQ INT8, built and benchmarked)

embedl access granted, so the ready-made QDQ ONNX was built into a TRT 11.2 strongly-typed engine
(the QDQ nodes carry the INT8/FP16 precision; no builder flag needed). Engine built in 94 s.
Inputs: image (1,3,924,924) + tokenized_text (1,32). Raw: results/2026-09-03-trt.json.

| path | precision | res | p50 | VRAM | note |
|---|---|---|---|---|---|
| transformers | bf16 | 1008 | 345.3 ms | 2350 MiB | incl. postproc |
| transformers | int4-nf4 | 1008 | 366.4 ms | 1200 MiB | incl. postproc |
| TensorRT | INT8/FP16 | 924 | 262.5 ms (min 228) | 4218 MiB* | engine-only |

*The 4218 MiB is a HARNESS ARTIFACT, not INT8's footprint. Causes: a 5 GiB TRT workspace pool
set in the build config, the engine built in the SAME process (builder + 3.3 GB ONNX still
resident), and the torch CUDA context. INT8 engine weights for 0.9B params are ~0.9 GB; INT4 is
~0.45 GB, so INT8 is ~2x INT4 at the weight level -- NOT 3.5x. This row is NOT comparable to the
transformers rows: different runtime, different measurement, different resolution (924 vs 1008),
engine-only vs incl-postproc. A true apples-to-apples VRAM comparison is PENDING and needs:
build-then-serialize, load in a fresh process, report engine.device_memory_size + weight bytes,
torch context measured and subtracted, and a matched resolution and scope for every config.

Findings:
1. TensorRT INT8 is the fastest path: 262 ms p50, ~24% under bf16. Hardware INT8/FP16 kernels
   deliver the speed win that bitsandbytes cannot (bnb cuts VRAM, not latency).
2. Not perfectly apples-to-apples: embedl runs at 924 res; the TRT number is engine-only while the
   transformers numbers include Python post-processing. Both lean slightly toward TRT.
3. For minimal VRAM: int4-nf4 (1200 MiB). For minimal latency: TensorRT INT8 (262 ms). For
   simplest deploy: transformers bf16.

## Cost verdict (measured, overturns the FP32 estimate)

SAM3 does detection + masks + tracking in ONE model, so it replaces OmDet (0.9 GiB) AND
SAM 2.1 (0.7 GiB) = 1.6 GiB, not SAM 2.1 alone.

| topology | GPU budget use (of 8 GiB) |
|---|---|
| current: Qwen3-VL 3.8 + OmDet 0.9 + SAM2.1 0.7 + ASR 0.1 | 5.5 GiB |
| SAM3 unified: Qwen3-VL 3.8 + SAM3 2.3 + ASR 0.1 | 6.2 GiB |

SAM3 FITS the 8 GiB budget with ~1.8 GiB headroom. It costs ~0.7 GiB more than the two models
it replaces, and adds open-vocab detection breadth and video tracking. The earlier ">3 GB, does
not fit" was FP32 ONNX and wrong for the bf16 deployment dtype.

## Open decisions

1. Frames. Desk lane self-served, drone lane OPEN for the owner. 117 raw webcam frames were
   recorded off-git at /root/models/vision/sam3-desk-frames (never committed; room footage, same
   privacy rule as ASR logs). Honest limitation: the webcam is fixed and the scene is static, so
   the frames differ by only 3.2-3.6 on a 0-255 scale -- sensor noise, effectively ONE scene.
   More static frames add nothing. A meaningful desk lane needs scene changes a human introduces
   (move objects, move the camera, other rooms). The aerial out-of-distribution lane -- the one
   the brief centers on because curated frames crowned LLMDet -- still needs the owner to supply
   recorded drone footage.
2. Model source (REVISED 2026-09-03). transformers 5.15.1 has NATIVE SAM3 support: Sam3Model,
   Sam3Processor, Sam3VideoModel, Sam3TrackerModel, and a smaller sam3_lite_text. The official
   facebook/sam3 is a transformers checkpoint (model.safetensors, library_name: transformers),
   gated. Running it natively on torch/CUDA (works here) is the clean path: no ONNX, no TensorRT,
   no opset trap. Recommendation, OPEN: owner downloads facebook/sam3; then measure bf16 native
   VRAM + latency + mask quality + open-vocab detection + tracking. embedl (needs TensorRT 10.x)
   and the raw ONNX ports are deprioritized. facebook/sam3.1 is newer but library_name: checkpoint
   (no transformers, needs the SAM3 GitHub repo) -- a later step only if sam3 proves worth it.
3. GPU-ONNX. Blocker recorded above and now MOOT for the measurement: the transformers-native
   path avoids ONNX entirely. Lower-opset ports exist (eyepop-ai/sam3-onnx-models-opset-19/14) if
   an ONNX path is ever needed again.

## Method (planned)

No labeled ground truth exists. The remaining measurement will report, honestly labeled: (a)
hygiene pass rate through the engine's mask-hygiene rules on the same frames and OmDet boxes,
Wilson 95% + exact McNemar on the SAM2.1/SAM3 pair; (b) IoU agreement between the two models;
(c) a side-by-side overlay dump for owner review; (d) latency percentiles (p25/p50/p75/p95/max)
per device; (e) VRAM measured, not quoted. Text-prompt mode is tested on the same phrases the
live system uses, on OOD frames, WITH adversarial absent-phrase negatives.

## Files

| path | role |
|---|---|
| `setup.sh` | reproducible deps: extra pip packages + the pinned samexporter clone |
| `samexporter/` | MIT reference SAM3 ONNX runtime (gitignored; recreated by setup.sh) |
| `results/` | date-stamped raw per-case JSON |
| `overlays/` | side-by-side mask overlays for human review (gitignored) |
