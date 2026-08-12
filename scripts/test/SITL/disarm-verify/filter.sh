#!/bin/bash
# P1 disarm verify -- AUTO VERDICT.
# Reads the captured FMU log and prints an unmissable PASS/FAIL: the four reconcile
# lines must all be present AND in order. Run after ./run.sh finishes.
#   PASS -> exit 0,  FAIL -> exit 1.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
LOG="${1:-captured_panes_log.txt}"

if [ ! -f "$LOG" ]; then
    echo "no log at '$LOG' -- run ./run.sh first" >&2
    exit 2
fi

# each step: label + grep pattern. Order matters.
labels=(
  "1. Reached FLIGHT (armed + offboard confirmed)"
  "2. In-flight disarm caught -> FLIGHT->FAULT"
  "3. FMU stopped, reconciled to STANDBY, aborted task"
  "4. Task aborted with reason backend_lost_flight"
)
pats=(
  "OFFBOARD\+ARM CONFIRMED"
  "unexpected disarm while airborne.*FLIGHT->FAULT"
  "backend left FLIGHT.*reconcile STANDBY, abort task"
  "task complete status=backend_lost_flight"
)

echo "================ P1 DISARM VERIFY ================"
prev=0
allok=1
for i in "${!pats[@]}"; do
    ln=$(grep -nE "${pats[$i]}" "$LOG" 2>/dev/null | head -1 | cut -d: -f1)
    if [ -z "$ln" ]; then
        printf "  [FAIL] %s\n         (line not found)\n" "${labels[$i]}"
        allok=0
    elif [ "$ln" -le "$prev" ]; then
        printf "  [FAIL] %s\n         (out of order: line %s not after %s)\n" "${labels[$i]}" "$ln" "$prev"
        allok=0
    else
        printf "  [ ok ] %s   (log line %s)\n" "${labels[$i]}" "$ln"
        prev=$ln
    fi
done

echo "-------------------------------------------------"
echo "Matched log lines:"
grep -nE "OFFBOARD\+ARM CONFIRMED|unexpected disarm while airborne|backend left FLIGHT|task complete status=backend_lost_flight" "$LOG" \
    | sed 's/^/  /'
echo "-------------------------------------------------"
if [ "$allok" = "1" ]; then
    echo ">>> RESULT: PASS -- in-flight disarm was caught and the task was aborted."
    echo "================================================="
    exit 0
else
    echo ">>> RESULT: FAIL -- see the [FAIL] steps above. Common cause: the disarm"
    echo ">>>         never reached the drone (never left a full clean orbit), or PX4"
    echo ">>>         never armed (open QGroundControl first)."
    echo "================================================="
    exit 1
fi
