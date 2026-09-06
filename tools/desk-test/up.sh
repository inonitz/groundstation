#!/usr/bin/env bash
# Bring up the whole desk test: mock control server, then the app (dji video + mock control).
# It does NOT leave you at a blocked terminal. run_mvd.sh ends in `tmux attach`, which blocks;
# we run it under a detached pseudo-terminal so the tmux session `mvd` stays alive and this
# script returns. Attach yourself with:  tmux attach -t mvd
#
#   bash up.sh              # dji drone video + MOCK control (the desk test)
#   VIDEO=webcam bash up.sh # webcam video + MOCK control
#
# All logs collect under one timestamped directory. `latest` always points at the newest run.
set -euo pipefail

VIDEO="${VIDEO:-dji}"
HERE=/root/groundstation/tools/desk-test
RUNMVD=/root/groundstation/projects/integration_harden/run_mvd.sh
MOCK=/root/groundstation/tools/dji_mock/mock_apiserver.py
# Phone IP = the WiFi gateway. Derive from the WIRELESS interface so a second (wired) default
# route cannot supply the wrong gateway. Override with PHONE_IP=<ip>.
phone_ip_wifi() {
    local i gw
    for i in $(ls /sys/class/net 2>/dev/null); do
        [ -d "/sys/class/net/$i/wireless" ] || continue
        gw=$(ip route show default dev "$i" 2>/dev/null | awk '{print $3; exit}')
        [ -n "$gw" ] && { echo "$gw"; return; }
    done
}
PHONE_IP="${PHONE_IP:-$(phone_ip_wifi)}"

RUN_ROOT="${DESK_TEST_LOGDIR:-${TMPDIR:-/tmp}/desk-test}"
RUN_DIR="$RUN_ROOT/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RUN_DIR"
ln -sfn "$RUN_DIR" "$RUN_ROOT/latest"
echo "[up] logs -> $RUN_DIR   (latest -> $RUN_ROOT/latest)"

echo "[up] preflight..."
VIDEO="$VIDEO" PHONE_IP="$PHONE_IP" bash "$HERE/preflight.sh" || { echo "[up] preflight FAILED. Not booting."; exit 1; }

# 1) mock control on 127.0.0.1:8079, recording every REST command into the run dir.
echo "[up] starting mock control on 127.0.0.1:8079 ..."
MOCK_CMD_LOG="$RUN_DIR/mock_commands.log" setsid python3 "$MOCK" 127.0.0.1 8079 >"$RUN_DIR/mock.log" 2>&1 &
for _ in $(seq 1 25); do ss -tln 2>/dev/null | grep -q "127.0.0.1:8079" && break; sleep 0.2; done
ss -tln 2>/dev/null | grep -q "127.0.0.1:8079" || { echo "[up] mock did not bind 8079. See $RUN_DIR/mock.log"; exit 1; }
echo "[up] mock up. commands -> $RUN_DIR/mock_commands.log"

# 2) the app via run_mvd.sh, under a detached pty so its final `tmux attach` does not block us
#    and its EXIT-trap cleanup does not fire. TMPDIR points its app/dicta logs into the run dir.
# Persistent dataset session folder: audio clips (ASR node) + utterances metadata (scene_omdet)
# co-locate here. Recording is ON by default; set DESK_TEST_RECORD=0 to disable.
SESSIONS_ROOT="${MVD_SESSIONS_ROOT:-/root/groundstation/projects/integration_harden/sessions}"
SESSION_DIR="$SESSIONS_ROOT/session-$(date +%Y%m%d-%H%M%S)-$(hostname)"
mkdir -p "$SESSION_DIR/clips"
echo "[up] dataset session -> $SESSION_DIR  (utterances.jsonl + clips/*.wav)"

echo "[up] launching run_mvd.sh $VIDEO mock (detached) ..."
MVD_SESSION_DIR="$SESSION_DIR" ASR_RECORD="${DESK_TEST_RECORD:-1}" ASR_RECORD_DIR="$SESSION_DIR/clips" \
TMPDIR="$RUN_DIR" PHONE_IP="$PHONE_IP" setsid script -q -e \
    -c "bash $RUNMVD $VIDEO mock" "$RUN_DIR/run_mvd.console.log" </dev/null >/dev/null 2>&1 &

# 3) wait for the tmux session, then mirror each pane to its own log file (one file per component).
for _ in $(seq 1 40); do tmux has-session -t mvd 2>/dev/null && break; sleep 0.5; done
if ! tmux has-session -t mvd 2>/dev/null; then
    echo "[up] tmux session 'mvd' never appeared. See $RUN_DIR/run_mvd.console.log"; exit 1
fi
for w in vlm dicta keys asr gst dog app; do
    tmux pipe-pane -o -t "mvd:$w" "cat >> $RUN_DIR/$w.log" 2>/dev/null || true
done

# A live pane for the mock's REST commands, so the JSON is visible on screen (not just in a file).
touch "$RUN_DIR/mock_commands.log"
tmux new-window -t mvd -n mock "bash -c 'echo \"[mock] live REST commands (POST /c/fly, /c/takeoff, /c/land, /c/stop):\"; echo; tail -n +1 -F \"$RUN_DIR/mock_commands.log\"; exec bash'" 2>/dev/null || true
tmux select-window -t mvd:app 2>/dev/null || true

echo "[up] UP. session 'mvd' running video=$VIDEO control=mock(127.0.0.1:8079)."
echo "[up]   attach:  tmux attach -t mvd     (press H to talk; Ctrl-b then a window number to switch)"
echo "[up]   status:  bash $HERE/status.sh"
echo "[up]   down:    bash $HERE/down.sh"
