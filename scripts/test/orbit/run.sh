#!/bin/bash
# ORBIT the car with REAL perception (ONNX seg+depth): hold radius, sweep the arc, then land.
# Run:  cd scripts/test/orbit && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Orbit the car a quarter turn, then land."
FMU_CANNED_FLAG="--canned-orbit"
WORLD_NAME="default_car"
SPAWN_POSE="0,6,3"
source ../lib/sim_core.sh
