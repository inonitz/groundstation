#!/bin/bash
cd "$(dirname "$0")"
: > results_sota.jsonl
for k in depthpro da3mono-large da3-small metric3d-small metric3d-large; do
  for d in cuda cpu; do
    echo "[sota] $k / $d ..." >&2
    python3 bench_one_sota.py "$k" "$d" >> results_sota.jsonl 2>>sota_errors.log
    tail -1 results_sota.jsonl >&2
  done
done
