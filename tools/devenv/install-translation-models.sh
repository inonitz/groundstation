#!/bin/bash
# install-translation-models.sh -- fetch the HE<->EN translation models (backlog B/D) into
# /root/models/translate (volume-mounted, survives container rebuilds). Idempotent.
set -euo pipefail
python3 - << 'PY'
from huggingface_hub import snapshot_download
for repo in ("Helsinki-NLP/opus-mt-tc-big-he-en",
             "Helsinki-NLP/opus-mt-en-he",
             "facebook/nllb-200-distilled-600M"):
    p = snapshot_download(repo, local_dir=f"/root/models/translate/{repo.split('/')[-1]}")
    print("ok:", p)
PY
# madlad400-3b-mt Q4_K_M GGUF (Google 2023 multilingual MT, runs on our llama-server; added 2026-09-01)
python3 - << 'PY'
from huggingface_hub import hf_hub_download
p = hf_hub_download("mtsdurica/madlad400-3b-mt-Q4_K_M-GGUF", "madlad400-3b-mt-q4_k_m.gguf",
                    local_dir="/root/models/translate/madlad400-3b-mt-gguf")
print("ok:", p)
PY
# TranslateGemma-4B-it Q4_K_M (Google 2026-01, translation-tuned Gemma; added 2026-09-01)
python3 - << 'PY'
from huggingface_hub import hf_hub_download
p = hf_hub_download("mradermacher/translategemma-4b-it-GGUF", "translategemma-4b-it.Q4_K_M.gguf",
                    local_dir="/root/models/translate/translategemma-4b-it-gguf")
print("ok:", p)
PY
# qwen2.5-coder-1.5b-instruct q4_0 -- the exoskeletons app's on-phone "Deep Think" parser model;
# pulled to bench the PRODUCTION model+prompt combo on the box (added 2026-09-01)
python3 - << 'PY'
from huggingface_hub import hf_hub_download
p = hf_hub_download("Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF", "qwen2.5-coder-1.5b-instruct-q4_0.gguf",
                    local_dir="/root/models/translate/qwen2.5-coder-1.5b-gguf")
print("ok:", p)
PY
