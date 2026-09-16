# harden2 live-test handoff (2026-09-12)

## THE COMPASS (read before anything -- a prior session drifted into prototype-local fixes and lost this)
- GLOBAL OBJECTIVE: a voice-commanded autonomous DJI drone (Israeli MOD contest; contest/Demo Day PASSED).
  Principle: "the VLM plans, deterministic math executes." Flagship = a complex command in an UNPLANNED
  environment ("exit through the door"). Scored: <1s command->action, local/no-cloud, noise + low-light
  robustness, intent + visual-parse accuracy, minimal hardware, Re-ID THROUGH OCCLUSION, command sequences.
- THE REAL SYSTEM is the C++ projects/llm_to_action/ (FMU: VLM planner + 20Hz loop; DJI Mini via the
  Exoskeletons Android app, MSDK v5). harden2 (this Python tree) is the PERCEPTION/COMMAND PROTOTYPE to
  FOLD IN via branch feature-total-integration. It is the current MVD, NOT the destination.
- BIGGEST UNSOLVED SCORED GAP: persistent Re-ID tracking through occlusion (OSNet embeddings + ANN index,
  NOT colour histograms). follow.py is a toy. UNTOUCHED. This, not more recognizer polish, moves the objective.
- FIELD REALITY (owner, first-class): optimize ENERGY per flight, not latency. The 5070-Mobile is the dev rig;
  the backpack deployment target (embedded, 15-60 W) is unmeasured. Run power_profile.py UNPLUGGED for Wh/flight.

