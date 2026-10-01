"""Shared helpers for the SAM3 video-tracking measurements: the frames, the nf4 loader
(the same BitsAndBytesConfig as perception2's Sam3Backend), percentiles and the
memory readings."""
import glob
import json
import os
import time

import cv2
import torch
from PIL import Image
from transformers import BitsAndBytesConfig

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
SAM3_DIR = "/root/models/vision/sam3-official"
# 117 real indoor frames (640x480), a continuous desk sequence
DESK_FRAMES = "/root/models/vision/sam3-desk-frames"


def nf4():
    """sam3/model.py's quantization, unchanged."""
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True
    )


def frames(n, width=0, height=0):
    """The first n desk frames as RGB PIL images, optionally resized."""
    out = []
    image = None
    for path in sorted(glob.glob(os.path.join(DESK_FRAMES, "*.jpg")))[:n]:
        image = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
        if width:
            image = cv2.resize(image, (width, height))
        out.append(Image.fromarray(image))
    return out


def real_boxes(path, width=640, height=480):
    """The boxes of real_boxes.py's file, clamped to the frame."""
    with open(path) as src:
        found = json.load(src)
    out = []
    for item in found:
        x0, y0, x1, y1 = item["box"]
        out.append([max(0.0, x0), max(0.0, y0), min(width, x1), min(height, y1)])
    return out


def pct(values, q):
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(q / 100 * (len(ordered) - 1))))]


def stats(values):
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "p50": round(pct(values, 50), 1),
        "p95": round(pct(values, 95), 1),
        "max": round(max(values), 1),
    }


def mib(n_bytes):
    return round(n_bytes / 2**20)


def gpu_used_mib():
    """What the whole process holds on the GPU (the CUDA context included)."""
    free, total = torch.cuda.mem_get_info()
    return mib(total - free)


def timed(fn):
    """-> (result, ms), with a CUDA sync on both sides."""
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    out = fn()
    torch.cuda.synchronize()
    return out, (time.perf_counter() - t0) * 1000


def write_result(name, data):
    path = os.path.join(RESULTS, f"{time.strftime('%Y-%m-%d')}-{name}.json")
    with open(path, "w") as out:
        json.dump(data, out, indent=1)
    print("wrote", path, flush=True)
    return path
