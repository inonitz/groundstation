# Pre-freeze plan, 2026-10-02: the code implements the design, 1:1 with the API headers

NOT IN FORCE: written before the owner set the ground-truth procedure (GT1). The procedure is
docs/api-harden2/rev3/README.md; this file is input for its step 6 (the change-impact table).

Rulings: DES1 (the design rules the code), API1 (headers and code 1:1 before the freeze), T1 (2),
T3C, STOP1 (3), AUTO1, D1 (one fix pass). The design = the plan documents and the API headers; a
header that drifted from the plan is corrected to the plan.

## Part A. Every Python name in a header (API1)
Measured 2026-10-02 (every public class, method and function, matched to header identifiers):
262 public names; 162 in a header; 100 in none. Two kinds:
- Named differently (the header has it under another name): sam3 VisionBackend / Sam3Backend /
  BackendLoader (header: Sam3, Sam3Load, VisionDetect), PriorityLock (SamLock / SamUnlock),
  ProcessSpec (SupProcess), RosStream (inside Video), Dispatcher.submit.
- In no header at all: the recognizer's inside (fast_path, bypass, guards, numbers, rewrites,
  lexicon, parse, prompts), perception2's inside (engine, verify, concept, counting, vlm_client),
  the screen's helpers (app/ui, draw, chat_rows, status_pane, state), log/perf_report, gemma/server
  helpers, guarded file_op / stream_call, cam_list.
Work:
- A1. Every module gets its header section; every public Python name gets a declaration that
  names it ("python: perception2.verify.split_target"), so the match is exact, not by spelling.
- A2. tools/api_check.py: the match above as a tool; test/test_api.py runs it and fails on any
  name missing either way. The gate includes it.

## Part B. The code implements the design
| part | design source | the code today | change |
|---|---|---|---|
| B1 stop and auto | T1 (2), STOP1 (3), AUTO1 | a stop word anywhere halts; auto anywhere switches | a table of whole emergency commands (stop words + the words that may come with them: already, now, the drone, ...); a duration makes it a wait (bypass); auto only as the whole sentence; "stop tracking" clears |
| B2 echo guard | recognizer.h step 5 | Hebrew read with the English number reader | nums_he (finding 7) |
| B3 reject reason | recognizer.h Decision.reject | a text tag parsed back by reject_why | a typed reason on the Decision |
| B4 Routed | recognizer.h Routed (no spoken text: "It never speaks") | Routed carries the text to say | Routed carries control status, mission, vision, task, reject; the app words it |
| B5 masks | sam3.h VisionMaskFor(frame, box); perception.h "one per box" | a one-entry cache of the last detect from any thread; masks and boxes lose their pairing | masks kept per frame (one entry per frame a task holds); one mask per box, or none, in the box's place |
| B6 highlights | plan: several highlights, each its own task until give-up or clear | one highlight; a new one clears the old | several live highlights, each with its own boxes by task; clear all (T3C); perception.h corrected |
| B7 Gemma box | ruling G4: boxes only from SAM3 | a dead fallback that draws Gemma's box | removed |
| B8 webcam | video.h "a live source never ends" | a webcam is not "live": a 7.5 s drop ends the app | every camera and stream is live; only a video file ends |
| B9 refused task | perception.h "refused, not queued"; onStart "before the task runs" | a refused task first starts (thinking on, log opened) | admit first; a refused request starts nothing; "thinking" counts the requests that wait for a first result |
| B10 log slots | the plan's several tasks at once | log.h: two slots; the code: one per task | log.h corrected to one slot per task |
| B11 run.sh down | (safety) | pkill -f on loose names kills unrelated processes | exact command matches |
| B12 planner | the joint review rulings | — | "a bit" = 1 m; feet -> meters; a question never flies; the military sentences and "Roger, continuing the scan" fly nothing; "scramble" takes off; measured by the benchmark |
| B13 ROS redraw | earlier ruling: "Display-loop efficiency (MEASURE first)" | the loop redraws the same frame without a pause | measure first, then decide |

## Change impact
| part | behaviour that changes | tests that stay unchanged | tests rewritten (why) | new tests |
|---|---|---|---|---|
| B1 | a stop word with other content no longer halts unless the table lists it; durations wait; auto needs the whole sentence | the stop-word lists (2026-09-08), "רחפן תעצור מיד בבקשה" | none expected | the table, durations, "stop tracking", auto (4) |
| B2 | a real command equal to an example plan flies | the echo test | none | Hebrew numbers (1) |
| B3, B4 | the app, not the recognizer, words a result | the routing tests | the reject_why test and the tests that read Routed.say (the result shape changes by design) | the typed reasons |
| B5 | masks appear on every box that has one | the engine and vision tests | the stand-in backend's mask_for_box (it gains the frame key) | a concurrent detect keeps the first task's masks; a box without a mask keeps its place |
| B6 | a new highlight no longer stops the old one | count, describe, the gate | the tests that assert "a new highlight clears the old" (the design says otherwise) | two highlights live at once; clear stops all, also one still in its gate |
| B7 | none (the path never ran) | all | none | none |
| B8 | a camera drop shows "waiting", never quits | the screen tests | a test that expects the loop to end on a camera (if one exists) | a webcam with missing frames keeps the app running |
| B9 | a refused request opens no log record and shows no "thinking" | the dispatcher tests | the FULL-path test in app (the special path goes) | refusal starts nothing; thinking counts |
| B11 | `run.sh down` kills only our processes | — | — | a shell naming "llama-server" survives |
| B12 | the plans for these sentences | — | — | the benchmark rerun |

Order: A1 and A2 first (the header is the design the code is checked against), then B1-B12, each
with its tests; then the gate (lint, audit, the suite twice, test_api), the end-to-end test, the
benchmark rerun and one final review. B13 is measured, then brought to the owner.
