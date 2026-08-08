# terrain-land test

Terrain / AGL landing check (spec-4 Part B follow-up).

- **Canned plan flag:** `--canned-terrain-land`
- **World:** `rubicon`   **Spawn:** `0,7,3`

## Run
```
cd scripts/test/terrain-land
./run.sh            # brings up the sim; WATCH the drone and note what it does
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest + PASS/FAIL
```

## Expected behavior (watch for this)
- Take off, fly ~2m forward onto the Rubicon terrain, then land.
- KNOWN GAP: landing keys on od.pos.z (height above takeoff origin), not AGL.
- Over sloped ground the drone may disarm above the real ground (a drop).
- Kept short (~2m) so terrain delta is small; a hard drop = the AGL gap, expected.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
