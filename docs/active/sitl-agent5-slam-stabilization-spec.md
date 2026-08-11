# Agent 5 — SLAM stabilization & recovery (owner: agent + human)

**Date: 2026-08-11** · Deadline: Wed evening 2026-08-12.

**Mission**: make SLAM close the Tello position loop and give it localization + minimum recovery for a
real "search & fly to the hatted man" run. All greenfield.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + LOCKS + commit rules),
then `CLAUDE.md`, `docs/code-guidelines.md`, `docs/writing-style.md`,
`docs/active/sitl-B1-task5-agent-prompt.md` (prior stella SITL prompt, reference). Study:
`source/slam/slam2.hpp` (publishes `slam/pose` + clouds; `tracker_is_paused` gate at `155`;
`slam1.hpp` is dead — ignore); `tello_backend.cpp` `odometry_impl` (`151`, returns `pos={0,0,height}`)
+ `tello_backend_base.hpp` state schema (velocity vgx/vgy/vgz + height, NO XY); `scripts/test/slam/`
(SITL comparator `compare_ground_truth.py`).

**Verified reality (trust code, not docs)**: nothing consumes `slam/pose` for control today; the Tello
reports no XY position; the ARCHITECTURE doc's "Simpson's-rule dead-reckoning" driver does NOT exist.

**Your place in the plan**: blocked-by Agent 4 (calibration) + the human's manual control. C1 is a
go/no-go gate for C2/C3.

## C1 — Assess on the REAL Tello first (go/no-go; needs manual control)

- Bring up `stella_vslam_monocular` on the Tello `camera/stream` (the `--tello` gstreamer RX feed);
  use Agent 4's calibrated `stella_config_tello.yaml`. Fly a path + a return-to-start loop.
- Measure (no EKF2 ground truth on Tello, unlike SITL): pose rate, **tracking fraction** (pose present
  vs `tracker_is_paused`), **scale consistency** (SLAM z vs metric Tello height), **return-to-start
  error**. SITL only de-risks the bridge code; the quality verdict is from reality.
- **If stella can't hold tracking indoors after calibration, STOP and report** — C2/C3 depend on it.

## C2 — Stabilization test (build; impl + test same bucket)

- **`slam/pose`→Tello odometry bridge**: consume `slam/pose` (map frame, up-to-scale); align map→ENU at
  init (initial yaw/gravity); **resolve monocular scale from the metric Tello height Z**; write XY into
  the Tello `odometry().pos` (today hard-zeroed).
- **Hover-hold controller**: XY position error → `set_velocity` (Tello takes only velocity setpoints,
  `tello_backend.cpp:143-149`). Note: `stop`/hover on the Tello is NOT a no-op like SITL — it must
  actively cancel drift.
- **Measure XY drift SLAM-on (hold) vs SLAM-off (drift)** during a hover. Package a self-contained test
  script (yours alone, no lock).

## C3 — DR + fusion + recovery (minimum recovery is required for the Tello demo)

- Simpson-integrate `vgx/vgy/vgz` from flight start → DR XY pose; expose via `odometry()`.
- Complementary-fuse: SLAM corrects DR bias while alive; DR free-runs when tracking is paused.
- Surface a **tracking-state topic** from `slam2.hpp` (not published today) so the FMU knows when to
  trust SLAM vs DR.
- On loss: hold on DR, seed relocalization with the DR pose, **relocalize against the live in-RAM map**
  (no disk save/load — the session map is already in memory). Re-anchor on success.

## Locks (docs/LOCKS.md)

`source/slam/slam2.hpp`, `tello_backend.cpp`, `tello_backend.hpp`, `tello_backend_base.hpp`,
`dependencies/stella_config_tello.yaml` (with Agent 4). Your new stabilization test script is yours alone.

## Constraints

No git writes — suggest `agent5: slam->odometry bridge` etc. per unit. Prose per `docs/writing-style.md`.

## Report
_(append C1 tracking numbers / C2 drift on-vs-off / C3 recovery result + blockers below)_
