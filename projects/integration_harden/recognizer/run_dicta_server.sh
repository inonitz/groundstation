#!/bin/bash
# DictaLM on CPU for the Recognizer's translate stage. Measured p50 199 ms at 16 threads;
# zero VRAM (ruling 2026-09-02: the GPU belongs to Qwen3-VL + the perception engine).
set -euo pipefail
BIN=/root/groundstation/build/release/shared/dji/bin
exec env LD_LIBRARY_PATH="$BIN" "$BIN/llama-server" \
  -m /root/models/asr/dictalm-3-1.7b/dictalm-3.0-1.7b-instruct-q4_k_m.gguf \
  -ngl 0 --threads 16 -c 4096 --temp 0.0 --host 127.0.0.1 --port 18091
