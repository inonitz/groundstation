#!/bin/bash
# preflight.sh -- ONE check of every model, binary, and tool the demos need; prints what is
# missing. Run before a demo morning or an interview. Read-only; touches nothing.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MISS=0
ck() {  # ck <label> <required|optional> <test...>
    local label="$1" req="$2"; shift 2
    if "$@" >/dev/null 2>&1; then printf '  OK       %s\n' "$label"
    elif [ "$req" = required ]; then printf '  MISSING  %s\n' "$label"; MISS=$((MISS+1))
    else printf '  absent   %s (optional)\n' "$label"; fi
}
echo "== models (/root/models, volume-mounted) =="
ck "VLM Qwen3-VL-4B Q4_K_M (MVD)"        required test -f /root/models/vlm/Qwen3-VL-4B-Instruct/Qwen3-VL-4B-Instruct-Q4_K_M.gguf
ck "VLM Qwen3-VL-2B Q4_K_M (SITL)"       required test -f /root/models/vlm/Qwen3-VL-2B-Instruct/Qwen3-VL-2B-Instruct-Q4_K_M.gguf
ck "ASR parakeet-tdt q4 (SITL voice)"    optional test -f /root/models/asr/nvidia--parakeet-tdt-0.6b-v3/ggml-parakeet-tdt-0.6b-v3-q4_k.bin
ck "vision yolo26n-seg.pt"               required test -f /root/models/vision/yolo26n-seg.pt
ck "vision sam2.1_b.pt"                  required test -f /root/models/vision/sam2.1_b.pt
ck "vision omdet-turbo (dir)"            required test -d /root/models/vision/omdet-turbo-swin-tiny
echo "== build artifacts =="
ck "dji backend bin/ (MVD C++ side)"     required test -x "$ROOT/build/release/shared/dji/bin/llm_to_action_fmu_dji"
ck "llama-server (dji tree)"             required test -x "$ROOT/build/release/shared/dji/bin/llama-server"
ck "px4 backend bin/ (SITL)"             optional test -x "$ROOT/build/release/shared/px4/bin/llm_to_action_fmu_px4"
echo "== tools =="
ck "tmux"      required command -v tmux
ck "gz sim"    optional command -v gz
ck "PX4-Autopilot checkout" optional test -d /root/PX4-Autopilot
ck "python aiohttp (dji mock)" required python3 -c "import aiohttp"
ck "python ultralytics (YOLO/SAM)" required python3 -c "import ultralytics"
ck "piper TTS"    optional command -v piper
ck "espeak-ng"    optional command -v espeak-ng
ck "aplay"        optional command -v aplay
ck "ffplay"       optional command -v ffplay
echo "== phone (read-only; needs the drone WiFi) =="
GW=$(ip route 2>/dev/null | awk '/^default/{print $3; exit}')
if [ -n "$GW" ] && curl -s -m 2 -o /dev/null "http://$GW:8080/status/"; then
    printf '  OK       phone API server at %s:8080\n' "$GW"
else
    printf '  absent   phone API server (gateway %s) -- fine off the drone WiFi\n' "${GW:-none}"
fi
echo
[ "$MISS" -eq 0 ] && echo "PREFLIGHT PASS" || { echo "PREFLIGHT: $MISS required item(s) MISSING"; exit 1; }
