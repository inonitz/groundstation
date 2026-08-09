#!/bin/bash
# interrupt-storm test (spec 2026-08-07-spec-1 §D, ROADMAP 6.3).
# --canned-storm: takeoff, then a synthetic obstacle burst trips the boundary many times inside
# kInterruptStormWindowMs (deterministic) -> escalated=1 + [ESCALATION] in the reassess prompt.
# The burst then clears. Unlike the old empty-world run, the world here is rubicon_targets: real
# terrain + two people + two cars in the drone's forward view. So AFTER the storm the VLM has a
# REAL scene to reason about and can actually plan an escape and complete it -- i.e. RECOVER.
# LAUNCH_VLM=1 is required (the escalated prompt + the recovery re-plan both need the VLM).
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Survive an interrupt storm, then reassess against the real scene and recover."
FMU_CANNED_FLAG="--canned-storm"
LAUNCH_VLM=1
WORLD_NAME="rubicon_targets"
SPAWN_POSE="0,7,3"
source ../lib/sim_core.sh
