# Project state and reorientation, 2026-09-09

Objective: a Hebrew voice interface to a drone. The operator speaks Hebrew. The system transcribes it,
decides what the operator wants, plans a bounded mission or a perception action, checks it against a
fixed safety layer, and sends it to the aircraft. Vision marks and counts objects on the video. The
phone answers back in Hebrew. Everything runs offline on one 8 GB laptop.

The judge meeting is cancelled (the earlier business meeting was deemed enough). We now work only to
meet the challenge-form requirements, so results can speak for themselves.

## 1. The two systems

integration_harden -- the proven multi-model chain and the fallback. whisper (Hebrew) transcribes ->
a Hy-MT2 model translates Hebrew to English -> a Qwen3-VL model plans the mission -> SAM3 does vision.
It is frozen as the safe demo path.

integration_harden2 -- the new single-model chain, where all recent work lives. One model, Gemma 4
E4B, does everything language: it classifies the request, plans the mission, names the target in
English, and answers questions in Hebrew. No separate translator. SAM3 is the eyes (marking and
counting). It flew on a real aircraft for the first time today.

Shared pieces (all vendor-blind): the speech node (whisper over ROS2, push-to-talk on F5), the video
ingest node, the drone REST wire (fly / takeoff / land / stop), the mock server for desk tests, and
the kill switch.

## 2. Challenge-form scorecard, with why we worked on each

Delivered:
- 4.2 local hardware -- runs on one laptop, 6.5 to 7.7 of 8.15 GiB used. Worked because the whole
  premise is an offline edge box, not a cloud service.
- 4.5 Hebrew support -- whisper Hebrew transcription at 8.4 % character error on 107 live clips.
  This was the central bet of the sprint: Hebrew end to end is the differentiator.
- 5.1.2 understand the operator's intent -- 415 of 466 on the test set; 0 cases where a code change
  turned a safe command dangerous. This is the core capability and the safety story.
- 5.1.4 minimal extra hardware -- a phone and one laptop.
- 5.1.5 execute the action -- proven on the mock all along, and on a real aircraft today (6 missions,
  HTTP 200). Marked partial only because there is no polished flight video yet.

In progress:
- 4.3 platform-agnostic -- the layers do not depend on the aircraft, but only DJI is demonstrated. An
  earlier prototype ran on a different flight stack.
- 4.4 respond within one second -- measured 0.3 to 1.6 s from end of speech to the REST call. Partly
  there.
- 5.1.3 visual input -- SAM3 marks and counts, but there are no human-labelled truth images, so the
  perception number (28 of 42 highlight asks) is not yet a credible accuracy figure.
- 5.2.2 chained commands -- multiple steps in ONE spoken sentence work; there is no memory across
  separate sentences.

Not met:
- 3.1 vision-conditioned action ("go out through the door") -- the headline gap. Vision does not yet
  drive flight. We can mark a door; we cannot fly through it. This is the single biggest missing
  capability and the natural next milestone.
- 2.3 autonomy in a changing environment.
- 5.2.1 military slang -- 0 of 21. The model was never trained or prompted on unit slang.
- 5.3.1 speaker identification -- not started.

Not measured:
- 4.1 and 5.1.1 noise, blast, low light -- no data collected. whisper's robustness to noise is
  untested, which is a real risk for a field system.

Why the priorities fell this way: the sprint was aimed at a credibility gate (prove a real Hebrew
voice loop with strong vision and a safety story), and real flight was deliberately deprioritised
after an earlier injury with a loose armed aircraft. So the effort went to the Hebrew dataset and
benchmark, the deterministic guard layer, SAM3 vision, and the one-model swap -- not to autonomy or
field-noise data.

## 3. What is measured (all at temperature 0, one model on the GPU at a time)

- whisper Hebrew: 8.4 % character error, 107 live clips.
- Test set: 488 hand-written Hebrew cases in a military register; each has the correct expected
  mission.
- harden2 single-model chain: 415 of 466 correct. The old harden chain: 410 of 466. The new one is
  as good and simpler.
