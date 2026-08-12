#!/bin/bash
# ==============================================================================
# scripts/tello/slam/run.sh -- C1: run stella_vslam on the REAL Tello and measure it.
#
# The Tello analogue of scripts/test/slam/run.sh (which is SITL). It brings up the
# real drone's forward video, attaches the SLAM node with Agent 4's calibrated
# config, and scores tracking -- so a human can fly a path + a return loop and get
# the C1 go/no-go numbers.
#
# NOTE: for a dated, self-correlating run + a digest, use ./c1test.sh instead of
# calling this directly -- it sets MEASURE_LOG to runs/c1_<stamp>.log for you.
#
# Four panes in one tmux session (drone @ 192.168.10.1 over its own WiFi AP):
#   1. llm_to_action_gstreamer_rx --tello  -- decode H.264 on UDP 11111 -> camera/stream
#   2. stella_vslam_monocular              -- camera/stream -> slam/pose (+ clouds)
#   3. tello_teleop                        -- MANUAL flight (T/L/WASD/RF/QE), no autonomy
#   4. measure_tello_slam.py               -- pose rate / tracking_frac / blind-frac / return err
#
# RX starts first so it is listening on 11111 before teleop's streamon. tello_teleop
# owns the command+state sockets (SDK mode + streamon), RX only decodes video, so the
# two coexist.
#
# PREREQ: joined to the Tello WiFi (SSID TELLO-XXXXXX; host becomes 192.168.10.2).
# Build the Tello tree AND the SLAM tree first (see scripts/tello/README.md and
# scripts/test/slam/README.md).
#
# Run:  cd scripts/tello/slam && ./run.sh   (or ./c1test.sh for a dated run + digest)
# ==============================================================================
set -u
cd "$(dirname "$0")" || exit 1
REPO_ROOT="$(cd ../../.. && pwd)"

SESSION_NAME="${SESSION_NAME:-tello_slam}"

# --- Tello binaries (shared tree) ---
TELLO_BIN_DIR="/root/groundstation/build/release/shared/tello/bin"
RX_BIN="$TELLO_BIN_DIR/llm_to_action_gstreamer_rx"
TELEOP_BIN="$TELLO_BIN_DIR/tello_teleop"

# --- SLAM binary (its own isolated tree, GROUNDSTATION_BUILD_SLAM=ON) ---
SLAM_BIN_DIR="${SLAM_BIN_DIR:-$REPO_ROOT/build/release/slam/bin}"
SLAM_BINARY="$SLAM_BIN_DIR/stella_vslam_monocular"

# Agent 4's calibrated Tello intrinsics. NOTE: the configs were relocated to config/,
# so slam2.hpp's compiled default (config/stella_config_px4.yaml) is the WRONG airframe --
# we set STELLA_CONFIG_PATH explicitly to the Tello config here.
export STELLA_CONFIG_PATH="${STELLA_CONFIG_PATH:-$REPO_ROOT/config/stella_config_tello.yaml}"
export STELLA_VOCAB_PATH="${STELLA_VOCAB_PATH:-$REPO_ROOT/dependencies/orb_vocab.fbow}"

MEASURE="$REPO_ROOT/scripts/tello/slam/measure_tello_slam.py"
# Honor a caller-set dated path (c1test.sh); else a fixed default.
MEASURE_LOG="${MEASURE_LOG:-$REPO_ROOT/scripts/tello/slam/tello_slam_check.log}"

# --- preflight ---
for b in "$RX_BIN" "$TELEOP_BIN" "$SLAM_BINARY"; do
    if [ ! -x "$b" ]; then
        echo "[ERROR] missing binary: $b"
        echo "        Build the Tello tree (scripts/tello/README.md) and the SLAM tree"
        echo "        (scripts/test/slam/README.md) first."
        exit 1
    fi
done
for asset in "$STELLA_CONFIG_PATH" "$STELLA_VOCAB_PATH"; do
    if [ ! -f "$asset" ]; then
        echo "[ERROR] missing SLAM asset: $asset"
        exit 1
    fi
done

# --- cleanup ---
cleanup() {
    echo -e "\n[CLEANUP] killing lingering processes..."
    pkill -9 -f "stella_vslam_monocular" 2>/dev/null || true
    pkill -9 -f "measure_tello_slam.py"  2>/dev/null || true
    pkill -9 -f "llm_to_action_"         2>/dev/null || true
    pkill -9 -f "tello_teleop"           2>/dev/null || true
    tmux kill-session -t "$SESSION_NAME"  2>/dev/null || true
    echo "[SUCCESS] clean."
}
trap cleanup EXIT INT TERM

DELAY_RX=2
DELAY_SLAM=6      # after RX is publishing camera/stream
DELAY_MEASURE=9

CMD_RX="export LD_LIBRARY_PATH=$TELLO_BIN_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_RX && $RX_BIN --tello; echo 'RX stopped'; read"
CMD_SLAM="export LD_LIBRARY_PATH=$SLAM_BIN_DIR:\$LD_LIBRARY_PATH && \
    export STELLA_CONFIG_PATH=$STELLA_CONFIG_PATH && \
    export STELLA_VOCAB_PATH=$STELLA_VOCAB_PATH && \
    sleep $DELAY_SLAM && $SLAM_BINARY; echo 'SLAM stopped'; read"
CMD_TELEOP="export LD_LIBRARY_PATH=$TELLO_BIN_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_RX && $TELEOP_BIN; echo 'teleop stopped'; read"
CMD_MEASURE="sleep $DELAY_MEASURE && python3 $MEASURE 2>&1 | tee $MEASURE_LOG; \
    echo 'measure stopped'; read"

echo "[INFO] launching tmux '$SESSION_NAME' (drone @ 192.168.10.1)..."
echo "[INFO] config=$STELLA_CONFIG_PATH"
echo "[INFO] measure log -> $MEASURE_LOG"
echo "[INFO] fly with teleop: T=takeoff L=land WASD=move RF=up/down QE=yaw Space=hover Esc=land+quit"
echo "[INFO] C1: fly a path, then a return-to-start loop; watch the [TELLO_SLAM] pane."
tmux start-server 2>/dev/null || true
tmux set-option -g history-limit 200000 2>/dev/null || true
tmux new-session  -d -s "$SESSION_NAME" -n "TelloSLAM" "$CMD_RX"
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_SLAM"
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_TELEOP"
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_MEASURE"
tmux select-layout -t "$SESSION_NAME:0" tiled
tmux attach-session -t "$SESSION_NAME"
