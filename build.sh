#!/bin/bash

# Important to propagate errors to parent terminals.
set -e


PROJECT_NAME="all"

# For More options see BuildDiagnostics.cmake
CMAKE_ARGLIST="\
    -DCMAKE_EXPORT_COMPILE_COMMANDS=1 \
    -DGROUNDSTATION_BUILD_EXECUTABLE=ON \
    -DGROUNDSTATION_BUILD_TESTS=OFF \
    -DGROUNDSTATION_BUILD_BENCHMARKS=OFF \
    \

    "




CMAKE_ORIGINAL_SCRIPT_PATH="$PWD" # Assuming that build.sh is in the same dir as the Root CMakeLists.txt
CMAKE_ROOT_BUILD_DIR="build"
CMAKE_INTRMD_BUILD_DIR=""


CLEAN_CURRENT_ROOT_BUILD_DIR="false"
CONFIGURE_CMAKE_FLAG="false"
BUILD_BINARIES_FLAG="false"
RUN_GROUNDSTATION_FLAG="false"
RUN_DOCKER_SIMULATION_FLAG="false"

if [[ "$1" == "help" || "$1" == "--help" || "$1" == "-h" ]]; then
    cat << EOF
Usage: $0 <build_type> <library_type> <action>

Arguments:
  build_type   - Type of build: debug, release, release_dbginfo, debug_perf, release_perf
  library_type - Type of library: shared (.dll/.so), static (.lib/.a)
  action       - Action to take: cleanbuild, configure, build, rungs, runsim

Options:
  help         - Display this help message

Examples:
  $0 debug   static build
  $0 release shared build
EOF
    exit 0
fi


if [[ $# -ne 3 ]]; then
    echo "3 Arguments required to run the script"
    exit 1
fi


if [[ "$1" == "debug" ]]; then
    CMAKE_ARGLIST+=" -DCMAKE_BUILD_TYPE=Debug"
    CMAKE_INTRMD_BUILD_DIR+="debug/"
elif [[ "$1" == "debug_perf" ]]; then
    CMAKE_ARGLIST+=" -DCMAKE_BUILD_TYPE=Debug -DMEASURE_PERFORMANCE_TIMEOUT=1"
    CMAKE_INTRMD_BUILD_DIR+="debug_perf/"
elif [[ "$1" == "release" ]]; then
    CMAKE_ARGLIST+=" -DCMAKE_BUILD_TYPE=Release"
    CMAKE_INTRMD_BUILD_DIR+="release/"
elif [[ "$1" == "release_dbginfo" ]]; then
    CMAKE_ARGLIST+=" -DCMAKE_BUILD_TYPE=RelWithDbgInfo"
    CMAKE_INTRMD_BUILD_DIR+="release_dbginfo/"
elif [[ "$1" == "release_perf" ]]; then
    CMAKE_ARGLIST+=" -DCMAKE_BUILD_TYPE=Release -DMEASURE_PERFORMANCE_TIMEOUT=1"
    CMAKE_INTRMD_BUILD_DIR+="release_perf/"
else
    printf "Unknown Argument %s - valid values are: debug, release, release_dbginfo, debug_perf, release_perf\nExiting...\n" "$1"
    exit 1
fi

if [[ "$2" == "shared" ]]; then
    CMAKE_ARGLIST+=" -DBUILD_SHARED_LIBS=1"
    CMAKE_INTRMD_BUILD_DIR+="shared/"
elif [[ "$2" == "static" ]]; then
    CMAKE_ARGLIST+=" -DBUILD_SHARED_LIBS=0"
    CMAKE_INTRMD_BUILD_DIR+="static/"
else
    printf "Unknown Argument %s - valid values are: shared, static\nExiting...\n" "$2"
    exit 1
fi

if [[ "$3" == "cleanbuild" ]]; then
    CLEAN_CURRENT_ROOT_BUILD_DIR="true"
elif [[ "$3" == "configure" ]]; then
    CONFIGURE_CMAKE_FLAG="true"
    CMAKE_ARGLIST+=" -DGIT_SUBMODULE=ON"
elif [[ "$3" == "build" ]]; then
    BUILD_BINARIES_FLAG="true"
elif [[ "$3" == "rungs" ]]; then
    RUN_GROUNDSTATION_FLAG="true"
elif [[ "$3" == "runsim" ]]; then
    RUN_DOCKER_SIMULATION_FLAG="true"
else
    printf "Unknown Argument %s - valid values are: cleanbuild, configure, build, rungs, runsim\nExiting...\n" "$3"
    exit 1
fi

# the actual script
CMAKE_FINAL_BUILD_DIR="$CMAKE_ROOT_BUILD_DIR/$CMAKE_INTRMD_BUILD_DIR"
echo "Out-of-source Root   Build Directory is '$CMAKE_ROOT_BUILD_DIR' "
echo "Out-of-source Target Build Directory is '$CMAKE_FINAL_BUILD_DIR' "
echo "Cmake Arguments passed are ==> { "
echo "$CMAKE_ARGLIST"
echo "}"
echo "Script arguments are '$1' '$2' '$3' "

mkdir -p build

if [[ "$CLEAN_CURRENT_ROOT_BUILD_DIR" == "true" ]]; then
    rm -rf "$CMAKE_FINAL_BUILD_DIR"
fi

if [[ "$CONFIGURE_CMAKE_FLAG" == "true" ]]; then
    mkdir -p "$CMAKE_FINAL_BUILD_DIR"
    # CMAKE_ARGLIST remains unquoted here purposely so CMake receives distinct arguments
    cmake -S . -B "$CMAKE_FINAL_BUILD_DIR" -G 'Ninja' $CMAKE_ARGLIST
fi

if [[ "$BUILD_BINARIES_FLAG" == "true" ]]; then
    cd "$CMAKE_FINAL_BUILD_DIR" || exit 1
    cp "compile_commands.json" "../../compile_commands.json"
    echo "CURRENT WORKING DIRECTORY IS $PWD"
    
    # Safely fallback to 1 core if nproc fails or is missing
    CORES=$(nproc 2>/dev/null || echo 1)
    JOBS=$(( CORES > 2 ? CORES - 2 : 1 ))
    
    # ninja "$PROJECT_NAME" -j$JOBS
    time cmake --build . --target "$PROJECT_NAME" -- -j$JOBS
fi

if [[ "$RUN_GROUNDSTATION_FLAG" == "true" ]]; then
    cd "$CMAKE_FINAL_BUILD_DIR" || exit 1
    ninja run_mavlink_example
fi

if [[ "$RUN_DOCKER_SIMULATION_FLAG" == "true" ]]; then
    cd "$CMAKE_ORIGINAL_SCRIPT_PATH" || exit 1
    ./dockerfiles/gazebo.sh
fi