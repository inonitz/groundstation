#!/bin/bash
# Full VLM-driven run (Qwen3-VL): the planner issues the verbs, no canned plan.
# Run:  cd scripts/test/vlm && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, find the car, approach it, then land."
FMU_CANNED_FLAG=""
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
LAUNCH_VLM="1"
source ../lib/sim_core.sh
