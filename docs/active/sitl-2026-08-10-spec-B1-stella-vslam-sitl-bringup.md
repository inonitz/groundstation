# B1 — stella_vslam SITL bring-up (the risk spike)

**Status:** IN PROGRESS 2026-08-09 — Tasks 1-4 done (build wired, `publish_rviz_pose()` uncommented,
`color_order` fixed to BGR, `scripts/test/slam/run.sh` + `compare_ground_truth.py` written, build
independently reproduced: `stella_vslam_monocular` 1.1MB). **Task 5 (live SITL run, real drift numbers
against EKF2) is the one open item** — see `docs/active/sitl-B1-task5-agent-prompt.md` for the dispatch
prompt. **Created:** 2026-08-10. **Revised:** 2026-08-09, twice (session
review, then an operator correction on the build-time estimate — see Revision log). **Branch:** none
needed to start (see B4's "Where this runs" note — same reasoning: `source/slam/` has no A-track
collision).
**Depends:** none — start in parallel. **ROADMAP:** 7.1. **Lock:** `source/slam/` + the top-level
`CMakeLists.txt` (new contention this revision — see Grounding). NO `fmu_node.hpp`.

## Objective
Answer the one unbounded question on the whole Tello path: **does stella_vslam actually track?** But
first, a question the original spec didn't know it needed to ask: **does it even build?**

## Grounding (verified against this checkout, 2026-08-09 — corrects the original spec materially)
- **`publish_rviz_pose()` is real and genuinely a one-line change**, as the original spec assumed.
  `source/slam/slam2.hpp:145-166` fully implements it (reads
  `m_slamSystem->get_map_publisher()->get_current_cam_pose()`, publishes `geometry_msgs::msg::PoseStamped`
  to `kSlamPoseTopic="slam/pose"` via `m_pubPose`, already constructed at `slam2.hpp:69-71`). The only
  thing disabling it is one commented-out call at `slam2.hpp:124` inside `slamWorkerThread()`:
  `// publish_rviz_pose();`. Uncomment it — this part of the spec was right.
- **`source/slam` is not in the build graph at all — confirmed this is new work, but small and fast
  (operator correction, 2026-08-09): this has been built and run successfully before, on this exact
  macro, just never committed with the wiring live.** Checked `feature-showcase-v2` (the branch this
  ran on previously) directly via `git show` — even there, `CMakeLists.txt:22-23` and `:63` have the
  identical two lines commented out, and `source/slam` is never `add_subdirectory()`'d on that branch
  either (only `source/llm_to_action`, `source/speech_to_action`, `source/nav` are). So the working state
  was local/uncommitted, not something to dig for in history. `cmake/FetchStellaSLAM.cmake` (same file,
  confirmed identical on both branches) **fully and correctly implements** the `ExternalProject_Add`
  chain (yaml-cpp -> g2o -> stella_vslam) producing the `stella_vslam::stella_vslam` alias target
  `source/slam/CMakeLists.txt` already links against — it is complete, tested code, not a stub. The fix
  is exactly three mechanical edits: (1) uncomment `include(cmake/FetchStellaSLAM.cmake)`, (2) uncomment
  `define_library_fetch_of_stella_vslam_with_external_project()`, (3) add
  `add_subdirectory(source/slam)` alongside the other three `source/` subdirectories, behind a new
  `GROUNDSTATION_BUILD_SLAM` option. **Operator estimate: at most ~10 minutes once wired correctly** —
  trust this over any abstract estimate of an ExternalProject g2o/yaml-cpp build; it's been done before
  on this same macro. This is step one, before "does it track" is askable, but it is not the schedule
  risk — stage 2 (verification, below) is.
