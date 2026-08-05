# Perception Library (YOLO26 seg+detect + metric depth) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `source/llm_to_action/vision/` — a ROS-free C++17 library that wraps YOLOs-CPP's
YOLO26 instance segmentation + monocular metric depth, fuses them into a `PerceptionSnapshot`, and
ships as `Perception::vision` via CMake — plus a standalone (no ROS/sim) correctness + latency
benchmark test.

**Architecture:** `vision/CMakeLists.txt` is a **self-sufficient CMake project** (its own
`project()`, its own CPM include) so it can be configured and built completely on its own —
`cmake -S source/llm_to_action/vision -B <dir>` — with zero ROS packages in scope, and *also*
composes cleanly via `add_subdirectory(vision)` when the full ROS workspace builds it. It depends
on: YOLOs-CPP (fetched headers-only via CPM, `DOWNLOAD_ONLY`, pinned to the exact commit
`nurmilkov/BUILD_YOLO` validated YOLO26 support against), a prebuilt ONNX Runtime tarball (fetched
+ extracted by our own `cmake/FetchYOLOsCPP.cmake`), and OpenCV. Two upstream gaps get patched
**in place, in CMake** (`string(REPLACE)` on the CPM-fetched source, not hand-vendored copies):
YOLOs-CPP's seg/depth constructors don't forward a thread count to ONNX Runtime, and don't disable
ORT's busy-wait spinning — both matter because this will run in-process with a 20 Hz control loop
on shared cores. `YoloSegEngine`/`YoloDepthEngine` wrap the two patched YOLOs-CPP classes behind a
non-throwing API (YOLOs-CPP throws internally; this library's boundary does not); `fuse()` runs
both on one frame and samples the depth map over each detection's mask to fill
`PerceptionSnapshot`.

**Tech Stack:** C++17, OpenCV 4.6 (`opencv_core`/`imgproc`/`imgcodecs`), ONNX Runtime 1.20.1 (CPU),
YOLOs-CPP (`Geekgineer/YOLOs-CPP` @ `2b3b2f640a085c2be8e62d3566117c84d623cee0`), CMake 3.16+, CPM
(`cmake/FetchCPM.cmake`, already in this repo), `util2/C/base_type.h` fixed-width types.

## Global Constraints

- **No exceptions cross the `vision/` public API.** YOLOs-CPP throws (`std::runtime_error`,
  `std::invalid_argument`) internally — every engine wrapper catches at its own boundary and
  exposes `bool ok()` instead. Internal `try`/`catch` is fine; nothing propagates out.
- **C++17. `util2/C/base_type.h` fixed-width types** (`f32/i32/u32/u64`) for the two canonical seam
  structs. `FixedStringType` = `char[32]`, matching `fmu/fmu_node.hpp`'s existing stub exactly.
- **Concrete structs only — no `virtual`, no `std::variant`.**
- **Do not edit** `source/llm_to_action/fmu/*`, the control loop, the backend, VLM plumbing, or any
  sim script. Blast radius is `source/llm_to_action/vision/` + `cmake/FetchYOLOsCPP.cmake` + the
  minimal wiring lines in the root `CMakeLists.txt` and `source/llm_to_action/CMakeLists.txt`
  (one `include()`, one `add_subdirectory()`).
- **Every engine takes a `numThreads` budget at construction** (small default: 2) and every ONNX
  Runtime session must have spinning disabled. This is a correctness requirement, not a nice-to-have
  — unpatched YOLOs-CPP silently ignores thread caps (verified: BUILD_YOLO's own
  `DepthEstimatorConfig::intraOpThreads` is dropped on the YOLO26 path too).
- **CPU inference only.** No GPU/CUDA code paths need to work; `useGPU` stays `false` everywhere
  fp32/int8/int4 model variants are selected purely by file path suffix (`""`, `.int8`, `.int4`).
- Full spec: `docs/superpowers/specs/2026-08-05-perception-library-design.md`. Read it before
  starting — this plan implements it exactly, including the two later addenda (verified CMake
  mechanics, constexpr label table).

---

## File Structure

```
cmake/FetchYOLOsCPP.cmake                          # NEW — ORT tarball fetch, YOLOs-CPP CPM fetch, in-place patch macro
CMakeLists.txt                                     # MODIFIED — include(cmake/FetchYOLOsCPP.cmake)
source/llm_to_action/CMakeLists.txt                # MODIFIED — add_subdirectory(vision)
source/llm_to_action/vision/
  CMakeLists.txt                                   # NEW — self-sufficient CMake project, Perception::vision
  perception_types.hpp                             # NEW — TargetDetection, PerceptionSnapshot (canonical seam types)
  coco_labels.hpp                                  # NEW — constexpr COCO-80 classId -> label
  yolo_seg_engine.hpp / .cpp                        # NEW — thread-capped wrapper over yolos::seg::YOLOSegDetector
  yolo_depth_engine.hpp / .cpp                      # NEW — thread-capped wrapper over yolos::depth::YOLODepthEstimator
  perception_fusion.hpp / .cpp                      # NEW — fuse(): seg + depth -> PerceptionSnapshot
  test/perception_test.cpp                          # NEW — standalone correctness + benchmark (no ROS)
```

---

### Task 1: Fetch + export + quantize the YOLO26 models

**Files:**
- Create (outside the repo, not committed): `/root/models/vision/yolo26n-seg.onnx`,
  `yolo26n-seg.int8.onnx`, `yolo26n-seg.int4.onnx`, `yolo26n-depth.onnx`,
  `yolo26n-depth.int8.onnx`, `yolo26n-depth.int4.onnx`
- Create (committed, reusable): `scripts/export_vision_models.py`

**Interfaces:**
- Produces: the 6 `.onnx` files under `/root/models/vision/` that every later task's tests load by
  path. No code interface — this is a data-prep task.

- [ ] **Step 1: Install the export toolchain in an isolated location (not the repo, not system
      packages)**

```bash
pip3 install --break-system-packages --target /root/.local/vision-export-tools ultralytics onnxruntime
```

Confirm it landed and YOLO26 checkpoints are real (already verified in this session — restate the
check so the executing agent doesn't skip it):

```bash
PYTHONPATH=/root/.local/vision-export-tools python3 -c "
from ultralytics.utils.downloads import GITHUB_ASSETS_NAMES
assert 'yolo26n-seg.pt' in GITHUB_ASSETS_NAMES
assert 'yolo26n-depth.pt' in GITHUB_ASSETS_NAMES
print('yolo26n-seg.pt and yolo26n-depth.pt confirmed in ultralytics asset list')
"
```

Expected: prints the confirmation line, no `AssertionError`.

- [ ] **Step 2: Write the export/quantize script**

```python
# scripts/export_vision_models.py
import pathlib
from ultralytics import YOLO
from onnxruntime.quantization import quantize_dynamic, QuantType

OUT_DIR = pathlib.Path("/root/models/vision")
OUT_DIR.mkdir(parents=True, exist_ok=True)

CHECKPOINTS = {
    "yolo26n-seg": "yolo26n-seg.pt",
    "yolo26n-depth": "yolo26n-depth.pt",
}

for stem, checkpoint in CHECKPOINTS.items():
    print(f"--- exporting {checkpoint} ---")
    model = YOLO(checkpoint)
    exported_path = model.export(format="onnx", dynamic=True)
    fp32_path = OUT_DIR / f"{stem}.onnx"
    pathlib.Path(exported_path).rename(fp32_path)
    print(f"fp32 -> {fp32_path}")

    int8_path = OUT_DIR / f"{stem}.int8.onnx"
    quantize_dynamic(str(fp32_path), str(int8_path), weight_type=QuantType.QInt8)
    print(f"int8 -> {int8_path}")

    try:
        import onnx
        from onnxruntime.quantization.matmul_4bits_quantizer import MatMul4BitsQuantizer

        int4_path = OUT_DIR / f"{stem}.int4.onnx"
        q = MatMul4BitsQuantizer(onnx.load(str(fp32_path)), block_size=32, is_symmetric=True)
        q.process()
        q.model.save_model_to_file(str(int4_path), use_external_data_format=False)
        print(f"int4 -> {int4_path}")
    except Exception as exc:  # noqa: BLE001 - best-effort per spec, report and move on
        print(f"int4 quantization failed for {stem}: {exc}")

print("done")
```

- [ ] **Step 3: Run it**

```bash
cd /root/groundstation
PYTHONPATH=/root/.local/vision-export-tools python3 scripts/export_vision_models.py
```

Expected: `--- exporting yolo26n-seg.pt ---` ... `fp32 ->` / `int8 ->` / `int4 -> (or a printed
failure, that's fine — report it, don't block on it)`, same for `yolo26n-depth.pt`, ending in
`done`.

- [ ] **Step 4: Verify the files landed**

```bash
ls -la /root/models/vision/
```

Expected: at minimum `yolo26n-seg.onnx`, `yolo26n-seg.int8.onnx`, `yolo26n-depth.onnx`,
`yolo26n-depth.int8.onnx` present and non-empty (int4 variants best-effort — note in the final
report whether they landed).

Commit `scripts/export_vision_models.py` (the model files themselves stay outside the repo
under `/root/models/vision/` — do not commit those).

---

### Task 2: `cmake/FetchYOLOsCPP.cmake` — fetch YOLOs-CPP + ONNX Runtime, patch the thread cap

**Files:**
- Create: `cmake/FetchYOLOsCPP.cmake`
- Modify: `CMakeLists.txt:20` (add `include(cmake/FetchYOLOsCPP.cmake)` next to the existing
  `include(cmake/FetchLLamaCPP.cmake)` line)

**Interfaces:**
- Produces: a macro `define_library_fetch_of_yolos_cpp()` that, when called, sets up two things
  any later `vision/CMakeLists.txt` consumes:
  - `safe_cpm_add_package(NAME yolos-cpp ...)` → CMake variable `${yolos-cpp_SOURCE_DIR}`
    (CPM's standard convention, same as `${moodycamel_readerwriterqueue_SOURCE_DIR}` used
    elsewhere in this repo) pointing at the patched YOLOs-CPP header tree.
  - An `IMPORTED` target `ONNXRuntime::onnxruntime` (include dir + `.so`) from the extracted
    tarball.

- [ ] **Step 1: Write the macro — ONNX Runtime tarball fetch**

```cmake
# cmake/FetchYOLOsCPP.cmake
include(ExternalProject)

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

- [ ] **Step 2: Write the in-place patch macro (exact byte-for-byte strings — verified against the
      pinned commit in this session)**

```cmake
# Appended to cmake/FetchYOLOsCPP.cmake, above DEFINE_LIBRARY_FETCH_OF_YOLOS_CPP
# (macros must be defined before use in the same file — put this one first)

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

Put both functions **above** `DEFINE_LIBRARY_FETCH_OF_YOLOS_CPP` in the file (CMake needs
functions defined before they're called — reorder Step 1's macro to come after Step 2's functions
in the actual file).

- [ ] **Step 3: Wire it into the root `CMakeLists.txt`**

Add one line next to the existing `include(cmake/FetchLLamaCPP.cmake)`:

```cmake
include(cmake/FetchLLamaCPP.cmake)
include(cmake/FetchYOLOsCPP.cmake)
```

(Only the `include()` — do **not** call `define_library_fetch_of_yolos_cpp()` from the root
`CMakeLists.txt`. `vision/CMakeLists.txt` calls it itself, so `vision/` stays self-sufficient
whether it's configured standalone or via `add_subdirectory`.)

- [ ] **Step 4: Smoke-test the fetch + patch in isolation**

```bash
mkdir -p /tmp/yolos-fetch-test
cat > /tmp/yolos-fetch-test/CMakeLists.txt <<'EOF'
cmake_minimum_required(VERSION 3.16)
project(yolos_fetch_smoke_test LANGUAGES CXX)
include(${CMAKE_CURRENT_LIST_DIR}/../../root/groundstation/cmake/FetchCPM.cmake)
include_cpm()
include(${CMAKE_CURRENT_LIST_DIR}/../../root/groundstation/cmake/FetchYOLOsCPP.cmake)
define_library_fetch_of_yolos_cpp()
message(STATUS "yolos-cpp source dir: ${yolos-cpp_SOURCE_DIR}")
EOF
cmake -S /tmp/yolos-fetch-test -B /tmp/yolos-fetch-test/build 2>&1 | tail -30
```

Expected: configure succeeds, prints `[FetchYOLOsCPP] Patched session_base.hpp includes`,
`[FetchYOLOsCPP] Patched session_base.hpp thread config`,
`[FetchYOLOsCPP] Patched segmentation.hpp constructor`,
`[FetchYOLOsCPP] Patched depth.hpp constructor`, then `yolos-cpp source dir: ...`.

- [ ] **Step 5: Verify the patched files actually compile against the constructor signatures we
      rely on**

```bash
grep -n "int numThreads = 0" $(cmake --build /tmp/yolos-fetch-test/build 2>&1 >/dev/null; \
  find /tmp/yolos-fetch-test/build -path "*_deps/yolos-cpp-src/include/yolos/tasks/segmentation.hpp") \
  || find / -path "*yolos-cpp-src/include/yolos/tasks/segmentation.hpp" -exec grep -n "int numThreads = 0" {} \;
```

Expected: at least one match (`YOLOSegDetector(...` with the new `int numThreads = 0` parameter
visible).

- [ ] **Step 6: Commit**

```bash
rtk git add cmake/FetchYOLOsCPP.cmake CMakeLists.txt
rtk git commit -m "vision: fetch YOLOs-CPP + ONNX Runtime, patch thread-cap in place"
```

---

### Task 3: `vision/coco_labels.hpp` — constexpr classId → label table

**Files:**
- Create: `source/llm_to_action/vision/coco_labels.hpp`
- Test: inline `static_assert`s in the same header (header-only, no separate test binary needed —
  it's exercised for real by Task 9's integration test)

**Interfaces:**
- Produces: `vision::coco_class_name(int classId) noexcept -> const char*` and
  `vision::coco_class_names_vector() -> std::vector<std::string>` — Task 5 uses both.

- [ ] **Step 1: Write the header**

```cpp
// source/llm_to_action/vision/coco_labels.hpp
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
#include "coco_labels.hpp"
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
g++ -std=c++17 -I source/llm_to_action/vision /tmp/coco_labels_check.cpp -o /tmp/coco_labels_check \
    && /tmp/coco_labels_check
```

Expected: `coco_labels_check OK`.

- [ ] **Step 3: Commit**

```bash
rtk git add source/llm_to_action/vision/coco_labels.hpp
rtk git commit -m "vision: constexpr COCO-80 classId->label table"
```

---

### Task 4: `vision/perception_types.hpp` — canonical seam types

**Files:**
- Create: `source/llm_to_action/vision/perception_types.hpp`

**Interfaces:**
- Consumes: `util2/C/base_type.h` (`f32/i32/u32/u64`) — fetched via CPM at the workspace level;
  for the standalone compile check in this task, point `-I` at wherever CPM caches it (see Step 2).
- Produces: global (no namespace — matches the existing stub in `fmu/fmu_node.hpp` exactly, so a
  future `#include` swap is a drop-in) `TargetDetection` and `PerceptionSnapshot`, used by Tasks
  5–7.

- [ ] **Step 1: Write the header**

```cpp
// source/llm_to_action/vision/perception_types.hpp
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

First locate where CPM cached `util2` from a prior configure (Task 2's smoke test already pulled
CPM machinery; if `util2` isn't cached yet, fetch it directly):

```bash
git clone --depth 1 https://github.com/inonitz/util2.git /tmp/util2-check
```

```cpp
// /tmp/perception_types_check.cpp
#include "perception_types.hpp"
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
g++ -std=c++17 -I source/llm_to_action/vision -I /tmp/util2-check \
    /tmp/perception_types_check.cpp -o /tmp/perception_types_check \
    && /tmp/perception_types_check
```

Expected: `perception_types_check OK`.

- [ ] **Step 3: Commit**

```bash
rtk git add source/llm_to_action/vision/perception_types.hpp
rtk git commit -m "vision: canonical TargetDetection/PerceptionSnapshot types"
```

---

### Task 5: `vision/yolo_seg_engine.hpp` / `.cpp` — thread-capped segmentation wrapper

**Files:**
- Create: `source/llm_to_action/vision/yolo_seg_engine.hpp`
- Create: `source/llm_to_action/vision/yolo_seg_engine.cpp`

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
// source/llm_to_action/vision/yolo_seg_engine.hpp
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
// source/llm_to_action/vision/yolo_seg_engine.cpp
#include "yolo_seg_engine.hpp"
#include "coco_labels.hpp"

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
fallback — no `coco.names` file needed. `YoloSegEngine` never reads `detector`'s own
`classNames_`; `SegDetection::classId` is enough, `vision::coco_class_name()` (Task 3) does the
label lookup at fusion time (Task 7).

- [ ] **Step 3: Compile-check it links (real correctness test happens in Task 9 once models
      exist — this step just proves the wrapper compiles and constructs/fails predictably)**

This can't fully link standalone without `libonnxruntime.so` + OpenCV `-l` flags. Defer the actual
build+run to Task 9's CMake target, which has all the include/link flags already assembled. Mark
this step done once Task 9's build succeeds and exercises `YoloSegEngine` (cross-reference: Task
9, Step 4).

- [ ] **Step 4: Commit**

```bash
rtk git add source/llm_to_action/vision/yolo_seg_engine.hpp source/llm_to_action/vision/yolo_seg_engine.cpp
rtk git commit -m "vision: thread-capped YoloSegEngine wrapper"
```

---

### Task 6: `vision/yolo_depth_engine.hpp` / `.cpp` — thread-capped depth wrapper

**Files:**
- Create: `source/llm_to_action/vision/yolo_depth_engine.hpp`
- Create: `source/llm_to_action/vision/yolo_depth_engine.cpp`

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
// source/llm_to_action/vision/yolo_depth_engine.hpp
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
// source/llm_to_action/vision/yolo_depth_engine.cpp
#include "yolo_depth_engine.hpp"

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

- [ ] **Step 3: Defer link-verification to Task 9** (same reasoning as Task 5, Step 3 — cross-
      reference: Task 9, Step 4).

- [ ] **Step 4: Commit**

```bash
rtk git add source/llm_to_action/vision/yolo_depth_engine.hpp source/llm_to_action/vision/yolo_depth_engine.cpp
rtk git commit -m "vision: thread-capped YoloDepthEngine wrapper"
```

---

### Task 7: `vision/perception_fusion.hpp` / `.cpp` — fuse seg + depth into `PerceptionSnapshot`

**Files:**
- Create: `source/llm_to_action/vision/perception_fusion.hpp`
- Create: `source/llm_to_action/vision/perception_fusion.cpp`

**Interfaces:**
- Consumes: `vision::YoloSegEngine::segment()` (Task 5), `vision::YoloDepthEngine::estimate()`
  (Task 6), `vision::coco_class_name()` (Task 3), `TargetDetection`/`PerceptionSnapshot` (Task 4).
- Produces: `vision::fuse(YoloSegEngine&, YoloDepthEngine&, const cv::Mat&, float, float) ->
  PerceptionSnapshot` — Task 9's test calls this directly.

- [ ] **Step 1: Write the header**

```cpp
// source/llm_to_action/vision/perception_fusion.hpp
#pragma once

#include "perception_types.hpp"
#include "yolo_depth_engine.hpp"
#include "yolo_seg_engine.hpp"

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
// source/llm_to_action/vision/perception_fusion.cpp
#include "perception_fusion.hpp"
#include "coco_labels.hpp"

#include <algorithm>
#include <chrono>
#include <cstring>
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
rtk git add source/llm_to_action/vision/perception_fusion.hpp source/llm_to_action/vision/perception_fusion.cpp
rtk git commit -m "vision: fuse() seg+depth into PerceptionSnapshot"
```

---

### Task 8: `vision/CMakeLists.txt` — self-sufficient `Perception::vision` target

**Files:**
- Create: `source/llm_to_action/vision/CMakeLists.txt`
- Modify: `source/llm_to_action/CMakeLists.txt` (add `add_subdirectory(vision)` next to the
  existing `add_subdirectory(gstreamer_gz_udp_tx)`)

**Interfaces:**
- Produces: target alias `Perception::vision` (links `coco_labels.hpp`, `perception_types.hpp`,
  `yolo_seg_engine.*`, `yolo_depth_engine.*`, `perception_fusion.*`, YOLOs-CPP headers, ONNX
  Runtime, OpenCV). Consumed later by the FMU (out of scope for this plan) and by Task 9's test
  target in this same file.

- [ ] **Step 1: Write the CMakeLists**

```cmake
# source/llm_to_action/vision/CMakeLists.txt
cmake_minimum_required(VERSION 3.16)
project(vision LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Self-sufficient: works whether configured standalone (no ROS in scope,
# satisfies the "build/test without ROS or the simulator" requirement) or
# nested via add_subdirectory() from the full workspace.
if(NOT COMMAND safe_cpm_add_package)
    include(${CMAKE_CURRENT_SOURCE_DIR}/../../../cmake/FetchCPM.cmake)
    include_cpm()
endif()
if(NOT COMMAND define_library_fetch_of_yolos_cpp)
    include(${CMAKE_CURRENT_SOURCE_DIR}/../../../cmake/FetchYOLOsCPP.cmake)
endif()

define_library_fetch_of_yolos_cpp()

safe_cpm_add_package(
    NAME           util2
    GIT_REPOSITORY https://github.com/inonitz/util2.git
    GIT_TAG        main
    GIT_SHALLOW    TRUE
)

find_package(OpenCV REQUIRED)

add_library(vision STATIC
    coco_labels.hpp
    perception_types.hpp
    yolo_seg_engine.hpp
    yolo_seg_engine.cpp
    yolo_depth_engine.hpp
    yolo_depth_engine.cpp
    perception_fusion.hpp
    perception_fusion.cpp
)
add_library(Perception::vision ALIAS vision)

target_include_directories(vision PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${yolos-cpp_SOURCE_DIR}/include
)

target_link_libraries(vision PUBLIC
    UTIL2::util2
    ONNXRuntime::onnxruntime
    opencv_core
    opencv_imgproc
    opencv_imgcodecs
)

set_target_properties(vision PROPERTIES
    BUILD_RPATH "${ORT_INSTALL_DIR}/lib"
)

option(VISION_BUILD_TESTS "Build the vision/ standalone correctness+benchmark test" ${GROUNDSTATION_IS_TOP_LEVEL})
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

`GROUNDSTATION_IS_TOP_LEVEL` won't exist when this is configured standalone (it's set in the root
`CMakeLists.txt`) — CMake treats an undefined variable in a boolean `option()` default as `OFF`.
That's fine here: standalone runs should pass `-DVISION_BUILD_TESTS=ON` explicitly (Task 9 does).

- [ ] **Step 2: Wire it into `source/llm_to_action/CMakeLists.txt`**

Add next to the existing `add_subdirectory(gstreamer_gz_udp_tx)`:

```cmake
add_subdirectory(gstreamer_gz_udp_tx)
add_subdirectory(vision)
```

- [ ] **Step 3: Configure standalone and confirm the target exists (no test executable yet — Task
      9 adds `test/perception_test.cpp`, so this will fail until then; expected failure, not a
      bug)**

```bash
cmake -S source/llm_to_action/vision -B /tmp/vision_build -DVISION_BUILD_TESTS=OFF 2>&1 | tail -30
cmake --build /tmp/vision_build -j 2>&1 | tail -40
```

Expected: configure succeeds (prints the `[FetchYOLOsCPP]` patch lines again — idempotent, no
`FATAL_ERROR`), `vision` static library builds with no errors.

- [ ] **Step 4: Commit**

```bash
rtk git add source/llm_to_action/vision/CMakeLists.txt source/llm_to_action/CMakeLists.txt
rtk git commit -m "vision: Perception::vision CMake target, standalone-buildable"
```

---

### Task 9: Standalone correctness test + fp32/int8/int4 × 1/2/4-thread benchmark

**Files:**
- Create: `source/llm_to_action/vision/test/perception_test.cpp`

**Interfaces:**
- Consumes: everything from Tasks 3–7 (`vision::fuse`, `vision::YoloSegEngine`,
  `vision::YoloDepthEngine`, `vision::coco_class_name`, `TargetDetection`, `PerceptionSnapshot`).
- Produces: nothing further downstream — this is the leaf verification task.

- [ ] **Step 1: Write the test**

```cpp
// source/llm_to_action/vision/test/perception_test.cpp
/*
    Standalone, ROS-free correctness + latency/thread benchmark for the vision/
    perception library. Build:
        cmake -S source/llm_to_action/vision -B /tmp/vision_build -DVISION_BUILD_TESTS=ON
        cmake --build /tmp/vision_build -j
        /tmp/vision_build/perception_test /root/models/vision
    (test image is copied to ${CMAKE_CURRENT_BINARY_DIR}/dog.jpg by CMake — no arg needed
    unless you want a different image as argv[2])
*/
#include "../coco_labels.hpp"
#include "../perception_fusion.hpp"
#include "../perception_types.hpp"
#include "../yolo_depth_engine.hpp"
#include "../yolo_seg_engine.hpp"

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
cmake -S source/llm_to_action/vision -B /tmp/vision_build -DVISION_BUILD_TESTS=ON 2>&1 | tail -30
cmake --build /tmp/vision_build -j 2>&1 | tail -60
```

Expected: builds `vision` and `perception_test` with no errors. (This is also where Task 5 Step 3
and Task 6 Step 3's deferred link-verification actually happens — if either engine wrapper has a
signature mismatch against the patched YOLOs-CPP headers, it fails here.)

- [ ] **Step 3: Run the correctness portion, confirm it passes before looking at the benchmark**

```bash
cd /tmp/vision_build && LD_LIBRARY_PATH=$(find /tmp/vision_build/_deps/onnxruntime -name lib -type d | head -1):$LD_LIBRARY_PATH ./perception_test /root/models/vision
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
      core)** — run once at `threads=1` under `taskset`/monitoring:

```bash
cd /tmp/vision_build && \
LD_LIBRARY_PATH=$(find /tmp/vision_build/_deps/onnxruntime -name lib -type d | head -1):$LD_LIBRARY_PATH \
./perception_test /root/models/vision & PID=$!; sleep 2; \
grep Threads /proc/$PID/status; ps -o pid,nlwp,psr,comm -p $PID; wait $PID
```

Expected: thread count in `/proc/$PID/status` stays low (roughly ORT intra/inter-op threads + a
couple of housekeeping threads, not e.g. 16). Report this observation alongside the benchmark
table — it's the empirical check that `SetIntraOpNumThreads`/spin-disable actually took effect.

- [ ] **Step 6: Commit**

```bash
rtk git add source/llm_to_action/vision/test/perception_test.cpp
rtk git commit -m "vision: standalone correctness test + fp32/int8/int4 x 1/2/4-thread benchmark"
```

---

### Task 10: Bounded full-workspace integration check

**Files:** none created/modified — verification only.

**Interfaces:** none new.

- [ ] **Step 1: Configure the full workspace** (ROS Jazzy + px4_msgs + gz-sim8 confirmed present
      in this environment)

```bash
source /opt/ros/jazzy/setup.bash
cmake -S . -B /tmp/full_ws_build -DGROUNDSTATION_BUILD_EXECUTABLE=ON 2>&1 | tail -60
```

Expected: configure succeeds (or fails for reasons **unrelated** to `vision/` — e.g. an in-flight
edit elsewhere on this branch to `fmu_node.cpp`/`llamaclient.cpp` per current `git status`; if so,
note the unrelated failure in the report and move to Step 2's narrower check instead of trying to
fix it — out of this task's blast radius).

- [ ] **Step 2: Build only the vision target, not the FMU/keyboard/ASR/offboard/gstreamer nodes**

```bash
cmake --build /tmp/full_ws_build --target vision -j 2>&1 | tail -60
```

Expected: `vision` builds cleanly inside the full workspace tree (proves `add_subdirectory(vision)`
composes correctly with the rest of `source/llm_to_action/CMakeLists.txt` and the root fetch
wiring), regardless of whether sibling targets (fmu, keyboard, etc.) currently build — do not
attempt to fix those; they're outside this plan's scope.

- [ ] **Step 3: No commit** — this task only verifies; nothing here should have been modified.

---

## Handoff Report (fill in from Task 9's actual output, not before)

When all 10 tasks are done, report:
1. Exact build/run commands (Task 9, Steps 2–3).
2. Correctness test result (pass/fail, from Task 9 Step 3's actual terminal output).
3. Full benchmark table (Task 9 Step 4's actual terminal output, verbatim).
4. Thread-cap verification observation (Task 9 Step 5).
5. Recommended variant + thread count, stated plainly against the ~25 ms depth / ~33 ms seg
   targets — including if neither is met.
6. Task 1's int4 quantization outcome (succeeded or failed, and why if it failed).
7. Task 10's full-workspace integration result.
