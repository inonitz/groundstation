#!/bin/bash
# interrupt-storm PASS/FAIL: N trips in the window -> escalated=1 + [ESCALATION].
# Plus a soft RECOVERY signal: did the VLM complete a real task AFTER the storm (escape)?
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

echo "----- interrupt-storm digest -----"
grep -E 'INTERRUPT \(reason=|escalated=1|ESCALATION block added|\[ESCALATION\]|task complete status=' "$OUT" || true

ESC=$(grep -Ec 'escalated=1' "$OUT")
BLOCK=$(grep -Ec 'ESCALATION block added to reassess prompt|\[ESCALATION\]' "$OUT")
TRIPS=$(grep -Ec 'INTERRUPT \(reason=' "$OUT")
# Soft recovery: a non-takeoff task completed AFTER the storm escalated == the VLM escaped.
RECOVERED=$(awk '
    /escalated=1|ESCALATION block added/ { stormed=1 }
    /task complete status=/ {
        st="";
        for (i=1;i<=NF;i++) if ($i ~ /status=/) st=$i;
        if (stormed && st !~ /takeoff_ok/) rec=1;
    }
    END { print rec?1:0 }' "$OUT")

echo ""
if [ "$TRIPS" -lt 3 ]; then
    echo "FAIL: only $TRIPS interrupt(s) seen (<3) — is --scenario-storm implemented + built?"
    exit 1
fi
if [ "$ESC" -ge 1 ] && [ "$BLOCK" -ge 1 ]; then
    echo "PASS — storm escalated (escalated=1) and the reassess prompt carried [ESCALATION]."
    if [ "$RECOVERED" -ge 1 ]; then
        echo "RECOVERY: yes — the VLM completed a real task after the storm (escaped the loop)."
    else
        echo "RECOVERY: not seen in the log — watch the drone; the 2B VLM may not always escape."
    fi
    exit 0
fi
echo "FAIL: storm not escalated as expected (escalated=1 count=$ESC, [ESCALATION] count=$BLOCK, trips=$TRIPS)."
exit 1
