"""SAM3 video tracking through transformers, in nf4, on real video (the desk frames),
streamed one frame at a time as a live camera would give them.

  text:  Sam3VideoModel. A text prompt finds the objects and tracks them.
  boxes: Sam3TrackerVideoModel. N boxes on the first frame (a grid) are tracked.

Measured per run: the load memory, the peak GPU memory (torch's allocator peak and the
whole process), ms per frame, the objects tracked, and the memory after 10, 50 and the
last frame (does the state grow with the frames tracked?). --state cpu keeps the
tracking state in CPU memory.
GPU. Run: python3 bench/sam3-video/video_track.py text --prompt person --frames 60"""
import argparse
import resource

import torch

import common


def load(mode):
    if mode == "text":
        from transformers import Sam3VideoModel as Model
        from transformers import Sam3VideoProcessor as Processor
    else:
        from transformers import Sam3TrackerVideoModel as Model
        from transformers import Sam3TrackerVideoProcessor as Processor
    model = Model.from_pretrained(
        common.SAM3_DIR,
        quantization_config=common.nf4(),
        dtype=torch.bfloat16
    ).eval()
    return model, Processor.from_pretrained(common.SAM3_DIR)


def grid_boxes(n, width, height):
    """n boxes on a square grid over the frame, each half its cell."""
    side = 1
    while side * side < n:
        side += 1
    cell_w = width / side
    cell_h = height / side
    boxes = []
    for i in range(n):
        x = (i % side) * cell_w + cell_w / 4
        y = (i // side) * cell_h + cell_h / 4
        boxes.append([x, y, x + cell_w / 2, y + cell_h / 2])
    return boxes


def prune(session, frame_idx, keep):
    """Drop what the tracker will never read again: the outputs of the non-conditioning
    frames older than `keep` frames (memory attention reads the last num_maskmem - 1 = 6,
    object pointers the last 16), and the stored input frames older than `keep` frames
    (Sam3VideoModel reads earlier input frames: dropping all but the last one changed its
    masks from frame 3 on, 2026-09-29)."""
    old = []
    for per_obj in session.output_dict_per_obj.values():
        frames = per_obj["non_cond_frame_outputs"]
        old = [f for f in frames if f < frame_idx - keep]
        for f in old:
            del frames[f]
    stored = session.processed_frames or {}
    old = [f for f in stored if f < frame_idx - keep]
    for f in old:
        del stored[f]
    return


def mask_areas(mode, out):
    """Per object, the positive pixels of its mask: a fingerprint to compare runs."""
    if mode == "text":
        masks = list(out.obj_id_to_mask.values())
    else:
        masks = list(out.pred_masks)
    return [int((m > 0).sum()) for m in masks]


def run(args):
    model, proc = load(args.mode)
    load_mib = common.gpu_used_mib()
    video = common.frames(args.frames, args.width, args.height)
    session = proc.init_video_session(
        inference_device="cuda",
        inference_state_device=args.state,
        processing_device="cpu",
        video_storage_device="cpu",
        dtype=torch.bfloat16
    )
    boxes = grid_boxes(args.objects, video[0].width, video[0].height)
    if args.boxes_file:
        boxes = common.real_boxes(args.boxes_file)
        args.objects = len(boxes)
    if args.mode == "text":
        # a comma-separated --prompt is several text prompts, tracked together
        proc.add_text_prompt(session, [t.strip() for t in args.prompt.split(",")])
    torch.cuda.reset_peak_memory_stats()
    rows = []
    areas = []
    marks = {}
    out = None
    ms = 0.0

    for i, image in enumerate(video):
        inputs = proc(images=image, return_tensors="pt")
        pixels = inputs.pixel_values[0].to("cuda", torch.bfloat16)
        if args.mode == "boxes" and i == 0:
            proc.add_inputs_to_inference_session(
                inference_session=session,
                frame_idx=0,
                obj_ids=list(range(1, args.objects + 1)),
                input_boxes=[boxes],
                original_size=inputs.original_sizes[0]
            )
        with torch.inference_mode():
            out, ms = common.timed(
                # an explicit frame index: after a prune, len(stored frames) is not it
                lambda: model(inference_session=session, frame=pixels, frame_idx=i)
            )
        objects = len(out.object_ids) if args.mode == "text" else args.objects
        rows.append({"frame": i, "ms": ms, "objects": objects})
        areas.append(mask_areas(args.mode, out))
        if args.keep:
            prune(session, i, args.keep)
        if i + 1 in (10, 50, args.frames):
            marks[i + 1] = {
                "allocated_mib": common.mib(torch.cuda.memory_allocated()),
                "process_mib": common.gpu_used_mib(),
            }
    steady = [r["ms"] for r in rows[1:]]
    objects = [r["objects"] for r in rows]
    return {
        "mode": args.mode,
        "prompt": args.prompt if args.mode == "text" else None,
        "objects_asked": args.objects if args.mode == "boxes" else None,
        "objects_tracked_p50": common.pct(objects, 50),
        "objects_tracked_max": max(objects),
        "frames": args.frames,
        "frame_size": list(video[0].size),
        "state_device": args.state,
        "keep_frames": args.keep,
        "load_process_mib": load_mib,
        "peak_allocated_mib": common.mib(torch.cuda.max_memory_allocated()),
        "end_process_mib": common.gpu_used_mib(),
        "memory_by_frames_tracked": marks,
        "first_frame_ms": round(rows[0]["ms"], 1),
        "ms_per_frame": common.stats(steady),
        "cpu_rss_max_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
        "mask_areas": areas,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("text", "boxes"))
    parser.add_argument("--prompt", default="person")
    parser.add_argument("--objects", type=int, default=1)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--state", default="cuda", choices=("cuda", "cpu"))
    # real object boxes (real_boxes.py) instead of the grid
    parser.add_argument("--boxes-file", default="")
    # 0 keeps every frame's state (the transformers default); N prunes older frames
    parser.add_argument("--keep", type=int, default=0)
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)
    args = parser.parse_args()
    result = run(args)
    for key, value in result.items():
        if key == "mask_areas":
            continue
        print(f"{key:26s} {value}", flush=True)
    tag = f"{args.objects}obj" + ("-real" if args.boxes_file else "")
    if args.mode == "text":
        tag = args.prompt.replace(" ", "").replace(",", "+")
    size = f"-{args.width}x{args.height}" if args.width else ""
    name = f"{args.mode}-{tag}-{args.frames}f-{args.state}-keep{args.keep}{size}"
    common.write_result(name, result)
    return


if __name__ == "__main__":
    main()
