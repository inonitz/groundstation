#!/bin/bash
# C1 with a UNIQUE, timestamped log so runs never overwrite -- so we can correlate
# "what you flew" to the exact file. Wraps run.sh (which brings up RX + stella +
# teleop + the measurement) and points the measurement log at runs/c1_<stamp>.log.
#
# Usage:  ./c1test.sh                 # default label "c1"
#         ./c1test.sh mats            # label the surface, e.g. runs/c1-mats_<stamp>.log
#
# Fly a path, then a return-to-start loop. Detach with Ctrl-B then D, or Ctrl-C to
# stop. Then run ./digest.sh to get the numbers to send back.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
LABEL="${1:-c1}"
mkdir -p "$HERE/runs"
STAMP="$(date +%Y%m%dT%H%M%S)"
export MEASURE_LOG="$HERE/runs/${LABEL}_${STAMP}.log"

echo "=================================================================="
echo " C1 -- stella on the real Tello (go/no-go)"
echo " label    : $LABEL"
echo " log file : $MEASURE_LOG"
echo " surface  : screen it first with ./feature_scout.py --floor <photo>"
echo " fly      : a path out, then a return-to-start loop"
echo " physical drift (metres): film it + run ../measure_drift.py on the clip"
echo " when done: Ctrl-B then D to detach (clean), or Ctrl-C to stop"
echo " then run : ./digest.sh"
echo "=================================================================="
exec "$HERE/run.sh"
