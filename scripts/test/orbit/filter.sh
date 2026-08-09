#!/bin/bash
# orbit milestones — capture + grep the FMU debug tags for this test.
# Self-contained: captures ALL tmux panes to captured_panes_log.txt IN THIS
# FOLDER, then filters/checks THIS test from that same file. Run after landing.
# Optional arg: tmux session name (default llmsim).
set -uo pipefail
cd "$(dirname "$0")" || exit 1
OUT="captured_panes_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"

echo "----- orbit milestones -----"
grep -E 'ORBIT activated|ORBIT target|ORBIT complete|ORBIT timed out|LANDING->STANDBY' "$OUT" \
    || echo "  (no matching milestone lines captured — check the FMU pane)"
echo ""
echo "PASS = an 'ORBIT complete ... orbit_ok' line after 'turned' reaches ~6.28 rad (full circle)."
echo "No auto PASS/FAIL — confirm against what you observed."
exit 0
