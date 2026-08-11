#!/bin/bash
# SPSC task-queue backpressure flood test (spec-3, ROADMAP 1.4).
# Injects ONE oversized plan (100 actions) against the queue cap (60) at FMU start --
# the worst-case VLM command-storm. The drone does NOT fly; this exercises only the
# queue producer, so the result shows up immediately in the FMU pane.
# Run:  cd scripts/test/flood && ./run.sh
# Then watch the FMU pane; in a 2nd terminal: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Backpressure flood test: 100 actions vs the queue cap."
FMU_CANNED_FLAG="--canned-flood"
WORLD_NAME="default_car"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
