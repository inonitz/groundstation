# B1 — stella_vslam SITL bring-up (the risk spike)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Branch:** feature-slam-tello (NEW).
**Depends:** none — start in parallel. **ROADMAP:** 7.1. **Lock:** `source/slam/` only; NO `fmu_node.hpp`.

## Objective
Answer the one unbounded question on the whole Tello path: **does stella_vslam actually track?**
Uncomment the pose publish, align the camera topic to the Gazebo sim, run it in-sim, and confirm
`slam/pose` tracks and the map builds. Separate node, zero FMU risk.

## Scope
- **In:** uncomment `publish_rviz_pose()` in `slam2.hpp`, point the config at the sim camera
  (`stella_config.yaml`, 1280×720), a launch entry, and a tracking-health assertion.
- **Out:** wiring pose into the FMU (that is B3). Keep it standalone.

## Tests to create
- **[AUTO]** run a `--canned` SITL flight in a textured world → assert `slam/pose` publishes at rate,
  tracking-state = tracking for > a threshold fraction of frames, and drift vs PX4 EKF2 ground truth
  stays under tolerance. **We have ground truth in sim, so this is fully automatable.**
- **[HUMAN]** eyeball the map + trajectory in rviz once.

## Acceptance
`slam/pose` tracks a canned SITL flight within a drift tolerance against EKF2.

## Agent notes
Timebox this. It is the schedule risk. If it does not track by the timebox, fall back to the
position-free Tello demos (B4) and defer B3. Front-load it so the fallback decision is made early.
