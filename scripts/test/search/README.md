# search test

SEARCH flies a parallel-track (lawnmower) pattern: a straight lane, a short sideways step, the next lane
back the other way, and so on — parallel lanes covering a rectangle at fixed altitude, until the target
comes into view. On a hit it logs full diagnostics (label, confidence, depth, bbox) — that log line is
the operator notification — then lands. ROADMAP 1.1.7.

**This demo is set up to let you watch the WHOLE pattern.** The canned plan targets `person`, which is
NOT in the `default_car` world, so nothing is found early and the pattern runs the full lawnmower to its
timeout. To instead see the found-and-stop path, change the plan's `target_object` to `car`.

**Direction is chosen by the caller.** The `search` command takes `start_heading_deg` (the first lane
heading, relative to current facing: 0=ahead, 90=left, -90=right, 180=behind) and `direction` (cw|ccw,
which side the lanes march across). The VLM sets these from where it expects the target.

- **Canned plan flag:** `--canned-search` (takeoff -> search "person" ccw from ahead -> land)
- **World:** `default_car`   **Spawn:** `0,0,3` (centered so you can watch inside the platform)
- **Filter:** milestone digest — lanes + crosses; PASS-for-detection = a `SEARCH DETECTED ...` line.

## Run
```
cd scripts/test/search
./run.sh            # brings up the sim; WATCH the drone trace the lanes
# in a SECOND terminal, after it lands:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- `SEARCH activated target=person alt=.. startHeadingDeg=0 dir=ccw ...`.
- A straight lane (`SEARCH lane=..`), a short sideways step (`SEARCH cross=..`), then the next lane
  running back the other way — parallel lanes marching across the area.
- Since `person` is absent, it runs to `timeout_sec` and finishes `SEARCH exhausted ... search_exhausted`,
  then `LANDING->STANDBY`.
- Swap the target to `car` and it will `SEARCH DETECTED target=car conf=.. ...` and stop — read `conf`
  to judge a weak/false hit.
- A hit only stops the search if `conf >= kSearchMinConfidence` (0.50). Weaker blobs log
  `SEARCH ignoring weak ...` and the pattern keeps going — this is what stops a phantom detection from
  ending the sweep early.

## Hardware note (DJI Tello)
The reliable core — fly straight and detect — suits the Tello. Lane geometry rides odometry, which
drifts on the Tello; a per-phase timeout advances the pattern regardless, so drift degrades coverage but
does not wedge the search.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
