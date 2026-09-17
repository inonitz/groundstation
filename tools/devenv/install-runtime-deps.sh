#!/bin/bash
# install-runtime-deps.sh -- python/runtime deps the demos need that the devenv image does not
# bake yet. Baked into tools/devenv/Dockerfile on 2026-09-02 -- this script covers
# already-built containers until their next image rebuild. The container WIPES ad-hoc installs on rebuild -- run this after every rebuild, and
# add to it instead of installing by hand (CLAUDE.md: script every install).
set -euo pipefail
pip install aiohttp        # tools/dji_mock/mock_apiserver.py
pip install python-bidi   # RTL Hebrew rendering in the scene_omdet chat overlay
apt-get install -y fonts-freefont-ttf   # FreeMono: only mono font with Hebrew glyphs (overlay columns)
apt-get install -y espeak-ng alsa-utils   # aplay (alsa-utils) plays the phonikud audio; espeak-ng backs phonemizer-fork (a phonikud dep). Baked in Dockerfile too.
# SAM3-nf4 (perception2 highlight backend, SCENE_SEG=sam3): bitsandbytes nf4 needs accelerate.
# Same pins as tools/bench/sam3-mask-bench/setup.sh (the SAM3 dependency source of truth).
pip install "bitsandbytes==0.50.2" "accelerate==1.14.0"
# Phonikud offline Hebrew TTS (SCENE_TTS=phonikud): G2P (niqqud+stress -> IPA) + Piper onnx voice.
# Models are cc-nc (SASpeech/ILSpeech) -- demo/competition use only (docs decision 2026-09-16).
pip install phonikud phonikud-onnx phonikud-tts
mkdir -p /root/models/tts/phonikud
P=/root/models/tts/phonikud
[ -f "$P/phonikud-1.0.int8.onnx" ] || wget -O "$P/phonikud-1.0.int8.onnx" https://huggingface.co/Phonikud/phonikud-onnx/resolve/main/phonikud-1.0.int8.onnx
[ -f "$P/model.onnx" ]            || wget -O "$P/model.onnx"            https://huggingface.co/Phonikud/phonikud-tts-checkpoints/resolve/main/model.onnx
[ -f "$P/model.config.json" ]     || wget -O "$P/model.config.json"     https://huggingface.co/Phonikud/phonikud-tts-checkpoints/resolve/main/model.config.json
# Warm the HF cache: the phonikud G2P loads the dicta-il/dictabert-large-char-menaked tokenizer from
# the HF cache, which a container rebuild wipes. Fetch it now (online) so the field runs OFFLINE.
python3 -c "from tokenizers import Tokenizer; Tokenizer.from_pretrained('dicta-il/dictabert-large-char-menaked')" || true
# The harden2 Hebrew voice is phonikud (above) or the phone; espeak/piper backends were removed
# (Hebrew-only, 2026-09-17). The old piper-CLI chain (projects/integration_tts) is not installed here.
echo "[install-runtime-deps] done"
