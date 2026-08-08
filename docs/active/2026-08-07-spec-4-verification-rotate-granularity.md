# Spec 4 — Verification tests + ROTATE granularity fix

**Status:** unassigned (for a spawned session). **ROADMAP:** 1.1.2 (ROTATE correctness), 9.11 (LAND
flare verification).
**Owns (edits):** `source/llm_to_action/fmu/fmu_node.hpp` (ROTATE branch + members + canned plans),
`.../fmu/fmu_node_base.hpp` (constants), a log-check test/script. Touches only the ROTATE code region
of the movement handler + new canned-plan constants — coordinate the shared canned-plan infra with
Specs 1 & 2 (whoever lands first owns the harness; others extend it).

> **Repo conventions (start-cold):** `rtk read/grep/ls` only (native Read/Grep/Glob forbidden by
> `CLAUDE.md`); edit via python heredocs with `assert s.count(old)==1`. **Never touch the
> `GenericCommand` byte layout.** No full builds; human does build + SITL.

## Part A — ROTATE granularity fix
> **DONE 2026-08-07 by the overseeing session — implemented directly (accumulated-angle law now
> in `fmu_node.hpp`). SKIP Part A; do Part B (tests) only.** Design retained below for reference.
**Bug:** the current ROTATE law (landed 2026-08-07) turns to a *target heading* by the *shortest*
path. Angles `< 180°` are correct/granular; `>= 180°` go the wrong way (`270° cw` → `90° ccw`) and
`360°` completes instantly. **Fix:** integrate actual rotation in the commanded direction, stop at the
full magnitude.

Current code to replace:
- Member (fmu_node.hpp ~line 962): `f32 m_targetYaw{0.0f};` → replace with
  `f32 m_rotateRemainingRad{0.0f}; f32 m_rotatePrevYaw{0.0f}; f32 m_rotateDir{1.0f};`
- Dispatch `case CommandID::ROTATE:` (~line 710): instead of computing `m_targetYaw`, set
  `m_rotateRemainingRad = fabs(r.angle_deg) * kPi / 180.0f;`
  `m_rotateDir = r.cw_or_ccw ? -1.0f : 1.0f;`  (cw decreases yaw; ENU is CCW+)
  `m_rotatePrevYaw = od.yaw;`
- Movement branch `else if (id == CommandID::ROTATE)` (~line 486): each tick
  ```
  f32 dYaw = od.yaw - m_rotatePrevYaw;
  while (dYaw >  kPi) dYaw -= 2.0f*kPi;   // wrap the per-tick delta
  while (dYaw < -kPi) dYaw += 2.0f*kPi;
  m_rotatePrevYaw = od.yaw;
  m_rotateRemainingRad -= m_rotateDir * dYaw;   // progress made in the commanded direction
  if (m_rotateRemainingRad <= kRotateCompletionRad) { STOP; completeCurrent("rotate_ok"); }
  else { yawRate = clamp(m_rotateDir * kRotateYawGainHz * m_rotateRemainingRad, ±kRotateMaxYawRate);
         set_velocity({0,0,0}, yawRate); }
  ```
This honors direction + full magnitude: `270° cw` turns 270° cw; `360°` does a full turn. Keep the
existing parser + dispatch schema (`direction`+`angle_deg`) — only the law + members change.
Edge: clamp `angle_deg` to a sane max (e.g. 720°) at parse to bound runaway. Update the ROADMAP 1.1.2
note when done.

## Part B — LAND flare + ROTATE log tests (the user's exact ask)
No automated tests exist for either. Build **log-based SITL integration tests** using the FMU's
existing canned-plan mechanism — the user's stated approach: *hardcoded initial command → run → assert
the logs are correct.*

Existing infra to reuse (fmu_node.hpp): `injectCannedPlan()` + `kCannedPlanJson` (~line 857) and the
`--canned*` CLI flags / `simenv_llm.sh` selectors already used for APPROACH.
1. Add canned plans:
   - `kCannedRotatePlanJson`: `[{takeoff},{rotate 90 cw},{rotate 200 ccw},{land}]` (exercises a
     <180 and a >=180 turn).
   - `kCannedLandFlarePlanJson`: `[{takeoff},{land}]` from the 2 m climb (exercises the flare taper).
   - A CLI flag each (mirror `--canned-approach`).
2. Assertion (a small script scraping the SITL log, or an extension of the canned-plan test harness):
   - ROTATE: for each turn, `ROTATE activated ... targetYaw/remaining` then `ROTATE complete
     yawErr<kRotateCompletionRad`; confirm the 200° turn actually sweeps ~200° in the CCW direction
     (measured yaw delta), proving Part A.
   - LAND flare: during `FlightState::LANDING`, the streamed `vLand` (add it to the throttled log if
     not present) **monotonically rises toward `kFlareTouchdownVelEnu`** as altitude drops below
     `kFlareStartAltEnu`, ending in `land_ok` — not a constant `-0.5`.

Keep it a thin, deterministic log check; no new heavy framework.

## Out of scope
Simpson-odometry SITL test, latency/IO record-replay harness (Tier 4, separate). GO/ORBIT/SEARCH
tests (Spec 2 owns those).

## Implementation report (session: append below, do not edit above)
<!-- ROTATE law change + verification that 270/360 now behave; canned plans added; log-assertion approach; SITL results -->


### Session report — Part B (2026-08-07, session `spec4-partB`)

**Scope:** Part B only. Part A (accumulated-angle ROTATE law + LAND flare taper) was already
landed by the overseeing session — left untouched. `GenericCommand` byte layout untouched.

