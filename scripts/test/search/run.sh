#!/bin/bash
# SEARCH for the car with REAL perception: fly the zig-zag/scan pattern until it comes into view,
# notify with diagnostics, then land.
# Run:  cd scripts/test/search && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Search a full sweep pattern (target absent) so the whole circle is traced, then land."
FMU_CANNED_FLAG="--canned-search"
WORLD_NAME="default_car"
# Centered on the platform so you can watch the full circle get traced. The canned plan targets an
# object NOT in the world ("person"), so nothing is found early and the whole pattern runs to timeout.
SPAWN_POSE="0,0,3"
source ../lib/sim_core.sh
