"""One image encoding shared by every concept of a phrase. Sam3Backend runs the whole
model once per concept, so "dresser" (three concepts) encodes the same frame three
times. Sam3Model.forward accepts vision_embeds, so the frame can be encoded once
(get_vision_features) and each concept runs only the text and detector parts.
Measures both ways on the same frames and checks that they return the same boxes.
GPU: ~1 min. Run: python3 bench/sam3-assessment/reuse.py"""
import time

import numpy as np
import torch
from PIL import Image

import common
from sam3.model import Sam3Backend

REPS = 12
CONCEPTS = [c.strip() for c in common.PHRASE_THREE.split(",")]


def post(sam3, out, sizes):
    result = sam3.proc.post_process_instance_segmentation(
        out,
        threshold=0.3,
        mask_threshold=sam3.mask_threshold,
        target_sizes=sizes
    )[0]
    return result["boxes"].float().cpu().numpy()


def per_concept(sam3, pil):
    """Today's path: the full model once per concept -> boxes per concept."""
    boxes = []
    inputs = None
    for concept in CONCEPTS:
        inputs = sam3.proc(images=pil, text=concept, return_tensors="pt").to("cuda")
        inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
        with torch.no_grad():
            out = sam3.model(**inputs)
        boxes.append(post(sam3, out, inputs["original_sizes"].tolist()))
    return boxes


def shared(sam3, pil, timing):
    """The image encoded once; per concept only the text and the detector."""
    boxes = []
    image = sam3.proc(images=pil, return_tensors="pt").to("cuda")
    t0 = time.perf_counter()
    with torch.no_grad():
        embeds = sam3.model.get_vision_features(image["pixel_values"].to(torch.bfloat16))
    torch.cuda.synchronize()
    timing.append(common.ms_since(t0))
    text = None
    out = None

    for concept in CONCEPTS:
        text = sam3.proc(text=concept, return_tensors="pt").to("cuda")
        with torch.no_grad():
            out = sam3.model(
                vision_embeds=embeds,
                input_ids=text["input_ids"],
                attention_mask=text["attention_mask"]
            )
        boxes.append(post(sam3, out, image["original_sizes"].tolist()))
    return boxes


def same(a, b):
    """Same number of boxes per concept, each within 2 px."""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x.shape != y.shape:
            return False
        if x.size and np.abs(x - y).max() > 2:
            return False
    return True


def main():
    frames = common.frames(8)
    sam3 = Sam3Backend()
    rows = {"per_concept": [], "shared": [], "encode_only": []}
    match = 0
    pil = None
    t0 = 0.0
    a = None
    b = None

    per_concept(sam3, Image.fromarray(frames[0][:, :, ::-1]))      # warm-up
    shared(sam3, Image.fromarray(frames[0][:, :, ::-1]), [])
    for i in range(REPS):
        pil = Image.fromarray(frames[i % len(frames)][:, :, ::-1])
        t0 = time.perf_counter()
        a = per_concept(sam3, pil)
        rows["per_concept"].append(common.ms_since(t0))
        t0 = time.perf_counter()
        b = shared(sam3, pil, rows["encode_only"])
        rows["shared"].append(common.ms_since(t0))
        match += int(same(a, b))
    results = {"reps": REPS, "concepts": CONCEPTS, "same_boxes": f"{match}/{REPS}"}
    for key, values in rows.items():
        results[key] = common.stats(values)
        print(f"{key:12s} {results[key]}", flush=True)
    print("same boxes", results["same_boxes"], flush=True)
    common.write_result("reuse", results)
    return


if __name__ == "__main__":
    main()
