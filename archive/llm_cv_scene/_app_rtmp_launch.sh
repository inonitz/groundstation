#!/usr/bin/env bash
# Launch helper for run_demo_rtmp.sh. Keeps OPENCV_FFMPEG_CAPTURE_OPTIONS (value contains a ';')
# out of the nested tmux/bash -c quoting that would otherwise split the command on it.
source /opt/ros/jazzy/setup.bash
cd "$(dirname "$0")"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp"
export SCENE_INPUT="${SCENE_INPUT:-rtsp://127.0.0.1:8554/live}"
sleep 2
exec python3 app.py
