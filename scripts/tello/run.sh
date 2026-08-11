#!/bin/bash
# ==============================================================================
# scripts/tello/run.sh -- real DJI Tello bring-up launcher (hardware, not SITL).
#
# Plays the role scripts/test/lib/sim_core.sh plays for the SITL harness, minus
# everything simulation: no Gazebo, no PX4, no world linking, no bag recorder.
# Brings up three panes in one tmux session, all talking to the real drone at
# 192.168.10.1 over the drone's own WiFi AP:
#   1. llm_to_action_gstreamer_rx --tello -- decodes raw H.264 on UDP 11111.
#   2. llm_to_action_fmu_tello            -- connects the Tello (command mode +
#                                            streamon), runs the 20Hz control loop
#                                            and the ~20Hz rc keepalive.
#   3. llm_to_action_keyboard_hook        -- manual arm / takeoff / interrupt / land.
#
# The RX pane starts first so it is already listening on 11111 before the FMU
# triggers streamon; otherwise the first frames are lost.
#
# PREREQ: the host must be joined to the Tello's WiFi (SSID TELLO-XXXXXX). The host
# then gets 192.168.10.2 and the drone is 192.168.10.1 (hardcoded in
# tello_backend_base.hpp -- no CLI arg). Build the Tello binaries first; see README.md.
#
# Run:  cd scripts/tello && ./run.sh
# ==============================================================================
set -u
cd "$(dirname "$0")" || exit 1

# --- knobs (override on the command line, e.g. FMU_OBJECTIVE="..." ./run.sh) ---
: "${FMU_OBJECTIVE:=Take off, yaw-scan the area, describe what you see, then land.}"
: "${FMU_FLAG:=}"   # optional canned-plan flag, e.g. --canned-rotate (no-VLM airframe+ROTATE test). Empty = VLM-driven.
: "${SESSION_NAME:=tello}"
# Per-drone runtime tuning profile (ROADMAP 9.14). Defaults to the apartment-scale Tello
# profile so ./run.sh flies indoor-safe constants with NO rebuild -- edit config/tello.yaml
# and re-run. Override to another profile, or to "" to fly on the compiled SITL defaults.
# The FMU aborts if this points at a missing/unreadable/unparsable file.
: "${DRONE_CONFIG:=/root/groundstation/config/tello.yaml}"
export DRONE_CONFIG

# --- fixed config (absolute paths; cwd-independent) ---
BUILD_DIR="/root/groundstation/build/release/shared/tello"
BUILD_BINARY_DIR="$BUILD_DIR/bin"
ONNXRUNTIME_LIB_DIR="$BUILD_DIR/_deps/onnxruntime/onnxruntime-linux-x64-1.20.1/lib"
DELAY_RX=2
DELAY_FMU=5

FMU_BIN="$BUILD_BINARY_DIR/llm_to_action_fmu_tello"
RX_BIN="$BUILD_BINARY_DIR/llm_to_action_gstreamer_rx"
KB_BIN="$BUILD_BINARY_DIR/llm_to_action_keyboard_hook"

# --- preflight: fail loudly if the Tello tree was never built ---
for b in "$FMU_BIN" "$RX_BIN" "$KB_BIN"; do
    if [ ! -x "$b" ]; then
        echo "[ERROR] missing binary: $b"
        echo "[ERROR] build the Tello tree first -- see scripts/tello/README.md (Build)."
        exit 1
    fi
done

# --- cleanup ---
cleanup() {
    echo -e "\n[CLEANUP] Killing lingering processes..."
    pkill -9 -f "llm_to_action_" 2>/dev/null || true
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true
    echo "[SUCCESS] Clean."
}
trap cleanup EXIT INT TERM

# --- command definitions ---
CMD_RX="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_RX && $RX_BIN --tello; \
    echo 'RX stopped'; read"
CMD_FMU="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:$ONNXRUNTIME_LIB_DIR:\$LD_LIBRARY_PATH && \
    export DRONE_CONFIG=\"$DRONE_CONFIG\" && \
    sleep $DELAY_FMU && $FMU_BIN \"$FMU_OBJECTIVE\" $FMU_FLAG; \
    echo 'FMU stopped'; read"
CMD_KEYBOARD="export LD_LIBRARY_PATH=$BUILD_BINARY_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_FMU && $KB_BIN; \
    echo 'keyboard stopped'; read"

# --- launch tmux ---
echo "[INFO] Launching tmux session '$SESSION_NAME' (drone @ 192.168.10.1)..."
tmux start-server 2>/dev/null || true
tmux set-option -g history-limit 200000 2>/dev/null || true
tmux new-session  -d -s "$SESSION_NAME" -n "Tello" "$CMD_RX"
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_FMU"
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_KEYBOARD"
tmux select-layout -t "$SESSION_NAME:0" tiled

echo "[INFO] Attached. The key hook reads /dev/input globally, so no pane needs focus."
echo "[INFO] Enter toggles manual override; WASD/arrows fly. There is NO takeoff or land key."
echo "[INFO] Land before stopping (VLM plan, or the tello_teleop harness) -- do not kill mid-flight."
echo "[INFO] When done: Ctrl-B then D to detach, or Ctrl-C the focused pane to stop."
tmux attach-session -t "$SESSION_NAME"
