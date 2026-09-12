#!/usr/bin/env bash
# harden2 (2026-09-08): ONE llama-server serves planning, vision and Hebrew answers.
#   MVD_PLANNER=gemma4 (default)  -> Gemma 4 E4B QAT Q4_K_XL + its vision projector, thinking OFF
#                                     (enable_thinking=false via the jinja template; --reasoning-budget 0 alone narrates).
#                                     Gemma gotchas (2026-09-08): NO --image-min-tokens (breaks its CLIP load),
#                                     NO q4_0 KV + flash-attn (empty output). Plain KV, temp 0.
#   MVD_PLANNER=qwen3vl           -> the harden server (Qwen3-VL-4B, prod flags), unchanged.
set -euo pipefail
BIN="$(cd "$(dirname "$0")/../.." && pwd)"/build/release/shared/dji/bin
export LD_LIBRARY_PATH="$BIN:${LD_LIBRARY_PATH:-}"
PORT=${SCENE_LLAMA_PORT:-18090}
case "${MVD_PLANNER:-gemma4}" in
  gemma4)
    DIR=/root/models/vlm/Gemma-4-E4B
    exec "$BIN/llama-server" \
        -m "$DIR/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf" --mmproj "$DIR/mmproj-BF16.gguf" \
        -dev Vulkan0 -ngl 99 -c 4096 -np 1 --temp 0.0 \
        --jinja --chat-template-kwargs '{"enable_thinking":false}' --reasoning-budget 0 \
        --host 127.0.0.1 --port "$PORT" --threads 1 ;;
  qwen3vl)
    DIR=/root/models/vlm/Qwen3-VL-4B-Instruct
    exec "$BIN/llama-server" \
        -m "$DIR/Qwen3-VL-4B-Instruct-Q4_K_M.gguf" --mmproj "$DIR/mmproj-BF16.gguf" \
        -dev Vulkan0 -ngl 99 -c 4096 -np 1 --flash-attn on --image-min-tokens 1024 \
        --cache-type-k q4_0 --cache-type-v q4_0 --temp 0.3 \
        --host 127.0.0.1 --port "$PORT" --threads 1 ;;
  *) echo "unknown MVD_PLANNER '${MVD_PLANNER}' (gemma4|qwen3vl)"; exit 1 ;;
esac
