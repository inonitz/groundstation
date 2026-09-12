#!/bin/bash
# Isolated setup for the SOTA monocular-depth benchmark (Depth Pro / Depth Anything 3 / Metric3D).
# Depth Pro ships in transformers 5.15.1. DA3 needs the depth-anything-3 pkg; Metric3D (torch.hub) needs mmengine.
# The Debian-managed psutil cannot be uninstalled by pip, so pre-install a fresh copy with --ignore-installed.
set -e
cd "$(dirname "$0")"
pip install --break-system-packages --ignore-installed --quiet psutil 2>&1 | tail -1 || true
echo "[setup] installing depth-anything-3 + mmengine ..."
pip install --break-system-packages --quiet "depth-anything-3==0.1.1" "mmengine" 2>&1 | tail -3 || true
python3 - <<'PY'
ok=[]
for name,mod in [("da3","depth_anything_3"),("mmengine","mmengine")]:
    try: __import__(mod); ok.append(name)
    except Exception as e: print(name,"FAIL:",repr(e)[:140])
try:
    from transformers import DepthProForDepthEstimation; ok.append("depthpro")
except Exception as e: print("depthpro FAIL:",repr(e)[:140])
print("[setup] ready:", ok)
PY
