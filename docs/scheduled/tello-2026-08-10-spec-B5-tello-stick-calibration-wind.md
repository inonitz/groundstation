# B5 — Tello stick→m/s calibration + wind correction

**Status:** scheduled / not started. **Created:** 2026-08-10. **Revised:** 2026-08-09 (session review —
see Revision log — **resolves a real contradiction in the original spec**). **Branch:** none needed —
same reasoning as B2/B4. **Owner:** operator + agent. **Depends:** B4 (bring-up).
**ROADMAP:** 2.3.1, 2.3.5.

## Objective
Make Tello `rc` predictable. Build the velocity(m/s)->stick(%) curve so any position control (and B3's
return) is metric, and add active wind/prop-wash correction so it holds station indoors.

## Grounding (verified against this checkout, 2026-08-09 — resolves a contradiction)
- **The original spec's "land via the runtime-config mechanism (9.14), not new constexpr" is not
  achievable as written — 9.14 doesn't exist yet.** `docs/ROADMAP.md:220` confirms
  `9.14 ... [ ] [GATE real-Tello]` — unbuilt. `docs/scheduled/2026-08-08-runtime-drone-config-constants.md`
  is a design sketch only (a `DroneConfig` struct populated from a profile file, selected via CLI
  arg/env var) — grepped the whole repo for `DroneConfig`/`runtime*config*`, zero implementation exists
  anywhere. **Decision (resolves the contradiction): B5 ships an interim `constexpr`, matching every
  other tuning value in this codebase** (`docs/code-guidelines.md` naming: `kPascalCase`) — the same
  pattern already used for `kTelloMaxSpeedMps`/`kTelloStickMax`/`kTelloMaxYawRateRadps` below, which B5's
  curve replaces. Leave a comment noting it should re-home into 9.14's profile mechanism once that
  lands, but do not build any part of 9.14 as part of B5 — that would turn a "lowest priority, only if
  time allows" item into an unscoped one.
- **The conversion B5 replaces is a bare linear scale, no calibration at all today.**
  `tello_backend.cpp:151`: `set_body_velocity` -> `setRc(flu_to_rc(flu, yawrate_to_stick(yawspeed)))`.
  `mps_to_stick()` (`tello_backend_base.hpp:78-84`):
  ```cpp
  static inline i32 mps_to_stick(f32 mps) {
      i32 s = __scast(i32, std::lroundf(mps / kTelloMaxSpeedMps * __scast(f32, kTelloStickMax)));
      if (s >  kTelloStickMax) return  kTelloStickMax;
      if (s < -kTelloStickMax) return -kTelloStickMax;
      return s;
  }
  ```
  `stick = round(mps / kTelloMaxSpeedMps * 100)`, clamped to +-100 — literal linear scale, no per-axis
  asymmetry, no curve. The three constants it depends on (`tello_backend_base.hpp:45-48`, verified 2026-08-10 --
  was cited as :61-67, stale:
  `kTelloMaxSpeedMps = 1.0f`, `kTelloStickMax = 100`, `kTelloMaxYawRateRadps = M_PI`) are explicitly
  commented as "a first estimate... plan: hardware calibration" — this is exactly what B5 replaces.
- **Hover has no existing drift-correction hook to extend — this is a smaller precedent than "extend
  existing feedback" implies, but not zero.** Control is mostly open-loop (GO uses only position error,
  no velocity feedback). The one existing velocity-feedback precedent is APPROACH's lateral damping
  (`fmu_node.hpp:841-844`): `lat = lateralComponent(od.vel, fwdDir)` (measured velocity's cross-track
  component), subtracted from commanded `velEnu` scaled by `kApproachLateralDamp = 0.5f`
  (`fmu_node_base.hpp:116`). "Hover" today is just `set_velocity(0,0,0)` (`fmu_node.hpp:1457`) — no
  correction at all for Tello, which (unlike PX4) has no onboard position hold. B5's wind-hold is a new
  feedback loop modeled on APPROACH's damping pattern, not an extension of an existing hover hook (none
  exists).
- `scripts/tello/` confirmed absent (matches B4's finding) — no existing calibration-data file anywhere
  in the repo either (only a TODO-style note in `docs/tello_backend_notes.md:19`).

## Scope
- **In:** a calibration procedure that maps commanded stick % to measured m/s (from telemetry
  `vgx`/`vgy`), the resulting curve (replaces the linear `mps_to_stick`/its inverse), and a closed-loop
  drift correction on hover (new, modeled on APPROACH's `lateralComponent`/damping pattern — see
  Grounding). Values land as **interim `constexpr`** (or a small lookup table, `kPascalCase` per
  `docs/code-guidelines.md`), explicitly noted for later migration into 9.14's profile mechanism once
  that lands — not blocked on it.
- **Out:** the runtime-config plumbing itself (9.14, its own scheduled spec, not touched here).

## Files
- Modify: `source/llm_to_action/tello_backend/tello_backend_base.hpp` (replace/augment
  `kTelloMaxSpeedMps` etc. with the calibrated curve constants — **coordinate with B3 via `docs/LOCKS.md`,
  both touch this file**).
- Modify: `source/llm_to_action/tello_backend/tello_backend.cpp` (`mps_to_stick`/inverse using the curve;
  new hover-drift correction).
- Create: `scripts/tello/calibrate_stick.py` or similar (offline curve-fit from a recorded flight, mirrors
  B2's Python calibration script pattern).

## Tests to create
- **[AUTO / desk]** replay a captured flight to validate the stick->m/s mapping offline (ROADMAP 2.3.6's
  replay-fixture approach, same as B4).
- **[HUMAN]** wind/prop-wash hold — real indoor flight.

## Acceptance
`rc` commands produce m/s within tolerance of the curve; hover drift stays bounded indoors.

## Change-impact (per `docs/code-guidelines.md`)
- **What this changes:** replaces a linear, uncalibrated stick mapping with a measured curve — this
  changes real Tello flight behavior (commanded m/s now maps to a different stick % than before), but
  only affects the Tello backend; PX4/SITL is untouched.
- **Breaks existing behavior:** intentionally changes Tello stick output values — that's the point. No
  SITL test is affected (PX4-only).
- **Tests that re-run as-is:** all 20 SITL scenarios (A1).
- **Tests that are new:** the two listed above.

## Agent notes
Gated on B4 and on hardware time. Lowest priority for tomorrow — only reachable if B1->B4 go smoothly.
Coordinate `tello_backend_base.hpp` with B3 via `docs/LOCKS.md` — both specs touch it; per the protocol,
take the lock right before your edit, release right after, don't run both edits concurrently unattended.

## Revision log
- 2026-08-09: resolved a real contradiction — the original spec said values land via the 9.14
  runtime-config mechanism, but 9.14 is unbuilt (design doc only, zero implementation). Decided B5 ships
  an interim `constexpr` like everything else in this codebase, noted for later migration, rather than
  silently blocking on unscoped work. Confirmed the conversion it replaces is a bare linear scale with
  explicitly-placeholder constants. Clarified hover has no existing drift-correction hook (APPROACH's
  lateral damping is the closest pattern to model from, not something to extend directly). Flagged the
  `tello_backend_base.hpp` lock coordination needed with B3.
