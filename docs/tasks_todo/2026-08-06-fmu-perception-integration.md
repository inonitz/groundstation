# Session Handoff — 2026-08-06 — FMU perception integration (block 4.2)

This is the starting point for the next session. Read this, then `docs/ROADMAP.md`, then the
perception spec (`docs/specs/2026-08-05-perception-library-design.md`) and the vision lib in
`/root/build_yolo/vision/`. The task is **block 4.2**: wire the finished vision library into the
FMU.

---

## Ready-to-paste prompt for the new session

```
You are continuing work on `groundstation`, an off-board VLM-driven autonomous drone FMU
(C++17 / ROS 2). Follow the repo's CLAUDE.md: use the `rtk` wrappers for all reads/searches/git
(e.g. `rtk read`, `rtk grep`, `rtk git`), and document any major design decision in docs/NOTES.md.

Orient first, in this order:
  1. docs/ROADMAP.md               — the full recursive objective tree + status (start here)
  2. docs/handoffs/2026-08-06-fmu-perception-integration.md  — this handoff (context + task)
  3. docs/specs/2026-08-05-perception-library-design.md      — the vision lib design
  4. /root/build_yolo/vision/                                — the finished vision library

Your task is ROADMAP block 4.2: integrate the finished vision library into the FMU.
  - Consume `vision::fuse(seg, depth, frame) -> PerceptionSnapshot` (types are GLOBAL:
    `TargetDetection` / `PerceptionSnapshot` in vision/include/vision/perception_types.hpp).
  - Vendor/link the vision lib the way the workspace links sttserv (CPM in the top-level
    CMakeLists.txt), exposing an alias target the FMU links.
  - Run perception on a dedicated thread, TWO-RATE from the start: seg near 30 Hz, depth on a
    slower decoupled loop (measured: depth is ~3x over its 40 Hz target; seg meets 30 Hz).
  - Publish an atomic PerceptionSnapshot the control/VLM path reads; feed label/bbox/
    median_depth_cm into buildDynamicPrompt (ARCHITECTURE.md section 6).
  - DELETE the FMU's stub `struct TargetDetection` at fmu_node.hpp:168 and its `m_targets`
    usage — it name-clashes with the vision lib's global type; use the lib's type instead.
  - Cap ORT/perception threads so it cannot starve the 20 Hz control loop.

Do NOT touch the vision lib internals (that lane is done) or start APPROACH/visual-servo yet
(block 5, gated on this). Build with `./build.sh release shared configure && ./build.sh release
shared build` (PX4 backend is the hardcoded default). Commit style: ASCII only, topics separated
by " | ", no arrows, end with the Co-Authored-By trailer. Update docs/ROADMAP.md statuses and
docs/NOTES.md as you go.

Secondary, time-boxed (only once 4.2 is underway, or while builds run -- must NOT derail 4.2 or
add scope): read https://github.com/pratikPhadte/LLM-controlled-drone and write a short note in
docs/NOTES.md covering (a) its architecture, (b) how it differs from / resembles ours, (c) any
idea cheap to borrow, (d) what it suggests we could SIMPLIFY -- now or deferred until the system
already works and is tested. Idea-harvest + simplification note, NOT a redesign. We must stay
finishable in ~2 days.
```

---

## Bonus investigation -- comparison repo (time-boxed, anti-scope-creep)

Repo: **https://github.com/pratikPhadte/LLM-controlled-drone**

This is SECONDARY to block 4.2 and must not derail it or grow scope. Do it only once 4.2 is
underway, or opportunistically while builds/SITL run. Deliverable is a short `docs/NOTES.md`
entry (prose, no code changes this pass):

1. **Their architecture** -- how the repo is structured; how the LLM drives the drone; what
   runs off-board vs on-board; perception, planning, and control split.
2. **Diff / resemblance to ours** -- where it lines up with our "VLM plans, deterministic math
   executes" FMU, and where it takes a fundamentally different path.
3. **Cheap-to-borrow ideas** -- anything we could adopt with low effort and clear payoff.
4. **Greener-grass simplification check** -- if we resented our current plan and eyed theirs,
   what would we SIMPLIFY in our own design? Split into (a) simplify NOW (safe, reduces work
   toward the 2-day finish) and (b) simplify LATER, only after the system works and is tested.

**Guardrail:** the point is to harvest ideas and prune scope, NOT to start a redesign. If a
"good idea" would add work or risk the 2-day finish, log it under (b) LATER and move on. Nothing
here outranks landing 4.2.

