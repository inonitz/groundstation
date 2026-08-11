#!/bin/bash
# Battery land-in-place behaviour test (spec-3, ROADMAP 6.2).
# Flies ~8m straight out, then the FMU forces a sudden 8% battery reading ~15s after reaching
# FLIGHT (models an "all of a sudden extremely low" fault). The <=10% law lands the drone WHERE
# IT IS -- no return to origin. Test-only override; PX4 drain pinned high so only 8% fires.
cd "$(dirname "$0")" || exit 1
export PX4_PARAM_SIM_BAT_DRAIN=3600
FMU_OBJECTIVE="Battery land-now: fly out, force 8% far, expect land-in-place (no return)."
FMU_CANNED_FLAG="--canned-battery-landnow"
WORLD_NAME="empty"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
