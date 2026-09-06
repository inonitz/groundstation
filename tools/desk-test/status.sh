#!/usr/bin/env bash
# Read the collected logs of the latest (or a given) run and print a compact status.
# Read-only. The agent reads this when the owner asks it to diagnose mid-session.
#
#   bash status.sh            # newest run
#   bash status.sh <run_dir>  # a specific run directory
set -uo pipefail
RUN_ROOT="${DESK_TEST_LOGDIR:-${TMPDIR:-/tmp}/desk-test}"
RUN_DIR="${1:-$RUN_ROOT/latest}"
[ -d "$RUN_DIR" ] || { echo "no run dir at $RUN_DIR"; exit 1; }
echo "=== desk-test status: $RUN_DIR ==="

echo "-- ports (LISTEN expected once up) --"
for pl in "18090:VLM Qwen3-VL" "18091:DictaLM" "8079:mock control" "8080:PhoneEars" "5600:gstreamer_rx"; do
    p="${pl%%:*}"; name="${pl#*:}"
    if ss -tln 2>/dev/null | grep -q ":$p "; then echo "  LISTEN  $p  $name"; else echo "  --      $p  $name (down)"; fi
done

echo "-- tmux session --"
if tmux has-session -t mvd 2>/dev/null; then
    echo "  mvd ALIVE. windows: $(tmux list-windows -t mvd -F '#{window_name}' 2>/dev/null | paste -sd, -)"
else
    echo "  mvd NOT running"
fi

sig(){ # sig <file> <label> <grep-regex>
    local f="$RUN_DIR/$1"; shift; local label="$1"; shift
    if [ -f "$f" ]; then
        local hit; hit=$(grep -aE "$*" "$f" 2>/dev/null | tail -1)
        echo "  $label: ${hit:-<none>}"
    else
        echo "  $label: <no $1>"
    fi
}

echo "-- app wiring (test point 7) --"
sig mvd_app.log "router"   "drone router (ON|DISABLED)"
sig mvd_app.log "PhoneEars" "PhoneEars|scene_omdet\] ASR"

echo "-- dicta (test point 1) --"
sig mvd_dicta.log "dicta" "listening|loaded|error|failed|HTTP"

echo "-- video (frame arrival) --"
sig gst.log "gst"  "frame|fps|EOS|error|connect"
sig dog.log "dog"  "stall|reconnect|ok|frames"

echo "-- last ASR transcripts (test point 8) --"
if [ -f "$RUN_DIR/asr.log" ]; then grep -aiE "text|transcri|heard|>" "$RUN_DIR/asr.log" 2>/dev/null | tail -5 | sed 's/^/    /' || echo "    <none>"; else echo "    <no asr.log>"; fi

echo "-- last REST commands the mock received (test points 2,4) --"
if [ -f "$RUN_DIR/mock_commands.log" ]; then tail -8 "$RUN_DIR/mock_commands.log" | sed 's/^/    /'; else echo "    <no mock_commands.log>"; fi
