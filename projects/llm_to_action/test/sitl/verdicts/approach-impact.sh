#!/bin/bash
# approach-impact PASS/FAIL: an impact must interrupt, not declare a clean approach_ok.
set -uo pipefail
cd "${SITL_RUN_DIR:-$(dirname "$0")}" || exit 1
OUT="captured_panes_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"

echo "----- approach-impact digest -----"
grep -E 'APPROACH activated|APPROACH reached|motion off-nominal|INTERRUPT \(reason=approach_impact\)|INTERRUPT \(reason=emergency_boundary\)|approach_ok|LANDING->STANDBY' "$OUT" || true

IMPACT=$(grep -Ec 'INTERRUPT \(reason=approach_impact\)|INTERRUPT \(reason=emergency_boundary\)' "$OUT")
OKAY=$(grep -Ec 'task complete status=approach_ok' "$OUT")
ACTIVATED=$(grep -Ec 'APPROACH activated' "$OUT")

echo ""
if [ "$ACTIVATED" -eq 0 ]; then
    echo "FAIL: APPROACH never activated — is --scenario-approach-impact implemented in fmu_node.cpp?"
    exit 1
fi
if [ "$IMPACT" -ge 1 ] && [ "$OKAY" -eq 0 ]; then
    echo "PASS — impact caught by an interrupt; no false approach_ok."
    exit 0
fi
echo "FAIL: expected an approach_impact/emergency_boundary interrupt and NO approach_ok"
echo "      (impact_interrupts=$IMPACT approach_ok=$OKAY)."
exit 1
