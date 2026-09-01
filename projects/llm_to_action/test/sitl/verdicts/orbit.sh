#!/bin/bash
# orbit accuracy verdict: parse 'ORBIT ... dist=X/R ... swept=S/T' -> radius-hold error + full sweep.
# PASS = orbit completed AND the measured distance-to-centre held near the commanded radius.
set -uo pipefail
cd "${SITL_RUN_DIR:-$(dirname "$0")}" || exit 1
OUT="captured_panes_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"

echo "----- orbit milestones -----"
grep -E 'ORBIT .*centerENU|ORBIT .*dist=|ORBIT complete' "$OUT" | tail -6 \
    || echo "  (no orbit lines captured -- check the FMU pane)"
echo ""
grep -E 'ORBIT' "$OUT" | awk '
    function val(line, key,   m,i,T){ m=split(line,T,/[ \t]+/);
        for(i=1;i<=m;i++){ if(index(T[i],key"=")==1) return substr(T[i],length(key)+2) } return "" }
    /dist=/ {
        dv=val($0,"dist"); k=split(dv,D,"/");
        if(k==2){ x=D[1]+0; r=D[2]+0; e=x-r; if(e<0)e=-e; sum+=e; if(e>mx)mx=e; cnt++; lastR=r }
        next
    }
    /ORBIT complete/ { done=1; next }
    END{
        if(cnt==0){ print "  FAIL: no ORBIT dist diagnostics -- orbit never ran"; exit 1 }
        mean=sum/cnt;
        printf "  radius R=%.2fm  samples=%d  mean|dist-R|=%.2fm  max=%.2fm\n", lastR, cnt, mean, mx;
        if(!done)      { print "  FAIL: orbit never completed the full sweep"; exit 1 }
        if(mx>0.15)    { printf "  FAIL: max radius error %.2fm > 0.15m -- circle not held\n", mx; exit 1 }
        if(mean>0.06)  { printf "  FAIL: mean radius error %.2fm > 0.06m\n", mean; exit 1 }
        print "  PASS: full circle swept + radius held within tolerance"; exit 0
    }'
