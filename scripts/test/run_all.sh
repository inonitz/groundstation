#!/bin/bash
# run_all.sh -- headless regression runner. Iterates every scripts/test/<scenario>/,
# runs it HEADLESS (ground-truth completion, not a human watching), invokes that
# scenario's filter.sh, aggregates PASS/FAIL. Nonzero exit if anything failed.
# Usage: cd scripts/test && ./run_all.sh
#        cd scripts/test && ./run_all.sh --only rotate-land     # one scenario, fast iteration
#        cd scripts/test && ./run_all.sh --include-unverifiable # also sweep the 8 that can't self-assert
set -uo pipefail
cd "$(dirname "$0")" || exit 1
SUMMARY_FILE="${SUMMARY_FILE:-$(pwd)/run_all_summary.txt}"
: > "$SUMMARY_FILE"
cd SITL || exit 1

ONLY=""
INCLUDE_UNVERIFIABLE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --only) ONLY="$2"; shift 2 ;;
        --include-unverifiable) INCLUDE_UNVERIFIABLE=1; shift ;;
        *) echo "unknown argument: $1" >&2; exit 1 ;;
    esac
done

# scenario -> "completion_mode:timeout_seconds"
# flight = waits on real arm/land ground truth; fixed = scenario never takes off
# (flood: ground-only queue test; override: needs a scripted trigger, see Task 6).
declare -A SCENARIO_CFG=(
    [forward]="flight:90"
    [cross]="flight:90"
    [speed]="flight:90"
    [rotate-land]="flight:90"
    [land-flare]="flight:90"
    [terrain-land]="flight:90"
    [approach]="flight:90"
    [approach-real]="flight:150"
    [approach-impact]="flight:90"
    [vlm]="flight:180"
    [queue-overflow]="fixed:30"
    [queue-overflow-airborne]="flight:90"
    [battery]="flight:120"
    [battery-rth]="flight:120"
    [battery-landnow]="flight:120"
    [override]="fixed:60"
    [obstacle-stop]="flight:120"
    [interrupt-storm]="flight:150"
    [orbit]="flight:120"
    [rotate]="flight:90"
    [hover]="flight:75"
    [follow]="flight:90"
    [search]="flight:120"
)

# High-VRAM scenarios (2026-08-09 operator finding): these three set LAUNCH_VLM=1, which loads
# Qwen3-VL-2B (-ngl 99 -c 65536, full GPU offload, 64k context) IN ADDITION to the seg+depth ONNX
# perception models every scenario already loads -- confirmed ~12GiB VRAM on the operator's machine,
# too much for a laptop-class GPU. SKIP_HIGH_VRAM=1 (default 0) skips these three; set it on
# constrained hardware. If a specific one of these three isn't actually the culprit, narrow this list
# rather than removing the mechanism -- the underlying LAUNCH_VLM=1 cost is real for all three.
HIGH_VRAM_SCENARIOS=(vlm approach-real override)
: "${SKIP_HIGH_VRAM:=0}"
is_high_vram() {
    local n="$1" s
    for s in "${HIGH_VRAM_SCENARIOS[@]}"; do [ "$n" = "$s" ] && return 0; done
    return 1
}

# These 8 filters have no automated verdict -- they dump a milestone digest and always exit 0
# (pre-existing, not introduced by this work). Headless, nobody is there to judge them, so a
# headless "PASS" from one of these is meaningless -- confirmed 2026-08-09. Excluded from the
# default sweep so the summary doesn't lie; run them attended instead:
#   cd scripts/test/SITL/<name> && ./run.sh   (watch it)   then   ./filter.sh   (report what you saw)
# --only <name> or --include-unverifiable still runs them, since that's an explicit ask.
UNVERIFIABLE_SCENARIOS=(approach approach-real cross vlm)
is_unverifiable() {
    local n="$1" s
    for s in "${UNVERIFIABLE_SCENARIOS[@]}"; do [ "$n" = "$s" ] && return 0; done
    return 1
}

run_one() {
    local name="$1" cfg mode timeout_s run_status filter_status
    cfg="${SCENARIO_CFG[$name]:-flight:90}"
    mode="${cfg%%:*}"
    timeout_s="${cfg##*:}"

    echo "=== $name (mode=$mode timeout=${timeout_s}s) ==="
    ( cd "$name" && HEADLESS=1 HEADLESS_COMPLETION="$mode" HEADLESS_TIMEOUT_SECONDS="$timeout_s" ./run.sh )
    run_status=$?
    if [ "$run_status" -ne 0 ]; then
        echo "$name: FAIL (run.sh exit $run_status)" | tee -a "$SUMMARY_FILE"
        FAIL=$((FAIL + 1))
        return
    fi

    if [ ! -f "$name/filter.sh" ]; then
        echo "$name: SKIP (ran headless; no filter.sh to auto-verdict)" | tee -a "$SUMMARY_FILE"
        SKIP=$((SKIP + 1))
        return
    fi
    ( cd "$name" && ./filter.sh )
    filter_status=$?
    if [ "$filter_status" -eq 0 ]; then
        if is_unverifiable "$name"; then
            echo "$name: PASS (no automated verdict -- this exit-0 is not a real check; read the digest above yourself)" | tee -a "$SUMMARY_FILE"
        else
            echo "$name: PASS" | tee -a "$SUMMARY_FILE"
        fi
        PASS=$((PASS + 1))
    else
        echo "$name: FAIL (filter.sh exit $filter_status)" | tee -a "$SUMMARY_FILE"
        FAIL=$((FAIL + 1))
    fi
}

PASS=0
FAIL=0
SKIP=0

if [ -n "$ONLY" ]; then
    [ -d "$ONLY" ] && [ -f "$ONLY/run.sh" ] || { echo "no such scenario: $ONLY" >&2; exit 1; }
    run_one "$ONLY"
else
    for dir in */; do
        name="${dir%/}"
        [ "$name" = "lib" ] && continue
        [ -f "$dir/run.sh" ] || continue
        if [ ! -f "$dir/filter.sh" ]; then
            echo "$name: SKIP (no filter.sh -- viewer/world helper, no automated verdict)" | tee -a "$SUMMARY_FILE"
            SKIP=$((SKIP + 1))
            continue
        fi
        if [ "$SKIP_HIGH_VRAM" = "1" ] && is_high_vram "$name"; then
            echo "$name: SKIP (high VRAM, SKIP_HIGH_VRAM=1)" | tee -a "$SUMMARY_FILE"
            SKIP=$((SKIP + 1))
            continue
        fi
        if [ "$INCLUDE_UNVERIFIABLE" != "1" ] && is_unverifiable "$name"; then
            echo "$name: SKIP (no automated verdict -- run attended: cd scripts/test/SITL/$name && ./run.sh && ./filter.sh)" | tee -a "$SUMMARY_FILE"
            SKIP=$((SKIP + 1))
            continue
        fi
        run_one "$name"
    done
fi

echo "---"
echo "PASS=$PASS FAIL=$FAIL SKIP=$SKIP  (summary: $SUMMARY_FILE)"
[ "$FAIL" -eq 0 ]
