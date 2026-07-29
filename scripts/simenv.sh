#!/bin/bash

# ==============================================================================
# RUN IN /root/groundstation
# HOW TO SAFELY EXIT:
# 1. Press [Ctrl + B] (Tells tmux to listen for an orchestration command)
# 2. Type [:kill-session] or [:exit-session]
# 3. Press [Enter]
#
# This completely destroys the background session and gracefully terminates the 
# MicroXRCEAgent, PX4 Autopilot, and all active ROS 2 nodes simultaneously.
# ==============================================================================

# ==============================================================================
# 1. CONTROL PANEL (Modify paths and configurations here)
# ==============================================================================
SESSION_NAME="devenv"
BUILD_DIRECTORY="/root/groundstation/build/release/shared"
BUILD_BINARY_DIR="$BUILD_DIRECTORY/bin"
PX4_DIRECTORY="/root/PX4-Autopilot"
ASR_MODEL_PATH="/root/models/asr/nvidia--parakeet-tdt-0.6b-v3/ggml-parakeet-tdt-0.6b-v3-q4_k.bin"
ASSET_DIR_PATH="/root/groundstation/dependencies"
# GAZEBO_MAP_FILEPATH="$ASSET_DIR_PATH/harmonic.sdf"
GAZEBO_MAP_FILEPATH="harmonic"

# Tell Gazebo where groundstation builds the .so file
GZ_SIM_SYSTEM_PLUGIN_PATH="$BUILD_BINARY_DIR:$GZ_SIM_SYSTEM_PLUGIN_PATH"
GZ_GIMBAL_SDF_FILE="$PX4_DIRECTORY/Tools/simulation/gz/models/gimbal/model.sdf"
TARGET_WORLD_DIR="$PX4_DIRECTORY/Tools/simulation/gz/worlds"

# Startup Delays (Adjust if services are racing or crashing on boot)
DELAY_PX4=2
DELAY_KEYBOARD=6
DELAY_ASR=7
DELAY_OFFBOARD=10

# ==============================================================================
# 2. CLEANUP MANAGEMENT (Automatic Restoration & Process Killing Lifecycle)
# ==============================================================================
cleanup() {
    echo -e "\n[CLEANUP] Restoring original gimbal SDF configuration..."
    if [ -f "${GZ_GIMBAL_SDF_FILE}.bak" ]; then
        mv "${GZ_GIMBAL_SDF_FILE}.bak" "$GZ_GIMBAL_SDF_FILE"
        echo "[SUCCESS] SDF file cleanly restored."
    else
        echo "[WARN] No backup found. File may already be clean."
    fi

    echo "[CLEANUP] Sweeping and force-killing lingering background processes..."
    pkill -9 -f "llama-server"
    pkill -9 -f "ruby"
    pkill -9 -f "gz"
    pkill -9 -f "px4"
    pkill -9 -f "MicroXRCEAgent"
    pkill -9 -f "ros2_speech_to_action"
    pkill -9 -f "parameter_bridge"
    echo "[SUCCESS] Zombie processes wiped cleanly."
}

# Catch normal exit, script cancellation, or session closure
trap cleanup EXIT INT TERM

# ==============================================================================
# 3. COMMAND DEFINITIONS
# ==============================================================================
CMD_BUILD_CONF="./build.sh release shared configure"
CMD_BUILD_MAKE="./build.sh release shared build"
CMD_TERMINAL_2="MicroXRCEAgent udp4 -p 8888"

#     export GZ_SIM_RESOURCE_PATH=$ASSET_DIR_PATH
CMD_TERMINAL_3="\
    export PX4_GZ_MODEL_POSE=0,7,3 && \
    export GZ_SIM_SYSTEM_PLUGIN_PATH=$GZ_SIM_SYSTEM_PLUGIN_PATH && \
    export PX4_GZ_WORLD=rubicon && \
    export PX4_NET_INTERFACE=eth0 && \
    cd $PX4_DIRECTORY && \
    make px4_sitl gz_x500_gimbal; \
    echo 'CRASHED. Press enter to exit...'; read"

CMD_TERMINAL_4="$BUILD_BINARY_DIR/ros2_speech_to_action_keyboard_input; echo 'Process Stopped'; read"

ASR_FLAGS=(
    "--backend=whisper-parakeet"
    "--model=$ASR_MODEL_PATH"
    "--fa"
    "--language=en"
    "--threads=1"
    "--gid=0"
    "--captureid=-1"
)

