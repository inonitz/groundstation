#!/bin/bash
# Multi-person SITL: three "person" actors (three_people world), one red-tinted
# TARGET holding the centre lane, two distractors sweeping the sides. Exercises the
# stable-id tracker (three ids held at once, no swap) and target selection: the VLM
# should pin the centre person and FOLLOW should hold on that track_id while the
# other two move. Real perception (ONNX seg+depth) + the live VLM.
# Run:  cd projects/llm_to_action/test/sitl-legacy/crowd && ./run.sh
# Then watch; in a 2nd terminal: ../follow/filter.sh  (or crowd/watch.sh for the view)
cd "$(dirname "$0")" || exit 1
FMU_OBJECTIVE="Take off, then follow the person in the middle of your view and hold your position. Do not approach, orbit, go, or move anywhere else -- only follow the middle person."
FMU_SCENARIO_FLAG=""
WORLD_NAME="three_people"
SPAWN_POSE="0,7,3"
LAUNCH_VLM="1"
source ../../lib/sim_core.sh
