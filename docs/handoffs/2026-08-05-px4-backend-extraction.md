# Session Handoff — PX4Backend extraction + GO-spiral debug

**Date:** 2026-08-05 (end of session). **Branch:** `feature-llm-driver`.
**Mode note:** caveman mode was active for chat prose; code/commits normal.

---

## Where we are (one paragraph)

Phase-2 sub-project **A** (DroneBackend abstraction) is being executed from the
plan `docs/superpowers/plans/2026-08-04-px4-backend-extraction.md` against the spec
`docs/superpowers/specs/2026-08-04-drone-backend-abstraction-design.md`. **Tasks 1–3
are code-complete and the refactored FMU flies the canned SITL smoke test end to
end** (takeoff → GO 1m → land → disarm), verified twice in `output.txt`. A real
flight-quality bug was then found and **root-caused** (GO traces a logarithmic
spiral). Task 4 (ENU seam) is NOT started. The spiral fix is NOT implemented.

## Task status

| Task | What | Status |
|---|---|---|
| U1 | `px4_backend/frame_convert.hpp` (ROS-free math) + `px4_backend_base.hpp` (wire builders + ALL ROS I/O config) + standalone `g++` test | ✅ done, test passes |
| U2 | `px4_backend/px4_backend.{hpp,cpp}` — concrete `PX4Backend` (pubs/subs/handshake/stream loop/atomics), NED | ✅ done, compiles, port verified |
| U3 | FMU rewired onto verbs; inline wire layer deleted; `offboard_translator.hpp` removed; planner code untouched | ✅ done, flies SITL |
| — | Debug instrumentation: `Odometry` now carries `vel` + `yawrate`; FMU logs measVelNED + yawrate | ✅ added (for the spiral diagnosis) |
| U4 | Flip seam to canonical ENU + numeric direction assert (LAST review gate) | ⬜ NOT started |
| Spiral fix | GO controller (see below) | ⬜ NOT started, root cause known |

Everything is still **NED end-to-end**. ENU only happens in U4.

## Files created/modified this session (for the README change-log later)

- Created: `source/llm_to_action/px4_backend/frame_convert.hpp`
- Created: `source/llm_to_action/px4_backend/px4_backend_base.hpp`
- Created: `source/llm_to_action/px4_backend/px4_backend.hpp`
- Created: `source/llm_to_action/px4_backend/px4_backend.cpp`
- Created: `source/llm_to_action/px4_backend/test/frame_convert_test.cpp`
- Modified: `source/llm_to_action/fmu/fmu_node.hpp` (rewired onto backend verbs + high-verbosity logs)
- Modified: `source/llm_to_action/fmu/fmu_node_base.hpp` (trimmed to FMU-only constants)
- Modified: `source/llm_to_action/CMakeLists.txt` (added px4_backend sources; removed translator)
- Deleted:  `source/llm_to_action/fmu/offboard_translator.hpp`
- Modified: `NOTES.md` (climb-authority note earlier; GO-spiral root cause today)
- caveman-init also dropped IDE rule files (`.cursor/ .windsurf/ .clinerules/ .github/ .opencode/`, appended `AGENTS.md`) — unrelated to the refactor.

## GIT — NOT PERFORMED BY CLAUDE (user rule)

Claude executed ZERO git commands all session. Every intended commit is logged in
`/tmp/claude-0/-root-groundstation/9480fabd-fd70-4042-9b2d-ebf4edaa9b0b/scratchpad/git_operations_ledger.md`
(scratchpad is session-scoped — copy it out before it expires if you want it).
Nothing was pushed/fetched. Review + commit manually. The instrumentation edits
(measVelNED/yawrate) are uncommitted on top of the Task-3 changes.

## THE BUG — GO logarithmic-spiral ("golden ratio arc")

**Confirmed root cause:** the GO controller in `fmu_node.hpp::controlLoop()` is
constant-speed **pure pursuit with no deceleration**. Each 20Hz tick it commands
`unit(targetNED - posNED) * 0.30 m/s` at a fixed waypoint. PX4's velocity
controller lags and the drone carries lateral momentum the 0.30 setpoint can't
cancel, so the velocity vector lags the rotating command and the position orbits
the target while distance shrinks → logarithmic-spiral pursuit curve.

