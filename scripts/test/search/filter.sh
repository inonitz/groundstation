#!/bin/bash
# search milestones — capture + grep the FMU debug tags for this test.
# Self-contained: captures ALL tmux panes to captured_panes_log.txt IN THIS
# FOLDER, then filters/checks THIS test from that same file. Run after landing.
# Optional arg: tmux session name (default llmsim).
set -uo pipefail
cd "$(dirname "$0")" || exit 1
SESSION="${1:-llmsim}"
OUT="captured_panes_log.txt"
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "no tmux session '$SESSION' — start it first with ./run.sh" >&2
    exit 2
fi
: > "$OUT"
while read -r pane; do
    # -J rejoins tmux-wrapped rows so long log lines are not truncated at pane width.
    { echo "===== pane $pane ====="; tmux capture-pane -p -J -S - -t "$pane"; echo; } >> "$OUT"
done < <(tmux list-panes -a -t "$SESSION" -F '#{session_name}:#{window_index}.#{pane_index}')
echo "[capture] all panes -> $OUT"

echo "----- search milestones -----"
grep -E 'SEARCH activated|SEARCH lane|SEARCH cross|SEARCH DETECTED|SEARCH exhausted|LANDING->STANDBY' "$OUT" \
    || echo "  (no matching milestone lines captured — check the FMU pane)"
echo ""
echo "PASS = a 'SEARCH DETECTED target=car conf=.. depth_cm=.. bbox=(..)' line, then search_ok."
echo "The DETECTED line IS the operator notification — read conf to judge a weak/false hit."
echo "No auto PASS/FAIL — confirm against what you observed."
exit 0
