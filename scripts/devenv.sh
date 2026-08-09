#!/bin/sh
HostPathProjectPath="$HOME/workspaces/groundstation"
ContainerPathProjectPath="/root/groundstation"

HostPathASRModel="$HOME/models/asr"
ContainerPathASRModelPath="/root/models/asr"

HostPathVLMModel="$HOME/models/vlm"
ContainerPathVLMModelPath="/root/models/vlm"

HostPathVisionModel="$HOME/models/vision"
ContainerPathVisionModelPath="/root/models/vision"

# Clear parameters
set --

# Run interactive, clean up, privileges
set -- "$@" -it --rm --privileged

# GUI mapping
set -- "$@" -v "/tmp/.X11-unix:/tmp/.X11-unix:rw"
set -- "$@" -e "DISPLAY"
set -- "$@" -e "QT_X11_NO_MITSHM=1"
set -- "$@" -e "XDG_RUNTIME_DIR=/tmp"
set -- "$@" -e "RTK_TELEMETRY_DISABLED=1"

# Host network
set -- "$@" --net=host

# Folder Mounts
set -- "$@" -v "${HostPathProjectPath}:${ContainerPathProjectPath}"
set -- "$@" -v "/run/user/$(id -u)/pulse/native:/tmp/pulse-socket"
set -- "$@" -v "$HOME/.config/pulse/cookie:/root/.config/pulse/cookie:ro"
set -- "$@" -e "PULSE_SERVER=unix:/tmp/pulse-socket"
set -- "$@" -v "${HostPathASRModel}:${ContainerPathASRModelPath}"
set -- "$@" -v "${HostPathVLMModel}:${ContainerPathVLMModelPath}"
set -- "$@" -v "${HostPathVisionModel}:${ContainerPathVisionModelPath}"
set -- "$@" -v "vscode_server_cache:/root/.vscode-server"
set -- "$@" -v "$HOME/.claude:/root/.claude"

# DRI for Intel/AMD/Generic
if [ -d "/dev/dri" ]; then
    set -- "$@" --device "/dev/dri"
fi

# AMD ROCm Compute & Vulkan Fix
if [ -e "/dev/kfd" ]; then
    set -- "$@" --device "/dev/kfd"
    set -- "$@" --security-opt seccomp=unconfined

    # Surgical fix Vulkan AMD JSON. Added radeon_icd.json.
    for icd in "/usr/share/vulkan/icd.d/radeon_icd.json" "/etc/vulkan/icd.d/radeon_icd.json" "/usr/share/vulkan/icd.d/radeon_icd.x86_64.json" "/usr/share/vulkan/icd.d/amd_icd64.json"; do
        if [ -f "$icd" ]; then
            set -- "$@" -v "$icd:$icd"
        fi
    done

    # Surgical fix Vulkan AMD Shared Library.
    for so in "/lib/x86_64-linux-gnu/libvulkan_radeon.so" "/usr/lib/x86_64-linux-gnu/libvulkan_radeon.so" "/usr/lib64/libvulkan_radeon.so" "/usr/lib/libvulkan_radeon.so"; do
        if [ -f "$so" ]; then
            set -- "$@" -v "$so:$so"
        fi
    done
fi

# NVIDIA Check & Dynamic Path Loop
if command -v nvidia-smi >/dev/null 2>&1; then
    set -- "$@" -e "NVIDIA_DRIVER_CAPABILITIES=all"
    set -- "$@" -e "NVIDIA_VISIBLE_DEVICES=all"
    set -- "$@" --gpus=all

    # Surgical fix Vulkan. Loop through common host paths.
    for icd in "/usr/share/vulkan/icd.d/nvidia_icd.json" "/etc/vulkan/icd.d/nvidia_icd.json" "/usr/local/share/vulkan/icd.d/nvidia_icd.json"; do
        if [ -f "$icd" ]; then
            set -- "$@" -v "$icd:/etc/vulkan/icd.d/nvidia_icd.json"
            break
        fi
    done

    # Surgical fix EGL. Loop through common host paths.
    for egl in "/usr/share/glvnd/egl_vendor.d/10_nvidia.json" "/etc/glvnd/egl_vendor.d/10_nvidia.json" "/usr/local/share/glvnd/egl_vendor.d/10_nvidia.json"; do
        if [ -f "$egl" ]; then
            set -- "$@" -v "$egl:/usr/share/glvnd/egl_vendor.d/10_nvidia.json"
            break
        fi
    done
fi

# Container startup command (kept as a variable so it stays readable, multi-line).
# The Tello firewall rules are separated from the && chain and inserted unconditionally.
# They used to be `iptables -C ... || iptables -I ...` hung off the chain, which failed
# silently two ways: an earlier command returning non-zero skipped them, and a -C match
# against rules from a previous session skipped the insert even though ufw later rebuilt
# INPUT and wiped them. Delete-then-insert is idempotent and cannot be short-circuited,
# and the printed chain head makes a missing rule visible at launch.
ContainerStartupCmd="\
    mkdir -p ~/.claude && \
    rtk init -g >/dev/null 2>&1 && \
    echo -e 'pcm.!default { type pulse }\nctl.!default { type pulse }' > ~/.asoundrc; \
    for TelloUdpPort in 8890 11111; do \
        while iptables -D INPUT -p udp --dport \$TelloUdpPort -j ACCEPT 2>/dev/null; do :; done; \
        iptables -I INPUT 1 -p udp --dport \$TelloUdpPort -j ACCEPT; \
    done; \
    echo '[devenv] Tello firewall rules:'; iptables -S INPUT | head -3; \
    exec bash"

# Execute
xhost +local:root
docker run "$@" px4_gazebo-lts-2028_ros2-lts-2029 bash -c "$ContainerStartupCmd"
