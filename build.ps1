param(
    [Parameter(Mandatory=$true, ParameterSetName="Build")]
    [ValidateSet("debug", "debug_perf", "release", "release_dbginfo", "release_perf")]
    [string]$BuildType,

    [Parameter(Mandatory=$true, ParameterSetName="Build")]
    [ValidateSet("shared", "static")]
    [string]$LinkType,

    [Parameter(Mandatory=$true, ParameterSetName="Build")]
    [ValidateSet(
        "cleanbuild",
        "configure",
        "build",
        "sandbox",
        "debugsandbox"
        # "debugctests",
        # "benchmark",
        # "debugbenchmark"
    )]
    [string]$Action,

    [Parameter(Mandatory=$false, ParameterSetName="Build")]
    [switch]$DryRun,

    [Parameter(Mandatory=$true, ParameterSetName="Help")]
    [Alias("h", "-Help")]
    [switch]$Help
)


# --- Helper Functions ---
function Show-CustomHelp {
    Write-Host "Usage: .\build.ps1 -BuildType <type> -LinkType <link> -Action <action> [-DryRun]" -ForegroundColor Cyan
    Write-Host "Usage: .\build.ps1 -Help" -ForegroundColor Cyan
    Write-Host "`nArguments:"
    Write-Host "  -BuildType   : debug, release, release_dbginfo, debug_perf, release_perf"
    Write-Host "  -LinkType    : shared, static"
    Write-Host "  -Action      : cleanbuild, configure, build, sandbox, debugsandbox, debugctests, benchmark, debugbenchmark"
}



function Run-Command {
    param([string]$Description, [scriptblock]$Command)
    if ($DryRun) {
        Write-Host "[DRY-RUN] Would execute: $Description" -ForegroundColor Yellow
    } else {
        try {
            & $Command
        } catch {
            Write-Error "Execution failed: $_"
            exit $LASTEXITCODE
        }
    }
}


# --- Initialization ---

if ($PSCmdlet.ParameterSetName -eq "Help") {
    Show-CustomHelp
    exit 0
}

$ErrorActionPreference = "Stop"
$PROJECT_NAME = "all"
$CMAKE_ROOT_BUILD_DIR = "build"
$CMAKE_ARGLIST = @(
    "-DCMAKE_EXPORT_COMPILE_COMMANDS=1",
    "-DSTTSERVER_BUILD_EXECUTABLE=ON",
    "-DSTTSERVER_BUILD_TESTS=ON",
    "-DSTTSERVER_BUILD_BACKEND_PARAKEET=ON",
    "-DSTTSERVER_BUILD_BACKEND_SHERPA_ONNX=ON"
)

# "-DCMAKE_C_COMPILER=clang",
# "-DCMAKE_CXX_COMPILER=clang++",
# "-DCMAKE_EXPORT_COMPILE_COMMANDS=1",
# "-DCMAKE_COLOR_DIAGNOSTICS=ON",
# "-DFORCE_COLOURED_OUTPUT=ON",
# "-DCMAKE_CXX_FLAGS=-fdiagnostics-color=always",
# "-DCMAKE_C_FLAGS=-fdiagnostics-color=always",
# "-DENABLE_SANITIZER_ADDRESS=OFF",
# "-DENABLE_SANITIZER_UNDEFINED=OFF",
# "-DENABLE_SANITIZER_MEMORY=OFF",
# "-DENABLE_LINK_TIME_OPTIMIZATION=OFF",

# "-DENABLE_PROFILING=OFF",
# "-DTRACY_ENABLE=OFF",
# "-DTRACY_VERBOSE=OFF",

# "-DNO_ISA_EXTENSIONS=OFF",
# "-DGGML_VULKAN=ON",
# "-DGGML_CUDA=OFF",
# "-DGGML_METAL=OFF",
# "-DGGML_MUSA=OFF",
# "-DGGML_SYCL=OFF",

