cmake_minimum_required(VERSION 3.16)
project(groundstation_workspace C CXX)

if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(GROUNDSTATION_IS_TOP_LEVEL ON)
else()
    set(GROUNDSTATION_IS_TOP_LEVEL OFF)
endif()


include(cmake/SubmoduleUpdate.cmake)
include(cmake/UseCCache.cmake)
include(cmake/ColouredOutput.cmake)
include(cmake/OutputDir.cmake)
include(cmake/WorkspaceOptions.cmake)
include(cmake/BuildDiagnostics.cmake)


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


find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(px4_msgs REQUIRED)

add_subdirectory(dependencies/util2)
add_subdirectory(dependencies/sttserver)
# add_subdirectory(dependencies/vlmnav)

if(GROUNDSTATION_BUILD_EXECUTABLE)
    add_subdirectory(src/groundstation)
endif()