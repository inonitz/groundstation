# sam3-video

Measures SAM3 and SAM3.1 video tracking in nf4 on this GPU (RTX 5070 Laptop, 8 GiB), alone on
the GPU: memory by object count and by frames tracked, and ms per frame.
The decision document: docs/research-complete-sam3-video-tracking.md.

| section | content |
|---|---|
| Why | the questions |
| How to run | one command per script |
| Results | the current numbers; raw JSON in results/ |

## Why
- The owner (S5, S5 (2), S5-M): run SAM3.1 in nf4 through any loader that works, and find out
  what the tracking memory (7000 MiB on 2026-09-04) is a function of.
- transformers 5.17 ships Sam3VideoModel (a text prompt finds and tracks) and
  Sam3TrackerVideoModel (tracks from boxes or points) for the SAM3 checkpoint we already use.

## How to run
Take the GPU lock first (`/root/groundstation/tools/lock.sh acquire <agent> gpu`); run alone.
Frames: the 117 desk frames in /root/models/vision/sam3-desk-frames (640x480), streamed one at a
time.

| script | measures | duration |
|---|---|---|
| video_track.py boxes --objects N [--frames F] [--state cpu] [--keep 16] | Sam3TrackerVideoModel nf4, N grid boxes on frame 0 | 1-3 min |
| video_track.py text --prompt a,b,c [--frames F] [--state cpu] [--keep 16] | Sam3VideoModel nf4, text prompts | 1-3 min |
| setup_sam31_venv.sh | installs Meta's sam3 code into /root/venvs/sam31 (main torch untouched) | 1 min, no GPU |
| sam31_track.py [--nf4] [--offload-video] [--frames F] [--evict] | SAM3.1 multiplex through Meta's code, nf4 Linear4bit, text prompt | 1-3 min |
| sam31_boxes.py --objects N [--frames F] [--keep 16] [--boxes-file F] | SAM3.1 nf4 with boxes, measured like video_track.py boxes | 1-4 min |
| real_boxes.py | the 5 real object boxes on desk frame 0 (results/real_boxes_frame0.json), for --boxes-file | 30 s |

```
cd /root/groundstation/bench/sam3-video
HF_HUB_OFFLINE=1 python3 video_track.py boxes --objects 16 --frames 117 --keep 16
bash setup_sam31_venv.sh
HF_HUB_OFFLINE=1 PYTHONPATH=/root/venvs/sam31 python3 sam31_track.py --nf4 --offload-video --frames 117
```
--keep N prunes the tracker's stored outputs older than N frames (transformers keeps every
frame's by default). --state cpu keeps the tracking state in CPU memory.

## Results (2026-09-29; peak = torch's allocator peak; process = the whole process on the GPU)

SAM3 (transformers 5.17, nf4), Sam3TrackerVideoModel, boxes:
| objects | frames | state | keep | peak MiB | process MiB at end | ms/frame p50 |
|---|---|---|---|---|---|---|
| 1 | 60 | cuda | all | 796 | 1264 | 407.2 |
| 4 | 60 | cuda | all | 1380 | 1860 | 603.8 |
| 16 | 117 | cuda | all | 6958 | 7624 | 1437.7 |
| 16 | 117 | cuda | 16 | 1865 | 2340 | 1442.8 |
| 16 | 117 | cpu | 16 | 1175 | 1688 | 1497.3 |

SAM3 (transformers 5.17, nf4), Sam3VideoModel, text prompts:
| prompts | objects | frames | state | keep | peak MiB | process MiB at end | ms/frame p50 |
|---|---|---|---|---|---|---|---|
| desk | 1 | 117 | cuda | all | 1343 | 1820 | 462.1 |
| chair, desk, window, cable | 5 | 117 | cuda | all | 2956 | 3586 | 888.3 |
| chair, desk, window, cable | 5 | 117 | cuda | 16 | 1425 | 2064 | 905.0 |
| chair, desk, window, cable | 5 | 117 | cuda | 32 | 1671 | 2316 | 904.2 |
| chair, desk, window, cable | 5 | 117 | cpu | 16 | 1237 | 1980 | 919.1 |

SAM3.1 (Meta's code, main branch 2026-09-29), text prompt "chair" (2 objects), video on CPU,
one frame per detector batch:
| weights | frames | evict | weights MiB | peak MiB | process MiB at end | ms/frame p50 |
|---|---|---|---|---|---|---|
| fp32 | 30 | no | 3744 | 5552 | 6238 | 509.9 |
| nf4 | 30 | no | 1486 | 3310 | 5576 | 538.6 |
| nf4 | 117 | no | 1486 | 4070 | 4760 | 541.0 |
| nf4 | 117 | yes | 1486 | 4010 | 4694 | 540.7 |

SAM3 and SAM3.1 side by side, boxes, nf4 (peak MiB / ms per frame p50; SAM3 first):
| objects | frames | keep | peak MiB | ms/frame p50 | masks equal with and without the limit |
|---|---|---|---|---|---|
| 1 | 60 | all | 796 / 3010 | 407.2 / 547.3 | - |
| 4 | 60 | all | 1380 / 3530 | 603.8 / 809.7 | - |
| 16 | 117 | all | 6958 / out of memory at frame 4 | 1437.7 / - | - |
| 16 | 117 | 16 | 1865 / 3558 | 1442.8 / 1858.0 | SAM3 117/117 |
| 5 real | 117 | all | 2482 / 4811 | 683.8 / 887.9 | - |
| 5 real | 117 | 16 | 920 / 2926 | 683.4 / 891.1 | 117/117 / 117/117 |

Text mode, run to run: two keep-all runs give identical masks. The limit changes the text model's
masks a little (keep 16: max 4.0 %, from frame 19); the box trackers not at all.
