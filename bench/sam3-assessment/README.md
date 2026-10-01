# sam3-assessment

Measures what SAM3 costs in the app and what its alternatives would cost: the frame transfer
to another process, detect() alone and next to Gemma, the start-up, and the concept fan-out.
The decision document built on these numbers: docs/research-complete-sam3-assessment.md.

| section | content |
|---|---|
| Why | the questions these scripts answer |
| How to run | one command per script, GPU use and duration |
| Results | the current numbers; raw JSON in results/ |

## Why
- The app measured 558 ms per SAM3 pass; the benchmarks measured about 400 ms (ruling C.2).
- The owner asked for SAM3 in its own process without sending 2.7 MiB per request (T6).
- torch costs about 0.9 s of the app's import (T8, R10).
- It replaces the method of bench/hebrew-command-bench/contention.py and real_cadence.py
  (G2 a): detect_cost.py uses the app's own modules, session.py reads a real session.

## How to run
Every script imports the app's modules in place from projects/integration_harden2. Take the
GPU lock first: `/root/groundstation/tools/lock.sh acquire <agent> gpu`.

| script | measures | GPU | duration |
|---|---|---|---|
| transfer.py | one frame to another process: pipe vs shared memory | no | 10 s |
| session.py <session folder> | the app's SAM3 records by concept count and Gemma overlap | no | 1 s |
| stages.py | the steps of one forward | yes | 1 min |
| detect_cost.py | detect() alone, Gemma idle, Gemma busy (text, vision); 1 and 3 concepts | yes | 6 min |
| process_split.py | SAM3 in its own process with a shared frame buffer vs in process; a UI probe | yes | 3 min |
| startup.py [imports or load or all] | torch and transformers imports; model load; first detect | load only | 1 min |
| reuse.py | one image encoding for all concepts of a phrase vs one full forward each | yes | 1 min |
| load_vs_frames.py <none, thread, thread-1ms or child> | a webcam frame loop while SAM3 loads: not at all, on a thread (today), on a thread with a 1 ms GIL switch interval, in its own process | yes + webcam + display | 25 s |

```
cd /root/groundstation/bench/sam3-assessment
python3 transfer.py
python3 session.py /root/groundstation/logs/sessions/session-20260925-045109-rog
python3 detect_cost.py
```

load_vs_frames.py needs a screen and the webcam:
`DISPLAY=:97 WEBCAM_DEV=2 python3 load_vs_frames.py thread` (start `Xvfb :97` first). Its JSON
holds the day's last run of each mode.

Frames: 8 real indoor frames from /root/models/vision/sam3-desk-frames (640x480), scaled to the
app's 1280x720. Phrases: "person" (one concept) and "dresser, chest of drawers, cabinet" (the
three concepts the app sends for "dresser").

## Results (2026-09-28, RTX 5070 Laptop 8 GiB, SAM3 nf4, torch 2.11, transformers 5.17)

| measurement | p50 ms | p95 ms | file |
|---|---|---|---|
| frame through a pipe (round trip) | 3.1 | 4.3 | transfer |
| frame through shared memory (round trip) | 0.1 | 0.1 | transfer |
| BGR -> RGB PIL image, inside detect() today | 9.8 | 10.7 | transfer |
| detect, 1 concept, alone | 416.7 | 425.9 | detect-cost |
| detect, 1 concept, Gemma loaded and idle | 409.9 | 431.4 | detect-cost |
| detect, 1 concept, Gemma busy (text) | 630.1 | 638.5 | detect-cost |
| detect, 1 concept, Gemma busy (vision) | 630.5 | 636.8 | detect-cost |
| detect, 3 concepts, alone | 1230.0 | 1234.2 | detect-cost |
| detect, 3 concepts, Gemma busy (text) | 1875.7 | 1884.4 | detect-cost |
| forward step of one detect | 389.8 | 400.2 | stages |
| own process: round trip minus the child's detect | 0.4 | 0.7 | process-split |
| 3 concepts, one image encoding shared | 508.7 | 511.6 | reuse |
| 3 concepts, one full forward each | 1196.4 | 1199.8 | reuse |
| import torch | 912.6 | 913.7 | startup-imports |
| SAM3 model load (fresh process) | 3959.8 | 4233.3 | startup-load |
| first detect after load | 838.6 | 864.3 | startup-load |

The SAM3 load and the frame loop (load_vs_frames.py, C920, 25 s per run, frames over 100 ms):
| mode | run 1 | run 2 | worst frame ms |
|---|---|---|---|
| none | 0 | - | 70.6 |
| thread (today) | 8 | 10 | 214.9, 240.7 |
| thread, 1 ms switch interval | 9 | - | 246.4 |
| child process | 0 | 0 | 40.4, 74.3 |

The analysis and the options: docs/research-complete-sam3-assessment.md.
