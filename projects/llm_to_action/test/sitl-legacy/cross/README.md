# cross test

Cross pattern: fwd/left/back/right 1m, returning to start after each leg (FLU sanity).

- **Scenario flag:** `--scenario-cross`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (per-leg GO activated/complete) — no PASS/FAIL.

## Run
```
cd scripts/test/cross
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Four legs: forward, left, back, right — each re-anchored to actual position and returned to start.
- Two `GO` events per leg (out + back); path is a plus/cross, not drifting.
- Ends with `LANDING->STANDBY`.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
