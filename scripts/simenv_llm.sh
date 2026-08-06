#!/bin/bash
# ==============================================================================
# simenv_llm.sh — rapid-prototyping stack for the llm_to_action FMU.
# RUN FROM /root/groundstation.
#
# Phase-1 smoke test: PX4 SITL + Gazebo + FMU driven by a CANNED plan
# (takeoff -> go forward 1m -> land). No VLM, no perception required.
#
# Usage: ./scripts/simenv_llm.sh [forward|cross|speed]
#   forward (default) -> takeoff, go forward 1m, land.
#   cross              -> takeoff, {go forward/left/back/right 1m then return
#                          to start} per axis in turn (FLU-frame sanity check;
#                          each leg re-anchored to actual position), land.
#   speed              -> takeoff, go forward 1m + return at LOW speed
#                          (15cm/s), same at HIGH speed (80cm/s), land --
#                          checks whether path curvature scales with speed.
#   approach           -> takeoff, closed-loop APPROACH toward a synthesized (no-YOLO)
#                          detection 3m north / 1m up of spawn, land. Verifies the servo
#                          reaches kApproachStandoffM and FAILs cleanly if the detection
#                          is killed mid-approach (see fmu_node_base.hpp
#                          kCannedApproachRigKillAfterMs).
#   approach-real      -> same servo, but real perception: real ONNX seg+depth models,
#                          target "car" (COCO label) against the Rubicon jeep already in
#                          the SITL world. No synthetic detection. Skips only the VLM
#                          planner, not vision.
#   vlm                -> launch the Qwen3-VL llama-server + drive the FMU from
#                          the VLM (no canned plan). Needs the model at
#                          /root/models/vlm and a Vulkan device.
#
# EXIT: Ctrl+B then :kill-session <Enter>  (tears down agent, PX4, gz, nodes).
# ==============================================================================

PLAN_MODE="${1:-forward}"

SESSION_NAME="llmsim"
BUILD_BINARY_DIR="/root/groundstation/build/release/shared/bin"
PX4_DIRECTORY="/root/PX4-Autopilot"
ASSET_DIR_PATH="/root/groundstation/dependencies"
GZ_GIMBAL_SDF_FILE="$PX4_DIRECTORY/Tools/simulation/gz/models/gimbal/model.sdf"
TARGET_WORLD_DIR="$PX4_DIRECTORY/Tools/simulation/gz/worlds"

GZ_SIM_SYSTEM_PLUGIN_PATH="$BUILD_BINARY_DIR:$GZ_SIM_SYSTEM_PLUGIN_PATH"
ONNXRUNTIME_LIB_DIR="/root/groundstation/build/release/shared/_deps/onnxruntime/onnxruntime-linux-x64-1.20.1/lib"
GZ_SIM_RESOURCE_PATH="/root/groundstation/dependencies/gz_models:$GZ_SIM_RESOURCE_PATH"

if [ "$PLAN_MODE" = "cross" ]; then
    FMU_OBJECTIVE="Fly forward/left/back/right 1m, returning to start after each, then land."
    FMU_CANNED_FLAG="--canned-cross"
elif [ "$PLAN_MODE" = "speed" ]; then
    FMU_OBJECTIVE="Fly forward 1m + return at low then high speed, then land."
    FMU_CANNED_FLAG="--canned-speed"
elif [ "$PLAN_MODE" = "approach" ]; then
    FMU_OBJECTIVE="Approach the canned target, then land."
    FMU_CANNED_FLAG="--canned-approach"
elif [ "$PLAN_MODE" = "approach-real" ]; then
    FMU_OBJECTIVE="Approach the car, then land."
    FMU_CANNED_FLAG="--canned-approach-real"
elif [ "$PLAN_MODE" = "vlm" ]; then
    FMU_OBJECTIVE="Take off, fly forward 1 meter, then land."
    FMU_CANNED_FLAG=""
else
    FMU_OBJECTIVE="Fly forward 1m then land."
    FMU_CANNED_FLAG="--canned"
fi

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
    export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH && \
    export PX4_GZ_WORLD=rubicon && \
    export PX4_NET_INTERFACE=eth0 && \
    cd $PX4_DIRECTORY && \
    make px4_sitl gz_x500_gimbal; \
    echo 'PX4 EXITED. Press enter...'; read"

CMD_RX="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_RX && $BUILD_BINARY_DIR/llm_to_action_gstreamer_rx; \
    echo 'RX stopped'; read"

CMD_FMU="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:$ONNXRUNTIME_LIB_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_FMU && \
    $BUILD_BINARY_DIR/llm_to_action_fmu_px4 \"$FMU_OBJECTIVE\" $FMU_CANNED_FLAG; \
    echo 'FMU stopped'; read"

# Phase 2: VLM server (Qwen3-VL). Launched only in `vlm` plan mode.
CMD_VLM="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:\$LD_LIBRARY_PATH && \
    $BUILD_BINARY_DIR/llama-server \
    -m /root/models/vlm/Qwen3-VL-2B-Instruct/Qwen3-VL-2B-Instruct-Q4_K_M.gguf \
    --mmproj /root/models/vlm/Qwen3-VL-2B-Instruct/mmproj-BF16.gguf \
    -dev Vulkan0 -ngl 99 -c 65536 --flash-attn on --temp 0.3 \
    --host 0.0.0.0 --port 8080 --threads 1; echo 'llama-server stopped'; read"

# ==============================================================================
# Launch 4-pane tmux
# ==============================================================================
echo "[INFO] Launching tmux session '$SESSION_NAME'..."
tmux new-session  -d -s "$SESSION_NAME" -n "DevEnv" "$CMD_AGENT"
tmux split-window -h -t "$SESSION_NAME:0" "$CMD_PX4"
tmux split-window -v -t "$SESSION_NAME:0.0" "$CMD_RX"
tmux split-window -v -t "$SESSION_NAME:0.2" "$CMD_FMU"
if [ "$PLAN_MODE" = "vlm" ]; then
    tmux split-window -v -t "$SESSION_NAME:0.1" "$CMD_VLM"
fi
tmux select-layout -t "$SESSION_NAME:0" tiled
tmux attach-session -t "$SESSION_NAME"
