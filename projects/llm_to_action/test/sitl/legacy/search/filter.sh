#!/bin/bash
# search verdict: SEARCH must activate and then DETECT the car within the advance-and-scan.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
OUT="captured_panes_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then echo "no FMU log at '$LOG_FILE' -- run ./run.sh first" >&2; exit 2; fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"
echo "----- search milestones -----"
grep -E 'SEARCH activated|SEARCH scan|SEARCH advance|SEARCH DETECTED' "$OUT" | tail -8 \
    || echo "  (no search lines captured)"
echo ""
if ! grep -q 'SEARCH activated' "$OUT"; then echo "  FAIL: SEARCH never activated"; exit 1; fi
if grep -q 'SEARCH DETECTED target=car' "$OUT"; then
    echo "  $(grep -E 'SEARCH DETECTED' "$OUT" | tail -1 | sed 's/.*SEARCH DETECTED/SEARCH DETECTED/')"
    echo "  PASS: search scanned and DETECTED the car"; exit 0
fi
echo "  FAIL: SEARCH activated but never DETECTED the car (scanned/timed out without a find)"; exit 1
