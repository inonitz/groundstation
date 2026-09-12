#!/usr/bin/env bash
# MVD launcher: perception + English ASR + the 4-tier command router, one command, tmux panes.
# ENABLES the in-process drone router (MVD_DRONE=1) and adds a
# raw-H.264-over-TCP:5600 drone-video fast path (~320 ms, vs slow RTMP).
#
#   bash run_mvd.sh                      # webcam video + MOCK control (safe desk test)
#   bash run_mvd.sh dji                  # drone raw-H.264 video + MOCK control
#   bash run_mvd.sh dji real            # drone video + REAL drone control  (HUMAN-ONLY; asks to confirm)
#   bash run_mvd.sh webcam real         # webcam video + REAL drone         (HUMAN-ONLY)
#   PHONE_IP=$(ip route | awk '/^default/{print $3}') bash run_mvd.sh dji real   # the phone = the hotspot gateway; its IP changes per hotspot session
#
# MOCK control expects the mock on 127.0.0.1:8079 (8080 = real drone / host process; VLM now on 18090):
#   python3 /root/groundstation/tools/dji_mock/mock_apiserver.py 127.0.0.1 8079
#
# SAFETY (CLAUDE.md): the ASSISTANT never runs this against a real drone. In `real` mode a HUMAN
# runs it, the aircraft must be SECURED, and the kill is the phone toggle / power button.
set -euo pipefail
VIDEO="${1:-webcam}"          # webcam | dji | rtmp
CONTROL="${2:-mock}"          # mock | real
SESSION=mvd
HERE="$(cd "$(dirname "$0")" && pwd)"
SCENE="$(cd "$(dirname "$0")" && pwd)"
BIN="$(cd "$(dirname "$0")/../.." && pwd)"/build/release/shared/dji/bin
# ASR: Hebrew whisper by default (desk test). Backend/language/model are env-overridable so
# English can be restored WITHOUT editing this file:
#   ASR_BACKEND=whisper-parakeet ASR_LANGUAGE=en \
#   ASR_MODEL_PATH=/root/models/asr/nvidia--parakeet-tdt-0.6b-v3/ggml-parakeet-tdt-0.6b-v3-q4_k.bin bash run_mvd.sh ...
# The default model is produced by tools/desk-test/quantize_hebrew_asr.sh (see the desk-test report).
ASR_MODEL="${ASR_MODEL_PATH:-/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_k.bin}"
ASR_BACKEND="${ASR_BACKEND:-whisper-whisper}"
ASR_LANGUAGE="${ASR_LANGUAGE:-he}"
# Session folder (trace.jsonl + asr_clips/ + perception/): up.sh passes MVD_SESSION_DIR; a direct run (dji real, 2026-09-09 block C)
# makes its own so the take is recorded the same way. `set -u` made the old bare $MVD_SESSION_DIR abort the real run.
MVD_SESSION_DIR="${MVD_SESSION_DIR:-$HERE/sessions/session-$(date +%Y%m%d-%H%M%S)-$(hostname)}"
mkdir -p "$MVD_SESSION_DIR/asr_clips"
ASR_RECORD="${ASR_RECORD:-1}"                 # 1 = save each utterance as a .wav (dataset); default ON since 2026-09-09
ASR_RECORD_DIR="${ASR_RECORD_DIR:-$MVD_SESSION_DIR/asr_clips}"   # clip output dir (up.sh points this at the session folder)
# One Gemma server does planning + vision + Hebrew answers (run_llama_server.sh); there is NO translator
# (Gemma reads the Hebrew directly). The highlight backend is SAM3: one nf4 forward gives boxes + masks.
SEG=sam3
ROS_SETUP=/opt/ros/jazzy/setup.bash
APP_LAUNCH="${TMPDIR:-/tmp}/mvd_app_launch.sh"

# --- phone IP: the WiFi default gateway (override with PHONE_IP) --------------------------------
PHONE_IP="${PHONE_IP:-$(ip route 2>/dev/null | awk '/^default/{print $3; exit}')}"

# --- video source (no spaces reach the export chain; the pipeline goes in a temp script) --------
case "$VIDEO" in
    webcam) SCENE_INPUT_VAL="${WEBCAM_DEV:-0}" ;;   # WEBCAM_DEV=2 = the Logitech C920 (host video2); 0 = the laptop lid camera (2026-09-08)
    dji)    SCENE_INPUT_VAL="ros" ;;   # gstreamer_rx receives :5600 -> publishes camera/stream -> CameraStream subscribes
    rtmp|drone) SCENE_INPUT_VAL="rtsp://127.0.0.1:8554/live" ;;
    *) echo "unknown video mode '$VIDEO' (webcam|dji|rtmp)"; exit 1 ;;
