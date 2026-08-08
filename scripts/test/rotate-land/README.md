# rotate-land test

ROTATE granularity regression (spec-4 Part B).

- **Canned plan flag:** `--canned-rotate`
- **World:** `default_car`   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/rotate-land
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest + PASS/FAIL
```

## Expected behavior (watch for this)
- First turn ~90 deg CLOCKWISE.
- Second turn ~200 deg COUNTER-clockwise the LONG way (not 160 deg shortest-path).
- Each turn logs `ROTATE complete`; net swept angle matches magnitude + direction.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
