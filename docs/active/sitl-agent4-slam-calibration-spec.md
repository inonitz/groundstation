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

**Done 2026-08-11.** Measured intrinsics written to `dependencies/stella_config_tello.yaml`.

Calibration from 39 checkerboard frames (9x6 inner corners, 20 mm squares), all 39 detected.
Resolution confirmed 960x720. First pass used 22 frames (RMS 0.555) but its distortion was
thin at the image edges, so k3 overfit to 1.38. A coverage analyzer (scripts/tello/
analyze_calibration_coverage.py) named the gaps -- right and top edges unreached, narrow
distance range -- and a targeted second burst filled them.

- fx=914.98, fy=914.71 (agree 0.03%)
- cx=486.09, cy=362.42 (near true centre 480, 360)
- distortion k1=-0.025, k2=-0.005, p1=0.0003, p2=0.0018, k3=0.107
- **reprojection RMS error: 0.438 px** (target < 1.0)

**Verdict: trustworthy, no caveats.** Adding edge and distance coverage dropped RMS from
0.555 to 0.438 and collapsed k3 from 1.38 to 0.11, confirming the first pass was edge-starved,
not the lens. Focal lengths match, principal point sits at centre, distortion is well-supported.
Agent 5 can rely on these for the C1 SLAM assessment.

fps in the config is the Tello's native 30, not the host-measured decode rate. The preview ran
far below 30 under load, so the capture script's measured-fps number was unreliable and not used.

Tooling added under scripts/tello/ (all mine): resumable frame numbering and a live battery
overlay in capture_calibration_frames.py, plus analyze_calibration_coverage.py, which reports
image-region coverage, edge reach, tilt, and distance spread so a thin capture is fixed by
targeted frames instead of guesswork.

Lock cycle on `stella_config_tello.yaml` acquired and released in `docs/LOCKS.md`.
