cmake_minimum_required(VERSION 3.16)
project(groundstation_workspace C CXX)

if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(GROUNDSTATION_IS_TOP_LEVEL ON)
else()
    set(GROUNDSTATION_IS_TOP_LEVEL OFF)
endif()

# 1. Include Utility Headers
include(ExternalProject)
include(cmake/DetectWSL.cmake)
include(cmake/FetchCPM.cmake)
include(cmake/SubmoduleUpdate.cmake)
include(cmake/UseCCache.cmake)
include(cmake/ColouredOutput.cmake)
include(cmake/OutputDir.cmake)
include(cmake/WorkspaceOptions.cmake)
include(cmake/BuildDiagnostics.cmake)
include(cmake/FetchLLamaCPP.cmake)
include(cmake/FindGStreamer.cmake)
# include(cmake/FetchOpenVINS.cmake)
# include(cmake/FetchStellaSLAM.cmake)
include_cpm()


enable_coloured_diagnostics_if_available()
use_ccache_program_if_exists()
define_aggregate_output_artifact_directory()
update_submodules_on_cmake_configure("dependencies")


OPTION(GROUNDSTATION_ENABLE_SANITIZER_ADDRESS      "Enable AddressSanitizer"                       OFF)
OPTION(GROUNDSTATION_ENABLE_SANITIZER_UNDEFINED    "Enable UndefinedBehaviorSanitizer"             OFF)
OPTION(GROUNDSTATION_ENABLE_SANITIZER_MEMORY       "Enable MemorySanitizer"                        OFF)
OPTION(GROUNDSTATION_ENABLE_LINK_TIME_OPTIMIZATION "Enable Link-Time/Interprocedural Optimization" OFF)
OPTION(GROUNDSTATION_BUILD_EXECUTABLE              "Build The GroundStation Server"                OFF)
OPTION(GROUNDSTATION_BUILD_TESTS                   "Testing Correct functionality of the project"  ${GROUNDSTATION_IS_TOP_LEVEL})
OPTION(GROUNDSTATION_BUILD_BENCHMARKS              "Testing Performance/Accuracy Metrics"          ${GROUNDSTATION_IS_TOP_LEVEL})
OPTION(GROUNDSTATION_BUILD_SYSTEM_BACKEND_TYPE     "Testing Performance/Accuracy Metrics"          "PX4")
# FMU drone backend selection: exactly one of these must be ON (checked below).
OPTION(GROUNDSTATION_BUILD_BACKEND_PX4   "Build the Groundstation against the PX4 backend"        OFF)
OPTION(GROUNDSTATION_BUILD_BACKEND_TELLO "Build the Groundstation against the Tello backend"      OFF)
OPTION(GROUNDSTATION_BUILD_BACKEND_ALL   "Build the Groundstation against all backends (px4+tello)" OFF)


if(GROUNDSTATION_ENABLE_SANITIZER_ADDRESS AND GROUNDSTATION_ENABLE_SANITIZER_MEMORY)
    message(FATAL_ERROR "ASan and MSan are mutually exclusive.")
endif()

if( 
    ( GROUNDSTATION_BUILD_BACKEND_PX4 AND GROUNDSTATION_BUILD_BACKEND_TELLO )
    OR
    ( GROUNDSTATION_BUILD_BACKEND_PX4 AND GROUNDSTATION_BUILD_BACKEND_ALL )
    OR
    ( GROUNDSTATION_BUILD_BACKEND_TELLO AND GROUNDSTATION_BUILD_BACKEND_ALL )
    OR
            (NOT GROUNDSTATION_BUILD_BACKEND_PX4) 
        AND (NOT GROUNDSTATION_BUILD_BACKEND_TELLO) 
        AND (NOT GROUNDSTATION_BUILD_BACKEND_ALL)
)
    message(FATAL_ERROR 
        "You can Only Enable a single Backend Option at a time - PX4 Flight-Controller, DJI Tello or ALL of them"
    )
endif()

declare_optional_interface_library_different_sanitizers()
declare_optional_interface_library_lto()
declare_optional_interface_default_project_configuration()
find_package(rclcpp          REQUIRED)
find_package(geometry_msgs   REQUIRED)
find_package(sensor_msgs     REQUIRED)
find_package(nav_msgs        REQUIRED)
find_package(cv_bridge       REQUIRED)
find_package(px4_msgs        REQUIRED)
# Required Dependency for OpenVINS
find_package(Eigen3          REQUIRED)
find_package(OpenCV          REQUIRED)
if(${GLOBAL_WORKSPACE_LINUX_IS_WSL})
    find_package(X11 REQUIRED)
endif()

define_library_fetch_of_llama_cpp_with_external_project()
define_library_fetch_of_gstreamer()
# define_library_fetch_of_stella_vslam_with_external_project()

