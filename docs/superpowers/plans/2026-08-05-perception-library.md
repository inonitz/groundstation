# Perception Library (YOLO26 seg+detect + metric depth) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `vision/` — a standalone C++17 library, its own repository (mirroring the shape of
`inonitz/sttserv`, not nested inside `groundstation`) — that wraps YOLOs-CPP's YOLO26 instance
segmentation + monocular metric depth, fuses them into a `PerceptionSnapshot`, and ships as
`Perception::vision` via CMake — plus a standalone correctness + latency benchmark test. A later,
separate session consumes it from `groundstation` the same way `groundstation` already consumes
`sttserver` (`safe_cpm_add_package(NAME vision GIT_REPOSITORY ...)`); that consumption step is
**not** part of this plan.

**Architecture:** Workspace root is `/root/build_yolo` (local git repo, not yet pushed to a
remote). It mirrors `inonitz/sttserv`'s shape exactly: a top-level `CMakeLists.txt`
(`project(vision_workspace ...)`, its own copy of the generic `cmake/` scaffolding — `FetchCPM`,
`SubmoduleUpdate`, `UseCCache`, `ColouredOutput`, `OutputDir`, `WorkspaceOptions`,
`BuildDiagnostics` — already copied from `groundstation/cmake/` as setup, not a task here) plus a
`vision/` subdirectory holding the actual library (`vision/CMakeLists.txt`,
`vision/include/vision/*.hpp`, `vision/source/*.cpp`, `vision/test/`), the same
`<repo>/<libname>/{include,source}` split `sttserv/sttserv/` uses.

