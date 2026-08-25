#!/usr/bin/env bash
# One-command launcher for the llm_cv_scene demo, WITH teardown. Windows: vlm | keys | asr | app.
# press H to start/stop recording (keyboard_hook publishes /keyboard/in/raw -> asr_node records on H press..release).
# Switch windows Ctrl-b 0/1/2/3.
# LEAVING shuts EVERYTHING down (VLM frees the GPU, ASR/keys release the mic + keyboard):
#   detach (Ctrl-b d) OR Ctrl-C the launcher -> cleanup() runs.
set -euo pipefail

SESSION=llm_cv_scene
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN=/root/groundstation/build/release/shared/dji/bin
ASR_MODEL="${ASR_MODEL_PATH:-/root/models/asr/nvidia--parakeet-tdt-0.6b-v3/ggml-parakeet-tdt-0.6b-v3-q4_k.bin}"
ROS_SETUP=/opt/ros/jazzy/setup.bash

cleanup() {
    tmux kill-session -t "$SESSION"      2>/dev/null || true
    pkill -f "$BIN/llama-server"         2>/dev/null || true
    pkill -f "llm_to_action_asr_server"  2>/dev/null || true
    pkill -f "llm_to_action_keyboard_hook" 2>/dev/null || true
    pkill -f "$HERE/app.py"              2>/dev/null || true
    echo "[run_demo] stopped: VLM + keys + ASR + app down."
}
trap cleanup EXIT INT TERM

command -v tmux >/dev/null 2>&1 || { echo "[run_demo] tmux not installed"; exit 1; }
[ -x "$BIN/llm_to_action_keyboard_hook" ] || echo "[run_demo] WARN: keyboard_hook not built -- H push-to-talk won't work."
[ -x "$BIN/llm_to_action_asr_server" ]    || echo "[run_demo] WARN: asr_server not built -- voice off, vision still works."
[ -f "$ASR_MODEL" ]                       || echo "[run_demo] WARN: ASR model missing: $ASR_MODEL"

# fresh start: purge any stale session/services from a previous run
tmux kill-session -t "$SESSION"        2>/dev/null || true
pkill -f "$BIN/llama-server"           2>/dev/null || true
pkill -f "llm_to_action_asr_server"    2>/dev/null || true
pkill -f "llm_to_action_keyboard_hook" 2>/dev/null || true

CMD_KEYS="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH && $BIN/llm_to_action_keyboard_hook"
CMD_ASR="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH && $BIN/llm_to_action_asr_server --backend=whisper-parakeet --model=$ASR_MODEL --fa --language=en --threads=1 --gid=0 --captureid=${ASR_CAPTUREID:--1}"
# HF_HUB_OFFLINE: weights are already cached/pre-baked -> load from disk, no hub check, works with NO internet.
CMD_APP="source $ROS_SETUP && cd $HERE && export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 SCENE_TMUX_SESSION=$SESSION SCENE_TTS=${SCENE_TTS:-phone} SCENE_TTS_HOST=${SCENE_TTS_HOST:-} SCENE_TTS_PORT=${SCENE_TTS_PORT:-8080} SCENE_TTS_LANG=${SCENE_TTS_LANG:-en} && sleep 3 && python3 app.py"

tmux new-session -d -s "$SESSION" -n vlm  "bash -c '$HERE/run_llama_server.sh; echo [vlm exited]; exec bash'"
tmux new-window  -t "$SESSION"    -n keys "bash -c '$CMD_KEYS; echo [keys exited]; exec bash'"
tmux new-window  -t "$SESSION"    -n asr  "bash -c '$CMD_ASR; echo [asr exited]; exec bash'"
tmux new-window  -t "$SESSION"    -n app  "bash -c '$CMD_APP; echo [app exited]; exec bash'"
LOGDIR="${SCENE_LOGDIR:-/tmp}"
for w in vlm keys asr app; do
    tmux pipe-pane -t "$SESSION:$w" "cat >> $LOGDIR/llm_cv_scene_$w.log"
done
echo "[run_demo] panes logging -> $LOGDIR/llm_cv_scene_{vlm,keys,asr,app}.log"
tmux select-window -t "$SESSION:app"

echo "[run_demo] up: vlm | keys | asr | app. press H to start/stop recording."
echo "[run_demo] Detach (Ctrl-b d) or Ctrl-C = FULL shutdown. Switch windows Ctrl-b 0/1/2/3 (no kill)."
tmux attach -t "$SESSION"