## Where the project is right now (committed)

- **GenericBackend CRTP seam** — done and building. PX4 & Tello interchangeable behind a
  non-templated FMU; one `llm_to_action_fmu_<backend>` binary per selection. Both binaries link,
  both backend libs build, the three hardware-free tests pass (`frame_convert_test`,
  `tello_convert_test`, `plan_parse_test`).
- **Per-node CMake split** — every ROS2 node and both backends own a `CMakeLists.txt`; module
  top-level keeps only shared macros + `util_base_header` + `add_subdirectory`. Zero `../` includes.
- **ENU seam (Task 4)** — done; canonical ENU across the seam, NED only on the PX4 wire. Operator
  SITL re-gate (climb +2.0, GO along heading, clean land) is a human check, still pending.
- **VLM planner** — works end to end in SITL; event-driven, async, vision-grounded planning
  confirmed. The camera path (TX to RX to FMU) is proven.
- **Vision lib (`/root/build_yolo`)** — built and benchmarked; that lane is done. See findings below.

## The task: block 4.2 (FMU-side perception integration)

The vision library is finished and its interface is fixed, so this is plumbing against a known
contract, not open design.

**Contract (from `/root/build_yolo/vision/include/vision/`):**
- `struct TargetDetection { char label[32]; i32 bbox_xmin/ymin/xmax/ymax; f32 confidence;
  f32 median_depth_cm; }` — GLOBAL namespace.
- `struct PerceptionSnapshot { TargetDetection dets[16]; u32 count; u64 host_stamp_us; bool valid; }`
  — GLOBAL namespace.
- `vision::fuse(YoloSegEngine&, YoloDepthEngine&, const cv::Mat&, conf=0.25, iou=0.45)
  -> PerceptionSnapshot` — runs seg + depth on one frame, per-detection median depth over the mask.
- Engines take a `numThreads` ctor arg (ORT intra-op cap) — use it; do not let perception starve
  the control loop.

**Steps (also in ROADMAP 4.2):**
1. Vendor/link the vision lib via CPM in the top-level `CMakeLists.txt` (mirror the `sttserv`
   `safe_cpm_add_package` block); expose an alias target and link it into the FMU.
2. Perception thread, TWO-RATE: seg near 30 Hz, depth on its own slower cadence (see the perf gap).
3. Atomic `PerceptionSnapshot` shared with the control/VLM path (align on the frame PTS from
   `rx_node`, per ARCHITECTURE.md section 9).
4. Feed `label` / `bbox` / `median_depth_cm` JSON into `buildDynamicPrompt` (ARCHITECTURE.md
   section 6). This closes ROADMAP 3.4 (the prompt perception JSON is currently a stub).
5. Delete the FMU stub `struct TargetDetection` (fmu_node.hpp:168) and its `m_targets` — replace
   with the vision lib's global type. (They share the name; the stub must go.)

**Why two-rate matters (measured):** the depth model is ~3x over its 40 Hz target (74-76 ms at
384x384 / 4 threads; int8 is slower than fp32 on non-VNNI CPUs; int4 does not help — it is
conv-backbone compute-bound). Segmentation meets 30 Hz. So depth runs slower and decoupled; the
downstream emergency boundary (block 6.1) must tolerate a stale-ish depth signal.

## What NOT to do this session
- Do not modify the vision lib internals (`/root/build_yolo` lane is complete).
- Do not start APPROACH / live-YOLO GO (block 5) — it is gated on 4.2 landing first.
- Do not chase the depth backbone swap (block 4.1.8b) — decouple now, revisit after real-world obs.

## Build / verify
- PX4 (default): `./build.sh release shared configure && ./build.sh release shared build`.
- Tello: reconfigure the build dir with `-DGROUNDSTATION_BUILD_BACKEND_TELLO=ON`
  `-DGROUNDSTATION_BUILD_BACKEND_PX4=OFF` (no CLI switch in build.sh; do not edit build.sh).
- Tests: add `-DGROUNDSTATION_BUILD_TESTS=ON` to a configure.

## Durable pointers
- `docs/ROADMAP.md` — objective tree + status + time estimate (the index).
- `../ARCHITECTURE.md` — FMU architecture spec (sections 6 perception prompt, 9 perception seam).
- `docs/NOTES.md` — running dev log (SITL debugging, control-law iteration, decisions).
- `docs/specs/` — durable design specs; `docs/plans/` — implementation plans.
