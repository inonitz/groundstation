#!/usr/bin/env bash
# run_fmu_mock.sh -- one-command BENCH launch of the llm_to_action C++ FMU against the local mock.
#
# SAFETY: mock-only by construction. It targets 127.0.0.1 and refuses anything else. It never
# touches a real phone/drone IP. Real-drone FMU flight is the human-only bringup path in
# docs/active/dji-bringup-runbook.md -- NOT this script.
#
#   bash scripts/run_fmu_mock.sh                 # default: --scenario-hover
#   bash scripts/run_fmu_mock.sh orbit           # --scenario-orbit
#   bash scripts/run_fmu_mock.sh follow 20        # scenario + run seconds (default 15)
#
# Scenarios: hover rotate orbit follow cross approach search  (see fmu_test_scenarios.hpp)
set -euo pipefail

SCENARIO="${1:-hover}"
SECS="${2:-15}"
ROOT=/root/groundstation
BIN="$ROOT/build/release/shared/dji/bin"
ONNX="$ROOT/build/release/shared/dji/_deps/onnxruntime/onnxruntime-linux-x64-1.20.1/lib"
MOCK="$ROOT/scripts/test/dji_mock/mock_apiserver.py"
HOST=127.0.0.1 PORT=8080     # mock only; do not change to a real IP

command -v ffplay >/dev/null 2>&1 || true
[ -x "$BIN/llm_to_action_fmu_dji" ] || { echo "FMU not built: $BIN/llm_to_action_fmu_dji"; exit 1; }
python3 -c "import aiohttp" 2>/dev/null || { echo "need aiohttp for the mock: pip install aiohttp"; exit 1; }
[ -f /opt/ros/jazzy/setup.bash ] || { echo "ROS 2 jazzy not found at /opt/ros/jazzy"; exit 1; }

# ROS setup scripts reference unbound vars; relax nounset just for the source.
set +u
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
set -u
export LD_LIBRARY_PATH="$BIN:$ONNX:${LD_LIBRARY_PATH:-}"

echo "[run_fmu_mock] starting mock on $HOST:$PORT"
python3 "$MOCK" "$HOST" "$PORT" >/tmp/fmu_mock.log 2>&1 &
MOCKPID=$!
cleanup() { kill -KILL "$MOCKPID" 2>/dev/null || true; pkill -9 -f llm_to_action_fmu_dji 2>/dev/null || true; }
trap cleanup EXIT INT TERM

for _ in $(seq 1 20); do
  curl -s -o /dev/null -w '%{http_code}' "http://$HOST:$PORT/status/" 2>/dev/null | grep -q 200 && break
  sleep 0.3
done

echo "[run_fmu_mock] FMU --scenario-$SCENARIO for ${SECS}s (mock backend, no aircraft)"
timeout "$SECS" "$BIN/llm_to_action_fmu_dji" "" "--scenario-$SCENARIO" || true
echo "[run_fmu_mock] done. mock verbs seen:"
grep -icE 'sticks raw' /tmp/fmu_mock.log | sed 's/^/  stick frames: /' || true
