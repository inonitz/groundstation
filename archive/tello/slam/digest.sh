#!/bin/bash
# Digest a C1 run log (from ./c1test.sh) into a small report to send back.
#
# Usage:  ./digest.sh              # newest run in runs/
#         ./digest.sh <logfile>    # a specific run
HERE="$(cd "$(dirname "$0")" && pwd)"
L="${1:-$(ls -t "$HERE"/runs/*.log 2>/dev/null | head -1)}"
if [ ! -f "$L" ]; then
    echo "no C1 log in $HERE/runs -- run ./c1test.sh first"; exit 1
fi
D="${L%.log}.digest.txt"

# per-second sample lines carry "note="; the summary line does NOT.
samples="$(grep -a "note=" "$L")"
nsamp="$(printf '%s\n' "$samples" | grep -c "note=")"
ntrack="$(printf '%s\n' "$samples" | grep -c "state=TRACKING")"
nblind="$(printf '%s\n' "$samples" | grep -c "state=BLIND")"
nnovid="$(printf '%s\n' "$samples" | grep -c "state=NO-VIDEO")"
summary="$(grep -a "TELLO_SLAM_SUMMARY" "$L" | grep -v "why:\|units are" | head -1)"
{
    echo "LOG: $L"
    echo
    echo "== VERDICT (from the summary line) =="
    if [ -n "$summary" ]; then echo "$summary"; else echo "(no summary -- run ended without Ctrl-C on the measure pane)"; fi
    echo
    echo "== seconds of data (want many) ==";              echo "$nsamp"
    echo "== tracking uptime (want >= 80%, ideal 100%) ==";
        if [ "$nsamp" -gt 0 ]; then awk "BEGIN{printf \"%d%% (%d/%d seconds had a pose)\n\", 100*$ntrack/$nsamp, $ntrack, $nsamp}"; else echo "n/a"; fi
    echo "== BLIND seconds (video but no pose; want ~0) =="; echo "$nblind"
    echo "== NO-VIDEO seconds (RX not publishing; want ~0) =="; echo "$nnovid"
    echo "== pose rate (Hz, want near 30) ==";
        printf '%s\n' "$samples" | grep -oE "rate=[ ]*[0-9]+hz" | sed 's/.*=//;s/hz//' \
        | awk '{s+=$1;n++} END{if(n)printf "avg %.0fhz over %d s\n",s/n,n; else print "n/a"}'
    echo "== return/peak ratio (SCALE-FREE drift proxy; want small) ==";
        printf '%s\n' "$samples" | grep -oE "return/peak=[0-9.]+" | tail -1
    echo "     (0 = ended at start; ~0.5 = ended halfway back; monocular units, NOT metres)"
    echo "== crashes/exceptions (want 0) ==";
        grep -aicE "terminate|exception|segfault|core dumped|what\(\):" "$L"
    echo
    echo "== READING IT =="
    echo "GO   : verdict PASS, uptime >= ~80%, BLIND/NO-VIDEO ~0, return/peak small + steady."
    echo "NO-GO: uptime low, many BLIND, or it drifts the instant tracking drops -> run SITL."
    echo "NOTE : positions are UP-TO-SCALE (monocular). Real drift in METRES = film + ../measure_drift.py."
} | tee "$D"
echo
echo "SEND ME THIS FILE: $D"
echo "(and $L itself if you want a deep read)"
