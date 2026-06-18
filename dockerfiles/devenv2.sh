#!/bin/sh
HostPath="$HOME/workspaces/groundstation"
ContainerPath="/root/groundstation"

# Clear existing positional parameters
set --

# Run interactive, clean up after, grant privileges
set -- "$@" -it --rm --privileged

# GUI and Display mapping
set -- "$@" -v "/tmp/.X11-unix:/tmp/.X11-unix:rw"
set -- "$@" -e "DISPLAY"
set -- "$@" -e "QT_X11_NO_MITSHM=1"

# GPU passthrough
set -- "$@" -e "NVIDIA_DRIVER_CAPABILITIES=all"
set -- "$@" -e "NVIDIA_VISIBLE_DEVICES=all"
set -- "$@" --gpus=all

# Use host network
set -- "$@" --net=host

# Local Devenv Folder Mount
set -- "$@" -v "${HostPath}:${ContainerPath}"

# VSCode Extensions
set -- "$@" -v "vscode_server_cache:/root/.vscode-server"

# Execute
# Allow local X11 connections
xhost +local:root
docker run "$@" px4_gazebo-lts-2028_ros2-lts-2029 bash