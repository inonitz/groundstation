# Recovery Checkpoint — 2026-08-12

Sleep/recovery snapshot of the multi-agent push. The human is recording 2 examples then sleeping;
the physical demo is deferred. All agents resume later from a Docker on the Workstation. This file plus
the session bundle (`/root/gs_sessions_20260812T210612.tgz`, re-bundle after agents stop) is the full
recovery. Code goes to `origin/feature-llm-driver`; the human runs all git — agents only suggest
messages.

Blocks are pasted verbatim from each agent (Manager, Agent 1, Agent 5, Insurance Agent — all collected).

---

## Manager (this session)

**DONE**
- Orchestration: authored the 6 agent specs + `docs/active/sitl-orchestration-plan.md`; fixed the
  `scripts/test/SITL/` path breakage (21 scenarios + `run_all.sh` descent).
- ASR measurement (in `/root/sttserv`, separate repo): model sweep → **Parakeet-q4 on raw audio** wins
  (37/44, fastest, smallest); whisper-large ~12× slower for no gain.
- Confidence finding: the vendored Parakeet fork stores the **raw logit** in `parakeet_token_data.plog`
  (not `log(p)`) — use `.p`. And token-probability confidence **does not track correctness** (failing
  clips score higher). Confidence gate dropped → operator read-back.
- Noise-filter A/B (in `/root/BUILD_noisefilter`, separate repo): GTCRN 27/44, SpeexDSP 30/44, classical
  33/44 — **all net-negative vs raw 37/44**. Ship raw. Documented in both repos' READMEs (anonymized).
- ASR integration spec rewritten to reality: `docs/active/sitl-asr-integration-spec.md` — node is built
  and publishes `/asr_server/transcribe`; the **only** gap is one FMU subscription writing
  `m_initialCommand` + re-triggering `maybePlan()`. Confidence gate + noise filter removed from scope.
- System diagram: `docs/system-architecture.md` (3 mermaid UML views) + `docs/system-architecture-slides.md`
  (12-slide deck) + `docs/active/sitl-system-diagram-spec.md`. Reconciled against FOLLOW and SLAM sessions.
- Sim fix: `dependencies/rubicon.sdf` — restored a local `ground_plane` + `sun` (commit `c3639fd` had
  made it Fuel-only with no ground/light → empty world "doesn't load"). Kept the Fuel Rubicon terrain.
- `scripts/test/SITL/rubicon/run.sh` scenario stub (world+human still TODO — no combined world exists).
- Privacy: `BUILD_noisefilter` git history contains private voice recordings; wrote the purge guide at
  `/root/models/asr/BUILD_noisefilter_privacy_purge.md` (host-mapped via devenv). Needs `git filter-repo`
  + a fresh public repo — not yet done.

**WIP / open**
- ASR integration itself: Steps 2 (FMU subscription — `fmu_node.hpp` is FREE) + VLM prewarm
  (27 s→~9 s) are NOT implemented; I was about to start when the checkpoint came. Launch already
  co-hosts VLM `-c 1024` + Parakeet in `scripts/simenv.sh`.

