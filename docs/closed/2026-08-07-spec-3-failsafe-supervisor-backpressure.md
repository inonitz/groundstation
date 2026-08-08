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

### Report — spec3-agent (2026-08-07)

**Scope correction landed with the overseer:** PX4 SITL *does* publish battery
(`/fmu/out/battery_status_v1`), so the PX4 backend was wired to real telemetry instead of the `-1`
stub. Override was redefined from a kill/land switch (my first wrong draft) to a **reversible manual
takeover**. The 10% action ships as honest land-in-place; the smart RTH/energy/terrain design is
documented in `docs/scheduled/2026-08-07-battery-rth-energy-terrain-subsystem.md`.

**Files changed (all via python heredoc; LOCKS acquired/released per file):**
- `generic_backend/generic_backend_types.hpp` — `kBatteryReadingUnknown = -1`.
- `px4_backend/{px4_backend_base.hpp,.hpp,.cpp}` — battery topic + `BatteryStatus` sub +
  `battery_pct_impl` returns `int(remaining*100)` (connected/NaN guard -> unknown). No CMake change
  (`px4_msgs` already linked).
- `fmu/fmu_node_base.hpp` — `kBatteryReturnPct=20`, `kBatteryLandPct=10`, `kFmuOverrideTopic`,
  `kManualTeleopVelCmS=50`, `kMaxPlanActions`.
- `fmu/fmu_node.hpp` — `batteryFailsafeTick` + `returnToOrigin` (GO-to-origin via `enu_to_flu`,
  dispatch-site land handoff), `overrideCallback`/`keyCallback`/`zeroManualVel`, control-loop
  failsafe + manual gate, `try_enqueue` backpressure. New subs `m_subOverride`/`m_subKey`.
- `keyboard/keyboard_node.hpp` — constructed the missing `m_rawKeyEvent` publisher (latent
  null-deref; overseer-approved).
- `scripts/simenv_llm.sh` — `llm_to_action_keyboard_hook` tmux pane + opt-in `DRAIN_BATTERY=1`.
- `docs/NOTES.md`, `docs/scheduled/...` — design note + deferred subsystem.

**Override mechanism chosen:** Bool `/fmu/in/override` toggles an atomic; `/keyboard/in/raw`
(Int32MultiArray) drives WASD/arrows/space -> constant body-FLU velocity (converted to ENU each
tick). Handback abandons the active task and forces a fresh VLM re-plan. Failsafe outranks manual.

**Backpressure policy:** reject-newest via `try_enqueue` against the fixed cap (60), every drop
logged via `m_taskDropCount`; producer stays single (control thread never enqueues). **Observed
queue depth: not yet measured** — needs a real VLM/SITL flood run (human, `[HW]`); heartbeat already
logs `qsize` for that measurement, and `kMaxPlanActions`/policy are tunable once data exists.

**Tests run:** none here (no full build in this environment; human does build + SITL/hardware).
Verification steps are in the spec's Testing section + the plan file
(`/root/.claude/plans/1-use-docs-code-guidelines-md-to-mossy-wren.md`). **All Spec-3 LOCKS released
(FREE).** Constants (`kManualTeleopVelCmS`, `kManualYaw` 0.6, thresholds) are placeholders to TUNE
in sim+real.

---

### Report — HITL verification & hardening (2026-08-08, spec3-agent)

**Manager review summary (read first).** Spec-3 (ROADMAP 6.2 battery/failsafe + user override,
1.4 SPSC backpressure) is implemented and **verified end-to-end in PX4 SITL** across a 6-test suite,
all PASS. Beyond the 2026-08-07 code drop, this session ran the tests human-in-the-loop and, in
doing so, found and fixed **8 real defects** — several safety-critical (a low-battery drone that
landed but never disarmed; a land-in-place that got overridden into flying home; PX4's own failsafe
silently taking the aircraft). Final behavior: the real PX4 battery drives the supervisor;
**≤20% → return-to-origin then land**, **≤10% → land-in-place**, both latched; a **reversible manual
override** (Bool topic + keyboard) that the failsafe outranks; and a **bounded SPSC task queue**
(reject-newest, every drop logged) proven under an in-air command storm. The `GenericCommand` byte
layout was not touched. Smart energy/terrain RTH stays deliberately deferred (pointer below).
**Not committed — left for manager review.**

**Final behavior shipped.**
- *Battery bridge:* `battery_pct` refreshed each 20 Hz tick from the real PX4 `battery_status_v1`
  (or Tello telemetry). `kBatteryReadingUnknown = -1` skips all battery logic (never a false alarm).
- *Failsafe laws* (`batteryFailsafeTick`, control thread, pre-empts plan AND pilot): `≤20% →
  returnToOrigin()` (brisk 0.8 m/s GO to the takeoff point, then land), `≤10% → land-in-place`. Both
  latch; once EITHER latches the supervisor stops re-evaluating (committed to a landing).
- *Manual override (ARCH 11):* Bool `/fmu/in/override` toggles an atomic; `/keyboard/in/raw` drives
  WASD/arrows/space → constant body-FLU velocity (→ENU per tick). Handback abandons the active task
  and forces a fresh VLM re-plan. Precedence: failsafe > manual > autonomy.
- *Backpressure (1.4):* producer uses bounded `try_enqueue` against the fixed cap
  (`kMaxPlanActions = 60`); reject-newest on full, every drop counted + logged; the control thread
  only drains — single-producer SPSC preserved.