- **Likely tracking-corrupting bug, unverified either way — check before trusting the config:**
  `dependencies/stella_config.yaml:16` declares `color_order: "RGB"`, but `slam2.hpp:122` decodes
  incoming frames as `sensor_msgs::image_encodings::BGR8`, and `rx_node.cpp` publishes `bgr8`/`rgb8`/`mono8`
  *dynamically* depending on the Gazebo-negotiated pixel format (not a fixed choice). A silent
  RGB/BGR mismatch degrades tracking without erroring — don't assume the yaml is already correct;
  confirm the actual encoding in flight and match `color_order` to it.
- **Two things already ready, genuinely no work needed:** the camera topic already matches on both ends
  (`rx_node_base.hpp:14` `kOutUDPCameraRawFrameTopic = "camera/stream"` == `slam2.hpp:28`
  `kCameraImageTopic = "camera/stream"`, no remap needed), and `dependencies/orb_vocab.fbow` is already
  present on disk (42.9M, confirmed).
- **No existing PX4 EKF2 ground-truth comparator exists anywhere in this codebase.** Everything that
  reads `vehicle_local_position`/`vehicle_odometry` today (`px4_backend*`, `offboard_ctrl/*`) consumes it
  for flight control, not comparison logging. The drift-vs-EKF2 test needs a **new** subscriber/harness
  node, not a reuse of anything existing.
- `source/slam/slam1.hpp` is a **separate, unrelated, unbuilt** OpenVINS-based node (different VIO
  approach, no pose publisher, not referenced by `source/slam/CMakeLists.txt` at all) — ignore it, not
  a fallback or alternative to slam2.hpp's stella_vslam path.

