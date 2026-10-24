# Thermo-nuclear code-quality review, harden2, 2026-10-02

Started by the owner (/thermo-nuclear-code-quality-review). Scope: projects/integration_harden2,
8439 lines of code without tests. No file is near 1000 lines (the largest: perception2/vision.py,
436). Each finding names the structural move, the bugs it removes, and its cost.

## T1. The fast path searches keywords anywhere in a sentence (recognizer/fast_path.py)
- Today: EMERGENCY_RE / MANUAL_RE / AUTO_RE use search(); one stop word anywhere halts, one
  "המשך" anywhere switches to auto.
- Bugs it causes: review findings 4 ("continue forward 5 m" -> auto) and 10 ("stop tracking" ->
  emergency); STOP1 (3) ("stop for 10 seconds" must wait).
- Move: a trigger is a whole command. Strip fillers (רחפן, בבקשה, מיד, עכשיו, please, now), then
  match the rest against one table {phrase -> emergency | manual | auto | clear}. A stop word
  with a duration goes on to the bypass as a wait. The three regexes and the lookahead special
  cases disappear.
- Safety: a stop word alone, with fillers, still halts in every mode (STOP1 (3)).

## T2. Masks travel as a second list next to the boxes (perception2/engine.py, vision.py, sam3/model.py)
- Today: detect() returns boxes; masks come later from mask_for_box(), a one-entry cache that
  the next detect (any thread) replaces; kept boxes and masks are two lists paired by index.
- Bugs it causes: review findings 3 (verify's detects wipe the cache: boxes drawn without
  masks) and 6 (a box without a mask shifts every later mask by one).
- Move: detect() returns each detection with its own mask (d["mask"]). The cache, its lock,
  mask_for_box() in the backend contract and the parallel masks lists disappear.

## T3. The code allows ONE highlight; the plan allows several (perception2/vision.py, app/, perception.h)
The design, as the plan documents carry it (read 2026-10-02, line by line):
| date | source | text |
|---|---|---|
| 2026-09-21/22 | refactor handoff 4a, lines 57-59 (owner rulings) | "HIGHLIGHT = gate, then a persistent record re-detected ... until the 8 s give-up or CLEAR"; "Task cap VISION_MAX_TASKS = 8" |
| 2026-09-22 | the owner's messages | one thread per detection query, up to 8; a highlight persists "until a manual override is sent"; "Clear Was pressed for this specific/All detection Queries" |
| 2026-09-23 | spec, line 255 (owner design, restated) | "a dispatcher ... spawns one thread per task, max 8 ... A highlight thread lives until clear or give-up" |
| 2026-09-23 | refactor handoff line 392 (agent progress, step 6) | "one highlight at a time": the deviation, with no ruling |
| 2026-09-24 | perception.h v2.3 | VisionHighlight: no "replaces" |
| 2026-09-26 | perception.h v2.4 (synced to the code) | "replaces the live one": the deviation copied into the header |
- Bugs it causes: review findings 1 and 2 (both come from one highlight replacing another).
- Move: restore the design in the code and in perception.h. Every highlight is its own task with
  its own boxes, keyed by its task id; the screen draws all live highlights; a new highlight stops
  none; a clear stops all, including those still in their gate; "clear this one" is in the design
  and needs a way to name a highlight (open).
## T4. A Gemma box fallback that no caller uses (perception2/engine.py)
- draw_step()/highlight_step() take vlm_box_px and draw a Gemma box when SAM3 finds nothing;
  every caller passes None, and presence_gate() computes a box nobody reads.
- It contradicts the ruling G4 (boxes only from SAM3, 2026-09-22). Owner rule TR16: unused code
  gets a test or a ruling, so this needs the owner's word to go.

## T5. A reject's reason is rebuilt by parsing its tag (recognizer/recognizer.py reject_why)
- Today: the guard writes an action tag ("reject-numbers"); reject_why() matches string
  prefixes to turn it back into a sentence, and app/turns.py imports it to show the reason.
