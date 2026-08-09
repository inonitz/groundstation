#!/bin/bash
# ==============================================================================
# sim_core.sh — shared launch engine for the llm_to_action SITL test harness.
# NOT run directly. Each scripts/test/<feature>/run.sh sets its knobs, then:
#     source ../lib/sim_core.sh
# to bring up PX4 SITL + Gazebo + the FMU (+ optional VLM) in one tmux session.
#
# Caller knobs (set BEFORE sourcing; defaults below):
#   FMU_OBJECTIVE    mission string handed to the FMU.
#   FMU_CANNED_FLAG  canned-plan flag, e.g. --canned-rotate ("" = VLM-driven).
#   WORLD_NAME       sim world basename in dependencies/ (default: default_car).
#   SPAWN_POSE       drone spawn x,y,z (default: 0,7,3).
#   LAUNCH_VLM       1 => also start the Qwen3-VL llama-server pane (default: 0).
#   SESSION_NAME     tmux session (default: llmsim).
#   DRAIN_BATTERY    1 => PX4 SITL drains battery for failsafe tests.
# ==============================================================================

: "${FMU_OBJECTIVE:=Canned SITL test.}"
FMU_CANNED_FLAG="${FMU_CANNED_FLAG-}"   # allow an explicit empty (VLM) value
: "${WORLD_NAME:=default_car}"
: "${SPAWN_POSE:=0,7,3}"
: "${LAUNCH_VLM:=0}"
: "${SESSION_NAME:=llmsim}"

# --- fixed config (absolute paths; cwd-independent) ---
BUILD_DIR="/root/groundstation/build/release/shared"
BUILD_BINARY_DIR="$BUILD_DIR/bin"
PX4_DIRECTORY="/root/PX4-Autopilot"
ASSET_DIR_PATH="/root/groundstation/dependencies"
GZ_GIMBAL_SDF_FILE="$PX4_DIRECTORY/Tools/simulation/gz/models/gimbal/model.sdf"
TARGET_WORLD_DIR="$PX4_DIRECTORY/Tools/simulation/gz/worlds"
GZ_SIM_SYSTEM_PLUGIN_PATH="$BUILD_BINARY_DIR:$GZ_SIM_SYSTEM_PLUGIN_PATH"
ONNXRUNTIME_LIB_DIR="$BUILD_DIR/_deps/onnxruntime/onnxruntime-linux-x64-1.20.1/lib"
GZ_SIM_RESOURCE_PATH="/root/groundstation/dependencies/gz_models:$GZ_SIM_RESOURCE_PATH"
DELAY_RX=4
DELAY_FMU=15

# --- cleanup ---
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

# --- world + camera plugin setup ---
echo "[INFO] Linking world asset ($WORLD_NAME)..."
mkdir -p "$TARGET_WORLD_DIR"
if [ -e "$TARGET_WORLD_DIR/$WORLD_NAME.sdf" ]; then rm -f "$TARGET_WORLD_DIR/$WORLD_NAME.sdf"; fi
ln -s "$ASSET_DIR_PATH/$WORLD_NAME.sdf" "$TARGET_WORLD_DIR/$WORLD_NAME.sdf"

echo "[INFO] Patching gimbal SDF with the GStreamer camera plugin..."
if [ ! -f "${GZ_GIMBAL_SDF_FILE}.bak" ]; then
    cp "$GZ_GIMBAL_SDF_FILE" "${GZ_GIMBAL_SDF_FILE}.bak"
fi
if ! grep -q "libGazeboGstCameraPlugin.so" "$GZ_GIMBAL_SDF_FILE"; then
    sed -i '/<\/camera>/a \        <plugin filename="libGazeboGstCameraPlugin.so" name="gazebo::GstCameraPlugin"></plugin>' "$GZ_GIMBAL_SDF_FILE"
fi

# --- opt-in SITL battery drain (failsafe tests) ---
if [ "${DRAIN_BATTERY:-0}" = "1" ]; then
    export PX4_PARAM_SIM_BAT_MIN_PCT=0.0
    export PX4_PARAM_SIM_BAT_DRAIN=1.5   # ~%/s drain; tune for a short test
    echo "[INFO] DRAIN_BATTERY=1 -> PX4 SIM_BAT_MIN_PCT=0.0 SIM_BAT_DRAIN=1.5"
else
    # PX4 SITL's sim battery drains to ~16% within ~10s of takeoff, tripping the RTH
    # failsafe (kBatteryReturnPct=20) and hijacking every canned plan (takeoff -> GO home
    # -> land). Pin the battery full for normal runs. ':=' so a test that sets its own
    # battery params first (e.g. battery/run.sh) is NOT overridden.
    : "${PX4_PARAM_SIM_BAT_MIN_PCT:=100.0}"
    export PX4_PARAM_SIM_BAT_MIN_PCT
    echo "[INFO] SITL battery floor SIM_BAT_MIN_PCT=$PX4_PARAM_SIM_BAT_MIN_PCT (RTH failsafe won't spuriously fire)."
fi

# --- command definitions ---
CMD_AGENT="MicroXRCEAgent udp4 -p 8888"
CMD_PX4="\
    export PX4_GZ_MODEL_POSE=$SPAWN_POSE && \
    export GZ_SIM_SYSTEM_PLUGIN_PATH=$GZ_SIM_SYSTEM_PLUGIN_PATH && \
    export GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH && \
    export PX4_GZ_WORLD=$WORLD_NAME && \
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
CMD_KEYBOARD="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_FMU && $BUILD_BINARY_DIR/llm_to_action_keyboard_hook; \
    echo 'keyboard stopped'; read"
CMD_VLM="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:\$LD_LIBRARY_PATH && \
    $BUILD_BINARY_DIR/llama-server \
    -m /root/models/vlm/Qwen3-VL-2B-Instruct/Qwen3-VL-2B-Instruct-Q4_K_M.gguf \
    --mmproj /root/models/vlm/Qwen3-VL-2B-Instruct/mmproj-BF16.gguf \
    -dev Vulkan0 -ngl 99 -c 65536 --flash-attn on --temp 0.3 \
    --host 0.0.0.0 --port 8080 --threads 1; echo 'llama-server stopped'; read"

# --- launch tmux ---
echo "[INFO] Launching tmux session '$SESSION_NAME'..."
# Large scrollback: a long hover (interrupt-storm) or the override toggle otherwise flushes the
# early takeoff/interrupt lines out of tmux's default 2000-line history before filter.sh captures.
tmux start-server 2>/dev/null || true
tmux set-option -g history-limit 200000 2>/dev/null || true
tmux new-session  -d -s "$SESSION_NAME" -n "DevEnv" "$CMD_AGENT"
tmux split-window -h -t "$SESSION_NAME:0" "$CMD_PX4"
tmux split-window -v -t "$SESSION_NAME:0.0" "$CMD_RX"
tmux split-window -v -t "$SESSION_NAME:0.2" "$CMD_FMU"
if [ "$LAUNCH_VLM" = "1" ]; then
    tmux split-window -v -t "$SESSION_NAME:0.1" "$CMD_VLM"
fi
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_KEYBOARD"
tmux select-layout -t "$SESSION_NAME:0" tiled
tmux attach-session -t "$SESSION_NAME"
