#!/bin/sh

HostPath=~/workspaces/groundstation
ContainerPath=/root/groundstation
args=(
    # Run interactive, clean up after, grant privileges
    -it --rm --privileged

    # GUI and Display mapping
    -v "/tmp/.X11-unix:/tmp/.X11-unix:rw"
    -e "DISPLAY"
    -e "QT_X11_NO_MITSHM=1"

    # GPU passthrough
    -e "NVIDIA_DRIVER_CAPABILITIES=all"
    -e "NVIDIA_VISIBLE_DEVICES=all"
    --gpus=all

    # Use host network
    --net=host

    # Local Devenv Folder Mount
    -v "${HostPath}:${ContainerPath}"

    # VSCode Extensions
    -v "vscode_server_cache:/root/.vscode-server"
)


# Execute
# Allow local X11 connections
xhost +local:root
docker run "${args[@]}" px4_gazebo-lts-2028_ros2-lts-2029 bash


