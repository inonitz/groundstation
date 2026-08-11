# Agent 0 — Physical Tello + keyboard override (owner: human)

**Date: 2026-08-11** · Deadline: Wed evening 2026-08-12.

**Mission**: get the physical Tello flyable by keyboard and characterize its in-space drift. You also
run the physical tests other agents' SLAM/FOLLOW work depends on.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + LOCKS + commit rules),
then `CLAUDE.md`, `docs/code-guidelines.md`. Study:
`docs/active/2026-08-10-tello-physical-handoff.md`, `scripts/tello/README.md`,
`docs/tello_backend_notes.md`; `fmu_node.hpp` `keyCallback` (`1490-1513`) + `overrideCallback`
(`1443`) + the manual-override block in `controlLoop` (`538-543`).

**Your place in the plan**: you unblock manual flying for Agents 1 (FOLLOW test) and 5 (SLAM
assessment). The Tello build/config is already done.

## Root cause (keyboard "keys captured, no motion")

`keyCallback` (`fmu_node.hpp:1494`) drops all movement keys unless `m_manualOverride` is true. That
flag is set ONLY by the `/fmu/in/override` Bool topic — which **nothing publishes and no key toggles**.
So WASD are logged but inert. (`keyCallback` also only implements WASD/arrows/Space — no arm/takeoff/
land keys, despite the README.)

## Do

1. **Keyboard override fix**: in `keyCallback`, handle a toggle key (Enter — already bound/published by
   the keyboard node) **before** the `!m_manualOverride` early-return at line 1494, flipping
   `m_manualOverride` (+ `zeroManualVel()` on disengage) and logging the new state. Lock `fmu_node.hpp`
   in `docs/LOCKS.md` first (short hold).
2. Fix `scripts/tello/README.md` — it wrongly claims keyboard does arm/takeoff/land.
3. Fly bring-up + manual control. Characterize the **drift**: it is the whole airframe drifting in
   space (the Tello holds attitude, not position — no XY feedback), NOT a rotate-specific bug. This is
   the case for Agent 5's SLAM. Optionally test whether a lower `rotateMaxYawRate` (`config/tello.yaml`,
   no rebuild) reduces rotation wander.

**Interim workaround** (until step 1 lands): engage override manually with
`ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data:true}"`.

## Test

Press Enter → override engages; WASD = plane, arrows = alt/yaw, Space = hover, with no manual topic pub.
Enter again disengages.

## Locks

`fmu_node.hpp` (short hold for `keyCallback`).

## Constraints

No git writes — suggest `agent0: keyboard override toggle`. Prose per `docs/writing-style.md`.

## Report
_(append findings / blockers / the measured drift behavior below)_
