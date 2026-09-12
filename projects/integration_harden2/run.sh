#!/usr/bin/env bash
# harden2 launcher -- self-contained. Brings the live stack up, tears it down, or reports status.
# No dependency on tools/desk-test. One Gemma server plans + sees + answers Hebrew; SAM3-nf4 is the
# eyes; whisper-ivrit is the ears.
#
#   bash run.sh up   [webcam|dji|rtmp] [mock|real]   # default: webcam mock
#   bash run.sh down                                  # kill the stack + free ports
#   bash run.sh status [run_dir]                      # ports, panes, last transcripts + commands
#   bash run.sh preflight [webcam|dji]                # checks only, starts nothing
#
# SAFETY (CLAUDE.md): 'real' control is HUMAN-ONLY and prompts to confirm. The assistant runs only 'mock'.
set -euo pipefail
export TZ="${TZ:-Asia/Jerusalem}"

# ------------------------------------------------------------------ config
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$(cd "$HERE/../.." && pwd)/build/release/shared/dji/bin"
MOCK=/root/groundstation/tools/dji_mock/mock_apiserver.py      # shared DJI API test double
ROS_SETUP=/opt/ros/jazzy/setup.bash
SESSION=mvd
VLM_PORT=18090
OUR_PORTS=(18090 8079 8080 5600)                               # Gemma, mock, phone, gstreamer_rx
RUN_ROOT="${DESK_TEST_LOGDIR:-${TMPDIR:-/tmp}/mvd-runs}"
SEG=sam3
ASR_MODEL="${ASR_MODEL_PATH:-/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_k.bin}"
ASR_BACKEND="${ASR_BACKEND:-whisper-whisper}"
ASR_LANGUAGE="${ASR_LANGUAGE:-he}"
GEMMA_GGUF=/root/models/vlm/Gemma-4-E4B/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf
GEMMA_MMPROJ=/root/models/vlm/Gemma-4-E4B/mmproj-BF16.gguf

log(){ echo "[run] $*"; }
die(){ echo "[run] ERROR: $*" >&2; exit 1; }

# ------------------------------------------------------------------ shared helpers
phone_ip(){   # the phone = the WiFi default gateway; override with PHONE_IP
    [ -n "${PHONE_IP:-}" ] && { echo "$PHONE_IP"; return; }
    local i gw
    for i in $(ls /sys/class/net 2>/dev/null); do
        [ -d "/sys/class/net/$i/wireless" ] || continue
        gw=$(ip route show default dev "$i" 2>/dev/null | awk '{print $3; exit}') || true
        [ -n "$gw" ] && { echo "$gw"; return 0; }
    done
    return 0   # no wireless gateway -> empty output, but NEVER non-zero (set -e safe)
}

make_camera_nodes(){   # a camera plugged in after the container started has no /dev node yet
    local d n
    for d in /sys/class/video4linux/video*; do
        [ -e "$d" ] || continue
        n="${d##*video}"; [ -e "/dev/video$n" ] || mknod "/dev/video$n" c 81 "$n" 2>/dev/null || true
    done
}

kill_stack(){
    local name pp
    for name in mvd.py llm_to_action_asr_server llm_to_action_keyboard_hook \
                llm_to_action_gstreamer_rx llama-server video.video_watchdog mediamtx mock_apiserver.py; do
        pkill -9 -f "$name" 2>/dev/null || true
    done
    for pp in $(tmux list-panes -s -t "$SESSION" -F '#{pane_pid}' 2>/dev/null); do
        kill -KILL -"$pp" 2>/dev/null || true   # negative PID = the whole process group
        kill -KILL  "$pp" 2>/dev/null || true
    done
    tmux kill-session -t "$SESSION" 2>/dev/null || true
}

free_ports(){
    local p pid
    for p in "${OUR_PORTS[@]}"; do
        for pid in $(ss -tlnpH "sport = :$p" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u); do
            kill -9 "$pid" 2>/dev/null || true
        done
    done
}

