# SAM3 and SAM3.1 video tracking in nf4 on the 8 GiB GPU

Measured 2026-09-29 on the RTX 5070 Laptop GPU (8151 MiB), every run alone on the GPU. Scripts and
raw data: bench/sam3-video/ (README.md, results/2026-09-29-*.json).

## Objective
1. Run SAM3 video tracking through transformers in nf4: Sam3VideoModel (a text prompt finds and
   tracks) and Sam3TrackerVideoModel (tracks from boxes).
2. Run SAM3.1 (the multiplex model) in nf4 through any loader that works.
3. For each path that runs: GPU memory and ms per frame by object count, by frames kept in the
   tracking memory, by input size, and with the tracking state in CPU memory.
4. Find what the 7000 MiB tracking peak of 2026-09-04 is a function of.

## Setup
- GPU: NVIDIA GeForce RTX 5070 Laptop, 8151 MiB. torch 2.11.0+cu128, transformers 5.17.0,
  bitsandbytes 0.50.2 (the main environment, unchanged).
- nf4: the BitsAndBytesConfig of perception2's Sam3Backend (nf4, double quantization, bf16
  compute).
- SAM3: /root/models/vision/sam3-official (its config names Sam3VideoModel), loaded by
  transformers.
- SAM3.1: /root/models/vision/sam3.1-official/sam3.1_multiplex.pt, built by Meta's code
  (facebookresearch/sam3, main branch 2026-09-29), installed by bench/sam3-video/setup_sam31_venv.sh
  into its own folder /root/venvs/sam31 (the container has no python3-venv, so it is a pip
  --target folder on PYTHONPATH). nf4: every nn.Linear swapped for a bitsandbytes Linear4bit, with
  two exceptions (Analysis 7).
- Video: the 117 desk frames (640x480, one continuous indoor sequence), streamed one frame at a
  time as a camera gives them. The desk offers few objects: "chair" finds 2, "desk" 1, and the
  four prompts "chair, desk, window, cable" 5. Controlled object counts (1, 4, 16) come from boxes:
  N boxes on a grid over frame 0, then tracked.
- SAM3.1 with boxes (added with task VT3): bench/sam3-video/sam31_boxes.py, the same grid boxes,
  video, frame counts and metrics as R1. SAM3.1 takes an instance box as two corner points
  (labels 2 and 3). Its builder's text-prompt policy (a 15-frame hold, masklet confirmation,
  suppression of tracks the detector does not match) is set back to the model class's defaults
  for box prompts. Real-object runs use the 5 boxes SAM3 finds on frame 0 (chair x2, desk,
  window, cable; bench/sam3-video/real_boxes.py) for both models.
- Terms: **peak** is torch's allocator peak after the load; **process** is everything the process
  holds on the GPU, the CUDA context and the allocator cache included. **keep** is how many past
  frames of tracker output stay stored (all = the transformers default).

## Results

### R1. SAM3, Sam3TrackerVideoModel (boxes), nf4
| objects | frames | state on | keep | peak MiB | process MiB at end | ms/frame p50 | p95 |
|---|---|---|---|---|---|---|---|
| 1 | 60 | GPU | all | 796 | 1264 | 407.2 | 416.2 |
| 4 | 60 | GPU | all | 1380 | 1860 | 603.8 | 619.7 |
| 16 | 117 | GPU | all | 6958 | 7624 | 1437.7 | 1467.5 |
| 16 | 117 | GPU | 16 | 1865 | 2340 | 1442.8 | 1462.4 |
| 16 | 117 | CPU | 16 | 1175 | 1688 | 1497.3 | 1515.7 |

Allocated memory by frames tracked, 16 objects, keep all: 848 MiB at frame 10, 2925 at 50,
6411 at 117. With keep 16: 848, 1241, 1231. With keep 16 the masks equal the keep-all masks on all
117 frames (the mask area of every object on every frame).

The load (the model on the GPU): 638 MiB for the process. First frame: 0.8-1.1 s.

### R2. SAM3, Sam3VideoModel (text prompts), nf4
| prompts | objects | frames | state on | keep | peak MiB | process MiB at end | ms/frame p50 | p95 |
|---|---|---|---|---|---|---|---|---|
| desk | 1 | 117 | GPU | all | 1343 | 1820 | 462.1 | 470.9 |
| chair, desk, window, cable | 5 | 117 | GPU | all | 2956 | 3586 | 888.3 | 915.8 |
| chair, desk, window, cable | 5 | 117 | GPU | 16 | 1425 | 2064 | 905.0 | 926.3 |
| chair, desk, window, cable | 5 | 117 | GPU | 32 | 1671 | 2316 | 904.2 | 926.2 |
| chair, desk, window, cable | 5 | 117 | CPU | 16 | 1237 | 1980 | 919.1 | 939.9 |

