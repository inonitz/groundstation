#!/usr/bin/env bash
# Desk-test preflight. Checks every precondition BEFORE boot and fails loudly if one is missing.
# Read-only: it starts nothing. up.sh calls this first; the owner may also run it alone.
#
#   bash preflight.sh              # dji video (default), mock control
#   VIDEO=webcam bash preflight.sh # webcam video (skips the phone/video checks)
set -uo pipefail

VIDEO="${VIDEO:-dji}"
BIN=/root/groundstation/build/release/shared/dji/bin
ASR_MODEL="${ASR_MODEL_PATH:-/root/models/asr/ivrit_ai/whisper-large-v3-turbo/ggml-model-q5_k.bin}"
# Phone IP = the WiFi gateway. Derive from the WIRELESS interface so a second (wired) default
# route cannot supply the wrong gateway. Override with PHONE_IP=<ip>.
phone_ip_wifi() {
    local i gw
    for i in $(ls /sys/class/net 2>/dev/null); do
        [ -d "/sys/class/net/$i/wireless" ] || continue
        gw=$(ip route show default dev "$i" 2>/dev/null | awk '{print $3; exit}')
        [ -n "$gw" ] && { echo "$gw"; return; }
    done
}
PHONE_IP="${PHONE_IP:-$(phone_ip_wifi)}"
FAIL=0
ok(){   echo "  OK   $*"; }
bad(){  echo "  FAIL $*"; FAIL=1; }

echo "== ports must be FREE (nothing listening yet) =="
for p in 18090 18091 8079 8080 5600; do
    if ss -tln 2>/dev/null | grep -q ":$p "; then bad "port $p is already in use"; else ok "port $p free"; fi
done

echo "== binaries present =="
for b in llm_to_action_asr_server llm_to_action_keyboard_hook llm_to_action_gstreamer_rx whisper-quantize; do
    [ -x "$BIN/$b" ] && ok "$b" || bad "$b missing in $BIN"
done

echo "== models present =="
[ -f "$ASR_MODEL" ] && ok "Hebrew ASR model: $ASR_MODEL" || bad "Hebrew ASR model MISSING: $ASR_MODEL  (run quantize_hebrew_asr.sh)"
for m in /root/models/vlm/Qwen3-VL-4B-Instruct/Qwen3-VL-4B-Instruct-Q4_K_M.gguf \
         /root/models/vlm/Qwen3-VL-4B-Instruct/mmproj-BF16.gguf \
         /root/models/asr/dictalm-3-1.7b/dictalm-3.0-1.7b-instruct-q4_k_m.gguf \
         /root/models/vision/sam2.1_b.pt; do
    [ -f "$m" ] && ok "$(basename "$m")" || bad "model MISSING: $m"
done

echo "== tools =="
for t in tmux python3 script; do command -v "$t" >/dev/null 2>&1 && ok "$t" || bad "$t not installed"; done

if [ "$VIDEO" = "dji" ]; then
    echo "== phone reachable (video source) =="
    echo "  (derived phone IP = ${PHONE_IP:-<none>}; override with PHONE_IP=<ip>)"
    if [ -z "$PHONE_IP" ]; then
        bad "PHONE_IP unset and no default route. Set PHONE_IP=<phone ip>."
    else
        code=$(curl -s -m 3 -o /dev/null -w '%{http_code}' "http://$PHONE_IP:8080/status/" 2>/dev/null)
        if echo "$code" | grep -q '^2'; then
            ok "phone API server up at $PHONE_IP:8080 (GET /status/ $code; frames confirmed post-boot by status.sh)"
        elif [ "$code" = "000" ] || [ -z "$code" ]; then
            bad "phone $PHONE_IP:8080 not answering. Turn the API Server toggle ON. (ICMP is blocked; we test :8080, not ping.)"
        else
            bad "phone $PHONE_IP:8080 answered HTTP $code (server up, drone/API NOT ready). Reconnect the drone to the app, then toggle API Server OFF then ON."
        fi
    fi
fi

echo "== display (scene window needs one) =="
[ -n "${DISPLAY:-}" ] && ok "DISPLAY=$DISPLAY" || bad "DISPLAY unset. The scene window needs a display."

echo
if [ "$FAIL" = "0" ]; then echo "PREFLIGHT: PASS"; exit 0; else echo "PREFLIGHT: FAIL (fix the FAIL lines above before boot)"; exit 1; fi
