#!/bin/bash
# Lightweight color-discrimination showcase (2026-08-09): two differently-colored cars, no
# people, in the same Rubicon terrain SLAM needs to track. Tests whether the VLM picks the
# right object by a real visual attribute instead of just detecting "a car" -- a meaningfully
# harder capability than object presence alone. Built to dodge rubicon_targets' ~12GiB VRAM
# footprint (ROADMAP 9.15) for field demos without a big GPU on hand.
# Run:  cd scripts/test/colors && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: cd ../../slam && ./filter.sh (shares the
# same FMU log format -- there is no colors-specific filter.sh, this one is judged by eye).
cd "$(dirname "$0")" || exit 1

REPO_ROOT="$(cd ../../.. && pwd)"

SLAM_BIN_DIR="${SLAM_BIN_DIR:-$REPO_ROOT/build/release/slam-openmp/bin}"
SLAM_BINARY="$SLAM_BIN_DIR/stella_vslam_monocular"
COMPARATOR="$REPO_ROOT/scripts/test/slam/compare_ground_truth.py"
SLAM_CHECK_LOG="$REPO_ROOT/scripts/test/colors/slam_check.log"

export STELLA_CONFIG_PATH="${STELLA_CONFIG_PATH:-$REPO_ROOT/config/stella_config_px4.yaml}"
export STELLA_VOCAB_PATH="${STELLA_VOCAB_PATH:-$REPO_ROOT/dependencies/orb_vocab.fbow}"

if [ ! -x "$SLAM_BINARY" ]; then
    echo "[ERROR] $SLAM_BINARY missing. Build it first -- see scripts/test/slam/run.sh for the cmake invocation."
    exit 1
fi

# --- sim_core.sh knobs ---
: "${FMU_OBJECTIVE:=Find the BLUE car specifically -- there are two cars, only approach the blue one, then land.}"
: "${FMU_SCENARIO_FLAG:=none}"
WORLD_NAME="rubicon_colors"
SPAWN_POSE="0,7,3"
LAUNCH_VLM="${LAUNCH_VLM:-1}"
SESSION_NAME="${SESSION_NAME:-llmsim}"
# 2026-08-10: a 2-object color-discrimination task needs nowhere near 65536 tokens of history.
# This is the actual VRAM lever (sim_core.sh's -c, not scene object count -- see docs/NOTES.md).
# Could not verify an exact resulting VRAM figure in the dev sandbox (no nvidia-smi/rocm-smi,
# vulkaninfo reports no live heap usage here) -- check the real number with whatever GPU tool
# your machine has before trusting this value for a field demo.
: "${VLM_CTX_SIZE:=4096}"
export FMU_OBJECTIVE FMU_SCENARIO_FLAG WORLD_NAME SPAWN_POSE LAUNCH_VLM SESSION_NAME VLM_CTX_SIZE

SLAM_START_DELAY="${SLAM_START_DELAY:-12}"
CMD_SLAM="export LD_LIBRARY_PATH=$SLAM_BIN_DIR:\$LD_LIBRARY_PATH && \
    export STELLA_CONFIG_PATH=$STELLA_CONFIG_PATH && \
    export STELLA_VOCAB_PATH=$STELLA_VOCAB_PATH && \
    sleep $SLAM_START_DELAY && $SLAM_BINARY; \
    echo 'SLAM stopped'; read"
CMD_COMPARE="sleep $((SLAM_START_DELAY + 3)) && \
    python3 $COMPARATOR 2>&1 | tee $SLAM_CHECK_LOG; \
    echo 'comparator stopped'; read"

(
    for _ in $(seq 1 150); do
        if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then break; fi
        sleep 0.2
    done
    if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo "[WARN] tmux session '$SESSION_NAME' never appeared; SLAM panes not added."
        exit 0
    fi
    tmux split-window -v -t "$SESSION_NAME:0" "$CMD_SLAM"
    tmux split-window -v -t "$SESSION_NAME:0" "$CMD_COMPARE"
    tmux select-layout -t "$SESSION_NAME:0" tiled
) &

source ../../lib/sim_core.sh

pkill -9 -f "stella_vslam_monocular"
pkill -9 -f "compare_ground_truth.py"
