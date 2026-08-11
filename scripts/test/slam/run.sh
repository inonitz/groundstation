#!/bin/bash
# stella_vslam SITL bring-up (spec B1): fly a canned cross in a textured world with
# the SLAM node attached, and score its pose against PX4 EKF2 ground truth.
# Run:  cd scripts/test/slam && ./run.sh
# Then watch the [SLAM_CHECK] pane; the same lines land in slam_check.log.
#
# Two extra panes are added on top of the standard sim_core.sh layout:
#   stella_vslam_monocular   the SLAM node (subscribes camera/stream, publishes slam/pose)
#   compare_ground_truth.py  the quantitative drift/tracking check
#
# Note: sim_core.sh's cleanup does not know about these two, so this script kills
# them itself after the tmux session detaches. A hard Ctrl-C may leave them; check
# with `pgrep -f stella_vslam_monocular` if a rerun misbehaves.
cd "$(dirname "$0")" || exit 1

REPO_ROOT="$(cd ../../.. && pwd)"

# The SLAM node is built by its own isolated tree (GROUNDSTATION_BUILD_SLAM=ON),
# not by the shared build sim_core.sh uses for the FMU and the camera RX.
SLAM_BIN_DIR="${SLAM_BIN_DIR:-$REPO_ROOT/build/release/slam/bin}"
SLAM_BINARY="$SLAM_BIN_DIR/stella_vslam_monocular"
COMPARATOR="$REPO_ROOT/scripts/test/slam/compare_ground_truth.py"
SLAM_CHECK_LOG="$REPO_ROOT/scripts/test/slam/slam_check.log"

# Point the node at THIS checkout's assets. Without these the node falls back to
# its compiled-in /root/groundstation/dependencies paths, which is the wrong tree
# whenever you run from a worktree.
export STELLA_CONFIG_PATH="${STELLA_CONFIG_PATH:-$REPO_ROOT/config/stella_config_px4.yaml}"
export STELLA_VOCAB_PATH="${STELLA_VOCAB_PATH:-$REPO_ROOT/dependencies/orb_vocab.fbow}"

if [ ! -x "$SLAM_BINARY" ]; then
    echo "[ERROR] $SLAM_BINARY missing. Build it first:"
    echo "  cmake -S $REPO_ROOT -B $REPO_ROOT/build/release/slam -G Ninja \\"
    echo "      -DGROUNDSTATION_BUILD_SLAM=ON -DGROUNDSTATION_BUILD_EXECUTABLE=OFF \\"
    echo "      -DGROUNDSTATION_BUILD_TESTS=OFF -DGROUNDSTATION_BUILD_BENCHMARKS=OFF \\"
    echo "      -DGROUNDSTATION_BUILD_BACKEND_PX4=ON -DBUILD_SHARED_LIBS=1 \\"
    echo "      -DCMAKE_BUILD_TYPE=Release -DGIT_SUBMODULE=ON"
    echo "  cmake --build $REPO_ROOT/build/release/slam --target stella_vslam_monocular -j\$(nproc)"
    exit 1
fi
for asset in "$STELLA_CONFIG_PATH" "$STELLA_VOCAB_PATH"; do
    if [ ! -f "$asset" ]; then
        echo "[ERROR] missing SLAM asset: $asset"
        exit 1
    fi
done

# --- sim_core.sh knobs ---
# A cross gives translation on both horizontal axes, so the drift number reflects
# real motion instead of a single straight line that a scale error can hide in.
: "${FMU_OBJECTIVE:=Fly a canned cross while SLAM tracks.}"
: "${FMU_CANNED_FLAG:=--canned-cross}"
# rubicon_targets is textured; default_car and empty are too feature-poor for
# monocular tracking to initialise reliably.
: "${WORLD_NAME:=rubicon_targets}"
: "${SPAWN_POSE:=0,7,3}"
SESSION_NAME="${SESSION_NAME:-llmsim}"
export FMU_OBJECTIVE FMU_CANNED_FLAG WORLD_NAME SPAWN_POSE SESSION_NAME

# The SLAM node needs stella/g2o/yaml-cpp, which install next to the binary.
SLAM_START_DELAY="${SLAM_START_DELAY:-12}"
CMD_SLAM="export LD_LIBRARY_PATH=$SLAM_BIN_DIR:\$LD_LIBRARY_PATH && \
    export STELLA_CONFIG_PATH=$STELLA_CONFIG_PATH && \
    export STELLA_VOCAB_PATH=$STELLA_VOCAB_PATH && \
    sleep $SLAM_START_DELAY && $SLAM_BINARY; \
    echo 'SLAM stopped'; read"
CMD_COMPARE="sleep $((SLAM_START_DELAY + 3)) && \
    python3 $COMPARATOR 2>&1 | tee $SLAM_CHECK_LOG; \
    echo 'comparator stopped'; read"

# sim_core.sh blocks on `tmux attach` at the end, so the extra panes have to be
# grafted on from a background waiter once the session exists.
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

source ../lib/sim_core.sh

# sim_core.sh's own cleanup does not cover these two.
pkill -9 -f "stella_vslam_monocular"
pkill -9 -f "compare_ground_truth.py"
