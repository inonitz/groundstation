# Perception Library (YOLO26 detection+seg + metric depth) — Design Spec

> **Status:** DESIGN / APPROVED-FOR-BUILD. Phase-2 sub-project **C** (perception) of the
> DroneBackend program. **Audience:** a fresh Claude session building this library in isolation.
> **Scope of this slice:** a ROS-free `vision/` library that turns a camera frame into structured
> perception (YOLO26 detection+instance-seg + monocular metric depth), fused into a
> `PerceptionSnapshot`, wrapping **YOLOs-CPP**. **NOT in scope:** FMU integration, the servo, the
> VLM prompt wiring — those are the main session's follow-up. **Target:** C++17, no exceptions,
> CPU-first.

---

## 0. Where this fits (read this first)

`groundstation` is an off-board **"VLM plans, deterministic math executes"** drone FMU
(`source/llm_to_action/`, see [ARCHITECTURE.md](../../../ARCHITECTURE.md)). It already flies
end-to-end off a VLM in PX4 SITL: camera → VLM plan → deterministic ENU control loop → PX4. But
the VLM today sees only a **raw JPEG** — there is **no structured perception**, so the drone can
only do blind geometric moves (`takeoff/go/land`). It cannot find or approach an object, which is
the whole point of the system.

This library closes that gap. It is the concrete implementation behind the **stubbed perception
seam** described in ARCHITECTURE.md **§9** (`YoloDetectionEngine` / `YoloDepthEngine` + an atomic
perception snapshot) and feeds the VLM prompt's perception JSON (**§6**: `label / bbox /
median_depth`). Once it exists, the main session wires it into the FMU and the planned APPROACH
visual-servoing primitive.

**Your deliverable:** the `vision/` library + a standalone test/benchmark. **You do NOT integrate
it into the FMU** — a separate session does that.

## 1. Placement & nature

- New folder **`source/llm_to_action/vision/`**.
- A **consumed library**, not a ROS node. **ROS-free**: depends only on **YOLOs-CPP**, OpenCV,
  and `util2` base types. It must build and be testable **without ROS or the simulator** — the
  same philosophy as `source/llm_to_action/px4_backend/frame_convert.hpp` (pure math, standalone
  `g++` test).
- **Conventions (match the repo):** C++17, **no exceptions**, `#include <util2/C/base_type.h>`
  types (`f32/u32/i32/u64/...`), enums one-per-line ≤95 cols, concrete structs (no `virtual`),
  no `std::variant`. `FixedStringType` = `char[32]` (see `fmu/fmu_node.hpp`).

## 2. Dependency — YOLOs-CPP (Geekgineer/YOLOs-CPP)

Header-first C++ inference engine over **ONNX Runtime + OpenCV**, supporting YOLO v5–v12 and
**YOLO26** for detection, segmentation, pose, OBB, classification, and **depth** (YOLO26-only
monocular **metric** depth). ONNX Runtime is auto-fetched (v1.16+) unless `ONNXRUNTIME_DIR` is set.

**Verified against upstream `Geekgineer/YOLOs-CPP` CMakeLists.txt and the `nurmilkov/BUILD_YOLO`
reference project (branch `yolodepth-update`, the most-current of its 4 branches — 2 commits ahead
of `modular-vision-api`, which is what ARCHITECTURE.md §9 calls "BUILD_YOLO modular-vision-api"):**

- YOLOs-CPP's own `CMakeLists.txt` defines **no library target** — only `add_executable()` for 10
  demo binaries, and it `FATAL_ERROR`s unless `ONNXRUNTIME_DIR` already points at an extracted ORT
  release. There is nothing to `add_subdirectory()` usefully. **BUILD_YOLO independently reached
  the same conclusion**: it vendors YOLOs-CPP as a git submodule and only ever points
  `target_include_directories` at `third_party/YOLOs-CPP/include` — it never builds YOLOs-CPP's
  CMakeLists either.
- So: fetch YOLOs-CPP **headers-only** via `safe_cpm_add_package(... DOWNLOAD_ONLY YES)` (CPM's
  download-only mode skips `add_subdirectory` entirely — no stray executables, no premature
  `ONNXRUNTIME_DIR` requirement). Pin `GIT_TAG` to the exact commit BUILD_YOLO validated YOLO26
  seg+depth against: **`2b3b2f640a085c2be8e62d3566117c84d623cee0`**. Build our own `INTERFACE`
  target over `${yolos-cpp_SOURCE_DIR}/include`.
