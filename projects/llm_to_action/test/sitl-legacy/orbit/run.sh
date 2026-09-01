#!/bin/bash
# ORBIT accuracy: takeoff, fly one full 4m-radius circle around a car parked at the orbit centre,
# then land. World orbit_car.sdf places the car at (4,7) -- exactly 4m ahead of the (0,7) spawn, so
# the fixed circle centres on it. filter.sh measures how tightly the 4m radius is held + full sweep.
# Run:  cd projects/llm_to_action/test/sitl-legacy/orbit && ./run.sh   then (2nd terminal, after it lands): ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Orbit the car one full turn, then land."
FMU_SCENARIO_FLAG="--scenario-orbit"
WORLD_NAME="orbit_car"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
