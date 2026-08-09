# B4 — Tello bring-up + position-free demos (T1 / T2)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Branch:** feature-slam-tello. **Owner:** operator + agent.
**Depends:** feature commit landed. **ROADMAP:** 2.3. **Lock:** `scripts/tello/` + Tello run config; no shared FMU.

## Objective
Fly the real drone tomorrow with what needs no position. This is the guaranteed hardware deliverable
if SLAM slips. See `docs/tello_backend_notes.md` for ports/init/keepalive/calibration facts.

## Scope
- **In:** Tello run config (real camera resolution), a bring-up smoke test
  (`command`→`streamon`, 16-field state parse, camera decode, 30 Hz `rc` keepalive beats the 15 s
  auto-land), and two demos — **T1** yaw-scan & describe, **T2** safety stack (failsafe / override /
  emergency stop).
- **Out:** APPROACH/ORBIT/SEARCH/GO — they drift without position (that path is B1→B3→B5).

## Tests to create
- **[AUTO / desk]** record a real flight's input/telemetry/frames once, replay as a fixture to assert
  the 16-field parse, odometry integration, and camera decode with no re-flying (ROADMAP 2.3.6).
- **[HUMAN]** the flights themselves (T1, T2) — real hardware, not automatable.

## Acceptance
Clean bring-up on hardware; T1 and T2 fly; the replay fixture guards the parser/odometry off-desk.

## Agent notes
Watch the two known gremlins from the Tello notes: UDP bind collision (`SO_REUSEADDR`) and the
`ReceiveResponse` timeout. Batteries last ~10–13 min — charge several.
