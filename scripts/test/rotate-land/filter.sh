#!/bin/bash
# rotate digest — ROTATE swept-angle/direction check.
# Self-contained: captures ALL tmux panes to captured_panes_log.txt IN THIS
# FOLDER, then filters/checks THIS test from that same file. Run after landing.
# Optional arg: tmux session name (default llmsim).
# Portable awk only (system awk may be mawk): value extraction is token-split.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
SESSION="${1:-llmsim}"
OUT="captured_panes_log.txt"
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "no tmux session '$SESSION' — start it first with ./run.sh" >&2
    exit 2
fi
: > "$OUT"
while read -r pane; do
    # -J rejoins tmux-wrapped rows so long log lines are not truncated at pane width.
    { echo "===== pane $pane ====="; tmux capture-pane -p -J -S - -t "$pane"; echo; } >> "$OUT"
done < <(tmux list-panes -a -t "$SESSION" -F '#{session_name}:#{window_index}.#{pane_index}')
echo "[capture] all panes -> $OUT"

echo "----- rotate digest -----"
grep -E 'ROTATE (activated|remainRad|complete)' "$OUT" || true
grep -E 'ROTATE (activated|remainRad|complete)' "$OUT" | awk '
    function abs(x){ return x<0 ? -x : x }
    function val(line, key,   m,i,T){ m=split(line,T,/[ \t]+/);
        for(i=1;i<=m;i++){ if(index(T[i],key"=")==1) return substr(T[i],length(key)+2) } return "" }
    BEGIN{ PI=3.14159265358979; TOL=15.0; turns=0; fails=0; cur=0 }
    /ROTATE activated/{
        turns++; ang[turns]=val($0,"angle_deg")+0; dir[turns]=val($0,"dir"); done[turns]=0;
        dsign[turns]=(val($0,"dir")=="ccw")? 1.0 : -1.0;   # ccw=+ (ENU CCW+), cw=-
        n[turns]=1; y[turns,1]=val($0,"startYaw")+0; cur=turns; next
    }
    /ROTATE remainRad/ && cur>0{ n[cur]++; y[cur,n[cur]]=val($0,"measYaw")+0; next }
    /ROTATE complete/ && cur>0{
        # measYaw is throttled and stops ~one tick short; reconstruct the true end-yaw
        # from the remaining angle so the swept magnitude is exact, not under-sampled.
        rc=val($0,"remainRad")+0;
        n[cur]++; y[cur,n[cur]]=y[cur,1] + dsign[cur]*(ang[cur]*PI/180.0 - rc);
        done[cur]=1; cur=0; next
    }
    END{
        if(turns==0){ print "  FAIL: no ROTATE activity captured"; exit 1 }
        for(i=1;i<=turns;i++){
            sw=0;
            for(j=2;j<=n[i];j++){ dd=y[i,j]-y[i,j-1];
                while(dd>PI)dd-=2*PI; while(dd<-PI)dd+=2*PI; sw+=dd }
            swdeg=sw*180.0/PI;
            want=dsign[i]*ang[i];
            tag=sprintf("turn %d (%d %s): swept %+.0f deg (want ~%+.0f)", i,ang[i],dir[i],swdeg,want);
            if(!done[i]){ print "  FAIL " tag " — no ROTATE complete"; fails++; continue }
            if(want!=0 && (swdeg==0 || (want>0)!=(swdeg>0))){ print "  FAIL " tag " — WRONG DIRECTION"; fails++; continue }
            if(abs(abs(swdeg)-abs(want))>TOL){ print "  FAIL " tag " — off by >" TOL; fails++; continue }
            print "  ok   " tag;
        }
        if(fails>0){ printf("\nFAIL (%d)\n",fails); exit 1 }
        print "\nPASS — confirm against what you observed."; exit 0
    }'
