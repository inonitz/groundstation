#!/bin/bash
# Forward hop (FLU-frame sanity): takeoff, GO ~1m forward, land.
# Run:  cd scripts/test/forward && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Fly forward 1m then land."
FMU_CANNED_FLAG="--canned"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../lib/sim_core.sh
