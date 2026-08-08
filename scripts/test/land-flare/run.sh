#!/bin/bash
# LAND flare-taper regression (spec-4 Part B).
# Run:  cd scripts/test/land-flare && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off to 2m then land (flare taper test)."
FMU_CANNED_FLAG="--canned-land-flare"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../lib/sim_core.sh
