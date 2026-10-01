#!/usr/bin/env bash
# A headless Chromium to SEE the labelling page (owner B4 (8), 2026-09-30).
# Its own folder outside the repo (pip --target; this Python has no venv module): never
# the main torch/transformers environment.
#   bash /root/groundstation/tools/asr-verify-transcript/install-browser.sh
# Then: PYTHONPATH=/root/.venvs/asr-verify-browser python3 \
#         /root/groundstation/tools/asr-verify-transcript/screenshots.py
set -euo pipefail
TARGET=/root/.venvs/asr-verify-browser
mkdir -p "$TARGET"
python3 -m pip install --quiet --target "$TARGET" --upgrade "playwright==1.55.0"
# the browser and the system libraries it needs (apt, as root in the dev container)
PYTHONPATH="$TARGET" python3 -m playwright install --with-deps chromium
echo "ready: PYTHONPATH=$TARGET python3 ..."
