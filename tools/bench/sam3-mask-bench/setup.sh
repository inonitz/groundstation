#!/bin/bash
# setup.sh -- reproducible deps for sam3-mask-bench.
# The dev container wipes ad-hoc pip installs on rebuild; run this after every rebuild.
# onnxruntime (CPU), torch, ultralytics, opencv are already baked into tools/devenv/Dockerfile;
# this adds ONLY what the SAM3 ONNX bench needs on top. --no-deps so the devenv-pinned
# numpy/torch are never disturbed.
set -euo pipefail
BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pip install --no-deps onnx ml_dtypes ftfy wcwidth regex
pip install bitsandbytes   # int8/int4 (nf4/fp4) quantization via transformers
pip install accelerate   # required by transformers for bnb quantization
pip install einops pycocotools   # required by the facebookresearch/sam3 repo (SAM3.1 inference)
# samexporter: MIT reference runtime for SAM3 ONNX (prompt encoding + CLIP tokenizer).
# Pinned to the exporter revision that produced the downloaded vietanhdev weights
# (MANIFEST.json exporter_revision).
if [ ! -d "$BENCH_DIR/samexporter" ]; then
  git clone https://github.com/vietanhdev/samexporter.git "$BENCH_DIR/samexporter"
  git -C "$BENCH_DIR/samexporter" checkout 35133ce8670e0d190ac10cc08efba9b9a443fb51
fi
echo "[sam3-mask-bench setup] done"
