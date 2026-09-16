#!/usr/bin/env bash
[ "${1:-}" = "--watch" ] && exec bash "$(dirname "$0")/../dji_mock/watch_503.sh" "${PHONE_IP:-}" "${2:-10}"   # stream the phone gate (owner ask 2026-09-08)
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
for pl in "18090:Gemma VLM" "8079:mock control" "8080:PhoneEars" "5600:gstreamer_rx"; do
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
sig mvd_app.log "PhoneEars" "PhoneEars|mvd\] ASR"


echo "-- video (frame arrival) --"
sig gst.log "gst"  "frame|fps|EOS|error|connect"
sig dog.log "dog"  "stall|reconnect|ok|frames"

echo "-- last ASR transcripts (test point 8) --"
if [ -f "$RUN_DIR/asr.log" ]; then grep -aiE "text|transcri|heard|>" "$RUN_DIR/asr.log" 2>/dev/null | tail -5 | sed 's/^/    /' || echo "    <none>"; else echo "    <no asr.log>"; fi

echo "-- last REST commands the mock received (test points 2,4) --"
if [ -f "$RUN_DIR/mock_commands.log" ]; then tail -8 "$RUN_DIR/mock_commands.log" | sed 's/^/    /'; else echo "    <no mock_commands.log>"; fi

# --- phone connection gate, one shot (owner ask 2026-09-08): 2xx ready | 503 RC/aircraft/product not connected or eco | 000 silent
PHONE_IP="${PHONE_IP:-$(ip route show default 2>/dev/null | awk '/ dev wl/ {print $3; exit}')}"
if [ -n "$PHONE_IP" ]; then
    code=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://$PHONE_IP:8080/status/" 2>/dev/null)
    echo "phone gate $PHONE_IP:8080/status/ -> ${code:-000}   (stream changes: bash $0 --watch [period_s])"
fi

# --- cameras (2026-09-08): which index is which; a running app holds its camera, so that one shows "cannot open"
echo "-- cameras (WEBCAM_DEV=<n>; the app's own camera reads 'cannot open' while it runs) --"
python3 /root/groundstation/tools/desk-test/list_cams.py
