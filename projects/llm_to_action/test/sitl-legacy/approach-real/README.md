# approach-real test

Same APPROACH servo, but REAL perception (ONNX seg+depth) vs the car in the world.

- **Scenario flag:** `--scenario-approach-real`
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
- Servo closes to the standoff distance (now 4.0 m, raised from 3.0): `APPROACH reached target=car range=..`.
- Skips only the VLM planner, not vision. Ends with `LANDING->STANDBY`.
- Motion-gate (spec 2026-08-07-spec-1 6.4): if the servo collides on a spiky frame, "reached" is
  rejected -- instead of `approach_ok` you see `APPROACH reached ... motion off-nominal ... impact
  interrupt` and `INTERRUPT (reason=approach_impact)`.
- Looming backstop (2026-08-08): SITL depth over-reads range ~2 m close up, so a smooth over-close
  can drive the drone into the car with no motion spike. The boundary now also trips on how much of
  the frame the car fills: `BOUNDARY looming fill=.. > 0.40 ... -> interrupt` +
  `INTERRUPT (reason=emergency_boundary)`. Seeing this instead of a crash is the CORRECT outcome --
  it stops the drone ~1 m short and re-plans.
- Verbose diagnostics: the log now streams `APPROACH ... rawRange=.. medRange=.. budget=.. trav=..
  rem=.. fill=..` and `BOUNDARY nearest=.. trig=.. loomFill=..` each tick. Use these to see the
  depth over-read directly -- rawRange/medRange stay high while the drone is physically at the car.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