- ONNX Runtime itself has no CPM/CMake target upstream — it's a prebuilt tarball (YOLOs-CPP's own
  `build.sh` downloads `onnxruntime-linux-x64-1.20.1.tgz` from the ONNX Runtime GitHub releases).
  Automate that download (BUILD_YOLO does it manually via a user-supplied `ONNXRUNTIME_ROOT`; we
  don't want that manual step). Isolated **`cmake/FetchYOLOsCPP.cmake`**: `file(DOWNLOAD ...)` +
  `file(ARCHIVE_EXTRACT ...)` the same tarball, expose an `IMPORTED` `ONNXRuntime::onnxruntime`
  target (`.so` + `include/`), `include()`d in the root `CMakeLists.txt` next to
  `FetchLLamaCPP.cmake`.
- **Thread cap must be patched — BUILD_YOLO does not have a working fix to copy.** Its
  `DepthEstimatorConfig::intraOpThreads` field exists but is silently dropped on the
  `DepthBackend::Yolo26Depth` path (`depth_estimator.cpp`: `YOLODepthEstimator(config_.modelPath,
  false)` — no thread arg forwarded); it only reaches their own unrelated `MidasSmallEngine`. Same
  gap confirmed directly in upstream: `OrtSessionBase` takes `numThreads`, but
  `YOLOSegDetector`/`YOLODepthEstimator` constructors hardcode `OrtSessionBase(modelPath, useGPU)`
  without forwarding it, and no spin-disable is set anywhere. **Patch in place, in CMake, after
  the CPM fetch** — not a hand-vendored copy of the (552 + 174 line) upstream files. A
  `patch_yolos_cpp_for_thread_cap(<source_dir>)` macro in `cmake/FetchYOLOsCPP.cmake` does
  `file(READ)` → `string(FIND)` (assert the exact old text is still there, `FATAL_ERROR` loudly if
  upstream shifts) → `string(REPLACE)` → `file(WRITE)` on exactly 3 files: add a `numThreads`
  parameter forwarded into `OrtSessionBase(modelPath, useGPU, numThreads)` in
  `yolos/tasks/segmentation.hpp` and `yolos/tasks/depth.hpp`, and add
  `sessionOptions_.AddConfigEntry(kOrtSessionOptionsConfigAllowIntraOpSpinning, "0")` in
  `yolos/core/session_base.hpp`'s `configureSessionOptions`. Runs once per fresh CPM fetch.

### YOLOs-CPP API (verified from the repo — use these exactly)
- Include `yolos/yolos.hpp` (all tasks), or per-task `yolos/tasks/{segmentation,depth}.hpp`.
- **Detection + instance masks (one model):**
  `yolos::seg::YOLOSegDetector(model_path, labels_file, gpu_flag)` →
  `segment(cv::Mat frame, float conf=0.25f, float iou=0.45f)` →
  `std::vector<{ std::string className; float confidence; cv::Rect box; cv::Mat mask; int classId; }>`.
  The seg output already carries the bounding box, so **no separate detector is needed**.
- **Monocular metric depth (separate model):**
  `yolos::depth::YOLODepthEstimator(model_path, gpu_flag)` →
  `estimate(cv::Mat frame)` → `cv::Mat` (`CV_32FC1`), per-pixel depth in **meters**.

## 3. Canonical seam types (this library OWNS them)

Define in a `vision/` header (e.g. `vision/perception_types.hpp`). These **supersede** the stub
`TargetDetection` in `fmu/fmu_node.hpp`. **Do not edit the FMU** — the main session removes the
stub and includes this header during integration.

```cpp
#include <util2/C/base_type.h>

using FixedStringType = char[32];              // matches fmu/fmu_node.hpp

struct TargetDetection {
    FixedStringType label{ "\0" };             // COCO class name
    i32 bbox_xmin{0}, bbox_ymin{0}, bbox_xmax{0}, bbox_ymax{0};
    f32 confidence{0.0f};
    f32 median_depth_cm{0.0f};                 // sampled from the depth map over the bbox (or mask)
    // Optional: a mask handle for landing-clearance later. Keep the struct trivially copyable.
};

struct PerceptionSnapshot {
    static constexpr u32 kMaxDetections = 16;
    TargetDetection dets[kMaxDetections];
    u32  count{0};
    u64  host_stamp_us{0};                     // frame receipt time (host steady clock), for staleness
    bool valid{false};                         // false until the first successful fuse()
};
```

## 4. Engine wrappers + fusion (concrete structs, no virtual)

Keep the FMU-facing shape aligned to ARCHITECTURE.md §9 (`YoloDetectionEngine` /
`YoloDepthEngine`) so the seam is stable while YOLOs-CPP stays an implementation detail.

- **`YoloSegEngine`** wraps `yolos::seg::YOLOSegDetector`. Upstream's `Segmentation` result is
  `{BoundingBox box; float conf; int classId; cv::Mat mask}` — **no `className` field.** Don't
  round-trip through `getClassNames()`/`coco.names` at runtime: embed a `constexpr` COCO-80
  `classId → const char*` table in `vision/coco_labels.hpp` and copy directly into
  `TargetDetection::label` (`FixedStringType`). Pass that same table (as a `vector<string>`, built
  once) into `YOLOSegDetector`'s labels-vector ctor overload so upstream's own drawing/debug
  helpers stay consistent — but our fused output never depends on a `coco.names` file at runtime.
- **`YoloDepthEngine`** wraps `yolos::depth::YOLODepthEstimator`. Exposes the `CV_32FC1` metric
  depth map.
- **Fusion** `PerceptionSnapshot fuse(const cv::Mat& frame)`:
  1. `seg.segment(frame)` → detections.
  2. `depth.estimate(frame)` → metric depth map (same frame).
  3. For each detection, sample the depth map over its bbox (median; use the mask region if you
     keep masks) → `median_depth_cm = median_meters * 100`.
  4. Fill up to `kMaxDetections`, set `host_stamp_us` (host steady clock), `valid = true`.

Both engines take their **model path** at construction (fp32 / int8 / int4 selected by path) plus
a **thread budget** (see §6).

## 5. CMake integration

- Build `vision/` as a **library target with an alias namespace** — model it on
  `source/llm_to_action/gstreamer_gz_udp_tx/CMakeLists.txt`, which builds `GazeboGstCamera` and
  exposes `add_library(CameraPlugin::GazeboGstCameraLibrary ALIAS ...)`. Expose e.g.
  `Perception::vision`. Register it with `add_subdirectory(vision)` from
  `source/llm_to_action/CMakeLists.txt` (mirror the existing `add_subdirectory(gstreamer_gz_udp_tx)`).
- Link YOLOs-CPP + OpenCV (`opencv_core/imgproc/imgcodecs`). The FMU will later add
  `Perception::vision` to its `ros2_node_add_library(...)` list — that's integration, not your task.

## 6. Performance & CPU budget — benchmark & report (NOT a gate)

BUILD_YOLO's author measured **`yolo26n-depth` ≈ 100 ms on an 8-core/8-thread CPU, and it
saturated the CPU.** This library will run **in-process with the FMU 20 Hz control loop and the
other `llm_to_action` multithreaded nodes**, so an ORT session that grabs every core would starve
them.

**Targets to measure against (you do NOT need to hit them — measure honestly and report):**
- **Depth: ~40 Hz (≈ 25 ms/frame).**
- **Segmentation / detection: ~30 Hz (≈ 33 ms/frame).**

If, after quantization + thread capping, the numbers fall short, **say so plainly and stop.** The
humans reassess (lower rate, core affinity, out-of-process, GPU, smaller input). Do not
over-optimize or claim a number you didn't reach.

**Two capabilities the library MUST have (so CPU use is tunable):**
- **Configurable ORT thread cap.** Each engine exposes a thread budget wired into the session:
  `Ort::SessionOptions::SetIntraOpNumThreads(n)` (+ `SetInterOpNumThreads`), small default (e.g.
  **2**). If YOLOs-CPP doesn't surface `SessionOptions`, extend/patch it (it's a small header lib)
  to pass a thread count into session creation. Prefer disabling ORT spinning
  (`intra_op.allow_spinning=0` / `ORT_DISABLE_SPINNING`) so idle threads don't busy-wait cores.
