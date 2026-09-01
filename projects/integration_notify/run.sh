#!/usr/bin/env bash
# run.sh -- MAIN COURSE: launch the notify MVD against the already-warm VLM (run bootstrap.sh first).
#   bash run.sh                # webcam + notify (drone-free; the morning train test)
#   bash run.sh dji            # drone video via the fork's run_mvd.sh (mock control)
#   bash run.sh dji real       # drone + REAL control (HUMAN, aircraft secured)
# Env:  NOTIFY_ATTRS="in a red shirt"   NOTIFY_TRACKER=iou|osnet   MVD_NO_ACTIONS=1 (perception-only)
#       MVD_DASH=1 (default; dashboard on :8090)   MVD_DASH_PORT=8090
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$ROOT/projects/integration_notify"
MODE="${1:-webcam}"
source /opt/ros/jazzy/setup.bash 2>/dev/null || true
export MVD_DASH="${MVD_DASH:-1}"
if [ "${MVD_DASH}" = "1" ]; then
    ( python3 "$HERE/dashboard/serve.py" "${MVD_DASH_PORT:-8090}" >/tmp/mvd_dash.log 2>&1 & )
    echo "[run] dashboard -> http://localhost:${MVD_DASH_PORT:-8090}  (cv2 pane is the always-on fallback)"
fi
if [ "$MODE" = "webcam" ]; then
    export SCENE_INPUT=0
    echo "[run] webcam + notify (tracker=${NOTIFY_TRACKER:-iou} attrs='${NOTIFY_ATTRS:-<voice-arm>}' perception_only=${MVD_NO_ACTIONS:-0})"
    exec python3 "$HERE/scene_omdet.py" --source 0
else
    exec bash "$HERE/run_mvd.sh" "$@"
fi
