#!/bin/bash
# SEARCH in the REAL rubicon world (rubicon_targets: 2 people + 2 cars, forward). Takeoff FACING AWAY
# (yaw ~180) so the drone must advance-and-scan to bring a person into view -- a real search + vision
# find, not a contrived setup. VLM off (scripted). On a confident hit the node logs SEARCH DETECTED and
# auto-hands the track to APPROACH. filter.sh passes iff SEARCH activates then DETECTS the car.
# Run:  cd projects/llm_to_action/test/sitl-legacy/search && ./run.sh   then (2nd terminal): ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Search for the car, then approach."
FMU_SCENARIO_FLAG="--scenario-search"
WORLD_NAME="rubicon_targets"
SPAWN_POSE="0,7,3,0,0,3.1416"
LAUNCH_VLM="0"
source ../../lib/sim_core.sh
