#!/bin/bash
# Multi-person run with the live observability view ON, so you can WATCH the tracker:
# the annotated stream draws each of the three people as "#<track_id> person NN%".
# The three ids must stay pinned to their own person as the distractors sweep -- the
# visual proof the stable-id tracker holds multiple targets without swapping.
#
# Run:  cd projects/llm_to_action/test/sitl-legacy/crowd && ./watch.sh
# Then in a SECOND terminal (ROS workspace sourced):
#     python3 scripts/dashboard/serve.py 8088   # open http://localhost:8088
#   or Foxglove import dependencies/foxglove_layout.json  (topic /fmu/perception/annotated)
cd "$(dirname "$0")" || exit 1
export FMU_OBSERVABILITY=1
exec ./run.sh
