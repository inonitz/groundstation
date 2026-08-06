> **Draft.** Written the day before implementation starts, to be handed to a
> fresh session/agent once the rest of the vision pipeline work has settled.
> Don't follow this to the letter — by the time it's picked up, the actual
> shape of "what other model we're adding" will likely be much clearer than
> it is here, and that should override anything below that no longer fits.

# Vision Library: Generic Backend Interface Refactor (CRTP)

## Context

`/root/build_yolo` (branch `feature-vision-api`, pushed to `origin` =
`https://github.com/nurmilkov/BUILD_YOLO.git`) hosts a standalone C++17
perception library (`vision/`) that currently wraps YOLOs-CPP's YOLO26
segmentation + depth models directly. Benchmarking (see `README.md`'s
"Results" sections) found neither model hits its real-time target on CPU —
seg misses by 2.1x, depth by 4.6x, even at the best config found (static
384x384 input, 4 threads). The plan going forward is to evaluate other model
families for depth (and possibly seg) instead of tuning YOLO26 further.

Today the library hardcodes YOLO everywhere a caller touches it:
`vision::YoloSegEngine`/`vision::YoloDepthEngine` are the *only* types
`perception_fusion.hpp`'s `fuse()` will accept, and label resolution in
`perception_fusion.cpp` calls a global `coco_class_name(classId)` — silently
assuming every future model was trained on COCO-80. Swapping in a
non-YOLO/non-COCO model later would require editing `perception_fusion.cpp`
itself, not just adding a new backend file.

**Goal of this refactor:** introduce a compile-time backend boundary so a new
model backend can be added by implementing two small CRTP-derived classes and
nothing else — `perception_fusion.hpp`/`.cpp`, `PerceptionSnapshot`, and any
downstream consumer (groundstation) stay untouched. This is *only* the
boundary — no model loader/factory/registry. We don't know which model we're
switching to yet, so building a loader now would be speculative; that's
explicitly out of scope, to be designed once a concrete second backend
exists.

**Why CRTP, not virtual/abstract interfaces:** static dispatch, no vtable,
inlines across the backend call in the hot path (relevant given this whole
exercise started because CPU compute is already the bottleneck). Cost:
`fuse()` becomes a template, so its backend-facing entry point has to live in
the header — see Design §3 for how that's kept to a thin wrapper around a
non-template core, so the bulk of the fusion logic stays compiled once in
`perception_fusion.cpp` rather than becoming header-only.

**Non-goals:**
- No model loader, factory, or config-driven backend selection.
- No change to `PerceptionSnapshot`/`TargetDetection` (already model-agnostic
  — confirmed by reading `vision/include/vision/perception_types.hpp`, zero
  YOLO/COCO coupling there already).
- No change to the YOLOs-CPP vendoring/patch layer (`cmake/FetchYOLOsCPP.cmake`).
- No behavior change. This is a pure structural refactor — the benchmark
  numbers after rebuilding must match the current README table (see
  Verification).

## Current State (read directly, not guessed)

```
vision/include/vision/
  coco_labels.hpp          constexpr COCO-80 classId -> label table (dataset
                            utility, not YOLO-specific - stays as-is)
  perception_types.hpp     TargetDetection, PerceptionSnapshot (already generic)
  yolo_seg_engine.hpp       class YoloSegEngine { ok(); segment(frame,conf,iou) -> vector<SegDetection>; }
                            struct SegDetection { cv::Rect box; float conf; int classId; cv::Mat mask; };
  yolo_depth_engine.hpp     class YoloDepthEngine { ok(); estimate(frame) -> cv::Mat CV_32FC1; }
  perception_fusion.hpp     PerceptionSnapshot fuse(YoloSegEngine&, YoloDepthEngine&, const cv::Mat&, float, float);
vision/source/
  yolo_seg_engine.cpp       PIMPL wrapping yolos::seg::YOLOSegDetector, try/catch-only-internal
  yolo_depth_engine.cpp     PIMPL wrapping yolos::depth::YOLODepthEstimator, same pattern
  perception_fusion.cpp     fuse(): calls segEngine.segment()/depthEngine.estimate(), then
                            copyLabel(out.label, coco_class_name(d.classId))  <- the COCO coupling
```

Both engines already use the PIMPL idiom and already expose only `ok()` +
one verb method each. `yolos::seg::YOLOSegDetector` already exposes
`getClassNames() -> const std::vector<std::string>&` (verified at
`segmentation.hpp:203` in the vendored YOLOs-CPP source under
`build/release/static/_deps/yolos-cpp-src/`), so the YOLO backend can resolve
its own labels without the fusion layer knowing about COCO at all.

## Design

### 1. CRTP base templates (compile-time interface, no vtable)

