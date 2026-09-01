#!/bin/bash
# DEMO -- voice-driven, VLM-REASONED approach on a real YOLO target (the car).
#
# World: rubicon_targets (Rubicon terrain + a blue hatchback + 2 people). The car is a
# canonical COCO "car", detects at ~80%+ up close. The VLM genuinely reads the SPOKEN objective, reasons
# (its `thought` shows on the dashboard), and emits takeoff -> approach(car) -> land.
# Real perception, real planning, real flight -- nothing canned.
#
# Run:  cd projects/llm_to_action/test/sitl-legacy/rubicon && ./run.sh          (QGroundControl MUST be up first)
#   Headless (laptop / stage):  HEADLESS=1 ./run.sh       -- no Gazebo GUI; show the DASHBOARD
#     instead (live camera feed + YOLO boxes + the model's thought). Lighter on the GPU.
# Speak ON THE GROUND, into the ASR pane: "approach the car and land near it"
# Detach when done: Ctrl-B then D  (never Ctrl-C).  Teardown: ../../lib/stop_session.sh
cd "$(dirname "$0")" || exit 1

# ---- VOICE MODE (default): real reasoning, spoken trigger --------------------
# Empty objective => idle in STANDBY until the first spoken transcript launches it.
FMU_OBJECTIVE="Take off, approach the car ahead of you, and land near it. Do not orbit, search, rotate, or go anywhere else."
LAUNCH_ASR="1"

# ---- TYPED FALLBACK (if the mic flakes on a take): still VLM-driven ----------
# Comment the two lines above, uncomment the two below -- runs at boot, no mic, but the
# VLM STILL reasons; the constraint just keeps a small model on rails.
# FMU_OBJECTIVE="Take off, approach the car ahead of you, and land near it. Do not orbit, search, rotate, or go anywhere else."
# LAUNCH_ASR="0"

FMU_SCENARIO_FLAG=""          # "" = VLM-driven (REAL reasoning). Do NOT set --scenario-* for the demo.
WORLD_NAME="rubicon_targets"  # Rubicon terrain + a blue hatchback (YOLO "car") + 2 people for scene.
SPAWN_POSE="0,3,3"          # facing +X; blue hatchback at (6,2) is ~6m dead ahead (~9deg right): clean car lock.
LAUNCH_VLM="1"              # llama-server (prewarmed on boot)
FMU_OBSERVABILITY="1"       # annotated frames + depth + HUD + vlm_text(thought) -> dashboard

source ../../lib/sim_core.sh
