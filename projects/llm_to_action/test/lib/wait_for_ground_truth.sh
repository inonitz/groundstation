#!/bin/bash
# wait_for_ground_truth.sh — the headless "is this run over" signal, sourced from real
# PX4 topics (arming_state + landed), NOT from FMU's own printed log lines. The FMU's
# self-reported "reached"/"complete" text has been wrong before (see ROADMAP 6.4); this
# only trusts what the vehicle itself is telling PX4.
#   flight (default): wait for ARMED, then DISARMED-while-landed.
#   fixed: no flight happens (flood/override) -- just sleep the timeout.
# Usage: wait_for_ground_truth.sh <flight|fixed> <timeout_seconds>
set -uo pipefail
MODE="${1:-flight}"
TIMEOUT="${2:-120}"
POLL_INTERVAL=2
STATUS_TOPIC="/fmu/out/vehicle_status_v4"
LAND_TOPIC="/fmu/out/vehicle_land_detected"
ARMING_STATE_ARMED=2   # px4_msgs::msg::VehicleStatus::ARMING_STATE_ARMED

if [ "$MODE" = "fixed" ]; then
    echo "[wait] fixed mode: sleeping ${TIMEOUT}s"
    sleep "$TIMEOUT"
    exit 0
fi

echo "[wait] flight mode: polling $STATUS_TOPIC / $LAND_TOPIC every ${POLL_INTERVAL}s (timeout ${TIMEOUT}s)"
elapsed=0
seen_armed=0
while [ "$elapsed" -lt "$TIMEOUT" ]; do
    arm_val=$(timeout 3 ros2 topic echo "$STATUS_TOPIC" --once 2>/dev/null | awk -F': *' '/^arming_state:/{print $2; exit}')
    landed_val=$(timeout 3 ros2 topic echo "$LAND_TOPIC" --once 2>/dev/null | awk -F': *' '/^landed:/{print $2; exit}')

    if [ "$arm_val" = "$ARMING_STATE_ARMED" ]; then
        seen_armed=1
    fi
    if [ "$seen_armed" = "1" ] && [ -n "$arm_val" ] && [ "$arm_val" != "$ARMING_STATE_ARMED" ] && [ "$landed_val" = "true" ]; then
        echo "[wait] ground truth: armed then landed+disarmed at t=${elapsed}s"
        exit 0
    fi
    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
done
echo "[wait] TIMEOUT after ${TIMEOUT}s (seen_armed=$seen_armed) -- tearing down; filter.sh will judge PASS/FAIL from whatever the log shows"
exit 0