`vision/include/vision/segmentation_backend.hpp`:
```cpp
#pragma once
#include <opencv2/core.hpp>
#include <string>
#include <vector>

namespace vision {

struct SegDetection {
    cv::Rect    box;
    float       conf{0.0f};
    int         classId{0};
    std::string label;   // resolved by whichever backend produced this detection
    cv::Mat     mask;
};

// CRTP boundary for pluggable segmentation models: Derived must implement
// okImpl() and segmentImpl(...). fuse() (perception_fusion.hpp) is templated
// on this, so adding a new backend never touches fuse() itself - just write
// a class deriving from SegmentationBackendBase<NewBackend>.
template <typename Derived>
class SegmentationBackendBase {
public:
    [[nodiscard]] bool ok() const noexcept { return derived().okImpl(); }

    std::vector<SegDetection> segment(const cv::Mat& frame,
                                       float confThreshold = 0.25f,
                                       float iouThreshold  = 0.45f) {
        return derived().segmentImpl(frame, confThreshold, iouThreshold);
    }

private:
    Derived&       derived()       { return static_cast<Derived&>(*this); }
    const Derived& derived() const { return static_cast<const Derived&>(*this); }
};

} // namespace vision
```

`vision/include/vision/depth_backend.hpp`:
```cpp
#pragma once
#include <opencv2/core.hpp>

namespace vision {

template <typename Derived>
class DepthBackendBase {
public:
    [[nodiscard]] bool ok() const noexcept { return derived().okImpl(); }

    /// CV_32FC1 metric depth in meters, sized to the input frame. Empty on failure.
    cv::Mat estimate(const cv::Mat& frame) { return derived().estimateImpl(frame); }

private:
    Derived&       derived()       { return static_cast<Derived&>(*this); }
    const Derived& derived() const { return static_cast<const Derived&>(*this); }
};

} // namespace vision
```

### 2. Rename concrete YOLO implementation to CRTP-derived "backend" naming

- `vision/include/vision/yolo_seg_engine.hpp` → `yolo_seg_backend.hpp`,
  class `YoloSegEngine` → `class YoloSegBackend : public
  SegmentationBackendBase<YoloSegBackend>`. Public methods rename
  `ok()`/`segment()` → `okImpl()`/`segmentImpl()` (called by the base via
  static dispatch; callers keep using `ok()`/`segment()` through the base).
  Drop the local `SegDetection` struct (now lives in
  `segmentation_backend.hpp`, included instead).
- `vision/source/yolo_seg_engine.cpp` → `yolo_seg_backend.cpp`. In
  `segmentImpl()`, populate `d.label` via
  `impl_->detector.getClassNames()[r.classId]` (bounds-check like YOLOs-CPP's
  own drawing code does at `segmentation.hpp:169`) instead of leaving label
  resolution to the caller.
- `vision/include/vision/yolo_depth_engine.hpp` → `yolo_depth_backend.hpp`,
  class `YoloDepthEngine` → `class YoloDepthBackend : public
  DepthBackendBase<YoloDepthBackend>`, `ok()`/`estimate()` →
  `okImpl()`/`estimateImpl()`.
- `vision/source/yolo_depth_engine.cpp` → `yolo_depth_backend.cpp`. No
  label concept for depth, otherwise unchanged logic.
- Keep the "yolo" prefix on these filenames/classes deliberately — they
  genuinely are the YOLO-specific backend. Only the interface layer and
  `perception_fusion.hpp`'s signature need to stop naming YOLO.

### 3. Generalize `perception_fusion` — thin template wrapper over a compiled core

`vision/include/vision/perception_fusion.hpp`:
```cpp
#pragma once
#include "vision/perception_types.hpp"
#include "vision/segmentation_backend.hpp"
#include "vision/depth_backend.hpp"
#include <opencv2/core.hpp>
#include <vector>

namespace vision {

// Non-template core: everything after the two backend calls (median-depth
// sampling, label copy, snapshot assembly). Compiled once in
// perception_fusion.cpp - stays a real compiled TU, not header-only.
PerceptionSnapshot fuseDetections(std::vector<SegDetection> detections,
                                   const cv::Mat& depth,
                                   bool segOk);

// Template entry point - the only place backend types are named. Adding a
// new backend never touches this file: implement SegmentationBackendBase /
// DepthBackendBase for it and call fuse<NewSeg, NewDepth>(...) (or just
// fuse(seg, depth, frame) - template args deduce from the arguments).
template <typename SegT, typename DepthT>
PerceptionSnapshot fuse(SegmentationBackendBase<SegT>& segBackend,
                        DepthBackendBase<DepthT>& depthBackend,
                        const cv::Mat& frame,
                        float confThreshold = 0.25f,
                        float iouThreshold  = 0.45f) {
    if (!segBackend.ok()) {
        return fuseDetections({}, cv::Mat(), false);
    }
    std::vector<SegDetection> detections = segBackend.segment(frame, confThreshold, iouThreshold);
    cv::Mat depth = depthBackend.ok() ? depthBackend.estimate(frame) : cv::Mat();
    return fuseDetections(std::move(detections), depth, true);
}

} // namespace vision
```

