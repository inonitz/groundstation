# Runtime drone-dependent config for tuning constants

**Status:** scheduled / not started. **Flagged:** 2026-08-08. **ROADMAP:** 9.14.
**Gate:** required before real-Tello flight; not blocking the SITL POC.

## Problem
Every physical tuning value in the FMU is a compile-time `constexpr` in `fmu_node_base.hpp`. These
values are drone- and environment-dependent. PX4 Gazebo SITL and the real Tello have different
dynamics, so they need different numbers. One binary cannot serve both today. Changing any value
means editing a header and rebuilding the whole workspace.

## Which constants
The tunables that differ by drone or environment, all currently `constexpr`:
- Takeoff: `kTakeoffTargetAltEnu`, `kTakeoffClimbVelEnu`.
- Land: `kLandDescendVelEnu`, `kFlareStartAltEnu`, `kFlareTouchdownVelEnu`, `kGroundContactEnu`.
- Battery failsafe: `kBatteryReturnPct`, `kBatteryLandPct`.
- Manual override: `kManualTeleopVelCmS` (+ the inline `kManualYaw`).
- GO: `kDefaultGoSpeedCmS`, `kGoApproachGainHz`, `kGoCrossTrackGainHz`, settle dwell.
- ROTATE: `kRotateYawGainHz`, `kRotateMaxYawRate`, `kRotateCompletionDeg`.
- APPROACH: `kApproachStandoffM`, gains, `kApproachRangeMedianWindow`, `kApproachCoastHoldMarginM`.
- Future emergency boundary (Spec 1): `kBoundaryBaseM`, `kBoundaryVelScale`, etc.

The Tier-4 Tello work lands here too: stick/velocity calibration (2.3.1) and the environment-keyed
velocity modes (2.3.4) are just per-drone profiles of the same values.

## Why it matters
SITL numbers were tuned against PX4 in Gazebo. The real Tello climbs, drifts, and brakes
differently. Flying it with the SITL constants is unsafe. We need one binary that loads the right
profile per drone, not a recompile per drone.

## Design sketch
- A small `DroneConfig` struct holding the tunables above.
- Populated at startup from a drone-selected profile file (e.g. `config/px4_sitl.yaml`,
  `config/tello.yaml`), chosen by CLI arg / env var / active backend type.
- The compiled `constexpr` values stay as the built-in **default** and as documentation of a sane
  number. They are the fallback when no profile file is given.
- No exceptions (project rule). A malformed profile logs then falls back to defaults. A missing
  profile for an explicitly-selected drone logs `RCLCPP_FATAL` then `std::abort()`.
- The FMU reads from the struct, not from the constants directly.

## Scope
- **In:** the tuning values listed above.
- **Out:** perception model paths (separate concern), a full ROS parameter server, per-flight
  hot-reload. Keep it a load-once struct.

## Priority
Not blocking the SITL POC — the defaults are the SITL values. Required before the first real-Tello
flight, and it unifies the deferred Tier-4 Tello calibration under one mechanism.