The load: 988 MiB for the process. The keep-16 and keep-32 rows prune the stored input frames by
the same window as the outputs (a first version kept only the last input frame). Their masks
against keep all: R7.

### R3. SAM3.1 (Meta's code), text prompt "chair" (2 objects), video frames in CPU memory, one frame per detector batch
| weights | frames | evict | weights MiB | peak MiB | process MiB at end | ms/frame p50 | p95 |
|---|---|---|---|---|---|---|---|
| fp32 | 30 | no | 3744 | 5552 | 6238 | 509.9 | 518.5 |
| nf4 | 30 | no | 1486 | 3310 | 5576 | 538.6 | 544.2 |
| nf4 | 117 | no | 1486 | 4070 | 4760 | 541.0 | 543.6 |
| nf4 | 117 | yes | 1486 | 4010 | 4694 | 540.7 | 543.5 |

nf4 swapped 389 Linear layers. The text prompt found 2 chairs, as SAM3 does on the same frame.
"evict" is Meta's evict_cached_frame_outputs.

### R4. What failed, with the exact error
| step | error | what made it run |
|---|---|---|
| SAM3.1 through transformers | no path: the checkpoint is Meta's format (1166 detector keys, 457 tracker keys, complex64 RoPE tables), and its model card says "there is no Hugging Face Transformers integration". SAM3.1 adds a new neck, a multiplex mask decoder and a new memory attention, so a weight-name conversion cannot map it onto Sam3VideoModel | Meta's own code |
| Meta's start_session | `TypeError: Sam3MultiplexTrackingWithInteractivity.init_state() got an unexpected keyword argument 'offload_state_to_cpu'` | the script calls model.init_state itself; the state stays on the GPU |
| SAM3.1 fp32, video frames on the GPU, 30 frames | `torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 162.00 MiB ... this process has 7.23 GiB memory in use` | video frames in CPU memory |
| nf4 on every Linear | `RuntimeError: self and mat2 must have the same dtype, but got BFloat16 and Byte` (attention reads out_proj.weight itself) | attention modules (those with in_proj_weight) keep their dtype |
| nf4, the ViT MLP | `RuntimeError: mat1 and mat2 shapes cannot be multiplied (5184x1024 and 1x2424832)` (a fused addmm reads fc1.weight) | that call goes through the module's own forward (a patch in the script, not in Meta's code) |
| SAM3.1 nf4, default detector batch | `torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 1.27 GiB` in the position encoding | one frame per detector batch (the builder sets 16) |

### R5. SAM3.1 (Meta's code, nf4), boxes, measured like R1
| objects | frames | keep | peak MiB | process MiB at end | ms/frame p50 | p95 |
|---|---|---|---|---|---|---|
| 1 | 60 | all | 3010 | 3836 | 547.3 | 550.1 |
| 1 | 60 | 16 | 2693 | 3660 | 543.7 | 546.6 |
| 4 | 60 | all | 3530 | 4302 | 809.7 | 821.3 |
| 4 | 60 | 16 | 2866 | 3680 | 805.8 | 809.0 |
| 16 | 117 | all | out of memory at frame 4 (6.14 GiB allocated), in 3 of 3 runs | - | - | - |
| 16 | 117 | 16 | 3558 | 4454 | 1858.0 | 1865.5 |
| 5 real | 117 | all | 4811 | 5566 | 887.9 | 898.4 |
| 5 real | 117 | 16 | 2926 | 3768 | 891.1 | 900.3 |

The load: 1898 MiB for the process (SAM3: 638). With the 16-frame limit, the masks of the 5 real
objects equal the keep-all masks on all 117 frames. Meta's postprocessed output is empty after
frame 0 in every box run, although the tracker scores each object high (for example 6.4-8.9 on
frames 1-3) and suppresses none; the masks are read from the tracker's state, as the SAM3 rows
read pred_masks. The grid-box runs of SAM3.1 were fingerprinted from that empty output, so their
mask check is not valid; the real-object runs are.

