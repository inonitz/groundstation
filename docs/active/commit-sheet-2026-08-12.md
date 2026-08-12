# Commit Sheet — 2026-08-12

Every commit, grouped by repo, in order. You run all git. Copy each block. Shared files
(`docs/NOTES.md`, `docs/LOCKS.md`) are touched by multiple agents — they get ONE combined commit at the
end of the groundstation set, not per-agent.

**Do NOT commit (junk in the tree):** `0`, `s_n_c_014.jpg.jpeg`, `snoffice3.jpg`, `snoffice4.jpg`,
`vlm_logs/`, `scripts/test/SITL/runs/`, `scripts/tello/slam/runs/`. Add to `.gitignore` or skip.

---

## Repo 1 — groundstation  (branch `feature-llm-driver`)

### 1. Agent 1 — FOLLOW / perception
```bash
git add source/llm_to_action/fmu/fmu_node.hpp source/llm_to_action/fmu/fmu_node_base.hpp \
        source/llm_to_action/fmu/llm_base.hpp source/llm_to_action/fmu/llamaclient.hpp \
        source/llm_to_action/fmu/perception_runtime.hpp source/llm_to_action/fmu/CMakeLists.txt \
        source/llm_to_action/perception/detection_query.hpp source/llm_to_action/perception/detection_query_test.cpp \
        source/llm_to_action/perception/target_tracker.hpp source/llm_to_action/fmu/test/target_tracker_test.cpp \
        dependencies/three_people.sdf \
        scripts/test/SITL/logtest.sh scripts/test/SITL/digest.sh scripts/test/SITL/TESTING.md \
        scripts/test/SITL/crowd scripts/test/SITL/search_follow scripts/test/SITL/follow/watch.sh
git commit -m "fmu: FOLLOW visual servo + HOVER + SEARCH-by-tag + stable-id tracker + perception-coast; grammar hardening; SITL follow test tooling"
```

### 2–5. Agent 5 — SLAM  (four commits)
```bash
git add source/slam/slam_pose_bridge.hpp source/slam/hover_hold_control.hpp source/slam/slam_recovery_fsm.hpp source/slam/test
git commit -m "agent5: slam pose->ENU bridge + hover-hold PID + recovery FSM (pure headers, offline-tested)"

git add source/slam/slam2.hpp
git commit -m "agent5: publish slam/tracking_state (Bool) from slam2.hpp every worker cycle"

git add source/llm_to_action/tello_backend/test/tello_slam_hold.cpp source/llm_to_action/tello_backend/CMakeLists.txt
git commit -m "agent5: tello_slam_hold node (slam/pose -> hold -> land-on-loss) + CMake target, no ament"

git add scripts/tello/slam/feature_scout.py scripts/tello/slam/run.sh scripts/tello/slam/c1test.sh \
        scripts/tello/slam/test3.sh scripts/tello/slam/measure_tello_slam.py scripts/tello/slam/digest.sh \
        scripts/tello/slam/runtests.sh scripts/tello/slam/aruco_pose.py scripts/tello/slam/README.md scripts/tello/slam/TESTING.md
git commit -m "agent5: C1 go/no-go harness + Test 3 hover launcher + venue pre-screen + docs"
```
(Do NOT `git add scripts/tello/slam/` wholesale — that pulls in `runs/` logs. List the files.)

### 6. Insurance — noise-robustness + demo plan
```bash
git add dependencies/noise_beds/battle_0.wav dependencies/noise_beds/battle_1.wav \
        dependencies/noise_beds/battle_2.wav dependencies/noise_beds/battle_3.wav \
        docs/active/asr-noise-robustness.md docs/active/demo-plan-spec.md
git commit -m "docs: ASR noise-robustness benchmark (91% intent @ 0 dB, raw audio) + gunfire/explosion noise beds + demo decision in NOTES"
```
(Insurance is re-running the sweep against 20 s beds — the curve numbers in the doc will refresh; the
commit is the same either way.)

### 7. Manager — architecture docs + specs
```bash
git add docs/system-architecture.md docs/system-architecture-slides.md \
        docs/active/sitl-system-diagram-spec.md docs/active/sitl-asr-integration-spec.md \
        docs/active/recovery-checkpoint-2026-08-12.md docs/active/commit-sheet-2026-08-12.md
git commit -m "docs: system-architecture diagram + 12-slide deck + ASR integration/diagram specs + recovery checkpoint"
```

### 8. Manager — rubicon sim fix
```bash
git add dependencies/rubicon.sdf
git commit -m "fix(sim): restore rubicon ground_plane + sun (c3639fd left it Fuel-only -> empty world)"
```

### 9. Manager — rubicon scenario stub
```bash
git add scripts/test/SITL/rubicon/run.sh
git commit -m "test(sitl): rubicon scenario stub (combined world + human still TODO)"
```

### 10. Shared docs (all agents) — commit LAST
```bash
git add docs/NOTES.md docs/LOCKS.md docs/ROADMAP.md
git commit -m "docs: multi-agent session notes + lock ledger + roadmap"
```

Then: `git status` should show only the junk from the do-not-commit list. Push: `git push origin feature-llm-driver`.

---

## Repo 2 — sttserv  (branch `feature-multimodel`)

### 1. Manager — benchmark docs
```bash
git add README.md
git commit -m "docs: noise-filter + transcription-confidence benchmark findings"
```

### 2. Insurance — SNR robustness sweep
```bash
git add test/asr_test.cpp test/asr_test.hpp test/snr_mix_core.h
git commit -m "asr: in-process gunfire/explosion SNR robustness sweep in the accuracy test | mix noise into clean clips at a controlled SNR and print an accuracy-vs-SNR table | fix util2/C/print.h -> print2.h after the util2 rename"
```
(Confirm `test/asr_test.cpp` no longer has the manager's throwaway CFDUMP probe — that was to be reverted;
Insurance's sweep is the real change here.)

---

## Repo 3 — BUILD_noisefilter  (branch `library`)

> **PRIVACY GATE — read before pushing.** This repo's git HISTORY contains private voice recordings
> (`recordings/`, `out/`). See `/root/models/asr/BUILD_noisefilter_privacy_purge.md`. Commit locally if
> you want, but do NOT push to a public repo until history is purged and moved to a fresh repo.

### 1. Manager — README + WAV support + MP3 helper
```bash
git add README.md .gitignore main.cpp wav_io.cpp mp32wav.c
git commit -m "Document benchmark findings; widen WAV support; add MP3 decode helper"
```

### 2. Insurance — SNR mixer
```bash
git add CMakeLists.txt snr_mix.h snr_mix.cpp snr_mix_core.h
git commit -m "Add snr_mix — header-only SNR noise mixer (mix_at_snr) plus a WavData adapter, folded into noisefilter_lib"
```

---

## Who owns what (one-line map)

| Repo | Agent 1 | Agent 5 | Insurance | Manager |
|---|---|---|---|---|
| groundstation | commit 1 | commits 2–5 | commit 6 | commits 7–9 |
| sttserv | — | — | commit 2 | commit 1 |
| BUILD_noisefilter | — | — | commit 2 | commit 1 |

Shared `docs/NOTES.md` / `LOCKS.md` / `ROADMAP.md` = groundstation commit 10 (everyone appended; commit once).
