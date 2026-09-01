#!/usr/bin/env bash
# One-command tmux launcher for the STAR demo (scene_omdet.py: OmDet open-vocab -> SAM2 masks, VOICE).
# Auto-starts everything, each in its OWN pane so you can watch for issues:  [rtmp] | vlm | keys | asr | app
#   bash run_scene_omdet.sh                  # webcam
#   bash run_scene_omdet.sh rtmp             # drone (MediaMTX ingest of DJI Fly Custom RTMP)
#   ASR_CAPTUREID=5 bash run_scene_omdet.sh  # pick mic device (C920=5; MOTU surround is dead)
# Switch panes: Ctrl-b then 0/1/2/3/4.  press H to talk.  Quit app (q/Esc) OR Ctrl-C = FULL shutdown.
set -euo pipefail
MODE="${1:-webcam}"
SESSION=scene_omdet
HERE="$(cd "$(dirname "$0")" && pwd)"
SCENE=/root/groundstation/source/llm_cv_scene
BIN=/root/groundstation/build/release/shared/dji/bin
ASR_MODEL="${ASR_MODEL_PATH:-/root/models/asr/nvidia--parakeet-tdt-0.6b-v3/ggml-parakeet-tdt-0.6b-v3-q4_k.bin}"
ROS_SETUP=/opt/ros/jazzy/setup.bash

cleanup() {
    tmux kill-session -t "$SESSION"        2>/dev/null || true
    pkill -x mediamtx                      2>/dev/null || true
    pkill -f "llama-server"                2>/dev/null || true
    pkill -f "llm_to_action_asr_server"    2>/dev/null || true
    pkill -f "llm_to_action_keyboard_hook" 2>/dev/null || true
    pkill -f "$HERE/scene_omdet.py"        2>/dev/null || true
    echo "[run_scene_omdet] stopped: mediamtx + VLM + keys + ASR + app down."
}
trap cleanup EXIT INT TERM

command -v tmux >/dev/null 2>&1 || { echo "tmux not installed"; exit 1; }
[ -x "$BIN/llm_to_action_keyboard_hook" ] || echo "[run_scene_omdet] WARN: keyboard_hook not built -- H push-to-talk won't work."
[ -x "$BIN/llm_to_action_asr_server" ]    || echo "[run_scene_omdet] WARN: asr_server not built -- voice off (vision still works)."
[ -f "$ASR_MODEL" ]                       || echo "[run_scene_omdet] WARN: ASR model missing: $ASR_MODEL"

# fresh start
tmux kill-session -t "$SESSION" 2>/dev/null || true
pkill -x mediamtx 2>/dev/null || true
pkill -f "llama-server" 2>/dev/null || true
pkill -f "llm_to_action_asr_server" 2>/dev/null || true
pkill -f "llm_to_action_keyboard_hook" 2>/dev/null || true

RTMP=0; SRC_ENV="SCENE_INPUT=0"
if [ "$MODE" = "rtmp" ] || [ "$MODE" = "drone" ] || [ "$MODE" = "--drone" ]; then
    command -v mediamtx >/dev/null 2>&1 || { echo "mediamtx not installed (needed for rtmp mode)"; exit 1; }
    RTMP=1; SRC_ENV="SCENE_INPUT=rtsp://127.0.0.1:8554/live"
    IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || hostname -I | awk '{print $1}')
    echo "=============================================================="
    echo " DJI Fly -> Live Streaming -> Custom RTMP:   rtmp://${IP}:1935/live"
    echo " Go Live in DJI Fly AFTER the app pane says it is waiting for the stream."
    echo "=============================================================="
fi

CMD_KEYS="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH && $BIN/llm_to_action_keyboard_hook"
CMD_ASR="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH && $BIN/llm_to_action_asr_server --backend=whisper-parakeet --model=$ASR_MODEL --fa --language=en --threads=1 --gid=0 --captureid=${ASR_CAPTUREID:--1}"
CMD_APP="source $ROS_SETUP && cd $HERE && export SCENE_TMUX_SESSION=$SESSION $SRC_ENV && sleep 3 && python3 scene_omdet.py"

tmux new-session -d -s "$SESSION" -n vlm "bash -c '$SCENE/run_llama_server.sh; echo [vlm exited]; exec bash'"
[ "$RTMP" = "1" ] && tmux new-window -t "$SESSION" -n rtmp "bash -c 'mediamtx; echo [rtmp exited]; exec bash'"
tmux new-window -t "$SESSION" -n keys "bash -c '$CMD_KEYS; echo [keys exited]; exec bash'"
tmux new-window -t "$SESSION" -n asr  "bash -c '$CMD_ASR; echo [asr exited]; exec bash'"
tmux new-window -t "$SESSION" -n app  "bash -c '$CMD_APP; echo [app exited]; exec bash'"
LOGDIR="${SCENE_LOGDIR:-/tmp}"
for w in vlm rtmp keys asr app; do
    tmux pipe-pane -t "$SESSION:$w" "cat >> $LOGDIR/scene_omdet_$w.log" 2>/dev/null || true
done
echo "[run_scene_omdet] panes logging -> $LOGDIR/scene_omdet_{vlm,keys,asr,app}.log"
tmux select-window -t "$SESSION:app"
echo "[run_scene_omdet] up. Ctrl-b then a number switches panes -- CHECK EACH for errors (asr = mic, vlm = llama)."
echo "[run_scene_omdet] press H to talk (say 'highlight the red backpack' / 'what do you see' / 'clear')."
echo "[run_scene_omdet] Quit app window (q/Esc) OR Ctrl-C here = FULL shutdown."
tmux attach -t "$SESSION"
