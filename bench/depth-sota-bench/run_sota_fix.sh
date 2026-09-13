#!/bin/bash
cd "$(dirname "$0")"
: > results_sota_fix.jsonl
for k in depthpro metric3d-small metric3d-large; do
  for d in cuda cpu; do
    echo "[sota-fix] $k / $d ..." >&2
    python3 bench_one_sota.py "$k" "$d" >> results_sota_fix.jsonl 2>>sota_fix_errors.log
    tail -1 results_sota_fix.jsonl >&2
  done
done
echo "SOTA_FIX DONE"