- **Runs quantized models** as drop-in alternates to fp32, selected by file path.

## 7. Models & quantization

Models live under **`/root/models/vision/`** (mirrors `/root/models/vlm/`). The user may place
them there manually; if absent, produce them with the commands below (the agent may run these
too). Both are YOLO26 **nano**.

```python
# 1) Export fp32 ONNX with dynamic axes (required by the C++ ORT engine)
from ultralytics import YOLO
YOLO("yolo26n-seg.pt").export(format="onnx", dynamic=True)     # detection + instance masks
YOLO("yolo26n-depth.pt").export(format="onnx", dynamic=True)   # monocular metric depth

# 2a) INT8 dynamic quantization (no calibration data)
from onnxruntime.quantization import quantize_dynamic, QuantType
quantize_dynamic("yolo26n-seg.onnx",   "yolo26n-seg.int8.onnx",   weight_type=QuantType.QInt8)
quantize_dynamic("yolo26n-depth.onnx", "yolo26n-depth.int8.onnx", weight_type=QuantType.QInt8)

# 2b) INT4 weight quantization (smaller/faster, some quality loss — worth measuring)
from onnxruntime.quantization.matmul_4bits_quantizer import MatMul4BitsQuantizer
import onnx
for name in ("yolo26n-seg", "yolo26n-depth"):
    q = MatMul4BitsQuantizer(onnx.load(f"{name}.onnx"), block_size=32, is_symmetric=True)
    q.process(); q.model.save_model_to_file(f"{name}.int4.onnx", use_external_data_format=False)
```

