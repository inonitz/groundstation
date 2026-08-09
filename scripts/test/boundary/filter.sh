#!/bin/bash
# boundary PASS/FAIL: closing on an obstacle must raise emergency_boundary + hover.
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
