#!/bin/bash
# Same APPROACH servo, but REAL perception (ONNX seg+depth) vs the car in the world.
# Run:  cd scripts/test/approach-real && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Approach the car, then land."
FMU_SCENARIO_FLAG="--scenario-approach-real"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
