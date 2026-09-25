#!/usr/bin/env bash
# harden2 launcher -- self-contained. Brings the live stack up, tears it down, or reports status.
# No dependency on tools/desk-test. One Gemma server plans + sees + answers Hebrew; SAM3-nf4 is the
# eyes; whisper-ivrit is the ears.
#
#   bash run.sh up   [webcam|dji|rtmp] [mock|real]   # default: webcam mock
#   bash run.sh down                                  # kill the stack + free ports
#   bash run.sh status [run_dir]                      # ports, panes, last transcripts + commands
#   bash run.sh preflight [webcam|dji]                # checks only, starts nothing
#   bash run.sh score [list.md] [session]             # score a recorded session vs an e2e list -> REPORT.md
#   bash run.sh show  [session]                       # pretty-print a session's utterances
#
# SAFETY (CLAUDE.md): 'real' control is HUMAN-ONLY and prompts to confirm. The assistant runs only 'mock'.
set -euo pipefail
export TZ="${TZ:-Asia/Jerusalem}"

# ------------------------------------------------------------------ config
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$(cd "$HERE/../.." && pwd)/build/release/shared/dji/bin"
ROS_SETUP=/opt/ros/jazzy/setup.bash
SESSION=mvd
VLM_PORT=18090
OUR_PORTS=(18090 8079 8080 5600)                               # Gemma, mock, phone, gstreamer_rx
RUN_ROOT="${DESK_TEST_LOGDIR:-$(cd "$HERE/../.." && pwd)/logs/runs}"
SEG=sam3

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
    for name in "python3 -m app.main" llm_to_action_asr_server llm_to_action_keyboard_hook \
                llm_to_action_gstreamer_rx llama-server mediamtx mock_apiserver.py; do
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
    for b in llama-server llm_to_action_asr_server llm_to_action_keyboard_hook llm_to_action_gstreamer_rx; do
        [ -x "$BIN/$b" ] && _ok "$b" || _bad "$b missing in $BIN"
    done
    # Every native program loads the ggml libraries by the SAME names (libggml*.so.0), so they
    # must all point at ONE ggml version. A mix crashed Gemma on every image (2026-09-25).
    local ggml_versions
    ggml_versions="$(for l in "$BIN"/libggml*.so.0; do readlink "$l"; done | sed 's/.*\.so\.//' | sort -u)"
    if [ "$(echo "$ggml_versions" | wc -l)" = 1 ] && [ -n "$ggml_versions" ]; then
        _ok "ggml libraries: one version ($ggml_versions)"
    else
        _bad "ggml libraries mix versions: $(echo $ggml_versions) (rebuild so one build installs them all)"
    fi

    echo "== models =="
    local ASR_MODEL GEMMA_GGUF GEMMA_MMPROJ    # config/ is the one home of every path
    read -r ASR_MODEL GEMMA_GGUF GEMMA_MMPROJ < <(cd "$HERE" && python3 -c \
        'import config; print(config.ASR_MODEL_PATH, config.GEMMA_MODEL_PATH, config.GEMMA_MMPROJ_PATH)')
    [ -f "$ASR_MODEL" ] && _ok "ASR: $(basename "$ASR_MODEL")" || _bad "ASR model MISSING: $ASR_MODEL"
    local m
    for m in "$GEMMA_GGUF" "$GEMMA_MMPROJ"; do
        [ -f "$m" ] && _ok "$(basename "$m")" || _bad "model MISSING: $m"
    done
    [ -d /root/models/vision/sam3-official ] && _ok "SAM3 model dir" || _bad "SAM3 dir MISSING"
    # find_spec checks the install WITHOUT importing: importing bitsandbytes loads torch + CUDA (5-10 s)
    python3 -c "import importlib.util as u, sys; sys.exit(not all(u.find_spec(m) for m in ('bitsandbytes', 'accelerate')))" \
        && _ok "bitsandbytes + accelerate (SAM3-nf4)" \
        || _bad "bitsandbytes/accelerate missing: bash /root/groundstation/tools/devenv/install-runtime-deps.sh"

    echo "== tools =="
    local t
    for t in tmux python3 ss; do command -v "$t" >/dev/null 2>&1 && _ok "$t" || _bad "$t not installed"; done
    [ -n "${DISPLAY:-}" ] && _ok "DISPLAY=$DISPLAY" || _bad "DISPLAY unset -- the scene window needs one"

    if [ "$video" = webcam ]; then
        echo "== cameras (pick the CAPTURE line with a picture; WEBCAM_DEV=<n>) =="
        make_camera_nodes
        python3 "$HERE/video/cam_list.py" 2>/dev/null || echo "  (no camera lister)"
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
    log "logs -> $run_dir"

    # --- phone-app target ---
    local dji_host dji_port dji_real
    if [ "$control" = real ]; then
        dji_host="$(phone_ip)"; [ -n "$dji_host" ] || die "real mode needs PHONE_IP"
        dji_port=8080; dji_real=1
        cat <<BANNER