### R6. SAM3 and SAM3.1 side by side (the same rows, video and metrics; nf4)
| objects | frames | keep | peak MiB SAM3 / SAM3.1 | process MiB SAM3 / SAM3.1 | ms/frame p50 SAM3 / SAM3.1 | masks equal with and without the limit |
|---|---|---|---|---|---|---|
| 1 | 60 | all | 796 / 3010 | 1264 / 3836 | 407.2 / 547.3 | - |
| 1 | 60 | 16 | not run / 2693 | not run / 3660 | not run / 543.7 | - |
| 4 | 60 | all | 1380 / 3530 | 1860 / 4302 | 603.8 / 809.7 | - |
| 4 | 60 | 16 | not run / 2866 | not run / 3680 | not run / 805.8 | - |
| 16 | 117 | all | 6958 / out of memory | 7624 / out of memory | 1437.7 / - | - |
| 16 | 117 | 16 | 1865 / 3558 | 2340 / 4454 | 1442.8 / 1858.0 | SAM3 yes (117/117) |
| 5 real | 117 | all | 2482 / 4811 | 3006 / 5566 | 683.8 / 887.9 | - |
| 5 real | 117 | 16 | 920 / 2926 | 1376 / 3768 | 683.4 / 891.1 | yes / yes (117/117 each) |

### R7. Run-to-run noise of the text mode (task VT4)
| comparison (Sam3VideoModel, 4 prompts, 117 frames) | mask area difference median | p95 | max | first differing frame |
|---|---|---|---|---|
| keep all, run 1 against run 2 | 0 | 0 | 0 | none |
| keep all against keep 16, inputs pruned to the last frame | 0.25 % | 2.8 % | 13.8 % | 3 |
| keep all against keep 16, inputs pruned like the outputs | 0.17 % | 2.0 % | 4.0 % | 19 |
| keep all against keep 32, inputs pruned like the outputs | 0.14 % | 1.9 % | 5.6 % | 35 |

The object count was the same on every frame in every row. Keep 32: 1671 MiB peak.

## Analysis
1. SAM3 video tracking runs in nf4 through transformers 5.17 on our checkpoint, with no new
   package: both Sam3TrackerVideoModel and Sam3VideoModel (R1, R2).
2. The tracking memory is a function of frames tracked times objects. transformers stores every
   frame's tracker output and never drops it: about 52 MiB per frame at 16 objects, about 3.3 MiB
   per object and frame (R1). After 117 frames that is 6411 MiB allocated and 7624 MiB for the
   process, the 7000 MiB of 2026-09-04.
3. The tracker reads only the last 6 frames' memories and the last 16 object pointers. Dropping
   the outputs older than 16 frames keeps the memory flat (1231 MiB allocated for 16 objects) and
   gives the same masks on every frame in the boxes mode (R1). The prune is 15 lines in the bench
   script, not a transformers setting.
4. The tracking state in CPU memory cuts the GPU further (511 MiB allocated for 16 objects with
   keep 16) and costs 4 % in time (1497 against 1443 ms).
5. The time per frame: every frame runs the image encoder (about 330 ms), so one tracked object
   costs 407 ms, about what one SAM3 detect costs (410 ms, the SAM3 assessment). Each more object
   adds about 65 ms (4 objects 604 ms, 16 objects 1438 ms): SAM3's tracker decodes each object on
   its own. A text prompt adds the detector: 462 ms for one prompt, 888 ms for four.
6. The input size does not matter to the model: every frame is resized to 1008x1008. One object
   at 1280x720 took 411 ms and the same memory as at 640x480 (a first-series run, raw data kept
   outside the repo).
7. SAM3.1 runs in nf4 through Meta's code, after three changes in the bench script: attention
   projections and the fused MLP read their weights directly, so they keep their dtype or go
   through the module; the detector's 16-frame look-ahead batch is set to one frame. nf4 cuts the
   weights from 3744 to 1486 MiB and the peak from 5552 to 3310 MiB (30 frames, 2 objects). It
   costs 6 % in time (541 against 510 ms).
8. SAM3.1's state also grows with the frames: 3310 MiB peak at 30 frames, 4070 at 117, for 2
   objects (about 8 MiB per frame). Meta's evict option saves 60 MiB. A prune like point 3 is not
   yet written for Meta's state.
9. The 7000 MiB of 2026-09-04 was not the weights, as that record found. It was three things this
   run separated: every frame's state kept (point 2), the detector's 16-frame look-ahead
   (1.27 GiB in one allocation), and the video frames on the GPU.
