#!/bin/bash
# HOVER persistence: fwd 1.5m, then HOVER holds forever. The queued back-go + land after it must
# NEVER dequeue -- if they do, HOVER leaked (completed instead of holding). See ./filter.sh.
# Run:  cd scripts/test/SITL/hover && ./run.sh   then (2nd terminal, after ~30s): ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Fly forward, hold position, do not move again."
FMU_SCENARIO_FLAG="--scenario-hover"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
