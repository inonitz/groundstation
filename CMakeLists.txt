cmake_minimum_required(VERSION 3.16)
project(groundstation_workspace C CXX)

if(CMAKE_PROJECT_NAME STREQUAL PROJECT_NAME)
    set(GROUNDSTATION_IS_TOP_LEVEL ON)
else()
    set(GROUNDSTATION_IS_TOP_LEVEL OFF)
endif()

include(FetchContent)
include(cmake/SubmoduleUpdate.cmake)
include(cmake/UseCCache.cmake)
include(cmake/ColouredOutput.cmake)
include(cmake/OutputDir.cmake)
include(cmake/WorkspaceOptions.cmake)
include(cmake/BuildDiagnostics.cmake)

# 1. Workspace/Project-Wide Specific Configurations
enable_coloured_diagnostics_if_available()
use_ccache_program_if_exists()
define_aggregate_output_artifact_directory()

update_submodules_on_cmake_configure("dependencies")

# 2. Workspace/Project-Wide Options
OPTION(GROUNDSTATION_FORCE_COLOURED_OUTPUT         "Always produce ANSI-colored output (GNU/Clang only)" ON)
OPTION(GROUNDSTATION_ENABLE_SANITIZER_ADDRESS      "Enable AddressSanitizer"                             OFF)
OPTION(GROUNDSTATION_ENABLE_SANITIZER_UNDEFINED    "Enable UndefinedBehaviorSanitizer"                   OFF)
OPTION(GROUNDSTATION_ENABLE_SANITIZER_MEMORY       "Enable MemorySanitizer"                              OFF)
OPTION(GROUNDSTATION_ENABLE_LINK_TIME_OPTIMIZATION "Enable Link-Time/Interprocedural Optimization"       OFF)
OPTION(GROUNDSTATION_BUILD_EXECUTABLE              "Build The GroundStation Server"                      OFF)
OPTION(GROUNDSTATION_BUILD_TESTS                   "Testing Correct functionality of the project"        ${GROUNDSTATION_IS_TOP_LEVEL})
OPTION(GROUNDSTATION_BUILD_BENCHMARKS              "Testing Performance/Accuracy Metrics"                ${GROUNDSTATION_IS_TOP_LEVEL})

# Early error conditions (FIXED variable names)
if(GROUNDSTATION_ENABLE_SANITIZER_ADDRESS AND GROUNDSTATION_ENABLE_SANITIZER_MEMORY)
    message(FATAL_ERROR "ASan and MSan are mutually exclusive. Please choose only one\n")
endif()

# 3. Declare interface libraries - Sanitizer Interface Library depends on these
declare_optional_interface_library_different_sanitizers()
declare_optional_interface_library_lto()
declare_optional_interface_default_project_configuration()

# 4. Process Actions related to the options above.
if(GROUNDSTATION_FORCE_COLOURED_OUTPUT)
    set(CMAKE_COLOR_DIAGNOSTICS ON)
    enable_coloured_diagnostics_if_available()
endif()

if(GROUNDSTATION_ENABLE_SANITIZER_ADDRESS)
    add_link_options(WORKSPACE_CONFIG::AddressSanitizerInterface)
endif()

if(GROUNDSTATION_ENABLE_SANITIZER_UNDEFINED)
    add_link_options(WORKSPACE_CONFIG::UBSanInterface)
endif()

if(GROUNDSTATION_ENABLE_SANITIZER_MEMORY)
    add_link_options(WORKSPACE_CONFIG::MemorySanitizerInterface)
endif()

if(GROUNDSTATION_ENABLE_LINK_TIME_OPTIMIZATION)
    add_link_options(WORKSPACE_CONFIG::LTO)
endif()

# 5. Print Enabled/Disabled Flags For Verbose Diagnostics
print_all_workspace_flags_and_vars()

find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(px4_msgs REQUIRED)

# 6. The Actual Start of the cmake
add_subdirectory(dependencies/sttserver)
set_target_properties(parakeet whisper ggml ggml-cpu ggml-vulkan PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(GROUNDSTATION_BUILD_EXECUTABLE)
    add_subdirectory(src/groundstation)
endif()
if(GROUNDSTATION_BUILD_TESTS)
    add_subdirectory(dependencies/googletest)
endif()
if(GROUNDSTATION_BUILD_BENCHMARKS)
    add_subdirectory(benchmark)
endif()