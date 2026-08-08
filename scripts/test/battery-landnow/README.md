# battery-landnow test

Battery **land-in-place** behaviour (spec-3, ROADMAP 6.2) — the "all of a sudden extremely low,
land NOW" fault. Distinct from RTH: the drone lands where it is, it does NOT fly home.

- **Canned flag:** `--canned-battery-landnow` — fly ~8m straight out, then force a sudden **8%**
  ~15s after reaching FLIGHT (test-only battery override; PX4 drain pinned high).
- Why forced, not drained: with gradual drain the 20% law latches RTH first, so 10% can never
  fire. Land-in-place is by nature a *discrete* crash to critical — so we inject it directly.
- **World:** `empty`
- Why not depict a collision either: run in the **empty** world (no car). land-in-place has **no obstacle awareness** (smart flat-site selection is the deferred subsystem), so in `default_car` it would drop onto the car at world 6,7 -- right on the outbound path.   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/battery-landnow
./run.sh            # takes off, flies out ~8m; ~15s into FLIGHT the battery craters to 8%
./filter.sh         # after it lands: -> captured_battery_landnow_log.txt + digest + PASS/FAIL
```

## Expected (watch the drone)
- Climbs, flies straight out to several metres.
- `TEST battery fault injected -> forcing 8%`, then `FAILSAFE battery 8% -> LAND in place`.
- **Drone descends straight down where it is** (does NOT fly back), then `LANDING->STANDBY
  (force_disarm)` far from spawn.

## PASS requires (all)
- reached FLIGHT; `maxDist > 3m` (flew out); `<=10% LAND-in-place` fired (NOT RTH);
  `landDist > 2m` (landed far from home, i.e. in place); `LANDING->STANDBY` (landed AND disarmed).

## Observed (fill in per run, then hand this whole file back)
- **date:**   **what I saw:**   **filter digest:**   **my comment:**
