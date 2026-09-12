#!/bin/bash
# install-runtime-deps.sh -- python/runtime deps the demos need that the devenv image does not
# bake yet. Baked into tools/devenv/Dockerfile on 2026-09-02 -- this script covers
# already-built containers until their next image rebuild. The container WIPES ad-hoc installs on rebuild -- run this after every rebuild, and
# add to it instead of installing by hand (CLAUDE.md: script every install).
set -euo pipefail
pip install aiohttp        # tools/dji_mock/mock_apiserver.py
pip install sentencepiece  # Marian/NLLB tokenizers (HE<->EN translation, backlog B/D)
pip install python-bidi   # RTL Hebrew rendering in the scene_omdet chat overlay
apt-get install -y fonts-freefont-ttf   # FreeMono: only mono font with Hebrew glyphs (overlay columns)
# SAM3-nf4 (perception2 highlight backend, SCENE_SEG=sam3): bitsandbytes nf4 needs accelerate.
# Same pins as tools/bench/sam3-mask-bench/setup.sh (the SAM3 dependency source of truth).
pip install "bitsandbytes==0.50.2" "accelerate==1.14.0"
# TTS chain (projects/integration_tts voice-out) -- piper + espeak-ng + aplay; the piper voice
# files live outside the repo. TODO(C5c): fold the full TTS install (binary + voice + alsa) here.
echo "[install-runtime-deps] done"