- Move: the Decision carries its reason when the guard makes it. reject_why() and the prefix
  matching disappear.

## T6. A missed video frame can end the whole app (app/ui.py, video/video.py, video/ros_stream.py)
- Mechanism: Ui.run() returns "input ended" after READ_RETRY missed reads when the source is not
  "live" (live = ros/stream/gstreamer only); main() then closes every module and service and
  kills the tmux session. The rule was written for a video FILE (its end ends the run); the
  webcam was left out of "live".
- Bug: review finding 8 (a 7.5 s webcam drop quits the ground station).
- Move: the screen never ends on missed frames. It shows "waiting for video" while the video
  row reports the stall (Video already watches stalls and reopens the source). Only the user
  quits. Separately, finding 9: RosStream.read() returns only a NEW frame, so the loop waits
  instead of redrawing the same one.
## T7. A refused vision task first starts, then is refused (perception2/vision.py _submit)
- Root cause: _submit() calls on_start() (thinking on, log record opened) BEFORE the dispatcher
  decides whether there is room. A refused task has already "started".
- Move: ask the dispatcher for a slot first; only an admitted task calls on_start(). A refused
  request opens nothing, so nothing must be undone, and the special FULL path in app/turns.py
  goes.
- With several highlights at once (T3), one on/off "thinking" flag cannot be right either: the
  first task to answer would clear it for all. It becomes a count of requests still waiting for
  their first result: +1 when admitted, -1 at the first result.
## T8. The transmit switch lives in the phone client, its policy in control (dji_app/client.py, control/flight.py)
- Today: DjiApp holds the switch and blocks motion; Control holds the lock and every rule about
  it (manual, auto, the emergency in manual mode).
- Move: the switch moves into Control; DjiApp becomes plain transport. Behaviour stays.
- Cost: it touches the safety path; the benefit is clarity, not a bug. Recommendation: after the
  freeze.

## What is good
- No file is near 1000 lines; the largest is 436.
- The service/module split (app/main.py Services, constructors with services or callbacks) is clean.
- route() deciding and act() acting keeps the recognizer testable and benchmarkable.

## Verdict
Not approved before the fix pass. T1, T2, T3, T6 and T7 are structural causes of confirmed bugs;
each is a presumptive blocker. T4 needs the owner's ruling. T5 is a small cleanup. T8 is optional.

## The fix pass this review proposes (one pass, ruling D1)
| part | removes |
|---|---|
| T1 the trigger table | findings 4 and 10; STOP1 (3) "stop for N seconds" waits |
| T2 masks inside the detections | findings 3 and 6 |
| T3 several highlights, each with its own boxes | findings 1 and 2 |
| T6 one read contract | findings 8 and 9 |
| T7 admit before start; a waiting count | finding 5 |
| T5 the reason on the Decision | reject_why's prefix parsing |
| the echo guard reads Hebrew numbers (nums_he) | finding 7 |
| run.sh kill_stack matches exact commands | unrelated processes killed |
| the planner prompt (with the benchmark rerun) | "a bit" = 1 m; feet -> meters; a question never flies; "Roger, continuing the scan" and the military sentences fly nothing; "scramble" takes off |

## Headers against the code and the plan (checked 2026-10-02, every declared name)
| header | mismatch |
|---|---|
| perception.h | "VisionHighlight ... replaces the live one" contradicts the plan (several highlights; clear one or all). The code follows the header. |
| recognizer.h | Decision carries a typed RejectReason; the code carries a string tag and rebuilds the reason (T5). Routed differs: the header has control, actionsJson, vision, target, task, reject, fromFastPath; the code has kind, action, say, vision_task, vision_status. RouteKind lacks the code's "empty". |
| log.h | two log slots (vision, describe); the code opens one slot per vision task (slot=task). |
| sam3.h, video.h | match the code today; T2 and T6 change both. |
| util, runtime, dji_app, control, audio, gemma, app | every declared name exists in the code. |
The fix pass brings every header and the code to one design, in the same change (rule 6.2).
