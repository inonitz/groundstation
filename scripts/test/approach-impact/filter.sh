#!/bin/bash
# approach-impact PASS/FAIL: an impact must interrupt, not declare a clean approach_ok.
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

echo "----- approach-impact digest -----"
grep -E 'APPROACH activated|APPROACH reached|motion off-nominal|INTERRUPT \(reason=approach_impact\)|INTERRUPT \(reason=emergency_boundary\)|approach_ok|LANDING->STANDBY' "$OUT" || true

IMPACT=$(grep -Ec 'INTERRUPT \(reason=approach_impact\)|INTERRUPT \(reason=emergency_boundary\)' "$OUT")
OKAY=$(grep -Ec 'task complete status=approach_ok' "$OUT")
ACTIVATED=$(grep -Ec 'APPROACH activated' "$OUT")

echo ""
if [ "$ACTIVATED" -eq 0 ]; then
    echo "FAIL: APPROACH never activated — is --canned-approach-impact implemented in fmu_node.cpp?"
    exit 1
fi
if [ "$IMPACT" -ge 1 ] && [ "$OKAY" -eq 0 ]; then
    echo "PASS — impact caught by an interrupt; no false approach_ok."
    exit 0
fi
echo "FAIL: expected an approach_impact/emergency_boundary interrupt and NO approach_ok"
echo "      (impact_interrupts=$IMPACT approach_ok=$OKAY)."
exit 1
