#!/bin/bash
# Hy-MT2-1.8B (Q4_K_M) on the GPU for the Recognizer's translate stage -- the deployed translator
# (ruling 2026-09-07: ONE model for commands and perception; the DictaLM split is rejected).
# Served LEAN: 1 slot, 1024 ctx (the V2 prompt + 2 few-shots + a long input is ~520 tokens; V1 is ~110). The
# ~180 tokens, and the 4-slot/4096 server defaults would spend ~550 MiB of KV for nothing.
# Same endpoint and port as run_dicta_server.sh, so pipeline.py needs no change. Select it with
# MVD_TRANSLATOR=hymt2 (run_mvd.sh); it needs SCENE_SEG=sam3 to fit next to Qwen on the 8 GB card.
set -euo pipefail
BIN=/root/groundstation/build/release/shared/dji/bin
MODEL="${HYMT2_MODEL:-/root/models/translate/hy-mt2-1.8b-gguf/Hy-MT2-1.8B-Q4_K_M.gguf}"
exec env LD_LIBRARY_PATH="$BIN" "$BIN/llama-server" \
  -m "$MODEL" -dev Vulkan0 -ngl 99 -c 1024 -np 1 --temp 0.0 \
  --host 127.0.0.1 --port "${SCENE_XLATE_PORT:-18091}" --threads 1