# "-DWHISPER_STANDALONE=OFF",
# "-DWHISPER_ALL_WARNINGS=ON",
# "-DWHISPER_ALL_WARNINGS_3RD_PARTY=ON",
# "-DWHISPER_FATAL_WARNINGS=OFF",
# "-DWHISPER_USE_SYSTEM_GGML=OFF",
# "-DWHISPER_SANITIZE_THREAD=OFF",
# "-DWHISPER_SANITIZE_ADDRESS=OFF",
# "-DWHISPER_SANITIZE_UNDEFINED=OFF",
# "-DWHISPER_BUILD_TESTS=OFF",
# "-DWHISPER_BUILD_EXAMPLES=ON",
# "-DWHISPER_BUILD_SERVER=OFF",
# "-DWHISPER_CURL=OFF",
# "-DWHISPER_SDL2=OFF",
# "-DWHISPER_FFMPEG=OFF",
# "-DWHISPER_COREML=OFF",
# "-DWHISPER_COREML_ALLOW_FALLBACK=OFF",
# "-DWHISPER_OPENVINO=OFF"

# "-DBUILD_GMOCK=OFF",
# "-DINSTALL_GTEST=OFF"
# "-DBENCHMARK_ENABLE_INSTALL=OFF",
# "-DBENCHMARK_INSTALL_DOCS=OFF",
# "-DBENCHMARK_INSTALL_TOOLS=OFF",
# "-DBENCHMARK_DOWNLOAD_DEPENDENCIES=OFF",
# "-DBENCHMARK_ENABLE_TESTING=OFF"
# "-DBENCHMARK_ENABLE_GTEST_TESTS=OFF",
# "-DBENCHMARK_USE_BUNDLED_GTEST=OFF"




