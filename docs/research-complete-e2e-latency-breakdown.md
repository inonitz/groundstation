# Command to action: where the time goes (2026-09-30)

The time from a command to its action, split by stage, for a highlight and for a planned mission.
Source: the perf record of three scripted runs (owner ruling FZ2 a). No code was changed.

| section | content |
|---|---|
| Objective | the question |
| Setup | the runs, the script, how a turn is split |
| Results | per stage, per turn type, with shares |
| Analysis | the critical path; what each cut would buy |
| Conclusions | the cuts, largest first; open decisions |
| After L1 + L2 | the first two cuts, measured the same way (2026-09-30) |

## Objective

ROADMAP (line 40) asks for command to action under 1 s. The first perf record of the e2e stage
(2026-09-28) gave 3.5 s from a highlight command to its first box and 1.26 s for a planned mission.
This document splits those times into their stages and names what a cut in each stage would buy.

## Setup

- Three runs of the app on the mock phone app (127.0.0.1), C920 webcam, virtual screen:
  `SCRIPT=<file> run.sh up webcam mock`. Sessions: logs/sessions/session-20260930-093550-rog,
  session-20260930-093757-rog, session-20260930-093950-rog. RTX 5070 Laptop; Gemma 4 E4B on Vulkan;
  SAM3-nf4 with one image encoding per detect (2026-09-29).
- The script, the same in each run: highlight "the person" (the first turn of the run), a planned
  two-step mission, highlight "the screen" (not in view), a planned mission, highlight "the chair",
  a planned mission, a typed mission (the fast path, no Gemma). A "clear" after each highlight.
- e2e starts at the transcript: a scripted run has no push-to-talk, so the ASR time is NOT in these
  numbers. It ends at the phone app's reply to the command, or at the first frame shown with the
  highlight's boxes.
