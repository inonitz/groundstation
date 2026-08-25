#!/usr/bin/env bash
# Serve Qwen3-VL-4B (the reasoning brain) on the repo's llama-server, Vulkan device.
# LD_LIBRARY_PATH + -dev Vulkan0 + flags mirror sim_core.sh's working VLM pane: the llama
# shared libs (libllama-server-impl.so, libllama.so, libggml*.so) live NEXT TO the binary,
# so without LD_LIBRARY_PATH the loader can't find them.
set -euo pipefail

BIN=/root/groundstation/build/release/shared/dji/bin
DIR=/root/models/vlm/Qwen3-VL-4B-Instruct

export LD_LIBRARY_PATH="$BIN:${LD_LIBRARY_PATH:-}"

exec "$BIN/llama-server" \
    -m "$DIR/Qwen3-VL-4B-Instruct-Q4_K_M.gguf" \
    --mmproj "$DIR/mmproj-BF16.gguf" \
    -dev Vulkan0 -ngl 99 -c 4096 --flash-attn on --image-min-tokens 1024 \
    --cache-type-k q4_0 --cache-type-v q4_0 --temp 0.3 \
    --host 127.0.0.1 --port 8090 --threads 1
