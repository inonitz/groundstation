param(
    [Parameter(Mandatory=$true, ParameterSetName="Build")]
    [ValidateSet("debug", "debug_perf", "release", "release_dbginfo", "release_perf")]
    [string]$BuildType,

    [Parameter(Mandatory=$true, ParameterSetName="Build")]
    [ValidateSet("shared", "static")]
    [string]$LinkType,

    [Parameter(Mandatory=$true, ParameterSetName="Build")]
    [ValidateSet("cleanbuild", "configure", "build")]
    [string]$Action,

    [Parameter(Mandatory=$true, ParameterSetName="Help")]
    [Alias("h")]
    [switch]$Help
)


function Show-CustomHelp {
    Write-Host "Usage: .\build.ps1 -BuildType <type> -LinkType <link> -Action <action>" -ForegroundColor Cyan
    Write-Host "Usage: .\build.ps1 -Help" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Arguments:"
    Write-Host "  -BuildType : debug, release, release_dbginfo, debug_perf, release_perf"
    Write-Host "  -LinkType  : shared, static"
    Write-Host "  -Action    : cleanbuild, configure, build"
}

if ($PSCmdlet.ParameterSetName -eq "Help") { Show-CustomHelp; exit 0 }

$ErrorActionPreference = "Stop"
$PROJECT_NAME = "all"
$CMAKE_ROOT_BUILD_DIR = "build"

$CMAKE_ARGLIST = @(
    "-DCMAKE_EXPORT_COMPILE_COMMANDS=1",
    "-DGROUNDSTATION_BUILD_EXECUTABLE=ON",
    "-DGROUNDSTATION_BUILD_TESTS=OFF",
    "-DGROUNDSTATION_BUILD_BENCHMARKS=OFF",
    "-DGROUNDSTATION_BUILD_BACKEND_PX4=ON"
)

switch ($BuildType) {
    "debug"           { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=Debug" }
    "debug_perf"      { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=Debug" }
    "release"         { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=Release" }
    "release_dbginfo" { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=RelWithDbgInfo" }
    "release_perf"    { $CMAKE_ARGLIST += "-DCMAKE_BUILD_TYPE=Release" }
}

switch ($LinkType) {
    "shared" { $CMAKE_ARGLIST += "-DBUILD_SHARED_LIBS=1" }
    "static" { $CMAKE_ARGLIST += "-DBUILD_SHARED_LIBS=0" }
}

$CMAKE_FINAL_BUILD_DIR = Join-Path $CMAKE_ROOT_BUILD_DIR (Join-Path $BuildType $LinkType)

Write-Host "Out-of-source Root   Build Directory: '$CMAKE_ROOT_BUILD_DIR'"  -ForegroundColor Blue
Write-Host "Out-of-source Target Build Directory: '$CMAKE_FINAL_BUILD_DIR'" -ForegroundColor Blue
Write-Host "Arguments: $BuildType $LinkType $Action"

New-Item -ItemType Directory -Path $CMAKE_ROOT_BUILD_DIR -Force | Out-Null

if ($Action -eq "cleanbuild") {
    if (Test-Path $CMAKE_FINAL_BUILD_DIR) { Remove-Item -Recurse -Force $CMAKE_FINAL_BUILD_DIR }
}

if ($Action -eq "configure") {
    $CMAKE_ARGLIST += "-DGIT_SUBMODULE=ON"
    New-Item -ItemType Directory -Path $CMAKE_FINAL_BUILD_DIR -Force | Out-Null
    cmake -S . -B $CMAKE_FINAL_BUILD_DIR -G "Ninja" $CMAKE_ARGLIST
}

if ($Action -eq "build") {
    Push-Location $CMAKE_FINAL_BUILD_DIR
    if (Test-Path "compile_commands.json") { Copy-Item "compile_commands.json" "../../compile_commands.json" -Force }
    $cores = [int]$env:NUMBER_OF_PROCESSORS
    $jobs  = if ($cores -gt 2) { $cores - 2 } else { 1 }
    cmake --build . --target $PROJECT_NAME -- -j$jobs
    Pop-Location
}
