# Handoff — YOLO26 Perception Library (new-session prompt)

This is the prompt to paste into a **fresh Claude session** (run from `/root/groundstation`) to
build the perception library. It's self-contained; the agent reads the spec for full detail.

**Full spec:** [`docs/superpowers/specs/2026-08-05-perception-library-design.md`](specs/2026-08-05-perception-library-design.md)

---

## Prompt (copy everything below the line)

---

You are extending the `groundstation` off-board drone FMU (C++17, ROS 2, `source/llm_to_action/`).
Build a **perception library** under `source/llm_to_action/vision/` that wraps **YOLOs-CPP**
(Geekgineer/YOLOs-CPP) to turn a camera frame into structured perception: **YOLO26
detection + instance segmentation** (`yolos::seg::YOLOSegDetector`) and **YOLO26 monocular metric
depth** (`yolos::depth::YOLODepthEstimator`), fused into a `PerceptionSnapshot`.

**Read first:**
- `docs/superpowers/specs/2026-08-05-perception-library-design.md` — the full spec (types, API,
  fusion, CMake, performance, models, tests). Follow it.
- `ARCHITECTURE.md` §9 (perception seam intent) and §6 (how the VLM consumes `label/bbox/depth`).
- The dependency pattern: `CMakeLists.txt` + `cmake/FetchCPM.cmake` (`safe_cpm_add_package`) and
  `cmake/FetchLLamaCPP.cmake` (isolated ExternalProject) — add YOLOs-CPP the **same way**.
- The library/CMake convention in `source/llm_to_action/gstreamer_gz_udp_tx/` (alias-namespace lib
  via `add_subdirectory`), and the pure/standalone-testable style of
  `source/llm_to_action/px4_backend/frame_convert.hpp` + its `test/`.

**Constraints:**
- **ROS-free** — depend only on YOLOs-CPP + OpenCV + `util2` base types. It must build and test
  without ROS or the simulator.
- C++17, **no exceptions**, `util2/C/base_type.h` types, concrete structs (no `virtual`).
- **Define** the canonical `TargetDetection` / `PerceptionSnapshot` types in `vision/` (they
  supersede the stub in `fmu/fmu_node.hpp`). **Do NOT edit `fmu/fmu_node.hpp`, the control loop,
  the backend, the VLM plumbing, or the sim scripts** — the main session integrates and swaps the
  FMU include. Your blast radius is `source/llm_to_action/vision/` + the CMake wiring for the dep.

**Models** (ONNX, under `/root/models/vision/`): `yolo26n-seg.onnx` (+ `.int8.onnx` [+ `.int4.onnx`])
and `yolo26n-depth.onnx` (+ quantized), plus `coco.names`. The spec §7 has the exact
export/quantize commands (INT8 dynamic + INT4 weight) — run them if the files aren't present,
otherwise use what's there. **CPU inference is fine.**

**CPU budget:** `yolo26n-depth` was ~100 ms and CPU-saturating on an 8-core box, and this will run
in-process with the FMU control loop and other nodes. So each engine must **cap ONNX Runtime
threads** via `Ort::SessionOptions::SetIntraOpNumThreads` (configurable, small default, e.g. 2;
patch YOLOs-CPP if it doesn't expose `SessionOptions`; disable ORT spinning).

**Benchmark & test properly — you do NOT need to prove anything or hit the targets.** Run the
correctness tests, then benchmark seg + depth latency across **fp32 / int8 / int4 × 1 / 2 / 4
threads** and report a table **against the targets (~40 Hz depth ≈ 25 ms, ~30 Hz seg/detection ≈
33 ms)** as honest measurement. If they're not met, say so plainly and stop — the humans reassess.

**Deliver:**
- The `vision/` library: thread-capped `YoloSegEngine` + `YoloDepthEngine` + `fuse()` + the
  canonical types + CMake (alias `Perception::vision`, added via `add_subdirectory`, YOLOs-CPP dep
  wired in the repo's style).
- A **standalone** test (no ROS/sim) that loads the models, runs on a sample image, asserts
  detections (bbox/label/conf) + a non-empty metric depth map + a populated fused
  `PerceptionSnapshot`, and prints the latency/thread benchmark.
- Exact build + run commands, the test result, and the benchmark table with your recommended
  variant + thread count.

Use the superpowers workflow (**brainstorming → writing-plans → TDD**). Do NOT integrate into the
FMU — the main session does that on return.

---

## For the human running the new session

- **What to fetch first (models):** see spec §7. Two YOLO26 nano checkpoints (`yolo26n-seg.pt`,
  `yolo26n-depth.pt`) → export ONNX `dynamic=True` → INT8 (`quantize_dynamic`) and optionally INT4
  (`MatMul4BitsQuantizer`) → drop under `/root/models/vision/` with `coco.names`. You can do this
  yourself or let the session do it end-to-end.
- **What to verify on that session:** the standalone correctness test passes, and the benchmark
  table is reported honestly against ~40 Hz depth / ~30 Hz seg (it does not need to hit them).
- **When you come back here** (after `/compact`): the main session integrates `Perception::vision`
  into the FMU — perception thread → `PerceptionSnapshot` → VLM prompt JSON (§6) + APPROACH
  `detectionByLabel` — and applies whatever the benchmark implies for rate/threads/affinity.
