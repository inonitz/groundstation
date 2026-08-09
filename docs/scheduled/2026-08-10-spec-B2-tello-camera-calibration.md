# B2 — Tello camera calibration (operator, ground)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Branch:** feature-slam-tello.
**Depends:** none (parallel, no flight). **ROADMAP:** 7.1 support. **Owner:** operator. **Lock:** none.

## Objective
Give stella a real-Tello camera model. Calibrate on the ground so B1's tracking transfers to hardware.

## Scope
- **In:** checkerboard capture (20–40 frames, varied angle/distance), OpenCV `calibrateCamera`,
  intrinsics + distortion + reprojection error, written to `dependencies/stella_config_tello.yaml` at
  the real resolution (~960×720, NOT the sim's 1280×720).
- **Out:** anything requiring flight.

## Tests to create
- **[AUTO]** assert reprojection error < ~1 px from the calibration output; assert the YAML loads.
- **[HUMAN]** the capture itself is manual.

## Acceptance
A Tello-resolution calibrated config with sub-pixel reprojection error, loadable by stella.

## Agent notes
Operator ground task, ~30–60 min with tooling ready. Runs fully in parallel with everything else.
