#!/usr/bin/env bash
# harden2: ONE llama-server serves planning, vision, and Hebrew answers -- Gemma 4 E4B only.
#   Gemma 4 E4B QAT Q4_K_XL + its vision projector, thinking OFF (enable_thinking=false via the jinja
#   template; --reasoning-budget 0 alone narrates). Gemma gotchas (2026-09-08): NO --image-min-tokens
#   (breaks its CLIP load), NO q4_0 KV + flash-attn (empty output). Plain KV, temp 0.
#   (The Qwen3-VL alternate was removed 2026-09-19: the app is gemma4-only and config hardcodes it.)
set -euo pipefail
BIN="$(cd "$(dirname "$0")/../.." && pwd)"/build/release/shared/dji/bin
export LD_LIBRARY_PATH="$BIN:${LD_LIBRARY_PATH:-}"
PORT=${SCENE_LLAMA_PORT:-18090}
DIR=/root/models/vlm/Gemma-4-E4B
exec "$BIN/llama-server" \
    -m "$DIR/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf" --mmproj "$DIR/mmproj-BF16.gguf" \
    -dev Vulkan0 -ngl 99 -c 4096 -np 1 --temp 0.0 \
    --jinja --chat-template-kwargs '{"enable_thinking":false}' --reasoning-budget 0 \
    --host 127.0.0.1 --port "$PORT" --threads 1
