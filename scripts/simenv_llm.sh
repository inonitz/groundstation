#!/bin/bash
# ==============================================================================
# simenv_llm.sh — rapid-prototyping stack for the llm_to_action FMU.
# RUN FROM /root/groundstation.
#
# Phase-1 smoke test: PX4 SITL + Gazebo + FMU driven by a CANNED plan
# (takeoff -> go forward 1m -> land). No VLM, no perception required.
#
# EXIT: Ctrl+B then :kill-session <Enter>  (tears down agent, PX4, gz, nodes).
# ==============================================================================

SESSION_NAME="llmsim"
BUILD_BINARY_DIR="/root/groundstation/build/release/shared/bin"
PX4_DIRECTORY="/root/PX4-Autopilot"
ASSET_DIR_PATH="/root/groundstation/dependencies"
GZ_GIMBAL_SDF_FILE="$PX4_DIRECTORY/Tools/simulation/gz/models/gimbal/model.sdf"
TARGET_WORLD_DIR="$PX4_DIRECTORY/Tools/simulation/gz/worlds"

GZ_SIM_SYSTEM_PLUGIN_PATH="$BUILD_BINARY_DIR:$GZ_SIM_SYSTEM_PLUGIN_PATH"

# The canned smoke-test objective (string is informational; --canned drives it).
FMU_OBJECTIVE="Fly forward 1m then land."

# Startup delays (seconds) — let each layer boot before the next.
DELAY_RX=4
DELAY_FMU=15

# ==============================================================================
# Cleanup
# ==============================================================================
cleanup() {
    echo -e "\n[CLEANUP] Restoring gimbal SDF..."
    if [ -f "${GZ_GIMBAL_SDF_FILE}.bak" ]; then
        mv "${GZ_GIMBAL_SDF_FILE}.bak" "$GZ_GIMBAL_SDF_FILE"
    fi
    echo "[CLEANUP] Killing lingering processes..."
    pkill -9 -f "llm_to_action_"
    pkill -9 -f "llama-server"
    pkill -9 -f "gz"
    pkill -9 -f "px4"
    pkill -9 -f "MicroXRCEAgent"
    echo "[SUCCESS] Clean."
}
trap cleanup EXIT INT TERM

# ==============================================================================
# World + camera plugin setup (needed later; harmless for the canned test)
# ==============================================================================
echo "[INFO] Linking world asset..."
mkdir -p "$TARGET_WORLD_DIR"
if [ -e "$TARGET_WORLD_DIR/rubicon.sdf" ]; then rm -f "$TARGET_WORLD_DIR/rubicon.sdf"; fi
ln -s "$ASSET_DIR_PATH/rubicon.sdf" "$TARGET_WORLD_DIR/rubicon.sdf"

echo "[INFO] Patching gimbal SDF with the GStreamer camera plugin..."
if [ ! -f "${GZ_GIMBAL_SDF_FILE}.bak" ]; then
    cp "$GZ_GIMBAL_SDF_FILE" "${GZ_GIMBAL_SDF_FILE}.bak"
fi
if ! grep -q "libGazeboGstCameraPlugin.so" "$GZ_GIMBAL_SDF_FILE"; then
    sed -i '/<\/camera>/a \        <plugin filename="libGazeboGstCameraPlugin.so" name="gazebo::GstCameraPlugin"></plugin>' "$GZ_GIMBAL_SDF_FILE"
fi

# ==============================================================================
# Command definitions
# ==============================================================================
CMD_AGENT="MicroXRCEAgent udp4 -p 8888"

CMD_PX4="\
    export PX4_GZ_MODEL_POSE=0,7,3 && \
    export GZ_SIM_SYSTEM_PLUGIN_PATH=$GZ_SIM_SYSTEM_PLUGIN_PATH && \
    export PX4_GZ_WORLD=rubicon && \
    export PX4_NET_INTERFACE=eth0 && \
    cd $PX4_DIRECTORY && \
    make px4_sitl gz_x500_gimbal; \
    echo 'PX4 EXITED. Press enter...'; read"

CMD_RX="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_RX && $BUILD_BINARY_DIR/llm_to_action_gstreamer_rx; \
    echo 'RX stopped'; read"

CMD_FMU="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_FMU && \
    $BUILD_BINARY_DIR/llm_to_action_fmu \"$FMU_OBJECTIVE\" --canned; \
    echo 'FMU stopped'; read"

# Phase 2: VLM server (Qwen3-VL). Uncomment + add a pane when wiring the VLM.
# CMD_VLM="$BUILD_BINARY_DIR/llama_shared/bin/llama-server \
#     -m /root/models/vlm/Qwen3-VL-2B-Instruct/Qwen3-VL-2B-Instruct-Q4_K_M.gguf \
#     --mmproj /root/models/vlm/Qwen3-VL-2B-Instruct/mmproj-BF16.gguf \
#     -dev Vulkan0 -ngl 99 -c 4096 --flash-attn on --temp 0.2 \
#     --host 0.0.0.0 --port 8080 --threads 2; read"

# ==============================================================================
# Launch 4-pane tmux
# ==============================================================================
echo "[INFO] Launching tmux session '$SESSION_NAME'..."
tmux new-session  -d -s "$SESSION_NAME" -n "DevEnv" "$CMD_AGENT"
tmux split-window -h -t "$SESSION_NAME:0" "$CMD_PX4"
tmux split-window -v -t "$SESSION_NAME:0.0" "$CMD_RX"
tmux split-window -v -t "$SESSION_NAME:0.2" "$CMD_FMU"
tmux select-layout -t "$SESSION_NAME:0" tiled
tmux attach-session -t "$SESSION_NAME"
