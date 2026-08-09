# orbit test

ORBIT the car with REAL perception (ONNX seg+depth). Flies a full circle around the car, keeping it in
the camera the whole way (that framing is the survey), then lands. ROADMAP 1.1.6.

How it avoids the wobble the earlier version had: at the start it medians a few depth reads into ONE
fixed car position (the circle center). After that the circle is flown from odometry around that fixed
point, so the flight path never reacts to the jittery depth and cannot oscillate. The camera turns
separately (a gentle image-centering) to keep the real car in view, and if the center estimate was a
bit off, that camera tracking still keeps the car framed.

- **Canned plan flag:** `--canned-orbit` (takeoff -> orbit car, 360 deg, ccw, 30 cm/s -> land)
- **World:** `default_car`   **Spawn:** `0,6,3`
- **Filter:** milestone digest — PASS = `ORBIT center locked ...` then `ORBIT complete ... orbit_ok`.

## Run
```
cd scripts/test/orbit
./run.sh            # brings up the sim; WATCH the drone
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- `ORBIT activated ...`, then it hovers a moment while it fixes the center: `ORBIT center locked
  target=car R=.. centerENU=(..)`.
- Then it flies one smooth circle of radius R around that point, camera staying on the car. Diagnostics
  show `swept` climbing to ~6.28 and `dist` holding near `R`.
- Ends with `ORBIT complete ... orbit_ok`, then `LANDING->STANDBY`.

## Known tuning to check in SITL
- **Direction sign** (`m_orbitDir`): if cw/ccw circles the wrong way, flip the sign in the ORBIT dispatch.
- **Center accuracy**: the center is the medianed startup depth and then stays FIXED. The path is flown
  from odometry only; vision never touches the geometry (a slow "drift correction" was tried and reverted
  -- it fed vision back into the path and dragged the center away). Odometry drift over one short orbit is
  the accepted trade for a circle that cannot wobble.
- **Camera aim** is driven from odometry now (point at the locked center), not from the bbox — that is
  what killed the earlier hard-yaw jitter. `kOrbitAimTrimGain` is a small vision nudge onto the real car
  on top of it; raise it if the car sits off-centre, lower it if the camera twitches.
- `kOrbitRadialGainHz` (how hard it holds the radius) and `kOrbitYawGain` (how fast it settles onto the
  center look-angle) — sweep if the radius drifts or the aim lags.

## Edge cases (SITL-verify manually)
- Target never seen at all -> after the acquire window: `ORBIT never locked ... orbit_lost_failed`.

## Hardware note (DJI Tello)
Uses odometry for the ~20-30 s circle. That is short enough that odometry drift stays small (the concern
with odometry is long flights, not a bounded maneuver). Expect a slightly looser circle than SITL.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
