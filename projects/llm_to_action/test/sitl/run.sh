#!/bin/bash
# run.sh -- consolidated SITL runner for the llm_to_action FMU (replaces the 20 per-scenario
# dirs, scripts/sandbox, and run_all.sh).
#   ./run.sh --list                         scenarios + verdict quality + world
#   ./run.sh <scenario>                     attended tmux run of one scenario
#   ./run.sh --free "<objective>" [world]   free-form VLM-driven run (the old sandbox)
#   ./run.sh --verdict <scenario>           PASS/FAIL (or digest) from the last run's log
#   ./run.sh --all                          headless sweep of every "verified" scenario;
#                                           SKIP_HIGH_VRAM=1 skips the ~12GiB VLM scenarios
# Each run works in runs/<scenario>/; the FMU log lands there and the verdict reads it.
SITL="$(cd "$(dirname "$0")" && pwd)"
CONF="$SITL/scenarios.conf"

row()  { awk -F'|' -v n="$1" '!/^#/ && $1==n {print; exit}' "$CONF"; }

launch() {  # $1=name  (expects flag/world/spawn/obj/extras already set by caller)
    export FMU_OBJECTIVE="$obj" FMU_SCENARIO_FLAG="$flag" WORLD_NAME="$world" SPAWN_POSE="$spawn"
    # Headless: nobody runs QGroundControl, so waive the PX4 GCS-link preflight check or the
    # drone never arms (the sim_core warning box). Attended runs keep the check.
    [ "${HEADLESS:-0}" = "1" ] && export PX4_PARAM_NAV_DLL_ACT="${PX4_PARAM_NAV_DLL_ACT:-0}"
    for kv in $extras; do export "$kv"; done
    mkdir -p "$SITL/runs/$1"
    export LOG_FILE="$SITL/runs/$1/captured_panes_log.txt"
    cd "$SITL/runs/$1" || exit 1
    source "$SITL/../lib/sim_core.sh"
}

verdict() {  # $1=name
    local v="$SITL/verdicts/$1.sh"
    [ -f "$v" ] || { echo "no verdict script for '$1' (unverified scenario)" >&2; return 2; }
    SITL_RUN_DIR="$SITL/runs/$1" bash "$v" "$SITL/runs/$1/captured_panes_log.txt"
}

case "${1:---list}" in
  --list)
      echo "scenarios (name / verdict / world / tags):"
      awk -F'|' '!/^#/ && NF {printf "  %-24s %-11s %-15s %s\n", $1, $8, $3, $9}' "$CONF"
      exit 0;;
  --verdict)
      [ -n "${2:-}" ] || { echo "usage: run.sh --verdict <scenario>" >&2; exit 2; }
      verdict "$2"; exit $?;;
  --free)
      [ -n "${2:-}" ] || { echo "usage: run.sh --free \"<objective>\" [world]" >&2; exit 2; }
      obj="$2"; world="${3:-default_car}"; flag=""; spawn="0,7,3"; extras="LAUNCH_VLM=1"
      launch free;;
  --all)
      pass=0; fail=0; skip=0
      while IFS='|' read -r name flag world spawn obj extras completion vq tags; do
          case "$name" in ''|'#'*) continue;; esac
          [ "$vq" = "verified" ] || { echo "SKIP $name ($vq)"; skip=$((skip+1)); continue; }
          [ -n "$completion" ] || { echo "SKIP $name (attended only)"; skip=$((skip+1)); continue; }
          if [ "${SKIP_HIGH_VRAM:-0}" = "1" ] && [ "$tags" = "highvram" ]; then
              echo "SKIP $name (highvram)"; skip=$((skip+1)); continue
          fi
          mode="${completion%%:*}"; secs="${completion##*:}"
          echo "=== $name (mode=$mode timeout=${secs}s) ==="
          ( obj="$obj" flag="$flag" world="$world" spawn="$spawn" extras="$extras" \
            HEADLESS=1 HEADLESS_COMPLETION="$mode" HEADLESS_TIMEOUT_SECONDS="$secs" \
            bash "$SITL/run.sh" "$name" ) </dev/null
          if verdict "$name"; then pass=$((pass+1)); echo "$name: PASS"; else fail=$((fail+1)); echo "$name: FAIL"; fi
      done < "$CONF"
      echo "=== sweep done: $pass pass / $fail fail / $skip skipped ==="
      [ "$fail" -eq 0 ];;
  *)
      name="$1"
      line="$(row "$name")"
      [ -n "$line" ] || { echo "unknown scenario '$name' -- try --list" >&2; exit 2; }
      IFS='|' read -r _ flag world spawn obj extras _ _ _ <<< "$line"
      launch "$name";;
esac
