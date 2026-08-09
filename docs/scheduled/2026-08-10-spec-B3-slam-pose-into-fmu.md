# B3 — SLAM pose → FMU (Tello position + return-to-start)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Branch:** feature-slam-tello.
**Depends:** B1 (must track first). **ROADMAP:** 7.4, 2.3. **Lock:** `fmu_node.hpp` + `TelloBackend` — coordinate.

## Objective
Once stella tracks, feed `slam/pose` into the FMU as the Tello's horizontal position and add
return-to-start — the capability the Tello physically cannot do today.

## Scope
- **In:** consume `slam/pose` as `TelloBackend` x/y; scale anchor via Tello ToF/baro altitude
  (scale-free relocalization is fine for return); a return-to-start command.
- **Out:** OctoMap / A* planning (post-POC, ROADMAP 7.2–7.3).

## Tests to create
- **[AUTO]** SITL canned return-to-start driven by `slam/pose` → assert the drone returns to origin
  within tolerance (ground truth available in sim).
- **[HUMAN]** hardware return-to-start once stella runs on the real drone.

## Acceptance
Return-to-start works in sim on slam pose; the FMU consumes it as Tello odometry.

## Agent notes
Gated on B1. This is the only slam-branch spec that touches the FMU hotspot — serialize via `LOCKS.md`.