- Gemma alone on commands: 318 of 328.
- Live end to end: 42 passed, 17 failed, 1 unsafe, of 62 spoken utterances.
- Highlight chain: 28 of 42 asks, no human truth labels.
- Safety: 0 cases of a safe command flipped to dangerous, at every guard.
- SAM3 alone as the presence gate: 82 of 89 against a two-model consensus.
- Gemma as a transcriber: rejected. 35.8 % character error against whisper's 8.4 %.

## 4. What was done today, 2026-09-09 (low level)

Perception (the big wins, all in harden2):
- Highlight recall fix. The live highlighter inherited a cap from the old OmDet+SAM2.1 pipeline: it
  drew at most 3 objects and the detector returned at most 8. SAM3 gives boxes and masks in one cached
  pass, so the cap was pointless but never lifted. Raised to 15 drawn and 24 detected. A 12-object
  simulation went from 3 drawn to 9-12. This was why "mark all the cars" showed only 3 of 12.
- Counting is now stable: deduplicate boxes contained in a stronger box, take the median of 3 frames,
  and drop specks under 0.1 % of the frame. Before, counting the same chairs gave 2, 5, 4, 6.
- Hebrew-to-English target lexicon under Gemma (about 120 nouns), used only when Gemma's English word
  matches none of a noun's aliases. Gemma had written "cabin" for drawers and "desks" for dressers.
