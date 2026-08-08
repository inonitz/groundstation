# land-flare test

LAND flare-taper regression (spec-4 Part B).

- **Canned plan flag:** `--canned-land-flare`
- **World:** `default_car`   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/land-flare
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest + PASS/FAIL
```

## Expected behavior (watch for this)
- Descent visibly SLOWS near the ground (flare), not a constant plunge.
- vLand tapers from -0.5 toward -0.12; reaches LANDING->STANDBY.
- Touchdown is gentle (flat world: altENU == real AGL).

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