wait_port(){   # wait_port <port> <up|down> [tries]
    local port="$1" want="$2" tries="${3:-25}" i
    for ((i=0; i<tries; i++)); do
        if ss -tln 2>/dev/null | grep -q ":$port "; then
            [ "$want" = up ] && return 0
        else
            [ "$want" = down ] && return 0
        fi
        sleep 0.2
    done
    return 1
}

# ------------------------------------------------------------------ preflight
cmd_preflight(){
    local video="${1:-webcam}" fail=0
    local ok='  OK  ' bad='  FAIL'
    _ok(){  echo "$ok $*"; }
    _bad(){ echo "$bad $*"; fail=1; }

    echo "== ports must be FREE =="
    local p holder
    for p in "${OUR_PORTS[@]}"; do
        if ss -tln 2>/dev/null | grep -q ":$p "; then
            holder=$(ss -tlnpH "sport = :$p" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1) || true
            if [ -n "$holder" ]; then _bad "port $p in use by pid $holder -- run: bash run.sh down"
            else _bad "port $p held by a process OUTSIDE this container; on the HOST: sudo ss -tlnp | grep :$p"; fi
        else _ok "port $p free"; fi
    done

    echo "== binaries =="
    local b
    for b in llm_to_action_asr_server llm_to_action_keyboard_hook llm_to_action_gstreamer_rx; do
        [ -x "$BIN/$b" ] && _ok "$b" || _bad "$b missing in $BIN"
    done

    echo "== models =="
    [ -f "$ASR_MODEL" ] && _ok "ASR: $(basename "$ASR_MODEL")" || _bad "ASR model MISSING: $ASR_MODEL"
    local m
    for m in "$GEMMA_GGUF" "$GEMMA_MMPROJ"; do
        [ -f "$m" ] && _ok "$(basename "$m")" || _bad "model MISSING: $m"
    done
    [ -d /root/models/vision/sam3-official ] && _ok "SAM3 model dir" || _bad "SAM3 dir MISSING"
    python3 -c "import bitsandbytes, accelerate" >/dev/null 2>&1 \
        && _ok "bitsandbytes + accelerate (SAM3-nf4)" \
        || _bad "bitsandbytes/accelerate missing: bash /root/groundstation/tools/devenv/install-runtime-deps.sh"

    echo "== tools =="
    local t
    for t in tmux python3 ss; do command -v "$t" >/dev/null 2>&1 && _ok "$t" || _bad "$t not installed"; done
    [ -n "${DISPLAY:-}" ] && _ok "DISPLAY=$DISPLAY" || _bad "DISPLAY unset -- the scene window needs one"

    if [ "$video" = webcam ]; then
        echo "== cameras (pick the CAPTURE line with a picture; WEBCAM_DEV=<n>) =="
        make_camera_nodes
        python3 "$HERE/cam_list.py" 2>/dev/null || echo "  (no camera lister)"
    elif [ "$video" = dji ]; then
        echo "== phone reachable =="
        local ip code
        ip="$(phone_ip)"
        if [ -z "$ip" ]; then _bad "no phone IP (set PHONE_IP=<ip>)"
        else
            code=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://$ip:8080/status/" 2>/dev/null) || true
            echo "$code" | grep -q '^2' && _ok "phone API up at $ip:8080 ($code)" || _bad "phone $ip:8080 -> ${code:-000}; turn API Server ON"
        fi
    fi

    echo
    [ "$fail" = 0 ] && { echo "PREFLIGHT: PASS"; return 0; } || { echo "PREFLIGHT: FAIL"; return 1; }
}

