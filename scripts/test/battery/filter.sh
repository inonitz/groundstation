#!/bin/bash
# Real-drain battery filter -- captures all panes, asserts the drone patrolled OUT, then OUR
# <=20% failsafe (not PX4's) returned it home and disarmed it. Run after touchdown.
set -euo pipefail
cd "$(dirname "$0")" || exit 1
SESSION="${1:-llmsim}"
OUT="captured_battery_log.txt"
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "no tmux session '$SESSION' — start it with ./run.sh" >&2; exit 2
fi
: > "$OUT"
while read -r pane; do
    { echo "===== pane $pane ====="; tmux capture-pane -p -J -S - -t "$pane"; echo; } >> "$OUT"
done < <(tmux list-panes -a -t "$SESSION" -F '#{session_name}:#{window_index}.#{pane_index}')
echo "[capture] all panes -> $OUT"
echo "----- battery (real-drain) digest -----"
grep -E 'FAILSAFE battery|RETURN to origin|LAND in place|LANDING->STANDBY|entering Hold|Failsafe activated|Critical battery' "$OUT" || true
awk '
    function posdist(line,   c,a,n){
        if (match(line, /posENU=\([^)]*\)/)) {
            c = substr(line, RSTART+8, RLENGTH-9); n = split(c, a, ",");
            if(n>=2) return sqrt(a[1]*a[1]+a[2]*a[2]);
        } return -1
    }
    /TAKEOFF->FLIGHT/{ flight=1 }
    /FAILSAFE battery .* RETURN to origin/{ rth=1 }
    /LANDING->STANDBY/{ landed=1 }
    /entering Hold/{ pxhold=1 }
    /posENU=/{ d=posdist($0); if(d>=0){ last=d; if(d>maxd) maxd=d } }
    END{
        fails=0;
        if(maxd>=3.0) flight=1;   # >3m out proves airborne even if the early TAKEOFF->FLIGHT line scrolled out of tmux history
        printf("  airborne=%s  ourRTH=%s  maxDist=%.2fm  landDist=%.2fm  disarmed=%s  PX4hijack=%s\n",
               (flight?"yes":"NO"),(rth?"yes":"NO"),maxd,last,(landed?"yes":"NO"),(pxhold?"YES":"no"));
        if(!flight){ print "  FAIL: never reached FLIGHT"; fails++ }
        if(!rth){ print "  FAIL: OUR <=20% RETURN-to-origin failsafe never fired (drain too slow? patrol landed first?)"; fails++ }
        if(maxd<3.0){ printf("  FAIL: only reached %.2fm -- the patrol did not fly OUT\n",maxd); fails++ }
        if(last>=1.5){ printf("  FAIL: ended %.2fm from origin -- RTH did not bring it home\n",last); fails++ }
        if(!landed){ print "  FAIL: no LANDING->STANDBY (force_disarm) -- landed but never disarmed"; fails++ }
        if(pxhold){ print "  FAIL: PX4 failsafe entered HOLD -- it hijacked the descent. Set COM_LOW_BAT_ACT=0 (see run.sh)."; fails++ }
        if(fails>0){ printf("\nFAIL (%d)\n",fails); exit 1 }
        printf("\nPASS — patrolled to %.2fm, OUR 20%% failsafe returned it home (%.2fm) and disarmed; PX4 did not intervene.\n",maxd,last); exit 0
    }' "$OUT"
