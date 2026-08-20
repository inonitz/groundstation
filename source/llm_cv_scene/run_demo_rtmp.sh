#!/usr/bin/env bash
# RTMP variant of run_demo.sh: ingest the DJI Fly "Custom RTMP" push ON THIS BOX (MediaMTX) and feed
# it to llm_cv_scene. No SDK app, no phone -- works with the locked DJI RC 2 + DJI Fly.
#
# In DJI Fly -> Transmission/Live Streaming -> Custom RTMP, enter:   rtmp://<THIS-BOX-IP>:1935/live
#   - RC 2 and this box must be on the SAME WiFi router.
#   - DJI Fly >= 1.16 needs ANY audio device in the RC 2's USB-C port to unlock "Go Live".
#
# Windows: rtmp | vlm | keys | asr | app.  Detach (Ctrl-b d) or Ctrl-C = FULL shutdown.
set -euo pipefail
SESSION=llm_cv_scene_rtmp
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN=/root/groundstation/build/release/shared/px4/bin
ASR_MODEL="${ASR_MODEL_PATH:-/root/models/asr/nvidia--parakeet-tdt-0.6b-v3/ggml-parakeet-tdt-0.6b-v3-q4_k.bin}"
ROS_SETUP=/opt/ros/jazzy/setup.bash
STREAM_PATH="${RTMP_PATH:-live}"
RTSP_URL="rtsp://127.0.0.1:8554/${STREAM_PATH}"

cleanup() {
    tmux kill-session -t "$SESSION"        2>/dev/null || true
    pkill -x mediamtx                    2>/dev/null || true
    pkill -f "$BIN/llama-server"           2>/dev/null || true
    pkill -f "llm_to_action_asr_server"    2>/dev/null || true
    pkill -f "llm_to_action_keyboard_hook" 2>/dev/null || true
    pkill -f "$HERE/app.py"                2>/dev/null || true
    echo "[run_demo_rtmp] stopped: mediamtx + VLM + keys + ASR + app down."
}
trap cleanup EXIT INT TERM

command -v tmux     >/dev/null 2>&1 || { echo "[run_demo_rtmp] tmux not installed"; exit 1; }
command -v mediamtx >/dev/null 2>&1 || { echo "[run_demo_rtmp] mediamtx not installed (RTMP ingest). See header."; exit 1; }
[ -x "$BIN/llm_to_action_keyboard_hook" ] || echo "[run_demo_rtmp] WARN: keyboard_hook not built -- H toggle won't work."
[ -x "$BIN/llm_to_action_asr_server" ]    || echo "[run_demo_rtmp] WARN: asr_server not built -- voice off."
[ -f "$ASR_MODEL" ]                       || echo "[run_demo_rtmp] WARN: ASR model missing: $ASR_MODEL"

IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || hostname -I | awk '{print $1}')  # LAN IP, never docker0
echo "=============================================================="
echo " DJI Fly -> Live Streaming -> Custom RTMP, enter this URL:"
echo "     rtmp://${IP}:1935/${STREAM_PATH}"
echo " (RC 2 + this box on the SAME WiFi; USB-C mic in the RC 2.)"
echo "=============================================================="

# fresh start
tmux kill-session -t "$SESSION"        2>/dev/null || true
pkill -x mediamtx                    2>/dev/null || true
pkill -f "$BIN/llama-server"           2>/dev/null || true
pkill -f "llm_to_action_asr_server"    2>/dev/null || true
pkill -f "llm_to_action_keyboard_hook" 2>/dev/null || true

CMD_RTMP="mediamtx"
CMD_KEYS="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH && $BIN/llm_to_action_keyboard_hook"
CMD_ASR="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH && $BIN/llm_to_action_asr_server --backend=whisper-parakeet --model=$ASR_MODEL --fa --language=en --threads=1 --gid=0 --captureid=${ASR_CAPTUREID:--1}"
# Read from MediaMTX over RTSP/TCP (OpenCV's FFMPEG backend). Warmup runs immediately; the app then
# waits for the stream (SCENE_OPEN_TIMEOUT) so you can 'Go Live' in DJI Fly after it's warm.
CMD_APP="SCENE_INPUT=$RTSP_URL SCENE_TMUX_SESSION=$SESSION bash $HERE/_app_rtmp_launch.sh"

tmux new-session -d -s "$SESSION" -n rtmp "bash -c '$CMD_RTMP; echo [rtmp/mediamtx exited]; exec bash'"
tmux new-window  -t "$SESSION"    -n vlm  "bash -c '$HERE/run_llama_server.sh; echo [vlm exited]; exec bash'"
tmux new-window  -t "$SESSION"    -n keys "bash -c '$CMD_KEYS; echo [keys exited]; exec bash'"
tmux new-window  -t "$SESSION"    -n asr  "bash -c '$CMD_ASR; echo [asr exited]; exec bash'"
tmux new-window  -t "$SESSION"    -n app  "bash -c '$CMD_APP; echo [app exited]; exec bash'"
LOGDIR="${SCENE_LOGDIR:-/tmp}"
for w in rtmp vlm keys asr app; do
    tmux pipe-pane -t "$SESSION:$w" "cat >> $LOGDIR/llm_cv_scene_$w.log"
done
tmux select-window -t "$SESSION:app"
echo "[run_demo_rtmp] up: rtmp | vlm | keys | asr | app."
echo "[run_demo_rtmp] app warms up (~2-4 min first time), then WAITS for the stream."
echo "[run_demo_rtmp] Point DJI Fly at the URL above, hit 'Go Live', then press H to talk."
echo "[run_demo_rtmp] Detach (Ctrl-b d) or Ctrl-C = FULL shutdown. Switch windows Ctrl-b 0-4."
tmux attach -t "$SESSION"
