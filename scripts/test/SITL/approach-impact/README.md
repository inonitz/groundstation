# approach-impact test

Verifies the APPROACH motion-gate (spec 2026-08-07-spec-1 §C, ROADMAP 6.4). A real collision reads
a plausible range off the impact frame and, before this spec, declared `approach_ok` while yaw-rate
spiked to ~6.9 and vertical velocity to ~-1.75 with altitude collapsing 0.99->0.02 m in ~1 s. The
gate now requires nominal motion before trusting "reached"; a collision instead raises
`INTERRUPT (reason=approach_impact)`.

- **Canned flag:** `--canned-approach-impact`
- **World:** `empty`   **Spawn:** `0,7,3`
- **Filter:** Auto PASS/FAIL.

## How it's triggered
`--canned-approach-impact` runs the canned synthetic APPROACH rig (deterministic, no real
perception) and forces the motion-gate off-nominal. The rig drives to the standoff, "reached" is
treated as an impact, and the FMU raises `approach_impact` instead of `approach_ok`. The queued
land then runs, so the flight ends with `LANDING->STANDBY`. Empty world so only the rig detection
is present.

## PASS condition
`APPROACH activated` appears, at least one `INTERRUPT (reason=approach_impact)` (or
`emergency_boundary`), and **no** `task complete status=approach_ok`.

## Run
```
cd scripts/test/approach-impact
./run.sh
./filter.sh         # -> PASS/FAIL
```

## Observed (fill in per run)
- **date:**
- **what I saw:**
- **filter digest:**
