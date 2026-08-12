#!/bin/bash
# P1 disarm verify (agent3, no code change -- verifies the px4_backend.cpp fix landed
# in 5f935e0). Takes off, flies a canned orbit, then a background injector fires
# `commander disarm -f` (PX4's in-flight force-disarm; the spec's "--force" maps to
# the `-f` magic-21196 override) into the PX4 pxh console mid-flight.
#
# Expected signature in captured_panes_log.txt:
#   [PX4_BACKEND_DEBUG] OFFBOARD+ARM CONFIRMED ...            (airborne, FLIGHT)
#   [PX4_BACKEND_DEBUG] unexpected disarm while airborne ... FLIGHT->FAULT.
#   [FMU_NODE_DEBUG] backend left FLIGHT ... -> stop, reconcile STANDBY, abort task.
#   completeCurrent("backend_lost_flight")  -> task abort
#
# Run:  cd scripts/test/SITL/disarm-verify && ./run.sh     (headless; ~2-3 min)
# Then: ./filter.sh   to print the captured signature.
cd "$(dirname "$0")" || exit 1

echo "================================================================"
echo " P1 DISARM VERIFY -- open QGroundControl FIRST (PX4 won't arm"
echo " without it). This will: arm, take off, start an orbit, then"
echo " force-disarm mid-flight. WATCH QGC: the drone should drop out"
echo " of the orbit and go DISARMED. When it finishes, run ./filter.sh"
echo " for an automatic PASS/FAIL."
echo "================================================================"

# WARNING: brings up the gz GstCameraPlugin (TX) + the gstreamer RX node, which bind
# the SAME UDP ports the real Tello uses (11111 video / 8889 cmd / 8890 state). Do NOT
# run while any Tello work is live -- it hogs those ports.
#
# Headless arming: PX4 refuses to arm without a GCS link when NAV_DLL_ACT > 0
# ("Preflight Fail: No connection to the GCS" -> "Arming denied: Resolve system health
# failures first"). Attended runs pass because QGroundControl supplies that link; a
# headless run has none, so waive the data-link-loss action to let it arm.
# (Set by agent3 from the log root-cause; NOT yet flight-tested by agent3 -- see Report.)
export PX4_PARAM_NAV_DLL_ACT=0

FMU_OBJECTIVE="Orbit the car a quarter turn, then land."
FMU_CANNED_FLAG="--canned-orbit"
WORLD_NAME="default_car"
SPAWN_POSE="0,6,3"

export SESSION_NAME=llmsim
# GUI=1 -> attended run: PX4 spawns the Gazebo GUI window and this attaches to the tmux
# session so you can watch. The auto-injector still fires the disarm. Detach with Ctrl-B
# then D when the drone is down; that triggers cleanup. Default (GUI unset) is headless.
if [ "${GUI:-0}" = "1" ]; then
    echo ">>> GUI=1: attended run -- a Gazebo window should open; watch the drone there."
    # leave HEADLESS unset so PX4 launches the Gazebo GUI and sim_core attaches to tmux
    :
else
    export HEADLESS=1
fi
export HEADLESS_COMPLETION=flight
export HEADLESS_TIMEOUT_SECONDS=140
LOG_FILE="$(pwd)/captured_panes_log.txt"
export LOG_FILE
INJ_LOG="$(pwd)/inject.log"
: > "$INJ_LOG"
rm -f "$LOG_FILE"

# --- background injector: force-disarm once solidly airborne ---
(
  echo "[inject] $(date -u +%H:%M:%SZ) waiting for FLIGHT (OFFBOARD+ARM CONFIRMED)..." >>"$INJ_LOG"
  confirmed=0
  for i in $(seq 1 150); do
    if [ -f "$LOG_FILE" ] && grep -q "OFFBOARD+ARM CONFIRMED" "$LOG_FILE" 2>/dev/null; then
      confirmed=1
      echo "[inject] $(date -u +%H:%M:%SZ) FLIGHT confirmed (loop=$i)" >>"$INJ_LOG"
      break
    fi
    sleep 1
  done
  if [ "$confirmed" != "1" ]; then
    echo "[inject] ERROR never saw FLIGHT confirmation -- aborting injection" >>"$INJ_LOG"
    exit 0
  fi
  sleep 8   # let it be unambiguously airborne (and visible in QGC/gz) before the disarm
  # target the PX4 pxh pane by its STABLE pane-id via the px4_sitl start-command
  # (pane INDEX renumbers after select-layout tiled, so $SESSION:0.1 is unreliable).
  PANE=$(tmux list-panes -t "$SESSION_NAME" -F '#{pane_id}|#{pane_start_command}' 2>/dev/null | awk -F'|' '/px4_sitl/{print $1; exit}')
  echo "[inject] $(date -u +%H:%M:%SZ) firing 'commander disarm -f' -> pane ${PANE:-<none>}" >>"$INJ_LOG"
  [ -n "$PANE" ] && tmux send-keys -t "$PANE" "commander disarm -f" Enter
  ok=0
  for i in $(seq 1 15); do
    grep -q "backend left FLIGHT" "$LOG_FILE" 2>/dev/null && { ok=1; echo "[inject] $(date -u +%H:%M:%SZ) reconcile captured (loop=$i)" >>"$INJ_LOG"; break; }
    sleep 1
  done
  if [ "$ok" != "1" ]; then
    echo "[inject] $(date -u +%H:%M:%SZ) no reconcile -- broadcasting disarm to ALL panes (fallback)" >>"$INJ_LOG"
    for pid in $(tmux list-panes -t "$SESSION_NAME" -F '#{pane_id}' 2>/dev/null); do
      tmux send-keys -t "$pid" "commander disarm -f" Enter 2>/dev/null
    done
    for i in $(seq 1 30); do
      grep -q "backend left FLIGHT" "$LOG_FILE" 2>/dev/null && { echo "[inject] $(date -u +%H:%M:%SZ) reconcile captured after broadcast (loop=$i)" >>"$INJ_LOG"; break; }
      sleep 1
    done
  fi
  echo "[inject] $(date -u +%H:%M:%SZ) injector done" >>"$INJ_LOG"
) &

source ../../lib/sim_core.sh

echo ""
echo "================================================================"
echo " Run  ./filter.sh  now for the PASS/FAIL verdict."
echo "================================================================"
