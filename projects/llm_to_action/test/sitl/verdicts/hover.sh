#!/bin/bash
# hover persistence verdict: fwd 1.5m -> HOVER holds -> the back-go must NEVER run.
# HOVER never completes, so the queued back-go + land can only run if HOVER leaked. PASS iff there
# is NO GO activity after 'HOVER activated' (the absence of the reversal IS the proof it held).
# Self-contained: captures panes to captured_panes_log.txt here, then verdicts from it.
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

echo "----- hover milestones -----"
grep -E 'GO activated|GO complete|HOVER activated|HOVER holding station' "$OUT" \
    || echo "  (no matching milestone lines captured -- check the FMU pane)"
echo ""
awk '
    /GO activated/ || /GO dist=/ || /GO complete/ { if (hover) go_after++; else go_before++; next }
    /HOVER activated/       { hover=1; next }
    /HOVER holding station/ { if (hover) hold++; next }
    END {
        if (go_before==0) { print "FAIL: forward GO never ran -- scenario did not launch"; exit 1 }
        if (!hover)       { print "FAIL: HOVER never activated -- forward leg did not hand off to hover"; exit 1 }
        if (hold==0)      { print "FAIL: no HOVER holding station -- stepHover did not run"; exit 1 }
        if (go_after>0)   { printf "FAIL: %d GO line(s) AFTER hover -- the back-go ran, HOVER leaked\n", go_after; exit 1 }
        print "PASS: forward 1.5m -> HOVER held (no back-go, no reversal)"; exit 0
    }' "$OUT"
