#!/bin/bash
# land digest — LAND flare-taper / STANDBY check.
# Self-contained: captures ALL tmux panes to captured_panes_log.txt IN THIS
# FOLDER, then filters/checks THIS test from that same file. Run after landing.
# Optional arg: tmux session name (default llmsim).
# Portable awk only (system awk may be mawk): value extraction is token-split.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
OUT="captured_panes_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"

echo "----- land digest -----"
grep -E 'LAND altENU|LANDING->STANDBY' "$OUT" || true
grep -E 'LAND altENU|LANDING->STANDBY' "$OUT" | awk '
    function val(line, key,   m,i,T){ m=split(line,T,/[ \t]+/);
        for(i=1;i<=m;i++){ if(index(T[i],key"=")==1) return substr(T[i],length(key)+2) } return "" }
    BEGIN{ TOUCH=-0.12; n=0; ended=0; mono=1 }
    /LAND altENU/{
        v=val($0,"vLand")+0;
        n++; last=v;
        if(n==1){ vmin=v; vmax=v }
        else{ if(v<vmin)vmin=v; if(v>vmax)vmax=v;
              if(v < prev-0.001){ mono=0; dropinfo=sprintf("%.3f -> %.3f", prev, v) } }
        prev=v; next
    }
    /LANDING->STANDBY/{ ended=1 }
    END{
        fails=0;
        if(n==0){ print "  FAIL: no LAND vLand samples captured"; exit 1 }
        if((vmax-vmin)<0.1){ printf("  FAIL: vLand near-constant (%.3f..%.3f) — flare taper missing\n",vmin,vmax); fails++ }
        if(!mono){ print "  FAIL: vLand not monotonic (dropped " dropinfo ")"; fails++ }
        if(last < TOUCH-0.15){ printf("  FAIL: final vLand %.3f never rose toward touchdown %.2f\n",last,TOUCH); fails++ }
        if(!ended){ print "  FAIL: no LANDING->STANDBY — landing did not complete"; fails++ }
        if(fails==0){ printf("  ok   vLand tapered %.3f -> %.3f toward %.2f, reached STANDBY (%d samples)\n",vmin,last,TOUCH,n) }
        if(fails>0){ printf("\nFAIL (%d)\n",fails); exit 1 }
        print "\nPASS"; exit 0
    }'
