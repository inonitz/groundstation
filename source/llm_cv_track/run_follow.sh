#!/usr/bin/env bash
# Voice-driven tracked highlighting on the drone feed: RTMP ingest -> follow.py (VLM lock + BoT-SORT).
# For live voice, run the ROS2 asr_node in another pane FIRST (press H there to talk). Or pass
# --command "..." for a keyboard-seeded test without ASR.  (../llm_cv_scene untouched.)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || hostname -I | awk '{print $1}')
cleanup() { pkill -x mediamtx 2>/dev/null || true; }   # follow.py cleans up llama-server itself
trap cleanup EXIT INT TERM
pkill -x mediamtx 2>/dev/null || true
mediamtx >/tmp/mediamtx_follow.log 2>&1 &
sleep 2
echo "=================================================================="
echo "  DJI Fly -> Custom RTMP:   rtmp://${IP}:1935/live"
echo "  Hit 'Go Live' in DJI Fly, THEN press ENTER."
echo "  Voice: start the asr_node in another pane and press H to talk."
echo "=================================================================="
read -r _
cd "$HERE"; python3 follow.py "$@"