## Scope
- **In (revised order — build gate now comes first):**
  1. Re-enable the stella_vslam fetch chain: uncomment `CMakeLists.txt:22` and `:84`, add a
     `GROUNDSTATION_BUILD_SLAM` option (default OFF, matching the `_IS_TOP_LEVEL`-gated pattern in
     `docs/code-guidelines.md`), `add_subdirectory(source/slam)` behind it. Operator has done this exact
     wiring before successfully — expect ~10 minutes, not a long ExternalProject grind. Still worth a
     clean-build sanity check before moving on, since "worked before, uncommitted" is not the same
     guarantee as "known-green in this exact tree."
  2. Uncomment `publish_rviz_pose()` (`slam2.hpp:124`).
  3. Verify (don't assume) `color_order` in `stella_config.yaml` matches the actual encoding `rx_node`
     is publishing during a real sim run — fix if mismatched.
  4. A launch entry (nothing exists — confirmed no `sim_core.sh`/`simenv.sh` reference to
     `slam_node`/`SLAMNode`/`stella` anywhere in `scripts/`).
  5. **Quantitative tracking verification — this is the real gate, not step 2's uncomment.** Per
     2026-08-09 operator note: a prior attempt got the pose topic publishing and looked at rviz, but
     "eyeballing colored dots in rviz" was not something the operator could actually interpret as
     correct or wrong. Uncommenting `publish_rviz_pose()` proves the code path runs, not that the pose
     is accurate. The EKF2 drift comparator below is not optional/secondary — it is the thing that
     actually answers "does it track," in a form a human can read as a number, not a picture.
- **Out:** wiring pose into the FMU (that is B3). Keep it standalone.

## Files
- Modify: top-level `CMakeLists.txt` (re-enable fetch chain + new build option), `source/slam/slam2.hpp`
  (uncomment pose publish), `dependencies/stella_config.yaml` (color_order, if the check in step 3 finds
  a mismatch).
- Create: a launch script (mirror `scripts/test/lib/sim_core.sh`'s role, but for slam — likely a new
  `scripts/test/slam/` scenario dir once A1 lands, or a standalone launcher if done before A1).
- Create: a new ground-truth comparator node/script (nothing to extend — this is net-new).

## Tests to create
- **[AUTO] — the primary correctness check, build this first, not last.** Run a `--canned` SITL flight
  in a textured world -> the new EKF2 comparator node subscribes to both `slam/pose` and PX4's
  `vehicle_odometry`/`vehicle_local_position` (real ground truth, since it's sim) and computes, as
  numbers written to a log/summary, not a visualization: (a) `slam/pose` publish rate, (b) tracking-state
  = tracking for > a threshold fraction of frames, (c) position drift (meters, over the flight) between
  slam/pose and EKF2 ground truth, both trajectories time-aligned. This is the thing that answers "does
  it track" — a rate and a drift number, not a judgment call from a screen full of dots.
- **[HUMAN] — secondary, visual sanity only, not a substitute for the numbers above.** Eyeball the map +
  trajectory in rviz once (`scripts/stella_vslam_viz.rviz` already exists for this). What to actually
  look for, concretely (2026-08-09 note — the previous attempt didn't know what it was looking at):
  the point-cloud landmarks should roughly trace the shape of the textured world's visible geometry (not
  a random scatter), the camera-pose trajectory line should be roughly smooth and match the commanded
  flight path (not a jagged zigzag or a single frozen point), and there should be no sudden large jumps
  in the pose arrow between frames. If any of those look wrong, trust that observation over a green
  "tracking" flag from the comparator — but the comparator's numbers are still the primary gate; this is
  a sanity check on top, not instead of.

## Acceptance
The build produces a working stella_vslam binary (gate 1); `slam/pose` tracks a canned SITL flight
within a drift tolerance against EKF2 (gate 2).

## Change-impact (per `docs/code-guidelines.md`)
- **What this changes:** re-enabling previously-disabled build infrastructure (additive at the option
  level — default OFF means existing builds without the flag are unaffected) plus one uncommented
  function call in a node nothing else currently depends on.
- **Breaks existing behavior:** no, if the new build option defaults OFF and existing targets don't
  transitively depend on `source/slam`.
- **Tests that re-run as-is:** all 20 SITL scenarios (A1) — `source/slam` is not in their dependency
  graph.
- **Tests that are new:** the tracking-health assertion above, gated on the new comparator existing.

## Agent notes
Two stages, not one, but stage 1 should be fast (operator has done it before, budget ~10-15 min not an
hour+). Stage 1: build stands up cleanly. Stage 2, the real gate: the EKF2 drift comparator reports
numbers, not a rviz screenshot. If stage 2 doesn't converge within its timebox, fall back to the
position-free Tello demos (B4, already unblocked and running in parallel) and defer B3. Front-load
stage 1 specifically — a build failure discovered late wastes the whole slot that was meant for the
tracking question.

## Revision log
- 2026-08-09 (session review): found `source/slam` is not wired into the CMake build graph and the
  stella_vslam ExternalProject fetch chain is fully commented out at the top level — the target this
  depends on (`stella_vslam::stella_vslam`) does not exist yet, so the original "uncomment one line, does
  it track" framing skipped an entire build-bring-up stage. Flagged a likely color_order (RGB vs BGR8)
  mismatch as unverified, not confirmed-fine. Confirmed camera topic already aligns (no remap needed) and
  `orb_vocab.fbow` is already present — two things that are NOT extra work. Confirmed no PX4 EKF2
  ground-truth comparator exists anywhere — net-new, not reuse. Clarified slam1.hpp is unrelated dead
  code, not a fallback.
- 2026-08-09 (operator correction): the build stage is NOT the multi-hour risk the first revision
  assumed — operator has built and run this exact `FetchStellaSLAM.cmake` macro successfully before
  (confirmed by diffing `feature-showcase-v2`, which has the identical macro and the identical two lines
  commented out — the working state was local/uncommitted, not recoverable from history). Corrected the
  estimate to ~10 minutes once the three mechanical wiring edits are in. Re-weighted the real risk onto
  stage 2 (verification): operator flagged that a previous attempt got the pose topic publishing and
  looked at rviz, but couldn't actually tell if what they were seeing was correct — "eyeballing dots" is
  not verification. Made the EKF2 drift comparator the primary, quantitative gate (build it first, not
  as an afterthought), and gave the rviz check concrete criteria to look for instead of an open-ended
  "eyeball it once."
