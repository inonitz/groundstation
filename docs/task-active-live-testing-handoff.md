# Handoff — live testing (for the live-testing-4 subagent), 2026-09-16

## Read first (safety + ownership — non-negotiable)
- CLAUDE.md HARD RULES: the assistant NEVER sends arm/takeoff/land/stick/velocity/motor to a REAL drone.
  It PREPARES the command; the HUMAN runs it. Run control tools ONLY against the mock (127.0.0.1), never a phone IP.
- The HUMAN owns ALL git writes. You prepare exact commands; never stage/commit/mv/rm/push. Use rtk wrappers for bash.
- Branch: feature-hardening-mvd, ~14 commits ahead of origin (unpushed). All cleanup is committed (aa787ca..32bd2fd).

## Where we are in the plan
1. Cleanup & restructure — DONE (committed). 2. Webcam smoke test — IN PROGRESS (green except 2 issues below).
3. Nuclear code review + ponytail review — NEXT if webcam green. 4. Outdoor field test -> freeze the baseline (git tag).
5. Post-freeze: run tools/power_profile.py (embedded power gauge, BEFORE low-light), whisper-noise + SAM3 low-light benches.
6. Features off the baseline. 7. Fuse harden2 into the C++ llm_to_action engine.
Entry points: docs/task-active-restructure-progress.md (full cleanup history + rulings), docs/README.md (overview),
docs/spec-harden2-architecture.md (LIVE arch), docs/ROADMAP.md (phase arc), docs/HISTORY.md (log + extracted rulings).

## The system (harden2 = LIVE)
- projects/integration_harden2: Hebrew voice -> whisper-ivrit ASR -> recognizer safety sieve (emergency stop / negation
  guard / basic verbs) -> ONE Gemma-4 E4B call (routes + plans mission + names target + presence-gate + answers Hebrew)
  -> {mission verbs -> DJI REST /c/fly | perception queries -> SAM3 open-vocab highlight/count/describe}.
- projects/integration_tts = FROZEN English demo fallback (changes never land there).
- projects/llm_to_action = PARKED C++ FMU engine (the destination product; fuse later). Its docs: spec-fmu-architecture.md.
- Laptop is the brain; DJI drone via phone (control/telemetry :8080, H.264 video :5600). 8 GB GPU holds Gemma; SAM3/depth on CPU.

## run.sh — the ONE run+diagnose script (projects/integration_harden2/run.sh)
- Subcommands: up | down | status | preflight | score | show. (desk-test was folded in; runbooks retired.)
- Boot (webcam + mock, agent-safe): WEBCAM_DEV=<n> SCENE_TTS=espeak bash projects/integration_harden2/run.sh up webcam mock
- Diagnose: run.sh status (ports/panes/transcripts/commands + app-wiring/video/phone-gate/cameras). run.sh show latest.
- Score a session vs an e2e list: run.sh score datasets/e2e/live-test-e2e-50.md <session>
- Sessions record to logs/sessions/session-* (trace.jsonl + asr_clips/). Runs to logs/runs/latest (per-pane *.log).
- Retest convention (memory retests-on-webcam): webcam + mock; phone/drone only for final footage, HUMAN-run.

## Webcam smoke test — STATUS 2026-09-16
GREEN (verified): preflight webcam PASS; boot = 5 panes (vlm keys asr app mock), no crashes; ASR all Hebrew tests pass;
planner+perception route highlight/count/describe; mission -> mock POST; recording lands in logs/sessions (trace+clips);
run.sh status/show diagnostics work. Bench logic already unchanged (410/487).
OPEN (non-blocking, for you to fix — small):
- #4 Scene window UX: opens tiny, and is fullscreen-able with empty margins around the frame+chatbox. Owner wants it to
  OPEN at the needed size (video frame + chatbox), not resizable to empty. Fix the opencv window setup in mvd.py / overlay.py
  (cv2.namedWindow + resizeWindow to content size, or WINDOW_AUTOSIZE; cap/disable fullscreen).
- #5 Laptop TTS silent: SCENE_TTS=on is INVALID and silently falls to OFF. Valid: phone|espeak|piper|both|off (audio/tts_io.py).
  For laptop: SCENE_TTS=espeak needs espeak-ng installed (NOT currently installed; preflight does not check it) OR
  SCENE_TTS=piper needs a piper bin+voice+aplay. FIX: install espeak-ng (add to tools/devenv/install-runtime-deps.sh + Dockerfile)
  AND make tts_io.py warn on an unrecognized SCENE_TTS value instead of silently going off.