10. Not measured: SAM3.1 with more than 16 objects, anything next to Gemma (owner: not yet),
    and tracking accuracy against labelled boxes. (SAM3.1 with boxes and a limit: R5, R6.)
11. The text-mode runs are deterministic: two keep-all runs gave the same masks on every frame
    (R7). So the keep-16 difference is not noise; the prune causes it. The first version dropped
    the stored input frames down to the last one, and Sam3VideoModel reads earlier inputs: the
    masks changed from frame 3. Pruning the inputs by the same 16-frame window moves the first
    difference to frame 19 (max 4.0 %); a 32-frame window to frame 35. The text model reads back
    further than the 16 frames the tracker uses (it re-conditions on detector frames every 16
    frames), so any window changes its masks a little. The box tracker is unaffected (R1, R5).
12. ONNX Runtime and GGUF were not needed: the transformers and Meta paths ran. An ONNX export of
    the SAM3 tracker exists (onnx-community/sam3-tracker-ONNX); none for SAM3.1 was found.
13. Measured the same way (R6), SAM3.1 costs more than SAM3 on this GPU: 2-3 times the peak
    memory and 35 % more time per frame at 1 object (547 against 407 ms), 29 % more at 16
    (1858 against 1443 ms). Each object adds about 87 ms in SAM3.1 and about 69 ms in SAM3.
    SAM3.1 runs its detector on every frame even without a text prompt, which SAM3's tracker does
    not. Meta's claim of 7 times faster tracking holds at 128 objects on an H100; at 16 objects on
    this GPU it is not faster (the 128-object case is not measured).
14. The 16-frame limit works for SAM3.1 too: 4811 -> 2926 MiB for the 5 real objects, the masks
    equal on all 117 frames. Without it, 16 objects ran out of memory at frame 4 in 3 of 3
    runs, although the run with the limit is identical up to frame 16; that early failure is
    not explained.
15. For box prompts, Meta's code returns no masks after frame 0 (R5): usable SAM3.1 box tracking
    needs a fix in Meta's output path or reading the tracker state, as the bench script does.

## Conclusions
1. SAM3 video tracking in nf4 fits the 8 GiB GPU: 16 objects in 1.2-1.9 GiB with a 16-frame prune.
2. The tracking memory is frames times objects, and the prune removes the frames factor.
3. SAM3.1 runs in nf4 through Meta's code, with a patched bench script and a separate package
   folder. Measured like SAM3 it costs more: 2.9-3.6 GiB peak with the limit, 544-1858 ms per
   frame for 1-16 objects, against SAM3's 0.9-1.9 GiB and 407-1443 ms.
4. Tracking is not faster than detection per frame (407 against 410 ms for one object); its gain is
   one identity per object across frames.

## Decisions for the owner (the recommendation is option a; IDs VT1-VT4, since V1 exists in the decision ledger)
| ID | question | options |
|---|---|---|
| VT1 | the tracker for a live highlight | a) SAM3's Sam3TrackerVideoModel from the first detect's boxes: the checkpoint we load today, transformers only, 1.2-1.9 GiB for 16 objects. b) SAM3.1 through Meta's code in its own package folder. c) keep one detect per refresh, as today |
| VT2 | the tracking memory policy | a) prune to the last 16 frames (flat memory, same masks in the boxes mode). b) also keep the state in CPU memory (-0.7 GiB, +4 % time). c) no prune (grows about 3.3 MiB per object and frame) |
| VT3 | SAM3.1 next | ruled (measure like SAM3): done, R5 and R6 |
| VT4 | the text-mode mask difference | ruled a: done, R7 (deterministic; the prune causes it) |
| VT5 | SAM3.1 after R6 | a) keep SAM3 for tracking and park SAM3.1: more memory and time at 1-16 objects, and Meta's box output path is empty. b) fix Meta's output path and measure 64-128 objects, where Meta reports its gain |
| VT6 | the text model and the limit (R7) | a) track with the box tracker (identical masks with the limit) and use the text model only to find the objects. b) the text model with a 32-frame limit (max 5.6 % area difference, 1671 MiB) |

Owner rulings (decision ledger): VT1 a, VT2 a (built after the freeze); VT3 and VT4 done; VT5: SAM3 kept, SAM3.1 not parked (POST (2)); VT6 a, the box way.
