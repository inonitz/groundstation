#!/bin/bash
# Manual operator override test (spec-3, ROADMAP 6.2 / ARCH 11).
# Bool /fmu/in/override toggles takeover; while engaged, keys on /keyboard/in/raw fly the
# drone (WASD=plane, arrows=alt/yaw, Space=hover). Handback resumes autonomy + re-plans.
# sim_core.sh already launches the keyboard node pane. LAUNCH_VLM=1 so handback re-plans.
# Run:  cd scripts/test/override && ./run.sh    ; then do the MANUAL STEPS in README.md
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, find the car, approach it, then land."
FMU_CANNED_FLAG=""              # VLM-driven so a handback has something to re-plan
LAUNCH_VLM=1
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../lib/sim_core.sh