**What landed:**
- `fmu_node.hpp` — two canned plans mirroring `injectCannedApproachPlan()`:
  - `injectCannedRotatePlan()` → `[takeoff, rotate cw 90, rotate ccw 200, land]` (a <180 and a
    >=180 turn, opposite directions → proves the law sweeps full magnitude/direction).
  - `injectCannedLandFlarePlan()` → `[takeoff, land]` (climb to ~2 m then land → exercises the flare).
  - `start()` gained `useRotatePlan` / `useLandFlarePlan` params + dispatch + mission log fields.
  - LANDING branch now streams `[FMU_NODE_DIAGNOSTICS] LAND altENU=.. vLand=..` (throttled 250 ms)
    — `vLand` was computed but never logged, so the flare was previously un-observable from logs.
- `fmu_node.cpp` — `--canned-rotate` / `--canned-land-flare` arg parsing → passed into `start()`.
- `simenv_llm.sh` — `rotate` and `land-flare` `PLAN_MODE` selectors + header docs + a pane-capture hint.
- `scripts/debug_sim_logs.sh` (new, portable awk — runs on mawk) — captures ALL tmux panes into
  `captured_panes_log.txt`, then filters + asserts from that same file:
  - `rotate`: unwraps the throttled `measYaw` stream per turn, asserts each turn reports
    `ROTATE complete` and that the net swept angle matches the commanded magnitude AND direction
    (±15° tol). Catches the exact Part-A bug (a 200° ccw collapsing to −160° shortest-path).
  - `land`: asserts `vLand` is monotonic non-decreasing, tapers from `-0.5` toward
    `kFlareTouchdownVelEnu` (−0.12), is not near-constant, and reaches `LANDING->STANDBY`.

**Assertion design:** thin, deterministic, no framework. Keys on the FMU's own `RCLCPP_INFO`
tags; the script captures every pane to `captured_panes_log.txt` and checks it in one shot.

**Verification done (no full build — human builds + runs SITL):**
- Static: `rtk grep` confirms all symbols landed and `GenericCommand` layout is unchanged.
- Checker self-test against 4 hand-generated fixtures (good + regression per mode):
  rotate_good→PASS, rotate_bad(200° wrong-way)→FAIL, land_good→PASS, land_bad(constant −0.5)→FAIL.
  All four exit codes correct.

**Operator runbook (human-in-the-loop — the checker assists, you confirm what you saw):**
1. Build, then `scripts/simenv_llm.sh rotate` (or `land-flare`).
2. Watch the loop: first turn ~90° **cw**, second ~200° **ccw** the long way (not 160° short);
   for land-flare, descent visibly slows near the ground.
4. `scripts/debug_sim_logs.sh rotate` (or `land`) — grabs every pane to `captured_panes_log.txt`,
   prints the filtered digest + PASS/FAIL.

**LOCKS:** short holds on `fmu_node.hpp` and `docs/ROADMAP.md` (acquired/released); added + released
rows for `fmu_node.cpp` and `scripts/simenv_llm.sh`. All released.

**SITL results:** ROTATE **PASS** (real run 2026-08-07): 90 cw swept -86 deg, 200 ccw swept
+195 deg (long way CCW, not shortest-path) — Part A confirmed. Needed a `capture-pane -J` fix
(pane-width truncation was mangling `measYaw`) + end-yaw reconstruction from `ROTATE complete
remainRad` to close the throttled-sampling gap. LAND-flare **PASS** (real run 2026-08-07): vLand held -0.500 above the flare start, then tapered
-0.437 -> -0.351 -> ... -> -0.139 toward touchdown as altitude dropped below 0.6 m, reaching
STANDBY. Both Part B tests green; ROADMAP 1.1.2 + 9.11 flipped to verified.


### Follow-up — terrain-land AGL exposure test (2026-08-07)

**Finding (from land-flare review):** landing keys on `d = od.pos.z` ([fmu_node.hpp:388](../../source/llm_to_action/fmu/fmu_node.hpp)),
i.e. height above the EKF/takeoff origin, NOT above-ground-level. Flare start (0.6 m) and contact
(0.1 m) thresholds assume `od.pos.z == AGL`. That holds only on flat ground; the old flat
car world (`default_car.sdf`) hid it. Over real terrain, landing over ground at a different height than takeoff mis-triggers
(force_disarm in mid-air over a rise, or a hard drop over a dip). Flare curve is also *linear*
(constant decel), not faster near the ground.

**Test added:** `terrain-land` sim mode runs the real Rubicon terrain world (`rubicon.sdf`, the
OpenRobotics Fuel Rubicon model — genuine uneven elevation). New canned plan `--canned-terrain-land` = takeoff -> go 10 m forward -> land, so
the landing spot sits over different-elevation ground than takeoff. Wiring: `injectCannedTerrainLandPlan()`
(fmu_node.hpp), `--canned-terrain-land` (fmu_node.cpp), `simenv_llm.sh terrain-land` (world switched to
rubicon via a new `WORLD_NAME` var; other modes default to the flat `default_car` world). It also
spawns at the flat Rubicon takeoff spot `PX4_GZ_MODEL_POSE=7,3,0` and flies forward onto the uneven ground.

**How to read it:** `scripts/simenv_llm.sh terrain-land`, watch the descent, then `scripts/debug_sim_logs.sh land`.
Unlike the flat land-flare (which PASSes), here a **FAIL / no-STANDBY / plateaued altENU is the expected
signal** that the drone stopped at the wrong height — i.e. the AGL gap is real and needs a rangefinder/
terrain-relative altitude to fix (out of Part B scope; a follow-up item).

**Caveat:** if the drone spawns under/through the Rubicon terrain at `7,3,0`, bump the `SPAWN_POSE`
z in `simenv_llm.sh`. AGL fix itself (distance-sensor plumbing) is not implemented here.