switch ($BuildType) {
    "debug"           { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=Debug" }
    "debug_perf"      { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=Debug" }
    "release"         { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=Release" }
    "release_dbginfo" { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=RelWithDbgInfo" }
    "release_perf"    { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=Release" }
}
# $CMAKE_ARGLIST += $( If ($LinkType -eq "shared") { "-DBUILD_SHARED_LIBS=1 -DGTEST_LINKED_AS_SHARED_LIBRARY=1" } Else { "-DBUILD_SHARED_LIBS=0 -DGTEST_LINKED_AS_SHARED_LIBRARY=0" } )
switch ($LinkType) {
    "shared" {
        $CMAKE_ARGLIST += "-DGTEST_CREATE_SHARED_LIBRARY=1"
        $CMAKE_ARGLIST += "-DGTEST_LINKED_AS_SHARED_LIBRARY=1"
        $CMAKE_ARGLIST += "-DBUILD_SHARED_LIBS=1"
    }
    "static" {
        $CMAKE_ARGLIST += "-DGTEST_CREATE_SHARED_LIBRARY=0"
        $CMAKE_ARGLIST += "-DGTEST_LINKED_AS_SHARED_LIBRARY=0"
        $CMAKE_ARGLIST += "-DBUILD_SHARED_LIBS=0"
    }
}


# Constructing paths
$CMAKE_FINAL_BUILD_DIR = Join-Path $CMAKE_ROOT_BUILD_DIR (Join-Path $BuildType $LinkType)

Write-Host "Out-of-source Target Build Directory: '$CMAKE_FINAL_BUILD_DIR'" -ForegroundColor Blue
Write-Host "Arguments: $BuildType $LinkType $Action"

# --- Execution ---

# 1. Directory Setup
if (-not (Test-Path $CMAKE_ROOT_BUILD_DIR)) {
    Run-Command "mkdir $CMAKE_ROOT_BUILD_DIR" { New-Item -ItemType Directory -Path $CMAKE_ROOT_BUILD_DIR | Out-Null }
}

if ($Action -eq "cleanbuild") {
    if (Test-Path $CMAKE_FINAL_BUILD_DIR) {
        Run-Command "Remove $CMAKE_FINAL_BUILD_DIR" { Remove-Item -Recurse -Force $CMAKE_FINAL_BUILD_DIR }
    }
}


# 2. Configure
if ($Action -eq "configure" -or $Action -eq "cleanbuild") {
    $CMAKE_ARGLIST += "-DGIT_SUBMODULE=ON"
    Run-Command "mkdir $CMAKE_FINAL_BUILD_DIR" { New-Item -ItemType Directory -Path $CMAKE_FINAL_BUILD_DIR -Force | Out-Null }
    Run-Command "CMake Configure" { cmake -S . -B $CMAKE_FINAL_BUILD_DIR -G "Ninja" $CMAKE_ARGLIST }
}


# 3. Build
if ($Action -eq "build") {
    if (-not $DryRun) { Push-Location $CMAKE_FINAL_BUILD_DIR }

    # Sync compile_commands.json as per original script
    if (Test-Path "compile_commands.json") {
        Run-Command "Update compile_commands.json" { Copy-Item "compile_commands.json" "../../compile_commands.json" -Force }
    }

    Run-Command "Ninja Build" { ninja $PROJECT_NAME -j(($env:NUMBER_OF_PROCESSORS)/2)}
    if (-not $DryRun) { Pop-Location }
}


# 4. Run
if ($Action -eq "sandbox") {
    if (-not $DryRun) { Push-Location $CMAKE_FINAL_BUILD_DIR }
    Run-Command "ninja run_sttserver_sandbox" { ninja run_sttserver_sandbox } # Defined in sandbox/CMakeLists.txt
    if (-not $DryRun) { Pop-Location }
}
if ($Action -eq "debugsandbox") {
    if (-not $DryRun) { Push-Location $CMAKE_FINAL_BUILD_DIR }
    Run-Command "ninja debug_sttserver_sandbox" { ninja debug_sttserver_sandbox } # Defined in sandbox/CMakeLists.txt
    if (-not $DryRun) { Pop-Location }
}
if ($Action -eq "debugcxxtests") {
    if (-not $DryRun) { Push-Location $CMAKE_FINAL_BUILD_DIR }
    Run-Command "ninja sttserver_sandbox_profile" { ninja sttserver_sandbox_profile } # Defined in sandbox/CMakeLists.txt
    if (-not $DryRun) { Pop-Location }
}

# if ($Action -eq "debugctests") {
#     if (-not $DryRun) { Push-Location $CMAKE_FINAL_BUILD_DIR }
#     # Defined in tests\CMakeListsCMocka.cmake
#     Run-Command "ninja debug_test_treelib_cmocka" { ninja debug_test_treelib_cmocka }
#     if (-not $DryRun) { Pop-Location }
# }


# if ($Action -eq "benchmark") {
#     if (-not $DryRun) { Push-Location $CMAKE_FINAL_BUILD_DIR }
#     Run-Command "ninja run_benchmark_treelib" { ninja run_benchmark_treelib }
#     if (-not $DryRun) { Pop-Location }
# }
# if ($Action -eq "debugbenchmark") {
#     if (-not $DryRun) { Push-Location $CMAKE_FINAL_BUILD_DIR }
#     Run-Command "ninja debug_benchmark_treelib" { ninja debug_benchmark_treelib }
#     if (-not $DryRun) { Pop-Location }
# }

# if($Action -eq "benchmarkconcurrent") {
#     $RUN_BENCHMARK_PARALLEL_SCRIPT = "..\..\..\scripts\benchmark_parallel.ps1"

#     if (-not $DryRun) { Push-Location $CMAKE_FINAL_BUILD_DIR }
#     Run-Command ".\scripts\benchmark_parallel.ps1" {
#         & $RUN_BENCHMARK_PARALLEL_SCRIPT
#     }
#     if (-not $DryRun) { Pop-Location }
# }
