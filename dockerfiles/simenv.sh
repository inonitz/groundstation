#!/bin/bash

# ==============================================================================
# HOW TO SAFELY EXIT:
# 1. Press [Ctrl + B] (Tells tmux to listen for an orchestration command)
# 2. Type [:kill-session] (You will see this appear at the bottom of the screen)
# 3. Press [Enter]
#
# This completely destroys the background session and gracefully terminates the 
# MicroXRCEAgent, PX4 Autopilot, and all active ROS 2 nodes simultaneously.
# ==============================================================================

# ==============================================================================
# 1. CONTROL PANEL (Modify paths and configurations here)
# ==============================================================================
SESSION_NAME="devenv"
PX4_DIRECTORY="/root/PX4-Autopilot"
ASR_MODEL_PATH="/root/models/nvidia--parakeet-tdt-0.6b-v3/ggml-parakeet-tdt-0.6b-v3-f32.bin"

# Startup Delays (Adjust if services are racing or crashing on boot)
DELAY_PX4=2
DELAY_KEYBOARD=6
DELAY_ASR=7
DELAY_OFFBOARD=10

# ==============================================================================
# 2. COMMAND DEFINITIONS (Easily add/remove flags here)
# ==============================================================================
CMD_BUILD_CONF="./build.sh release shared configure"
CMD_BUILD_MAKE="./build.sh release shared build"
CMD_TERMINAL_2="MicroXRCEAgent udp4 -p 8888"
# Wrap the command in 'bash -c' with a 'read' at the end
CMD_TERMINAL_3="cd $PX4_DIRECTORY && make px4_sitl gz_x500_gimbal; echo 'CRASHED. Press enter to exit...'; read"
CMD_TERMINAL_4="./build/release/static/bin/ros2_speech_to_action_keyboard_input"

ASR_FLAGS=(
    "--backend=whisper-parakeet"
    "--model=$ASR_MODEL_PATH"
    "--fa"
    "--language=en"
    "--threads=1"
    "--gid=0"
    "--captureid=1"
)

CMD_TERMINAL_5="./build/release/shared/bin/ros2_speech_to_action_asr_server ${ASR_FLAGS[*]}"
CMD_TERMINAL_6="./build/release/shared/bin/ros2_speech_to_action_offboard_mode"


# ==============================================================================
# 3. EXECUTION BLOCK
# ==============================================================================
echo "🤖 Running pre-flight build..."
$CMD_BUILD_CONF && $CMD_BUILD_MAKE
if [ $? -ne 0 ]; then
    echo "❌ Build failed. Core logic broken. Exiting."
    exit 1
fi

echo "🏁 Launching 6-Pane Tmux Environment..."

# 1. Start Session (Pane 1)
tmux new-session -d -s "$SESSION_NAME" -n "DevEnv" "$CMD_TERMINAL_2"

# 2. Create the grid structure (3 columns)
tmux split-window -h -t "$SESSION_NAME:0" "$CMD_TERMINAL_3"
tmux split-window -h -t "$SESSION_NAME:0" "$CMD_TERMINAL_4"

# 3. Split each of the 3 columns to create 2 rows (Total 6 panes)
tmux split-window -v -t "$SESSION_NAME:0.0" "sleep $DELAY_KEYBOARD && $CMD_TERMINAL_5"
tmux split-window -v -t "$SESSION_NAME:0.2" "sleep $DELAY_ASR && $CMD_TERMINAL_6"
tmux split-window -v -t "$SESSION_NAME:0.4" "sleep $DELAY_OFFBOARD && $CMD_TERMINAL_7_PLACEHOLDER"

# 4. Final Tiling
tmux select-layout -t "$SESSION_NAME:0" tiled
tmux attach-session -t "$SESSION_NAME"