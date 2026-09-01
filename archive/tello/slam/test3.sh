#!/bin/bash
# ==============================================================================
# scripts/tello/slam/test3.sh -- Test 3: the SLAM hover-hold + land-on-loss node,
# ON THE REAL TELLO. This is the stabilization test C1 gates, NOT a vision check.
#
# Same bring-up as run.sh (RX video + stella pose), but the manual-teleop pane is
# replaced by tello_slam_hold -- the node that reads slam/pose + slam/tracking_state
# and ACTIVELY commands the drone to hold the position you engage at, landing if
# tracking stays lost. The node owns the Tello command+state sockets (exactly as
# teleop did), so do NOT run teleop at the same time -- one command client only.
#
# Four panes (drone @ 192.168.10.1 over its own WiFi AP):
#   1. llm_to_action_gstreamer_rx --tello  -- decode H.264 on UDP 11111 -> camera/stream
#   2. stella_vslam_monocular              -- camera/stream -> slam/pose + slam/tracking_state
#   3. tello_slam_hold                     -- THE STABILIZER (T/L takeoff/land, H hold, G release)
#   4. measure_tello_slam.py               -- logs slam/pose for the record
#
# THE KEYS (in the tello_slam_hold pane):
#   T  takeoff        L  land        Esc  land + quit
#   H  engage hold -- captures the CURRENT SLAM position as the setpoint, then the
#                     node fights to hold it. Watch for "[hold] setpoint E=.. N=.. U=.."
#                     -- that line means pose + tracking_state are flowing and it locked on.
#   G  release     -- back to a plain zero-velocity hover (no SLAM hold).
#
# The node's own [hold] output is ALSO written to runs/hold_<stamp>.log so it can be
# read after the flight (the tmux pane scrollback is otherwise lost).
#
# HOW TO READ IT (the honest A/B, over BARE floor so the VPS can't cheat):
#   - Fly up, hover with G (hold OFF) ~20s: it WILL drift (VPS blind on bare floor).
#   - Press H (hold ON) ~20s: the node should arrest the drift and hold station.
#   - Film both with a fixed phone; run ../measure_drift.py on each clip for metres.
#   - If "[hold] setpoint" never prints -> tracking_state/pose not arriving (tell agent5).
#   - If it prints "[hold] recovery LAND" -> SLAM stayed lost; it landed on purpose.
#
# SAFETY: on bare floor with hold OFF the drone drifts for real. Low altitude, small
# clear space, hand ready, thumb on L.
#
# PREREQ: joined to the Tello WiFi. The Tello tree + SLAM tree are already built
# (this script only launches existing binaries).
#
# Run:  cd scripts/tello/slam && ./test3.sh
# ==============================================================================
set -u
cd "$(dirname "$0")" || exit 1
REPO_ROOT="$(cd ../../.. && pwd)"

SESSION_NAME="${SESSION_NAME:-tello_slam_hold}"

TELLO_BIN_DIR="/root/groundstation/build/release/shared/tello/bin"
RX_BIN="$TELLO_BIN_DIR/llm_to_action_gstreamer_rx"
HOLD_BIN="$TELLO_BIN_DIR/tello_slam_hold"

SLAM_BIN_DIR="${SLAM_BIN_DIR:-$REPO_ROOT/build/release/slam/bin}"
SLAM_BINARY="$SLAM_BIN_DIR/stella_vslam_monocular"

export STELLA_CONFIG_PATH="${STELLA_CONFIG_PATH:-$REPO_ROOT/config/stella_config_tello.yaml}"
export STELLA_VOCAB_PATH="${STELLA_VOCAB_PATH:-$REPO_ROOT/dependencies/orb_vocab.fbow}"

MEASURE="$REPO_ROOT/scripts/tello/slam/measure_tello_slam.py"
STAMP="$(date +%Y%m%dT%H%M%S)"
MEASURE_LOG="${MEASURE_LOG:-$REPO_ROOT/scripts/tello/slam/runs/test3_${STAMP}.log}"
HOLD_LOG="$REPO_ROOT/scripts/tello/slam/runs/hold_${STAMP}.log"
mkdir -p "$REPO_ROOT/scripts/tello/slam/runs"

