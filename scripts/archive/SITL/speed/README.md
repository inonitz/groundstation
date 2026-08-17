# speed test

Speed sweep: forward 1m + return at LOW (15cm/s) then HIGH (80cm/s) speed.

- **Canned plan flag:** `--canned-speed`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (GO speed=..) — no PASS/FAIL.

## Run
```
cd scripts/test/speed
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Forward+return at speed~0.15, then again at speed~0.80 (see `GO activated ... speed=`).
- Check whether path curvature/overshoot scales with speed.
- Ends with `LANDING->STANDBY`.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
