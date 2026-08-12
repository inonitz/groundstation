#!/bin/bash
# follow milestones — capture + grep the FMU debug tags for this test.
# Self-contained: captures ALL tmux panes to captured_panes_log.txt IN THIS
# FOLDER, then filters/checks THIS test from that same file. Run during or after
# a run (FOLLOW does not self-complete, so capture while it is holding).
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

echo "----- follow milestones -----"
grep -E 'FOLLOW activated|FOLLOW holding|FOLLOW target|FOLLOW lost|FOLLOW re-acquired' "$OUT" \
    || echo "  (no matching milestone lines captured — check the FMU pane)"
echo ""
echo "PASS = after 'FOLLOW activated', a stream of 'FOLLOW target ... errX ~0 errY ~0'"
echo "       lines with range holding near the standoff as the person moves. No completion line."
echo "No auto PASS/FAIL — confirm against what you observed."
exit 0
