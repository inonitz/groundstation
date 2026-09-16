#!/bin/bash
# Closed-loop APPROACH toward a canned (synthetic, no-YOLO) detection, then land.
# Run:  cd scripts/test/approach && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Approach the canned target, then land."
FMU_SCENARIO_FLAG="--scenario-approach"
WORLD_NAME="empty"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
