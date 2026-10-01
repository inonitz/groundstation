#!/usr/bin/env python3
"""Save SAM3 ONCE in its nf4 form (owner S7 c, 2026-09-29), so the app loads the ready
4-bit weights instead of quantizing the bf16 checkpoint at every start. Reads
config.SAM3_MODEL_DIR, writes config.SAM3_NF4_DIR (weights, config with its
quantization settings, and the processor). Needs the GPU (bitsandbytes quantizes on
CUDA). tools/devenv/install-runtime-deps.sh runs it when the folder is missing.

    python3 /root/groundstation/projects/integration_harden2/sam3/save_nf4.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config  # noqa: E402
from sam3.model import Sam3Backend  # noqa: E402


def main():
    sam3 = Sam3Backend(model_dir=config.SAM3_MODEL_DIR, quantize=True)
    os.makedirs(config.SAM3_NF4_DIR, exist_ok=True)
    sam3.model.save_pretrained(config.SAM3_NF4_DIR)
    sam3.proc.save_pretrained(config.SAM3_NF4_DIR)
    print(f"[sam3] saved the nf4 model to {config.SAM3_NF4_DIR}", flush=True)
    return


if __name__ == "__main__":
    main()