- A turn is split with the perf record's own events (an event's time is its end): gemma (the plan
  request), turn (the recognizer's handle), highlight_gate, sam3 (each forward, with its lock wait),
  e2e. Gemma's own split (prompt evaluation, token generation) is from each session's llama-server
  log (proc-gemma.log). The SAM3 lock wait was 0.0-0.1 ms in every pass: no pass waited.

## Results

### A warm highlight: "the chair" (turn 5; 3 runs)

| stage | run 1 ms | run 2 ms | run 3 ms | mean ms | share |
|---|---|---|---|---|---|
| Gemma plan (the kind and the target) | 390 | 396 | 402 | 396 | 27 % |
| recognizer + hand-off to the vision task | 3 | 4 | 4 | 4 | 0 % |
| gate: one SAM3 forward (is it there?) | 539 | 667 | 533 | 580 | 39 % |
| first tracking pass: a second SAM3 forward | 472 | 493 | 490 | 485 | 32 % |
| until the frame with the box is shown | 24 | 38 | 24 | 29 | 2 % |
| **e2e (transcript to first box)** | **1428** | **1597** | **1454** | **1493** | 100 % |

### The first highlight of a run: "the person" (turn 1; 3 runs)

| stage | run 1 ms | run 2 ms | run 3 ms | mean ms | share |
|---|---|---|---|---|---|
| Gemma plan | 1484 | 1810 | 1531 | 1608 | 42 % |
| of which: the prompt, evaluated cold (1998 tokens) | 1162 | 1109 | 1177 | 1149 | 30 % |
| recognizer + hand-off | 5 | 4 | 5 | 5 | 0 % |
| gate: the first SAM3 forward of the run | 2057 | 1720 | 1437 | 1738 | 46 % |
| first tracking pass | 409 | 404 | 399 | 404 | 11 % |
| until the frame is shown | 54 | 43 | 39 | 45 | 1 % |
| **e2e** | **4018** | **3988** | **3421** | **3809** | 100 % |

### A planned mission (turns 2, 4 and 6; 9 turns)

| stage | mean ms | range ms | share |
|---|---|---|---|
| Gemma: the prompt (only the new 22-24 tokens; the prefix is cached) | 91 | 83-99 | 11 % |
| Gemma: generation, 45-46 tokens at 13.9 ms each | 638 | 625-654 | 79 % |
| the plan request's own overhead (HTTP, parsing) | 62 | 42-140 | 8 % |
| the guards, then the POST to the phone app until its reply | 14 | 1-59 | 2 % |
| **e2e (transcript to the phone app's reply)** | **805** | **767-876** | 100 % |

### Other turns

| turn | time | stages |
|---|---|---|
| a typed mission (fast path, no Gemma) | e2e 0.9-1.5 ms | the guards and the POST |
| a refused highlight ("the screen", not in view) | 952-984 ms to the refusal | plan 394-407 ms + one SAM3 forward 542-574 ms |

Frames: the loop ran at about 30 fps (the gap between frames, P50 33 ms), so the wait for the next
shown frame is under one frame period.

## Analysis

1. A warm highlight takes 1.49 s. Its critical path is Gemma's plan, then two SAM3 forwards in a row,
   then one frame. The two forwards are 71 % of it.
2. The second forward repeats the first. The gate runs SAM3 on the frame to decide "present"; the
   tracking loop then runs SAM3 again before its first box is drawn. Drawing the gate's own boxes as
   the first tracking update would remove one forward: about 485 ms, to about 1.0 s.
3. The first highlight of a run takes 3.8 s, 2.3 s more than a warm one. Two cold starts add it. The
   first Gemma request evaluates the whole 1998-token system prompt (1.15 s; later requests evaluate
   11-24 new tokens in about 90 ms). The first SAM3 forward takes 1.4-2.1 s against 0.5-0.7 s warm.
4. Both cold starts can move to start-up: one Gemma request with the plan prompt and one SAM3
   forward on a blank frame, while the app loads. That is the owner's rule 3.3 ("I don't want load
   times to slip into the app runtime"). It would bring the first highlight near the warm 1.5 s. The
   start would grow by at most about 1.2 s + 1.7 s (not measured; both would run beside the rest of
   the load).
5. A planned mission is under 1 s from its transcript: 0.77-0.88 s. Token generation is 79 % of it:
   45 tokens at 13.9 ms each. The mission's JSON length is the lever: every token cut saves 13.9 ms;
   a 20-token answer (the size of a highlight plan) would save about 350 ms.
6. The earlier 1.26 s mission (2026-09-28) followed a describe turn in the default script. These runs
   never exceed 0.88 s. Not measured: whether a describe answer before a plan slows that plan.
7. The ASR time is not in these numbers. With the laptop mic, command to action = the ASR time + the
   times above. Measuring it needs push-to-talk runs with a human speaking, not a script.
8. The phone app here is the mock; its reply takes about 1 ms. On the real phone, the POST and the
   app's own start of the mission add a time this record cannot see.

## Conclusions

The cuts, largest effect first. Each saving is arithmetic on the measured stages, not a measured
result.

| id | cut | turns it helps | saves (estimate) | result (estimate) |
|---|---|---|---|---|
| E1 | warm Gemma (the plan prompt) and SAM3 (one forward) at start-up | the first Gemma turn and the first highlight of a run | 1.15 s + 1.2-1.6 s | first highlight ~1.5 s |
| E2 | draw the gate's boxes as the first tracking update | every highlight | ~485 ms | warm highlight ~1.0 s |
| E3 | a shorter plan answer (fewer JSON tokens) | every Gemma plan | 13.9 ms per token | planned mission ~0.45-0.6 s |
| E4 | the wait for the next frame | - | under 33 ms | nothing to gain |

Open for the owner: whether to do E1, E2 and E3, and in which order. None is decided.

## After L1 + L2 (2026-09-30)

The owner ruled two cuts: L1 = E1 (warm Gemma with one plan and SAM3 with one pass at start; the
rows turn UP after the warm-up) and L2 = E2 (the gate's own boxes are the first drawn update). Three
runs with the same script and setup as above. Sessions: logs/sessions/session-20260930-095934-rog,
session-20260930-100124-rog, session-20260930-100320-rog.

### Command to action, before and after (e2e from the transcript; ms)

| turn | before (3 runs) | before mean | after (3 runs) | after mean | change |
|---|---|---|---|---|---|
| first highlight of a run ("the person") | 4018 / 3988 / 3421 | 3809 | 867 / 1202 / 841 | 970 | -2839 (-75 %) |
| warm highlight ("the chair") | 1428 / 1597 / 1454 | 1493 | 915 / 946 / 920 | 927 | -566 (-38 %) |
| refused highlight ("the screen"), to the refusal | 984 / 952 / 961 | 966 | 950 / 943 / 913 | 935 | -31 |
| planned mission (9 turns) | 767-876 | 805 | 743-819 | 773 | -32 (not a target) |
| typed mission | 0.9-1.5 | - | 1.1-1.4 | - | none |

### A highlight after the cuts (the 6 turns)

| stage | mean ms | share |
|---|---|---|
| Gemma plan | 453 (384-735) | 48 % |
| gate: one SAM3 forward | 459 (422-505) | 48 % |
| until the frame with the gate's box is shown | 37 | 4 % |

### The start, before and after (the perf "startup" rows; ms from launch)

| row | before (3 runs) | before mean | after (3 runs) | after mean |
|---|---|---|---|---|
| gemma | 11722 / 7279 / 5492 | 8164 | 9182 / 10894 / 9385 | 9820 |
| sam3 | 12624 / 11080 / 11953 | 11886 | 13221 / 14306 / 12397 | 13308 |
| every row | 12624 / 11080 / 11953 | 11886 | 13221 / 14306 / 12397 | 13308 |
| frames over 100 ms before sam3 is UP | 10 / 8 / 10 | 9 | 12 / 12 / 7 | 10 |

The warm-up requests: Gemma 1553 / 2037 / 1576 ms (the 2000-token prompt, evaluated once, 1050-1141 ms
of it); SAM3 one pass on a blank frame, inside the "sam3" row's time.

### Analysis of the cuts

1. Every highlight in view now reaches its first box in under 1 s but one: 0.84-0.95 s, and 1.20 s
   in run 2 (below). The first highlight of a run lost 2.8 s; a warm one lost 0.57 s.
2. L2 removed the second SAM3 forward: a highlight is now the plan, one forward and one frame.
3. L1 removed both cold starts from the first command: its gate forward is 422 ms (was 1437-2057 ms),
   and its plan request evaluates 11 new tokens (75-102 ms), not the whole prompt.
4. The price is at start: every row is UP 1.4 s later (11.9 -> 13.3 s, mean of 3). The start stutter
   is unchanged (7-12 frames over 100 ms before SAM3 is UP, against 8-10).
5. One outlier: run 2's first plan took 735 ms, while Gemma's own log shows 371 ms (102 ms prompt +
   269 ms generation). The other 364 ms are outside llama-server (the client, HTTP); not explained.
6. The planned mission did not change (0.77 s): its cost is token generation (E3, not done).

### Open

- E3 (a shorter plan answer) is still open: 13.9 ms per token on every Gemma plan, highlights included
  (their plan is now half of the highlight's time).
- The 364 ms outside llama-server in one of three first plans: not explained.

