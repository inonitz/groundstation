#!/bin/bash
# Run a SITL scenario with a UNIQUE, timestamped log so runs never overwrite each
# other -- so we can always correlate "what you saw" to the exact file.
#
# Usage:  ./logtest.sh follow            # one moving person
#         ./logtest.sh crowd             # three people, follow the middle one
#         ./logtest.sh follow hires      # annotated dashboard stream at 1280x720
#         ./logtest.sh follow 960x540    # annotated stream at a custom size
#
# The FMU tees its own clean stdout to $LOG_FILE (set below). When the run ends,
# get the digest with:  ./digest.sh
HERE="$(cd "$(dirname "$0")" && pwd)"
SCN="${1:-follow}"
RES="${2:-}"
if [ ! -x "$HERE/$SCN/run.sh" ]; then
    echo "no scenario '$SCN' -- use: follow | crowd"; exit 1
fi
mkdir -p "$HERE/runs"
STAMP="$(date +%Y%m%dT%H%M%S)"
export LOG_FILE="$HERE/runs/${SCN}_${STAMP}.log"
export FMU_OBSERVABILITY=1        # live dashboard/annotated stream ON

# Optional higher-res annotated stream (the 320x240 default is too small to read the
# box labels). "hires" = 1280x720 (native); or pass WxH like 960x540. Clamped to source.
case "$RES" in
    hires)          export FMU_A2_IMG_W=1280 FMU_A2_IMG_H=720 ;;
    "")             : ;;
    *x*)            export FMU_A2_IMG_W="${RES%x*}" FMU_A2_IMG_H="${RES#*x}" ;;
    *)              echo "bad res '$RES' -- use 'hires' or WxH e.g. 960x540"; exit 1 ;;
esac

echo "=================================================================="
echo " scenario : $SCN"
echo " log file : $LOG_FILE"
[ -n "$FMU_A2_IMG_W" ] && echo " annotated: ${FMU_A2_IMG_W}x${FMU_A2_IMG_H} (hi-res)"
echo " dashboard: python3 scripts/dashboard/serve.py 8088  (http://localhost:8088)"
echo " when done: Ctrl-B then D to detach (clean), or Ctrl-C to stop"
echo " then run : ./digest.sh"
echo "=================================================================="
cd "$HERE/$SCN" && exec ./run.sh
