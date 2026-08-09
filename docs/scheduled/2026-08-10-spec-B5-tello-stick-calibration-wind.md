# B5 — Tello stick→m/s calibration + wind correction

**Status:** scheduled / not started. **Created:** 2026-08-10. **Branch:** feature-slam-tello. **Owner:** operator + agent.
**Depends:** B4 (bring-up). **ROADMAP:** 2.3.1, 2.3.5; profile lands via `2026-08-08-runtime-drone-config-constants.md` (9.14).

## Objective
Make Tello `rc` predictable. Build the velocity(m/s)→stick(%) curve so any position control (and B3's
return) is metric, and add active wind/prop-wash correction so it holds station indoors.

## Scope
- **In:** a calibration procedure that maps commanded stick % to measured m/s (from telemetry `vgx/vgy`),
  the resulting curve, and a closed-loop drift correction on hover. Values land as the Tello profile
  in the runtime-config mechanism (9.14), not new `constexpr`.
- **Out:** the runtime-config plumbing itself (its own scheduled spec).

## Tests to create
- **[AUTO / desk]** replay a captured flight to validate the stick→m/s mapping offline.
- **[HUMAN]** wind/prop-wash hold — real indoor flight.

## Acceptance
`rc` commands produce m/s within tolerance of the curve; hover drift stays bounded indoors.

## Agent notes
Gated on B4 and on hardware time. Lowest priority for tomorrow — only reachable if B1→B4 go smoothly.
