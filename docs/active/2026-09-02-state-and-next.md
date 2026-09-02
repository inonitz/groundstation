# State and next — rewritten clean 2026-09-02 night (supersedes all earlier inserts)

## The component: the RECOGNIZER

Pipeline: stage 0 emergency (production regex) -> bypass -> Hebrew rewrites -> DictaLM
translate -> output guards -> English rewrites. Output: mission JSON | command English |
perception English | rejection. Code: tools/bench/hebrew-command-bench/recognizer.py
(the component, no model deps) + prompts.py. Diagram + scorecard: that directory's README.

System chain: ASR => Recognizer => VLM/LLM => REST API (MSDK server).

## Measured state (all 370 sentences, complete pipeline)

emergency 6/6 | std-190 98% | verbose 85% | perception 58% (DictaLM) | military 55% |
ALL 307/369 (83%). Command core is at the planner ceiling. One stage-0 false positive
("עצור שם לעשר שניות" emergency-stops; keep-greedy recommended, ruling pending).

## Rulings in force (2026-09-02)

1. Integration approved; until tonight nothing was integrated by rule.
2. Revised planner prompt adopted. Split not adopted; TranslateGemma deferred to future E2E ASR.
3. Emergency filter = stage 0 inside the Recognizer.
4. Routing is the Recognizer's decision (classifier = integration build item).
5. Unresolved number guard = reject and read back what was recognized.
6. TTS inside the Recognizer: TODO.

## Rulings added 2026-09-02 (late night)
- Stage-0 stays greedy: "stop for N seconds" remains expressible via חכה/המתן, so only the
  עצור phrasing is sacrificed. עצור always stops.
- Direct-Hebrew parked WITH REASON: the VLM must be resident for flight anyway, so removing
  Qwen from the command path saves nothing today.
- Routing stage BUILT (recognizer.py route()): deterministic, movement verb wins over a
  perception clause; measured offline 100/100 perception, 240/243 commands (the 3 are
  see-questions correctly sent to the VLM; dual-intent executes the motion).
- Rejection delivery: text now, English TTS optional now, Hebrew TTS later.
- Trace recorder = the owner's database request; JSONL per utterance unless SQLite preferred.
- serving-bench renamed where-models-run. ASR work DEFERRED until Recognizer alpha.

## Perception engine extracted (2026-09-02, night)
Same treatment as the Recognizer: projects/integration_harden/perception/ = engine.py (pure
logic, injected models, self-test), detectors.py (OmDet + Eyes, moved verbatim), vlm_client.py
(vlm.py + testable parse_reply). scene_omdet.py stays the glue and now wires the engine;
highlight_seg.py / eyes.py / vlm.py deleted (code moved, git history keeps them). open_capture
moved to camera_stream.py. Tests 26/26 across router + recognizer + perception; scene_omdet
imports cleanly. NOT yet run against live video -- the desk-loop smoke needs a camera/RTSP and
stays for the next live session.

## Integration DONE (2026-09-02, late)
recognizer/ module landed in integration_harden: recognizer.py + pipeline.py (drop-in for the
Router's on_complex; router.py untouched) + trace.py (the per-utterance JSONL recorder,
traces/ gitignored) + run_dicta_server.sh (CPU) + README with the sync rule. Tests 20/20
(13 router + 7 new wiring, all model calls faked). Going live = the documented one-liner at
assembly: Router(wire, on_complex=Pipeline(wire, vlm_query, say).handle) with the dicta
server running. Remaining from the old list: reject via English TTS (say= currently text),
audio path into traces (with ASR).

## Integration build items (original list, for reference)

1. Recognizer module into integration_harden behind the router: recognizer.py + prompts +
   the two llama-server configs (DictaLM on CPU, Qwen3-VL on GPU) + tests.
3. Reject-message delivery (TTS is backlog D; interim behavior to decide).
4. Trace recorder: per-utterance JSONL {id, timestamp, audio path, ASR text, stage io, flags,
   final JSON, latencies}. Audio and transcripts never enter git.
5. General cleanup of integration_harden alongside.

## Open beyond integration

- ASR round: quant ladder ready (q4_0/q5_1/q8_0), wav2vec2 challenger downloaded, recording
  spec ready (where-models-run/RECORDING-SPEC.md). Gates: faster-whisper + pyctcdecode/kenlm
  scripted installs, team recordings.
- Stage-0 greedy-vs-context ruling. Direct-Hebrew single-model variant (92.6% w/ bypass) as
  an alternative architecture. Chain-initial takeoff rewrite; planner "a second" delay trap.
- VRAM topology is measured and closed: GPU = Qwen3-VL + OmDet + SAM2.1 + ASR (5.5 GiB of 8);
  CPU = translators (where-models-run/README.md).