**Evidence (output.txt, GO block):**
- `yawrate ≈ 0.00` throughout → NOT weathervane (yaw drifts 1.92→1.73 passively).
- cmd vs meas velocity agree in SIGN (N−, E+) → NOT a frame/sign error.
- `|meas| ≈ 0.53 m/s` vs `|cmd| = 0.30` → overspeed/coast; direction lags command.
- altitude sagged 2.28→1.68m during GO → velocity-only offboard has no altitude hold.
- GO-entry meas vz = −1.28 → residual takeoff climb velocity still active.
- "forward → ESE" is CORRECT: sim spawn yaw ≈ 2.09 rad (matches NOTES.md 2.10).

**Fix options (DECIDE FIRST tomorrow):**
1. **PREFERRED — GO as a PX4 POSITION setpoint.** Send `position = targetNED`,
   `velocity = NaN` in `TrajectorySetpoint` for GO; keep velocity setpoints only for
   takeoff/land. PX4's position controller then gives a straight line, smooth decel,
   and altitude hold — removes spiral AND the alt sag in one move. Requires a
   `position_setpoint(...)` builder in `px4_backend_base.hpp` and a backend verb
   like `set_position(Vec3 targetWorld, f32 yaw)` (or extend the streamed setpoint to
   carry a mode+position). Mind the architecture: the backend stream loop currently
   always publishes `mode_velocity`; GO-position needs `mode_position` on those ticks.
2. Fallback — proportional decel in the existing velocity path:
   `speed = clamp(kApproachGain * dist, vMin, vMax)` toward the target. Cheap, keeps
   the velocity architecture, but still lag-prone and won't fix altitude sag.

## OPEN ITEM (lower priority)

First odometry arrived ~20s after node start in BOTH runs → handshake gated on
`!m_gotFirstOdom` sat idle ~20s (CONFIRMED at setpoints≈603 @30Hz). Not blocking
(it still armed + flew), but the 20s odom-publish latency in this Gazebo world is
worth a look (EKF convergence? DDS discovery? QoS?).

## How to rebuild + reproduce

```bash
# build (operator does this; Claude does NOT compile ROS):
#   build the llm_to_action_fmu target as usual.
# run the canned smoke test:
cd /root/groundstation && ./scripts/simenv_llm.sh
# exit tmux: Ctrl+B then :kill-session
```
Standalone frame-math test (Claude CAN run this, ROS-free):
```bash
g++ -std=c++17 -I build/release/shared/_deps/sttserver-src/dependencies/util2/include \
  source/llm_to_action/px4_backend/test/frame_convert_test.cpp -o /tmp/fct && /tmp/fct
# expect: frame_convert_test OK
```

Debug logs to grep in `output.txt`: `FMU_NODE_DEBUG` (transitions/verbs),
`FMU_NODE_DIAGNOSTICS` (500ms heartbeat: pos + measVelNED + yaw + yawrate; GO block
at 250ms with cmdVelNED vs measVelNED), `PX4_BACKEND_DEBUG` (handshake + 1Hz stream).
Log lines are WRAPPED by the tmux capture — un-wrap with
`open(f).read().replace('\n','')` before regex, or records will look truncated.

## Resume checklist (tomorrow, in order)

1. Decide GO fix: **position setpoint (preferred)** vs proportional decel.
2. Implement + SITL-verify a straight, non-spiraling GO with altitude hold.
3. Then Task 4: ENU seam + numeric direction assert (§8.2 of the plan) — LAST gate.
4. (Optional) investigate the 20s first-odom latency.
5. Commit manually per the ledger; annotate the README change-log of created/
   modified/deleted files (list above).

## Process reminders that still apply

- Claude does NOT compile ROS; operator compiles + runs, Claude diffs logs.
- Claude does NOT run git; all git ops go to the ledger for manual review.
- No hardcoded ROS I/O — topics/QoS/tuning live in `px4_backend_base.hpp`.
- Concurrency: keep the proven Reentrant-cbgroup + atomics model (spec §10.M1
  defers the `Shared<T>` mutex design until an off-executor thread forces it).
- Bite-sized units, reviewed one before the next; caveman prose, normal code.