**Defects found & fixed during HITL (root cause → fix):**
1. *RTH fired mid-TAKEOFF → drone hung armed, never disarmed.* `returnToOrigin` queued a GO but left
   `FlightState::TAKEOFF`, whose branch streams climb and ignores active tasks, so the RTH GO never
   ran. Fix: force `FlightState::FLIGHT` in `returnToOrigin`.
2. *Land-in-place clobbered by RTH.* The supervisor short-circuited only on `mb_batteryReturn`; after
   a ≤10% land latched (`mb_batteryLand`), the next tick's ≤20% branch still fired RTH and overrode
   it (then the RTH→LAND handoff was skipped → hovered, never disarmed). Fix:
   `if (mb_batteryReturn || mb_batteryLand) return false`.
3. *Land-in-place double-disarm.* The ≤10% branch didn't drain the queue, so the outbound plan's
   leftover `land` re-ran after touchdown. Fix: drain the queue (consumer-side) in that branch.
4. *PX4's own low-battery failsafe hijacked the landing.* On a real drain PX4 hit "Critical battery",
   entered Hold, froze our descent at ~0.34 m and dropped the drone — PX4, not us, ended the flight.
   Fix: `COM_LOW_BAT_ACT=0` in the real-drain test so our FMU is the sole authority.
5. *Land-in-place collided with the car.* `default_car` puts the car at world (6,7), on the +8 m
   outbound path; land-in-place has no obstacle awareness (deferred), so it dropped onto the car.
   Fix: new flat empty world `dependencies/empty.sdf` for the battery tests.
6. *Flood test asserted the wrong bound.* `moodycamel::ReaderWriterQueue(60)` rounds usable capacity
   up to 63 (`ceilpow2(61)-1`); the code was correct (63 enqueued, 37 dropped) — the test's magic
   60/40 was wrong. Fix: assert the real invariants (drops>0, enqueued+drops==injected, ≤ usable cap).
7. *Filter false-fail from tmux scrollback.* A ~2.5-min real-drain run overflows tmux's 2000-line
   pane history and evicts the early `TAKEOFF->FLIGHT` line. Fix: infer "airborne" from `maxDist>3 m`.
8. *Battery drain was deterministic.* Fixed `SIM_BAT_DRAIN` made the failsafe fire at the same patrol
   spot every run. Fix: randomize the drain per run (140–200 s, env-pinnable) so the break-off varies.

Carried over from 2026-08-07: PX4 SITL *does* publish battery (wired the real bridge, not a `-1`
stub); the missing `keyboard_node` publisher (`m_rawKeyEvent`) was constructed (latent null-deref,
overseer-approved).

**Test suite built** (`scripts/test/`, each self-contained: `run.sh` + `filter.sh` + `README.md`;
captures all tmux panes → PASS/FAIL digest). Filters enforce the full safety chain — a landing that
never disarms is a hard FAIL; RTH must actually travel then return home (posENU distance);
land-in-place must stay put:

| folder | proves | SITL result |
|---|---|---|
| `battery/`         | real *random* PX4 drain → our ≤20% RTH from distance → home → disarm; PX4 does not intervene | PASS |
| `battery-rth/`     | forced 18% far → RTH all the way home → land + disarm | PASS |
| `battery-landnow/` | forced 8% far → land-in-place (no return), single disarm, flat ground | PASS |
| `flood/`           | startup command storm → queue bounded (63 usable), reject-newest, nothing lost | PASS |
| `flood-airborne/`  | in-flight storm (producer-role async) absorbed, maneuver not hijacked, land + disarm | PASS |
| `override/`        | Bool engage → autonomy paused, keys fly it; handback → fresh re-plan | PASS |

**Files changed (spec-3 only):**
- Code: `fmu/fmu_node.hpp` (supervisor, RTH, manual override, backpressure, test-only battery
  override + canned plans), `fmu/fmu_node.cpp` (flag parsing), `fmu/fmu_node_base.hpp` (constants),
  `generic_backend/generic_backend_types.hpp` (`kBatteryReadingUnknown`),
  `px4_backend/{px4_backend_base.hpp,.hpp,.cpp}` (real battery bridge),
  `keyboard/keyboard_node.hpp` (constructed the missing publisher).
- Assets: `dependencies/empty.sdf` (new flat, obstacle-free world).
- Tests: `scripts/test/{battery,battery-rth,battery-landnow,flood,flood-airborne,override}/`.
- Docs: `docs/scheduled/2026-08-07-battery-rth-energy-terrain-subsystem.md`, `docs/NOTES.md`
  (design + full HITL log), this report; ROADMAP 6.2/1.4 + poc-tasklist status updated.
- NOT touched: `GenericCommand` byte layout; keyboard raw-publish *logic*; CMake (`px4_msgs`
  already linked); the shared `scripts/test/lib/sim_core.sh`.

**Deferred (documented, not built):** smart RTH feasibility (energy models, 10–15% window, terrain
flat-site landing) → `docs/scheduled/2026-08-07-battery-rth-energy-terrain-subsystem.md`. The POC
ships honest 20%→RTH / 10%→land-in-place with no obstacle awareness on the landing spot.

**Caveats / tunables for the reviewer:** thresholds (20/10), `kManualTeleopVelCmS`, RTH speed
(0.8 m/s), the ≤10% land-vs-flat-site window, and the test drain ranges are placeholders to tune in
sim + on the real Tello. `empty.sdf` loads cleanly in SITL (log: "Gazebo world is ready … world:
empty"). Build: `./build.sh release shared build` links clean (only the pre-existing
`GenericCommand` packed-union warning).
