#!/bin/bash
# Speed sweep: forward 1m + return at LOW (15cm/s) then HIGH (80cm/s) speed.
# Run:  cd scripts/test/speed && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Fly forward 1m + return at low then high speed, then land."
FMU_CANNED_FLAG="--canned-speed"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