esac

# --- control wire target -----------------------------------------------------------------------
if [ "$CONTROL" = "real" ]; then
    [ -n "$PHONE_IP" ] || { echo "real mode needs PHONE_IP (no default route found)"; exit 1; }
    WIRE_HOST="$PHONE_IP"; WIRE_PORT=8080; WIRE_REAL=1
    cat <<BANNER
==================================================================
  REAL DRONE CONTROL ARMED PATH -> ${WIRE_HOST}:${WIRE_PORT}
  Before continuing (kill-switch-verification.md):
   - Aircraft SECURED (clamped/held in open space), props off for first checks.
   - Phone API Server ON; you can hit the power button (3-5s) to kill.
   - You, the human, are running this. Voice verbs WILL move the aircraft.
==================================================================
BANNER
    read -r -p "Type ARMED to proceed, anything else aborts: " CONFIRM
    [ "$CONFIRM" = "ARMED" ] || { echo "aborted."; exit 1; }
else
    WIRE_HOST=127.0.0.1; WIRE_PORT=8079; WIRE_REAL=""
    echo "[run_mvd] MOCK control -> 127.0.0.1:8079. Start it in another shell if not up:"
    echo "         python3 /root/groundstation/tools/dji_mock/mock_apiserver.py 127.0.0.1 8079"
fi

STACK_PATTERNS=(llama-server llm_to_action_asr_server llm_to_action_keyboard_hook mvd.py llm_to_action_gstreamer_rx)

kill_stack() {
    pkill -9 -x mediamtx 2>/dev/null || true
    for pat in "${STACK_PATTERNS[@]}"; do pkill -9 -f "$pat" 2>/dev/null || true; done
}

free_vlm_port() {
    local pid
    pid=$(ss -tlnpH "sport = :18090" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1) || true   # no match under set -e must not kill the script
    [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null || true
}

cleanup() {
    for pp in $(tmux list-panes -s -t "$SESSION" -F '#{pane_pid}' 2>/dev/null); do
        kill -KILL -"$pp" 2>/dev/null || true   # negative PID = the whole process group
        kill -KILL  "$pp" 2>/dev/null || true
    done
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    kill_stack
    free_vlm_port
}
trap cleanup EXIT INT TERM

command -v tmux >/dev/null 2>&1 || { echo "tmux not installed"; exit 1; }
[ -x "$BIN/llm_to_action_keyboard_hook" ] || echo "[run_mvd] WARN: keyboard_hook not built -- F5 push-to-talk won't work."
[ -x "$BIN/llm_to_action_asr_server" ]    || echo "[run_mvd] WARN: asr_server not built -- voice off (vision still works)."
[ -f "$ASR_MODEL" ]                       || echo "[run_mvd] WARN: ASR model missing: $ASR_MODEL"

# fresh start -- SIGKILL survivors (a GPU-busy llama-server ignores SIGTERM) and WAIT for :18090 to clear
tmux kill-session -t "$SESSION" 2>/dev/null || true
kill_stack
free_vlm_port
for _i in $(seq 1 12); do ss -tln 2>/dev/null | grep -q "127.0.0.1:18090" || break; sleep 0.5; done
if ss -tln 2>/dev/null | grep -q "127.0.0.1:18090"; then
    echo "[run_mvd] WARN: VLM port 18090 is held by another process -- llama-server cannot bind."
    echo "[run_mvd]   ss -tlnp | grep 18090   to see who; if it is a stray llama-server: kill -9 <PID>."
    echo "[run_mvd]   else set SCENE_LLAMA_PORT + SCENE_LLAMA_URL to a free port and re-run."
    exit 1
fi

# app launch script: all env (incl. the spaced GStreamer pipeline) lives here, quoting-safe.
cat > "$APP_LAUNCH" <<APPEOF
#!/usr/bin/env bash
source $ROS_SETUP
cd $HERE
export HF_HUB_OFFLINE=1          # transformers/ultralytics load from /root/models cache; never touch the hub
export TRANSFORMERS_OFFLINE=1  # (the phone hotspot has no internet -> a fetch = 'connection reset')
export SCENE_TMUX_SESSION=$SESSION
export MVD_DRONE=1
export SCENE_SEG=$SEG                     # SAM3 highlight backend
export SCENE_TTS_LANG="${SCENE_TTS_LANG:-he}"   # owner ruling 2026-09-08: Hebrew answers straight to the phone TTS
export SCENE_BG="${SCENE_BG:-off}"        # harden2: YOLO OFF by default (owner ruling 2026-09-08, saves 282 MiB); SCENE_BG=/root/models/vision/yolo26n-seg.pt turns the grey squares back on
export MVD_SESSION_DIR=$MVD_SESSION_DIR   # session folder: trace.jsonl + asr_clips/ (C++ ASR writes wavs) + perception/
export MVD_WIRE_HOST=$WIRE_HOST
export MVD_WIRE_PORT=$WIRE_PORT
export MVD_WIRE_REAL=$WIRE_REAL
export SCENE_INPUT="$SCENE_INPUT_VAL"
export DISPLAY="${DISPLAY:-:0}"
export PULSE_SERVER="${PULSE_SERVER:-unix:/tmp/pulse-socket}"
sleep 3
python3 mvd.py 2>&1 | tee ${TMPDIR:-/tmp}/mvd_app.log; echo "[app exit=$?]" | tee -a ${TMPDIR:-/tmp}/mvd_app.log
APPEOF
chmod +x "$APP_LAUNCH"

RTMP=0
[ "$VIDEO" = "rtmp" ] || [ "$VIDEO" = "drone" ] && RTMP=1
if [ "$RTMP" = "1" ]; then
    command -v mediamtx >/dev/null 2>&1 || { echo "mediamtx not installed (rtmp mode)"; exit 1; }
    IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || hostname -I | awk '{print $1}')
    echo " DJI Fly -> Live -> Custom RTMP:  rtmp://${IP}:1935/live  (Go Live AFTER app says waiting)"