CMD_TERMINAL_5="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:$LD_LIBRARY_PATH && \
    $BUILD_BINARY_DIR/ros2_speech_to_action_asr_server ${ASR_FLAGS[*]}; echo 'Process Stopped'; read"

CMD_TERMINAL_6="$BUILD_BINARY_DIR/ros2_speech_to_action_offboard_mode; echo 'Process Stopped'; read"

CMD_TERMINAL_7="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:$LD_LIBRARY_PATH && \
    $BUILD_BINARY_DIR/llama_shared/bin/llama-server \
    -m /root/models/vlm/Qwen3-VL-2B-Instruct/Qwen3-VL-2B-Instruct-Q4_K_M.gguf \
    --mmproj /root/models/vlm/Qwen3-VL-2B-Instruct/mmproj-BF16.gguf \
    --verbose \
    -dev Vulkan0 \
    -ngl 99 \
    -c 1024 \
    --flash-attn on \
    --temp 0.2 \
    --host 0.0.0.0 \
    --port 8080 \
    --threads 2; echo 'Process Stopped'; read"

CMD_TERMINAL_8="ros2 run ros_gz_bridge parameter_bridge \
    /world/default/model/x500_gimbal_0/link/camera_link/sensor/camera/image@sensor_msgs/msg/Image[gz.msgs.Image; echo 'CRASHED.'; read"




# ==============================================================================
# 4. EXECUTION BLOCK
# ==============================================================================
# echo "[INFO] Building The Project"
# $CMD_BUILD_CONF && $CMD_BUILD_MAKE
# if [ $? -ne 0 ]; then
#     echo "[ERROR] Build failed. Core logic broken. Exiting."
#     exit 1
# fi

echo "[INFO] Syncing Gazebo Simulation World Assets..."
mkdir -p "$TARGET_WORLD_DIR"

# Clean old or broken links out to safely mount updated configurations
if [ -L "$TARGET_WORLD_DIR/rubicon.sdf" ] || [ -f "$TARGET_WORLD_DIR/rubicon.sdf" ]; then
    rm -f "$TARGET_WORLD_DIR/rubicon.sdf"
fi
ln -s "$ASSET_DIR_PATH/rubicon.sdf" "$TARGET_WORLD_DIR/rubicon.sdf"
echo "[SUCCESS] Symbolic link for rubicon.sdf generated dynamically."

echo "[INFO] Creating temporary backup and auto-patching gimbal SDF with GStreamer Plugin..."
if [ ! -f "${GZ_GIMBAL_SDF_FILE}.bak" ]; then
    cp "$GZ_GIMBAL_SDF_FILE" "${GZ_GIMBAL_SDF_FILE}.bak"
fi

if ! grep -q "libGazeboGstCameraPlugin.so" "$GZ_GIMBAL_SDF_FILE"; then
    sed -i '/<\/camera>/a \        <plugin filename="libGazeboGstCameraPlugin.so" name="gazebo::GstCameraPlugin"></plugin>' "$GZ_GIMBAL_SDF_FILE"
fi

echo "[INFO] Launching 6-Pane Tmux Environment..."

# 1. Start Session (Pane 1)
tmux new-session -d -s "$SESSION_NAME" -n "DevEnv" "$CMD_TERMINAL_2"

# 2. Create the grid structure (3 columns)
tmux split-window -h -t "$SESSION_NAME:0" "$CMD_TERMINAL_3"
tmux split-window -h -t "$SESSION_NAME:0" "$CMD_TERMINAL_4"

# 3. Split each of the 3 columns to create 2 rows (Total 6 panes)
tmux split-window -v -t "$SESSION_NAME:0.0" "sleep $DELAY_KEYBOARD && $CMD_TERMINAL_5"
tmux split-window -v -t "$SESSION_NAME:0.2" "sleep $DELAY_ASR && $CMD_TERMINAL_6"
# tmux split-window -v -t "$SESSION_NAME:0.4" "sleep $DELAY_OFFBOARD && $CMD_TERMINAL_7"

tmux split-window -v -t "$SESSION_NAME:0.4" "socat UDP4-LISTEN:14550,reuseaddr,fork UDP4-SENDTO:$PX4_SIM_HOST_ADDR:14550"

# 4. Final Tiling
tmux select-layout -t "$SESSION_NAME:0" tiled
tmux attach-session -t "$SESSION_NAME"