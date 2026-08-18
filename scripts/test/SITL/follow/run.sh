#!/bin/bash
# FOLLOW a moving person, REAL perception (ONNX seg+depth + YOLO tracker), VLM OFF (scripted).
# Person slides left-right (moving_person world). FOLLOW is a yaw-only servo: it centres the person
# and holds standoff, and never self-completes -> the drone holds a lock. filter.sh checks the lock
# resolves, sustains, and the track id stays stable.
# Run:  cd scripts/test/SITL/follow && ./run.sh   then (2nd terminal): ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Follow the person and hold."
FMU_SCENARIO_FLAG="--scenario-follow"
WORLD_NAME="moving_person"
SPAWN_POSE="0,7,3"
LAUNCH_VLM="0"
source ../../lib/sim_core.sh
