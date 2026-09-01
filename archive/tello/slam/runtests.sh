#!/bin/bash
# Compile + run every hardware-free SLAM unit test in one shot, and report PASS/FAIL.
# These are the "prove the math before the drone" tests -- no ROS, no Gazebo, no Tello.
#
# Usage:  ./runtests.sh
# Exit code is 0 only if ALL tests pass, so CI / a human can gate on it.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"

# util2 headers live under a fetched dep; find one include root (any shared tree works).
UTIL2_INC="$(find "$ROOT/build" -path '*util2/include/util2/C/base_type.h' 2>/dev/null \
             | head -1 | sed 's#/util2/C/base_type.h##')"
if [ -z "$UTIL2_INC" ]; then
    echo "[ERROR] util2 include not found under build/ -- configure any tree once first."
    exit 1
fi

INC=(-Isource/llm_to_action -Isource -Isource/slam -I"$UTIL2_INC")
TESTS=(
    "source/slam/test/slam_pose_bridge_test.cpp"
    "source/slam/test/slam_recovery_fsm_test.cpp"
    "source/slam/test/hover_hold_control_test.cpp"
    "source/slam/test/hover_hold_sim_test.cpp"
)

cd "$ROOT" || exit 1
pass=0; fail=0
echo "=================================================================="
echo " SLAM offline unit tests"
echo "=================================================================="
for src in "${TESTS[@]}"; do
    name="$(basename "$src" .cpp)"
    bin="/tmp/slam_ut_${name}"
    if ! g++ -std=c++17 "${INC[@]}" "$src" -o "$bin" 2>/tmp/slam_ut_err; then
        echo "[FAIL] $name -- did not COMPILE:"; sed 's/^/    /' /tmp/slam_ut_err | head -8
        fail=$((fail+1)); continue
    fi
    if out="$("$bin" 2>&1)"; then
        echo "[PASS] $out"
        pass=$((pass+1))
    else
        echo "[FAIL] $name -- test asserted:"; echo "$out" | sed 's/^/    /'
        fail=$((fail+1))
    fi
done
echo "------------------------------------------------------------------"
echo " result: $pass passed, $fail failed"
echo "=================================================================="
[ "$fail" -eq 0 ]
