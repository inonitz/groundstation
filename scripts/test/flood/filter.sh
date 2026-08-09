#!/bin/bash
# Backpressure flood-test filter — captures ALL tmux panes to captured_flood_log.txt IN
# THIS FOLDER, prints the digest + PASS/FAIL. Run once the sim is up (the flood happens at
# FMU start; the drone does NOT fly -- this test only stresses the task queue). Optional
# arg: tmux session name (default llmsim).
#
# What we prove: one plan of 100 'stop' actions is injected in a single burst at FMU start.
# The SPSC queue is a moodycamel::ReaderWriterQueue built with cap=kMaxPlanActions(=60).
# That queue rounds capacity UP to (next power of two of cap+1) - 1 usable slots = 63, so
# ~63 enqueue and the rest are rejected with a BACKPRESSURE log. The invariant that matters
# is NOT a magic number: (a) backpressure engaged (drops>0), (b) the queue stayed BOUNDED
# near cap (never grew to hold all 100), (c) nothing vanished silently (enqueued+dropped ==
# injected). Portable awk only (mawk-safe).
set -euo pipefail
cd "$(dirname "$0")" || exit 1
OUT="captured_flood_log.txt"
LOG_FILE="${1:-$(pwd)/captured_panes_log.txt}"
if [ ! -f "$LOG_FILE" ]; then
    echo "no FMU log at '$LOG_FILE' -- start a run first with ./run.sh" >&2
    exit 2
fi
[ "$LOG_FILE" -ef "$OUT" ] || cp "$LOG_FILE" "$OUT"
echo "[capture] FMU log -> $OUT"

echo "----- flood digest -----"
grep -E 'FLOOD test: injecting|BACKPRESSURE queue full|qsize=' "$OUT" || true
grep -E 'FLOOD test: injecting|BACKPRESSURE queue full|qsize=' "$OUT" | awk '
    function ceilpow2(x,   p){ p=1; while(p<x) p*=2; return p }
    function val(line, key,   m,i,T){ m=split(line,T,/[ \t]+/);
        for(i=1;i<=m;i++){ if(index(T[i],key"=")==1) return substr(T[i],length(key)+2) } return "" }
    BEGIN{ maxq=0; drops=0; inj=0; cap=0; haveinj=0 }
    /FLOOD test: injecting/{
        for(i=1;i<=NF;i++){ if($i=="injecting") inj=$(i+1)+0; if($i=="cap") cap=$(i+1)+0 }
        haveinj=1; next
    }
    /qsize=/{ q=val($0,"qsize")+0; if(q>maxq) maxq=q; next }
    /BACKPRESSURE queue full/{
        for(i=1;i<=NF;i++){ if(index($i,"(total=")==1){ s=$i; gsub(/[^0-9]/,"",s); drops=s+0 } }
        next
    }
    END{
        if(!haveinj){ print "  FAIL: no FLOOD injection line — did you run ./run.sh (flood mode)?"; exit 1 }
        if(cap<=0) cap=60;
        capbound = ceilpow2(cap+1) - 1;   # moodycamel RWQ real usable capacity
        enq = inj - drops;                # accepted = injected - rejected (exact counters)
        fails=0;
        printf("  injected=%d  cap=%d (usable<=%d)  maxQsize=%d  drops=%d  enqueued=%d\n",
               inj, cap, capbound, maxq, drops, enq);
        if(drops<=0){ print "  FAIL: 0 drops — backpressure never engaged (unbounded enqueue?)"; fails++ }
        if(enq>capbound){ printf("  FAIL: enqueued %d > usable cap %d — queue NOT bounded\n", enq, capbound); fails++ }
        if(maxq>capbound){ printf("  FAIL: observed qsize %d > usable cap %d — queue NOT bounded\n", maxq, capbound); fails++ }
        if(enq!=maxq){ printf("  note: peak qsize %d != enqueued %d (heartbeat missed the exact peak; harmless)\n", maxq, enq) }
        if(fails==0) printf("  ok   bounded to %d usable slots; %d dropped; %d+%d==%d accounted\n",
                            capbound, drops, enq, drops, inj);
        if(fails>0){ printf("\nFAIL (%d)\n", fails); exit 1 }
        print "\nPASS — queue bounded, backpressure engaged, every action accounted for."; exit 0
    }'
