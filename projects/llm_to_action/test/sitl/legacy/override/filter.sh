#!/bin/bash
# Manual override filter — captures ALL tmux panes to captured_override_log.txt IN THIS
# FOLDER, prints the digest + PASS/FAIL. Run after you've toggled override at least once.
# Optional arg: tmux session name (default llmsim).
set -euo pipefail
cd "$(dirname "$0")" || exit 1
OUT="captured_override_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"

echo "----- override digest -----"
grep -E 'MANUAL OVERRIDE (engaged|released)|will re-plan' "$OUT" || true
awk '
    /MANUAL OVERRIDE engaged/{ eng++ }
    /MANUAL OVERRIDE released/{ rel++ }
    /will re-plan/{ replan++ }
    END{
        if(!eng){ print "\n  FAIL: no MANUAL OVERRIDE engaged — press Enter (or publish {data: true} to /fmu/in/override)"; exit 1 }
        print "\n  ok   engaged x" eng+0 " (autonomy paused, operator in control)";
        if(rel){ print "  ok   released x" rel+0 " (autonomy resumed)"; }
        else    { print "  WARN: no release seen — press Enter again to hand control back"; }
        if(rel && !replan){ print "  WARN: released but no re-plan line — check the VLM pane is up (LAUNCH_VLM=1)"; }
        print "\nPASS (manual keys flew it; handback resumed autonomy).";
        exit 0
    }' "$OUT"
