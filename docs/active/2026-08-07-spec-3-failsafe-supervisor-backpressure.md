# Spec 3 — Failsafe supervisor & task-queue backpressure

**Status:** unassigned (for a spawned session). **ROADMAP:** 6.2 (battery/failsafe supervisor + user
override), 1.4 (SPSC backpressure).
**Owns (edits):** `source/llm_to_action/fmu/fmu_node.hpp` (supervisor check + enqueue site),
`.../fmu/fmu_node_base.hpp` (thresholds), and one keyboard/topic path for the override. This package
is the most file-isolated (supervisory layer + queue) — least overlap with Specs 1/2/4.

> **Repo conventions (start-cold):** `rtk read/grep/ls` only (native Read/Grep/Glob forbidden by
> `CLAUDE.md`); edit via python heredocs with `assert s.count(old)==1`. **Never touch the
> `GenericCommand` byte layout.** No full builds; human does build + SITL/hardware.

## Design
### 6.2 Failsafe supervisor + user override
Battery is now real through the backend: `m_telemetry.battery_pct` is refreshed each tick from
`m_backend->battery_pct()` (fmu_node.hpp ~line 379). Add a supervisory check in the 20 Hz tick,
evaluated **before** normal task dispatch:
- `pct = m_telemetry.battery_pct;`
- **`pct == -1` means UNKNOWN** (PX4/SITL sentinel) — skip all battery logic, never treat as empty.
- `pct >= 0 && pct <= kBatteryLandPct` → force LAND: pre-empt the plan, push `CmdLand` / set
  `FlightState::LANDING`, log `[FMU] FAILSAFE low battery %d%% -> forced LAND`. Latch it (don't
  oscillate if pct wobbles at the threshold — once latched, stay landing).
- `pct >= 0 && pct <= kBatteryAbortPct` (lower) → `force_disarm()` / abort, log FAILSAFE abort.
- **User override (ARCH 11):** a manual kill/override input (keyboard key via the existing teleop/key
  path, or a std_msgs topic) that forces hover/land/manual regardless of the VLM. Wire the simplest
  reliable path; document it. This is the human's "stop obeying the model NOW" switch.

Coordinate with Spec 1: forced-LAND should ideally route through the same interrupt/stop reflex
(`raiseInterrupt`) if that has landed; if Spec 1 isn't merged yet, do a self-contained STOP+LAND and
leave a `TODO: route via raiseInterrupt once Spec 1 lands`.

### 1.4 SPSC backpressure (empirical, not theoretical)
The FMU task queue is `moodycamel::ReaderWriterQueue<ActiveTask>` sized `3*kControlLoopRateHz`
(fmu_node.hpp ~line 206). Producer = VLM planner thread, `m_taskQueue->enqueue(task)` (~line 850,
marked `TODO: handle backpressure`) — `enqueue` **grows unbounded** if the 20 Hz consumer falls
behind or a huge plan arrives. Consumer = `try_dequeue` (~line 565).
- **Step 1 (observe):** instrument `size_approx()` over time; drive the queue with real VLM plan
  output (long/rapid plans) and record how deep it actually gets. Characterize the real behavior
  before choosing a policy.
- **Step 2 (mitigate in the queue):** switch the producer to `try_enqueue` against the fixed
  capacity; on full, apply a policy chosen from Step 1's data — reject-newest or drop-oldest — and
  **log every drop** (silent loss is unacceptable). Optionally cap plan length at parse time.

## New constants (fmu_node_base.hpp)
`kBatteryLandPct` (~20), `kBatteryAbortPct` (~10), and a queue-policy note. Tune with real telemetry.

## Testing
Supervisor: SITL/real — drive `battery_pct` low (Tello real telemetry; PX4 sentinel path must be
proven to do nothing) → assert forced-LAND log + latch. Override: trigger the input mid-flight →
assert manual takeover. Backpressure: flood the queue → assert bounded size + drop logs, no unbounded
growth.

## Out of scope
Full power-model / time-to-empty estimation. Anything needing SLAM.

## Implementation report (session: append below, do not edit above)
<!-- files changed, override mechanism chosen, observed queue depth + policy picked, tests run -->
