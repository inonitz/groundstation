#!/bin/bash
# FOLLOW, but with the live observability view switched ON so you can WATCH it:
# the annotated camera stream draws each box as "#<track_id> person NN%", and the
# track_id stays pinned to the same person as they move -- the visual proof the
# stable-id tracker is running in the pipeline.
#
# Run:  cd scripts/test/SITL/follow && ./watch.sh
# Then in a SECOND terminal (ROS workspace sourced):
#     python3 scripts/dashboard/serve.py 8088   # open http://localhost:8088
#   or  rviz2 -d dependencies/a2_observability.rviz
#   or  Foxglove import dependencies/foxglove_layout.json  (topic /fmu/perception/annotated)
#
# FMU_OBSERVABILITY=1 is propagated to the FMU by sim_core.sh (CMD_FMU); with it OFF
# (plain ./run.sh) the annotated/depth/hud/vlm_text topics do not publish.
cd "$(dirname "$0")" || exit 1
export FMU_OBSERVABILITY=1
exec ./run.sh
