#!/bin/bash

PROJECT_NAME="all"
    # -DCMAKE_CUDA_HOST_COMPILER=clang++ \
    # -DCMAKE_C_COMPILER=clang \
    # -DCMAKE_CXX_COMPILER=clang++ \
    # -DCMAKE_AR=/usr/bin/llvm-ar-18 \
    # -DCMAKE_RANLIB=/usr/bin/llvm-ranlib-18 \
    # -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc \
    # -DCMAKE_CUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda-12.8 \
    # -DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=lld-18 \
    # -DCMAKE_SHARED_LINKER_FLAGS=-fuse-ld=lld-18 \
    # -DCMAKE_MODULE_LINKER_FLAGS=-fuse-ld=lld-18 \
    # -DCMAKE_SKIP_RPATH=ON \


# For More options see BuildDiagnostics.cmake
CMAKE_ARGLIST="\
    -DCMAKE_EXPORT_COMPILE_COMMANDS=1 \
    -DSTTSERVER_BUILD_EXECUTABLE=ON \
    -DSTTSERVER_BUILD_TESTS=ON \
    -DSTTSERVER_BUILD_BACKEND_PARAKEET=ON \
    -DSTTSERVER_BUILD_BACKEND_SHERPA_ONNX=ON
    "


#    -DSTTSERVER_BUILD_BACKEND_WHISPER=ON \

# CMAKE_ARGLIST="\
#     -DCMAKE_C_COMPILER=clang \
#     -DCMAKE_CXX_COMPILER=clang++ \
#     -DCMAKE_AR=/usr/bin/llvm-ar-18 \
#     -DCMAKE_RANLIB=/usr/bin/llvm-ranlib-18 \
#     -DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=lld-18 \
#     -DCMAKE_SHARED_LINKER_FLAGS=-fuse-ld=lld-18 \
#     -DCMAKE_MODULE_LINKER_FLAGS=-fuse-ld=lld-18 \
#     -DCMAKE_EXPORT_COMPILE_COMMANDS=1 \
#     -DCMAKE_COLOR_DIAGNOSTICS=ON \
#     \
#     -DFORCE_COLOURED_OUTPUT=ON \
#     -DENABLE_SANITIZER_ADDRESS=OFF \
#     -DENABLE_SANITIZER_UNDEFINED=OFF \
#     -DENABLE_SANITIZER_MEMORY=OFF \
#     -DENABLE_LINK_TIME_OPTIMIZATION=OFF \
#     \
#     -DENABLE_PROFILING=OFF \
#     -DTRACY_ENABLE=OFF \
#     -DTRACY_VERBOSE=OFF \
#     \
#     -DNO_ISA_EXTENSIONS=OFF \
#     -DGGML_VULKAN=ON \
#     -DGGML_CUDA=OFF \
#     -DGGML_METAL=OFF \
#     -DGGML_MUSA=OFF \
#     -DGGML_SYCL=OFF \
#     \
#     -DWHISPER_STANDALONE=OFF \
#     -DWHISPER_ALL_WARNINGS=ON \
#     -DWHISPER_ALL_WARNINGS_3RD_PARTY=ON \
#     -DWHISPER_FATAL_WARNINGS=OFF \
#     -DWHISPER_USE_SYSTEM_GGML=OFF \
#     -DWHISPER_SANITIZE_THREAD=OFF \
#     -DWHISPER_SANITIZE_ADDRESS=OFF \
#     -DWHISPER_SANITIZE_UNDEFINED=OFF \
#     -DWHISPER_BUILD_TESTS=OFF \
#     -DWHISPER_BUILD_EXAMPLES=ON \
#     -DWHISPER_BUILD_SERVER=OFF \
#     -DWHISPER_CURL=OFF \
#     -DWHISPER_SDL2=OFF \
#     -DWHISPER_FFMPEG=OFF \
#     -DWHISPER_COREML=OFF \
#     -DWHISPER_COREML_ALLOW_FALLBACK=OFF \
#     -DWHISPER_OPENVINO=OFF \
#     \
#     -DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc \
#     -DCMAKE_CUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda-12.8 \
#     -DGGML_CUDA=ON \
#     \
#     -DSHERPA_ONNX_ENABLE_BINARY=ON \
#     -DSHERPA_ONNX_ENABLE_PYTHON=OFF \
#     -DSHERPA_ONNX_ENABLE_TESTS=ON \
#     -DSHERPA_ONNX_ENABLE_CHECK=ON \
#     -DSHERPA_ONNX_ENABLE_PORTAUDIO=ON \
#     -DSHERPA_ONNX_ENABLE_JNI=OFF \
#     -DSHERPA_ONNX_ENABLE_C_API=ON \
#     -DSHERPA_ONNX_ENABLE_WEBSOCKET=OFF \
#     -DSHERPA_ONNX_ENABLE_GPU=ON \
#     -DSHERPA_ONNX_ENABLE_DIRECTML=OFF \
#     -DSHERPA_ONNX_LINK_D3D=OFF \
#     -DSHERPA_ONNX_ENABLE_WASM=OFF \
#     -DSHERPA_ONNX_ENABLE_TTS=OFF \
#     -DSHERPA_ONNX_ENABLE_SPEAKER_DIARIZATION=OFF \
#     -DSHERPA_ONNX_USE_PRE_INSTALLED_ONNXRUNTIME_IF_AVAILABLE=OFF \
#     -DSHERPA_ONNX_ENABLE_SANITIZER=OFF \
#     -DSHERPA_ONNX_BUILD_C_API_EXAMPLES=ON \
#     -DSHERPA_ONNX_ENABLE_RKNN=OFF \
#     -DSHERPA_ONNX_ENABLE_AXERA=OFF \
#     -DSHERPA_ONNX_ENABLE_AXCL=OFF \
#     -DSHERPA_ONNX_ENABLE_ASCEND_NPU=OFF \
#     -DSHERPA_ONNX_ENABLE_QNN=OFF \
#     -DSHERPA_ONNX_ENABLE_SPACEMIT=OFF \
#     "