- SAM3 synonyms (screen -> monitor, television, screen) and positional-word stripping ("top left
  window" -> window; SAM3 cannot use position words).
- Presence gate default flipped to SAM3 ("Gemma plans, SAM3 sees"), with SCENE_GATE=vlm|either|sam3.

Control and safety:
- First real flight of harden2: 6 missions reached the aircraft, HTTP 200, including a 180 turn and
  chained steps from one sentence.
- Kill switch (M key) verified on the mock: stop, refuse missions, re-arm. Its events now print to the
  session log.
- Planner gap found: "square" plans are phrasing-dependent. Fix is a few-shot example plus a test
  rerun, deferred.

Reliability fixes:
- run_mvd.sh direct real run aborted under set -u on an unset session-dir variable. Fixed; a direct
  run now records its own session.
- The phone hotspot IP changed between sessions; the old hardcoded IP made every command time out
  mid-flight. Now derived from the default route.
- A laptop restart wiped bitsandbytes and accelerate; SAM3 would not load. Restored by the scripted
  installer. Rule: run it after any restart, then preflight.

Documents:
- Team summary (docs/private, gitignored): all 12 competitors validated against 16-39 sources each,
  rewritten as plain-Hebrew prose, no jargon. Key finding: Primordial Labs (Anura) is the one direct
  competitor; English only, US only. Several original claims were wrong (Elbit's Hebrew voice is
  actually ThirdEye's; Kronos likely confused with Kratos).

61 automated tests pass in harden2.

## 5. What is left, ranked for the reorientation

1. Verify today's perception fixes live on the webcam (caps, SAM3 gate, lexicon). Cheap, do first, no
   drone needed.
2. Vision-conditioned action, 3.1. Mark a target, then approach it or pass an opening. This is the
   headline missing capability and the next real milestone.
3. Negation rule in code. The one live unsafe event was a double negation. Close it with a rule plus
   adversarial tests.
4. Noise and low light, 4.1 and 5.1.1. Start with whisper on noisy clips; it is the field risk.
5. Military slang, 5.2.1, and context across sentences, 5.2.2.
6. Human labels for the vision asks, so 5.1.3 has a real accuracy number.
7. Fine-tune Gemma on the corpus once it is a few thousand cases. This turns the novelty answer from
   "no" to "yes".
8. Speaker identification, 5.3.1. Last.

Housekeeping: consolidate the repo docs and add the data folder; commit both trees (the human runs git).

## 6. Where the detail lives

- Session handoff: docs/active/2026-09-08-session-handoff.md (sections 17-19 cover the last day).
- Dated decisions and measurements: docs/NOTES.md (the 2026-09-09 entries).
- Numbers and research tables: docs/active/assets/slide-numbers.md, slides-research.md.
- Diagrams: docs/active/assets/harden2-*.{png,svg,drawio}.
- Competitor validation and the team summary: docs/private/ (gitignored).
- The morning test procedure: tools/desk-test/live-run-2026-09-09.md, checklist-2026-09-09.md.

## 7. Replan 2026-09-09 (after owner review) — the live plan

Owner approvals this round: negation guard+test approved (B); operator-mission context is its own project
(C); the tracker is back on, not Plane (D); noise becomes a real whisper-Hebrew e2e benchmark, no denoiser
research. Nothing dropped.

Two tracks run at once.

TRACK 1 — organization (owner-driven, in parallel, do soon; it is how we manage all the paths below):
- Stand up a self-hosted Jira alternative to hold work topics, their tasks, and research subtopics.
  Recommendation: OpenProject (GPL, free, no seat cost, strong project/subproject/work-package hierarchy
  + wiki, Docker Compose, ~4 GB). Alternative if you want a modern Linear-like feel and have the RAM:
  Huly (needs 8-16 GB). Host it on the workstation, NOT the 8 GB demo laptop. Not Plane (owner call).
- Seed it with the topics: Hebrew ASR noise/low-light, this-arch vs llm_to_action + merge, VLM-in-the-loop
  deterministic actions / behaviour trees, whole-project e2e benchmark, per-system human-written tests,
  branch model + CI, and the technical projects below.

TRACK 2 — technical, in order:
1. Verify today's perception fixes live on the webcam: draw-all caps, SAM3 gate, lexicon, count median.
   No drone. First.
2. Commit integration_harden2 first (it is UNTRACKED = at risk), then freeze integration_harden and verify
   harden2 routing on the 488 set and live. Fold the cleanup commits in (see the cleanup draft).
3. Negation guard + test: a deterministic action-negation rule BEFORE the model, with positives,
   adversarial negatives, and zero false fires. The demo showed every negation currently reaches Gemma.
4. Whisper-Hebrew noise e2e benchmark (reuse the mixer + gunfire beds; proper SNR sweep + metrics), then
   the low-light image benchmark for SAM3 (labeled image sets scored like the audio clips).
5. Big projects, scoped as tracker projects, not rushed: 3.1 vision-conditioned action (mark -> approach /
   through), operator-mission context (model the operator's mission/phase, not just dialogue memory),
   military slang.

## 8. Session artifact index + resume pointer (2026-09-11)
RESUME HERE: docs/active/2026-09-10-guard-and-config-workplan.md, section "STATUS at stop" -> run A5
(re-run unified_bench, compare to the 410/487 baseline) FIRST. Everything below is in files, not chat:
- Track 2 plan: docs/active/2026-09-10-track2-execution-draft.md (rev5). harden = DEAD intermediate; the
  fallback is projects/integration/; outdoor-validate harden2 -> freeze; cleanup must be behaviour-preserving.
- Track 1 (project-manager self-host, separate subagent): docs/active/2026-09-10-track1-tracker-handoff.md
  (kickoff prompt in section 14; OpenProject rec; host = the owner's old server, NOT the demo laptop).
- Living workplan (negation guard + config merge, with the assurance-math appendix):
  docs/active/2026-09-10-guard-and-config-workplan.md.
- Config draft (NOT wired; golden-master merge = workstream B): projects/integration_harden2/config_constants.py
  + config_defaults.py.
- Run-arguments reference: docs/active/2026-09-10-harden2-run-arguments.md (SCENE_TTS is a NO-OP; use MVD_TTS=0).
- Repo cleanup draft: docs/active/2026-09-09-repo-cleanup-draft.md.  Challenge form: docs/active/challenge-form.md.
- Team summary (PRIVATE/gitignored): docs/private/team-summary-2026-09-09.{md,pdf}, competitors-validation.md.
- Dated decision/measurement log: docs/NOTES.md (2026-09-09..11).
Guard code in the tree (uncommitted, offline-tested GREEN): recognizer/recognizer.py (negation_only + stage),
recognizer/pipeline.py (reject branch), tools/bench/hebrew-command-bench/unified_bench.py (reject scoring),
test/test_negation_guard.py.
