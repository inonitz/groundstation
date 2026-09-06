#!/usr/bin/env bash
# Tear the desk test down cleanly and free every port. Safe to run at any time.
set -uo pipefail
echo "[down] killing named processes ..."
for name in "scene_omdet.py" "llm_to_action_asr_server" "llm_to_action_keyboard_hook" \
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
for p in 18090 18091 8079 8080 5600; do
    for pid in $(ss -tlnpH "sport = :$p" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u); do
        kill -9 "$pid" 2>/dev/null || true
    done
done
sleep 0.5
echo "[down] remaining listeners on our ports (should be empty):"
ss -tln 2>/dev/null | grep -E ':(18090|18091|8079|8080|5600) ' || echo "  none"
echo "[down] done."
