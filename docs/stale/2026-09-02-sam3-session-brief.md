# SAM 3.x session brief — for the delegated agent (written 2026-09-02, owner-commissioned)

You are a measurement agent on the groundstation repo, tasked with ONE thing: evaluate
SAM 3 / SAM 3.1 as the replacement for SAM 2.1 in the perception mask path.
Read before anything, in this order:
1. docs/active/2026-09-02-manager-handoff.md — protocol, rails, measurement method.
2. docs/active/2026-09-02-state-and-next.md — current system state and rulings in force.
3. projects/integration_harden/perception/README.md — the component you would feed.
4. tools/bench/hebrew-command-bench/README.md — a FINISHED scorecard: mirror its structure.
5. docs/writing-style.md (result-doc register), docs/code-guidelines.md (commit style).
CLAUDE.md binds you fully: RTK wrappers, NO git writes (suggest commit blocks), no drone
commands ever, decisions into repo docs the same turn.

## Objective

Measure whether a quantized SAM 3.x gives better masks than SAM 2.1 at equal or lower cost
(VRAM, latency), and whether its text-promptable open-vocabulary mode could additionally
cover OmDet's detector role. Output: a measured scorecard and a recommendation — the OWNER
decides. Recommendations are not decisions. NO integration: the swap point is the injected
mask_for_box callable in perception/engine.py; you never touch engine.py or scene_omdet.py.

## Verified starting points (checked 2026-09-02; re-verify, links rot)

- facebook/sam3.1 on Hugging Face: gated — ACCESS GRANTED to the owner 2026-09-02. The
  official checkpoints and the 7 linked quantized variants are downloadable; measure them
  alongside the community SAM 3 ONNX ports. Text or
  visual prompts (points/boxes/masks), images + video, exhaustive open-vocab segmentation;
  ~7x faster multi-object tracking claimed vs SAM 3 (their number, unverified by us).
  No transformers integration — checkpoints + GitHub only. 7 quantized variants are linked
  from the card.
- Ungated free ONNX ports are SAM 3 (not 3.1): vietanhdev/segment-anything-3-onnx-models
  (onnxruntime, text-promptable) and embedl/sam3 (INT8/FP16 quantized).
- GATE: verify the LICENSE of any community port before downloading weights; a port of a
  gated model may not be redistributable for our use. Record the license in the scorecard.

## System context

Live mask path: perception/detectors.py Eyes = background YOLO26-seg + lazy SAM 2.1;
OmDet-Turbo grounds open-vocab boxes; engine.py applies the relative-confidence gate, mask
hygiene, and the VLM presence gate. Measured VRAM census (8 GiB GPU): Qwen3-VL 3.8 + OmDet
0.9 + SAM2.1 0.7 + ASR 0.1 = 5.5 GiB. Your budget: SAM slot <= 0.7 GiB on GPU, or CPU via
onnxruntime. One model resident on the GPU at a time while measuring.

## Gates (before any measurement)

1. Scripted install: onnxruntime (+ anything else) goes into tools/devenv/Dockerfile
   (ruling 2026-09-02); install-runtime-deps.sh is the stopgap for running containers.
2. Weights live under the MOUNTED /root/models/vision — non-mounted paths are wiped on
   rebuild (the translate-models loss). The install script must refuse non-mounted targets.
3. Duration estimate stated BEFORE every run.

## Method

- No labeled ground truth exists. Report, honestly labeled: (a) hygiene pass rate — the same
  frames + OmDet boxes through SAM2.1 and SAM3.x, masks judged by the engine's existing mask
  hygiene rules; Wilson 95%, exact McNemar on the pair. (b) IoU agreement between the two
  models. (c) a side-by-side overlay dump for human review — the owner reviews, you do not
  declare a winner from eyeballs. (d) latency percentiles (p25/p50/p75/p95/max) per device.
  (e) VRAM measured, not quoted.
- Frames: recorded desk and drone footage, NOT curated favorites. Remember the LLMDet lesson
  (docs + memory): curated-set recall crowned a model that hallucinated on OOD footage.
- Text-prompt mode (the OmDet-replacement question): same phrases the live system uses, on
  OOD frames, WITH adversarial absent-phrase negatives — grounding an absent phrase onto a
  salient object is the exact failure the presence gate exists for. Zero-shot claims from
  model cards are unverified until you measure them.
- Full result tables in chat, never abbreviated. Raw per-case JSON to results/ files.

## Deliverables

1. New bench home: tools/bench/sam3-mask-bench/ — README scorecard (Objective/Setup/Results/
   Analysis/Conclusions), results/ raw data, overlay dump dir (gitignored if heavy).
2. docs/active/2026-09-02-state-and-next.md updated with the outcome + open decisions.
3. Suggested commit block(s); the human runs all git.

## Owner protocol (audited)

Answer every numbered point by number; never fuse or skip. Label unmeasured numbers
"unverified". Lead with disagreement. Background output to files; short summaries + full
tables in chat.
