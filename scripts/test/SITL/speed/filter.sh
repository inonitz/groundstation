#!/bin/bash
# speed milestones — capture + grep the FMU debug tags for this test.
# Self-contained: captures ALL tmux panes to captured_panes_log.txt IN THIS
# FOLDER, then filters/checks THIS test from that same file. Run after landing.
# Optional arg: tmux session name (default llmsim).
# Portable awk only (system awk may be mawk): value extraction is token-split.
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

echo "----- speed milestones -----"
grep -E 'GO activated|GO complete|LANDING->STANDBY' "$OUT" || echo "  (no matching milestone lines captured — check the FMU pane)"
echo ""
echo "No PASS/FAIL for this test — confirm against what you observed."
exit 0
