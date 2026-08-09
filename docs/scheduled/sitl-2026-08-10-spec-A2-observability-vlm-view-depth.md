# A2 — Observability: VLM view, depth map, prompt/response log

**Status:** scheduled / not started. **Created:** 2026-08-10. **Revised:** 2026-08-09 (session review — see
Revision log). **Branch:** feature-llm-driver (SITL showcase).
**Depends:** A1 (runner, soft). **ROADMAP:** new (debug tooling). **Lock:** touches `fmu_node.hpp` (new
publisher members + one hook in `callLlamaServer()`) and `fmu_node_base.hpp` (new constants) —
coordinate with A3 via `docs/LOCKS.md`; take the lock right before each edit, release right after, per
the protocol there. `perception_runtime.hpp` is NOT locked (nothing else touches it this session).

## Objective
Kill the human-debuggee problem: today nobody can see what the model sees. Publish the annotated
camera frame (boxes + labels) and a depth colormap to ROS topics, and log every VLM prompt+response
to a file, so a failed run is inspectable instead of a mystery.

## Grounding (verified against this checkout, 2026-08-09)
- `PerceptionRuntime` (`perception_runtime.hpp`) owns two independent loops, `segLoop()` and
  `depthLoop()`, each with the raw `cv::Mat` frame and (for seg) the `vision::SegDetection` list in
  scope. It does **not** own an `rclcpp::Node` — it already takes injected `std::function` callbacks
  (see `m_frameSource` in the constructor) instead of coupling to ROS2 directly. Follow that existing
  pattern: add two more constructor params, `std::function<void(cv::Mat const&)> onAnnotatedFrame` and
  `std::function<void(cv::Mat const&)> onDepthColormap`, called from `segLoop()`/`depthLoop()`
  respectively, right after the frame/depth mat is available. This publishes at each loop's own native
  rate (`kVisionSegLoopMs`/`kVisionDepthLoopMs`) — no new threads, no new atomics.
- `sensor_msgs::sensor_msgs` is **already linked** in `source/llm_to_action/fmu/CMakeLists.txt`
  (`target_link_libraries(... sensor_msgs::sensor_msgs ...)`). Zero new build dependency for image
  publishing.
- The prompt+response hook point is `callLlamaServer()` in `fmu_node.hpp` (~line 1550-1597): it builds
  the dynamic prompt (`dyn = buildDynamicPrompt();`) **and** awaits + parses the HTTP response
  (`content = j["choices"][0]["message"]["content"];`) in the same function, on a single `std::async`
  thread that `maybePlan()` already single-flight-guards (`m_planning`). One writer, no concurrency
  concerns — no mutex needed for the log file.
- This codebase has **zero `getenv` usage anywhere** — every path is a compile-time
  `constexpr const char*` (e.g. `kVisionSegModelPath` in `fmu_node_base.hpp`). Runtime config is
  tracked as its own debt item (ROADMAP 9.14, `docs/scheduled/2026-08-08-runtime-drone-config-constants.md`)
  — do not opportunistically introduce an env-var pattern here just to solve per-run log naming; see
  the per-run design below, which solves it without one.

## Scope
- **In:**
  1. Annotated-frame publisher (bboxes + labels drawn via `cv::rectangle`/`cv::putText`) and a
     depth-colormap publisher (`cv::applyColorMap` on a normalized 8-bit copy of the depth mat), both
     `sensor_msgs::msg::Image` via `cv_bridge`, owned/created by the FMU node, fed by the two callbacks
     above.
  2. Per-run VLM prompt+response JSONL log (design below) plus a small `scripts/test/lib/vlm_log_tool.sh`
     to list/aggregate and optionally wipe them.
  3. A Foxglove/rviz layout committed under `dependencies/`.
- **Out:** a full web dashboard. Topics + a log tool + a layout is enough. Cross-checking the VLM's
  *claims* ("approach_ok") against ground truth is explicitly deferred — same fast-follow noted in A1
  (real PX4 topics, not FMU-printed text, are the trust boundary; A1 already wires the ground-truth bag).

## Prompt/response log — per-run, not a fixed path (revised 2026-08-09)
The original draft used one fixed `constexpr` log path, which every run would overwrite — useless for
comparing runs, and directly wrong for `run_all.sh` (A1) running 20 scenarios back to back. Fixed
design, still zero `getenv`/runtime-config (the directory is a compile-time constant; only the
*filename* is computed once per process, the same idiom `sim_core.sh` already uses for `BAG_DIR`
timestamps, just in C++ instead of bash):