# --- preflight ---
for b in "$RX_BIN" "$HOLD_BIN" "$SLAM_BINARY"; do
    if [ ! -x "$b" ]; then
        echo "[ERROR] missing binary: $b"
        echo "        tello_slam_hold builds under a Tello-backend config"
        echo "        (-DGROUNDSTATION_BUILD_EXECUTABLE=ON -DGROUNDSTATION_BUILD_BACKEND_TELLO=ON)."
        exit 1
    fi
done
for asset in "$STELLA_CONFIG_PATH" "$STELLA_VOCAB_PATH"; do
    if [ ! -f "$asset" ]; then
        echo "[ERROR] missing SLAM asset: $asset"
        exit 1
    fi
done

cleanup() {
    echo -e "\n[CLEANUP] killing lingering processes..."
    pkill -9 -f "stella_vslam_monocular" 2>/dev/null || true
    pkill -9 -f "measure_tello_slam.py"  2>/dev/null || true
    pkill -9 -f "llm_to_action_"         2>/dev/null || true
    pkill -9 -f "tello_slam_hold"        2>/dev/null || true
    tmux kill-session -t "$SESSION_NAME"  2>/dev/null || true
    echo "[SUCCESS] clean."
}
trap cleanup EXIT INT TERM

DELAY_RX=2
DELAY_SLAM=6
DELAY_HOLD=8       # after stella is publishing slam/pose + slam/tracking_state
DELAY_MEASURE=9

# stdbuf -oL so the node's [hold] lines reach the tee'd log immediately (a pipe would
# otherwise block-buffer stdout and the log would fill only on exit).
CMD_RX="export LD_LIBRARY_PATH=$TELLO_BIN_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_RX && $RX_BIN --tello; echo 'RX stopped'; read"
CMD_SLAM="export LD_LIBRARY_PATH=$SLAM_BIN_DIR:\$LD_LIBRARY_PATH && \
    export STELLA_CONFIG_PATH=$STELLA_CONFIG_PATH && \
    export STELLA_VOCAB_PATH=$STELLA_VOCAB_PATH && \
    sleep $DELAY_SLAM && $SLAM_BINARY; echo 'SLAM stopped'; read"
CMD_HOLD="export LD_LIBRARY_PATH=$TELLO_BIN_DIR:\$LD_LIBRARY_PATH && \
    sleep $DELAY_HOLD && stdbuf -oL $HOLD_BIN 2>&1 | tee $HOLD_LOG; echo 'hold node stopped'; read"
CMD_MEASURE="sleep $DELAY_MEASURE && python3 $MEASURE 2>&1 | tee $MEASURE_LOG; \
    echo 'measure stopped'; read"

echo "=================================================================="
echo " Test 3 -- SLAM hover-hold + land-on-loss on the real Tello"
echo " keys (hold pane): T=takeoff L=land  H=engage-hold G=release  Esc=quit"
echo " pose log : $MEASURE_LOG"
echo " hold log : $HOLD_LOG   <-- send me THIS after the run"
echo " A/B : bare floor. G (hold off) ~20s -> H (hold on) ~20s. Film both."
echo " watch for: '[hold] setpoint ...' = locked on;  '[hold] recovery LAND' = lost."
echo "=================================================================="
tmux start-server 2>/dev/null || true
tmux set-option -g history-limit 200000 2>/dev/null || true
tmux new-session  -d -s "$SESSION_NAME" -n "TelloHold" "$CMD_RX"
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_SLAM"
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_HOLD"
tmux split-window -v -t "$SESSION_NAME:0" "$CMD_MEASURE"
tmux select-layout -t "$SESSION_NAME:0" tiled
tmux attach-session -t "$SESSION_NAME"
