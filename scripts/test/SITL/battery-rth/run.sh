#!/bin/bash
# Battery RTH behaviour test (spec-3, ROADMAP 6.2).
# Flies ~8m straight out, then the FMU forces an 18% battery reading ~15s after reaching FLIGHT
# (a test-only fault injection -- no PX4-drain roulette). The <=20% law returns the drone all
# the way to origin, where it lands + disarms. This is the REAL RTH the cross plan couldn't show.
cd "$(dirname "$0")" || exit 1
export PX4_PARAM_SIM_BAT_DRAIN=3600      # keep the real pack ~full; only the forced value fires
FMU_OBJECTIVE="Battery RTH: fly out, force 18% far, expect return-to-origin + land."
FMU_SCENARIO_FLAG="--scenario-battery-rth"
WORLD_NAME="empty"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
