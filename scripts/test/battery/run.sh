#!/bin/bash
# Battery REAL-DRAIN test (spec-3, ROADMAP 6.2) -- the realistic one.
# Flies a patrol that stays 6-10m OUT (never sitting at origin) while the PX4 pack drains for
# real. When OUR <=20% failsafe fires -- at a drain-dependent, "random" point along the patrol
# -- the drone returns to origin and lands. PX4's OWN low-battery failsafe is DISABLED
# (COM_LOW_BAT_ACT=0) so it cannot hijack the descent: previously it entered Hold at "Critical
# battery", froze our descent at ~0.34m and dropped the drone -- NOT our system landing it.
cd "$(dirname "$0")" || exit 1
export PX4_PARAM_COM_LOW_BAT_ACT=0        # PX4 warns only -> OUR FMU owns the battery reaction
export PX4_PARAM_SIM_BAT_MIN_PCT=0.0
# Randomize the drain each run so the 20% crossing -- and thus the RTH break-off point -- lands
# at a DIFFERENT, unpredictable spot along the patrol every time (models real battery variance).
# Pin it for a reproducible run:  PX4_PARAM_SIM_BAT_DRAIN=170 ./run.sh
export PX4_PARAM_SIM_BAT_DRAIN=${PX4_PARAM_SIM_BAT_DRAIN:-$(( 140 + RANDOM % 61 ))}   # random 140..200 s-to-empty
echo "[battery test] this run: SIM_BAT_DRAIN=${PX4_PARAM_SIM_BAT_DRAIN}s (higher=slower; export it to pin)"
FMU_OBJECTIVE="Real-drain battery: patrol out, expect RTH when OUR 20% fires."
FMU_CANNED_FLAG="--canned-patrol"
WORLD_NAME="empty"
SPAWN_POSE="0,7,3"
source ../lib/sim_core.sh
