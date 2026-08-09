#!/bin/bash
# boundary PASS/FAIL: closing on an obstacle must raise emergency_boundary + hover.
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
    { echo "===== pane $pane ====="; tmux capture-pane -p -J -S - -t "$pane"; echo; } >> "$OUT"
done < <(tmux list-panes -a -t "$SESSION" -F '#{session_name}:#{window_index}.#{pane_index}')
echo "[capture] all panes -> $OUT"

echo "----- boundary digest -----"
grep -E 'BOUNDARY nearest=|INTERRUPT \(reason=emergency_boundary\)|LANDING->STANDBY' "$OUT" || true

TRIP=$(grep -Ec 'INTERRUPT \(reason=emergency_boundary\)' "$OUT")
SAW=$(grep -Ec 'BOUNDARY nearest=' "$OUT")

echo ""
if [ "$TRIP" -ge 1 ]; then
    echo "PASS — emergency boundary tripped and interrupted ($SAW boundary log line(s))."
    exit 0
fi
echo "FAIL: no emergency_boundary interrupt seen — is --canned-boundary implemented in fmu_node.cpp?"
echo "      (boundary_log_lines=$SAW)"
exit 1
