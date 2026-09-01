#!/usr/bin/env bash
# bootstrap.sh -- PREPARE step: bring up + prewarm the VLM and verify models, so run.sh is instant.
# Leaves llama-server running warm. Safe: reads only; starts the VLM the same way the MVD does.
set -euo pipefail
ROOT=/root/groundstation
HERE="$ROOT/source/integration_notify"
source /opt/ros/jazzy/setup.bash 2>/dev/null || true
echo "[bootstrap] checking models ..."
for m in /root/models/vlm/Qwen3-VL-4B-Instruct/Qwen3-VL-4B-Instruct-Q4_K_M.gguf /root/models/vision/sam2.1_b.pt; do
    [ -e "$m" ] || echo "[bootstrap] MISSING: $m"
done
[ -e "$HERE/yolo26n-seg.pt" ] || echo "[bootstrap] WARN: yolo26n-seg.pt missing"
if [ "${NOTIFY_TRACKER:-iou}" = "osnet" ]; then
    python3 -c "import torchreid" 2>/dev/null && echo "[bootstrap] OSNet deps OK" || echo "[bootstrap] WARN: torchreid missing -> IoU fallback at runtime"
fi
if ! pgrep -f llama-server >/dev/null 2>&1; then
    echo "[bootstrap] starting VLM (llama-server, :18090) ..."
    ( bash "$HERE/run_llama_server.sh" >/tmp/notify_llama.log 2>&1 & )
else
    echo "[bootstrap] VLM already running."
fi
bash "$ROOT/scripts/prewarm_llama.sh" || echo "[bootstrap] prewarm skipped"
echo "[bootstrap] READY -> run: bash $HERE/run.sh"
