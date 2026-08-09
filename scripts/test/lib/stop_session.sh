#!/bin/bash
# stop_session.sh -- the safe way to end a manually-attended test.
#
# Stops any live ros2 bag recorder gracefully FIRST (SIGINT, then waits for it to actually
# exit so metadata.yaml finalizes), THEN ends the tmux session. Use this instead of
# `:kill-session` or closing the terminal -- see
# docs/active/2026-08-09-wave1-testing-runbook.md for exactly why those lose the bag:
# tmux kill-session sends SIGHUP to every pane, and `ros2 bag record` does not handle
# SIGHUP gracefully (dies immediately, no finalization). Confirmed against the real binary.
#
# Usage: scripts/test/lib/stop_session.sh [SESSION_NAME]   (default: llmsim)
#
# Caveat: if more than one test session is recording a bag at once, `pgrep` may match more
# than one process; this takes the most-recently-started one. Fine for the normal one-test-
# at-a-time workflow; not safe to assume for concurrent runs.
set -uo pipefail
SESSION="${1:-llmsim}"

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[stop_session] no tmux session '$SESSION' -- nothing to stop."
    exit 0
fi

echo "[stop_session] looking for a live bag recorder..."
BAGPID=$(pgrep -f "ros2 bag record" | tail -1)
if [ -n "$BAGPID" ]; then
    echo "[stop_session] found bag recorder pid=$BAGPID -- sending SIGINT and waiting for it to finalize..."
    kill -INT "$BAGPID" 2>/dev/null
    for i in $(seq 1 20); do
        kill -0 "$BAGPID" 2>/dev/null || { echo "[stop_session] bag recorder exited cleanly after ~$((i * 500))ms"; break; }
        sleep 0.5
    done
    if kill -0 "$BAGPID" 2>/dev/null; then
        echo "[stop_session] WARNING: bag recorder still alive after 10s -- it may not finalize cleanly. Investigate before trusting this bag."
    fi
else
    echo "[stop_session] no live bag recorder found (already stopped, or this run had none)."
fi

echo "[stop_session] ending tmux session '$SESSION'..."
tmux kill-session -t "$SESSION" 2>/dev/null
echo "[stop_session] done."
