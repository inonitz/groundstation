#!/usr/bin/env bash
# The SAM3.1 runtime (facebookresearch/sam3, the only code that builds the multiplex model)
# in its own package folder. The container has no python3-venv (ensurepip), so the
# isolated environment is a --target folder put first on PYTHONPATH by run_sam31.sh.
# It never changes the main environment's torch, transformers or bitsandbytes: sam3
# installs with --no-deps, and only the packages sam3 imports and the main environment
# lacks go into the folder.
# Run: bash /root/groundstation/bench/sam3-video/setup_sam31_venv.sh
set -euo pipefail
TARGET=/root/venvs/sam31
ARCHIVE=https://github.com/facebookresearch/sam3/archive/refs/heads/main.zip

mkdir -p "$TARGET"
python3 -m pip install --no-deps --target "$TARGET" "$ARCHIVE"
for pkg in timm ftfy iopath hydra-core omegaconf portalocker einops pycocotools wcwidth antlr4-python3-runtime==4.9.3; do
    mod=${pkg%%==*}; mod=${mod//-/_}
    [ "$mod" = hydra_core ] && mod=hydra
    [ "$mod" = antlr4_python3_runtime ] && mod=antlr4
    PYTHONPATH="$TARGET" python3 -c "import $mod" 2>/dev/null \
        || python3 -m pip install --no-deps --target "$TARGET" "$pkg"
done
PYTHONPATH="$TARGET" python3 -c \
    "import torch, sam3; print('sam3 from', sam3.__file__, 'torch', torch.__version__)"
