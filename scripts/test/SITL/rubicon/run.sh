#!/bin/bash
# DEMO -- voice-driven, VLM-REASONED approach on a real YOLO target (the car).
#
# World: default_car (Rubicon jeep -- a canonical COCO "car", detects at ~80%+, far more
# reliable than a distant person). The VLM genuinely reads the SPOKEN objective, reasons
# (its `thought` shows on the dashboard), and emits takeoff -> approach(car) -> land.
# Real perception, real planning, real flight -- nothing canned.
#
# Run:  cd scripts/test/SITL/rubicon && ./run.sh          (QGroundControl MUST be up first)
#   Headless (laptop / stage):  HEADLESS=1 ./run.sh       -- no Gazebo GUI; show the DASHBOARD
#     instead (live camera feed + YOLO boxes + the model's thought). Lighter on the GPU.
# Speak ON THE GROUND, into the ASR pane: "approach the car and land near it"
# Detach when done: Ctrl-B then D  (never Ctrl-C).  Teardown: ../../lib/stop_session.sh
cd "$(dirname "$0")" || exit 1

# ---- VOICE MODE (default): real reasoning, spoken trigger --------------------
# Empty objective => idle in STANDBY until the first spoken transcript launches it.
FMU_OBJECTIVE=""
LAUNCH_ASR="1"

# ---- TYPED FALLBACK (if the mic flakes on a take): still VLM-driven ----------
# Comment the two lines above, uncomment the two below -- runs at boot, no mic, but the
# VLM STILL reasons; the constraint just keeps a small model on rails.
# FMU_OBJECTIVE="Take off, approach the car ahead of you, and land near it. Do not orbit, search, rotate, or go anywhere else."
# LAUNCH_ASR="0"

FMU_CANNED_FLAG=""          # "" = VLM-driven (REAL reasoning). Do NOT set --canned-* for the demo.
WORLD_NAME="default_car"    # Rubicon jeep -- reliable YOLO "car" detection from the spawn.
SPAWN_POSE="0,7,3"          # proven approach-real geometry: car dead ahead (+X), detects on takeoff.
LAUNCH_VLM="1"              # llama-server (prewarmed on boot)
FMU_OBSERVABILITY="1"       # annotated frames + depth + HUD + vlm_text(thought) -> dashboard

source ../../lib/sim_core.sh
