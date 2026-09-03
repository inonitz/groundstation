# State and next — rewritten clean 2026-09-02 night (supersedes all earlier inserts)

## The component: the RECOGNIZER

Pipeline: stage 0 emergency (production regex) -> bypass -> Hebrew rewrites -> DictaLM
translate -> output guards -> English rewrites. Output: mission JSON | command English |
perception English | rejection. Code: projects/integration_harden/recognizer/recognizer.py (the component, no model deps; the bench imports it in place) + prompts.py. Diagram + scorecard: that directory's README.

System chain: ASR => Recognizer => VLM/LLM => REST API (MSDK server).

## Measured state (all 370 sentences, complete pipeline)

emergency 6/6 | std-190 98% | verbose 85% | perception 58% (DictaLM) | military 55% |
ALL 306/364 (84%); with emergency 312/370 (after the 2026-09-02 residue rules). Command core is at the planner ceiling. One stage-0 false positive
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

## Clustered (2026-09-02, later)
integration_harden top level -> control/ (commands, router, dji_wire), audio/ (ears, phone_ears,
voice; ASR stays external), video/ (camera_stream + doctor + watchdog; camera self-test added).
Glue stays top: scene_omdet, config, run scripts. Verified: 26/26, audit CLEAN, both self-tests,
scene_omdet import, webcam frames live, live_mock_smoke PASSED (aiohttp reinstalled via the
scripted installer; smoke's DEVNULL replaced with a log). README rewritten to the new layout.

## E2E Hebrew verified on the go-live wiring (2026-09-02, later)
Router(wire->mock, on_complex=Pipeline(dicta CPU :18091, Qwen3-VL :18090, vlm_query=real VLM
with live webcam frame).handle): 19 sentences from the bench sets, all four outcomes exercised.
Bypass missions POSTed at 0 ms; translated+planned missions 1.2-2.9 s; VLM queries 2.7-4.2 s
with correct presence-negative answers; OOD chat correctly refused (empty plan, no flight);
Hebrew emergency fired tier-4 via the imported EMERGENCY_RE. Both known residues reproduced
live: chain-initial takeoff planned as land (combo_tl) and DictaLM answering instead of
translating a see-question (question -> "I see a red car."). Trace JSONLs recorded in traces/.
ASR delegated-session brief written: docs/active/2026-09-02-asr-session-brief.md.

## Parallel workstreams (2026-09-02, late)
Three lanes: (1) this manager session on integration_harden; (2) ASR round, delegated to an
Opus 4.8 agent, brief = docs/active/2026-09-02-asr-session-brief.md (kicked off by the owner);
(3) SAM 3.x mask evaluation, brief = docs/active/2026-09-02-sam3-session-brief.md (facebook/
sam3.1 access GRANTED 2026-09-02; official quantized variants + community SAM 3 ONNX
ports both get measured). RULED (2026-09-02, late): the router-level emergency check STAYS. The regex lives once
(Recognizer); the router's one-line check is position, not duplication -- it alone runs
before the basic-verb matcher (measured: without it, "stop going forward" -> go_forward,
"stop the spin" -> spin, "kill/abort landing" -> land; in manual mode those stops are
dropped entirely). Recognizer stage 0 stays the net for COMPLEX text and router-less
consumers. Follow-up recommendation, OPEN, in ROADMAP: single command catalogue post-sprint.

## Residue rules measured (2026-09-02, latest)
Three sieve rules landed and re-measured on all 370: takeoff-verb-inline + takeoff-noun-inline
(chain-initial takeoff no longer becomes land/fly-forward; combo5 and all verbose chain openers
fixed) and stay-there-strip (planner's invented {"delay":1} gone; r_mis2 fixed). 301 -> 306/364;
std 184/185 (99%), verbose 50/53 (94%). Military -1 is a probe artifact (s_jump_point requires
the very words the strip removes; mission behaviorally correct) -- probe amendment is an OPEN
owner call. Discovered and documented: ±1-2 cross-run noise on model-dependent sets (identical
translations flipped english<->reject across dicta restarts); determinism holds within one
server session only. Scorecard updated in place; old numbers in results/HISTORY.md.
