# SAM3 assessment: where it runs, what it costs, what to change

Measured 2026-09-28 on the RTX 5070 Laptop GPU (8 GiB). Scripts and raw data:
bench/sam3-assessment/ (README.md, results/2026-09-28-*.json).

## Objective
Decide what to do with SAM3 on measured evidence, before any change to it. Five questions:
1. What does the app do today, and what does a SAM3 failure do?
2. What would SAM3 in its own process cost, with a shared frame buffer instead of a 2.7 MiB copy
   per request?
3. Why did the app measure 558 ms per SAM3 pass when the benchmarks measured about 400 ms?
4. What does SAM3 cost at start?
5. What would SAM3.1 and EOVSAM change?

## Setup
- GPU: NVIDIA GeForce RTX 5070 Laptop, 8151 MiB. SAM3: facebook/sam3, int4-nf4 (bitsandbytes),
  loaded through the app's own perception2.sam3_backend.Sam3Backend. torch 2.11.0+cu128,
  transformers 5.17.0, Python 3.12.3.
- Gemma: started through the app's supervisor and gemma.server.process (llama.cpp, Vulkan).
- Frames: 8 real indoor frames (sam3-desk-frames, 640x480) scaled to the app's 1280x720 BGR frame
  (2.64 MiB). One random frame for comparison with the older benchmarks.
- Phrases: "person" is one concept. "dresser, chest of drawers, cabinet" is the three concepts the
  app sends for "dresser" (perception2/concept.py). A term used below: a **pass** is one detect()
  call; a **forward** is one run of the model for one concept. A pass runs one forward per concept.
- Real app data: session-20260925-045109-rog (the webcam run behind the 558 ms figure).
- Percentiles are nearest-rank. Every GPU series ran alone on the GPU (tools/lock.sh).

## Results

### R1. The app's record, by concept count (session.py; 48 passes)
| passes | n | p50 ms | p95 ms | min | max |
|---|---|---|---|---|---|
| all | 48 | 576.4 | 1456.0 | 374.7 | 2352.0 |
| 1 concept, GPU otherwise idle | 8 | 408.6 | 469.7 | 378.7 | 469.7 |
| 1 concept, Gemma or ASR running | 1 | 557.5 | 557.5 | 557.5 | 557.5 |
| 3 concepts, GPU otherwise idle | 20 | 1321.4 | 1608.7 | 1293.6 | 2352.0 |
| 3 concepts, Gemma or ASR running | 2 | 1413.2 | 1456.0 | 1413.2 | 1456.0 |
| no pass file (highlight refreshes), idle | 13 | 380.8 | 384.9 | 374.7 | 427.0 |
| no pass file, Gemma or ASR running | 4 | 576.4 | 669.7 | 382.6 | 669.7 |

The 2352 ms maximum is the first pass after the model load (a cold pass; see R5).

### R2. detect() under the app's conditions (detect_cost.py; 16 passes each)
| condition | 1 concept p50 | 1 concept p95 | 3 concepts p50 | 3 concepts p95 | GPU memory max MiB |
|---|---|---|---|---|---|
| SAM3 alone | 416.7 | 425.9 | 1230.0 | 1234.2 | 1723 |
| SAM3 alone, random frame | 411.8 | 422.3 | - | - | 1723 |
| Gemma loaded, idle | 409.9 | 431.4 | 1216.0 | 1231.8 | 5656 |
| Gemma busy, text requests | 630.1 | 638.5 | 1875.7 | 1884.4 | 5656 |
| Gemma busy, vision requests | 630.5 | 636.8 | 1874.7 | 1888.8 | 5656 |

GPU load was 100 % in every series.

### R3. The steps of one pass, 1 concept (stages.py; 16 passes)
| step | p50 ms | p95 ms |
|---|---|---|
| BGR -> RGB PIL image | 7.8 | 8.2 |
| processor (resize, normalize, tokenize; CPU) | 7.1 | 7.5 |
| copy to the GPU | 5.0 | 6.0 |
| model forward | 389.8 | 400.2 |
| post-processing and masks to numpy | 0.6 | 0.8 |
| total | 410.5 | 420.7 |