==================================================================
  REAL DRONE CONTROL -> ${dji_host}:${dji_port}
  Aircraft SECURED (clamped/held), props off for first checks.
  Kill = phone API Server toggle OFF / power button 3-5 s. YOU run this.
==================================================================
BANNER
        read -r -p "Type ARMED to proceed, anything else aborts: " confirm
        [ "$confirm" = ARMED ] || die "aborted."
    else
        dji_host=127.0.0.1; dji_port=8079; dji_real=""
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
    # the app starts every process itself (Gemma, ASR, keys, gstreamer, mock) through its supervisor

    # --- session dir (recording lands here) ---
    local session_dir="${MVD_SESSIONS_ROOT:-$(cd "$HERE/../.." && pwd)/logs/sessions}/session-$(date +%Y%m%d-%H%M%S)-$(hostname)"
    mkdir -p "$session_dir/asr_clips"
    log "session -> $session_dir"

    # --- the app pane's env, written once (one export per line, quoting-safe) ---
    # PHONE_IP means the PHONE (video + real control). Mock control is always 127.0.0.1 inside config, so
    # PHONE_IP is exported only in real mode; exporting the mock's 127.0.0.1 broke the video (review R3).
    local phone_export=""
    [ "$control" = real ] && phone_export="export PHONE_IP=$dji_host"
    local app="$run_dir/app.sh"
    cat > "$app" <<APP