`vision/source/perception_fusion.cpp`: keep `medianDepthMeters()` as-is
(unchanged - already only touches `SegDetection`/`cv::Mat`, no backend
type). Replace the old `fuse()` body with `fuseDetections()`, doing exactly
what it did before except: no `#include "vision/coco_labels.hpp"` (delete
it - no longer needed here), and `copyLabel(out.label, d.label.c_str())`
instead of `copyLabel(out.label, coco_class_name(d.classId))`. The
`host_stamp_us` timestamp (`std::chrono::steady_clock::now()`) moves into
`fuseDetections()` too, right where it was relative to the old `ok()` check.

### 4. Update `vision/CMakeLists.txt`

In the `SOURCES`/`HEADERS` `set()` blocks (already follows sttserv's
`set(SOURCES...)`/`set(HEADERS...)` + `target_sources()` pattern, keep that
structure):
- Add `include/vision/segmentation_backend.hpp`, `include/vision/depth_backend.hpp`
  to `HEADERS`.
- Rename `yolo_seg_engine.{hpp,cpp}` → `yolo_seg_backend.{hpp,cpp}` and
  `yolo_depth_engine.{hpp,cpp}` → `yolo_depth_backend.{hpp,cpp}` in both
  `SOURCES` and `HEADERS`.

### 5. Update `vision/test/perception_test.cpp`

Change `vision::YoloSegEngine seg(...)` → `vision::YoloSegBackend seg(...)`
and `vision::YoloDepthEngine depth(...)` → `vision::YoloDepthBackend
depth(...)` at every construction site (correctness block, main benchmark
loop, and the static-384/480 benchmark block). No other change needed —
`fuse(seg, depth, frame, ...)` call sites are unchanged; template argument
deduction picks up `YoloSegBackend`/`YoloDepthBackend` automatically.

### 6. Update `README.md`

Add a short "Architecture" note (in the existing Architecture section)
documenting the CRTP backend boundary and why it exists (link back to the
benchmark findings: depth likely needs a different backend, this refactor
is what makes that swap cheap once the model is chosen).

## Files touched (complete list)

- New: `vision/include/vision/segmentation_backend.hpp`
- New: `vision/include/vision/depth_backend.hpp`
- Rename+edit: `vision/include/vision/yolo_seg_engine.hpp` → `yolo_seg_backend.hpp`
- Rename+edit: `vision/include/vision/yolo_depth_engine.hpp` → `yolo_depth_backend.hpp`
- Rename+edit: `vision/source/yolo_seg_engine.cpp` → `yolo_seg_backend.cpp`
- Rename+edit: `vision/source/yolo_depth_engine.cpp` → `yolo_depth_backend.cpp`
- Edit: `vision/include/vision/perception_fusion.hpp` (gains the template `fuse()` body)
- Edit: `vision/source/perception_fusion.cpp` (old `fuse()` becomes `fuseDetections()`)
- Edit: `vision/CMakeLists.txt`
- Edit: `vision/test/perception_test.cpp`
- Edit: `README.md` (Architecture section)

Not touched: `perception_types.hpp`, `coco_labels.hpp`, `cmake/FetchYOLOsCPP.cmake`,
`build.sh`/`build.ps1`, any export/bench Python scripts.

## Verification

1. Build: `cd /root/build_yolo && ./build.sh release static configure && ./build.sh release static build`
   (configure only needed because `CMakeLists.txt`'s file lists changed).
2. `build.sh`'s own `test` action is currently broken (looks for
   `./vision/perception_test`, binary actually lands at `./bin/perception_test`
   — pre-existing bug, not part of this refactor, don't fix it as a drive-by).
   Run directly instead:
   ```bash
   cd build/release/static
   LD_LIBRARY_PATH="_deps/onnxruntime/onnxruntime-linux-x64-1.20.1/lib:$LD_LIBRARY_PATH" \
     ./bin/perception_test /root/models/vision /root/build_yolo/scripts/dog.png
   ```
   (models were last relocated to `/root/groundstation/models/vision/` for
   host extraction — check there first and copy back to `/root/models/vision`
   if the container-local copy is empty.)
3. Confirm "ALL CORRECTNESS CHECKS PASSED" still prints, and that the
   benchmark table's numbers match the C++ results already recorded in
   `README.md` (the "Static-shape C++ results" and "C++ results" sections)
   within normal run-to-run noise (~5-10%). A refactor that changes any
   number by more than that indicates a real behavior change, not just a
   rename/restructure — stop and investigate rather than updating the README
   to match.
4. Update README only for the interface-boundary documentation (step 6
   above) — do not touch the benchmark numbers/tables, they should be
   unaffected by this refactor.
