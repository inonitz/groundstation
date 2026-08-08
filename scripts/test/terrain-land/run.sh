#!/bin/bash
# Terrain / AGL landing check (spec-4 Part B follow-up).
# Run:  cd scripts/test/terrain-land && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, fly ~2m forward over terrain, then land (AGL check)."
FMU_CANNED_FLAG="--canned-terrain-land"
WORLD_NAME="rubicon"
SPAWN_POSE="0,7,3"
source ../lib/sim_core.sh