CMAKE_ORIGINAL_SCRIPT_PATH="$PWD" # Assuming that build.sh is in the same dir as the Root CMakeLists.txt
CMAKE_ROOT_BUILD_DIR="build"
CMAKE_INTRMD_BUILD_DIR=""


CLEAN_CURRENT_ROOT_BUILD_DIR="false"
CONFIGURE_CMAKE_FLAG="false"
BUILD_BINARIES_FLAG="false"
RUN_SANDBOX_FLAG="false"
RUN_DEBUG_SANDBOX_FLAG="false"


if [[ "$1" == "help" || "$1" == "--help" || "$1" == "-h" ]]; then
    cat << EOF
Usage: $0 <build_type> <library_type> <action>

Arguments:
  build_type   - Type of build: debug, release, release_dbginfo, debug_perf, release_perf
  library_type - Type of library: shared (.dll/.so), static (.lib/.a)
  action       - Action to take: cleanbuild, configure, build, sandbox, debugsandbox

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
    CMAKE_ARGLIST+=" -DSHERPA_ONNX_LINK_LIBSTDCPP_STATICALLY=OFF"
    CMAKE_ARGLIST+=" -DSHERPA_ONNX_USE_STATIC_CRT=OFF"
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
elif [[ "$3" == "sandbox" ]]; then
    RUN_SANDBOX_FLAG="true"
elif [[ "$3" == "debugsandbox" ]]; then
    RUN_DEBUG_SANDBOX_FLAG="true"
else
    printf "Unknown Argument %s - valid values are: cleanbuild, configure, build, sandbox, debugsandbox\nExiting...\n" "$3"
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

# 7. FIXED: Missing closing bracket `]]` in this condition
if [[ "$CONFIGURE_CMAKE_FLAG" == "true" ]]; then
    mkdir -p "$CMAKE_FINAL_BUILD_DIR"
    # CMAKE_ARGLIST remains unquoted here purposely so CMake receives distinct arguments
    cmake -S . -B "$CMAKE_FINAL_BUILD_DIR" -G 'Ninja' $CMAKE_ARGLIST
fi

if [[ "$BUILD_BINARIES_FLAG" == "true" ]]; then
    cd "$CMAKE_FINAL_BUILD_DIR" || exit 1
    cp "compile_commands.json" "../../compile_commands.json"
    echo "CURRENT WORKING DIRECTORY IS $PWD"
    ninja "$PROJECT_NAME" -j$(( $(nproc) / 2 > 0 ? $(nproc) / 2 : 1 ))
fi

if [[ "$RUN_SANDBOX_FLAG" == "true" ]]; then
    cd "$CMAKE_FINAL_BUILD_DIR" || exit 1
    ninja run_sttserver_sandbox
fi

if [[ "$RUN_DEBUG_SANDBOX_FLAG" == "true" ]]; then
    cd "$CMAKE_FINAL_BUILD_DIR" || exit 1
    ninja debug_sttserver_sandbox
fi