- `kVlmPromptLogDir = "/root/groundstation/vlm_logs"` (new constant, `fmu_node_base.hpp`).
- At construction, the FMU node computes one filename for its whole run:
  `vlm_prompts_<YYYYMMDD_HHMMSS>.jsonl` (wall-clock at process start, computed once, stored in a
  member — no per-cycle recomputation, no lock needed since it never changes after construction).
- **Size control:** the dominant size cost is the base64-encoded JPEG (`b64` in `callLlamaServer()`,
  routinely tens of KB per request), not the text prompt (~a few KB). The log does **not** duplicate the
  image bytes — record `image_attached: bool` and `image_b64_bytes: <int>` only. The image itself is
  already inspectable live via the new annotated-frame topic (this spec's other half); re-encoding it a
  second time into a text log is waste, not debuggability. This keeps each record on the order of a few
  KB, so a long VLM-driven run (dozens of reassess cycles) stays in the hundreds-of-KB to low-single-digit-MB
  range, not the tens-of-MB it would be with images inlined.
- Record shape (one JSON object per line): `{"timestamp_us": u64, "image_attached": bool,
  "image_b64_bytes": int, "prompt": "<full dyn text>", "response": "<full content text>"}`.
- Write at **every** exit path of `callLlamaServer()`, not just the success path — a failed/empty VLM
  response (HTTP error, bad status, unparseable body) is exactly the case you need logged to debug "why
  did nothing happen." `response` is empty string on those paths, which is itself informative.
- `scripts/test/lib/vlm_log_tool.sh` (new): default (no args) lists every file under
  `kVlmPromptLogDir` with record count + size, and total size across all of them. `--clean` deletes
  everything under the directory. No finer granularity (by age, by scenario, etc.) — per this session's
  explicit call, that complexity isn't worth it for a debug log; wholesale list-or-wipe is enough.

## Files
- Modify: `source/llm_to_action/fmu/perception_runtime.hpp` (two new callback params, called from
  `segLoop()`/`depthLoop()`).
- Modify: `source/llm_to_action/fmu/fmu_node.hpp` (own the two `rclcpp::Publisher<sensor_msgs::msg::Image>`,
  wire the callbacks at `PerceptionRuntime` construction, add the JSONL write in `callLlamaServer()`).
- Modify: `source/llm_to_action/fmu/fmu_node_base.hpp` (`kVlmPromptLogDir` and the two new image topic
  name constants, `kPascalCase` per `docs/code-guidelines.md`).
- Create: `scripts/test/lib/vlm_log_tool.sh`.
- Create: `dependencies/foxglove_layout.json`.

## Tests to create
- **[AUTO]** assert both image topics publish at the expected rate during a canned run (seg-rate for
  the annotated frame, depth-rate for the colormap).
- **[AUTO]** assert the prompt/response log file grows one valid JSON record per reassess cycle,
  including a forced-failure cycle (VLM unreachable) — the record still gets written with an empty
  `response`.
- **[AUTO]** `vlm_log_tool.sh` with no args reports the file just written; `--clean` removes it and a
  second no-arg call reports zero files.
- **[HUMAN]** one-time visual spot-check that boxes/labels/colormap look right in Foxglove/rviz.

## Acceptance
In a sandbox run, Foxglove shows the annotated frame + depth colormap live, and the prompt/response
log has one record per cycle, written to a fresh per-run file, with the image bytes excluded from the
logged text.

## Change-impact (per `docs/code-guidelines.md`)
- **What this changes:** additive only — new publishers, new callback params on `PerceptionRuntime`
  (default-constructible `std::function`, so existing callers/tests that don't pass them still compile
  and simply skip publishing), a new log file, a new script. No existing behavior/output changes.
- **Breaks existing behavior:** no.
- **Tests that re-run as-is:** all 20 SITL scenarios (A1) — none of their assertions touch these new
  topics/log.
- **Tests that are new:** the four listed above.

## Agent notes
Can start against a live sim; A1's bag/record path is not a hard dependency (the image topics and log
are independent of A1's ground-truth mechanism). Serialize the `fmu_node.hpp`/`fmu_node_base.hpp`
touches with A3 via `docs/LOCKS.md` — take the lock immediately before editing, release immediately
after, hold it only as long as the actual edit takes.

## Revision log
- 2026-08-09: per-run log path (was one fixed path, clobbered across runs); excluded base64 image
  bytes from the log (size concern); added `vlm_log_tool.sh` (list/aggregate + `--clean`); corrected
  lock scope to include `fmu_node.hpp`/`fmu_node_base.hpp` (original said "small hooks," didn't name
  the actual locked files); added grounding section with verified file:line hooks and the
  already-linked `sensor_msgs` dependency; added change-impact section.
