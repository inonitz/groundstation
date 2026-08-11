#!/bin/bash
# Cross pattern: fwd/left/back/right 1m, returning to start after each leg (FLU sanity).
# Run:  cd scripts/test/cross && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Fly forward/left/back/right 1m, returning to start after each, then land."
FMU_CANNED_FLAG="--canned-cross"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