## Immediate next steps
1. Fix #4 (window size) + #5 (TTS value + espeak-ng install). Retest on webcam.
2. Nuclear code review: /thermo-nuclear-code-quality-review (user-invoked / cloud). Then ponytail review (/ponytail-review).
3. Report results; if clean -> owner runs the outdoor field test -> freeze the exact tested commit as the baseline (git tag).

## Constraints / gotchas / loose ends
- DANGLING refs: CLAUDE.md still points at @docs/writing-style.md and docs/code-guidelines.md, both now merged into
  docs/guidelines.md. Repoint them (or do the planned CLAUDE.md -> AGENTS.md move). Small, not yet done.
- Docs are FLAT + prefixed: spec- / research- / research-complete- / task-active- / task-scheduled-. Only stale/ and
  private/ are folders. stale/ is DELETED at the GitHub commit / freeze (owner's manual review). private/ never committed.
- Bench: bench/hebrew-command-bench/unified_bench.py is THE harness (410/487 baseline). Re-run full after touching
  recognizer/pipeline; temp 0; one model on GPU at a time; state a duration estimate before GPU runs; zero-false-fire gate.
- datasets/asr: built (139 clips, 101 matched to transcripts, 38 unmatched; gitignored). Transcripts are whisper OUTPUT,
  NOT corrected references -- a raw corpus; the correction pass is still future work.
- Memories (in ~/.claude): retests-on-webcam, drone safety, phone-IP-is-gateway (changes per session, derive from route),
  indoor-VPS-denial (yaw+slow-vertical only indoors), field-power-thermal, hebrew-bench-state, be-critical-not-sycophantic,
  owner-wants-short-reports, prose lists-or-flow. READ them before acting.
- Owner interaction: address every numbered point; decisions into repo docs immediately; recommendations != decisions;
  concrete copy-paste commands with absolute paths; real tests over mocks; short reports (answer first, one table, detail in files).

## Key files
- run/diagnose: projects/integration_harden2/run.sh (+ score_session.py, show_session.py, cam_list.py)
- app: projects/integration_harden2/{mvd.py (scene loop), overlay.py (pane), config.py, audio/tts_io.py, recognizer/, session_log.py}
- bench: bench/hebrew-command-bench/unified_bench.py ; e2e lists: datasets/e2e/live-test-*.md
- docs: docs/{README,ROADMAP,HISTORY,guidelines,spec-harden2-architecture,spec-fmu-architecture}.md

## Test utterances (Hebrew, one per path) — say each with F5
- Emergency: "עצור עצור"            -> halt/stop, MUST NOT fly (zero false-fire)
- Negation:  "בלי להסתובב בבקשה"    -> refused, MUST NOT spin (negation guard)
- Mission:   "טוס קדימה שני מטרים"   -> fly_by mission -> POST /c/fly in mock_commands.log
- Highlight: "סמן את הכיסא"          -> perception(highlight), NO drone POST, overlay drawn
- Count:     "כמה כיסאות"            -> perception(count), a number
- Scene Q:   "מה אתה רואה"           -> Hebrew scene answer

## Container / devenv (so nothing is lost on rebuild)
- The dev container WIPES ad-hoc installs on rebuild. Never apt/pip ad-hoc -- add to tools/devenv/Dockerfile
  AND tools/devenv/install-runtime-deps.sh (run that script after any rebuild). This is exactly how to fix TTS #5:
  bake espeak-ng, not apt-install it by hand.
- devenv.sh host-mounts persist across rebuild: the repo, all model dirs (asr/translate/vlm/vision = 143 GB),
  ~/.claude (memories), the DJI backend repo. logs/ and datasets/ live in the mounted repo (persist, gitignored).
- To STOP a real drone (field test, HUMAN only): phone API Server toggle OFF, or hold the aircraft power button 3-5 s.
  Full kill procedure + classification of every tool (SAFE vs ARMS-THE-DRONE) is in CLAUDE.md -- read it in full.

## FIXES DONE 2026-09-16 (live-testing-4) — #4 + #5 closed

- #5 TTS: espeak-ng + alsa-utils already baked in install-runtime-deps.sh + Dockerfile.
  Ran `bash tools/devenv/install-runtime-deps.sh`; espeak-ng + aplay now on PATH.
  tts_io.py: added an invalid-SCENE_TTS guard. An unknown value now prints
  "[voice] SCENE_TTS='on' not recognized (use phone|espeak|piper|both|off) -> OFF"
  instead of going silently off.
  VERIFIED (real): espeak-ng synth to WAV OK; live playback rc=0 (HDMI card 0 present);
  SCENE_TTS=espeak -> backend "espeak" ("speaking on: laptop espeak");
  SCENE_TTS=on -> warns + backend "off". Audible check is the human's (no ears here).
- #4 Scene window: mvd.py window flag WINDOW_NORMAL|WINDOW_KEEPRATIO -> WINDOW_AUTOSIZE.
  AUTOSIZE opens at content size and is not user-resizable, so no empty-margin fullscreen.
  VERIFIED (real, on DISPLAY :0.0): a 720x1740 canvas (frame+chat) in an AUTOSIZE window
  reports getWindowImageRect w=1740 h=720 -- opens at exact content size.
- Files changed (owner git): projects/integration_harden2/mvd.py,
  projects/integration_harden2/audio/tts_io.py. (Dockerfile + install-runtime-deps.sh
  were already modified by the prior agent.)
- STILL NEEDS THE HUMAN: the F5 Hebrew retest (mic + eyes on window). My edits do not
  touch the ASR/planner/perception/mission paths, which were already GREEN.

## CORRECTION 2026-09-16 (live-testing-4) — espeak Hebrew was spelling letters

My earlier #5 "verified" tested ENGLISH text only, so it passed while the real
Hebrew path (SCENE_TTS_LANG=he) was broken. espeak got NO voice flag, so the
English voice read each Hebrew letter by name ("Letter LAMED", "Letter MEM" ...).
FIX: tts_io.py _say_local now calls espeak with `-v config.TTS_LANG` (e.g. -v he).
VERIFIED: Voice invokes ['espeak-ng','-v','he',text]; on the real utterances the
WAV drops ~5x with -v he (words, not letter names): "עצור עצור" 255KB -> 49KB.
Audible check is still the human's. espeak Hebrew is a robotic desk-debug voice;
the demo TTS remains the phone (Google he-IL). piper Hebrew would need a he voice model.

## DECISION 2026-09-16 (owner): adopt Phonikud offline Hebrew TTS

- espeak Hebrew rejected (unintelligible). Chatterbox multilingual rejected (owner: "pretty bad").
  ElevenLabs rejected (closed API). Phone Google TTS rejected for field use (needs cellular data).
- ADOPT Phonikud (INTERSPEECH 2026) as the offline Hebrew voice: Phonikud G2P -> Piper voice.
  Demo quality judged "significantly better than Chatterbox" by the owner.
- LICENSE (checked): G2P code = CC BY 4.0 (commercial OK, attribution). Voice checkpoints
  (phonikud-tts-checkpoints) = CC non-commercial (cc-nc); trained data (SASpeech/ILSpeech) = non-commercial.
  RULING: fine for demo/competition now. Commercial use deferred -- owner: replicate or improve the work
  with ~3 months of research + compute if a commercial voice is ever needed.
- TASK: wire Phonikud -> Piper as an offline SCENE_TTS backend in projects/integration_harden2/audio/tts_io.py.
  Bake models into tools/devenv (Dockerfile + install-runtime-deps.sh). Owner runs the model download
  (auto-mode blocks downloads). Note (attribution) the Phonikud G2P per CC BY 4.0.

## PHONIKUD WIRED 2026-09-16 (live-testing-4) — offline Hebrew TTS, verified

- New backend SCENE_TTS=phonikud in audio/tts_io.py. Chain: text -> phonikud G2P (adds niqqud+stress,
  emits IPA) -> phonikud_tts.Piper onnx voice -> float32 PCM -> aplay. Pure onnxruntime; no piper CLI.
- Config: config_defaults.py + config.py add PHONIKUD_G2P / PHONIKUD_VOICE / PHONIKUD_CONFIG
  (default /root/models/tts/phonikud/{phonikud-1.0.int8.onnx,model.onnx,model.config.json};
  override via SCENE_PHONIKUD_G2P / _VOICE / _CONFIG). Falls back to espeak if models or aplay are missing.
- Deps + models: install-runtime-deps.sh installs phonikud/phonikud-onnx/phonikud-tts, downloads the 3
  models, and warms the dicta-il tokenizer cache. Same pip pins baked in tools/devenv/Dockerfile.
- VERIFIED (real, this container):
  - End-to-end synth: "עצור עצור" -> "ʔatsˈoʁ ʔatsˈoʁ", 0.94s clean audio (real words + stress, not letters).
    "טוס קדימה שני מטרים" -> "tˈus kadˈima ʃnˈej mˈetʁim", 1.88s. aplay rc=0.
  - Voice class: SCENE_TTS=phonikud -> backend "phonikud", speaks.
  - OFFLINE: with HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 it still loads and speaks (field-safe).
  - The protobuf 4->7 bump from phonikud deps did NOT break torch/transformers/onnxruntime/app imports.
- Audible quality is the owner's ear; the owner already judged the same models "significantly better than Chatterbox".
- CAVEATS: G2P is a 307MB int8 CPU onnx, loaded once; per-utterance synth was sub-second in the test but
  compute latency was not isolated -- unverified. HF cache (tokenizer) is not a devenv mount; a rebuild wipes
  it, so run install-runtime-deps.sh (online) after each rebuild -- the warm-up repopulates it for offline field use.
- Boot: SCENE_TTS=phonikud bash projects/integration_harden2/run.sh up webcam mock

## CORRECTION 2026-09-17 (owner): models via host mount, NOT baked in Dockerfile

- Reverted the Dockerfile model-download RUN block. The Dockerfile bakes only the pip packages
  (phonikud phonikud-onnx phonikud-tts). Models belong on a host logical-volume mount, like the other model dirs.
- /root/models/tts is NOT yet mounted in tools/devenv/devenv.sh (only asr/translate/vlm/vision are). Owner adds it.
- 5a VERIFIED: SCENE_TTS is read through the python config chain -- env SCENE_TTS -> config.py
  TTS_BACKEND (os.environ.get) -> tts_io Voice. Tested: phonikud/phone/off map through, default phone.
  The run.sh fix (forward SCENE_TTS to the app env) makes the CLI value reach that chain reliably.

## FROZEN-TREE / STALE-PATH BUG SWEEP 2026-09-17 (owner-requested)

Two bug types hunted repo-wide, squashed in the LIVE integration_harden2 tree (never touched the frozen
integration_tts or the other dev's llm_to_action). Verified: 66 tests pass; final greps clean.

TYPE A -- runtime output written INTO the frozen tree (resolved off __file__/$HERE):
- recognizer/trace.py: default traces/ (next to the package) -> <repo>/logs/traces (+ MVD_TRACE_DIR override).
- config_defaults.py: SESSIONS_ROOT default _HERE/sessions -> <repo>/logs/sessions (CLIPS_DIR/SESSION_DIR derive from it).
- run_mvd.sh: MVD_SESSION_DIR default $HERE/sessions -> <repo>/logs/sessions.
- Checked clean: run.sh (RUN_ROOT + session_dir already logs/), session_log.py, show_session.py, score_session.py,
  video_watchdog BIN, recognizer/llama.py (logs to /tmp), perception vlm_client (/tmp).

TYPE B -- stale paths to archived/moved locations:
- projects/integration_harden (the fork archived in the restructure) -> projects/integration_harden2 in
  video/{video_watchdog,video_doctor,camera_stream}.py, perception{,2}/detectors.py comments,
  perception2/chain_demo.py, and README run commands.
- tools/bench (moved to bench/) -> bench/ in perception2/{sam3_backend,chain_demo}.py + README, recognizer/{README,__init__}.
- PRESERVED as history (correct, not bugs): README.md:1 "FORK of integration_harden", recognizer.py:39 "copied from
  projects/integration_harden/commands.py". MVD_HOME defaults already = integration_harden2 (correct).

FLAGGED, not fixed here (out of the two bug types):
- README.md:7 heading "# integration_harden/ -- the revised MVD" is stale prose -> the README doc-pass, not a path fix.
- run_mvd.sh is a LEGACY launcher superseded by run.sh (referenced only in comments); the restructure slated it for
  archival. Recommend archiving it rather than keeping two launchers.
- bench/ still has tools/bench + integration_harden refs (retired campaigns + the owner-accepted run_all.sh default);
  separate from the frozen harden2 tree.
