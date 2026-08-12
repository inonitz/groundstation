#!/bin/bash
# Rubicon world + a sample human. STUB — fill in the objective and wire the human.
# Run:  cd scripts/test/SITL/rubicon && ./run.sh
# Then watch the drone; in a 2nd terminal after it lands: ./filter.sh
cd "$(dirname "$0")" || exit 1

# TODO: the objective the VLM should carry out in the rubicon world.
FMU_OBJECTIVE=""

FMU_CANNED_FLAG=""

# The human lives INSIDE the world .sdf (this rig has no separate actor-spawn knob).
# rubicon.sdf / rubicon_colors.sdf carry no human today; moving_person.sdf / three_people.sdf
# are person worlds with no rubicon texture. TODO: author a combined world under
# dependencies/ (e.g. rubicon_human.sdf = rubicon geometry + one actor) and set it here.
WORLD_NAME="rubicon"     # TODO: -> rubicon_human once the combined world exists

SPAWN_POSE="0,7,3"
LAUNCH_VLM="1"

source ../../lib/sim_core.sh
