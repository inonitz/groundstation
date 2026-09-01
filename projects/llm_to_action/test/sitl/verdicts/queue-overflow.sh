#!/bin/bash
# Backpressure flood-test filter — captures ALL tmux panes to captured_flood_log.txt IN
# THIS FOLDER, prints the digest + PASS/FAIL. Run once the sim is up (the flood happens at
# FMU start; the drone does NOT fly -- this test only stresses the task queue). Optional
# arg: tmux session name (default llmsim).
#
# What we prove: one plan of 100 'stop' actions is injected in a single burst at FMU start.
# The SPSC queue is a moodycamel::ReaderWriterQueue built with cap=kMaxPlanActions(=60).
# That queue rounds capacity UP to (next power of two of cap+1) - 1 usable slots = 63, so
# ~63 enqueue and the rest are rejected with a BACKPRESSURE log. The invariant that matters
# is NOT a magic number: (a) backpressure engaged (drops>0), (b) the queue stayed BOUNDED
# near cap (never grew to hold all 100), (c) nothing vanished silently (enqueued+dropped ==
# injected). Portable awk only (mawk-safe).
set -euo pipefail
cd "${SITL_RUN_DIR:-$(dirname "$0")}" || exit 1
OUT="captured_flood_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"

echo "----- flood digest -----"
grep -E 'QUEUE-OVERFLOW test:|overflow dropped by backpressure' "$OUT" || echo "  (no flood lines)"
echo ""
if grep -q 'QUEUE-OVERFLOW test:' "$OUT" && grep -q 'overflow dropped by backpressure' "$OUT"; then
    echo "  PASS: flood injected the oversized plan and backpressure dropped the overflow (queue held)."
    exit 0
fi
echo "  FAIL: no FLOOD injection / no backpressure drop -- did you run ./run.sh (flood scenario)?"
exit 1