# ------------------------------------------------------------------ up
cmd_up(){
    local video="${1:-webcam}" control="${2:-mock}"
    make_camera_nodes
    cmd_preflight "$video" || die "preflight failed; not booting"

    local run_dir="$RUN_ROOT/$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$run_dir"; ln -sfn "$run_dir" "$RUN_ROOT/latest"
    touch "$run_dir/mock_commands.log"
    log "logs -> $run_dir"

    # --- control wire target ---
    local wire_host wire_port wire_real
    if [ "$control" = real ]; then
        wire_host="$(phone_ip)"; [ -n "$wire_host" ] || die "real mode needs PHONE_IP"
        wire_port=8080; wire_real=1
        cat <<BANNER
==================================================================
  REAL DRONE CONTROL -> ${wire_host}:${wire_port}
  Aircraft SECURED (clamped/held), props off for first checks.
  Kill = phone API Server toggle OFF / power button 3-5 s. YOU run this.
==================================================================
BANNER
        read -r -p "Type ARMED to proceed, anything else aborts: " confirm
        [ "$confirm" = ARMED ] || die "aborted."
    else
        wire_host=127.0.0.1; wire_port=8079; wire_real=""
    fi

    # --- video source ---
    local scene_input
    case "$video" in
        webcam)      scene_input="${WEBCAM_DEV:-0}" ;;
        dji)         scene_input="ros" ;;
        rtmp|drone)  scene_input="rtsp://127.0.0.1:8554/live" ;;
        *) die "unknown video mode '$video' (webcam|dji|rtmp)" ;;
    esac

    # --- fresh slate, then the mock ---
    kill_stack; free_ports
    wait_port "$VLM_PORT" down 12 || die "port $VLM_PORT still held; see: ss -tlnp | grep $VLM_PORT"
    if [ "$control" = mock ]; then
        MOCK_CMD_LOG="$run_dir/mock_commands.log" setsid python3 "$MOCK" 127.0.0.1 8079 >"$run_dir/mock.log" 2>&1 &
        wait_port 8079 up 25 || die "mock did not bind 8079 (see $run_dir/mock.log)"
        log "mock control up on 127.0.0.1:8079"
    fi

    # --- session dir (recording lands here) ---
    local session_dir="${MVD_SESSIONS_ROOT:-$HERE/sessions}/session-$(date +%Y%m%d-%H%M%S)-$(hostname)"
    mkdir -p "$session_dir/asr_clips"
    log "session -> $session_dir"

    # --- the app pane's env, written once (one export per line, quoting-safe) ---
    local app="$run_dir/app.sh"
    cat > "$app" <<APP
