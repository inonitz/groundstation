# approach-real test

Same APPROACH servo, but REAL perception (ONNX seg+depth) vs the car in the world.

- **Canned plan flag:** `--canned-approach-real`
- **World:** `default_car`   **Spawn:** `0,7,3`
- **Filter:** milestone digest (APPROACH sees label=car ...) — no PASS/FAIL.

## Run
```
cd scripts/test/approach-real
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- Real ONNX models detect the 'car' (COCO label) — `APPROACH sees ... first label=car`.
- Servo closes to the standoff distance: `APPROACH reached target=car range=..`.
- Skips only the VLM planner, not vision. Ends with `LANDING->STANDBY`.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
