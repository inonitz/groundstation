"""SAM3.1 (Meta's code, nf4) measured like the SAM3 tracker rows of video_track.py: N
boxes on a grid over frame 0 of the desk video, tracked forward frame by frame, with and
without a limit on the stored per-frame state (--keep, like video_track.py's prune).

SAM3.1 takes an instance box as two corner points (labels 2 and 3, the SAM convention); a
box without obj_id would be a concept example for the detector, not an object to track.
GPU. Run:
  PYTHONPATH=/root/venvs/sam31 python3 bench/sam3-video/sam31_boxes.py --objects 16"""
import argparse
import resource
import time

import sam3.model.vitdet as vitdet
import torch
from sam3.model_builder import build_sam3_multiplex_video_predictor

import common
from sam31_track import CHECKPOINT, addmm_act_through_module, frame_folder, to_nf4
from video_track import grid_boxes

WIDTH = 640     # the desk frames
HEIGHT = 480


def prune(state, frame_idx, keep):
    """Drop the stored outputs of non-conditioning frames older than `keep` frames: in
    each tracker state (all objects and per object) and the per-frame mask cache."""
    stores = []
    old = []
    for tracker in state["sam2_inference_states"]:
        stores.append(tracker["output_dict"]["non_cond_frame_outputs"])
        for per_obj in tracker.get("output_dict_per_obj", {}).values():
            stores.append(per_obj["non_cond_frame_outputs"])
    stores.append(state.get("cached_frame_outputs", {}))
    for store in stores:
        old = [f for f in store if f < frame_idx - keep]
        for f in old:
            del store[f]
    return


def mask_areas(state, frame_idx):
    """Per object, the positive pixels of the tracker's own low-res mask on this frame.
    Meta's postprocessed output is empty after frame 0 for point/box-only sessions
    (out_obj_ids is empty although the tracker scores every object high, 2026-09-29), so
    the fingerprint reads the tracker state, as video_track.py reads pred_masks."""
    areas = []
    out = None
    for tracker in state["sam2_inference_states"]:
        out = tracker["output_dict"]["non_cond_frame_outputs"].get(frame_idx)
        if out is None:
            out = tracker["output_dict"]["cond_frame_outputs"].get(frame_idx)
        if out is None:
            continue
        for mask in out["pred_masks"]:
            areas.append(int((mask > 0).sum()))
    return areas


def build():
    predictor = build_sam3_multiplex_video_predictor(
        checkpoint_path=CHECKPOINT,
        use_fa3=False,
        async_loading_frames=False
    )
    # one frame per detector batch (the builder's 16-frame look-ahead ran out of memory)
    predictor.model.batched_grounding_batch_size = 1
    predictor.model.postprocess_batch_size = 1
    # The builder sets the text-prompt policy: hold outputs 15 frames (hotstart), confirm
    # each masklet against the detector, suppress tracks the detector does not match. Box
    # prompts have no text, so the detector matches nothing and every box was dropped
    # after frame 0 (2026-09-29). Back to the model class's defaults, a pure tracker.
    predictor.model.hotstart_delay = 0
    predictor.model.masklet_confirmation_enable = False
    predictor.model.suppress_unmatched_only_within_hotstart = True
    vitdet.addmm_act = addmm_act_through_module
    predictor.model.cpu()
    swapped = to_nf4(predictor.model, set())
    predictor.model.cuda()
    torch.cuda.empty_cache()
    return predictor, swapped


def add_boxes(predictor, session, boxes):
    for obj_id, (x0, y0, x1, y1) in enumerate(boxes, start=1):
        predictor.handle_request({
            "type": "add_prompt",
            "session_id": session,
            "frame_index": 0,
            "points": [[x0 / WIDTH, y0 / HEIGHT], [x1 / WIDTH, y1 / HEIGHT]],
            "point_labels": [2, 3],
            "obj_id": obj_id,
        })
    return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--objects", type=int, default=1)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--keep", type=int, default=0)
    # real object boxes (real_boxes.py) instead of the grid
    parser.add_argument("--boxes-file", default="")
    args = parser.parse_args()

    predictor, swapped = build()
    load_mib = common.gpu_used_mib()
    state = predictor.model.init_state(
        resource_path=frame_folder(args.frames),
        offload_video_to_cpu=True,
        async_loading_frames=False
    )
    session = "bench"
    predictor._all_inference_states[session] = {
        "state": state,
        "session_id": session,
        "start_time": time.time(),
        "last_use_time": time.time(),
    }
    torch.cuda.reset_peak_memory_stats()
    boxes = grid_boxes(args.objects, WIDTH, HEIGHT)
    if args.boxes_file:
        boxes = common.real_boxes(args.boxes_file)
        args.objects = len(boxes)
    add_boxes(predictor, session, boxes)
    stream = predictor.handle_stream_request({
        "type": "propagate_in_video",
        "session_id": session,
        "propagation_direction": "forward",
        # point prompts leave no detector output on frame 0, so Meta's "no prompts"
        # check needs the start frame named
        "start_frame_index": 0,
    })
    rows = []
    areas = []
    marks = {}
    t_prev = time.perf_counter()
    now = 0.0
    frame_idx = 0
    objects = 0

    for out in stream:
        torch.cuda.synchronize()
        now = time.perf_counter()
        frame_idx = out["frame_index"]
        areas.append(mask_areas(state, frame_idx))
        # the objects in the tracker state (Meta's output list is empty, see mask_areas)
        objects = len(areas[-1])
        rows.append({"ms": (now - t_prev) * 1000, "objects": objects})
        if args.keep:
            prune(state, frame_idx, args.keep)
        if frame_idx % 5 == 0:
            # the last line before an out-of-memory names the frame it reached
            print(f"frame {frame_idx}: {common.mib(torch.cuda.memory_allocated())} MiB",
                  flush=True)
        if frame_idx + 1 in (10, 50, args.frames):
            marks[frame_idx + 1] = {
                "allocated_mib": common.mib(torch.cuda.memory_allocated()),
                "process_mib": common.gpu_used_mib(),
            }
        t_prev = time.perf_counter()
    steady = [r["ms"] for r in rows[1:]]
    result = {
        "model": "sam3.1 nf4",
        "linear_swapped": swapped,
        "objects_asked": args.objects,
        "objects_tracked_max": max((r["objects"] for r in rows), default=0),
        "frames": args.frames,
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
    for key, value in result.items():
        if key != "mask_areas":
            print(f"{key:26s} {value}", flush=True)
    real = "-real" if args.boxes_file else ""
    name = f"sam31-boxes-{args.objects}obj{real}-{args.frames}f-keep{args.keep}"
    common.write_result(name, result)
    return


if __name__ == "__main__":
    main()
