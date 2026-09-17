#!/bin/bash
# install-translation-models.sh -- fetch the qwen2.5-coder phone-parser bench model into
# /root/models/translate. The HE<->EN translation models (opus-mt/nllb/madlad400/translategemma) were
# REMOVED 2026-09-17: the translated path is retired (unified_bench runs Gemma direct-Hebrew,
# MVD_TRANSLATOR=none). WARNING (2026-09-02): /root/models/translate is NOT volume-mounted by default;
# add the host mount (like asr/vlm/vision) or downloads die on every devenv rebuild.
set -euo pipefail
if ! mountpoint -q /root/models/translate; then
  echo "WARNING: /root/models/translate is NOT a mount -- downloads will be wiped on rebuild." >&2
  if [ "${FORCE_EPHEMERAL:-0}" != "1" ]; then
    echo "Add the host mount first (see header), or rerun with FORCE_EPHEMERAL=1 to accept ephemeral." >&2
    exit 1
  fi
fi
# qwen2.5-coder-1.5b-instruct q4_0 -- the exoskeletons app's on-phone "Deep Think" parser model;
# pulled to bench the PRODUCTION model+prompt combo on the box (added 2026-09-01)
python3 - << 'PY'
from huggingface_hub import hf_hub_download
p = hf_hub_download("Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF", "qwen2.5-coder-1.5b-instruct-q4_0.gguf",
                    local_dir="/root/models/translate/qwen2.5-coder-1.5b-gguf")
print("ok:", p)
PY