# ---------------------------------------------------------------------------
# Local Subdirectories 
# This has to be First due to sherpa-onnx dependency inside sttserver,
# which pulls nlohmann_json without tracking for duplicates
# Reserving the order between "Migrated VLMNav" & "Local Subdirectories"
# will cause a duplicate target error
# ---------------------------------------------------------------------------
# add_subdirectory(dependencies/util2)
# add_subdirectory(dependencies/sttserver)


safe_cpm_add_package(
    NAME sttserver
    GIT_REPOSITORY https://github.com/inonitz/sttserv.git
    GIT_TAG        feature-multimodel
    GIT_SHALLOW    TRUE
    OPTIONS
        "STTSERVER_FORCE_COLOURED_OUTPUT OFF"
        "STTSERVER_ENABLE_SANITIZER_ADDRESS OFF"
        "STTSERVER_ENABLE_SANITIZER_UNDEFINED OFF"
        "STTSERVER_ENABLE_SANITIZER_MEMORY OFF"
        "STTSERVER_ENABLE_LINK_TIME_OPTIMIZATION OFF"
        "STTSERVER_BUILD_LIBRARY_BACKEND_WHISPER ON"
        "STTSERVER_BUILD_LIBRARY_BACKEND_SHERPA_ONNX OFF"
        "STTSERVER_BUILD_LIBRARY ON"
        "STTSERVER_BUILD_TESTS OFF"
        "STTSERVER_BUILD_BENCHMARKS OFF"
)


safe_cpm_add_package(
    NAME util2
    GIT_REPOSITORY https://github.com/inonitz/util2.git
    GIT_TAG        main
    GIT_SHALLOW    TRUE
)

# Perception library (YOLO26 seg + metric depth). Vendored as a full nested
# project, same pattern as sttserver above: OPTIONS turn off its own
# tests/benchmarks/sanitizers so only Perception::vision (vision/CMakeLists.txt)
# gets built here. Pins to a branch (not a tag) deliberately -- see
# docs/handoffs/2026-08-06-build-yolo-vision-generic-backend-refactor.md for the
# planned follow-up API change on this same branch.
safe_cpm_add_package(
    NAME vision
    GIT_REPOSITORY https://github.com/nurmilkov/BUILD_YOLO.git
    GIT_TAG        feature-vision-api
    GIT_SHALLOW    TRUE
    OPTIONS
        "VISION_ENABLE_SANITIZER_ADDRESS OFF"
        "VISION_ENABLE_SANITIZER_UNDEFINED OFF"
        "VISION_ENABLE_SANITIZER_MEMORY OFF"
        "VISION_ENABLE_LINK_TIME_OPTIMIZATION OFF"
        "VISION_BUILD_LIBRARY ON"
        "VISION_BUILD_TESTS OFF"
        "VISION_BUILD_BENCHMARKS OFF"
)


safe_cpm_add_package(
    NAME cpp-httplib
    GIT_REPOSITORY https://github.com/yhirose/cpp-httplib.git
    GIT_TAG        v0.18.0
    GIT_SHALLOW    TRUE
)

safe_cpm_add_package(
    NAME cpp-base64
    GIT_REPOSITORY https://github.com/inonitz/cpp-base64.git
    GIT_TAG        feature-cmake
    GIT_SHALLOW    TRUE
)

safe_cpm_add_package(
    NAME cxxopts
    GIT_REPOSITORY https://github.com/jarro2783/cxxopts.git
    GIT_TAG        v3.2.0
    GIT_SHALLOW    TRUE
)

safe_cpm_add_package(
    NAME nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG        v3.11.3
    GIT_SHALLOW    TRUE
)

safe_cpm_add_package(
    NAME moodycamel_readerwriterqueue
    GIT_REPOSITORY https://github.com/cameron314/readerwriterqueue
    GIT_TAG        v1.0.7
    GIT_SHALLOW    TRUE
)

safe_cpm_add_package(
    NAME spdlog
    GIT_REPOSITORY https://github.com/gabime/spdlog.git
    GIT_TAG        v1.14.1
    GIT_SHALLOW    TRUE
)

# ctello: DOWNLOAD_ONLY so we compile only its client .cpp (see
# source/llm_to_action/tello_backend/CMakeLists.txt) and skip its examples.
safe_cpm_add_package(
    NAME ctello
    GIT_REPOSITORY https://github.com/carlospzlz/ctello.git
    GIT_TAG        master
    GIT_SHALLOW    TRUE
    DOWNLOAD_ONLY  YES
)


# ---------------------------------------------------------------------------
# Local Project
# ---------------------------------------------------------------------------
if(GROUNDSTATION_BUILD_EXECUTABLE)
    add_subdirectory(source/llm_to_action)
    # add_subdirectory(source/speech_to_action)
    # add_subdirectory(source/nav)
endif()