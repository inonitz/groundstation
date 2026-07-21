$RawPath       = Split-Path $PSScriptRoot -Parent
$LinuxSafePath = $RawPath -replace '\\', '/'
$HostPath      = (wsl wslpath -a "$LinuxSafePath").Trim()

# Define and convert Model Paths
$WindowsHome          = [Environment]::GetFolderPath("UserProfile")
$WindowsHomeLinuxSafe = $WindowsHome -replace '\\', '/'
$WSLHome              = (wsl wslpath -a "$WindowsHomeLinuxSafe").Trim()

$HostPathASRModel = "$WSLHome/models/asr"
$HostPathVLMModel = "$WSLHome/models/vlm"

$ContainerPath             = "/root/groundstation"
$ContainerPathASRModelPath = "/root/models/asr"
$ContainerPathVLMModelPath = "/root/models/vlm"

# Core Arguments (Network, Privileges, Display, Audio, Models)
$dockerArguments = @(
    "docker run --rm -it",
    "--privileged",
    "--net=host",
    
    # WSLg Display Mounts
    "-v /tmp/.X11-unix:/tmp/.X11-unix:rw",
    "-v /mnt/wslg:/mnt/wslg",
    '-e DISPLAY=$DISPLAY',
    "-e WAYLAND_DISPLAY=wayland-0",
    "-e XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir",
    "-e QT_X11_NO_MITSHM=1",

    # WSLg Audio (PulseAudio) Mounts
    "-v /mnt/wslg/PulseServer:/tmp/pulse-socket",
    "-e PULSE_SERVER=unix:/tmp/pulse-socket",

    # Project Mount
    "-v ${HostPath}:${ContainerPath}",

    # Model Mounts
    "-v ${HostPathASRModel}:${ContainerPathASRModelPath}",
    "-v ${HostPathVLMModel}:${ContainerPathVLMModelPath}",

    # VSCode
    "-v vscode_server_cache:/root/.vscode-server"
)

# GPU Agnostic Detection Module
$VideoControllers = Get-CimInstance Win32_VideoController
$HasNvidia = $VideoControllers | Where-Object { $_.Name -match "NVIDIA" }

if ($HasNvidia) {
    Write-Host "NVIDIA GPU Detected. Applying Native GPU Passthrough..." -ForegroundColor Green
    $dockerArguments += @(
        "--gpus=all",
        "-e NVIDIA_DRIVER_CAPABILITIES=all",
        "-e NVIDIA_VISIBLE_DEVICES=all"
    )
} else {
    Write-Host "Non-NVIDIA GPU Detected. Applying Generic D3D12/dxg Passthrough..." -ForegroundColor Yellow
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

# Execution Command (includes audio socket config)
$dockerArguments += "px4_gazebo-lts-2028_ros2-lts-2029 bash -c `"echo -e 'pcm.!default { type pulse }\nctl.!default { type pulse }' > ~/.asoundrc && exec bash`""

Write-Host "Firing up Gazebo in WSL2..." -ForegroundColor Cyan
$dockerCmd = $dockerArguments -join ' '

# Allow local X11 connections inside WSL
wsl --exec bash -c "xhost +local:root > /dev/null 2>&1 || true"

# Execute
wsl --exec bash -c $dockerCmd