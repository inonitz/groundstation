#!/bin/bash
# Airborne flood filter — captures ALL tmux panes to captured_flood_airborne_log.txt IN THIS
# FOLDER, prints the digest + PASS/FAIL. Run after the drone has flown a bit (ideally after it
# lands). Optional arg: tmux session name (default llmsim).
#
# What we prove: the drone reaches FLIGHT (airborne), THEN a 100-action flood is injected mid-
# air. The SPSC queue (moodycamel, cap 60 -> 63 usable) stays bounded, excess is dropped, and
# the live maneuver is not hijacked (the drone still finishes its legs + lands). Portable awk.
set -euo pipefail
cd "${SITL_RUN_DIR:-$(dirname "$0")}" || exit 1
OUT="captured_flood_airborne_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"

echo "----- airborne-flood digest -----"
grep -E 'AIRBORNE FLOOD armed|TAKEOFF->FLIGHT|FLOOD test: injecting|BACKPRESSURE queue full|LANDING->STANDBY' "$OUT" || true
grep -E 'AIRBORNE FLOOD armed|TAKEOFF->FLIGHT|FLOOD test: injecting|BACKPRESSURE queue full|qsize=|LANDING->STANDBY' "$OUT" | awk '
    function ceilpow2(x,   p){ p=1; while(p<x) p*=2; return p }
    function val(line, key,   m,i,T){ m=split(line,T,/[ \t]+/);
        for(i=1;i<=m;i++){ if(index(T[i],key"=")==1) return substr(T[i],length(key)+2) } return "" }
    BEGIN{ maxq=0; drops=0; inj=0; cap=0; nrFlight=0; nrInject=0; armed=0; landed=0 }
    /AIRBORNE FLOOD armed/{ armed=1; next }
    /TAKEOFF->FLIGHT/{ if(!nrFlight) nrFlight=NR; next }
    /FLOOD test: injecting/{
        if(!nrInject) nrInject=NR;
        for(i=1;i<=NF;i++){ if($i=="injecting") inj=$(i+1)+0; if($i=="cap") cap=$(i+1)+0 }
        next
    }
    /qsize=/{ q=val($0,"qsize")+0; if(q>maxq) maxq=q; next }
    /BACKPRESSURE queue full/{
        for(i=1;i<=NF;i++){ if(index($i,"(total=")==1){ s=$i; gsub(/[^0-9]/,"",s); drops=s+0 } }
        next
    }
    /LANDING->STANDBY/{ landed=1; next }
    END{
        if(cap<=0) cap=60;
        capbound = ceilpow2(cap+1) - 1;
        fails=0;
        printf("  airborne(FLIGHT)=%s  flood_armed=%s  injected=%d  drops=%d  maxQsize=%d (usable<=%d)  landed=%s\n",
               (nrFlight?"yes":"NO"), (armed?"yes":"NO"), inj, drops, maxq, capbound, (landed?"yes":"NO"));
        if(!armed){ print "  FAIL: no AIRBORNE FLOOD armed — did you run ./run.sh (--scenario-queue-overflow-airborne)?"; fails++ }
        if(!nrFlight){ print "  FAIL: drone never reached FLIGHT — the flood was NOT airborne"; fails++ }
        if(!nrInject){ print "  FAIL: no flood injection seen (give it ~5s in FLIGHT, re-run filter)"; fails++ }
        if(nrFlight && nrInject && nrInject<=nrFlight){ print "  FAIL: flood fired BEFORE FLIGHT — not an airborne storm"; fails++ }
        if(nrInject && drops<=0){ print "  FAIL: flood injected but 0 drops — backpressure did not engage"; fails++ }
        if(maxq>capbound){ printf("  FAIL: qsize %d > usable cap %d — queue NOT bounded\n", maxq, capbound); fails++ }
        if(!landed){ print "  FAIL: no LANDING->STANDBY (force_disarm) — flight did not land+disarm after the storm. If it is still flying the cross, wait for touchdown and re-run ./filter.sh."; fails++ }
        if(fails==0 && nrFlight && nrInject){
            printf("  ok   airborne when flooded (FLIGHT@%d < flood@%d); bounded at %d; %d dropped; maneuver not hijacked\n",
                   nrFlight, nrInject, capbound, drops);
            print "  ok   LANDING->STANDBY (force_disarm) — flight landed AND disarmed after the storm";
        }
        if(fails>0){ printf("\nFAIL (%d)\n", fails); exit 1 }
        print "\nPASS — in-air storm absorbed: bounded queue, excess dropped, flight uninterrupted, landed AND disarmed."; exit 0
    }'
