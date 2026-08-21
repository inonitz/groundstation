#!/usr/bin/env bash
# Priority-1 demo: voice -> open-vocab detect (OmDet-Turbo) -> SAM2.1 mask, on the drone feed.
# For live voice, run the ROS2 asr_node in another pane FIRST (press H there to talk), or pass
# --target "..." to seed a highlight without ASR. (../llm_cv_scene untouched.)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || hostname -I | awk '{print $1}')
cleanup() { pkill -x mediamtx 2>/dev/null || true; }   # highlight_seg cleans up llama-server itself
trap cleanup EXIT INT TERM
pkill -x mediamtx 2>/dev/null || true
mediamtx >/tmp/mediamtx_hlseg.log 2>&1 &
sleep 2
echo "=================================================================="
echo "  DJI Fly -> Custom RTMP:   rtmp://${IP}:1935/live"
echo "  Hit 'Go Live' in DJI Fly, THEN press ENTER."
echo "  Voice: start the asr_node in another pane and press H to talk."
echo "  (No drone? test with: python3 ${HERE}/highlight_seg.py --source 0 --target \"guitar case\")"
echo "=================================================================="
read -r _
cd "$HERE"; python3 highlight_seg.py "$@"