#!/usr/bin/env bash
source $ROS_SETUP
cd $HERE
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export SCENE_TMUX_SESSION=$SESSION SCENE_SEG=$SEG
export TTS_OUTPUTS="${TTS_OUTPUTS-phone}"   # "" = silent; "phone,laptop" = both
export MVD_SESSION_DIR="$session_dir"
export CONTROL=$control   # config derives the phone-app target from this one decision
$phone_export
export VIDEO="$video" WEBCAM_DEV="${WEBCAM_DEV:-0}"   # config derives the source from VIDEO
export DISPLAY="${DISPLAY:-:0}" PULSE_SERVER="${PULSE_SERVER:-unix:/tmp/pulse-socket}"
sleep 3
exec python3 -m app.main
APP
    chmod +x "$app"

    # --- the tmux stack, DETACHED (this returns; the app self-tears-down on quit) ---
    # The app starts and supervises every process; each other pane only SHOWS a process log.
    tail_pane(){ tmux new-window -t "$SESSION" -n "$1" "bash -c 'touch $2; tail -n +1 -F $2; exec bash'"; }
    tmux new-session -d -s "$SESSION" -n app "bash -c '$app; echo [app exited]; exec bash'"
    tail_pane vlm "$session_dir/proc-gemma.log"
    tail_pane asr "$session_dir/proc-asr.log"
    tail_pane keys "$session_dir/proc-keys.log"
    [ "$video" = dji ] && tail_pane gst "$session_dir/proc-gstreamer.log"
    [ "$control" = mock ] && tail_pane mock "$session_dir/mock_commands.log"
    # the scripted run (SCRIPT=<file> or SCRIPT=default): fixed sentences on the ASR topic, mock only
    if [ -n "${SCRIPT:-}" ]; then
        [ "$control" = mock ] || die "SCRIPT drives commands: it runs only with control=mock"
        local script="$SCRIPT"; [ "$script" = default ] && script=""
        tmux new-window -t "$SESSION" -n feed "bash -c 'source $ROS_SETUP; cd $HERE; export CONTROL=mock; python3 -m app.feed $script; exec bash'"
    fi
    tmux select-window -t "$SESSION:app"

    # --- mirror each pane to its own log ---
    local w
    for w in app; do
        tmux pipe-pane -o -t "$SESSION:$w" "cat >> $run_dir/$w.log" 2>/dev/null || true
    done

    log "UP. video=$video control=$control dji=$dji_host:$dji_port seg=$SEG"
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
    for pl in "18090:Gemma VLM" "8079:mock control" "8080:phone speech" "5600:gstreamer_rx"; do
        p="${pl%%:*}"; name="${pl#*:}"
        if ss -tln 2>/dev/null | grep -q ":$p "; then echo "  LISTEN $p  $name"; else echo "  --     $p  $name (down)"; fi
    done
    echo "-- tmux session --"
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "  $SESSION ALIVE: $(tmux list-windows -t "$SESSION" -F '#{window_name}' 2>/dev/null | paste -sd, -)"
    else echo "  $SESSION not running"; fi
    [ -d "$run_dir" ] || { echo "(no run dir at $run_dir)"; return 0; }
    # the app writes every process log into its session dir; the run's app.sh names that dir
    local sess; sess="$(grep -o 'MVD_SESSION_DIR="[^"]*"' "$run_dir/app.sh" 2>/dev/null | cut -d'"' -f2)"
    echo "-- session: ${sess:-<unknown>} --"
    echo "-- last ASR transcripts --"
    [ -f "$sess/proc-asr.log" ] && grep -aiE "text|transcri|heard|>" "$sess/proc-asr.log" 2>/dev/null | tail -5 | sed 's/^/    /' || echo "    <none>"
    echo "-- last mock REST commands --"
    [ -f "$sess/mock_commands.log" ] && tail -8 "$sess/mock_commands.log" | sed 's/^/    /' || echo "    <none>"
    # ported from the retired tools/desk-test/status.sh
    _sig(){ local f="$run_dir/$1"; shift; local lbl="$1"; shift; if [ -f "$f" ]; then echo "  $lbl: $(grep -aE "$*" "$f" 2>/dev/null | tail -1 || echo "<none>")"; else echo "  $lbl: <no $1>"; fi; }
    echo "-- app wiring --";  _sig app.log router "drone router ON"; _sig app.log phone "\\[status\\] phone speech"
    echo "-- video --";       _sig app.log video "\\[status\\] (video|gstreamer)"
    [ -f "$sess/proc-gstreamer.log" ] && echo "  gst: $(grep -aE 'frame|fps|EOS|error|connect' "$sess/proc-gstreamer.log" | tail -1)"
    echo "-- process states (the app's status board) --"; _sig app.log last "\\[status\\]"
    echo "-- phone gate --";  local ip; ip="$(phone_ip)"; if [ -n "$ip" ]; then echo "  $ip:8080/status/ -> $(curl -s -m 3 -o /dev/null -w "%{http_code}" "http://$ip:8080/status/" 2>/dev/null || echo 000)"; else echo "  (no phone IP)"; fi
    echo "-- cameras (WEBCAM_DEV=<n>; the running app holds its own) --"; make_camera_nodes; python3 "$HERE/video/cam_list.py" 2>/dev/null || echo "  (no camera lister)"
}

# ------------------------------------------------------------------ score / show (diagnose a recorded session)
cmd_score(){  # run.sh score [list.md] [session];  SAFETY: read-only, writes REPORT.md into the session
    local list="${1:-$(cd "$HERE/../.." && pwd)/datasets/e2e/live-test-e2e-50.md}"
    python3 "$HERE/log/score.py" "$list" "${2:-}"
}
cmd_perf(){ python3 "$HERE/log/perf_report.py" "${1:-latest}"; }  # read-only: p50/p95/max per stage
cmd_show(){ python3 "$HERE/log/show.py" "${1:-latest}"; }  # read-only pretty-print

# ------------------------------------------------------------------ dispatch
cmd="${1:-up}"; shift || true
case "$cmd" in
    up)        cmd_up "$@" ;;
    down)      cmd_down ;;
    status)    cmd_status "$@" ;;
    preflight) cmd_preflight "$@" ;;
    score)     cmd_score "$@" ;;
    show)      cmd_show "$@" ;;
    perf)      cmd_perf "$@" ;;
    *) die "usage: run.sh up|down|status|preflight|score|show|perf" ;;
esac