fi

CMD_KEYS="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH && $BIN/llm_to_action_keyboard_hook"
# Capture device: system DEFAULT mic unless ASR_CAPTUREID is set (owner ruling 2026-09-04).
ASR_CAPTURE_ARG=""
[ -n "${ASR_CAPTUREID:-}" ] && ASR_CAPTURE_ARG="--captureid=$ASR_CAPTUREID"
ASR_RECORD_ARG=""
[ "$ASR_RECORD" = "1" ] && ASR_RECORD_ARG="--record --recordDir=$ASR_RECORD_DIR"
CMD_ASR="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH PULSE_SERVER=${PULSE_SERVER:-unix:/tmp/pulse-socket} && $BIN/llm_to_action_asr_server --backend=$ASR_BACKEND --model=$ASR_MODEL --fa --language=$ASR_LANGUAGE --threads=1 --gid=0 $ASR_CAPTURE_ARG $ASR_RECORD_ARG"
CMD_GST="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH && $BIN/llm_to_action_gstreamer_rx --dji $PHONE_IP"

tmux new-session -d -s "$SESSION" -n vlm "bash -c '$SCENE/run_llama_server.sh; echo [vlm exited]; exec bash'"
[ "$RTMP" = "1" ] && tmux new-window -t "$SESSION" -n rtmp "bash -c 'mediamtx; echo [rtmp exited]; exec bash'"
tmux new-window -t "$SESSION" -n keys "bash -c '$CMD_KEYS; echo [keys exited]; exec bash'"
tmux new-window -t "$SESSION" -n asr  "bash -c '$CMD_ASR; echo [asr exited]; exec bash'"
[ "$VIDEO" = "dji" ] && tmux new-window -t "$SESSION" -n gst  "bash -c '$CMD_GST; echo [gst exited]; exec bash'" || true   # sole :5600 receiver -> camera/stream
[ "$VIDEO" = "dji" ] && tmux new-window -t "$SESSION" -n dog  "bash -c 'source $ROS_SETUP && cd $HERE && SCENE_TMUX_SESSION=$SESSION python3 -m video.video_watchdog; echo [watchdog exited]; exec bash'" || true   # detect stall -> notify + auto-reconnect gst
tmux new-window -t "$SESSION" -n app  "bash -c '$APP_LAUNCH; echo [app exited]; exec bash'"
tmux select-window -t "$SESSION:app"
echo "[run_mvd] up: video=$VIDEO control=$CONTROL wire=$WIRE_HOST:$WIRE_PORT seg=$SEG. Ctrl-b then 0-4 to switch panes."
echo "[run_mvd] press F5 to talk (F5, speak, F5). Verbs: takeoff/land/go up|down|forward|back|left|right/spin/stop/manual/resume."
echo "[run_mvd] questions ('what do you see', 'highlight the red backpack') -> perception. Ctrl-C = full shutdown."
tmux bind-key -T prefix k kill-session -t "$SESSION"
tmux attach -t "$SESSION"
