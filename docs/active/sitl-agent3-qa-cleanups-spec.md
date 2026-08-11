# Agent 3 — QA / cleanups / roadmap

**Date: 2026-08-11** · Deadline: Wed evening 2026-08-12.

**Mission**: verification tasks and roadmap curation — no big features. Later, verify SLAM changes
don't break the PX4 path.

**REQUIRED reading**: `docs/active/sitl-orchestration-plan.md` (whole plan + LOCKS + commit rules),
then `CLAUDE.md`, `docs/code-guidelines.md`, `docs/writing-style.md`. Study: `fmu_node_base.hpp:82-83`
(YOLO model paths), `perception_runtime.hpp` (seg/depth), `px4_backend.cpp` (the FLIGHT→FAULT fix +
`fmu_node.hpp:638` lost-flight guard), `docs/ROADMAP.md`.

**Your place in the plan**: independent for the QA items; the PX4-SLAM safety check waits on Agent 5.

## Do

1. **YOLO image-quality test** (static scene): measure how detection/classification quality degrades as
   image quality drops, and 384 vs 480, fp32 vs INT4 (`/root/models/vision/` has the variants; current
   is `yolo26n-seg-384.onnx` / `yolo26n-depth-384.onnx`). Note: 384 is baked into the ONNX model — you
   swap by changing the two path constants at `fmu_node_base.hpp:82-83`. **Verdict**: if a smaller INT4
   384/480 model degrades quality materially, do NOT adopt it. Report a numbers table.
2. **P1 disarm verify** (no code — fix already in `px4_backend.cpp`): run a SITL flight, inject
   `commander disarm --force` in the PX4 console mid-flight, capture the logs, confirm
   FLIGHT→FAULT→reconcile STANDBY→task abort. Hand the logs to the manager/human to verify.
3. **ROADMAP notes** (`docs/ROADMAP.md` — lock it): schedule (a) the **prompt-trim** (the GBNF now
   enforces JSON shape / thought-first / verb enum / takeoff-first, so the OUTPUT-FORMAT block + the
   dynamic-prompt "MUST start with takeoff" line are redundant — but it only speeds the first plan, so
   it is not urgent); (b) the **rotate/drift** item, reframed: the airframe drifts in space, so rotation
   testing is blocked on SLAM stabilization (Agent 5), not a yaw fix.
4. **Later** (after Agent 5 lands SLAM): verify the SLAM/odometry changes don't break the PX4/SITL path
   (run a normal SITL VLM mission, confirm takeoff/approach/orbit still pass).

## Locks

`docs/ROADMAP.md`, `docs/NOTES.md` (short holds). Your test scripts are yours alone.

## Constraints

No git writes — suggest `agent3: <item>`. Prose per `docs/writing-style.md`.

## Report
_(append findings / the YOLO numbers table / P1 logs summary below)_
