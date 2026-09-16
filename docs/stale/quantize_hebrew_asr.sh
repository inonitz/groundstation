#!/usr/bin/env bash
# Quantize the ivrit-ai Hebrew whisper-large-v3-turbo model with whisper.cpp's quantize tool.
#
# OWNER RULING 2026-09-04 asked for type "q5_k_m". The whisper.cpp quantize tool does NOT accept
# that string. Its accepted types are: q2_k q3_k q4_0 q4_1 q4_k q5_0 q5_1 q5_k q6_k q8_0.
# The 5-bit k-quant for Whisper is spelled "q5_k" (ggml ftype 13). whisper.cpp has NO S/M mixture
# selection; "q5_k" IS the k-quant. Passing "q5_k_m" fails with "unknown ftype" and leaves a
# corrupt ~600 KB partial file. This is verified. The type below is therefore q5_k by DEFAULT,
# pending the owner's ruling. Override with the first argument if the owner rules otherwise.
#
# Usage:  bash quantize_hebrew_asr.sh [type]
#   type  default q5_k   (one of the accepted types listed above)
set -euo pipefail

TYPE="${1:-q5_k}"
SRC=/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model.bin
OUT="/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-${TYPE}.bin"
BIN=/root/groundstation/build/release/shared/dji/bin
QUANT="$BIN/whisper-quantize"

echo "[quantize] type=$TYPE"
echo "[quantize] src =$SRC"
echo "[quantize] out =$OUT"

[ -x "$QUANT" ] || { echo "[quantize] FAIL: whisper-quantize not found at $QUANT"; exit 1; }
[ -f "$SRC" ]   || { echo "[quantize] FAIL: source model missing: $SRC"; exit 1; }

if [ "$TYPE" = "q5_k_m" ]; then
    echo "[quantize] REFUSING: 'q5_k_m' is not a whisper.cpp ftype (verified). Use 'q5_k'."
    echo "[quantize] Accepted: q2_k q3_k q4_0 q4_1 q4_k q5_0 q5_1 q5_k q6_k q8_0"
    exit 2
fi

export LD_LIBRARY_PATH="$BIN:${LD_LIBRARY_PATH:-}"
echo "[quantize] running: $QUANT $SRC $OUT $TYPE"
"$QUANT" "$SRC" "$OUT" "$TYPE"

echo "[quantize] done. Result:"
ls -la "$OUT"
