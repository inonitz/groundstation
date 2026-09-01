#!/bin/bash
# ROTATE granularity: takeoff, rotate 90 cw then 200 ccw (a >180 sweep), then land.
# Recovered from scripts/archive/SITL/rotate-land. filter.sh reconstructs swept angle + direction
# from the log and auto-verdicts them (+-15 deg).
# Run:  cd scripts/test/SITL/rotate && ./run.sh   then (2nd terminal, after it lands): ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, rotate 90 cw then 200 ccw, then land."
FMU_SCENARIO_FLAG="--scenario-rotate"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
