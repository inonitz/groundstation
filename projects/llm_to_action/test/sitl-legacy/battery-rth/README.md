# battery-rth test

Battery **return-to-origin** behaviour (spec-3, ROADMAP 6.2) — the REAL RTH the plain `battery/`
test couldn't show (there the drone sat at origin, so "fly home" was a no-op).

- **Scenario:** `--scenario-battery-rth` — fly ~8m straight out, then force **18%** ~15s after
  reaching FLIGHT (test-only battery override; PX4 drain pinned high so only the forced value fires).
- **World:** `empty`   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/battery-rth
./run.sh            # takes off, flies out ~8m; ~15s into FLIGHT the battery is forced to 18%
./filter.sh         # after it lands: -> captured_battery_rth_log.txt + digest + PASS/FAIL
```

## Expected (watch the drone)
- Climbs, flies straight out to several metres.
- `TEST battery fault injected -> forcing 18%`, then `FAILSAFE battery 18% -> RETURN to origin`.
- **Drone flies all the way back toward spawn**, then `LANDING->STANDBY (force_disarm)` at origin.

## PASS requires (all)
- reached FLIGHT; `maxDist > 3m` (genuinely flew out); `<=20% RETURN` fired (not land-in-place);
  `landDist < 1.5m` (RTH actually brought it home); `LANDING->STANDBY` (landed AND disarmed).

## Observed (fill in per run, then hand this whole file back)
- **date:**   **what I saw:**   **filter digest:**   **my comment:**
