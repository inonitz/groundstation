# forward test

Forward hop (FLU-frame sanity): takeoff, GO ~1m forward, land.

- **Canned plan flag:** `--canned`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (GO activated/complete, STANDBY) — no PASS/FAIL.

## Run
```
cd scripts/test/forward
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Takeoff, one ~1m hop straight FORWARD (+x ENU at yaw 0), then land.
- `GO activated` then `GO complete dist~1.0`.
- Gentle touchdown -> `LANDING->STANDBY`.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
