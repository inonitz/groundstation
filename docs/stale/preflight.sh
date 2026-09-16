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
        [ -n "$gw" ] && { echo "$gw"; return 0; }
    done
    return 0    # no wireless gateway -> empty output, but NEVER a non-zero status (set -e safe)
}
PHONE_IP="${PHONE_IP:-$(phone_ip_wifi)}"
FAIL=0
ok(){   echo "  OK   $*"; }
bad(){  echo "  FAIL $*"; FAIL=1; }

echo "== ports must be FREE (nothing listening yet) =="
for p in 18090 8079 8080 5600; do
    if ss -tln 2>/dev/null | grep -q ":$p "; then
        holder=$(ss -tlnpH "sport = :$p" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1)
        if [ -n "$holder" ]; then
            bad "port $p is in use by pid $holder ($(tr '\0' ' ' < /proc/$holder/cmdline 2>/dev/null | cut -c1-60)) -- run down.sh"
        else
            uid=$(awk -v hp=$(printf '%04X' $p) '$2 ~ ":"hp"$" && $4=="0A" {print $8; exit}' /proc/net/tcp)
            bad "port $p is held by a process OUTSIDE this container (uid ${uid:-?}); down.sh cannot reach it. On the HOST: sudo ss -tlnp | grep :$p  then kill that pid."
        fi
    else ok "port $p free"; fi
done

echo "== binaries present =="
for b in llm_to_action_asr_server llm_to_action_keyboard_hook llm_to_action_gstreamer_rx; do
    [ -x "$BIN/$b" ] && ok "$b" || bad "$b missing in $BIN"
done

echo "== models present =="
[ -f "$ASR_MODEL" ] && ok "Hebrew ASR model: $ASR_MODEL" || bad "Hebrew ASR model MISSING: $ASR_MODEL  (run quantize_hebrew_asr.sh)"
for m in /root/models/vlm/Gemma-4-E4B/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf \
         /root/models/vlm/Gemma-4-E4B/mmproj-BF16.gguf; do
    [ -f "$m" ] && ok "$(basename "$m")" || bad "model MISSING: $m"
done

SEG="${SCENE_SEG:-sam3}"   # harden2: Gemma reads the Hebrew itself, no translator (MVD_HOME deleted)
if [ "${VIDEO:-dji}" = "webcam" ]; then
    echo "-- cameras (VIDEO=webcam; pick the CAPTURE line with a picture, then WEBCAM_DEV=<n>) --"
    for d in /sys/class/video4linux/video*; do n="${d##*video}"; [ -e "/dev/video$n" ] || mknod "/dev/video$n" c 81 "$n" 2>/dev/null || true; done
    python3 /root/groundstation/tools/desk-test/list_cams.py
fi
echo "== stack: Gemma 4 (no translator) + SAM3 seg=$SEG =="
ok "translator: none (harden2 -- Gemma 4 reads the Hebrew itself; MVD_PLANNER=${MVD_PLANNER:-gemma4})"
if [ "$SEG" = "sam3" ]; then
    [ -d /root/models/vision/sam3-official ] && ok "SAM3 model dir" || bad "SAM3 model dir MISSING: /root/models/vision/sam3-official"
    python3 -c "import bitsandbytes, accelerate" >/dev/null 2>&1 && ok "bitsandbytes + accelerate (SAM3-nf4)" \
        || bad "bitsandbytes/accelerate missing: bash /root/groundstation/tools/devenv/install-runtime-deps.sh"
fi

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
        echo "      gate watcher (eco -> 503): bash /root/groundstation/tools/dji_mock/watch_503.sh $PHONE_IP 10   or   bash /root/groundstation/tools/desk-test/status.sh --watch"
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
