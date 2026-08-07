# Spec 1 — Interrupt & reactive safety

**Status:** unassigned (for a spawned session). **ROADMAP:** 1.5, 6.1, 6.4.
**Owns (edits):** `source/llm_to_action/fmu/fmu_node.hpp`, `.../fmu/fmu_node_base.hpp`.
Overlaps the movement handler with Spec 2 & 4 — the overseeing session merges; keep edits localized
and clearly commented.

> **Repo conventions (read first, you start cold):** this project's `CLAUDE.md` forbids the native
> Read/Grep/Glob tools — use `rtk read <file>` / `rtk grep <pat> <path>` / `rtk ls` via Bash. Edit
> with python heredocs (`open().read()/.replace()/.write()` with `assert s.count(old)==1`) since
> native Edit needs a blocked Read. **Do NOT touch the `GenericCommand` byte layout** (`m_id` +
> `m_padToMultipleForCmd` + `union m_rawBytes`) — it is intentionally 8-byte aligned. Match existing
> style/indentation. Do not run a full build (heavy); leave build + SITL verify to the human.

## Goal
One reflex shared by three triggers: **detect a problem → STOP → stash the active task → wake the
VLM to reassess → hold until cleared.** This is the safety spine the other specs lean on.

## Current state
The 20 Hz tick is `fmu_node.hpp` ~line 376+ (`od = m_backend->odometry(); n/e/d = od.pos.*; st =
m_flightState.load(...)`). Movement commands run in `if (m_hasActive)` (~line 427) dispatching by
`m_currTask.m_cmd.id()`. There is **no** interrupt/hold path today: a task runs to completion or
FAIL; nothing can pre-empt it and resume later.

## Design
### A. Interrupt core (1.5)
Add one helper and one saved slot:
- Members: `ActiveTask m_stashedTask{}; bool m_hasStashed{false};` (near `m_currTask`).
- `void raiseInterrupt(const char* reason)`:
  1. `m_backend->set_velocity(Vec3{0,0,0}, 0.0f);` — immediate hover/STOP.
  2. If `m_hasActive`: copy `m_currTask` → `m_stashedTask`, `m_hasStashed=true`, `m_hasActive=false`.
  3. Log `[FMU_NODE_DEBUG] INTERRUPT (reason=%s): stashed=%s hover+reassess`.
  4. Trigger the existing event-driven VLM wake with `reason` folded into the prompt (see the
     dynamic-prompt builder ~line 716) so the model reassesses with context.
- **Hold-clearance:** while interrupted and no active task, keep streaming hover each tick. Resume is
  implicit: the VLM's next plan enqueues normally. The stashed task is **not** auto-resumed (the
  reassess decides); expose it in the prompt as "interrupted: <thought>" so the model can re-issue if
  still valid. (Auto-resume is out of scope — reassess owns the decision.)

### B. Emergency boundary (6.1) — a trigger for A
Each tick, after odometry: `speed = norm(od.vel)`, `trigger = kBoundaryBaseM + kBoundaryVelScale *
speed`. Read the nearest obstacle distance from the atomic `PerceptionSnapshot` the FMU already holds
for the prompt (min `median_depth_cm/100` over detections; if you must, add a small
`nearestDepthM()` helper next to the existing snapshot accessor). If `nearest > 0 && nearest <
trigger` → `raiseInterrupt("emergency_boundary")`. Depth is slow: gate on snapshot age — if the
snapshot is older than `kBoundaryMaxSnapshotAgeMs`, treat nearest as unknown (do **not** trip on
stale data; optionally slow down instead). Constants → `fmu_node_base.hpp`.

### C. APPROACH motion-gate (6.4) — a trigger for A
In the APPROACH movement branch (`else if (id == CommandID::APPROACH)`, ~line 476+), at the tick
where "reached/approach_ok" would be declared, **also** require nominal motion:
`fabs(od.yawrate) < kApproachNominalYawrate && fabs(od.vel.z) < kApproachNominalVertVel` (altitude
not collapsing). If motion is out of nominal → `raiseInterrupt("approach_impact")` instead of
`approach_ok`. (Root cause: a real collision produced yawrate 6.9, vert vel −1.75, alt 0.99→0.02 m in
~1 s but range read 1.83 m off an impact frame and declared success.)

## New constants (fmu_node_base.hpp)
`kBoundaryBaseM` (~0.6), `kBoundaryVelScale` (~0.5 s), `kBoundaryMaxSnapshotAgeMs` (~500),
`kApproachNominalYawrate` (~1.0 rad/s), `kApproachNominalVertVel` (~0.6 m/s). Tune in SITL.

## Testing (log-based, SITL)
Reuse the canned-plan rig (`injectCannedPlan`/`--canned*`). (1) Force a boundary trip with a canned
obstacle → assert `INTERRUPT (reason=emergency_boundary)` + hover. (2) Reuse the canned-approach
collision path → assert `INTERRUPT (reason=approach_impact)` NOT `approach_ok`. Coordinate the test
harness with Spec 4 (shared canned infra).

## Out of scope
Interrupt hysteresis / max-retries (6.3, dropped). Auto-resume of the stashed task. Evasion motion
(move-aside / nudge-opposite) — design it here only if trivial; otherwise leave a stub + note for a
follow-up, hover-and-reassess is the MVP.

## Implementation report (session: append below, do not edit above)
<!-- files changed, key decisions, deviations from this spec, what was/wasn't SITL-tested -->