### R4. One image encoding for all concepts (reuse.py; 12 passes, 3 concepts)
| method | p50 ms | p95 ms |
|---|---|---|
| today: one full forward per concept | 1196.4 | 1199.8 |
| the image encoded once, then text + detector per concept | 508.7 | 511.6 |
| the image encoding alone | 332.9 | 336.5 |

The boxes were the same (within 2 px, same count per concept) in 12 of 12 passes.

### R5. Start-up (startup.py; 3 fresh processes each)
| cost | p50 ms | max ms |
|---|---|---|
| import torch | 912.6 | 913.7 |
| import perception2 (the app's import; it loads torch) | 860.7 | 909.1 |
| import transformers Sam3Model (inside the load thread today) | 2533.4 | 3353.6 |
| Sam3Backend() model load | 3959.8 | 4233.3 |
| first detect after the load (cold) | 838.6 | 864.3 |
| second detect | 402.3 | 406.8 |

### R6. The frame to another process (transfer.py; 300 round trips each)
| path | p50 ms | p95 ms |
|---|---|---|
| the frame pickled through a pipe | 3.1 | 4.3 |
| the frame copied into shared memory, the slot number through the pipe | 0.1 | 0.1 |
| shared memory, and the receiver makes the RGB image | 8.5 | 9.9 |
| the RGB image in the same process (what detect() does today) | 9.8 | 10.7 |

### R7. SAM3 in its own process (process_split.py; 24 passes, 1 concept)
| measurement | p50 ms | p95 ms |
|---|---|---|
| in the app's process: detect | 412.5 | 424.0 |
| own process: round trip | 412.5 | 433.1 |
| own process: round trip minus the child's detect | 0.4 | 0.7 |
| own process: start to ready (torch import + model load) | 7711 (one run) | - |

A 30 Hz draw loop on the main thread (boxes, a label, a mask blend) measured the effect on the
frame loop. Its draw time was 0.3 ms p50 in all three cases: no SAM3, SAM3 in process, SAM3 in its
own process. Its tick started late by at most 4.6 ms with SAM3 in process, 0.2 ms in its own process.

### R8. The retired contention measurements (2026-09-18, bench/hebrew-command-bench)
These scripts drove both models from one process with a random frame. Their results move here
(rule C for deleting a benchmark).

contention.py, both models driven without pause (a saturation bound):
| component | isolated p50 ms | under the other's load p50 ms | slowdown |
|---|---|---|---|
| SAM3 detect | 415 | 623 | 1.50x |
| Gemma plan | 498 | 1258 | 2.53x |

real_cadence.py, SAM3 held at 1 pass per second, Gemma one plan every 1.5 s, 3 repeats:
| path | p50 ms | p95 ms | p99 ms | n |
|---|---|---|---|---|
| SAM3 isolated | 411 | 451 | 461 | 60 |
| SAM3 at 1 pass/s next to Gemma | 401 | 413 | 420 | 246 |
| Gemma isolated | 493 | 502 | 504 | 60 |
| Gemma, no SAM3 overlap | 499 | 506 | 508 | 109 |
| Gemma, overlapped a SAM3 pass | 500 | 516 | 516 | 11 |

Overlap rate 9 %. Raw data stays in bench/hebrew-command-bench/results/2026-09-18-*.json.

### R9. The SAM3 load and the frame loop (load_vs_frames.py, added with task E1)
A webcam frame loop (read, draw with PIL text, show on a virtual screen) ran 25 s; the SAM3 load
started at 3 s. Frames over 100 ms, the first frame (camera open) excluded:
| SAM3 load | run 1 | run 2 | worst frame ms |
|---|---|---|---|
| none | 0 | - | 70.6 |
| on a thread of the same process (today) | 8 | 10 | 214.9, 240.7 |
| on a thread, GIL switch interval 1 ms | 9 | - | 246.4 |
| in its own process | 0 | 0 | 40.4, 74.3 |

In four scripted app runs (2026-09-28), 43 of 433 frames before the "sam3" row went UP took over
100 ms (max 1785 ms); after it, 1 of 5723 (max 105.5 ms).

## Analysis
1. Today's design. SAM3 runs in the app's process. BackendLoader loads it on a thread at start;
   until then detect() answers DETECT_NOT_READY. Every pass holds the SAM3 priority lock, so one
   forward runs at a time. A load failure, or a GPU out-of-memory inside a pass, throws; the crash
   hook (system/fatal.py, threading.excepthook) calls die() and the whole app ends (R9). No SAM3
   failure appears in the logs of the 40 recorded sessions.
2. The 558 ms is a mix of two populations, not a slow SAM3. One pass runs one forward per concept.
   "dresser" is three concepts, so its passes take about 1300 ms. One-concept passes take
   380-410 ms, the benchmark figure. 22 of the 48 passes were three-concept passes (R1).
3. Gemma loaded and idle costs nothing: 409.9 against 416.7 ms (R2). The GPU memory it holds does
   not slow SAM3.
4. Gemma busy costs SAM3 about 51 %: 630 against 417 ms, for text and vision requests alike (R2).
   In the app this happens only while a command is answered: 7 of 48 passes overlapped Gemma or
   ASR (R1). At the live cadence the retired real_cadence.py found Gemma itself unaffected (R8).
5. The widened investigation (ruling C.2) found the cause in point 2, and a fix: the image
   encoding is 333 of the ~410 ms. Encoding the frame once and running only the text and detector
   per concept cuts a three-concept pass from 1196 to 509 ms, with the same boxes (R4). It is a
   change inside Sam3Backend._run and detect(); Sam3Model.forward already accepts vision_embeds.
   The parity check covered one to two boxes per frame; a scene with many hits is not yet checked.
6. The forward is 95 % of a pass (R3). The CPU steps together cost about 20 ms. The BGR -> RGB copy
   (7.8-9.8 ms) is the largest; a faster copy saves at most 2 %.
7. A separate process costs almost nothing per request. A shared-memory slot moves the frame in
   0.1 ms; the pickled pipe path takes 3.1 ms (R6). The whole round trip adds 0.4 ms to a 412 ms
   pass (R7). The 2.7 MiB copy per request is avoidable, and even the copy is under 1 % of a pass.
8. A separate process does not make the frame loop faster. The draw loop measured no difference
   between the two layouts (R7). The app's session agrees: seconds with a SAM3 pass ran at 15 fps
   p50, the same as idle seconds. The likely reason, unverified: torch releases the GIL while
   the GPU works.
9. What a separate process would change: a SAM3 failure becomes a supervisor restart (3 restarts,
   then die) instead of the end of the app; the app no longer imports torch (0.9 s of its import).
   What it would cost: a process spec, a request protocol and a shared-memory ring in new code, and
   a restart takes 5.7-7.7 s (import 0.9 s + load 4.0 s + first pass 0.8 s, R5; 7.7 s in R7),
   during which detect() answers DETECT_NOT_READY. The GPU stays shared; contention (point 4) is unchanged.
10. torch's import can leave the app's import path without a separate process. app/main.py
    imports perception2.backend; perception2/__init__.py imports sam3_backend, which imports torch.
    If __init__.py stops importing Sam3Backend, torch loads on the load thread with the model,
    in parallel with the rest of the start. The app starts in 14-18.5 s, bound by the Gemma and
    SAM3 loads (HISTORY 2026-09-27), so the gain is about 0.9 s of the first line, not the total.
11. SAM3.1 (measured 2026-09-03, bench/sam3-mask-bench/RESULTS.md): on single images it finds the
    same objects as SAM3, 1.7 times slower (587 against 345 ms, bf16) and 2.3 times heavier
    (4723 against 2006 MiB). Its gain is video tracking (Object Multiplex): a live highlight could
    follow objects between frames instead of a full pass per refresh. Tracking peaked at about
    7000 MiB; weight quantization did not lower it, because the peak is activations and tracking
    state. That does not fit next to Gemma (about 3.9 GiB) on 8 GiB. It runs only through the
    facebookresearch/sam3 repository, which is not installed. Not measured again here.
12. EOVSAM (hustvl, arXiv 2608.02284, 2026): SAM3 adapted to segment every category in one pass,
    with the prompt conditioning removed and a new classification step. The paper reports better
    accuracy than SAM3 on semantic and panoptic benchmarks and up to 338 times faster inference for
    large vocabularies (unverified here). Our passes hold one to three concepts, so for us its gain
    is close to point 5's shared encoding, which needs no new model. Its model is not downloaded;
    it is not measured. Its instance boxes at our confidence floor are unknown.
13. Quantization does not speed SAM3 up (bench/sam3-mask-bench/results/sam3-quantization.md):
    nf4 saves memory; a forward is compute-bound. fp8 with torch.compile reached a 202 ms forward
    but needs a 319 s cold compile at every fresh start.
14. The start-up frame dips come from the SAM3 load on the app's thread (R9). In its own
    process the load caused no frame over 100 ms; on a thread it caused 8 and 10. The slow step
    varies (read, draw or show): the frame loop waits for the GIL while the load holds it
    (inferred from these two facts, not traced). A 1 ms GIL switch interval did not help. After
    the load, the frame loop has no dips. This adds a third gain to option S2 a.

## Conclusions
1. The 558 ms is explained: three-concept passes, plus Gemma running at the same time for a few.
   Gemma loaded and idle is not a cause.
2. The largest gain available is the shared image encoding: 1196 -> 509 ms for three concepts.
3. The shared frame buffer answers T6: 0.1 ms per frame, 0.4 ms per request.
4. A separate process buys failure isolation, a lighter app import and a smooth screen during
   the start; it does not make a pass faster.

## Open decisions (the owner rules; the recommendation is option a)
| ID | question | options |
|---|---|---|
| S1 | the three-concept cost | a) encode the frame once per pass, text + detector per concept (1196 -> 509 ms); check the boxes on a many-hit scene first. b) keep one full forward per concept. c) fewer synonyms per concept |
| S2 | where SAM3 lives | a) its own process, a shared-memory frame slot, started by the supervisor: a failure restarts SAM3, not the app; torch leaves the app; no frame dips while it loads (R9). b) stay in the app's process, as today: simpler; no SAM3 failure seen in 40 sessions |
| S3 | torch in the app's import, if S2 is b | a) perception2/__init__.py stops importing Sam3Backend, so torch loads on the load thread (0.9 s off the first line). b) leave it |
| S4 | SAM3 slowed 51 % while Gemma answers | a) accept it: it happens only during a command. b) pause highlight refreshes while a Gemma request runs |
| S5 | SAM3.1 (phase 7) | a) keep it for video tracking, deferred until the GPU memory allows it (about 7000 MiB peak). b) try true-int4 compute to shrink it (the 2026-09-04 plan) |
| S6 | EOVSAM (phase 7) | a) measure it after S1: the owner downloads the model (hustvl/EOVSAM), then one run against R4. b) skip it: our passes hold 1-3 concepts |

Owner rulings (decision ledger): S1 a (done: one encoding per pass); S2 b now, a on the back burner; S3 done by D2; S4 a (accept); S5 and S6 replaced by S5-M (done), VT5 (SAM3 kept) and POST (2): SAM3.1 and EOVSAM evaluated by the owner and the main agent together after the freeze; S7 c done (S7c).
