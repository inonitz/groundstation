# approach test

Closed-loop APPROACH toward a canned (synthetic, no-YOLO) detection, then land.

- **Scenario flag:** `--scenario-approach`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (APPROACH activated/sees/reached/lost) — no PASS/FAIL.

## Run
```
cd scripts/test/approach
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Servo drives toward a synthetic detection 3m north / 1m up of spawn.
- `APPROACH reached target ... range~standoff` — reaches the standoff distance.
- If the rig kills the detection mid-approach, expect a CLEAN `APPROACH lost ... FAIL`, not a crash.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