**TODO / not started**
- SNR-sweep robustness curve (Insurance Agent's plan): a WAV mixer (RMS-scale noise, add at target SNR)
  on the BUILD_noisefilter harness → accuracy-vs-SNR against real gunfire/explosion audio.
- Combined `dependencies/rubicon_human.sdf` (rubicon terrain + one actor) for the rubicon demo.

**Files changed (manager, groundstation)**
- MODIFIED: `dependencies/rubicon.sdf`, `docs/active/sitl-asr-integration-spec.md`.
- NEW: `docs/system-architecture.md`, `docs/system-architecture-slides.md`,
  `docs/active/sitl-system-diagram-spec.md`, `docs/active/recovery-checkpoint-2026-08-12.md`,
  `scripts/test/SITL/rubicon/run.sh`.
- Separate repos (own commits, messages already suggested): `/root/sttserv` (README + `asr_bench...`
  removed for privacy + benchmark section), `/root/BUILD_noisefilter` (README + `wav_io.cpp` +
  `main.cpp` + `mp32wav.c`).
- Host-only (outside repo): `/root/models/asr/BUILD_noisefilter_privacy_purge.md`.

**Commit-msg suggestions (manager)**
- `docs: system-architecture diagram + 12-slide deck + ASR integration/diagram specs`
- `fix(sim): restore rubicon ground_plane + sun (c3639fd left it Fuel-only → empty world)`
- `test(sitl): rubicon scenario stub (combined world + human still TODO)`

**Do-not-commit flag for the human:** the working tree also holds junk that should NOT be staged —
`0`, `s_n_c_014.jpg.jpeg`, `snoffice3.jpg`, `snoffice4.jpg`, `vlm_logs/`, `scripts/test/SITL/runs/`
(run logs). Add to `.gitignore` or skip.

---

## Agent 1 — FOLLOW / perception / target-id

**DONE (landed, both px4+tello build clean)**
- FOLLOW verb: yaw-only visual servo (kFollowYawGain 5.0, cap 1.5), position-free; per-tick
  label+nearest-centroid; resolve-once at activation (track_id → target_index → CENTRE-detection
  fallback); standoff_cm = min-safe (back off only, never advance); loss = HOLD + re-acquire (sweep
  REMOVED, was spinning); never self-completes.
- HOVER verb (persistent hold, never wakes VLM).
- SEARCH-by-tag: CmdSearch.target_id + surfaces found track_id in "SEARCH DETECTED".
- Stable-id tracker: perception/target_tracker.hpp (greedy IoU+centroid, coast 15 frames, monotonic
  ids) + wired into perception_runtime; drawn on annotated frame.
- Grammar hardening (llamaclient.hpp): typed members (kills {"parameters":...} blob), single verb list,
  airborne drops takeoff, hover verb.
- Perception robustness (fmu_node): [PERCEPTION] COASTS blank frames (feeds last-seen <1.5s so seg
  flicker doesn't say "no detections"); first plan waits for first detection; zero-go dropped (no
  hover-starvation).
- Prompt (llm_base): rules 10 (hold/objective-complete), 11 (target-visible), 12
  (no-guess-ids/act-on-search_ok).
- VLM infra: OOM on 4GB GPU FIXED by running llama-server with --parallel 1 -c 4096.
- Tooling: scripts/test/SITL/{logtest.sh (hires), digest.sh (self-reporting), TESTING.md, crowd/,
  search_follow/, follow/watch.sh}, dependencies/three_people.sdf, fmu/test/target_tracker_test.cpp
  (7/7 green).
- Docs: docs/NOTES.md updated.

**WIP / open (NOT resolved)**
- VLM SPEED: ~30s prompt eval on the 4GB GPU (image-heavy). Mitigations (image 640→448, a perception
  directive) were tried and REVERTED at the human's explicit instruction (do NOT bias the model /
  degrade the image). Speed is UNSOLVED and is the top demo risk.
- VLM (2B Qwen3-VL) sometimes hallucinates "person not visible" and searches even when a person IS in
  [PERCEPTION] → erratic search. Prompt fix insufficient; an FMU-side guard (drop search when following
  + person detected) is PROPOSED, not built, awaiting human decision.
- FOLLOW responsiveness: gain 5 tracks, but errX still spikes ~0.96 on the worst detection gaps.

