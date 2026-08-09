#!/bin/bash
# boundary test (spec 2026-08-07-spec-1 §B, ROADMAP 6.1).
# --canned-boundary: takeoff, then the FMU injects a synthetic close obstacle for a ~1.5s burst
# once airborne (test-only, no real object needed). nearestDepthM reads ~0.4m, well inside
# trig = kBoundaryBaseM + kBoundaryVelScale*speed, so the emergency boundary stops the drone and
# raises INTERRUPT (reason=emergency_boundary). Empty world so no real detection competes.
# The drone hovers after the burst (no VLM); watch the trip, then Ctrl-C and run ./filter.sh.
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Synthetic close obstacle; the emergency boundary must stop + interrupt."
FMU_CANNED_FLAG="--canned-boundary"
WORLD_NAME="empty"
SPAWN_POSE="0,7,3"
source ../lib/sim_core.sh