## CURRENT PRIMARY OBJECTIVE (owner ruling 2026-09-12) -- the order of operations
Original intent was: live-test outside -> cleanup -> retest outside -> freeze -> roadmap. The owner OPTED to
reorder: do the cleanup & restructure FIRST. So the sequence we are executing NOW, in order:
  1. Finish the cleanup & restructure (the translated-path retirement commit, bench.py legacy strip, stale README,
     the gitignore->logs/* restructure).
  2. Make sure harden2 works WELL IN THE FIELD, bug-free (the outdoor live test; webcam first, then drone).
  3. THERMO-NUCLEAR code review on harden2 AND the rest of the repo. USER-invoked only:
     /thermo-nuclear-code-quality-review. Pin --model and HIDE the recognizer-bench skill from both skill dirs
     before any measured agent run (memory isolate-confounds-and-pin-model; headless agents discover skills regardless).
  4. Freeze harden2 (declare it closed / merge-ready -- the most up-to-date work).
  5. THEN the originally-planned objectives: persistent Re-ID through occlusion (the big scored gap) + the C++
     feature-total-integration fusion + the roadmap. This is the destination; steps 1-4 free us to get there.

## REQUIRED READING (do NOT rely on this file alone; it is the tactical tail, not the whole picture)
- Compass memory: ~/.claude/.../memory/global-objective-voice-drone.md + current-demo-decision.md.
- Prior full handoff: docs/active/2026-09-12-session-handoff.md (its S10 standing rules, S12 audit + cross-refs).
- Commit plan + buckets: docs/active/2026-09-12-order-to-commit.md, 2026-09-12-commit-manifest.md (Bucket A this
  session / B pre-existing pile incl. dead integration_harden, devenv, docs / C unknown-origin files to check).
- Cross-refs (mostly post-commit): docs/research/asr-noise-robustness.md (whisper/Hebrew SNR sweep + low-light
  SAM3 bench still TODO), docs/active/challenge-form.md, 2026-09-10-track1-tracker-handoff.md (OpenProject,
  parallel), 2026-09-09-repo-cleanup-draft.md, docs/private/ (GITIGNORED judge/team material; never name judges).
- Nuclear review: USER-invoked only -- /thermo-nuclear-code-quality-review scoped to projects/integration_harden2,
  "audit the files not the diff". The assistant cannot launch it.
- phone-ip-is-wifi-gateway memory: the phone IP = the WiFi default gateway, CHANGES per hotspot; derive from the
  default route, never hardcode. Needed for any `run.sh up dji real` run (HUMAN-only).

For the next session / live-test subagent. This is the single source of truth for what the system is,
how to run it, what is done, what is uncommitted, and what to do next. Read it fully before acting.

## 0. HARD RULES (never violate)
- NEVER send arm/takeoff/land/stick/velocity/motor to a REAL drone. PREPARE the command, the HUMAN runs it.
  The assistant runs control tools ONLY against the mock at 127.0.0.1. A real phone IP = stop, hand over.
- The HUMAN owns ALL git. No add/commit/push/rm/mv/reset/clean. Suggest commands; the human runs them.
- projects/integration/ is FROZEN (the proven English fallback). integration_harden is DEAD. harden2 is THE system.
- ONE model on the GPU at a time. NEVER pre-start llama-server by hand. run.sh and the bench each bring up
  their OWN single server; starting one yourself makes TWO Gemmas (~7 GiB on an 8 GiB card) -- the 2026-09-12 mistake.
- Measurement: temp 0, state a duration estimate before any GPU run, re-run the full bench after touching
  measured code (recognizer/pipeline) and compare per-set counts. Read tool is disabled -> use Bash. No SendUserFile
  -> give the owner a workspace path.

## 1. What the system IS
- harden2 = projects/integration_harden2/. One Gemma-4-E4B (Q4_K_XL + BF16 mmproj, thinking OFF, temp 0) does
  routing + planning + Hebrew answers in ONE call. SAM3-nf4 is the open-vocab eyes (boxes+masks, 1008x1008).
  whisper-ivrit (C++ node) is the ASR. YOLO26 background detector kept, OFF by default.
- Entry point: mvd.py (the live scene app; renamed from scene_omdet.py this session). It imports:
  overlay.py (the chat-pane renderer, 3 fonts), session_log.py (crash-safe recorder).
- The recognizer (the pre-Gemma safety sieve) lives in recognizer/. Live entry = recognize_direct(he)
  [recognizer.py ~L760], called from pipeline.handle_direct [pipeline.py:80]. Order on the transcript:
  None-guard -> stage 0 emergency filter (EMERGENCY_RE, acts immediately / wire.halt) -> stage 1 bypass
  (exact-match -> deterministic mission, no model) -> negation guard (negation_only, subtract rule, pure
  negation -> reject) -> stage 2 apply_he (Hebrew rewrites) -> ("direct", he2) -> the single Gemma call (_plan2).
  Rejects: negation guard (pre-Gemma), Gemma kind="reject", and the post-Gemma number guard (numbers_vs_mission).

## 2. How to run (THE one command)
```
WEBCAM_DEV=2 MVD_TTS=0 bash /root/groundstation/projects/integration_harden2/run.sh up webcam mock
```
- run.sh is self-contained: subcommands up | down | status | preflight. It runs preflight, starts the mock on
  127.0.0.1:8079, makes the session dir (asr_clips/ + perception/ + trace.jsonl), and brings up ONE tmux session
  `mvd` (vlm=Gemma server, keys=F5 hook, asr=whisper node, app=mvd.py, mock=command log).
- `up webcam mock` = webcam + mock control. `up dji real` = drone + REAL control -- HUMAN ONLY, run.sh prompts ARMED.
- Stop: `bash .../run.sh down`. Status: `bash .../run.sh status`. Checks only: `bash .../run.sh preflight webcam`.
- WEBCAM_DEV=2 is the C920; 0 is the laptop lid cam. MVD_TTS=0 silences the phone TTS for desk tests.

## 3. What is COMMITTED (13 commits pushed, branch feature-hardening-mvd)
- The harden2 baseline: config merge, recognizer + negation guard, SAM3 perception, mvd.py app + overlay +
  session_log + run.sh, 66 tests, the tools (replayer, power_profiler), and the consolidated bench numbers.
- Commit scope = CODE + consolidated benchmark NUMBERS only. Gitignored (on disk, NOT committed): docs/active/*,
  docs/active/assets/ (diagrams/slides/demo images), raw bench dumps, ui-mockups renders, build/venv/sessions/recordings.

## 4. What is UNCOMMITTED right now (on disk, NOT in git) -- decide commit vs revert
- The LEGACY TRANSLATED PATH RETIREMENT (done on disk this session, verified, 66 tests green, control bench 410/487):
  - recognizer/prompts.py  : removed WIRE_GRAMMAR, all TRANSLATE_*, LINE_GRAMMAR, PURPOSE_*, HE_SIGN_ADDENDUM,
                             PLANNER_SHOTS_D_HE, TGEMMA_*; write_prompts_md trimmed; PROMPTS.md regenerated.
  - recognizer/recognizer.py : removed recognize(he, translate) (the old translated entry). recognize_direct kept.
  - recognizer/__init__.py : dropped the `recognize` export.
  - tools/bench/hebrew-command-bench/bench.py : removed its dead prompt import.
  - results/HISTORY.md, RESULTS.md : retirement + ablation lines; RESULTS lists unified_bench as the harness.
  - .claude/skills/recognizer-bench/SKILL.md : retargeted from the dead integration_harden to harden2 + unified_bench.
- CRITICAL CORRECTION: do NOT `git rm bench.py`. It holds the SHARED infra unified_bench.py imports
  (to_scorer_schema + the re-exposed llama server config). Earlier this session I wrongly proposed git rm'ing it.
- LOOSE END: bench.py's legacy functions (make_translator, plan, main) still reference the removed prompt names ->
  NameError if CALLED (they are not called by unified_bench, so import is fine). They should be stripped for
  cleanliness (the proper bench.py cleanup, deferred).
- Suggested commit (human runs): git add the 4 recognizer files + bench.py + HISTORY/RESULTS + the skill; NO git rm.
- NOT mine, pre-existing, leave: projects/integration_harden/ (dead fork, ~22), projects/llm_to_action/ (~10),
  docs/ ARCHITECTURE/NOTES + docs/active handoffs. Audit files in repo root (gitignored) can be rm'd.

## 5. The apply_he ablation -- DECISION: KEEP
- Question: with Gemma reading Hebrew natively, is stage 2 (apply_he, ~659 of 786 recognizer lines, built "to make
  the Hebrew survivable before translation") now dead weight?
- Measured 2026-09-12 (unified_bench, temp 0, one server): raw Hebrew to Gemma (apply_he OFF) = 404/487 vs
  410/487 with it. std190 236->228 (-8), perception 103->105 (+2), others flat. Net -6.
- Verdict: apply_he is LOAD-BEARING for commands (+8 std190), slightly hurts perception. KEEP it. It is not bloat.
- Deferred option if leanness still wanted: per-rule ablation to keep only the load-bearing rules (likely
  number-word composition + the sign map) and drop the rest. A measured mini-project, not a blind delete.

## 6. WHAT TO DO NEXT (priority order)
1. LIVE WEBCAM TEST (never run with this session's changes). Command in section 2. Validate: boot, F5->ASR->
   recognizer->Gemma routing, SAM3 highlight, count median, the live pane, and that the recording lands intact
   (asr_clips/utt_NNNN.wav linked in trace.jsonl; perception/<seq>-<kind>/). Fix what it surfaces.
2. Commit the translated-path retirement (section 4) -- corrected (no git rm bench.py).
3. Strip bench.py's dangling legacy functions (make_translator, plan, main).
4. Rewrite tools/bench/hebrew-command-bench/README.md to current state (it is still translated-path-centric;
   point it at unified_bench.py, move the DictaLM/Hy-MT2 comparison to superseded).
5. Open PERCEPTION bugs to verify/fix on the webcam run:
   - SAM3 grounds ZERO for visibly-present objects at the 0.1 floor (the "all guitars" miss). Investigate.
   - count median is partly fake: COUNT_GAP < SAM3_PERIOD so the frame cache returns the same frame.
6. FIELD POWER (owner's first-class concern): optimize ENERGY per flight, not latency. Run power_profile.py
   UNPLUGGED (battery discharging) for the true total-system Wh/flight. 5070-Mobile is the dev rig; the backpack
   deployment target (embedded, 15-60 W) is unmeasured. See docs/NOTES.md + the field-power memory.
7. Owner's gitignore->logs/* restructure (remove the gitignore pile, move artifacts into dedicated dirs). BLOCKED:
   groundstation-c2 is live in docs/active/assets/ + .claude/skills/diagram-authoring/ (untracked). Do NOT git clean.

## 7. Key files
- App: mvd.py, overlay.py, session_log.py, run.sh, config_constants.py / config_defaults.py / config.py.
- Recognizer: recognizer/recognizer.py (recognize_direct, negation_only, EMERGENCY_RE), pipeline.py (handle_direct, _plan2), prompts.py (UNIFIED_PROMPT/GRAMMAR/SHOTS).
- Perception: perception2/sam3_backend.py (SAM3, 1008px), perception/detectors.py (YOLO26 bg).
- Bench: tools/bench/hebrew-command-bench/unified_bench.py (THE harness), results/RESULTS.md + HISTORY.md.
- Server: run_llama_server.sh (Gemma on :18090; the BENCH uses llama.py PORT=18091 for its own). Tools: session-replayer/replayer.html, desk-test/power_profile.py.


## FIELD-TEST NOTES (the two that still hold)
- INDOOR vs OUTDOOR: a real drone INDOORS refuses lateral/vertical sticks (VPS can't lock) -- yaw + slow vertical
  only; OUTDOORS is nominal. Not a comms fault. Expect this in an indoor dry-run. (memory indoor-vps-denial-behavior)
- PHONE IP = the WiFi default gateway, CHANGES per hotspot session; derive from the default route, never hardcode.
  (The other memory field notes -- hardware-baseline, drone-bootstrap, retests-on-webcam -- are STALE; ignore them.)

## ADDITIONAL OPEN ITEMS (triple-check 2026-09-12 -- things the body missed)
- Bucket C (commit-manifest): files touched 2026-09-11 23:47..00:39 of unclear authorship -- NOW KNOWN to be
  groundstation-c2's diagram/skill A-B work (skill-ab-test, ab-*-prompt.md, the diagram-authoring skill, some
  memory edits). Leave them; they are the teammate's, untracked. NOT harden2 work -- do not commit as such.
- SUPERSEDED launchers still tracked/committed: tools/desk-test/{up,down,status,preflight}.sh + run_mvd.sh are
  replaced by run.sh. Retire them in the cleanup (owner git rm). list_cams.py is superseded by cam_list.py.
- ASR mis-transcription seen live ("היי עלי לגיטר" garbled -> reject): ASR quality, separate issue.
- trace.jsonl timings{} validated only on a SYNTHETIC session; a real webcam run fills them for the first time.
- Throwaway audit files in the repo root: gitignored-decisions.txt, gitignored-all.txt (gitignored) -- rm after review.
- whole-system RESULTS.md "(not recorded)" gaps: whisper k-quant WER/CER on real clips, Gemma live-mic + native
  Hebrew answer quality -- open research, post-commit.
