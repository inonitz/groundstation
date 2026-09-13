#!/usr/bin/env bash
# One command to reproduce the Hebrew ASR benchmark.
#   bash run.sh                                  # full run: all lanes, all 792 clips
#   bash run.sh --n 30 --lanes fp16,w2v2         # quick subset
# Bootstraps a venv on first run, sets the HF cache + the CUDA libs faster-whisper needs.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HERE/venv"
NV=/usr/local/lib/python3.12/dist-packages/nvidia   # torch bundles cuBLAS-12 + cuDNN-9 here
if [ ! -x "$VENV/bin/python" ]; then
  echo "[run] bootstrapping venv (one-time, a few minutes) ..."
  python3 -m venv --system-site-packages "$VENV"
  "$VENV/bin/pip" install --no-input "numpy==1.26.4" jiwer soundfile librosa datasets \
      pyctcdecode kenlm faster-whisper scipy
fi
export HF_HOME="$HERE/hf_cache"
export LD_LIBRARY_PATH="$NV/cublas/lib:$NV/cudnn/lib:${LD_LIBRARY_PATH:-}"
exec "$VENV/bin/python" "$HERE/asr_bench.py" "$@"
