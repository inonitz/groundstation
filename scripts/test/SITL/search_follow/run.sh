#!/bin/bash
# SEARCH-by-tag exercise. The drone spawns FACING AWAY (yaw ~180 deg) from the three
# actors, so none are in the initial camera view. The VLM must SEARCH to bring a person
# into view, then FOLLOW that person by track_id. This is the path that surfaces
# "SEARCH DETECTED target=person track_id=N" and proves the search -> tag -> follow chain
# (as opposed to the crowd/ scenario, where people are visible at spawn so it follows
# directly and never searches).
# Run:  cd scripts/test/SITL && ./logtest.sh search_follow hires
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, then find a person and follow them. No one is in view at first -- the people are behind you. Search to bring a person into view, then follow that person by their track_id and hold. Search first, then follow once found."
FMU_SCENARIO_FLAG=""
WORLD_NAME="three_people"
SPAWN_POSE="0,7,3,0,0,3.1416"
LAUNCH_VLM="1"
source ../../lib/sim_core.sh
