#!/bin/bash
# install-runtime-deps.sh -- runtime dependencies the demos need that the devenv image does not bake yet.
#
# The container WIPES ad-hoc installs on rebuild, so ALWAYS add here, never install by hand
# (CLAUDE.md: script every install). These are also baked into tools/devenv/Dockerfile; this script
# covers already-built containers until their next rebuild. Run it after every rebuild.
#
# Sections: (1) system packages, (2) python packages, (3) phonikud model files, (4) offline HF cache,
# (5) a self-test that fails loud if any library did not install and load.
set -euo pipefail

# --- 1. system packages (apt) -------------------------------------------------------------
# espeak-ng: backs phonemizer-fork, a phonikud dependency.  libportaudio2: native lib sounddevice
# needs to play the phonikud audio (aplay retired 2026-09-21).  fonts-freefont-ttf: FreeMono, the only
# mono font with Hebrew glyphs (overlay tag column).  alsa-utils: legacy audio tools.
echo "[install-runtime-deps] 1/5 system packages..."
apt-get install -y espeak-ng alsa-utils libportaudio2 fonts-freefont-ttf

# --- 2. python packages (pip) -------------------------------------------------------------
echo "[install-runtime-deps] 2/5 python packages..."
pip install aiohttp                                          # tools/dji_mock/mock_apiserver.py
pip install python-bidi                                      # right-to-left Hebrew in the scene overlay
pip install "bitsandbytes==0.50.2" "accelerate==1.14.0"      # SAM3-nf4 backend; pins match sam3-mask-bench/setup.sh
pip install phonikud phonikud-onnx phonikud-tts sounddevice  # offline Hebrew TTS (SCENE_TTS=phonikud) + playback

# --- 3. phonikud model files --------------------------------------------------------------
# phonikud G2P (niqqud+stress -> IPA) + the Piper onnx voice. Models are cc-nc (SASpeech/ILSpeech),
# demo/competition use only (docs decision 2026-09-16). Downloaded once, then reused.
echo "[install-runtime-deps] 3/5 phonikud model files..."
P=/root/models/tts/phonikud
mkdir -p "$P"
[ -f "$P/phonikud-1.0.int8.onnx" ] || wget -O "$P/phonikud-1.0.int8.onnx" https://huggingface.co/Phonikud/phonikud-onnx/resolve/main/phonikud-1.0.int8.onnx
[ -f "$P/model.onnx" ]            || wget -O "$P/model.onnx"            https://huggingface.co/Phonikud/phonikud-tts-checkpoints/resolve/main/model.onnx
[ -f "$P/model.config.json" ]     || wget -O "$P/model.config.json"     https://huggingface.co/Phonikud/phonikud-tts-checkpoints/resolve/main/model.config.json

# --- 4. warm the offline HF cache ---------------------------------------------------------
# The phonikud G2P loads the dicta-il/dictabert tokenizer from the HF cache, which a rebuild wipes.
# Fetch it now (online) so the field run works OFFLINE. Non-fatal: the field can still fetch it later.
echo "[install-runtime-deps] 4/5 warm the offline HF cache..."
python3 -c "from tokenizers import Tokenizer; Tokenizer.from_pretrained('dicta-il/dictabert-large-char-menaked')" || true

# --- 5. self-test: fail loud if a runtime library did not install and load ----------------
echo "[install-runtime-deps] 5/5 self-test..."
python3 - <<'PYTEST'
import sounddevice                              # raises OSError if the native PortAudio lib is missing
import phonikud_onnx, phonikud, phonikud_tts    # the offline Hebrew TTS stack
import bitsandbytes, accelerate                 # the SAM3-nf4 stack
print(f"[selftest] OK: sounddevice ({len(sounddevice.query_devices())} audio devices), phonikud, bitsandbytes")
PYTEST

echo "[install-runtime-deps] done"
