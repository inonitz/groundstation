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
