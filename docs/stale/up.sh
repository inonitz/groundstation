#!/usr/bin/env bash
# Bring up the whole desk test: mock control server, then the app (dji video + mock control).
# It does NOT leave you at a blocked terminal. run_mvd.sh ends in `tmux attach`, which blocks;
# we run it under a detached pseudo-terminal so the tmux session `mvd` stays alive and this
# script returns. Attach yourself with:  tmux attach -t mvd
#
#   bash up.sh              # dji drone video + MOCK control (the desk test)
#   VIDEO=webcam bash up.sh # webcam video + MOCK control -- THE RETEST DEFAULT (owner ruling 2026-09-08):
#                           # nothing connected, no hotspot; add SCENE_TTS=off (no phone speaker)
#   SCENE_SEG=omdet MVD_TRANSLATOR=dicta bash up.sh   # the OLD pair (OmDet+SAM2.1, DictaLM on CPU); defaults are sam3 + hymt2 since 2026-09-08
#   MVD_XLATE_PORT=18092 bash up.sh                  # translator on another port (18091 held from outside the container)
#   VIDEO=webcam WEBCAM_DEV=2 bash up.sh            # the Logitech C920 (host video2); WEBCAM_DEV=0 = the laptop lid camera (black when the lid is shut)
# Defaults stay on the proven demo path (OmDet+SAM2.1, DictaLM on CPU) until the live test passes.
#
# All logs collect under one timestamped directory. `latest` always points at the newest run.
set -euo pipefail
export TZ="${TZ:-Asia/Jerusalem}"   # container is UTC; stamp sessions/clips in local time (override TZ=... if elsewhere)

VIDEO="${VIDEO:-dji}"
# Cameras plugged in AFTER the container started have no /dev/video node inside it (docker snapshots /dev; the
# container is --privileged, so we can create them): one node per host video4linux device (2026-09-08, the C920 case).
for d in /sys/class/video4linux/video*; do n="${d##*video}"; [ -e "/dev/video$n" ] || mknod "/dev/video$n" c 81 "$n" 2>/dev/null || true; done
HERE=/root/groundstation/tools/desk-test
RUNMVD=/root/groundstation/projects/integration_harden2/run_mvd.sh   # harden2 is THE system; MVD_HOME deleted (owner 2026-09-10)
MOCK=/root/groundstation/tools/dji_mock/mock_apiserver.py
# Phone IP = the WiFi gateway. Derive from the WIRELESS interface so a second (wired) default
# route cannot supply the wrong gateway. Override with PHONE_IP=<ip>.
phone_ip_wifi() {
    local i gw
    for i in $(ls /sys/class/net 2>/dev/null); do
        [ -d "/sys/class/net/$i/wireless" ] || continue
        gw=$(ip route show default dev "$i" 2>/dev/null | awk '{print $3; exit}')
        [ -n "$gw" ] && { echo "$gw"; return 0; }
    done
    return 0    # no wireless gateway -> empty output, but NEVER a non-zero status (set -e safe)
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
# Persistent dataset session folder: audio clips (ASR node) + utterances metadata (mvd)
# co-locate here. Recording is ON by default; set DESK_TEST_RECORD=0 to disable.
SESSIONS_ROOT="${MVD_SESSIONS_ROOT:-/root/groundstation/projects/integration_harden2/sessions}"
SESSION_DIR="$SESSIONS_ROOT/session-$(date +%Y%m%d-%H%M%S)-$(hostname)"
# harden2 writes ASR clips FLAT under asr_clips/ (owner ruling 2026-09-11); session_log claims from there.
CLIPS_SUB=asr_clips
mkdir -p "$SESSION_DIR/$CLIPS_SUB"
echo "[up] dataset session -> $SESSION_DIR  ($CLIPS_SUB + trace.jsonl + perception/)"

echo "[up] launching run_mvd.sh $VIDEO mock (detached) ..."
MVD_SESSION_DIR="$SESSION_DIR" ASR_RECORD="${DESK_TEST_RECORD:-1}" ASR_RECORD_DIR="$SESSION_DIR/$CLIPS_SUB" \
TMPDIR="$RUN_DIR" PHONE_IP="$PHONE_IP" setsid script -q -e \
    -c "bash $RUNMVD $VIDEO mock" "$RUN_DIR/run_mvd.console.log" </dev/null >/dev/null 2>&1 &

# 3) wait for the tmux session, then mirror each pane to its own log file (one file per component).
for _ in $(seq 1 40); do tmux has-session -t mvd 2>/dev/null && break; sleep 0.5; done
if ! tmux has-session -t mvd 2>/dev/null; then
    echo "[up] tmux session 'mvd' never appeared. See $RUN_DIR/run_mvd.console.log"; exit 1
fi
for w in vlm xlate keys asr gst dog app; do
    tmux pipe-pane -o -t "mvd:$w" "cat >> $RUN_DIR/$w.log" 2>/dev/null || true
done

# A live pane for the mock's REST commands, so the JSON is visible on screen (not just in a file).
touch "$RUN_DIR/mock_commands.log"
tmux new-window -t mvd -n mock "bash -c 'echo \"[mock] live REST commands (POST /c/fly, /c/takeoff, /c/land, /c/stop):\"; echo; tail -n +1 -F \"$RUN_DIR/mock_commands.log\"; exec bash'" 2>/dev/null || true
tmux select-window -t mvd:app 2>/dev/null || true

echo "[up] UP. session 'mvd' running video=$VIDEO control=mock(127.0.0.1:8079) seg=sam3 (Gemma reads Hebrew directly, no translator)."
echo "[up]   attach:  tmux attach -t mvd     (press F5 to talk; Ctrl-b then a window number to switch)"
echo "[up]   status:  bash $HERE/status.sh"
echo "[up]   down:    bash $HERE/down.sh"
