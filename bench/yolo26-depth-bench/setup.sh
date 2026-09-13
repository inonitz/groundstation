#!/bin/bash
# Isolated deps for the yolo26-depth benchmark, installed into ./libs (no venv -> no apt needed).
# Pins onnxruntime==1.20.1 to MATCH the runtime the FMU links (build/.../onnxruntime-linux-x64-1.20.1).
set -e
cd "$(dirname "$0")"
python3 -m pip install --target ./libs --upgrade "onnxruntime==1.20.1" "numpy>=1.24" 2>&1 | tail -3
PYTHONPATH=./libs python3 -c 'import onnxruntime as o; print("[setup] onnxruntime", o.__version__, o.get_available_providers())'
