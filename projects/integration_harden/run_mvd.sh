#!/usr/bin/env bash
# MVD launcher: perception + English ASR + the 4-tier command router, one command, tmux panes.
# Builds on run_scene_omdet.sh but ENABLES the in-process drone router (MVD_DRONE=1) and adds a
# raw-H.264-over-TCP:5600 drone-video fast path (~320 ms, vs slow RTMP).
#
#   bash run_mvd.sh                      # webcam video + MOCK control (safe desk test)
#   bash run_mvd.sh dji                  # drone raw-H.264 video + MOCK control
#   bash run_mvd.sh dji real            # drone video + REAL drone control  (HUMAN-ONLY; asks to confirm)
#   bash run_mvd.sh webcam real         # webcam video + REAL drone         (HUMAN-ONLY)
#   PHONE_IP=10.222.215.92 bash run_mvd.sh dji real
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
ASR_MODEL="${ASR_MODEL_PATH:-/root/models/asr/nvidia--parakeet-tdt-0.6b-v3/ggml-parakeet-tdt-0.6b-v3-q4_k.bin}"
ROS_SETUP=/opt/ros/jazzy/setup.bash
APP_LAUNCH="${TMPDIR:-/tmp}/mvd_app_launch.sh"

# --- phone IP: the WiFi default gateway (override with PHONE_IP) --------------------------------
PHONE_IP="${PHONE_IP:-$(ip route 2>/dev/null | awk '/^default/{print $3; exit}')}"

# --- video source (no spaces reach the export chain; the pipeline goes in a temp script) --------
case "$VIDEO" in
    webcam) SCENE_INPUT_VAL="0" ;;
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

cleanup() {
    # 1. SIGKILL each tmux pane's whole PROCESS GROUP -- catches double-forked children
    #    (llama-server, gst) that plain kill-session (SIGHUP) leaves orphaned holding ports.
    for pp in $(tmux list-panes -s -t "$SESSION" -F '#{pane_pid}' 2>/dev/null); do
        kill -KILL -"$pp" 2>/dev/null || true   # negative PID = the process group
        kill -KILL  "$pp" 2>/dev/null || true
    done
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    # 2. belt-and-suspenders by name, -9 so a GPU-busy llama-server cannot ignore it
    pkill -9 -x mediamtx                      2>/dev/null || true
    pkill -9 -f "llama-server"                2>/dev/null || true
    pkill -9 -f "llm_to_action_asr_server"    2>/dev/null || true
    pkill -9 -f "llm_to_action_keyboard_hook" 2>/dev/null || true
    pkill -9 -f "scene_omdet.py"              2>/dev/null || true
    pkill -9 -f "llm_to_action_gstreamer_rx"  2>/dev/null || true
    # 3. authoritative free of :18090 (VLM) -- no fuser needed: socket inode -> owning pid -> SIGKILL
    python3 - <<'DOC' 2>/dev/null || true
import glob, os, signal
ino=set()
for f in ("/proc/net/tcp","/proc/net/tcp6"):
    try:
        for r in open(f).read().splitlines()[1:]:
            c=r.split()
            if len(c)>9 and c[1].upper().endswith(":46AA") and c[3]=="0A": ino.add(c[9])  # 18090 LISTEN
    except Exception: pass
for fd in glob.glob("/proc/[0-9]*/fd/*"):
    try:
        l=os.readlink(fd)
        if l.startswith("socket:") and l.split("[")[1].rstrip("]") in ino:
            os.kill(int(fd.split("/")[2]), signal.SIGKILL)
    except Exception: pass
DOC
}
trap cleanup EXIT INT TERM

command -v tmux >/dev/null 2>&1 || { echo "tmux not installed"; exit 1; }
[ -x "$BIN/llm_to_action_keyboard_hook" ] || echo "[run_mvd] WARN: keyboard_hook not built -- H toggle won't work."
[ -x "$BIN/llm_to_action_asr_server" ]    || echo "[run_mvd] WARN: asr_server not built -- voice off (vision still works)."
[ -f "$ASR_MODEL" ]                       || echo "[run_mvd] WARN: ASR model missing: $ASR_MODEL"

