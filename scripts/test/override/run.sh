#!/bin/bash
# Manual operator override test (spec-3, ROADMAP 6.2 / ARCH 11).
# Bool /fmu/in/override toggles takeover; while engaged, keys on /keyboard/in/raw fly the
# drone (WASD=plane, arrows=alt/yaw, Space=hover). Handback resumes autonomy + re-plans.
# sim_core.sh already launches the keyboard node pane. LAUNCH_VLM=1 so handback re-plans.
#
# Manual run:   cd scripts/test/override && ./run.sh   ; then do the MANUAL STEPS in README.md
# Headless run: HEADLESS=1 ./run.sh -- scripts the /fmu/in/override toggle itself (engage,
#               hold, release) since filter.sh's PASS bar is "engaged" being observed; no
#               human keypresses are simulated, so the release/replan lines stay WARN-only,
#               same as a human run that never presses a movement key.
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, find the car, approach it, then land."
FMU_CANNED_FLAG=""              # VLM-driven so a handback has something to re-plan
LAUNCH_VLM=1
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"

if [ "${HEADLESS:-0}" = "1" ]; then
    (
        sleep 25   # let TAKEOFF clear FLIGHT before toggling override
        ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data: true}" >/dev/null 2>&1
        sleep 5
        ros2 topic pub --once /fmu/in/override std_msgs/msg/Bool "{data: false}" >/dev/null 2>&1
    ) &
    disown
fi

source ../lib/sim_core.sh
