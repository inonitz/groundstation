$ErrorActionPreference = "Stop"

Write-Host "=== [1/4] Resolving Paths ===" -ForegroundColor Yellow
$RawPath       = Split-Path $PSScriptRoot -Parent
$LinuxSafePath = $RawPath -replace '\\', '/'
$HostPath      = (wsl wslpath -a "$LinuxSafePath").Trim()

$HostModelFolderPathRaw    = [System.Environment]::GetEnvironmentVariable("ML_MODEL_PATH")
$HostModelFolderPathFilter = $HostModelFolderPathRaw -replace '\\', '/'
$HostModelFolderPath       = (wsl wslpath -a "$HostModelFolderPathFilter").Trim()

$HostPathASRModel    = "$HostModelFolderPath/ASR"
$HostPathVLMModel    = "$HostModelFolderPath/VLM"
$HostPathVisionModel = "$HostModelFolderPath/VISION"

$ContainerPath                = "/root/groundstation"
$ContainerPathASRModelPath    = "/root/models/asr"
$ContainerPathVLMModelPath    = "/root/models/vlm"
$ContainerPathVisionModelPath = "/root/models/vision"
$HostIP                       = (Get-NetIPAddress -InterfaceAlias 'vEthernet (WSL)' -AddressFamily IPv4).IPAddress

Write-Host "HostPath:             $HostPath"
Write-Host "HostModelFolderPath:  $HostModelFolderPath"
Write-Host "HostPathASRModel:     $HostPathASRModel"
Write-Host "HostPathVLMModel:     $HostPathVLMModel"
Write-Host "HostPathVisionModel:  $HostPathVisionModel"
Write-Host "HostIP:               $HostIP"

Write-Host "`n=== [2/4] Building Docker Args ===" -ForegroundColor Yellow
$dockerArguments = @(
    "docker run --rm -it",
    "--privileged",
    "--dns 8.8.8.8",
    "--net=host",
    "-v /tmp/.X11-unix:/tmp/.X11-unix:rw",
    "-v /mnt/wslg:/mnt/wslg",
    '-e DISPLAY=$DISPLAY',
    "-e WAYLAND_DISPLAY=wayland-0",
    "-e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir",
    "-e QT_X11_NO_MITSHM=1",
    "-e PULSE_SERVER=tcp:${HostIP}:4713",
    "-v ${HostPath}:${ContainerPath}",
    "-v ${HostPathASRModel}:${ContainerPathASRModelPath}",
    "-v ${HostPathVLMModel}:${ContainerPathVLMModelPath}",
    "-v ${HostPathVisionModel}:${ContainerPathVisionModelPath}",
    "-v vscode_server_cache:/root/.vscode-server"
)

$VideoControllers = Get-CimInstance Win32_VideoController
$HasNvidia = $VideoControllers | Where-Object { $_.Name -match "NVIDIA" }

if ($HasNvidia) {
    Write-Host "GPU: NVIDIA Detected" -ForegroundColor Green
    $dockerArguments += @(
        "--gpus=all",
        "-e NVIDIA_DRIVER_CAPABILITIES=all",
        "-e NVIDIA_VISIBLE_DEVICES=all"
    )
} else {
    Write-Host "GPU: Non-NVIDIA Detected" -ForegroundColor Yellow
    $dockerArguments += @(
        "--device /dev/dxg",
        "-v /usr/lib/wsl/lib:/usr/lib/wsl/lib",
        "-v /usr/lib/wsl/drivers:/usr/lib/wsl/drivers",
        "-v /usr/lib/wsl/lib/libdxcore.so:/usr/lib/x86_64-linux-gnu/libdxcore.so.1",
        "-e LD_LIBRARY_PATH=/usr/lib/wsl/lib:/usr/lib/wsl/drivers",
        "-e MESA_LOADER_DRIVER_OVERRIDE=d3d12",
        "-e GALLIUM_DRIVER=d3d12",
        "-e LIBGL_ALWAYS_SOFTWARE=0"
    )
}

# Image and entrypoint (Using double quotes for bash -c string, single quotes inside)
$dockerArguments += "px4_gazebo-lts-2028_ros2-lts-2029 bash -c `"echo -e 'pcm.!default { type pulse }\nctl.!default { type pulse }' > ~/.asoundrc && exec bash`""

$dockerCmd = $dockerArguments -join ' '

Write-Host "`n=== [3/4] Preparing Temporary Launch Script ===" -ForegroundColor Cyan

# Write command to temp file. Force LF (\n) line endings for Linux compatibility.
$TempScriptHost = [System.IO.Path]::GetTempFileName() + ".sh"
[System.IO.File]::WriteAllText($TempScriptHost, $dockerCmd.Replace("`r`n", "`n"))

# Convert Windows temp path to WSL path
$TempScriptWSL = (wsl wslpath -a ($TempScriptHost -replace '\\', '/')).Trim()

Write-Host "`n=== [4/4] Executing via WSL ===" -ForegroundColor Yellow

# Run if xhost exists
Write-Host "Configuring X11 permissions..."
wsl --exec bash -c "command -v xhost >/dev/null 2>&1 && xhost +local:root || true"

# Run docker command from script file (preserves TTY and quotes)
Write-Host "Launching Docker Container..."
wsl --exec bash $TempScriptWSL

Write-Host "`nWSL Command exited with code: $LASTEXITCODE" -ForegroundColor Magenta

# Cleanup
Remove-Item $TempScriptHost -ErrorAction SilentlyContinue
