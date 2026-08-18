#!/usr/bin/env bash
# Serve Qwen3-VL-4B (the reasoning brain) on the repo's own llama-server.
# The llm_cv_scene app is a thin HTTP client to this. Warm it once before demoing.
set -euo pipefail
LLAMA=/root/groundstation/build/release/shared/px4/bin/llama-server
DIR=/root/models/vlm/Qwen3-VL-4B-Instruct
exec "$LLAMA" \
  -m "$DIR/Qwen3-VL-4B-Instruct-Q4_K_M.gguf" \
  --mmproj "$DIR/mmproj-BF16.gguf" \
  --host 127.0.0.1 --port 8080 -c 4096 --flash-attn on -ngl 99
