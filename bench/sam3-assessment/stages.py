"""Where one SAM3 forward spends its time: the BGR->RGB image, the processor (resize and
normalize on the CPU), the copy to the GPU, the model forward, and the post-processing
(masks at the frame size, back to numpy). The steps are Sam3Backend._run's, timed with a
CUDA sync after each.
GPU: ~1 min. Run: python3 bench/sam3-assessment/stages.py"""
import time

import torch
from PIL import Image

import common
from sam3.model import Sam3Backend

REPS = 16
STEPS = ("rgb", "processor", "to_gpu", "forward", "post", "total")


def one_pass(sam3, frame, concept):
    """One forward, as Sam3Backend._run does it -> {step: ms}."""
    marks = [time.perf_counter()]
    pil = Image.fromarray(frame[:, :, ::-1])
    marks.append(time.perf_counter())
    inputs = sam3.proc(images=pil, text=concept, return_tensors="pt")
    marks.append(time.perf_counter())
    inputs = inputs.to("cuda")
    inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
    torch.cuda.synchronize()
    marks.append(time.perf_counter())
    with torch.no_grad():
        out = sam3.model(**inputs)
    torch.cuda.synchronize()
    marks.append(time.perf_counter())
    result = sam3.proc.post_process_instance_segmentation(
        out,
        threshold=0.3,
        mask_threshold=sam3.mask_threshold,
        target_sizes=inputs.get("original_sizes").tolist()
    )[0]
    result["masks"].cpu().numpy()
    marks.append(time.perf_counter())
    row = {}

    for i, step in enumerate(STEPS[:-1]):
        row[step] = (marks[i + 1] - marks[i]) * 1000
    row["total"] = (marks[-1] - marks[0]) * 1000
    return row


def main():
    frames = common.frames(8)
    sam3 = Sam3Backend()
    results = {"reps": REPS, "concept": "person"}
    rows = []

    one_pass(sam3, frames[0], "person")                       # warm-up
    for i in range(REPS):
        rows.append(one_pass(sam3, frames[i % len(frames)], "person"))
    for step in STEPS:
        results[step] = common.stats([row[step] for row in rows])
        print(f"{step:10s} {results[step]}", flush=True)
    common.write_result("stages", results)
    return


if __name__ == "__main__":
    main()
