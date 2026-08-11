#!/bin/bash
# Airborne backpressure / command-storm test (spec-3, ROADMAP 1.4).
# Flies the canned cross plan; ~5s after reaching FLIGHT the FMU injects a 100-action flood
# from a producer-role async (the same std::async path the VLM uses). Proves an in-flight
# command storm is absorbed safely: the queue stays bounded, excess is dropped, and the
# maneuver in progress is NOT hijacked (FIFO -> the storm queues behind the live plan).
# Run:  cd scripts/test/flood-airborne && ./run.sh   ; 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Airborne backpressure: fly the cross, get flooded mid-air."
FMU_CANNED_FLAG="--canned-cross-flood"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
