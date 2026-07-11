#!/bin/sh
HostPathProjectPath="$HOME/workspaces/groundstation"
ContainerPathProjectPath="/root/groundstation"

HostPathASRModel="$HOME/models/asr"
ContainerPathASRModelPath="/root/models/asr"

HostPathVLMModel="$HOME/models/vlm"
ContainerPathVLMModelPath="/root/models/vlm"

# Clear existing positional parameters
set --

# Run interactive, clean up after, grant privileges
set -- "$@" -it --rm --privileged

# GUI and Display mapping
set -- "$@" -v "/tmp/.X11-unix:/tmp/.X11-unix:rw"
set -- "$@" -e "DISPLAY"
set -- "$@" -e "QT_X11_NO_MITSHM=1"
# Fix IPC crash
set -- "$@" -e "XDG_RUNTIME_DIR=/tmp"

# GPU passthrough
set -- "$@" -e "NVIDIA_DRIVER_CAPABILITIES=all"
set -- "$@" -e "NVIDIA_VISIBLE_DEVICES=all"
set -- "$@" --gpus=all

# Use host network
set -- "$@" --net=host

# Local Devenv Folder Mount
set -- "$@" -v "${HostPathProjectPath}:${ContainerPathProjectPath}"

# Mount the Audio Device (For ASR Testing, Native Linux)
set -- "$@" -v "/run/user/$(id -u)/pulse/native:/tmp/pulse-socket"
set -- "$@" -v "$HOME/.config/pulse/cookie:/root/.config/pulse/cookie:ro"
set -- "$@" -e "PULSE_SERVER=unix:/tmp/pulse-socket"

# Mount the ASR Model Path
set -- "$@" -v "${HostPathASRModel}:${ContainerPathASRModelPath}"

# Mount the VLM Model Path
set -- "$@" -v "${HostPathVLMModel}:${ContainerPathVLMModelPath}"

# Mount GPU Direct Rendering Infrastructure (DRI) nodes
set -- "$@" --device "/dev/dri"

# Mount NVIDIA Vulkan Driver description file (Surgical fix for Vulkan loader)
set -- "$@" -v "/usr/share/vulkan/icd.d/nvidia_icd.json:/etc/vulkan/icd.d/nvidia_icd.json:ro"
# Mount NVIDIA EGL Driver description file (Surgical fix for EGL loader)
set -- "$@" -v "/usr/share/glvnd/egl_vendor.d/10_nvidia.json:/usr/share/glvnd/egl_vendor.d/10_nvidia.json:ro"

# VSCode Extensions
set -- "$@" -v "vscode_server_cache:/root/.vscode-server"

# Execute
# Allow local X11 connections
xhost +local:root
docker run "$@" px4_gazebo-lts-2028_ros2-lts-2029 bash -c "echo -e 'pcm.!default { type pulse }\nctl.!default { type pulse }' > ~/.asoundrc && exec bash"