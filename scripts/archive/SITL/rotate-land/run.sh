#!/bin/bash
# ROTATE granularity regression (spec-4 Part B).
# Run:  cd scripts/test/rotate-land && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, rotate 90 cw then 200 ccw, then land."
FMU_CANNED_FLAG="--canned-rotate"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