It depends on: YOLOs-CPP (fetched headers-only via CPM, `DOWNLOAD_ONLY`, pinned to the exact
commit `nurmilkov/BUILD_YOLO` validated YOLO26 support against), a prebuilt ONNX Runtime tarball
(fetched + extracted by `cmake/FetchYOLOsCPP.cmake`), and OpenCV. Two upstream gaps get patched
**in place, in CMake** (`string(REPLACE)` on the CPM-fetched source, not a fork, not a hand-vendored
copy — this was a deliberate choice over forking `inonitz/YOLOs-CPP`, made explicitly in this
session: forking would mean maintaining a second dependency and manually re-syncing upstream fixes,
for no real benefit — the unused YOLOs-CPP task headers (pose/obb/classification/yoloe) are never
`#include`d by our seg/depth path either way, so a fork's "strip dead code" appeal is moot): YOLOs-
CPP's seg/depth constructors don't forward a thread count to ONNX Runtime, and don't disable ORT's
busy-wait spinning — both matter because this will eventually run in-process with a 20 Hz control
loop on shared cores once `groundstation` consumes it. `YoloSegEngine`/`YoloDepthEngine` wrap the
two patched YOLOs-CPP classes behind a non-throwing API (YOLOs-CPP throws internally; this
library's boundary does not); `fuse()` runs both on one frame and samples the depth map over each
detection's mask to fill `PerceptionSnapshot`.

**Tech Stack:** C++17, OpenCV 4.6 (`opencv_core`/`imgproc`/`imgcodecs`), ONNX Runtime 1.20.1 (CPU),
YOLOs-CPP (`Geekgineer/YOLOs-CPP` @ `2b3b2f640a085c2be8e62d3566117c84d623cee0`), CMake 3.16+, CPM,
`util2/C/base_type.h` fixed-width types (fetched the same way `groundstation` and `sttserv` both
already fetch `util2`).

## Global Constraints

- **This is its own repository at `/root/build_yolo`, not part of `groundstation`.** Nothing in
  this plan touches the `groundstation` checkout. The future step where `groundstation`'s root
  `CMakeLists.txt` gains a `safe_cpm_add_package(NAME vision ...)` block (mirroring its existing
  `sttserver` block) and links `Perception::vision` into the FMU is explicitly **out of scope**.
- **No exceptions cross the `vision/` public API.** YOLOs-CPP throws (`std::runtime_error`,
  `std::invalid_argument`) internally — every engine wrapper catches at its own boundary and
  exposes `bool ok()` instead. Internal `try`/`catch` is fine; nothing propagates out.
- **C++17. `util2/C/base_type.h` fixed-width types** (`f32/i32/u32/u64`) for the two canonical seam
  structs. `FixedStringType` = `char[32]`, matching `groundstation`'s
  `source/llm_to_action/fmu/fmu_node.hpp` stub exactly (that repo will drop its own copy in favor
  of this library's version when it later consumes this).
- **Concrete structs only — no `virtual`, no `std::variant`.**
- **Every engine takes a `numThreads` budget at construction** (small default: 2) and every ONNX
  Runtime session must have spinning disabled. This is a correctness requirement, not a nice-to-have
  — unpatched YOLOs-CPP silently ignores thread caps (verified: BUILD_YOLO's own
  `DepthEstimatorConfig::intraOpThreads` is dropped on the YOLO26 path too).
- **CPU inference only.** No GPU/CUDA code paths need to work; `useGPU` stays `false` everywhere.
  fp32/int8/int4 model variants are selected purely by file path suffix (`""`, `.int8`, `.int4`).
- Full spec: `groundstation`'s `docs/superpowers/specs/2026-08-05-perception-library-design.md`
  (read-only reference — do not edit that repo). This plan implements it, adapted mid-flight to the
  standalone-repo structure decided in this session.

---

## File Structure

```
/root/build_yolo/                                   # repo root (git init'd, not yet pushed)
  CMakeLists.txt                                     # ALREADY WRITTEN (setup, not a task) — mirrors sttserv's root CMakeLists.txt
  cmake/
    FetchCPM.cmake                                   # ALREADY COPIED from groundstation/cmake/ (setup)
    SubmoduleUpdate.cmake / UseCCache.cmake / ColouredOutput.cmake /
    OutputDir.cmake / WorkspaceOptions.cmake / BuildDiagnostics.cmake / DetectWSL.cmake
                                                       # ALREADY COPIED (setup, generic workspace boilerplate)
    FetchYOLOsCPP.cmake                               # NEW — Task 2
  vision/
    CMakeLists.txt                                   # NEW — Task 8
    include/vision/
      perception_types.hpp                            # NEW — Task 4
      coco_labels.hpp                                  # NEW — Task 3
      yolo_seg_engine.hpp                              # NEW — Task 5
      yolo_depth_engine.hpp                             # NEW — Task 6
      perception_fusion.hpp                             # NEW — Task 7
    source/
      yolo_seg_engine.cpp                              # NEW — Task 5
      yolo_depth_engine.cpp                             # NEW — Task 6
      perception_fusion.cpp                             # NEW — Task 7
    test/
      perception_test.cpp                              # NEW — Task 9
```

The root `CMakeLists.txt` and the generic `cmake/*.cmake` files (everything except
`FetchYOLOsCPP.cmake`) already exist — copied from `groundstation/cmake/` and hand-written to
mirror `sttserv`'s root `CMakeLists.txt` as setup for this plan, not a task an implementer needs to
redo. Task 2 only needs to **write `cmake/FetchYOLOsCPP.cmake`** — the root file already
`include()`s it and calls `define_library_fetch_of_yolos_cpp()`.

---

### Task 1: Fetch + export + quantize the YOLO26 models — DONE (handled directly, not via subagent)

Handled by the human partner directly outside this plan's subagent flow. `scripts/` in this
context meant `groundstation/scripts/export_vision_models.py` (a `groundstation`-repo script,
since the model files themselves are consumed from `/root/models/vision/` regardless of which
repo's code loads them — that path is shared/absolute, not repo-relative). No action needed here;
Task 9 loads `/root/models/vision/*.onnx` same as originally planned.

---

### Task 2: `cmake/FetchYOLOsCPP.cmake` — fetch YOLOs-CPP + ONNX Runtime, patch the thread cap

**Files:**
- Create: `/root/build_yolo/cmake/FetchYOLOsCPP.cmake`

**Interfaces:**
- Consumes: nothing from earlier tasks (first real code task).
- Produces: a macro `define_library_fetch_of_yolos_cpp()` — already called from
  `/root/build_yolo/CMakeLists.txt` (existing, do not edit that file) — that sets up two things
  Task 8's `vision/CMakeLists.txt` consumes:
  - `safe_cpm_add_package(NAME yolos-cpp ...)` -> CMake variable `${yolos-cpp_SOURCE_DIR}` (CPM's
    standard convention) pointing at the patched YOLOs-CPP header tree.
  - An `IMPORTED` target `ONNXRuntime::onnxruntime` (include dir + `.so`) from the extracted
    tarball, and a variable `ORT_INSTALL_DIR` (set inside the macro, and — because CMake macros
    don't create a new variable scope — still visible to whatever calls the macro) pointing at the
    extracted ONNX Runtime directory, needed later for `BUILD_RPATH`.

- [ ] **Step 1: Write the patch functions FIRST in the file (CMake needs functions defined before
      they're called — the macro that calls them, `define_library_fetch_of_yolos_cpp`, must come
      after these in the same file)**

```cmake
# /root/build_yolo/cmake/FetchYOLOsCPP.cmake
include(ExternalProject)

function(yolos_cpp_patch_file FILE_PATH OLD_TEXT NEW_TEXT LABEL)
    file(READ "${FILE_PATH}" FILE_CONTENT)
    string(FIND "${FILE_CONTENT}" "${OLD_TEXT}" MATCH_POS)
    if(MATCH_POS EQUAL -1)
        # Either already patched (idempotent re-configure) or upstream shifted.
        string(FIND "${FILE_CONTENT}" "${NEW_TEXT}" ALREADY_PATCHED_POS)
        if(ALREADY_PATCHED_POS EQUAL -1)
            message(FATAL_ERROR
                "[FetchYOLOsCPP] Patch target for '${LABEL}' not found in ${FILE_PATH}. "
                "Upstream YOLOs-CPP API likely changed — update cmake/FetchYOLOsCPP.cmake.")
        endif()
        return()
    endif()
    string(REPLACE "${OLD_TEXT}" "${NEW_TEXT}" PATCHED_CONTENT "${FILE_CONTENT}")
    file(WRITE "${FILE_PATH}" "${PATCHED_CONTENT}")
    message(STATUS "[FetchYOLOsCPP] Patched ${LABEL}")
endfunction()

function(yolos_cpp_patch_for_thread_cap SOURCE_DIR)
    # --- session_base.hpp: include the spin-disable config key header ---
    yolos_cpp_patch_file(
        "${SOURCE_DIR}/include/yolos/core/session_base.hpp"
        "#include <onnxruntime_cxx_api.h>\n#include <opencv2/opencv.hpp>"
        "#include <onnxruntime_cxx_api.h>\n#include <onnxruntime_session_options_config_keys.h>\n#include <opencv2/opencv.hpp>"
        "session_base.hpp includes"
    )

    # --- session_base.hpp: disable ORT intra-op spinning, cap inter-op threads too ---
    yolos_cpp_patch_file(
        "${SOURCE_DIR}/include/yolos/core/session_base.hpp"
        "        sessionOptions_.SetIntraOpNumThreads(threads);\n        sessionOptions_.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);"
        "        sessionOptions_.SetIntraOpNumThreads(threads);\n        sessionOptions_.SetInterOpNumThreads(threads);\n        sessionOptions_.AddConfigEntry(kOrtSessionOptionsConfigAllowIntraOpSpinning, \"0\");\n        sessionOptions_.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);"
        "session_base.hpp thread config"
    )

    # --- segmentation.hpp: forward numThreads, allow empty labelsPath (ONNX metadata fallback) ---
    yolos_cpp_patch_file(
        "${SOURCE_DIR}/include/yolos/tasks/segmentation.hpp"
        "    YOLOSegDetector(const std::string& modelPath,\n                    const std::string& labelsPath,\n                    bool useGPU = false)\n        : OrtSessionBase(modelPath, useGPU) {\n        \n        // Validate output count for segmentation models\n        if (numOutputNodes_ != 2) {\n            throw std::runtime_error(\"Expected 2 output nodes for segmentation model (output0 and output1)\");\n        }\n        \n        classNames_ = utils::getClassNames(labelsPath);"
        "    YOLOSegDetector(const std::string& modelPath,\n                    const std::string& labelsPath,\n                    bool useGPU = false,\n                    int numThreads = 0)\n        : OrtSessionBase(modelPath, useGPU, numThreads) {\n        \n        // Validate output count for segmentation models\n        if (numOutputNodes_ != 2) {\n            throw std::runtime_error(\"Expected 2 output nodes for segmentation model (output0 and output1)\");\n        }\n        \n        classNames_ = labelsPath.empty() ? getExportedClassNamesFromMetadata() : utils::getClassNames(labelsPath);"
        "segmentation.hpp constructor"
    )

    # --- depth.hpp: forward numThreads ---
    yolos_cpp_patch_file(
        "${SOURCE_DIR}/include/yolos/tasks/depth.hpp"
        "    explicit YOLODepthEstimator(const std::string& modelPath, bool useGPU = false)\n        : OrtSessionBase(modelPath, useGPU) {"
        "    explicit YOLODepthEstimator(const std::string& modelPath, bool useGPU = false, int numThreads = 0)\n        : OrtSessionBase(modelPath, useGPU, numThreads) {"
        "depth.hpp constructor"
    )
endfunction()
```

- [ ] **Step 2: Write the fetch macro (appended below the functions in the same file)**

```cmake
macro(DEFINE_LIBRARY_FETCH_OF_YOLOS_CPP)
    # -------------------------------------------------------------------
    # 1. ONNX Runtime — prebuilt CPU tarball (Linux x86_64). No upstream
    #    CMake target exists for it; YOLOs-CPP's own build.sh downloads the
    #    exact same release, we just automate the download instead of
    #    requiring a manually-set ONNXRUNTIME_DIR.
    # -------------------------------------------------------------------
    set(ORT_VERSION "1.20.1")
    set(ORT_ARCHIVE_NAME "onnxruntime-linux-x64-${ORT_VERSION}")
    set(ORT_URL "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/${ORT_ARCHIVE_NAME}.tgz")
    set(ORT_ROOT "${CMAKE_BINARY_DIR}/_deps/onnxruntime")
    set(ORT_ARCHIVE "${CMAKE_BINARY_DIR}/_deps/${ORT_ARCHIVE_NAME}.tgz")

    if(NOT EXISTS "${ORT_ROOT}/${ORT_ARCHIVE_NAME}/include/onnxruntime_cxx_api.h")
        file(MAKE_DIRECTORY "${ORT_ROOT}")
        if(NOT EXISTS "${ORT_ARCHIVE}")
            message(STATUS "[FetchYOLOsCPP] Downloading ONNX Runtime ${ORT_VERSION}...")
            file(DOWNLOAD "${ORT_URL}" "${ORT_ARCHIVE}"
                STATUS ORT_DOWNLOAD_STATUS
                SHOW_PROGRESS
            )
            list(GET ORT_DOWNLOAD_STATUS 0 ORT_DOWNLOAD_CODE)
            if(NOT ORT_DOWNLOAD_CODE EQUAL 0)
                message(FATAL_ERROR "[FetchYOLOsCPP] Failed to download ONNX Runtime: ${ORT_DOWNLOAD_STATUS}")
            endif()
        endif()
        message(STATUS "[FetchYOLOsCPP] Extracting ONNX Runtime...")
        file(ARCHIVE_EXTRACT INPUT "${ORT_ARCHIVE}" DESTINATION "${ORT_ROOT}")
    endif()

    set(ORT_INSTALL_DIR "${ORT_ROOT}/${ORT_ARCHIVE_NAME}")

    add_library(onnxruntime_imported SHARED IMPORTED GLOBAL)
    set_target_properties(onnxruntime_imported PROPERTIES
        IMPORTED_LOCATION             "${ORT_INSTALL_DIR}/lib/libonnxruntime.so"
        INTERFACE_INCLUDE_DIRECTORIES "${ORT_INSTALL_DIR}/include"
    )
    add_library(ONNXRuntime::onnxruntime ALIAS onnxruntime_imported)

    # -------------------------------------------------------------------
    # 2. YOLOs-CPP — headers only. Its own CMakeLists.txt defines no
    #    library target (only 10 demo executables) and FATAL_ERRORs
    #    without a pre-set ONNXRUNTIME_DIR, so DOWNLOAD_ONLY skips
    #    add_subdirectory entirely and we build our own target over its
    #    include/ tree.
    # -------------------------------------------------------------------
    safe_cpm_add_package(
        NAME           yolos-cpp
        GIT_REPOSITORY https://github.com/Geekgineer/YOLOs-CPP.git
        GIT_TAG        2b3b2f640a085c2be8e62d3566117c84d623cee0
        DOWNLOAD_ONLY  YES
    )

    yolos_cpp_patch_for_thread_cap("${yolos-cpp_SOURCE_DIR}")
endmacro()
```

- [ ] **Step 3: Configure the workspace root and confirm the patch runs**

```bash
cd /root/build_yolo
cmake -S . -B build -DVISION_BUILD_LIBRARY=OFF 2>&1 | tail -40
```

(`-DVISION_BUILD_LIBRARY=OFF` because `vision/CMakeLists.txt` doesn't exist until Task 8 — this
step only proves the fetch+patch macro itself works.)

Expected: configure succeeds, prints `[FetchYOLOsCPP] Downloading ONNX Runtime 1.20.1...`,
`[FetchYOLOsCPP] Extracting ONNX Runtime...`, then
`[FetchYOLOsCPP] Patched session_base.hpp includes`,
`[FetchYOLOsCPP] Patched session_base.hpp thread config`,
`[FetchYOLOsCPP] Patched segmentation.hpp constructor`,
`[FetchYOLOsCPP] Patched depth.hpp constructor`.

- [ ] **Step 4: Verify the patch actually landed in the fetched source**

```bash
grep -n "int numThreads = 0" build/_deps/yolos-cpp-src/include/yolos/tasks/segmentation.hpp
grep -n "int numThreads = 0" build/_deps/yolos-cpp-src/include/yolos/tasks/depth.hpp
grep -n "kOrtSessionOptionsConfigAllowIntraOpSpinning" build/_deps/yolos-cpp-src/include/yolos/core/session_base.hpp
```

Expected: one match each.

- [ ] **Step 5: Re-run configure to confirm idempotency (the patch must not double-apply or
      FATAL_ERROR on a second run)**

```bash
cd /root/build_yolo && cmake -S . -B build -DVISION_BUILD_LIBRARY=OFF 2>&1 | tail -15
```

Expected: succeeds again, no `FATAL_ERROR`, no duplicated patch text (the `ALREADY_PATCHED_POS`
branch in `yolos_cpp_patch_file` takes over silently).

- [ ] **Step 6: Commit**

```bash
cd /root/build_yolo
git add cmake/FetchYOLOsCPP.cmake
git commit -m "Fetch YOLOs-CPP + ONNX Runtime, patch thread-cap in place"
```

---

### Task 3: `vision/include/vision/coco_labels.hpp` — constexpr classId to label table

**Files:**
- Create: `/root/build_yolo/vision/include/vision/coco_labels.hpp`

**Interfaces:**
- Produces: `vision::coco_class_name(int classId) noexcept -> const char*` and
  `vision::coco_class_names_vector() -> std::vector<std::string>` — Task 5 uses both.

- [ ] **Step 1: Write the header**

```cpp
// vision/include/vision/coco_labels.hpp
#pragma once

#include <array>
#include <string>
#include <vector>

namespace vision {

inline constexpr std::array<const char*, 80> kCocoClassNames = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush"
};
static_assert(kCocoClassNames.size() == 80, "COCO has exactly 80 classes");

constexpr const char* coco_class_name(int classId) noexcept {
    return (classId >= 0 && classId < static_cast<int>(kCocoClassNames.size()))
        ? kCocoClassNames[static_cast<std::size_t>(classId)]
        : "unknown";
}

inline std::vector<std::string> coco_class_names_vector() {
    return std::vector<std::string>(kCocoClassNames.begin(), kCocoClassNames.end());
}

} // namespace vision
```

- [ ] **Step 2: Compile-check it standalone (this IS the test — a bad table fails these asserts at
      compile time)**

```cpp
// /tmp/coco_labels_check.cpp
#include "vision/coco_labels.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

int main() {
    assert(std::strcmp(vision::coco_class_name(0), "person") == 0);
    assert(std::strcmp(vision::coco_class_name(16), "dog") == 0);
    assert(std::strcmp(vision::coco_class_name(79), "toothbrush") == 0);
    assert(std::strcmp(vision::coco_class_name(-1), "unknown") == 0);
    assert(std::strcmp(vision::coco_class_name(80), "unknown") == 0);
    auto names = vision::coco_class_names_vector();
    assert(names.size() == 80);
    assert(names[16] == "dog");
    std::printf("coco_labels_check OK\n");
    return 0;
}
```

```bash
g++ -std=c++17 -I /root/build_yolo/vision/include /tmp/coco_labels_check.cpp -o /tmp/coco_labels_check \
    && /tmp/coco_labels_check
```

Expected: `coco_labels_check OK`.

- [ ] **Step 3: Commit**

```bash
cd /root/build_yolo
git add vision/include/vision/coco_labels.hpp
git commit -m "vision: constexpr COCO-80 classId->label table"
```

---

### Task 4: `vision/include/vision/perception_types.hpp` — canonical seam types

**Files:**
- Create: `/root/build_yolo/vision/include/vision/perception_types.hpp`

**Interfaces:**
- Consumes: `util2/C/base_type.h` (`f32/i32/u32/u64`).
- Produces: global (no namespace — matches `groundstation`'s existing
  `source/llm_to_action/fmu/fmu_node.hpp` stub exactly, so that repo's future `#include` swap is a
  drop-in) `TargetDetection` and `PerceptionSnapshot`, used by Tasks 5-7.

- [ ] **Step 1: Write the header**

```cpp
// vision/include/vision/perception_types.hpp
#pragma once

#include <util2/C/base_type.h>

using FixedStringType = char[32];

struct TargetDetection {
    FixedStringType label{"\0"};
    i32 bbox_xmin{0};
    i32 bbox_ymin{0};
    i32 bbox_xmax{0};
    i32 bbox_ymax{0};
    f32 confidence{0.0f};
    f32 median_depth_cm{0.0f};
};

struct PerceptionSnapshot {
    static constexpr u32 kMaxDetections = 16;
    TargetDetection dets[kMaxDetections];
    u32  count{0};
    u64  host_stamp_us{0};
    bool valid{false};
};
```

- [ ] **Step 2: Compile-check it standalone**

```bash
git clone --depth 1 https://github.com/inonitz/util2.git /tmp/util2-check
```

```cpp
// /tmp/perception_types_check.cpp
#include "vision/perception_types.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

int main() {
    TargetDetection d;
    assert(std::strcmp(d.label, "") == 0);
    assert(d.bbox_xmin == 0 && d.confidence == 0.0f && d.median_depth_cm == 0.0f);

    PerceptionSnapshot snap;
    assert(PerceptionSnapshot::kMaxDetections == 16);
    assert(snap.count == 0);
    assert(snap.valid == false);
    static_assert(sizeof(snap.dets) / sizeof(snap.dets[0]) == PerceptionSnapshot::kMaxDetections, "");

    std::printf("perception_types_check OK\n");
    return 0;
}
```

```bash
g++ -std=c++17 -I /root/build_yolo/vision/include -I /tmp/util2-check \
    /tmp/perception_types_check.cpp -o /tmp/perception_types_check \
    && /tmp/perception_types_check
```

Expected: `perception_types_check OK`.

- [ ] **Step 3: Commit**

```bash
cd /root/build_yolo
git add vision/include/vision/perception_types.hpp
git commit -m "vision: canonical TargetDetection/PerceptionSnapshot types"
```

---

### Task 5: `vision/include/vision/yolo_seg_engine.hpp` + `vision/source/yolo_seg_engine.cpp`

**Files:**
- Create: `/root/build_yolo/vision/include/vision/yolo_seg_engine.hpp`
- Create: `/root/build_yolo/vision/source/yolo_seg_engine.cpp`

**Interfaces:**
- Consumes: `vision::coco_class_names_vector()` (Task 3), patched
  `yolos::seg::YOLOSegDetector(modelPath, labelsPath, useGPU, numThreads)` (Task 2).
- Produces:
  ```cpp
  namespace vision {
  struct SegDetection { cv::Rect box; float conf; int classId; cv::Mat mask; };
  class YoloSegEngine {
  public:
      YoloSegEngine(const std::string& modelPath, int numThreads = 2, bool useGpu = false);
      ~YoloSegEngine();
      [[nodiscard]] bool ok() const noexcept;
      std::vector<SegDetection> segment(const cv::Mat& frame,
                                         float confThreshold = 0.25f,
                                         float iouThreshold = 0.45f);
  };
  }
  ```
  Task 7 (`fuse()`) consumes exactly this.

- [ ] **Step 1: Write the header**

```cpp
// vision/include/vision/yolo_seg_engine.hpp
#pragma once

#include <opencv2/core.hpp>
#include <memory>
#include <string>
#include <vector>

namespace vision {

struct SegDetection {
    cv::Rect box;
    float    conf{0.0f};
    int      classId{0};
    cv::Mat  mask;
};

class YoloSegEngine {
public:
    explicit YoloSegEngine(const std::string& modelPath, int numThreads = 2, bool useGpu = false);
    ~YoloSegEngine();

    YoloSegEngine(const YoloSegEngine&) = delete;
    YoloSegEngine& operator=(const YoloSegEngine&) = delete;

    [[nodiscard]] bool ok() const noexcept;

    std::vector<SegDetection> segment(const cv::Mat& frame,
                                       float confThreshold = 0.25f,
                                       float iouThreshold  = 0.45f);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    bool ok_{false};
};

} // namespace vision
```

- [ ] **Step 2: Write the implementation**

```cpp
// vision/source/yolo_seg_engine.cpp
#include "vision/yolo_seg_engine.hpp"
#include "vision/coco_labels.hpp"

#include "yolos/tasks/segmentation.hpp"

namespace vision {

struct YoloSegEngine::Impl {
    yolos::seg::YOLOSegDetector detector;

    Impl(const std::string& modelPath, int numThreads, bool useGpu)
        : detector(modelPath, /*labelsPath=*/std::string{}, useGpu, numThreads) {}
};

YoloSegEngine::YoloSegEngine(const std::string& modelPath, int numThreads, bool useGpu) {
    try {
        impl_ = std::make_unique<Impl>(modelPath, numThreads, useGpu);
        ok_ = true;
    } catch (...) {
        impl_.reset();
        ok_ = false;
    }
}

YoloSegEngine::~YoloSegEngine() = default;

bool YoloSegEngine::ok() const noexcept { return ok_; }

std::vector<SegDetection> YoloSegEngine::segment(const cv::Mat& frame,
                                                  float confThreshold,
                                                  float iouThreshold) {
    std::vector<SegDetection> out;
    if (!ok_ || frame.empty()) {
        return out;
    }
    try {
        std::vector<yolos::seg::Segmentation> raw =
            impl_->detector.segment(frame, confThreshold, iouThreshold);
        out.reserve(raw.size());
        for (const auto& r : raw) {
            SegDetection d;
            d.box     = cv::Rect(r.box.x, r.box.y, r.box.width, r.box.height);
            d.conf    = r.conf;
            d.classId = r.classId;
            d.mask    = r.mask;
            out.push_back(std::move(d));
        }
    } catch (...) {
        out.clear();
    }
    return out;
}

} // namespace vision
```

Note: `labelsPath = ""` triggers the Task 2 patch's `getExportedClassNamesFromMetadata()`
fallback — no `coco.names` file needed. `YoloSegEngine` never reads the detector's own
`classNames_`; `SegDetection::classId` is enough, `vision::coco_class_name()` (Task 3) does the
label lookup at fusion time (Task 7).

- [ ] **Step 3: Defer link-verification to Task 9** (can't fully link standalone without
      `libonnxruntime.so`/OpenCV `-l` flags assembled — Task 9's CMake target has them). Mark this
      step done once Task 9's build succeeds and exercises `YoloSegEngine`.

- [ ] **Step 4: Commit**

```bash
cd /root/build_yolo
git add vision/include/vision/yolo_seg_engine.hpp vision/source/yolo_seg_engine.cpp
git commit -m "vision: thread-capped YoloSegEngine wrapper"
```

---

### Task 6: `vision/include/vision/yolo_depth_engine.hpp` + `vision/source/yolo_depth_engine.cpp`

**Files:**
- Create: `/root/build_yolo/vision/include/vision/yolo_depth_engine.hpp`
- Create: `/root/build_yolo/vision/source/yolo_depth_engine.cpp`

**Interfaces:**
- Consumes: patched `yolos::depth::YOLODepthEstimator(modelPath, useGpu, numThreads)` (Task 2).
- Produces:
  ```cpp
  namespace vision {
  class YoloDepthEngine {
  public:
      YoloDepthEngine(const std::string& modelPath, int numThreads = 2, bool useGpu = false);
      ~YoloDepthEngine();
      [[nodiscard]] bool ok() const noexcept;
      cv::Mat estimate(const cv::Mat& frame); // CV_32FC1 meters, empty cv::Mat on failure
  };
  }
  ```
  Task 7 (`fuse()`) consumes exactly this.

- [ ] **Step 1: Write the header**

```cpp
// vision/include/vision/yolo_depth_engine.hpp
#pragma once

#include <opencv2/core.hpp>
#include <memory>
#include <string>

namespace vision {

class YoloDepthEngine {
public:
    explicit YoloDepthEngine(const std::string& modelPath, int numThreads = 2, bool useGpu = false);
    ~YoloDepthEngine();

    YoloDepthEngine(const YoloDepthEngine&) = delete;
    YoloDepthEngine& operator=(const YoloDepthEngine&) = delete;

    [[nodiscard]] bool ok() const noexcept;

    /// CV_32FC1 metric depth in meters, sized to the input frame. Empty on failure.
    cv::Mat estimate(const cv::Mat& frame);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    bool ok_{false};
};

} // namespace vision
```

- [ ] **Step 2: Write the implementation**

```cpp
// vision/source/yolo_depth_engine.cpp
#include "vision/yolo_depth_engine.hpp"

#include "yolos/tasks/depth.hpp"

namespace vision {

struct YoloDepthEngine::Impl {
    yolos::depth::YOLODepthEstimator estimator;

    Impl(const std::string& modelPath, int numThreads, bool useGpu)
        : estimator(modelPath, useGpu, numThreads) {}
};

YoloDepthEngine::YoloDepthEngine(const std::string& modelPath, int numThreads, bool useGpu) {
    try {
        impl_ = std::make_unique<Impl>(modelPath, numThreads, useGpu);
        ok_ = true;
    } catch (...) {
        impl_.reset();
        ok_ = false;
    }
}

YoloDepthEngine::~YoloDepthEngine() = default;

bool YoloDepthEngine::ok() const noexcept { return ok_; }

cv::Mat YoloDepthEngine::estimate(const cv::Mat& frame) {
    if (!ok_ || frame.empty()) {
        return cv::Mat();
    }
    try {
        return impl_->estimator.estimate(frame);
    } catch (...) {
        return cv::Mat();
    }
}

} // namespace vision
```

- [ ] **Step 3: Defer link-verification to Task 9** (same reasoning as Task 5, Step 3).

- [ ] **Step 4: Commit**

```bash
cd /root/build_yolo
git add vision/include/vision/yolo_depth_engine.hpp vision/source/yolo_depth_engine.cpp
git commit -m "vision: thread-capped YoloDepthEngine wrapper"
```

---

### Task 7: `vision/include/vision/perception_fusion.hpp` + `vision/source/perception_fusion.cpp`

**Files:**
- Create: `/root/build_yolo/vision/include/vision/perception_fusion.hpp`
- Create: `/root/build_yolo/vision/source/perception_fusion.cpp`

**Interfaces:**
- Consumes: `vision::YoloSegEngine::segment()` (Task 5), `vision::YoloDepthEngine::estimate()`
  (Task 6), `vision::coco_class_name()` (Task 3), `TargetDetection`/`PerceptionSnapshot` (Task 4).
- Produces: `vision::fuse(YoloSegEngine&, YoloDepthEngine&, const cv::Mat&, float, float) ->
  PerceptionSnapshot` — Task 9's test calls this directly.

- [ ] **Step 1: Write the header**

```cpp
// vision/include/vision/perception_fusion.hpp
#pragma once

#include "vision/perception_types.hpp"
#include "vision/yolo_depth_engine.hpp"
#include "vision/yolo_seg_engine.hpp"

#include <opencv2/core.hpp>

namespace vision {

/// Runs segmentation + depth on the same frame and fuses them into a
/// PerceptionSnapshot. median_depth_cm is sampled over each detection's mask
/// (falls back to its bbox if the mask is empty). valid is true whenever the
/// seg engine is ok() — even with zero detections in frame.
PerceptionSnapshot fuse(YoloSegEngine& segEngine,
                        YoloDepthEngine& depthEngine,
                        const cv::Mat& frame,
                        float confThreshold = 0.25f,
                        float iouThreshold  = 0.45f);

} // namespace vision
```

- [ ] **Step 2: Write the implementation**

```cpp
// vision/source/perception_fusion.cpp
#include "vision/perception_fusion.hpp"
#include "vision/coco_labels.hpp"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cmath>
#include <vector>

namespace vision {

namespace {

float medianDepthMeters(const cv::Mat& depth, const SegDetection& det) {
    if (depth.empty()) {
        return 0.0f;
    }
    cv::Rect bbox = det.box & cv::Rect(0, 0, depth.cols, depth.rows);
    if (bbox.width <= 0 || bbox.height <= 0) {
        return 0.0f;
    }

    std::vector<float> samples;
    samples.reserve(static_cast<size_t>(bbox.width) * static_cast<size_t>(bbox.height));

    const bool useMask = !det.mask.empty() &&
                          det.mask.size() == depth.size() &&
                          det.mask.type() == CV_8UC1;

    for (int y = bbox.y; y < bbox.y + bbox.height; ++y) {
        const float* depthRow = depth.ptr<float>(y);
        const uchar* maskRow  = useMask ? det.mask.ptr<uchar>(y) : nullptr;
        for (int x = bbox.x; x < bbox.x + bbox.width; ++x) {
            if (useMask && maskRow[x] == 0) {
                continue;
            }
            const float v = depthRow[x];
            if (v > 0.0f && std::isfinite(v)) {
                samples.push_back(v);
            }
        }
    }

    if (samples.empty()) {
        return 0.0f;
    }
    std::sort(samples.begin(), samples.end());
    return samples[samples.size() / 2];
}

void copyLabel(FixedStringType& label, const char* src) {
    std::snprintf(label, sizeof(FixedStringType), "%s", src);
}

} // namespace

PerceptionSnapshot fuse(YoloSegEngine& segEngine,
                        YoloDepthEngine& depthEngine,
                        const cv::Mat& frame,
                        float confThreshold,
                        float iouThreshold) {
    PerceptionSnapshot snapshot;
    snapshot.host_stamp_us = static_cast<u64>(
        std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now().time_since_epoch())
            .count());

    if (!segEngine.ok()) {
        return snapshot;
    }

    std::vector<SegDetection> detections = segEngine.segment(frame, confThreshold, iouThreshold);
    cv::Mat depth = depthEngine.ok() ? depthEngine.estimate(frame) : cv::Mat();

    const u32 n = std::min(static_cast<u32>(detections.size()), PerceptionSnapshot::kMaxDetections);
    for (u32 i = 0; i < n; ++i) {
        const SegDetection& d = detections[i];
        TargetDetection& out  = snapshot.dets[i];

        copyLabel(out.label, coco_class_name(d.classId));
        out.bbox_xmin = d.box.x;
        out.bbox_ymin = d.box.y;
        out.bbox_xmax = d.box.x + d.box.width;
        out.bbox_ymax = d.box.y + d.box.height;
        out.confidence = d.conf;
        out.median_depth_cm = medianDepthMeters(depth, d) * 100.0f;
    }

    snapshot.count = n;
    snapshot.valid = true;
    return snapshot;
}

} // namespace vision
```

- [ ] **Step 3: Defer the run-with-real-models check to Task 9** (this is the function Task 9's
      `main()` calls directly).

- [ ] **Step 4: Commit**

```bash
cd /root/build_yolo
git add vision/include/vision/perception_fusion.hpp vision/source/perception_fusion.cpp
git commit -m "vision: fuse() seg+depth into PerceptionSnapshot"
```

---

### Task 8: `vision/CMakeLists.txt` — the `Perception::vision` library target

**Files:**
- Create: `/root/build_yolo/vision/CMakeLists.txt`

**Interfaces:**
- Consumes: `define_library_fetch_of_yolos_cpp()` (Task 2, already called from the repo root
  `CMakeLists.txt` before `add_subdirectory(vision)` runs — do not call it again here),
  `UTIL2::util2` (already CPM-fetched by the repo root), `find_package(OpenCV REQUIRED)` (already
  called by the repo root).
- Produces: target alias `Perception::vision`. Consumed by Task 9's test target in this same file,
  and — later, out of scope for this plan — by `groundstation` once it starts consuming this repo.

- [ ] **Step 1: Write the CMakeLists**

```cmake
# vision/CMakeLists.txt
project(vision
    VERSION 0.1.0
    DESCRIPTION "YOLO26 segmentation + metric depth perception library"
    LANGUAGES CXX
)

add_library(${PROJECT_NAME} STATIC
    include/vision/coco_labels.hpp
    include/vision/perception_types.hpp
    include/vision/yolo_seg_engine.hpp
    source/yolo_seg_engine.cpp
    include/vision/yolo_depth_engine.hpp
    source/yolo_depth_engine.cpp
    include/vision/perception_fusion.hpp
    source/perception_fusion.cpp
)
add_library(Perception::vision ALIAS ${PROJECT_NAME})

target_include_directories(${PROJECT_NAME} PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${yolos-cpp_SOURCE_DIR}/include
)

target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_17)

target_link_libraries(${PROJECT_NAME} PUBLIC
    UTIL2::util2
    ONNXRuntime::onnxruntime
    opencv_core
    opencv_imgproc
    opencv_imgcodecs
)

set_target_properties(${PROJECT_NAME} PROPERTIES
    BUILD_RPATH "${ORT_INSTALL_DIR}/lib"
)

if(VISION_BUILD_TESTS)
    add_executable(perception_test test/perception_test.cpp)
    target_link_libraries(perception_test PRIVATE Perception::vision)
    set_target_properties(perception_test PROPERTIES
        BUILD_RPATH "${ORT_INSTALL_DIR}/lib"
    )
    configure_file(
        "${yolos-cpp_SOURCE_DIR}/data/dog.jpg"
        "${CMAKE_CURRENT_BINARY_DIR}/dog.jpg"
        COPYONLY
    )
endif()
```

- [ ] **Step 2: Configure and build from the repo root (this is the first time the whole workspace
      composes: root `CMakeLists.txt` -> `FetchYOLOsCPP` -> this file)**

```bash
cd /root/build_yolo
cmake -S . -B build -DVISION_BUILD_TESTS=OFF 2>&1 | tail -40
cmake --build build -j 2>&1 | tail -60
```

Expected: configure succeeds (prints the `[FetchYOLOsCPP]` lines again — idempotent), `vision`
static library builds with no errors. (`VISION_BUILD_TESTS=OFF` here because `test/perception_test.cpp`
doesn't exist until Task 9 — expected, not a bug.)

- [ ] **Step 3: Commit**

```bash
cd /root/build_yolo
git add vision/CMakeLists.txt
git commit -m "vision: Perception::vision CMake target"
```

---

### Task 9: Standalone correctness test + fp32/int8/int4 x 1/2/4-thread benchmark

**Files:**
- Create: `/root/build_yolo/vision/test/perception_test.cpp`

**Interfaces:**
- Consumes: everything from Tasks 3-7 (`vision::fuse`, `vision::YoloSegEngine`,
  `vision::YoloDepthEngine`, `vision::coco_class_name`, `TargetDetection`, `PerceptionSnapshot`).
- Produces: nothing further downstream — this is the leaf verification task.

- [ ] **Step 1: Write the test**

```cpp
// vision/test/perception_test.cpp
/*
    Correctness + latency/thread benchmark for the vision/ perception library.
    Build:
        cd /root/build_yolo
        cmake -S . -B build -DVISION_BUILD_TESTS=ON
        cmake --build build -j
        ./build/vision/perception_test /root/models/vision
    (test image is copied to the same directory as the binary by CMake — no arg needed
    unless you want a different image as argv[2])
*/
#include "vision/coco_labels.hpp"
#include "vision/perception_fusion.hpp"
#include "vision/perception_types.hpp"
#include "vision/yolo_depth_engine.hpp"
#include "vision/yolo_seg_engine.hpp"

#include <opencv2/imgcodecs.hpp>

#include <algorithm>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <numeric>
#include <string>
#include <vector>

namespace {

struct Latency {
    double meanMs{0.0};
    double p95Ms{0.0};
};

template <typename Fn>
Latency benchmark(Fn&& fn, int warmup, int iters) {
    for (int i = 0; i < warmup; ++i) fn();
    std::vector<double> samples;
    samples.reserve(static_cast<size_t>(iters));
    for (int i = 0; i < iters; ++i) {
        const auto start = std::chrono::steady_clock::now();
        fn();
        const auto end = std::chrono::steady_clock::now();
        samples.push_back(std::chrono::duration<double, std::milli>(end - start).count());
    }
    std::sort(samples.begin(), samples.end());
    Latency out;
    out.meanMs = std::accumulate(samples.begin(), samples.end(), 0.0) /
                 static_cast<double>(samples.size());
    const size_t p95Index = static_cast<size_t>(0.95 * static_cast<double>(samples.size() - 1));
    out.p95Ms = samples[p95Index];
    return out;
}

std::string modelPath(const std::string& modelsDir, const std::string& stem, const std::string& variant) {
    const std::string suffix = (variant == "fp32") ? "" : ("." + variant);
    return modelsDir + "/" + stem + suffix + ".onnx";
}

bool fileExists(const std::string& path) {
    return std::ifstream(path).good();
}

} // namespace

int main(int argc, char** argv) {
    const std::string modelsDir = argc > 1 ? argv[1] : "/root/models/vision";
    const std::string imagePath = argc > 2 ? argv[2] : "dog.jpg";

    cv::Mat frame = cv::imread(imagePath);
    if (frame.empty()) {
        std::fprintf(stderr, "FAIL: could not load test image '%s'\n", imagePath.c_str());
        return 1;
    }
    std::printf("Loaded test image %s (%dx%d)\n", imagePath.c_str(), frame.cols, frame.rows);

    // --- Correctness: fp32, 2 threads ---
    {
        vision::YoloSegEngine seg(modelPath(modelsDir, "yolo26n-seg", "fp32"), /*numThreads=*/2);
        vision::YoloDepthEngine depth(modelPath(modelsDir, "yolo26n-depth", "fp32"), /*numThreads=*/2);

        assert(seg.ok() && "seg engine failed to load fp32 model");
        assert(depth.ok() && "depth engine failed to load fp32 model");

        std::vector<vision::SegDetection> detections = seg.segment(frame);
        assert(!detections.empty() && "expected at least one detection on the test image");
        for (const auto& d : detections) {
            assert(d.box.x >= 0 && d.box.y >= 0);
            assert(d.box.x + d.box.width  <= frame.cols);
            assert(d.box.y + d.box.height <= frame.rows);
            assert(d.conf > 0.0f && d.conf <= 1.0f);
        }
        std::printf("Correctness: seg found %zu detection(s), first label='%s' conf=%.3f\n",
                    detections.size(), vision::coco_class_name(detections.front().classId),
                    detections.front().conf);

        cv::Mat depthMap = depth.estimate(frame);
        assert(!depthMap.empty());
        assert(depthMap.type() == CV_32FC1);
        double minDepth = 0.0, maxDepth = 0.0;
        cv::minMaxLoc(depthMap, &minDepth, &maxDepth);
        assert(std::isfinite(minDepth) && std::isfinite(maxDepth) && maxDepth > 0.0);
        std::printf("Correctness: depth map %dx%d, range [%.3f, %.3f] m\n",
                    depthMap.cols, depthMap.rows, minDepth, maxDepth);

        PerceptionSnapshot snapshot = vision::fuse(seg, depth, frame);
        assert(snapshot.valid);
        assert(snapshot.count > 0);
        for (u32 i = 0; i < snapshot.count; ++i) {
            assert(snapshot.dets[i].median_depth_cm > 0.0f);
        }
        std::printf("Correctness: fused PerceptionSnapshot count=%u first_depth_cm=%.1f\n",
                    snapshot.count, snapshot.dets[0].median_depth_cm);
    }
    std::printf("ALL CORRECTNESS CHECKS PASSED\n\n");

    // --- Benchmark: fp32/int8/int4 x 1/2/4 threads ---
    const std::vector<std::string> variants = {"fp32", "int8", "int4"};
    const std::vector<int> threadCounts = {1, 2, 4};

    std::printf("%-8s %-8s %10s %10s %10s %10s\n",
                "task", "variant", "threads", "mean_ms", "p95_ms", "vs_target");
    for (const auto& variant : variants) {
        const std::string segPath = modelPath(modelsDir, "yolo26n-seg", variant);
        if (!fileExists(segPath)) {
            std::printf("seg      %-8s  (model file missing, skipped: %s)\n", variant.c_str(), segPath.c_str());
        } else {
            for (int threads : threadCounts) {
                vision::YoloSegEngine seg(segPath, threads);
                if (!seg.ok()) {
                    std::printf("seg      %-8s %10d  (failed to load)\n", variant.c_str(), threads);
                    continue;
                }
                Latency lat = benchmark([&] { seg.segment(frame); }, /*warmup=*/3, /*iters=*/20);
                const char* verdict = lat.meanMs <= 33.0 ? "MEETS" : "MISSES";
                std::printf("seg      %-8s %10d %10.2f %10.2f %10s (target ~33ms/30Hz)\n",
                            variant.c_str(), threads, lat.meanMs, lat.p95Ms, verdict);
            }
        }

        const std::string depthPath = modelPath(modelsDir, "yolo26n-depth", variant);
        if (!fileExists(depthPath)) {
            std::printf("depth    %-8s  (model file missing, skipped: %s)\n", variant.c_str(), depthPath.c_str());
            continue;
        }
        for (int threads : threadCounts) {
            vision::YoloDepthEngine depth(depthPath, threads);
            if (!depth.ok()) {
                std::printf("depth    %-8s %10d  (failed to load)\n", variant.c_str(), threads);
                continue;
            }
            Latency lat = benchmark([&] { depth.estimate(frame); }, /*warmup=*/3, /*iters=*/20);
            const char* verdict = lat.meanMs <= 25.0 ? "MEETS" : "MISSES";
            std::printf("depth    %-8s %10d %10.2f %10.2f %10s (target ~25ms/40Hz)\n",
                        variant.c_str(), threads, lat.meanMs, lat.p95Ms, verdict);
        }
    }

    return 0;
}
```

- [ ] **Step 2: Build**

```bash
cd /root/build_yolo
cmake -S . -B build -DVISION_BUILD_TESTS=ON 2>&1 | tail -30
cmake --build build -j 2>&1 | tail -60
```

Expected: builds `vision` and `perception_test` with no errors. (This is also where Task 5 Step 3
and Task 6 Step 3's deferred link-verification actually happens — if either engine wrapper has a
signature mismatch against the patched YOLOs-CPP headers, it fails here.)

- [ ] **Step 3: Run the correctness portion, confirm it passes before looking at the benchmark**

```bash
cd /root/build_yolo/build/vision
LD_LIBRARY_PATH=$(find /root/build_yolo/build/_deps/onnxruntime -name lib -type d | head -1):$LD_LIBRARY_PATH \
./perception_test /root/models/vision
```

Expected: `Loaded test image dog.jpg (...)`, three `Correctness: ...` lines, then
`ALL CORRECTNESS CHECKS PASSED`. If any `assert` fires, the test aborts — fix the underlying
engine/fusion code (not the test) and rerun before moving on.

- [ ] **Step 4: Confirm the benchmark table printed and read the numbers honestly**

Same run's remaining output is the benchmark table. Do not edit the test to make numbers look
better. Copy the full table into the final handoff report verbatim, plus a one-line recommended
variant+thread-count call (lowest mean_ms that still `MEETS`, or if none `MEETS`, the closest one
— state plainly that the target wasn't hit, per the spec's instruction to stop and let a human
reassess rather than over-optimize).

- [ ] **Step 5: Confirm the thread cap actually bounds cores used (not spawning a thread per
      core)** — run once under monitoring:

```bash
cd /root/build_yolo/build/vision && \
LD_LIBRARY_PATH=$(find /root/build_yolo/build/_deps/onnxruntime -name lib -type d | head -1):$LD_LIBRARY_PATH \
./perception_test /root/models/vision & PID=$!; sleep 2; \
grep Threads /proc/$PID/status; ps -o pid,nlwp,psr,comm -p $PID; wait $PID
```

Expected: thread count in `/proc/$PID/status` stays low (roughly ORT intra/inter-op threads + a
couple of housekeeping threads, not e.g. 16). Report this observation alongside the benchmark
table — it's the empirical check that `SetIntraOpNumThreads`/spin-disable actually took effect.

- [ ] **Step 6: Commit**

```bash
cd /root/build_yolo
git add vision/test/perception_test.cpp
git commit -m "vision: standalone correctness test + fp32/int8/int4 x 1/2/4-thread benchmark"
```

---

### Task 10: Full-workspace top-level build check

**Files:** none created/modified — verification only.

**Interfaces:** none new.

- [ ] **Step 1: Confirm a completely clean top-level configure+build works end to end** (proves
      someone who clones this repo fresh, with nothing pre-fetched, gets a working library+test
      purely from `cmake -S . -B build`)

```bash
rm -rf /root/build_yolo/build
cd /root/build_yolo
cmake -S . -B build 2>&1 | tail -60
cmake --build build -j 2>&1 | tail -60
```

Expected: succeeds top to bottom — ONNX Runtime download+extract, YOLOs-CPP fetch+patch, util2
fetch, `vision` library, `perception_test` executable, no manual intervention. `VISION_BUILD_TESTS`
defaults to `ON` here (top-level build), so this also rebuilds the test target from Task 9.

- [ ] **Step 2: Run the test once more from this clean build to confirm nothing about the fresh
      configure changed behavior**

```bash
cd /root/build_yolo/build/vision
LD_LIBRARY_PATH=$(find /root/build_yolo/build/_deps/onnxruntime -name lib -type d | head -1):$LD_LIBRARY_PATH \
./perception_test /root/models/vision
```

Expected: same `ALL CORRECTNESS CHECKS PASSED` result as Task 9.

- [ ] **Step 3: No commit** — this task only verifies; nothing here should have been modified.

---

## Handoff Report (fill in from Task 9's actual output, not before)

When all 10 tasks are done, report:
1. Exact build/run commands (Task 9, Steps 2-3).
2. Correctness test result (pass/fail, from Task 9 Step 3's actual terminal output).
3. Full benchmark table (Task 9 Step 4's actual terminal output, verbatim).
4. Thread-cap verification observation (Task 9 Step 5).
5. Recommended variant + thread count, stated plainly against the ~25 ms depth / ~33 ms seg
   targets — including if neither is met.
6. Task 1's int4 quantization outcome (succeeded or failed, and why if it failed) — from the
   human partner's manual run.
7. Task 10's clean top-level build result.
8. **Not done, and intentionally out of scope:** consuming this repo from `groundstation` (the
   `safe_cpm_add_package(NAME vision ...)` block + linking `Perception::vision` into the FMU).
   That's a separate future step.
