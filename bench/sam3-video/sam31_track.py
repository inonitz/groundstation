"""SAM3.1 (the multiplex video model) through Meta's own code, in its own package folder
(setup_sam31_venv.sh), optionally with every nn.Linear swapped for a bitsandbytes nf4
Linear4bit (the quantization perception2 uses for SAM3).

A text prompt on frame 0, then forward propagation over the desk frames. Measured: the
load memory, the peak GPU memory, ms per frame, the objects tracked, the frames kept.
GPU. Run:
  PYTHONPATH=/root/venvs/sam31 python3 bench/sam3-video/sam31_track.py --nf4"""
import argparse
import glob
import os
import resource
import tempfile
import time

import bitsandbytes as bnb
import sam3.model.vitdet as vitdet
import torch
from sam3.model_builder import build_sam3_multiplex_video_predictor

import common

CHECKPOINT = "/root/models/vision/sam3.1-official/sam3.1_multiplex.pt"


def frame_folder(n):
    """Meta's loader sorts a folder by the integer file name: link the desk frames as
    0.jpg, 1.jpg, ..."""
    folder = tempfile.mkdtemp(prefix="sam31-frames-")
    paths = sorted(glob.glob(os.path.join(common.DESK_FRAMES, "*.jpg")))[:n]
    for i, path in enumerate(paths):
        os.symlink(path, os.path.join(folder, f"{i}.jpg"))
    return folder


def addmm_act_through_module(activation, linear, mat1):
    """vitdet's MLP calls a fused addmm that reads linear.weight directly, which an nf4
    Linear4bit holds packed. The same math through the module's own forward."""
    y = linear(mat1.to(torch.bfloat16))
    if activation in (torch.nn.functional.relu, torch.nn.ReLU):
        return torch.nn.functional.relu(y)
    return torch.nn.functional.gelu(y)


def to_nf4(module, skip):
    """Swap every nn.Linear under `module` for an nf4 Linear4bit, except the names in
    `skip`. -> the number swapped. The weights quantize when the module moves to CUDA."""
    swapped = 0
    # A multi-head attention (torch's, or Meta's copy in model_misc) reads
    # out_proj.weight itself: a Linear4bit there multiplies bf16 by the packed bytes.
    # Such a module holds in_proj_weight; its projections keep their dtype.
    if hasattr(module, "in_proj_weight"):
        return 0
    for name, child in list(module.named_children()):
        if name in skip:
            continue
        if isinstance(child, torch.nn.Linear):
            new = bnb.nn.Linear4bit(
                child.in_features,
                child.out_features,
                bias=child.bias is not None,
                compute_dtype=torch.bfloat16,
                quant_type="nf4",
                device="cpu"
            )
            new.weight = bnb.nn.Params4bit(
                child.weight.data.cpu(),
                requires_grad=False,
                quant_type="nf4"
            )
            if child.bias is not None:
                new.bias = torch.nn.Parameter(child.bias.data.cpu(), requires_grad=False)
            setattr(module, name, new)
            swapped += 1
            continue
        swapped += to_nf4(child, skip)
    return swapped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--nf4", action="store_true")
    parser.add_argument("--prompt", default="chair")
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--offload-video", action="store_true")
    parser.add_argument("--evict", action="store_true")
    # Meta's builder grounds 16 frames per detector batch (look-ahead); 1 = one frame
    parser.add_argument("--ground-batch", type=int, default=1)
    parser.add_argument("--postprocess-batch", type=int, default=1)
    parser.add_argument("--skip", default="", help="comma-separated child names kept fp")
    args = parser.parse_args()

    predictor = build_sam3_multiplex_video_predictor(
        checkpoint_path=CHECKPOINT,
        use_fa3=False,
        async_loading_frames=False
    )
    predictor.model.batched_grounding_batch_size = args.ground_batch
    predictor.model.postprocess_batch_size = args.postprocess_batch
    swapped = 0
    if args.nf4:
        vitdet.addmm_act = addmm_act_through_module
        predictor.model.cpu()
        swapped = to_nf4(predictor.model, set(filter(None, args.skip.split(","))))
    predictor.model.cuda()
    # the builder placed the fp model on the GPU first: hand its freed blocks back
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    load_mib = common.gpu_used_mib()
    weights_mib = common.mib(torch.cuda.memory_allocated())
    print(f"loaded: nf4={args.nf4} linear swapped={swapped} weights={weights_mib} MiB "
          f"process={load_mib} MiB", flush=True)

    # Meta's start_session passes offload_state_to_cpu, which the multiplex model's
    # init_state does not accept (TypeError, main branch 2026-09-29): start it here.
    state = predictor.model.init_state(
        resource_path=frame_folder(args.frames),
        offload_video_to_cpu=args.offload_video,
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
    t0 = time.perf_counter()
    first = predictor.handle_request({
        "type": "add_prompt",
        "session_id": session,
        "frame_index": 0,
        "text": args.prompt,
    })
    prompt_ms = (time.perf_counter() - t0) * 1000
    rows = []
    t_prev = time.perf_counter()
    stream = predictor.handle_stream_request({
        "type": "propagate_in_video",
        "session_id": session,
        "propagation_direction": "forward",
        "evict_cached_frame_outputs": args.evict,
    })
    for out in stream:
        torch.cuda.synchronize()
        now = time.perf_counter()
        outputs = out.get("outputs", {}) if isinstance(out, dict) else {}
        ids = outputs.get("out_obj_ids", [])
        rows.append({"ms": (now - t_prev) * 1000, "objects": len(ids)})
        t_prev = now
    steady = [r["ms"] for r in rows[1:]]
    result = {
        "nf4": args.nf4,
        "linear_swapped": swapped,
        "skip": args.skip,
        "prompt": args.prompt,
        "frames": args.frames,
        "offload_video": args.offload_video,
        "evict": args.evict,
        "ground_batch": args.ground_batch,
        "postprocess_batch": args.postprocess_batch,
        "weights_mib": weights_mib,
        "load_process_mib": load_mib,
        "prompt_ms": round(prompt_ms, 1),
        "first_prompt_objects": len(first.get("outputs", {}).get("out_obj_ids", [])),
        "objects_tracked_max": max((r["objects"] for r in rows), default=0),
        "peak_allocated_mib": common.mib(torch.cuda.max_memory_allocated()),
        "end_process_mib": common.gpu_used_mib(),
        "ms_per_frame": common.stats(steady),
        "cpu_rss_max_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
    }
    for key, value in result.items():
        print(f"{key:22s} {value}", flush=True)
    tag = "nf4" if args.nf4 else "fp"
    extra = "".join(
        f"-{k}" for k in ("offload_video", "evict") if getattr(args, k)
    )
    name = f"sam31-{tag}-{args.prompt}-{args.frames}f-gb{args.ground_batch}{extra}"
    common.write_result(name, result)
    return


if __name__ == "__main__":
    main()
