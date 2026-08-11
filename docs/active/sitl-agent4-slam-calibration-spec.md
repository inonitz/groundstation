# Agent 4 — SLAM camera calibration (owner: agent + human)

**Date: 2026-08-11** · Deadline: Wed evening 2026-08-12.

**Mission**: produce real, verified Tello camera intrinsics. `dependencies/stella_config_tello.yaml`
currently self-flags its values as provisional/unverified — monocular SLAM needs real intrinsics.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + LOCKS + commit rules),
then `CLAUDE.md`, `docs/code-guidelines.md`. Study: `scripts/tello/CALIBRATION.md`,
`scripts/tello/calibrate_camera.py`, `scripts/tello/capture_calibration_frames.py`,
`scripts/tello/make_checkerboard.py`, `scripts/tello/checkerboard_a4_9x6_20mm.pdf`;
`dependencies/stella_config_tello.yaml` (the `Camera:` block you will fill).

**Your place in the plan**: you unblock Agent 5's SLAM assessment (C1). Do this early — it gates SLAM.

## Do (manual, with the human)

1. Print the checkerboard; capture 20–40 varied frames with `capture_calibration_frames.py` over the
   Tello video feed.
2. Run `calibrate_camera.py` → intrinsics (fx, fy, cx, cy) + distortion + reprojection error.
3. Write the verified intrinsics into `dependencies/stella_config_tello.yaml` `Camera:` block; note the
   reprojection error in the file header. **Coordinate this file with Agent 5** (both touch it — lock it
   in `docs/LOCKS.md` while editing).

## Deliverable

Calibrated `stella_config_tello.yaml` + a one-line reprojection-error note. Report whether the
calibration is trustworthy (low reprojection error) — Agent 5's tracking verdict depends on it.

## Locks

`dependencies/stella_config_tello.yaml` (coordinate with Agent 5). Calibration outputs / captured
frames are yours alone.

## Constraints

No git writes — suggest `agent4: tello camera calibration`. Prose per `docs/writing-style.md`.

## Report
_(append the intrinsics summary + reprojection error + trust verdict below)_
