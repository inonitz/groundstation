#!/bin/bash
# install-runtime-deps.sh -- python/runtime deps the demos need that the devenv image does not
# bake yet. The container WIPES ad-hoc installs on rebuild -- run this after every rebuild, and
# add to it instead of installing by hand (CLAUDE.md: script every install).
set -euo pipefail
pip install aiohttp        # tools/dji_mock/mock_apiserver.py
# TTS chain (projects/integration_tts voice-out) -- piper + espeak-ng + aplay; the piper voice
# files live outside the repo. TODO(C5c): fold the full TTS install (binary + voice + alsa) here.
echo "[install-runtime-deps] done"
