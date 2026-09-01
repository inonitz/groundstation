#!/usr/bin/env bash
# Real-time tracking on the drone feed: start RTMP ingest, then BoT-SORT track. (../llm_cv_scene untouched.)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || hostname -I | awk '{print $1}')
pkill -x mediamtx 2>/dev/null || true
mediamtx >/tmp/mediamtx_track.log 2>&1 &
sleep 2
echo "=================================================================="
echo "  DJI Fly -> Custom RTMP:   rtmp://${IP}:1935/live"
echo "  Hit 'Go Live' in DJI Fly, THEN press ENTER."
echo "=================================================================="
read -r _
cd "$HERE"; exec python3 track.py "$@"
