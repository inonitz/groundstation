#!/usr/bin/env bash
# Tear the desk test down cleanly and free every port. Safe to run at any time.
set -uo pipefail
echo "[down] killing named processes ..."
for name in "mvd.py" "llm_to_action_asr_server" "llm_to_action_keyboard_hook" \
            "llm_to_action_gstreamer_rx" "llama-server" "video.video_watchdog" \
            "mediamtx" "mock_apiserver.py"; do
    pkill -9 -f "$name" 2>/dev/null || true
done
echo "[down] killing tmux session 'mvd' ..."
# kill each pane's whole process group first (catches double-forked llama-server/gst)
for pp in $(tmux list-panes -s -t mvd -F '#{pane_pid}' 2>/dev/null); do
    kill -KILL -"$pp" 2>/dev/null || true
    kill -KILL  "$pp" 2>/dev/null || true
done
tmux kill-session -t mvd 2>/dev/null || true
echo "[down] freeing ports ..."
XLATE_PORT="${MVD_XLATE_PORT:-18091}"
for p in 18090 $XLATE_PORT 8079 8080 5600; do
    for pid in $(ss -tlnpH "sport = :$p" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u); do
        kill -9 "$pid" 2>/dev/null || true
    done
done
sleep 0.5
echo "[down] remaining listeners on our ports (should be empty):"
left=$(ss -tln 2>/dev/null | grep -E ":(18090|$XLATE_PORT|8079|8080|5600) ")
if [ -z "$left" ]; then echo "  none"; else
    echo "$left"
    for p in 18090 $XLATE_PORT 8079 8080 5600; do
        if ss -tln 2>/dev/null | grep -q ":$p " && ! ss -tlnpH "sport = :$p" 2>/dev/null | grep -q 'pid='; then
            uid=$(awk -v hp=$(printf '%04X' $p) '$2 ~ ":"hp"$" && $4=="0A" {print $8; exit}' /proc/net/tcp)
            echo "  port $p is held by a process OUTSIDE this container (uid ${uid:-?}). This script cannot kill it."
            echo "  On the HOST run:  sudo ss -tlnp | grep :$p   and kill that pid; or boot with MVD_XLATE_PORT=18092."
        fi
    done
fi
echo "[down] done."
