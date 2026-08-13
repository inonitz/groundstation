#!/bin/bash
# DEMO 2 -- orbit a building, approach the first window, land.
# The VLM SEES the building/window (they are NOT YOLO/COCO classes), so it emits an
# `orbit`/`approach` with a "bbox":[x,y,x,y] around what it sees; the FMU freezes a world
# anchor from that bbox + dense depth and flies the circle / approach off odometry. No YOLO
# box for the building is needed. (bbox path: fmu_node bboxToEnuAnchor + perception medianDepthCmInRect.)
#
# Run:  cd scripts/test/SITL/rubicon_orbit && ./run.sh
# Watch (workstation GUI is up) + log: captured_panes_log.txt in THIS folder.
# Detach: Ctrl-B then D.  Teardown: ../../lib/stop_session.sh
cd "$(dirname "$0")" || exit 1

# ---- VOICE MODE (default -- this IS the demo: ASR-driven autonomy) -----------
# Empty objective => drone idles in STANDBY until your first spoken transcript on
# /asr_server/transcribe launches the mission (fmu_node asrCallback). Speak ON THE GROUND:
#   "Execute an orbit on the building in front of us, find the first window you can see
#    and get close to it. Land shortly after."
FMU_OBJECTIVE=""
LAUNCH_ASR="1"

# ---- TYPED fallback (ONLY for isolating orbit bugs from ASR; not the demo) ----
# FMU_OBJECTIVE="Execute an orbit on the building in front of us, find the first window you can see and get close to it. Land shortly after."
# LAUNCH_ASR="0"

FMU_CANNED_FLAG=""            # "" = VLM-driven
WORLD_NAME="rubicon_tree"     # Rubicon map (has the building) + the three people (harmless here)
SPAWN_POSE="0,7,3"           # facing +x; adjust if the building isn't in front (you can SEE the GUI)
LAUNCH_VLM="1"               # Qwen3-VL llama-server (prewarmed)
export FMU_OBSERVABILITY=1   # annotated stream + richer logs so we can verify the anchor/orbit

source ../../lib/sim_core.sh
