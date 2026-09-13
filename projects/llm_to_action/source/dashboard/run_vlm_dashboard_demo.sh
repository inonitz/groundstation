#!/bin/bash
# Headless multi-step VLM demo on the live dashboard.
#
# Runs the `vlm` scenario -- a TYPED objective, no voice needed:
#   "Take off, find the car, approach it, move 2 m back, orbit it 15 s, then land."
# The VLM (Qwen3-VL) plans; the FMU flies it; the dashboard shows the camera, depth,
# flight HUD, and the VLM objective + plan + reasoning. Watch in a browser, not a
# Gazebo window. The stack self-tears-down after HEADLESS_TIMEOUT_SECONDS.
#
#   ./run_vlm_dashboard_demo.sh                       # default model (sim_core), up to 5 min
#   VLM_MODEL=/root/models/vlm/Qwen3-VL-2B-Instruct/Qwen3-VL-2B-Instruct-Q4_K_M.gguf \
#   VLM_MMPROJ=/root/models/vlm/Qwen3-VL-2B-Instruct/mmproj-BF16.gguf \
#     ./run_vlm_dashboard_demo.sh                     # 2B (faster)
#
# Watch:  http://localhost:$DASH_PORT
# Needs: PX4 built, gz, the ONNX vision models, the Qwen VLM, MicroXRCEAgent.
set -u
cd "$(dirname "$0")" || exit 1
GS="$(cd "$(dirname "$0")/../../../.." && pwd)"
: "${DASH_PORT:=8088}"
: "${HEADLESS_TIMEOUT_SECONDS:=300}"
LOGDIR="$(pwd)/logs_vlm_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOGDIR"
echo "[vlm-dash] logs      -> $LOGDIR"
echo "[vlm-dash] dashboard -> http://localhost:$DASH_PORT  (watch here, not a Gazebo window)"

python3 "$GS/projects/llm_to_action/source/dashboard/serve.py" "$DASH_PORT" --log "$LOGDIR/dashboard.log" \
    > "$LOGDIR/dashboard.stderr" 2>&1 &
DASH_PID=$!
trap 'kill "$DASH_PID" 2>/dev/null' EXIT INT TERM

echo "[vlm-dash] bringing up headless SITL (vlm scenario), holding up to ${HEADLESS_TIMEOUT_SECONDS}s..."
HEADLESS=1 FMU_OBSERVABILITY=1 PX4_PARAM_NAV_DLL_ACT=0 RECORD_BAG=0 \
    HEADLESS_TIMEOUT_SECONDS="$HEADLESS_TIMEOUT_SECONDS" HEADLESS_COMPLETION=flight \
    SESSION_NAME=vlmdash \
    bash "$GS/projects/llm_to_action/test/sitl/run.sh" "vlm" > "$LOGDIR/sim.log" 2>&1

echo "[vlm-dash] stack torn down."
echo "[vlm-dash] FMU log: $GS/projects/llm_to_action/test/sitl/runs/vlm/captured_panes_log.txt"
echo "[vlm-dash] logs in $LOGDIR"
