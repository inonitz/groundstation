# Steps 5 and 6: the gaps between the ground truth (rev3 draft) and today's code

Each gap says four things: what the design says (with its source), what the code does, what a user
sees, and the proposed change. "Kind" is one of: CODE DEVIATES (change the code) or DOCS LAG (the code
is faithful; write it into the header, owner's step 7). No gap is open: every one is decided by a
ruling, named in the gap (owner, GT1 (3): "Rulings have all the information"). Nothing here is
implemented. Evidence for the code column: docs/refactor/code-review-2026-10-01.md
(10 findings, each verified in the code) and docs/refactor/thermonuclear-review-2026-10-02.md.

## A. Vision

### G1. How many highlights can be alive
- The design: several. Each highlight is its own task, up to 8 tasks, and lives until its give-up
  timeout or a clear (refactor handoff 4a; spec line 255; ruling TN2).
- The code: one. `Vision._track` calls `self.clear()` first, so a new highlight stops the old one.
  The screen state holds one set of boxes (app/state.py: hl_dets, hl_masks, target).
- A user sees: "highlight the chair", then "highlight the door": the chair's boxes vanish. Sometimes
  the door's boxes vanish too for about a second, with "Cleared the highlight." printed after
  "Highlighting: door" (the old task's last update lands after the new task's first one).
- Kind: CODE DEVIATES.
- Change: remove the clear() in _track; the screen state keeps boxes per task (a dict by task id) and
  draws all of them; an update from a task changes only that task's entry.
- Tests: new: two highlights alive at once, each with its own boxes; rewritten: any test that asserts
  "a new highlight clears the old one".

### G2. What "clear" reaches
- The design: `VisionClear(task)`: 0 clears every live highlight; a task id clears that one (v2.3;
  rulings T3C, TN2). A highlight is a task from the moment it is submitted.
- The code: `clear()` takes no task and stops only highlights that already passed their gate (a
  highlight registers its stop event inside _track, after the gate).
- A user sees: "highlight the red car", then "clear" (or F2) while the check still runs: nothing is
  cleared; the highlight appears a moment later and stays.
- Kind: CODE DEVIATES.
- Change: register the stop event when the task is admitted; clear(task=0) stops all; clear(task=n)
  stops one; a task stopped in its gate reports CLEARED and draws nothing.
- Tests: new: clear during the gate; clear one of two.

### G3. A refused request
- The design: `TASK_FULL`: "refused, not queued"; onStart runs "before the task runs" (perception.h).
- The code: `_submit` calls on_start (the log record opens, "thinking..." turns on) and only then asks
  the dispatcher for room.
- A user sees: with 8 tasks alive, a ninth request is refused and spoken as such, but "thinking..."
  stays on the screen.
- Kind: CODE DEVIATES.
- Change: ask the dispatcher for a slot first; only an admitted task calls on_start. "thinking" becomes
  a count of requests that wait for their first result (several tasks run at once, G1).
- Tests: new: a refused request opens no record and shows no "thinking"; rewritten: the app's test of
  the FULL path (its special handling goes).

### G4. Which masks a box gets
- The design: a mask for a given frame and box (sam3.h VisionMaskFor(frame, box)).
- The code: the SAM3 model keeps the masks of its LAST detect only, from any thread
  (sam3/model.py `self._cache`); the drawing step asks it later.
- A user sees: for "the bag held by the child", the first frame shows boxes with no masks: the verify
  step ran two more detects in between and replaced the masks. With several tasks (G1) it happens
  more often.
- Kind: CODE DEVIATES.
- Change: keep the masks per frame (one entry per frame a task still holds), so a later detect on
  another frame cannot replace them.
- Tests: new: a detect on frame B does not remove frame A's masks.

### G5. One mask per box
- The design: "masks: one per box, or NULL when masks are off" (perception.h HighlightUpdate).
- The code: a box with no clean mask is kept without one, so the masks list gets shorter than the box
  list; `_drop_specks` then pairs them by position.
- A user sees: a mask drawn on the wrong object, or missing from the right one.
- Kind: CODE DEVIATES.
- Change: a box with no mask keeps an empty place in the list; every pairing stays by position.
- Tests: new: a box without a mask followed by a box with one.

### G6. A box from Gemma
- The design: boxes come only from SAM3 (ruling G4, 2026-09-22: "we stopped doing that BECAUSE it was
  inaccurate!").
- The code: `PerceptionEngine.draw_step` / `highlight_step` can draw a Gemma box when SAM3 finds
  nothing; every caller passes "no box", so it never runs; `presence_gate` computes a box nobody reads.
- A user sees: nothing today.
- Kind: CODE DEVIATES. The ruling of 2026-09-22 decides: Gemma never draws a box. TR16 (never delete
  working code because git keeps it) protects code that does what the design wants; this path does
  what a ruling forbids.
- Change: remove the Gemma box from draw_step, highlight_step and presence_gate (the gate keeps its
  yes/no answer).
- Tests: the gate tests stay; none is expected to change (no caller passes a box).

### G7. The one set of callbacks
- The design: v2.3 gave each request its own callback (CountDoneFn, HighlightFn, DescribeDoneFn).
  The ruling of 2026-09-23 night: a module gets its callbacks in its constructor.
- The code and v2.4: one VisionSinks struct given when Vision is created.
- Kind: DOCS LAG. The 2026-09-23 night ruling decides (callbacks in the constructor); rev3 keeps
  VisionSinks. No change to the code.

### G8. The jobs pane
- The design: a pane of active jobs; a click focuses or deletes one (T3C (2)). Not designed further.
- The code: none.
- Kind: CODE DEVIATES (the feature is ruled and not built). T3C (2) decides what it does: it lists the
  live vision jobs; a click focuses one or deletes one.
- Change: Vision gives the list of live jobs (rev3: VisionJobs); the screen draws the pane; a click
  on a job deletes it through VisionClear(task), or focuses it (its boxes drawn alone or marked).
- Tests: new: the list follows the live tasks; a click on a job clears only that job.

## B. Video and the screen

### G9. A camera that stops sending frames
- The design: "a live source never ends" (video.h).
- The code: only ros, stream and gstreamer sources are "live"; a webcam is not. After about 7.5 s of
  missing frames (READ_RETRY misses) the screen loop returns, and the app closes every module, stops
  its processes and kills the tmux session.
- A user sees: the webcam cable slips for a few seconds and the whole ground station quits.
- Kind: CODE DEVIATES.
- Change: every camera and stream is live; only a video file ends. The screen shows "waiting for
  video" and the video row reports the stall.
- Tests: new: a webcam with missing frames keeps the loop running.

### G10. The same frame drawn again and again
- The design: an earlier ruling: "Display-loop efficiency (MEASURE first)".
- The code: on VIDEO=dji, RosStream.read() returns the last frame on every call; the loop redraws it
  without a pause and records each redraw as a frame.
- Kind: the earlier ruling decides the order: MEASURE FIRST. A task for the builder: measure the CPU
  use and the frame record on VIDEO=dji (the mock video path), write the numbers into HISTORY, then
  make RosStream.read() wait for a new frame if the numbers show the waste.

## C. The recognizer

### G11. Stop, auto and "stop tracking"
- The design: the emergency is a table of whole commands (T1 (2)); a stop word alone halts in every
  mode, with a duration it waits (STOP1 (3)); auto acts only as the whole sentence (AUTO1); "stop
  tracking" clears a perception job (ruling 2026-09-08, for the Hebrew form).
- The committed code: a stop word anywhere halts; "המשך" anywhere switches to auto and drops the rest
  of the sentence; the English "stop tracking" halts.
- The four files in the working tree: durations wait, auto needs the whole sentence, "stop tracking"
  clears, but a stop word anywhere still halts (not the table).
- A user sees (committed code): "continue forward 5 meters" flies nothing and switches to auto; "stop
  for 10 seconds" halts; "stop tracking" halts the drone.
- Kind: CODE DEVIATES.
- Change: build the table in recognizer/fast_path.py: strip the words that may come with a trigger
  (the drone, already, now, please, immediately; Hebrew and English), then match the rest against
  the list of stop, manual and auto commands. Keep the four files' other parts.
- Tests: the 2026-09-08 stop-word lists must pass unchanged; new: the table, durations, "stop
  tracking", auto.

### G12. The echo guard reads Hebrew with the English number reader
- The design: a plan equal to a planner example is refused only when the sentence has none of its
  numbers (recognizer.h step 5).
- The committed code: `is_shot_echo` uses nums_en on Hebrew text; "בעשרים" (by twenty) reads as no
  number.
- A user sees: "turn the drone right by twenty degrees" is refused as a copied example.
- Kind: CODE DEVIATES. Fixed in the working tree (nums_he), with a test.

### G13. The reject reason
- The design: Decision.reject is a typed reason (recognizer.h RejectReason).
- The code: a text tag ("reject-numbers[5.0]"); `reject_why()` matches its prefix to rebuild a
  sentence; app/turns.py imports it.
- Kind: CODE DEVIATES (ruling TN1, T5).
- Change: the Decision carries the reason from the guard that made it.
- Tests: rewritten: the reject_why test (the function goes); the routing tests stay.

### G14. What a Routed result holds
- The design: recognizer.h Routed: the control status, the mission, the vision kind, the target, the
  task, the reject reason; "It never speaks and never draws: the app turns the result into chat,
  speech and log".
- The code: Routed holds kind, action (a log tag), say (the text to speak), vision_task,
  vision_status; the recognizer words the text.
- Kind: CODE DEVIATES. The owner approved recognizer.h as API v2.1 (2026-09-23) and ruled that the
  recognizer never speaks: the header decides.
- Change: Routed carries the control status, the mission, the vision kind, the target, the task and
  the reject reason; app/turns.py words the chat and speech text from them (control.outcome_text is
  already the one wording of a flight result).
- Tests: rewritten: the tests that read Routed.say or Routed.action (the result's shape changes by
  design); the routing decisions themselves stay.

### G15. A result kind the header lacks
- The code: Routed kind "empty": Gemma planned a mission with no steps, so nothing flies.
- Kind: DOCS LAG (owner's step 7: faithful code the docs did not show). rev3 holds ROUTED_EMPTY.

### G16. Plans the owner ruled in the joint review
- The design (JR9, JR11, JR15, MIL1): a question never flies; "Roger, continuing the scan" flies
  nothing; "a bit" is exactly 1 m; "one more pass", "returning to the rally point" and "fly low along
  the wadi" fly nothing; "scramble" takes off; 800 feet is 243.8-244 m.
- The code: Gemma plans a landing for "is it possible to land now?"; flies 1 m for the "Roger"
  sentence; plans `home` for "scramble"; plans 800 METERS for 800 feet; flies the three military
  sentences.
- Kind: CODE DEVIATES (the planner prompt and one bypass rule).
- Change: a bypass rule for "a bit"; prompt examples for the rest; measured by the benchmark
  (bench/recognizer; the labels already expect the right answers).

## D. Log, tools, coverage

### G17. Log slots
- v2.4: two slots (vision, describe). The code: one slot per vision task.
- Kind: DOCS LAG (several tasks need one record each). rev3 corrected.

### G18. `run.sh down`
- The code: `pkill -9 -f` on loose names ("llama-server", "python3 -m app.main", "mock_apiserver.py").
- A user sees: `run.sh down` also kills a benchmark's own Gemma, or a shell whose command names one
  of them.
- Kind: CODE DEVIATES (a safety fix; no header covers run.sh).
- Change: match the exact command lines of the processes the app started.

### G19. 100 public names in no header
- The list: AS-BUILT.md (by file, with each signature and its docstring's first words).
- Kind: DOCS LAG (owner's step 7; API1 decides: 1:1). Every name in AS-BUILT.md gets its declaration
  in its module's rev3 header, naming its Python counterpart. A name that contradicts a ruling is a
  code deviation and is listed above (reject_why: G13; the Gemma box parts: G6).
- Change: write the declarations; add tools/api_check.py and a test that fails on any name missing in
  either direction.

## E. From the owner's header review (HDR1, 2026-10-02)

### G20. The name "Turns"
- The design (owner): ONE struct "Turn" (the request and the response), kept as a list.
- The code: the Turn record exists: SessionLog builds it per turn and writes it as one line of
  trace.jsonl (rev3 log.h: struct Turn). The class named Turns (app/turns.py) holds no turn data: it
  is the handler a transcript runs through. No list of turns is kept in memory; the chat pane keeps
  its own 60 lines (app/state.py).
- Kind: CODE DEVIATES. Change: rename the class to TurnHandler (rev3 app.h); SessionLog keeps the
  committed Turns in a list (the owner, HDR1: "a single struct called "Turn", which is maintained in
  a vector"). The chat pane keeping its own 60 lines stays as built until the owner says otherwise.

### G21. The scripted run in app.h
- v2.4 app.h declared FeedMain and FeedPublishTranscript. They are test tools: the app never calls
  them. They publish sentences on the ASR topic so a test drives the real app through its real input.
- Kind: DOCS LAG. rev3 moved them to scripted_run.h, with the reason they exist (ruling 2.1 / Q4: the
  second main left app/ and became test/scripted_e2e_run.py).

### G22. Structs with no members
- Every rev3 struct now lists its data members, one per attribute of the Python class named beside it.
  Opaque by purpose: the OS primitives (lock, event, condition, thread, queue) and three third-party
  objects (a parsed JSON value, an asyncio stream, an rclpy publisher).
- keys.h is its own header (owner HDR1); app.h includes it.

