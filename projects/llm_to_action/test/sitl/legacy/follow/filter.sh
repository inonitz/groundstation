#!/bin/bash
# follow verdict: the yaw-only servo must lock the person, sustain the lock, and not churn the id.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
OUT="captured_panes_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then echo "no FMU log at '$LOG_FILE' -- run ./run.sh first" >&2; exit 2; fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"
echo "----- follow milestones -----"
grep -E 'FOLLOW activated|follow_no_target|FOLLOW\(yaw-only\)' "$OUT" | tail -6 \
    || echo "  (no follow lines captured)"
echo ""
grep -E 'FOLLOW' "$OUT" | awk '
    function val(line,key,  m,i,T){ m=split(line,T,/[ \t]+/);
        for(i=1;i<=m;i++){ if(index(T[i],key"=")==1) return substr(T[i],length(key)+2) } return "" }
    /follow_no_target/ { released=1; next }
    /FOLLOW\(yaw-only\)/ {
        ticks++; tid=val($0,"trackId");
        if(tid!="" && !(tid in seen)){ seen[tid]=1; ndist++ }
        ex=val($0,"errX")+0; if(ex<0)ex=-ex; ey=val($0,"errY")+0; if(ey<0)ey=-ey; sx+=ex; sy+=ey;
        d=(val($0,"range")+0)-(val($0,"minSafe")+0); if(cnt==0||d<mind)mind=d; cnt++;
        next
    }
    END{
        if(ticks==0){ print "  FAIL: no FOLLOW(yaw-only) ticks -- never locked a target"; exit 1 }
        printf "  ticks=%d  distinct trackIds=%d  mean|errX|=%.3f mean|errY|=%.3f  min(range-standoff)=%.2fm\n", ticks, ndist, sx/ticks, sy/ticks, mind;
        if(released){ print "  FAIL: follow_no_target -- lost the target"; exit 1 }
        if(ticks<20){ print "  FAIL: <20 follow ticks -- lock not sustained"; exit 1 }
        if(ndist>2){ printf "  FAIL: %d distinct track ids -- lock churned\n", ndist; exit 1 }
        print "  PASS: sustained follow, stable lock, no release"; exit 0
    }'
