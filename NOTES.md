# Architectural Notes

## PX4 OFFBOARD engage (fmu_node offboardPublishLoop)
- Stream `OffboardControlMode` + `TrajectorySetpoint` continuously from node start
  (zero-vel in STANDBY) — PX4 rejects an OFFBOARD switch without a live setpoint stream.
- **Do NOT arm on a wall-clock/setpoint timer.** Gate the engage on first odometry
  received (`m_gotFirstOdom`) so the estimator is actually valid — arming before the
  local-position/velocity estimate exists spins motors with nothing to act on -> no
  climb -> auto-disarm. This was the "rotors spun then stopped" bug.
- Proven order (from speech_to_action): **arm first, then request OFFBOARD**, and RETRY
  both every tick until `VehicleStatus` confirms `ARMING_STATE_ARMED (2)` +
  `NAVIGATION_STATE_OFFBOARD (14)`. Never fire-and-forget a single VehicleCommand.
- **Takeoff needs climb AUTHORITY, not a gentle setpoint.** A -1.0 m/s climb velocity
  did NOT track (altNED stuck ~0.04 for ~4s while commanding velz=-1.0): PX4's MC
  controller ramps thrust timidly while it still thinks the vehicle is *landed*, so a
  small velocity error lingers in ground effect - long enough for uneven terrain to tip
  the airframe onto its props before it gains height. Fix: climb at **-2.0 m/s to -2.0 m**
  (the proven speech_to_action profile). Bigger vz error -> more thrust -> clears ground fast.
  `kTakeoffClimbVelNed`/`kTakeoffTargetAltNed` in fmu_node_base.hpp.

## PX4 message versioning -> topic name suffixes (gotcha)
- PX4 appends `_vN` to a topic when its `.msg` has `MESSAGE_VERSION = N > 0`.
  - `VehicleStatus` (MESSAGE_VERSION=4) -> `/fmu/out/vehicle_status_v4`
  - `VehicleOdometry` (MESSAGE_VERSION=0) -> `/fmu/out/vehicle_odometry` (no suffix)
- A ROS2 sub on the wrong (unversioned) name fails SILENTLY — it just holds default
  values, no error. Cost us a dead VehicleStatus sub (nav/arm stuck at 0) that looked
  fine because the flight worked anyway via the odom-gate above.

## Coordinate frame (verified in sim)
- `flu_to_ned(flu, yaw)`: north = x·cosψ + y·sinψ, east = x·sinψ − y·cosψ, down = −z.
- Verified: "forward 1 m" at spawn yaw 2.10 rad produced NED (−0.50, +0.86) = (cosψ, sinψ)
  — drone flew along its heading. Forward mapping correct; y-left sign not yet exercised.
