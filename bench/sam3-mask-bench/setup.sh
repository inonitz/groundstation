#!/bin/bash
# setup.sh -- reproducible deps for sam3-mask-bench AND the perception2 SAM3 stack.
# The dev container wipes ad-hoc pip installs on rebuild, and the Dockerfile has NOT been rebuilt in
# a while, so THIS SCRIPT is the source of truth for the SAM3 dependency stack -- not the image.
# Run it after every rebuild.
#
# Verified working stack (2026-09-04, RTX 5070 Laptop, sm120 Blackwell):
#   torch 2.11.0+cu128   Blackwell sm120 -- comes from the Dockerfile base; do NOT reinstall here.
#   transformers 5.15.1  has Sam3Model/Sam3Processor. REQUIRED -- older transformers has NO SAM3.
#   torchao 0.18.0       fp8 dynamic-activation kernels (only engage under torch.compile).
#   bitsandbytes 0.50.2  nf4 / int8 quantization via transformers.
#   accelerate 1.14.0    required by transformers for bnb quantization.
# NOT installed here: gemlite (true int4 compute for the SAM3.1 quant effort) -- that session adds it.
set -euo pipefail
BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- SAM3 core stack (perception2 + the transformers-native bench) ---
pip install "transformers==5.15.1"        # Sam3Model/Sam3Processor -- the SAM3 work does not exist below this
pip install --no-deps "torchao==0.18.0"   # fp8 compute; --no-deps so the pinned cu128 torch is untouched
pip install "bitsandbytes==0.50.2"        # nf4 / int8 quantization
pip install "accelerate==1.14.0"          # required by transformers for bnb
pip install einops pycocotools            # facebookresearch/sam3 repo (SAM3.1 inference)

# --- ONNX bench extras (community SAM3 ONNX ports); --no-deps to not disturb the pinned numpy/torch ---
pip install --no-deps onnx ml_dtypes ftfy wcwidth regex

# samexporter: MIT reference runtime for SAM3 ONNX (prompt encoding + CLIP tokenizer). Pinned to the
# exporter revision that produced the downloaded vietanhdev weights (MANIFEST.json exporter_revision).
if [ ! -d "$BENCH_DIR/samexporter" ]; then
  git clone https://github.com/vietanhdev/samexporter.git "$BENCH_DIR/samexporter"
  git -C "$BENCH_DIR/samexporter" checkout 35133ce8670e0d190ac10cc08efba9b9a443fb51
fi
echo "[sam3-mask-bench setup] done"
