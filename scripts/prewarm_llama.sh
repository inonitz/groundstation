#!/usr/bin/env bash
# prewarm_llama.sh -- fire dummy image inferences at the VLM so the FIRST real perception query
# doesn't eat the cold vision-pipeline spike (measured 1.3s..4.8s cold on Vulkan). The recurring
# per-new-frame cost (~1.2s here) is inherent and UNCHANGED by this -- prewarm only hides the
# one-time warmup. Run AFTER run_llama_server.sh is up; e.g. run_mvd backgrounds this after the VLM pane.
set -euo pipefail
PORT="${SCENE_LLAMA_PORT:-18090}"
URL="http://127.0.0.1:${PORT}"
echo "[prewarm] waiting for VLM ready on :$PORT ..."
for i in $(seq 1 180); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/health" 2>/dev/null)" = "200" ] && { echo "[prewarm] ready (${i}s)"; break; }
  sleep 1
done
IMG=$(python3 - <<'PY'
import base64,io
from PIL import Image
im=Image.new("RGB",(320,320),(128,128,128))
b=io.BytesIO(); im.save(b,"PNG"); print("data:image/png;base64,"+base64.b64encode(b.getvalue()).decode())
PY
)
PL='{"messages":[{"role":"user","content":[{"type":"text","text":"warmup"},{"type":"image_url","image_url":{"url":"'"$IMG"'"}}]}],"max_tokens":1,"temperature":0}'
for n in 1 2; do
  t=$(curl -s -o /dev/null -w '%{time_total}' -X POST "$URL/v1/chat/completions" -H 'Content-Type: application/json' -d "$PL" 2>/dev/null)
  echo "[prewarm] warmup pass $n: ${t}s"
done
echo "[prewarm] VLM warm; first real query will run at steady-state."
