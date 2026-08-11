#!/bin/bash
# approach-impact test (spec 2026-08-07-spec-1 §C, ROADMAP 6.4).
# --canned-approach-impact: the canned synthetic APPROACH rig drives to the standoff, but the
# motion-gate is forced off-nominal, so "reached" is treated as an impact -- the FMU raises
# INTERRUPT (reason=approach_impact) instead of declaring approach_ok. Deterministic, no real
# collision. Empty world so the synthetic rig is the only detection source. The queued land then
# runs, so the flight ends with LANDING->STANDBY.
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Canned approach reaches the standoff; a forced impact must interrupt, not approach_ok."
FMU_CANNED_FLAG="--canned-approach-impact"
WORLD_NAME="empty"
SPAWN_POSE="0,7,3"
source ../../lib/sim_core.sh
