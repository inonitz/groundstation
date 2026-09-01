#!/bin/bash
set -euo pipefail
cd "${SITL_RUN_DIR:-$(dirname "$0")}" || exit 1
OUT="captured_battery_rth_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"

echo "----- battery-rth digest -----"
grep -E 'TAKEOFF->FLIGHT|TEST battery fault|FAILSAFE battery|RETURN to origin|LAND in place|LANDING->STANDBY' "$OUT" || true
awk '
    function posdist(line,   c,a,n){
        if (match(line, /posENU=\([^)]*\)/)) {
            c = substr(line, RSTART+8, RLENGTH-9); n = split(c, a, ",");
            if(n>=2) return sqrt(a[1]*a[1]+a[2]*a[2]);
        } return -1
    }
    /TAKEOFF->FLIGHT/{ flight=1 }
    /TEST battery fault/{ forced=1 }
    /FAILSAFE battery .* RETURN to origin/{ rth=1 }
    /FAILSAFE battery .* LAND in place/{ landip=1 }
    /LANDING->STANDBY/{ landed=1 }
    /posENU=/{ d=posdist($0); if(d>=0){ last=d; if(d>maxd) maxd=d } }
    END{
        fails=0;
        if(maxd>=3.0) flight=1;   # >3m out proves airborne even if the early TAKEOFF->FLIGHT line scrolled out of tmux history
        printf("  airborne=%s  forced18=%s  RTH=%s  maxDist=%.2fm  landDist=%.2fm  disarmed=%s\n",
               (flight?"yes":"NO"),(forced?"yes":"NO"),(rth?"yes":"NO"),maxd,last,(landed?"yes":"NO"));
        if(!flight){ print "  FAIL: never reached FLIGHT"; fails++ }
        if(!rth){ print "  FAIL: no <=20% RETURN-to-origin failsafe fired"; fails++ }
        if(landip){ print "  FAIL: land-in-place fired -- expected RTH, not land-now"; fails++ }
        if(maxd<3.0){ printf("  FAIL: drone only reached %.2fm -- it did not fly OUT (RTH would be trivial)\n",maxd); fails++ }
        if(last>=1.5){ printf("  FAIL: ended %.2fm from origin -- RTH did NOT bring it home\n",last); fails++ }
        if(!landed){ print "  FAIL: no LANDING->STANDBY (force_disarm) -- landed but never disarmed"; fails++ }
        if(fails>0){ printf("\nFAIL (%d)\n",fails); exit 1 }
        printf("\nPASS — flew out %.2fm, RTH returned it to ~origin (%.2fm), landed AND disarmed.\n",maxd,last); exit 0
    }' "$OUT"