# fresh start -- SIGKILL survivors (a GPU-busy llama-server ignores SIGTERM) and WAIT for :18090 to clear
tmux kill-session -t "$SESSION" 2>/dev/null || true
pkill -9 -x mediamtx                      2>/dev/null || true
pkill -9 -f "llama-server"                2>/dev/null || true
pkill -9 -f "llm_to_action_asr_server"    2>/dev/null || true
pkill -9 -f "llm_to_action_keyboard_hook" 2>/dev/null || true
pkill -9 -f "scene_omdet.py"              2>/dev/null || true
pkill -9 -f "llm_to_action_gstreamer_rx"  2>/dev/null || true
python3 - <<'DOC' 2>/dev/null || true
import glob, os, signal
ino=set()
for f in ("/proc/net/tcp","/proc/net/tcp6"):
    try:
        for r in open(f).read().splitlines()[1:]:
            c=r.split()
            if len(c)>9 and c[1].upper().endswith(":46AA") and c[3]=="0A": ino.add(c[9])
    except Exception: pass
for fd in glob.glob("/proc/[0-9]*/fd/*"):
    try:
        l=os.readlink(fd)
        if l.startswith("socket:") and l.split("[")[1].rstrip("]") in ino:
            os.kill(int(fd.split("/")[2]), signal.SIGKILL)
    except Exception: pass
DOC
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
export HF_HUB_OFFLINE=1          # OmDet/transformers load from /root/models cache; never touch the hub
export TRANSFORMERS_OFFLINE=1  # (the phone hotspot has no internet -> a fetch = 'connection reset')
export SCENE_TMUX_SESSION=$SESSION
export MVD_DRONE=1
export SCENE_SAM2=/root/models/vision/sam2.1_b.pt
export MVD_WIRE_HOST=$WIRE_HOST
export MVD_WIRE_PORT=$WIRE_PORT
export MVD_WIRE_REAL=$WIRE_REAL
export SCENE_INPUT="$SCENE_INPUT_VAL"
export DISPLAY="${DISPLAY:-:0}"
export PULSE_SERVER="${PULSE_SERVER:-unix:/tmp/pulse-socket}"
sleep 3
python3 scene_omdet.py 2>&1 | tee ${TMPDIR:-/tmp}/mvd_app.log; echo "[app exit=$?]" | tee -a ${TMPDIR:-/tmp}/mvd_app.log
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
CMD_ASR="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH PULSE_SERVER=${PULSE_SERVER:-unix:/tmp/pulse-socket} && $BIN/llm_to_action_asr_server --backend=whisper-parakeet --model=$ASR_MODEL --fa --language=en --threads=1 --gid=0 --captureid=${ASR_CAPTUREID:-1}"
CMD_GST="source $ROS_SETUP && export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH && $BIN/llm_to_action_gstreamer_rx --dji $PHONE_IP"

tmux new-session -d -s "$SESSION" -n vlm "bash -c '$SCENE/run_llama_server.sh; echo [vlm exited]; exec bash'"
[ "$RTMP" = "1" ] && tmux new-window -t "$SESSION" -n rtmp "bash -c 'mediamtx; echo [rtmp exited]; exec bash'"
tmux new-window -t "$SESSION" -n keys "bash -c '$CMD_KEYS; echo [keys exited]; exec bash'"
tmux new-window -t "$SESSION" -n asr  "bash -c '$CMD_ASR; echo [asr exited]; exec bash'"
[ "$VIDEO" = "dji" ] && tmux new-window -t "$SESSION" -n gst  "bash -c '$CMD_GST; echo [gst exited]; exec bash'" || true   # sole :5600 receiver -> camera/stream
[ "$VIDEO" = "dji" ] && tmux new-window -t "$SESSION" -n dog  "bash -c 'source $ROS_SETUP && cd $HERE && SCENE_TMUX_SESSION=$SESSION python3 -m video.video_watchdog; echo [watchdog exited]; exec bash'" || true   # detect stall -> notify + auto-reconnect gst
tmux new-window -t "$SESSION" -n app  "bash -c '$APP_LAUNCH; echo [app exited]; exec bash'"
tmux select-window -t "$SESSION:app"
echo "[run_mvd] up: video=$VIDEO control=$CONTROL wire=$WIRE_HOST:$WIRE_PORT. Ctrl-b then 0-4 to switch panes."
echo "[run_mvd] press H to talk. Verbs: takeoff/land/go up|down|forward|back|left|right/spin/stop/manual/resume."
echo "[run_mvd] questions ('what do you see', 'highlight the red backpack') -> perception. Ctrl-C = full shutdown."
tmux bind-key -T prefix k kill-session -t "$SESSION"
tmux attach -t "$SESSION"
