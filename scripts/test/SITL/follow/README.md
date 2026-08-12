# follow test

FOLLOW a moving person with REAL perception (ONNX seg+depth) and the live VLM. The person slides
left-right in front of the drone. The drone holds a fixed standoff and keeps the person centered. It
backs off when the person comes too close. FOLLOW is position-free: it servos on the bounding box and
depth only, so it works even where odometry gives no target position (the Tello). It never self-
completes; it runs until you re-assess or stop it.

Instance selection is by index. The VLM reads the `index` field printed for each detection in the
`[PERCEPTION]` block and returns `target_index`. FOLLOW resolves that index once at activation to a
label plus a bounding-box center, then tracks by nearest-centroid each tick (detections carry no
stable id).

- **Plan:** VLM-driven (`LAUNCH_VLM=1`, no canned flag). Objective: find the person and follow them.
- **World:** `moving_person` (a `person_walking` mesh on a kinematic left-right trajectory).
- **Spawn:** `0,7,3` (drone faces +X; the person sweeps `y=5..9` at `x=4`, ~4 m ahead).
- **Filter:** milestone digest — capture WHILE it is holding, since FOLLOW does not land on its own.

## Run
```
cd scripts/test/SITL/follow
./run.sh            # brings up the sim; WATCH the drone
# in a SECOND terminal, while it is following:
./filter.sh         # -> captured_panes_log.txt (this folder) + digest
```

## Expected behavior (watch for this)
- `FOLLOW activated target=person`, then a hover-and-acquire moment if the person is not framed yet.
- A steady stream of `FOLLOW target=person range=.. errX=.. errY=..` with `errX`/`errY` driven toward
  0 as the person moves, and `range` held near the standoff.
- When the person walks toward the drone, forward speed goes negative — the drone backs off.
- On a brief loss of the person: it coasts, then hovers; it never fails or lands. It re-locks when the
  person returns.

## Tuning to check in SITL
- **Standoff:** `followStandoffM` in `config/px4_sitl.yaml` (default 2.0 m). Constant fallback is
  `kFollowStandoffM` in `fmu_node_base.hpp`.
- **Forward hold gain:** `kFollowFwdGain` — how hard it drives `range` back to the standoff. Raise if
  it lags the person's depth changes; lower if it surges on noisy depth.
- **Centering:** reuses `kApproachYawGain` (horizontal) and `kApproachVertGain` (vertical). Same
  bbox-centering law as APPROACH.
- **Lost window:** `kFollowLostTimeoutMs` — how long it coasts before hovering on a lost target.

## Edge cases (SITL-verify manually)
- You fly the drone manually off-center → it re-centers on a static person (use the override topic /
  keyboard, then let go).
- Person leaves the frame entirely → coast, then hover; no fail, no land. Re-lock on return.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