Under `/root/models/vision/`: `yolo26n-seg.onnx` + `.int8.onnx` (+ `.int4.onnx`),
`yolo26n-depth.onnx` + `.int8.onnx` (+ `.int4.onnx`). No `coco.names` file needed — labels come
from the `constexpr` COCO-80 table in `vision/coco_labels.hpp` (see §4). (`yolo26n-seg.pt` is at `ultralytics/assets` v8.4.0; `yolo26n-depth.pt` is the
YOLO26-depth nano checkpoint — the depth variant exists across n/s/m/l/x. INT4 on CNN heads may be
partial; attempt it and report accuracy vs speed.)

## 8. Testing & benchmark (do it properly — nothing to prove)

Standalone, no ROS/sim (like `px4_backend/test/frame_convert_test.cpp`):

1. Load the ONNX models; run on a **sample image** with known objects (a COCO photo is fine).
2. **Correctness:** seg returns ≥1 detection with a bbox inside the frame, a plausible label, and
   conf ∈ (0,1]; depth `estimate()` returns a non-empty `CV_32FC1` map with plausible **metric**
   values (finite, > 0 in-scene); `fuse()` populates `PerceptionSnapshot` with a `median_depth_cm`
   per detection that matches the sampled region.
3. **Benchmark:** seg + depth latency (ms/frame, mean + p95) across variants **fp32 / int8 /
   int4** × thread counts **1 / 2 / 4**. Print a table and state each result **against the targets
   (~40 Hz depth, ~30 Hz seg)** — as measurement, not pass/fail. Confirm the thread cap actually
   bounds cores used (ORT isn't spawning a thread-per-core).
4. Give exact **build + run commands** and confirm the correctness test passes before handing back.
   If the targets aren't met, report it plainly for human reassessment.

## 9. Definition of done (this slice)

- [ ] `source/llm_to_action/vision/` builds as `Perception::vision` via `add_subdirectory`,
      YOLOs-CPP wired in the repo's dependency style.
- [ ] Canonical `TargetDetection` / `PerceptionSnapshot` defined in `vision/` (FMU untouched).
- [ ] `YoloSegEngine`, `YoloDepthEngine`, `fuse()` — concrete, ROS-free, thread-cap configurable,
      run fp32/int8/int4 by path.
- [ ] Standalone correctness test passes; latency/thread benchmark printed and reported against
      the targets.
- [ ] No edits to `fmu/`, backend, VLM plumbing, or sim scripts.

## 10. Handoff back

When done, report: what was built, the exact build/run commands, the test result, and the
benchmark table vs the ~40 Hz / ~30 Hz targets (with your recommended variant + thread count).
The main session then integrates `Perception::vision` into the FMU (perception thread →
`PerceptionSnapshot` → VLM prompt JSON per §6 + APPROACH `detectionByLabel`), applying whatever
the benchmark implies for rate/threads/affinity.
