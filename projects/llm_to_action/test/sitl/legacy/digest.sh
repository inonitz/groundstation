#!/bin/bash
# Digest a timestamped run log (from ./logtest.sh) into a full report -- everything we
# care about, so no hand-digging in the raw log.
#
# Usage:  ./digest.sh              # newest run in runs/
#         ./digest.sh <logfile>    # a specific run
HERE="$(cd "$(dirname "$0")" && pwd)"
L="${1:-$(ls -t "$HERE"/runs/*.log 2>/dev/null | head -1)}"
if [ ! -f "$L" ]; then
    echo "no log found in $HERE/runs -- run ./logtest.sh <scenario> first"; exit 1
fi
D="${L%.log}.digest.txt"
VLOG="$(ls -t /root/groundstation/vlm_logs/vlm_prompts_*.jsonl 2>/dev/null | head -1)"

# --- errX stats (responsiveness) ---
ticks=$(grep -c "FOLLOW(yaw-only) target=" "$L")
maxerr=$(grep -aoE "errX=-?[0-9.]+" "$L" | grep -aoE "[0-9.]+" | sort -rn | head -1)
bigerr=$(grep -aoE "errX=-?[0-9.]+" "$L" | grep -aoE "[0-9.]+" | awk '$1>0.5' | wc -l)

{
    echo "LOG:  $L"
    echo "VLM PROMPTS: ${VLOG:-<none>}"
    echo "--------------------------------------------------------"
    echo "OUTCOME COUNTS"
    printf "  takeoffs (want 1) ............ %s\n"   "$(grep -c 'TAKEOFF activated' "$L")"
    printf "  takeoff_rejected (want 0) .... %s\n"   "$(grep -c 'takeoff_rejected' "$L")"
    printf "  parameters blobs (want 0) .... %s\n"   "$(grep -c '"parameters"' "$L")"
    printf "  FOLLOW activated (want>=1) ... %s\n"   "$(grep -c 'FOLLOW activated' "$L")"
    printf "  HOVER activated (want 0) ..... %s\n"   "$(grep -c 'HOVER activated' "$L")"
    printf "  follow_no_target (want 0) .... %s\n"   "$(grep -c 'follow_no_target' "$L")"
    printf "  centre-fallback fired ........ %s\n"   "$(grep -c 'centre-detection fallback' "$L")"
    printf "  SEARCH activated ............. %s\n"   "$(grep -c 'SEARCH activated' "$L")"
    printf "  search_exhausted ............. %s\n"   "$(grep -c 'search_exhausted' "$L")"
    printf "  loss-sweep (look to last-seen) %s\n"   "$(grep -c 'sweeping to last-seen' "$L")"
    printf "  crashes/exceptions ........... %s\n"   "$(grep -icE 'terminate|exception|segfault|core dumped' "$L")"
    echo "--------------------------------------------------------"
    echo "FOLLOW RESPONSIVENESS"
    printf "  servo ticks (want many) ...... %s\n"   "$ticks"
    printf "  max |errX| (want < ~0.4) ..... %s\n"   "${maxerr:-none}"
    printf "  ticks with |errX|>0.5 (trail)  %s / %s\n" "$bigerr" "$ticks"
    echo "--------------------------------------------------------"
    echo "PERCEPTION SEEN BY THE DRONE (HUD DET field)"
    printf "  frames with a person ......... %s\n"   "$(grep -c 'DET=person' "$L")"
    printf "  frames with NOTHING (DET=-) .. %s\n"   "$(grep -c 'DET=-' "$L")"
    echo "--------------------------------------------------------"
    echo "PERCEPTION FED TO THE VLM (from prompt log)"
    if [ -n "$VLOG" ]; then
        total=$(grep -c '"prompt"' "$VLOG")
        empty=$(grep -c '(no detections)' "$VLOG")
        printf "  prompts total ................ %s\n" "$total"
        printf "  prompts saying no-detections . %s   <-- high = VLM told 'nothing' -> it searches\n" "$empty"
        printf "  VLM empty responses (0 chars). %s   <-- >0 = llama-server down/OOM (no plan -> nothing runs)\n" "$(grep -c 'VLM plan received (0 chars)' "$L")"
    else
        echo "  (no vlm_prompts log found)"
    fi
    echo "--------------------------------------------------------"
    echo "WHAT THE VLM ACTUALLY PLANNED (actions)"
    grep -aoE '"action": *"[a-z-]+"' "$L" | sort | uniq -c | sed 's/^/  /'
    echo "--------------------------------------------------------"
    echo "ORDERED TIMELINE (verbs + outcomes)"
    grep -aoE "(TAKEOFF activated|SEARCH activated|FOLLOW activated track_id=[0-9-]+|centre-detection fallback|task complete status=[a-z_]+|sweeping to last-seen)" "$L" \
      | awk '!(/task complete/ && $0==p){print} {p=$0}' | sed 's/^/  /' | head -30
} | tee "$D"
echo
echo "SEND ME THIS FILE: $D"
