#!/bin/bash
# Driver: benchmarks every yolo26n-depth ONNX variant, one isolated process each, then writes results.md.
set -u
cd "$(dirname "$0")"
export PYTHONPATH="$(pwd)/libs"
PY=python3
MODELS=/root/models/vision
THREADS="${THREADS:-2}"; WARMUP="${WARMUP:-20}"; ITERS="${ITERS:-200}"
VARIANTS="yolo26n-depth.onnx yolo26n-depth-384.onnx yolo26n-depth-480.onnx yolo26n-depth.int8.onnx yolo26n-depth.int4.onnx"
OUT=results.jsonl; : > "$OUT"
for m in $VARIANTS; do
    echo "[bench] $m (threads=$THREADS warmup=$WARMUP iters=$ITERS)" >&2
    "$PY" bench_one.py "$MODELS/$m" "$THREADS" "$WARMUP" "$ITERS" >> "$OUT"
done
"$PY" make_table.py "$OUT" "$THREADS" > results.md
cat results.md
