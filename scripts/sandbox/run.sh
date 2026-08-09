#!/bin/bash
# scripts/sandbox/run.sh -- live full-system sandbox: Gazebo + PX4 + FMU + VLM + perception,
# free-form objective, human-driven (attaches tmux like any manual test run), and recorded
# to a ros2 bag for later replay. Not a canned scenario -- always VLM-driven.
# Usage: ./run.sh ["<objective text>"] [world_name]
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="${1:-Explore the area and describe what you see.}"
FMU_CANNED_FLAG=""
WORLD_NAME="${2:-default_car}"
SPAWN_POSE="0,7,3"
LAUNCH_VLM=1
RECORD_BAG=1
mkdir -p "$(pwd)/bags"
BAG_DIR="$(pwd)/bags/$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$(pwd)/bags/$(basename "$BAG_DIR")_fmu_log.txt"
source ../test/lib/sim_core.sh
