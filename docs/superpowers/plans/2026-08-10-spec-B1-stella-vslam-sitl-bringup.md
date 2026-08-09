# B1 - stella_vslam SITL Bring-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer "does stella_vslam actually track in SITL?" with a number (drift vs PX4 EKF2 ground truth), not a screenshot.

**Architecture:** Re-enable the already-written (previously verified working, just never committed live) `FetchStellaSLAM.cmake` fetch chain, wire `source/slam` into the build behind a new option, uncomment the one disabled pose-publish call, then build a standalone ground-truth comparator that gives a quantitative verdict instead of relying on an operator interpreting rviz.

**Tech Stack:** CMake/ExternalProject, ROS2 (rclcpp/px4_msgs/geometry_msgs), stella_vslam, Python/rclpy for the comparator.

## Global Constraints

- No git writes (no add/commit/push) — suggest exact commands for the human at the end of each task, per `docs/code-guidelines.md`.
- Native `Read`/`Grep`/`Glob`/`View`/`Echo` are project-denied (`.claude/settings.local.json`) — use `rtk read`/`rtk grep`/`rtk ls`/`rtk find`/`rtk git` via Bash. This is enforced, not just a preference.
- Before each step, choose the right tool deliberately: LSP (`goToDefinition`/`findReferences`/`hover`) for precise C++ symbol navigation instead of defaulting to text grep; Bash/rtk for shell-shaped work. Don't default to one tool for everything.
- This spec's lock scope is `CMakeLists.txt` (top-level), `source/slam/`, `dependencies/stella_config.yaml` (conditionally), `scripts/test/slam/` (new) — no `fmu_node.hpp` touch, no lock needed in `docs/LOCKS.md`.
- End your final report with an explicit human-reviewer handoff: the exact commands to run, what output confirms success, and what a failure looks like. Not "it should work" — the actual commands and actual expected numbers.

---

### Task 1: Re-enable the stella_vslam build

**Files:**
- Modify: `CMakeLists.txt` (top-level)

**Interfaces:**
- Produces: `GROUNDSTATION_BUILD_SLAM` CMake option (default OFF); when ON, `source/slam` builds and produces `stella_vslam_monocular`.

- [ ] **Step 1: Re-enable the fetch chain**

In the top-level `CMakeLists.txt`:
- Line 23: `# include(cmake/FetchStellaSLAM.cmake)` -> uncomment.
- Line 84: `# define_library_fetch_of_stella_vslam_with_external_project()` -> uncomment.

`cmake/FetchStellaSLAM.cmake` is complete, previously-working code (confirmed identical on `feature-showcase-v2`, where this exact macro built and ran successfully) — this is wiring, not implementation.

- [ ] **Step 2: Add the build option**

Near the existing backend-selection options (lines 41-43):
```cmake
OPTION(GROUNDSTATION_BUILD_SLAM "Build the stella_vslam bring-up node" OFF)
```

- [ ] **Step 3: Wire source/slam in, behind the new option**

