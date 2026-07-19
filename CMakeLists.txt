cmake_minimum_required(VERSION 3.16)
project(groundstation_workspace C CXX)

if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(GROUNDSTATION_IS_TOP_LEVEL ON)
else()
    set(GROUNDSTATION_IS_TOP_LEVEL OFF)
endif()

# 1. Include Utility Headers
include(ExternalProject)
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
include(cmake/FetchStellaSLAM.cmake)
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

if(GROUNDSTATION_ENABLE_SANITIZER_ADDRESS AND GROUNDSTATION_ENABLE_SANITIZER_MEMORY)
    message(FATAL_ERROR "ASan and MSan are mutually exclusive.")
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
define_library_fetch_of_llama_cpp_with_external_project()
define_library_fetch_of_gstreamer()
define_library_fetch_of_stella_vslam_with_external_project()

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


# ---------------------------------------------------------------------------
# Local Project
# ---------------------------------------------------------------------------
if(GROUNDSTATION_BUILD_EXECUTABLE)
    add_subdirectory(source/gz_cam_plugin)
    add_subdirectory(source/gst_rx)
    add_subdirectory(source/nav)
    add_subdirectory(source/speech_to_action)
    add_subdirectory(source/slam)
endif()