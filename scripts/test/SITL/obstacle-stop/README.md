# boundary test

Verifies the velocity-scaled emergency boundary (spec 2026-08-07-spec-1 §B, ROADMAP 6.1). Each
FLIGHT tick the FMU computes `trig = kBoundaryBaseM + kBoundaryVelScale * speed` and reads the
nearest detection depth via `nearestDepthM`. If a detection is inside `trig` it stops and raises
`INTERRUPT (reason=emergency_boundary)`. A snapshot older than `kBoundaryMaxSnapshotAgeMs` is
treated as unknown and must NOT trip it.

- **Scenario:** `--scenario-obstacle-stop`
- **World:** `empty`   **Spawn:** `0,7,3`
- **Filter:** Auto PASS/FAIL.

## How it's triggered
`--scenario-obstacle-stop` takes off, then injects a synthetic close obstacle (~0.4 m, below the 0.6 m
base trip distance) for a ~1.5 s burst once airborne, through the same atomic snapshot path real
perception uses. No real object in the world is needed; `empty` world keeps real detections from
competing. After the burst the drone hovers (no VLM) -- watch the trip, then Ctrl-C and filter.

## PASS condition
At least one `INTERRUPT (reason=emergency_boundary)`, preceded by a `BOUNDARY nearest=...` line.

## Run
```
cd scripts/test/boundary
./run.sh
./filter.sh         # -> PASS/FAIL
```

## Observed (fill in per run)
- **date:**
- **what I saw:**
- **filter digest:**
