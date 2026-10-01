"""The boxes of the real objects on desk frame 0, found by SAM3 (nf4, image model), for
the trackers' real-object runs (--boxes-file). GPU, 30 s.
Run: python3 bench/sam3-video/real_boxes.py"""
import json
import os

import torch
from transformers import Sam3Model, Sam3Processor

import common

NOUNS = ("chair", "desk", "window", "cable")


def main():
    model = Sam3Model.from_pretrained(
        common.SAM3_DIR,
        quantization_config=common.nf4(),
        dtype=torch.bfloat16
    ).eval()
    proc = Sam3Processor.from_pretrained(common.SAM3_DIR)
    image = common.frames(1)[0]
    boxes = []
    inputs = None
    for noun in NOUNS:
        inputs = proc(images=image, text=noun, return_tensors="pt").to("cuda")
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
        with torch.no_grad():
            out = model(**inputs)
        found = proc.post_process_instance_segmentation(
            out,
            threshold=0.5,
            mask_threshold=0.5,
            target_sizes=inputs["original_sizes"].tolist()
        )[0]
        for box in found["boxes"].float().cpu().tolist():
            boxes.append({"label": noun, "box": [round(v, 1) for v in box]})
    path = os.path.join(common.RESULTS, "real_boxes_frame0.json")
    with open(path, "w") as out_file:
        json.dump(boxes, out_file, indent=1)
    print(len(boxes), "boxes ->", path, flush=True)
    return


if __name__ == "__main__":
    main()