**TODO (not started)**
- SITL ground-truth PASS/FAIL assertion (scripts/test/lib/wait_for_ground_truth.sh).
- Rename/sort all scripts/test/SITL/* dirs (naming is inconsistent).
- confirmed_target metadata (needs seg-thread-safe tracker passthrough — deferred to avoid a data race).
- Appearance-embedding re-ID (deferred, flag-gated).

**Files changed**: source/llm_to_action/fmu/{fmu_node.hpp,fmu_node_base.hpp,llm_base.hpp,llamaclient.hpp,
perception_runtime.hpp,CMakeLists.txt}, perception/{detection_query.hpp,detection_query_test.cpp}; NEW:
perception/target_tracker.hpp, fmu/test/target_tracker_test.cpp, dependencies/three_people.sdf,
scripts/test/SITL/{logtest.sh,digest.sh,TESTING.md,crowd/,search_follow/,follow/watch.sh};
docs/{NOTES.md,LOCKS.md}.

**Commit-msg suggestion**: "fmu: FOLLOW visual servo + HOVER + SEARCH-by-tag + stable-id tracker +
perception-coast; grammar hardening; SITL follow test tooling"

---

## Agent 5 — SLAM / Tello localization

**Suggested commits (house style; human commits)**
1. `agent5: slam pose->ENU bridge + hover-hold PID + recovery FSM (pure headers, offline-tested)`
2. `agent5: publish slam/tracking_state (Bool) from slam2.hpp every worker cycle`
3. `agent5: tello_slam_hold node (slam/pose -> hold -> land-on-loss) + CMake target, no ament`
4. `agent5: C1 go/no-go harness + Test 3 hover launcher + venue pre-screen + docs`

**DONE (landed)**
- C1 assessment: stella_vslam on the real Tello. Clean tracking on textured forward scenes — 99–100%
  uptime, 0 blind, ~27 Hz over multi-minute flights. GO on textured surfaces.
- Frame mapping decoded + validated on hardware: stella map is camera-optical (+x right, +y down,
  +z forward); Tello horizontal plane = map (x,z), up = -y.
- Pure control headers, all offline-unit-tested (runtests.sh, 4/4 pass): map->ENU align,
  scale-from-height (median), OneEuro (toggle), hover-hold PID (anti-windup), degrade-then-land recovery
  FSM.
- slam/tracking_state (Bool) published from slam2.hpp (built + links in the real SLAM binary).
- tello_slam_hold node: built + linked on hardware config, instrumented (per-tick [hold] diag), gains
  env-tunable (TELLO_HOLD_KP/KI/MAXV). Turnkey harness: feature_scout (venue ORB pre-screen),
  c1test/digest (go/no-go), test3.sh (hover-hold + land-on-loss), TESTING.md.

**WIP (open — active blocker)**
- Hover-hold NOT yet validated on hardware. First flights: the hold does not visibly stabilize over
  BARE floor. Key finding: earlier "good" holds were the Tello VPS holding over floor mats, NOT SLAM —
  VPS looks DOWN, stella looks FORWARD, different surfaces. Re-testing over bare floor (VPS blinded) to
  isolate SLAM. Instrumented the node this session to resolve weak-authority (raise maxVel) vs
  sign/frame bug from the [hold] log. Awaiting the human's next diagnostic run.
- Recovery land-on-loss: coded + offline-tested, hardware-unconfirmed.

**TODO (not started)**
- Unit A: TelloBackend.setSlamPose + write last-known XY into odometry().pos (deferred; only
  FMU-APPROACH consumes it).
- ArUco fallback INTEGRATION: aruco_pose.py exists standalone (self-test passes) but is not wired as a
  pose source. After hover-hold validates; the controller is source-agnostic so it's a wiring job.
- FMU integration of the bridge (slam/pose -> fmu_node) — deferred until other agents finish.
- Smoothing on/off A/B, drift on-vs-off (external-camera metres) — after the hold holds.

**Files changed**
- Modified: docs/NOTES.md, docs/LOCKS.md, source/slam/slam2.hpp,
  source/llm_to_action/tello_backend/CMakeLists.txt
- New (headers): source/slam/{slam_pose_bridge,hover_hold_control,slam_recovery_fsm}.hpp
- New (offline tests): source/slam/test/{slam_pose_bridge,hover_hold_control,slam_recovery_fsm,
  hover_hold_sim}_test.cpp
- New (node): source/llm_to_action/tello_backend/test/tello_slam_hold.cpp
- New (scripts): scripts/tello/slam/{feature_scout.py, run.sh, c1test.sh, test3.sh,
  measure_tello_slam.py, digest.sh, runtests.sh, aruco_pose.py, README.md, TESTING.md}
- Note: scripts/tello/slam/runs/ is generated logs — gitignore, do not commit.

## Insurance Agent — demo decision / ASR noise-robustness

**DONE**
- **Demo decision LOCKED with the user:** pure-SITL voice-driven mission on the dashboard is the
  headline; Tello hardware NOT bet on. Mission chains perception-conditioned verbs live: "take off and
  find the hatted man" → approach/hold → "now follow him" (sequential context) → "orbit him" (re-task)
  → one improvised Q&A command (proves not-canned). Hebrew = English-live + one canned Hebrew clip +
  roadmap. Must-dos: pre-warm the VLM (cold 27 s), record a backup video, deterministic world/seed,
  speak on the ground.
- ASR noise-robustness benchmark BUILT + RAN. `snr_mix_core.h` (header-only, zero-dep) mixes
  gunfire/explosion beds into clean clips at controlled SNR; wired in-process into
  `sttserv/test/asr_test.cpp` as a sweep printing an accuracy-vs-SNR table. Result (Parakeet-q4, raw
  audio): **91% intent @ 0 dB, ~80% @ −4 dB, collapse past −6 dB.** Confirms "ship raw" (all denoisers
  net-negative). 4 gunfire/explosion beds → `dependencies/noise_beds/`.
- Fixed a pre-existing break: `asr_test.cpp` included `util2/C/print.h`; the util2 swap renamed it to
  `util2/C/print2.h` — this was the only file left on the old path (grep other consumers).
- Docs: `docs/active/asr-noise-robustness.md` (method + curve + reproduce), `docs/NOTES.md` bullets.

**WIP**: none — all deliverables landed.

**TODO (hand to demo prep)**
- ASR→FMU wiring (manager lane, ~1 hr) is the one gap between this and a live voice demo.
- End-to-end latency benchmark (mic-release → first setpoint) to put the ~2 s number on a slide.
- Cosmetic: teardown prints "223/538 (0.414%)" — missing ×100, should be 41.4%. Left as-is.

**Files changed (3 repos)**
- BUILD_noisefilter: M CMakeLists.txt; NEW snr_mix.h, snr_mix.cpp, snr_mix_core.h
- sttserv: M test/asr_test.cpp, test/asr_test.hpp; NEW test/snr_mix_core.h
- groundstation: NEW dependencies/noise_beds/battle_{0..3}.wav, docs/active/asr-noise-robustness.md;
  M docs/NOTES.md

**Commit messages (per-repo; human runs)**
- sttserv: `asr: in-process gunfire/explosion SNR robustness sweep in the accuracy test | mix noise into
  clean clips at a controlled SNR and print an accuracy-vs-SNR table | fix util2/C/print.h -> print2.h
  after the util2 rename`
- BUILD_noisefilter: `Add snr_mix — header-only SNR noise mixer (mix_at_snr) plus a WavData adapter,
  folded into noisefilter_lib`
- groundstation: `docs: ASR noise-robustness benchmark (91% intent @ 0 dB, raw audio) +
  gunfire/explosion noise beds + demo decision in NOTES`

## Agents 0 / 2 / 3 / 4 (earlier waves, largely committed)

Not separately pinged (their sessions closed). Their landed work + reports live in their spec files:
`docs/active/sitl-agent0-tello-keyboard-spec.md` (keyboard override + drift; closed on real hardware),
`sitl-agent2-dashboard-spec.md` (dashboard, verified headless — committed `54b8a6a`),
`sitl-agent3-qa-cleanups-spec.md` (P1 disarm PASS, YOLO test, ROADMAP), `sitl-agent4-slam-calibration-spec.md`
(Tello intrinsics, RMS 0.438 — committed). Recent commits already on the branch:
`a87946b` (grammar), `c4f308f` (config loader), `673e5f0` (camera), `54b8a6a` (dashboard),
`bb72903` (FOLLOW).