#!/usr/bin/env bash
source $ROS_SETUP
cd $HERE
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export SCENE_TMUX_SESSION=$SESSION MVD_DRONE=1 SCENE_SEG=$SEG
export SCENE_TTS_LANG="${SCENE_TTS_LANG:-he}" SCENE_BG="${SCENE_BG:-off}" MVD_TTS="${MVD_TTS:-1}"
export MVD_SESSION_DIR="$session_dir"
export MVD_WIRE_HOST=$wire_host MVD_WIRE_PORT=$wire_port MVD_WIRE_REAL=$wire_real
export SCENE_INPUT="$scene_input"
export DISPLAY="${DISPLAY:-:0}" PULSE_SERVER="${PULSE_SERVER:-unix:/tmp/pulse-socket}"
sleep 3
exec python3 mvd.py
APP
    chmod +x "$app"

    # --- C++ pane command strings ---
    local ld="export LD_LIBRARY_PATH=$BIN:\$LD_LIBRARY_PATH"
    local rec="" cap=""
    [ "${ASR_RECORD:-1}" = 1 ] && rec="--record --recordDir=$session_dir/asr_clips"
    [ -n "${ASR_CAPTUREID:-}" ] && cap="--captureid=$ASR_CAPTUREID"
    local pulse="${PULSE_SERVER:-unix:/tmp/pulse-socket}"
    local phone; phone="$(phone_ip)"

    # --- the tmux stack, DETACHED (this returns; the app self-tears-down on quit) ---
    tmux new-session -d -s "$SESSION" -n vlm "bash -c '$HERE/run_llama_server.sh; echo [vlm exited]; exec bash'"
    tmux new-window -t "$SESSION" -n keys "bash -c 'source $ROS_SETUP && $ld && $BIN/llm_to_action_keyboard_hook; echo [keys exited]; exec bash'"
    tmux new-window -t "$SESSION" -n asr  "bash -c 'source $ROS_SETUP && $ld PULSE_SERVER=$pulse && $BIN/llm_to_action_asr_server --backend=$ASR_BACKEND --model=$ASR_MODEL --fa --language=$ASR_LANGUAGE --threads=1 --gid=0 $cap $rec; echo [asr exited]; exec bash'"
    if [ "$video" = dji ]; then
        tmux new-window -t "$SESSION" -n gst "bash -c 'source $ROS_SETUP && $ld && $BIN/llm_to_action_gstreamer_rx --dji $phone; echo [gst exited]; exec bash'"
        tmux new-window -t "$SESSION" -n dog "bash -c 'source $ROS_SETUP && cd $HERE && SCENE_TMUX_SESSION=$SESSION python3 -m video.video_watchdog; echo [dog exited]; exec bash'"
    fi
    tmux new-window -t "$SESSION" -n app "bash -c '$app; echo [app exited]; exec bash'"
    [ "$control" = mock ] && tmux new-window -t "$SESSION" -n mock "bash -c 'tail -n +1 -F $run_dir/mock_commands.log; exec bash'"
    tmux select-window -t "$SESSION:app"

    # --- mirror each pane to its own log ---
    local w
    for w in vlm keys asr gst dog app; do
        tmux pipe-pane -o -t "$SESSION:$w" "cat >> $run_dir/$w.log" 2>/dev/null || true
    done

    log "UP. video=$video control=$control wire=$wire_host:$wire_port seg=$SEG"
    log "  attach: tmux attach -t $SESSION     (F5 to talk; Ctrl-b then a number to switch panes)"
    log "  status: bash $HERE/run.sh status"
    log "  down:   bash $HERE/run.sh down"
}

# ------------------------------------------------------------------ down
cmd_down(){
    log "killing the stack ..."
    kill_stack
    log "freeing ports ..."
    free_ports
    sleep 0.5
    local left
    left=$(ss -tln 2>/dev/null | grep -E ":(18090|8079|8080|5600) ") || true
    [ -z "$left" ] && log "ports clear." || { echo "$left"; log "some ports still held (may be outside the container)."; }
    log "down."
}

# ------------------------------------------------------------------ status
cmd_status(){
    local run_dir="${1:-$RUN_ROOT/latest}"
    echo "=== status: $run_dir ==="
    echo "-- ports (LISTEN expected once up) --"
    local pl p name
    for pl in "18090:Gemma VLM" "8079:mock control" "8080:PhoneEars" "5600:gstreamer_rx"; do
        p="${pl%%:*}"; name="${pl#*:}"
        if ss -tln 2>/dev/null | grep -q ":$p "; then echo "  LISTEN $p  $name"; else echo "  --     $p  $name (down)"; fi
    done
    echo "-- tmux session --"
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "  $SESSION ALIVE: $(tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | paste -sd, -)"
    else echo "  $SESSION not running"; fi
    [ -d "$run_dir" ] || { echo "(no run dir at $run_dir)"; return 0; }
    echo "-- last ASR transcripts --"
    [ -f "$run_dir/asr.log" ] && grep -aiE "text|transcri|heard|>" "$run_dir/asr.log" 2>/dev/null | tail -5 | sed 's/^/    /' || echo "    <none>"
    echo "-- last mock REST commands --"
    [ -f "$run_dir/mock_commands.log" ] && tail -8 "$run_dir/mock_commands.log" | sed 's/^/    /' || echo "    <none>"
}

# ------------------------------------------------------------------ dispatch
cmd="${1:-up}"; shift || true
case "$cmd" in
    up)        cmd_up "$@" ;;
    down)      cmd_down ;;
    status)    cmd_status "$@" ;;
    preflight) cmd_preflight "$@" ;;
    *) die "usage: run.sh up|down|status|preflight" ;;
esac
