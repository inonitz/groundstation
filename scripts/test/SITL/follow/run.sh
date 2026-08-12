#!/bin/bash
# FOLLOW a moving person with REAL perception (ONNX seg+depth) + the live VLM.
# The person slides left-right (moving_person world); the drone holds standoff and
# keeps them centered, backing off when they come too close. FOLLOW never self-
# completes -- it runs until re-assess or stop.
# Run:  cd scripts/test/SITL/follow && ./run.sh
# Then watch the drone; in a 2nd terminal: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, then immediately follow the person and hold your position. Do not approach, orbit, go, or move anywhere else -- only follow."
FMU_CANNED_FLAG=""
WORLD_NAME="moving_person"
SPAWN_POSE="0,7,3"
LAUNCH_VLM="1"
source ../../lib/sim_core.sh
