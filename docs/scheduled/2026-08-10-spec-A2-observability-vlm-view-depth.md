# A2 — Observability: VLM view, depth map, prompt/response log

**Status:** scheduled / not started. **Created:** 2026-08-10. **Branch:** feature-llm-driver (SITL showcase).
**Depends:** A1 (runner, soft). **ROADMAP:** new (debug tooling). **Lock:** small `fmu`/`perception_runtime` hooks — coordinate with A3 on `fmu_node.hpp`.

## Objective
Kill the human-debuggee problem: today nobody can see what the model sees. Publish the annotated
camera frame (boxes + labels) and a depth colormap to ROS topics, and log every VLM prompt+response
to a file, so a failed run is inspectable instead of a mystery.

## Scope
- **In:** annotated-frame + depth-colormap publishers (from `PerceptionRuntime` / a small viz node),
  per-cycle prompt+response JSON log, a Foxglove/rviz layout committed under `dependencies/`.
- **Out:** a full web dashboard. Topics + a log file + a layout is enough.

## Files
- `perception_runtime.hpp` (publish colormap / annotated image), VLM planner (append prompt+response
  to a log), `dependencies/foxglove_layout.json` (new).

## Tests to create
- **[AUTO]** assert both image topics publish at the expected rate during a canned run.
- **[AUTO]** assert the prompt/response log file grows one valid JSON record per reassess cycle.
- **[HUMAN]** one-time visual spot-check that boxes/labels/colormap look right.

## Acceptance
In a sandbox run, Foxglove shows the annotated frame + depth colormap live, and the prompt/response
log has one record per cycle.

## Agent notes
Depends on A1 for the record/replay bag but can start against a live sim. Serialize the `fmu_node.hpp`
touch with A3 via `LOCKS.md`.
