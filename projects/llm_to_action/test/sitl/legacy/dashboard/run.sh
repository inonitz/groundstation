#!/bin/bash
# Headless SITL + live dashboard, self-assessing.
#
# Brings up the moving_person FOLLOW demo with Gazebo HEADLESS (no GUI window)
# and FMU_OBSERVABILITY on, starts the dashboard bridge, and runs an assessor
# that checks the whole pipeline -- topics, the 320x240 FMU-side resize, the
# publish rate, the HUD, and the website's MJPEG + SSE -- then writes a PASS/FAIL
# verdict. Watch the demo at http://localhost:$DASH_PORT instead of a Gazebo
# window. The stack self-tears-down after HEADLESS_TIMEOUT_SECONDS.
#
#   ./run.sh                                # demo: up ~30 min, assesses once
#   HEADLESS_TIMEOUT_SECONDS=150 ./run.sh   # short self-test / CI
#
# Logs (fmu.log, dashboard.log, assess.log, verdict.txt, sim.log) land in
# ./logs_<timestamp>/. The stack (PX4, gz, FMU, VLM) is a child process with its
# own cleanup trap; this wrapper only owns the dashboard bridge + assessor.
#
# Needs: PX4 built, gz, the ONNX vision + Qwen VLM models, MicroXRCEAgent.
set -u
cd "$(dirname "$0")" || exit 1
HERE="$(pwd)"
GS=/root/groundstation
: "${DASH_PORT:=8088}"
: "${HEADLESS_TIMEOUT_SECONDS:=1800}"
LOGDIR="$HERE/logs_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOGDIR"
echo "[dashboard-test] logs      -> $LOGDIR"
echo "[dashboard-test] dashboard -> http://localhost:$DASH_PORT  (watch here, not a Gazebo window)"

# Dashboard bridge + assessor run alongside the stack. Start them first so the
# assessor is already polling when the topics appear.
python3 "$GS/scripts/dashboard/serve.py" "$DASH_PORT" --log "$LOGDIR/dashboard.log" \
    > "$LOGDIR/dashboard.stderr" 2>&1 &
DASH_PID=$!
python3 "$GS/scripts/dashboard/assess.py" --port "$DASH_PORT" \
    --out "$LOGDIR/verdict.txt" --wait 120 --measure 6 \
    > "$LOGDIR/assess.log" 2>&1 &
ASSESS_PID=$!
trap 'kill "$DASH_PID" "$ASSESS_PID" 2>/dev/null' EXIT INT TERM

# The SITL stack as a child: reuse the follow scenario unchanged, headless, with
# observability on and the GCS arm-check waived. Its own trap (sim_core) tears
# down PX4/gz/FMU/VLM when it returns; we only clean the dashboard, above.
echo "[dashboard-test] bringing up headless SITL (moving_person FOLLOW), holding ${HEADLESS_TIMEOUT_SECONDS}s..."
HEADLESS=1 FMU_OBSERVABILITY=1 PX4_PARAM_NAV_DLL_ACT=0 RECORD_BAG=0 \
    HEADLESS_TIMEOUT_SECONDS="$HEADLESS_TIMEOUT_SECONDS" HEADLESS_COMPLETION=fixed \
    SESSION_NAME=dashdemo LOG_FILE="$LOGDIR/fmu.log" \
    bash "$GS/projects/llm_to_action/test/sitl-legacy/follow/run.sh" > "$LOGDIR/sim.log" 2>&1

echo "[dashboard-test] stack torn down. Verdict:"
echo "--------------------------------------------------------------------"
cat "$LOGDIR/verdict.txt" 2>/dev/null || echo "(no verdict -- see $LOGDIR/assess.log)"
echo "--------------------------------------------------------------------"
echo "[dashboard-test] full logs in $LOGDIR"