Find (lines 201-204):
```cmake
if(GROUNDSTATION_BUILD_EXECUTABLE)
    add_subdirectory(source/llm_to_action)
    # add_subdirectory(source/nav)
endif()
```
Add a sibling block right after it (don't fold into the existing `if` — SLAM is independently toggleable):
```cmake
if(GROUNDSTATION_BUILD_SLAM)
    add_subdirectory(source/slam)
endif()
```

- [ ] **Step 4: Build verification**

Run:
```bash
cmake -S . -B build/release/slam -G Ninja \
    -DGROUNDSTATION_BUILD_SLAM=ON \
    -DGROUNDSTATION_BUILD_EXECUTABLE=OFF \
    -DGROUNDSTATION_BUILD_TESTS=OFF \
    -DGROUNDSTATION_BUILD_BENCHMARKS=OFF \
    -DBUILD_SHARED_LIBS=1 \
    -DCMAKE_BUILD_TYPE=Release \
    -DGIT_SUBMODULE=ON
cmake --build build/release/slam --target all -j"$(nproc)"
```
Expected: configures without error, builds `build/release/slam/bin/stella_vslam_monocular` (target name from `source/slam/CMakeLists.txt`'s `define_ros2_node` macro combined with `project(stella_vslam C CXX)`). Isolated build dir — doesn't touch the existing PX4 build at `build/release/shared`. Budget ~10-15 minutes total, not longer — if it's running long, stop and report rather than waiting indefinitely.

- [ ] **Step 5: Suggested commit (human runs)**

```bash
git add CMakeLists.txt
git commit -m "build: wire source/slam into the build behind GROUNDSTATION_BUILD_SLAM, re-enable the stella_vslam fetch chain"
```

---

### Task 2: Uncomment the pose publish, verify color_order

**Files:**
- Modify: `source/slam/slam2.hpp`
- Modify (conditionally): `dependencies/stella_config.yaml`

**Interfaces:**
- Consumes: the built `stella_vslam_monocular` binary from Task 1.
- Produces: `slam/pose` (`geometry_msgs/msg/PoseStamped`) actually publishing when the node runs.

- [ ] **Step 1: Uncomment the publish call**

`source/slam/slam2.hpp:124`: change `// publish_rviz_pose();` to `publish_rviz_pose();`.

- [ ] **Step 2: Determine the real camera encoding**

`dependencies/stella_config.yaml:16` declares `color_order: "RGB"`, but `slam2.hpp:122` decodes frames as `BGR8`, and `rx_node.cpp` sets `msg.encoding` dynamically (`bgr8`/`rgb8`/`mono8`) depending on what Gazebo actually negotiates — don't assume either side is correct. Determine the real encoding empirically (e.g. a one-off debug print of `msg->encoding` from a live run, or inspect via `ros2 topic echo /camera/stream --once --no-arr | grep encoding`).

- [ ] **Step 3: Fix whichever side is wrong**

If the real encoding is RGB: `stella_config.yaml`'s `color_order: "RGB"` is already correct, but `slam2.hpp:122`'s decode should not force `BGR8` — either decode as `RGB8` or convert. If the real encoding is BGR: fix `stella_config.yaml:16` to `color_order: "BGR"` instead, leaving the decode as-is. Pick whichever is fewer/smaller changes once you know the actual value — do not guess and leave both possibly wrong.

- [ ] **Step 4: Syntax/build check**

Run: `cmake --build build/release/slam --target all -j"$(nproc)"`
Expected: builds clean with no new warnings from the touched lines.

- [ ] **Step 5: Suggested commit (human runs)**

```bash
git add source/slam/slam2.hpp dependencies/stella_config.yaml
git commit -m "feat: publish stella_vslam pose to slam/pose | Fix camera color_order mismatch between config and decode"
```

---

### Task 3: Launch script

**Files:**
- Create: `scripts/test/slam/run.sh`

**Interfaces:**
- Consumes: `scripts/test/lib/sim_core.sh` (if A1 has landed by the time this task runs, its `HEADLESS`/`LOG_FILE` knobs are available and should be used; if not, follow the plain pre-A1 `sim_core.sh` contract — check which is true before writing this, don't assume).

- [ ] **Step 1: Write the launch script**

Follow the `scripts/test/<feature>/run.sh` convention (`cd "$(dirname "$0")"`, set knobs, `source ../lib/sim_core.sh`), plus launch `stella_vslam_monocular` in its own tmux pane pointed at `dependencies/stella_config.yaml` and `dependencies/orb_vocab.fbow` (already present on disk, confirmed 42.9M). Use `WORLD_NAME="rubicon_targets"` or `"rubicon"` (textured, better for visual tracking than `default_car`/`empty`).

- [ ] **Step 2: Syntax check**

Run: `bash -n scripts/test/slam/run.sh`
Expected: no output, exit 0.

- [ ] **Step 3: Suggested commit (human runs)**

```bash
git add scripts/test/slam/run.sh
git commit -m "test: add SITL launch script for the stella_vslam bring-up node"
```

---

### Task 4: EKF2 ground-truth comparator

**Files:**
- Create: `scripts/test/slam/compare_ground_truth.py`

**Interfaces:**
- Consumes: `slam/pose` (`geometry_msgs/msg/PoseStamped`), `/fmu/out/vehicle_odometry` (`px4_msgs/msg/VehicleOdometry`, topic name confirmed already working in `px4_backend.cpp`'s `kPx4OdometryTopic`, no version suffix).
- Produces: periodic tagged stdout lines reporting publish rate, tracking fraction, and drift (meters) — parseable the same way every `filter.sh` already greps FMU log lines.

- [ ] **Step 1: Write the comparator**

An rclpy script (matching B2's precedent of standalone Python tooling, not a build-integrated C++ node) that:
- Subscribes to both topics, buffering recent samples.
- On a ~1 Hz timer, time-aligns the nearest sample pair and computes horizontal (XY) drift between them. Check whether stella's camera-pose frame needs converting before comparing against PX4's ENU frame — don't assume they're already aligned; if unsure, verify empirically against a known static/simple motion first.
- Prints tagged lines (e.g. `[SLAM_CHECK] rate=X.XXhz tracking_frac=X.XX drift_m=X.XX`) so a human or a future `filter.sh` can grep/assert on them.

- [ ] **Step 2: Live verification**

Run a `--canned` SITL flight (Task 3's script) in the chosen textured world with this comparator attached.
Expected: `rate` is near the camera's real framerate, `tracking_frac` is not near-zero, `drift_m` is a small, sane, moving number (not constant, not wildly erratic tick to tick).

- [ ] **Step 3: Suggested commit (human runs)**

```bash
git add scripts/test/slam/compare_ground_truth.py
git commit -m "test: add a quantitative EKF2 drift/tracking-rate comparator for stella_vslam, not a visual-only check"
```

---

### Task 5: End-to-end confirmation

**Files:** none (verification-only task).

- [ ] **Step 1: Full run**

Run Task 3's launch script with Task 4's comparator attached against a live SITL flight.

- [ ] **Step 2: Report to the human reviewer**

In the final report, give the human reviewer: the exact commands from Tasks 1/3/4, the comparator's actual observed numbers from this run, and these concrete rviz-inspection criteria (so the human isn't left guessing what they're looking at): the point-cloud landmarks should roughly trace the shape of the textured world's visible geometry (not a random scatter), the trajectory line should be roughly smooth and match the commanded flight path (not jagged or a frozen point), and there should be no sudden large jumps in the pose arrow between frames. State plainly whether stage 1 (build) and stage 2 (tracking quality) each succeeded or not — this determines whether B3 is reachable tomorrow or whether the fallback (B4, already unblocked) is the right call.

---

## Self-review

**Spec coverage:** Task 1 = build gate (the original spec's blind spot). Task 2 = the original spec's "uncomment + config" scope, corrected for the color_order risk. Task 3 = launch entry (spec's scope, nothing existed). Task 4 = the quantitative gate the operator asked for in place of "eyeball rviz." Task 5 = acceptance + human handoff.

**No placeholders:** every step has an exact command or exact file:line edit.

**Type/name consistency:** `GROUNDSTATION_BUILD_SLAM`, `slam/pose`, `compare_ground_truth.py`'s tagged output format are used consistently across tasks 1-5.
