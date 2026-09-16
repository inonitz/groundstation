# SAM3.1 quantization session brief — for the delegated agent (written 2026-09-04, owner-commissioned)

You are a measurement + engineering agent with ONE task: make a QUANTIZED SAM3.1 run in production
for our on-demand image "highlight" path, on the 8 GiB RTX 5070. The owner RULED SAM3.1 is the
target -- it is better than SAM3 -- so this is a "find the method" task, not a "decide whether"
task. HOW is your recommendation; THAT SAM3.1 is the goal is settled.

Read before anything, in order:
1. docs/active/2026-09-03-manager-handoff.md -- protocol, rails, method, the whole board.
2. tools/bench/sam3-mask-bench/INTEGRATION-HANDOFF.md -- SAM3 adoption + the exact SAM3.1 block.
3. tools/bench/sam3-mask-bench/RESULTS.md + results/sam3-quantization.md -- the measured evidence.
4. projects/integration_harden/perception2/README.md -- the SAM3 module = your integration shape.
5. memory sam3-quantization-insights (session 44's notes).
CLAUDE.md binds you: rtk wrappers, NO git writes (suggest commit blocks), no drone commands, GPU
coordination with the manager, script every install, measure don't assume, decisions into docs
the same turn.

## Why SAM3.1, and why it was parked (measured by session 44)

SAM3.1 is a SUPERSET of SAM3: its checkpoint carries a full image detector that routes to the
image-grounding forward, plus Object Multiplex for VIDEO multi-object tracking. On single images
SAM3.1 detection equals SAM3 (10 @0.957 vs 10 @0.96) today; the owner wants the 3.1 line for its
trajectory and video capability.

What blocked it on the 8 GiB GPU (session 44, measured):
- Run via the repo build_sam3_multiplex_video_predictor, the tracking PEAK is ~7000 MiB --
  activation/tracking-state memory, NOT weights. Weight quant (int8/HQQ int4 -> 1418 MiB weights)
  does NOT lower that peak.
- True int4 COMPUTE (gemlite) is blocked by a mixed-precision fp32 detector forward + a direct
  .weight transpose in the model.
- AOTInductor (~10 s cold path) is blocked on an unbacked symint: the vision grid H*W carried as a
  runtime tensor (spatial_shapes in modeling_sam3.py ~1795). fp8 AOT compile OOMs the 8 GB card.

## Angles to try (yours to sequence; the owner named several)

1. IMAGE-DETECTOR-ONLY path (try FIRST, cheapest unblock): our production use is on-demand single
   frames -- we do NOT need the multiplex VIDEO machinery that causes the ~7 GiB peak. Invoke ONLY
   SAM3.1's image-grounding forward, without the video predictor. If that activation peak fits the
   ~2 GiB headroom, the "shelved" verdict flips. Measure this before anything heavier.
2. gemlite int4-compute: unblock the mixed-precision forward + the .weight transpose.
3. Custom llama.cpp fork: the owner notes SAM3/SAM3.1 can run through a llama.cpp fork; evaluate
   whether a GGUF/quantized path there gives a lower peak than the transformers/torch path.
4. Off-box AOT compile: build the .so on a bigger machine, ship it; fix the spatial_shapes
   unbacked symint (specialize H*W to ints).
5. If none fit 8 GiB: quantify EXACTLY what VRAM SAM3.1-image needs, so the owner can decide on
   hardware. A clean "does not fit, needs X GiB" is a valid deliverable.

## Method (non-negotiable)

- The production shape is perception2/Sam3Backend: one text-prompted forward -> boxes+masks+scores,
  on-demand (~0.4 s/call acceptable, never per-frame). Your SAM3.1 path must fit that interface.
- Measure standalone VRAM (torch peak, CUDA-context floor excluded) AND projected into the live
  topology (Qwen3-VL 3.8 + ASR 0.1 + your SAM3.1). One model on the GPU at a time while measuring.
- Latency percentiles as columns; a duration estimate before every run; full tables in chat.
- Compare SAM3.1-image detection HEAD-TO-HEAD with the adopted SAM3-nf4 on the same frames. The
  bar: "better than SAM3-nf4 at a VRAM that fits", else SAM3-nf4 stays.
- Frames: recorded desk/drone footage, never a curated set (the LLMDet lesson).

## Resources

- Model: /root/models/vision/sam3.1-official (mounted, survives rebuild).
- Repo: facebookresearch/sam3 -- RE-CLONE (session 44's clone + quant scripts were ephemeral
  scratch, lost). Script the clone + installs into a setup script in your bench home; bake
  production deps into tools/devenv/Dockerfile.
- Bench home: add tools/bench/sam3-mask-bench/sam31/ -- do NOT edit session 44's files there.
- Integration target: projects/integration_harden/perception2/ (do NOT wire until the owner
  declares SAM3.1 closed; perception2 currently uses SAM3-nf4).

## Deliverables

1. A verdict: does a quantized SAM3.1-image path fit the 8 GiB budget and beat SAM3-nf4? With the
   method that got there, or the exact blocker if not.
2. Scorecard + raw data in tools/bench/sam3-mask-bench/sam31/.
3. docs/active update + a suggested commit block. GPU coordinated via the manager. Human runs git.

## Owner protocol (audited)

Answer every numbered point by number. Label unmeasured numbers "unverified". Lead with
disagreement. Background output to files; short summaries + full tables in chat.
