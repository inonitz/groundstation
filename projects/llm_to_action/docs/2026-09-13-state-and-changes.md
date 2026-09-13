# llm_to_action — state and changes (2026-09-13)

This is the current state of the subproject. It lets the next person continue without re-finding
what is already known. It is committed with the changes it describes.

## Status
Parked behind integration_harden2 (owner-ruled 2026-09-12). harden2 is the active demo successor.
llm_to_action is committed as-is after more than a week uncommitted. It resumes later: re-evaluate,
settle the architecture, write real code, measure. Fusion path: bring harden2 perception in, likely
rewritten to C++/C for the embedded box, then fuse the two.

## The one finding that matters
The drone hits the car. The planner is fine. The approach fails on world-grounding.
- Loom guard at `source/fmu/fmu_node.hpp:826` interrupts when a detection's bounding box fills more
  than `kBoundaryLoomFillFrac` = 0.28 of the frame. Near the car, the car fills the frame, so the
  guard fires on the target itself. Root cause: monocular depth is unreliable up close.

## Changes in this commit (previously uncommitted)
- `test/lib/sim_core.sh`: default VLM model is Qwen3-VL-4B Q4_K_M. `VLM_MODEL`/`VLM_MMPROJ` override,
  falling back to 2B.
- `source/fmu/fmu_node.hpp:2244`: APPROACH auto-land fires only when the task queue is empty. Multi-step
  missions no longer land at the first approach.
- `source/dashboard/run_vlm_dashboard_demo.sh` (new): runs the `vlm` scenario — a typed multi-step
  objective, no microphone — headless through the dashboard. This is how to demo without ASR.
- `source/dashboard/serve.py`: SIGINT/SIGTERM handlers plus a spin-thread join. Fixes the port-8088
  leak across runs.
- Dashboard support files (`assess.py`, `mock_data.py`, `run_sitl_demo.sh`, `README.md`): supporting
  edits for the dashboard demo path.

## SLAM removed (2026-09-13, separate commit)
projects/slam is being retired (Tello-only monocular SLAM; the Tello is no longer the target). Its
only build tie into llm_to_action was removed so slam can be archived:
- Deleted `source/tello_backend/test/tello_slam_hold.cpp`.
- Removed the `tello_slam_hold` target block from `source/tello_backend/CMakeLists.txt` (it added
  `../../slam` to the include path).
The core tello backend is untouched. SLAM can be re-added later; the pattern followed `tello_teleop`.
Remaining slam-dependent runtime bit, NOT a build dependency: `scripts/test/colors/run.sh` launches
the built `stella_vslam_monocular`; the `colors` scenario is already marked broken in
`sitl/scenarios.conf`. Safe to delete in a later cleanup.

## How to run the demo
`source/dashboard/run_vlm_dashboard_demo.sh`. Full runbook and standing gotchas:
`docs/active/2026-09-10-llm-to-action-demo-handoff.md`.
