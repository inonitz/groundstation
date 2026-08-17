#!/bin/bash
# Voice / emergency-fastpath unit tests -- headless, no sim, ~20s total.
# Runs the FMU binary with canned flags and checks the log. Run:  scripts/test/voice_unit.sh
cd "$(dirname "$0")/../.." || exit 1
BIN="build/release/shared/px4/bin/llm_to_action_fmu_px4"
export LD_LIBRARY_PATH="$PWD/build/release/shared/px4/bin:$PWD/build/release/shared/px4/_deps/onnxruntime/onnxruntime-linux-x64-1.20.1/lib:$LD_LIBRARY_PATH"
[ -x "$BIN" ] || { echo "FATAL: $BIN missing -- build first (./build.sh release shared px4 build)"; exit 1; }
LOG="$(mktemp)"; pass=0; fail=0
check() {  # $1 name  $2 flag  $3 pattern  $4 present|absent
  timeout 7 "$BIN" x "$2" >"$LOG" 2>&1
  n=$(grep -ac "$3" "$LOG")
  if { [ "$4" = present ] && [ "$n" -ge 1 ]; } || { [ "$4" = absent ] && [ "$n" -eq 0 ]; }; then
    printf "PASS  %s\n" "$1"; pass=$((pass+1))
  else
    printf "FAIL  %s  (matches=%s, wanted %s)\n" "$1" "$n" "$4"; fail=$((fail+1))
  fi
}
check "completion verdict stands the drone down" --canned-complete "verdict objective_complete=true" present
check "voice raises user_command interrupt"      --canned-voice    "reason=user_command"             present
check "regression: normal scenario has NO verdict" --canned-cross  "verdict objective_complete"      absent
rm -f "$LOG"
echo "---- $pass passed, $fail failed ----"
[ "$fail" -eq 0 ]
