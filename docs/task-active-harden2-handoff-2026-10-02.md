# harden2 handoff, 2026-10-02: to the agent that builds

You take over from the agent of 2026-10-01/02. It ran the joint review, the benchmarks and both code
reviews, and it found that the API headers and the code drifted apart. The owner then set a procedure
to build a ground truth. The planning is done on paper (ledger GT1 .. GT1 (3)): the ground truth is docs/api-harden2/rev3; your
job is to build it. Start coding only when the owner tells you to start.

| section | content |
|---|---|
| 0. Read first | the order |
| 1. Where we stand | the road, and what blocks it |
| 2. Your job | the ground-truth procedure, then the build |
| 3. Decided, waiting for the build | every ruled change, with its ledger ID |
| 4. The working tree | what is uncommitted, and four half-done files |
| 5. Lessons of this session | each with the incident |
| 6. Where everything is | the documents |

## 0. Read first
1. This file. 2. docs/api-harden2/rev3/README.md (the procedure and its state).
3. docs/task-active-harden2-handoff-2026-10-01.md sections 1-3 and 7 (the hard rules, the 19 lessons,
   the system, the agents); its sections 4-6 are superseded by this file and docs/harden2-status.md.
4. docs/guidelines.md. 5. docs/spec-harden2-cleanup.md "Decision ledger": the rows dated 2026-10-01
   and 2026-10-02 (CP3 .. GT1) are this session, word for word. 6. docs/HISTORY.md, the entries of
   2026-10-01 and 2026-10-02.

## 1. Where we stand
- Road steps 1-3 (RM1) are DONE: the joint review of every label and draft (ledger JR4-JR17, MIL1), B2
  and the benchmark rerun (473 of 545 PASS; recordings 92 of 106 on the labels, 85 on whisper's
  text; whisper's word error rate 9.6 %), the cleanup.
- Step 4: /code-review found 10 bugs, all verified (docs/refactor/code-review-2026-10-01.md); the
  thermo-nuclear review is written (docs/refactor/thermonuclear-review-2026-10-02.md). NOTHING of it
  is fixed. The owner then found the real blocker: headers and code are not 1:1 (API1), so there
  is no ground truth to fix the code against.
- Steps 5-8 (the webcam test, the field test, the walk-through, the freeze) wait for that.

## 2a. UPDATE (2026-10-02, later): the owner is redesigning the API: rev4
After rev3, the owner reviewed every header and is devising a better API with the agent:
docs/api-harden2/rev4/ (README.md there: the rules, the state, what changes). rev4 is the design to
build ONCE THE OWNER APPROVES IT; until then rev3 + GAPS.md describe what was ruled before the redesign.
Read docs/api-harden2/rev3/REVIEW-1-owner.md, rev4/REVIEW-2-owner.md and rev4/REVIEW-3-owner.md: they are the
owner's own words. Round 4 (2026-10-04) rejected the round-3 designs: rev4/REVIEW-4-owner.md (his words), rev4/REVIEW-4-answers.md
(every point with its full picture and the proposal as code). The house rules of round 4 are the ledger rows HDR6 ..
AUD3 (CODE1, ONE1, PROC2, OWN1, NAM2, TEL1, PRF2, REC1, VIS1, VIS2, ARC1, CTX1, ATM1, FR1). Next: a design review per
system in plan mode, the vision system first; a spec per system that the owner approves; only then the headers.

## 2a3. UPDATE (2026-10-17): the rev5 module reviews, where to resume

### A. Read first
| order | file | why |
|---|---|---|
| 1 | docs/api-harden2/rev5/README.md | the procedure and the house rules |
| 2 | docs/api-harden2/rev5/modules/README.md | the template, the eleven-point gate, the state table, the carried items |
| 3 | docs/spec-harden2-cleanup.md, rows PRF1-PRF6, TEL1-TEL19, RUN1-RUN14, MOD1, MOD2, GATE1 | every ruling, verbatim |
| 4 | docs/api-harden2/rev5/01-system-architecture.md and .html | THE settled high-level design and its drawing (RVW1-RVW7 applied); the pending edits from the module reviews are listed under "the app step" at the bottom of modules/README.md |
| 5 | docs/api-harden2/rev5/01-system-sketch.md, 05-review-summary.md | how the design was reached: the forces (section 4) and the review's 23 items |

### B. Done
| module | files in rev5/modules/<name>/ | review record | state |
|---|---|---|---|
| perf | perf.md, perf.h, perf.html, perf_record_<owner>.h x7 | rev5/test/round-*.md, conclusions.md | APPROVED (PRF3-PRF5) |
| telemetry | telemetry.md, telemetry.h, telemetry_record_dispatch.h, telemetry_record_vision.h, telemetry.html, telemetry-writes.html | rev5/test/telemetry-*.md | APPROVED (TEL2-TEL19) |
| runtime | runtime.md, runtime.h, runtime_internal.h, runtime.html | rev5/test/runtime-*.md | APPROVED (RUN1-RUN14) |

### C. The procedure per module (do not shorten)
| step | what | where it is defined |
|---|---|---|
| 1 | the full picture: today's code and callers, the rulings, the forces measured on this machine | CTX1, BRN2 |
| 2 | <name>.md in the template order; <name>.h readable without comments; <name>_internal.h only for a mechanism the owner must see; NO drawing unless he asks (DOC1) | MOD1, MOD2, RUN3, RUN4, DOC1 |
| 3 | the eleven-point gate, answered in section 7b with the failure matrix | GATE1, RUN14 |
| 4 | three reviewer rounds before the owner: general-purpose agent, model opus; round 1 three lenses, round 2 push-back, round 3 landing check; every accepted finding applied the same turn; ONE record file per module in rev5/test/ (DOC1) | the briefs in rev5/test/*-round-1-* |
| 5 | the owner's review; his Gemini reviews judged on the merits against his rulings, taken or rejected in the ledger | RUN2, RUN4-RUN6, RUN10 |
| 6 | every ruling into the ledger and the document the same turn; decision lists with full context | the guidelines |

### D. What each review taught
| module | fault in my first draft | the rule now |
|---|---|---|
| perf | a thread-local write index the writer could not see | review the Python mapping as code |
| perf | a payload cut mid-JSON | never cut; replace and count |
| perf | the file format only in prose | the file contract in the header |
| perf | the table sized by nproc | the design's thread count, never the machine's |
| telemetry | the main thread waited 5 s on a full queue | the main thread never waits on a logger |
| telemetry | die() on a disk fault | a logger never dies (TEL2); drop, count, one event |
| telemetry | domain records inside the sink | a generic sink; the owners hold their records (TEL3) |
| telemetry | JPEG frames; the reserve for a busy hour | lossless PNG at the source's size; the rule from the real vision rate |
| telemetry | a frozen dataclass "copy" | it freezes nothing inside; copy during the call |
| runtime | a SIGCHLD handler | it waits behind a C call (665 ms); a pidfd per child |
| runtime | waitpid(-1) | it steals other callers' exits; reap only own pids |
| runtime | modules launched their own process | the supervisor owns the processes (RUN9) |
| runtime | a flag named after llama-server | a stop policy per spec |
| runtime | a global struct and loop functions in the public header | the house split; internals cut to a boundary or a pure test |
| runtime | the hand-over through the emergency thread | the hand-over sends its POSTs itself |
| all | a summary that dropped sub-choices; sentences transcribed, not designed | TEL13, TEL3 (3) |

### E. Every module, all details (status 2026-10-17; the recorder note of 2026-10-19 below)
**2026-10-19: perf (item 1) and telemetry (item 2) are FOLDED into one module, the recorder
(rev5/modules/01-recorder: recorder.md, the headers, the drawing; the ledger RCD1 to RCD11).
Every module reaches it without a handle: RecordSpan, RecordEvent, RecordFrame with typed fields;
MonotonicNow for every timestamp. The general structures it is built on are in rev5/modules/00-util
(a byte ring with one producer and one consumer, an index queue, fixed texts). Items 1 and 2
below are history until the fold deletes their folders.**

Fifteen modules in the review order of rev5/README.md. For each: the job; what the design document
says; today's code; the state; the decisions taken; what it must still settle; what it depends on.

**1. perf. APPROVED (PRF3 to PRF5, PRF6 a comment).**
- Job: the timing record of a run, from any thread, to disk.
- Design: section 7 (a tracer per process, a lock-free ring per thread, one merge by the clock).
- Today: log/perf.py (208 lines), log/perf_report.py. Replaced whole.
- Decided: PerfCreate(sessionDir, processName); PerfNow; PerfRecord(stage, start, end, payload);
  PerfFlush in Die's step 3; a ring of 4096 fixed 128-byte records per recording thread, found
  through thread-local storage, drained by one writer every 5 s to perf-<process>-<pid>.jsonl;
  the clock line first (monotonic, realtime, boottime); a drop line per ring per drain; the stage
  enum (16 stages) with the payload keys per stage as the report's contract; PERF_GPU once a
  second by the main thread, no queue depths; the table size is the design's thread count (16
  app, 2 SAM3), a config constant, never nproc; a thread past it is a bug and dies; the Python
  ring is a bytearray with struct.pack_into; the writer sleeps on an Event.
- Helpers: perf_record_<owner>.h x7 (screen, dispatch, vision, sam3, llama, platform,
  speech_out); each moves into its module's header at that review.
- Still to settle: nothing. The report rewrite is a build task.

**2. telemetry. APPROVED (TEL2 to TEL19).**
- Job: the events, frames and masks of a run to disk, for replay; it never kills the app.
- Design: section 7; section 9's failure handling for its drops.
- Today: log/session.py (265), log/disk.py, log/session_files.py, log/show.py. Replaced whole.
- Decided: a generic sink (RecordEvent with a topic and keys; RecordFrame with a channel and
  pixels); the records with their owners (telemetry_record_dispatch.h: a turn twice and an
  event; telemetry_record_vision.h: a pass, a job twice, a box); a ring of 256 events per
  recording thread; a frame pool of 8 and a mask pool of 24 at the source's size, known before
  Create; one writer thread; lossless PNG level 1 for frames and masks, at the source's
  resolution; one trace.jsonl with every line by topic; frames and masks by channel folder;
  write the files, then the line; fsync the trace every 5 s, the PNGs never; a full ring or pool
  drops and counts; a failed write pauses the writer, counts, resumes; a wrong size is
  INVALID_ARG; six health counters read by the main thread each frame; no die() after
  start-up; Create fails under the start reserve; the free-space rule bytes = W x H x 3 x 0.45 x
  30 passes a minute x minutes, 40 minutes at start, 5 minutes of reserve; the mic listener
  carries the newest ASR clip name, "" when unchanged; no clip rename; the stop's reply as a
  PlatformReply from the emergency thread; no blob call.
- Still to settle: nothing. Carried out: the replayer and log/show.py rewrite with a
  sample-session generator (a build task); the ASR node publishing the clip name (speech in,
  the owner's C++).

**3. runtime. APPROVED (RUN1 to RUN14).**
- Job: starts and stops the processes, turns a fatal error into a safe crash, hosts ROS 2.
- Design: sections 2, 3, 9.
- Today: runtime/fatal.py, supervisor.py, status.py, ros.py, deps.py. Replaced whole.
- Decided: Die with four named steps (the hand-over: two POSTs on their own connection, 1 s;
  the notify: one POST /tts, 0.5 s; the flushes: perf and telemetry, 5 s; the children, 10 s),
  each action on its own thread joined against the cap, the first Die wins, a start-up fault
  dies at once; the supervisor owns the processes (SupervisorCreate with every spec; a module
  gives a pure spec function; SupervisorProcess(name); WaitUntilReady; RestartOnPurpose;
  Destroy); one thread, a pidfd per child, one poll, one timer per entry; only own pids reaped,
  through Popen, under the launch lock; every fork on that thread, in its own session, with the
  parent-death signal by a setpriv prefix; a stop policy per spec (SIGINT; llama-server a
  second SIGINT after 2 s; the grace 10 s; the kill logged); the relaunch delays 1.5, 3, 4.5 s;
  the budget 3, reset after 60 s up; a laptop part dies, a phone part waits and retries every
  5 s; the probe per spec every 500 ms with a 200 ms call cap (/health, /status/, a status line,
  a publisher count for the three ROS 2 nodes); the L1 warm-up after UP on the app's start
  thread, the Gemma module's own row says "warm"; the row as one atomic reference to a pair;
  Ctrl+C is the F1 quit; the launch lock (TOCTOU named: the pidfd, no reap or close once
  stopping, the flag checked under the lock, the lock timeout covered by the parent-death
  signal); RosContextInit and Shutdown, a RosSubscription per topic on its own executor thread;
  PreflightOrDie with the ggml version check and the CPU check (a config switch).
- Still to settle: nothing. Carried out: the design document's "SIGCHLD" wording; Die as a third
  sender of the stop; our C++ nodes exit when getppid() is 1.

**4. the frame buffer. NEXT.**
- Job: the shared-memory ring of frames every reader takes the latest from.
- Design: section 6: 32 slots, a sequence number and a reference count per slot (C11 atomics
  through the atomics package, measured 4 us an op), "latest" set after a slot is complete; the
  frame source the only writer, it takes the next slot whose count is zero; a reader acquires
  before use (read latest, increment, re-read the sequence, retry); a job holds its slot across
  the SAM3 request and releases after the reply; the server reads pixels only. Rejected: a
  mutex per slot (SK4), hazard pointers (SK5), the server claiming the slot (RVW3), copy and
  release (RVW3).
- Today: perception2 keeps frames in-process; a snapshot per request.
- Must settle: the slot size per source, known before telemetry and the buffer are created
  (the webcam probed, 1280x720; the drone 1920x1080, a given; a file probed); a geometry
  change is a planned restart of the video path, never a new size mid-run; the frame path's
  thread and copy against the measured 1080p ROS listener cost (17 ms worst stall on the main
  thread, 22 of 30 frames delivered); what the telemetry copy costs on a job thread (0.05 to
  0.18 ms at 720p); a dead reader's count (the SAM3 server dies holding a slot: the supervisor
  relaunches it; the design must say who clears the count); the 32-slot derivation (8 jobs, the
  draw, the telemetry copy is gone, so fewer holders).
- Depends on: perf (timestamps). Parallel with: none.

**5. the llama server.**
- Job: the one llama-server process and its client; one slot, one request at a time.
- Design: section 2 (HTTP :18090), section 8 (489 ms a plan alone, 1362 ms while SAM3 runs).
- Today: gemma/server.py (the spec, the argv, the ready and warm-up), gemma/client.py.
- Must settle: the pure spec function (argv from config, env with the native path, /health as
  the probe, 240 s timeout, the stop policy SIGINT then SIGINT after 2 s then 10 s, BUDGET_SPENT_DIE);
  the client's connection handling (closes its connections before a normal shutdown); the L1
  warm-up after UP and the module's own "warm" row; the request timed from the app
  (PERF_LLAMA_REQUEST with req, label, ok, the server's token timings; perf_record_llama.h
  moves here); the known gotchas (no --image-min-tokens; no q4_0 KV with flash attention;
  thinking off needs both flags).
- Depends on: runtime, perf. Parallel with: the SAM3 server.

**6. the SAM3 server.**
- Job: our detector process: one image encoding per frame, boxes and masks per concept.
- Design: section 2 (a priority queue inside, command before refresh; it holds a slot by its
  count: superseded by RVW3, the job holds it), section 6, section 8 (410 ms a pass alone,
  630 ms with Gemma busy, 1.9 s for three concepts).
- Today: sam3/model.py, loader.py, contract.py in-process with a lock (T6, R2 rule its own process).
- Must settle: the process boundary (the frame by name in shared memory, the request over a
  socket with the frame's sequence number); the pure spec function (python3 -m sam3.server
  --weights nf4 --frames <shm> --port; the probe: a status line on its socket, "ready" after a
  warm pass; its own SIGINT handler that sets its stop event; BUDGET_SPENT_DIE; its own perf
  tracer with PERF_SAM3_PASS: req, wait, boxes; perf_record_sam3.h moves here); the priority
  queue; the reply format (boxes as corners with score and label; masks as 0-or-nonzero bytes
  at the frame's size, at most 3); a GPU out-of-memory dies and is relaunched (section 9); the
  frame size from the buffer.
- Depends on: the frame buffer, runtime, perf. Parallel with: the llama server.

**7. the phone client and its mock.**
- Job: the one client of the phone app (or the mock): /c/fly, /c/stop, /c/takeoff, /c/land,
  /tts; the probe of the phone.
- Design: section 2 (HTTP :8080 | :8079; the phone's server is ktor CIO, concurrent), section 3
  (the platform worker, the emergency thread), section 9 (the phone dead: WAITING, a probe
  every 2 s; a real drone human-only; the loopback check).
- Today: dji_app/client.py (the client, from_env, the mock spec), tools/dji_mock/mock_apiserver.py.
- Must settle: the client's API (the owner's PlatformCommandDispatcher names are the
  dispatcher's; the client sends); the emergency thread's own connection and its PlatformReply
  message for the stop (TEL7); Die's hand-over function (two POSTs, 400 ms each, on their own
  connection); the mock's pure spec function (/status/ as the probe, 25 s, SIGINT, 1 s shutdown,
  the TCP line closed in on_shutdown, BUDGET_SPENT_WAIT_FOR_USER); the mock's "mock: true" in
  its status (A15, a future consideration); PERF_DJI_REQUEST and PERF_EMERGENCY
  (perf_record_platform.h moves here); the stop response measured on the mock (open since RVW3).
- Depends on: runtime, perf. Parallel with: none.

**8. speech in.**
- Job: the two transcript inputs: the mic through the ASR node and ROS 2; the phone's own
  recognizer through one persistent TCP line.
- Design: section 2 (the ASR node; the TCP line in), section 3 (the mic listener, the phone
  listener), section 9 (an "ok" line per transcript back; the socket keepalive; the listener
  owns both; RVW5), AUD3 (the two inputs must be visible in the code).
- Today: audio/asr_ros.py (the ASR spec, the ROS subscription), audio/asr_phone.py (asyncio; goes:
  a plain TCP thread in rev5).
- Must settle: the ASR node's pure spec function (argv from config, PULSE_SERVER, the clip folder
  asr_clips/, a publisher count on /asr_server/transcribe as the probe, SIGINT, BUDGET_SPENT_DIE);
  the mic listener as a RosSubscription that stamps the Transcript message and carries the
  newest clip name ("" when unchanged); the ASR node publishing the clip name (the exact join;
  the owner's C++; he added a log line on 2026-10-16); the phone TCP line thread (the "ok" line,
  the keepalive, its status row); the Transcript message's fields; whisper's time against the
  emergency budget (RVW item 15: measure on a one-word and a five-word utterance).
- Depends on: runtime, the phone client (the mock's spec only). Speech in OWNS the phone's TCP line listener (the owner, 2026-10-18, PHN5 D3). Parallel with: speech out.

**9. speech out.**
- Job: the two voices: the phone's TTS by POST /tts; the laptop's piper; every sentence on both.
- Design: section 3 (two voice workers, a FIFO each, no cutting; SK6), section 8 (a laptop
  sentence takes seconds), review item 18 (the bound of a voice queue, "how would it fill").
- Today: audio/speech_out.py (the outputs and the worker), audio/tts_laptop.py.
- Must settle: VoiceCreate and Destroy per voice; the FIFO and its bound (the owner asked how
  it would fill at 3 passes a second); a refused /tts is a chat line and the row (RVW2); Die's
  notify is NOT through the FIFO; PERF_SAY (perf_record_speech_out.h moves here); the piper and
  phonikud handles.
- Depends on: the phone client, perf. Parallel with: speech in.

**10. the recognizer.**
- Job: one sentence in, one tagged decision out; pure functions (REC1).
- Design: section 4 (the trigger table: emergency, manual, auto, clear act now; anything else to
  the route queue; the stop rule and the epoch counter; RVW6, RVW7), section 8 (a plan 0.5 to
  1.5 s).
- Today: recognizer/recognizer.py, fast_path.py, bypass.py, guards.py, rewrites.py, lexicon.py.
- Must settle: the step functions (match trigger, fixed command, negation, rewrite, planner
  messages, parse plan, numbers match, copied example); the Decision record; the trigger
  table's words (the owner: "Are these the only keywords?"); the recognizer worker thread and
  the Decision message; the epoch carried on a sentence; the warm-up request built here, sent
  by the app; PERF_TURN (perf_record_dispatch.h, the dispatch's).
- Depends on: the llama server. Parallel with: the frame source.

**11. the platform dispatcher.**
- Job: the owner's PlatformCommandDispatcher (NAM2): manual mode, the emergency stop, a command
  list; no log in it (D2).
- Design: section 4 (the command queue, the priority queue with the emergency first; 409 in
  manual; a mission refused while the phone's row is WAITING; no time-to-live).
- Today: control/ (the flight dispatch), app/turns.py pieces.
- Must settle: the platform worker thread and its priority queue; the emergency thread's event;
  the PlatformReply message; manual mode's state (the main thread's, read by the worker as an
  atomic); the HALT mission in auto; the turn's record of the mission (the dispatch helper).
- Depends on: the phone client. Parallel with: none.

**12. the frame source.**
- Job: webcam | drone stream | file; the only writer of the frame buffer.
- Design: section 3 (the frame source thread writes a slot and publishes latest), section 9 (the
  video stalls: a planned restart after 6 s), RVW5 (the gstreamer receiver stays a separate ROS 2
  node).
- Today: video/video.py (the webcam, MJPG 720p 30 fps), video/ros_stream.py (the gstreamer spec
  and the ROS subscription), video/cam_list.py.
- Must settle: FrameSourceCreate and Destroy per kind; the size probe at start (the webcam: open,
  read one frame; the drone: 1920x1080; a file: probed); the gstreamer receiver's pure spec
  function (a publisher count on camera/stream as the probe, SIGINT, BUDGET_SPENT_WAIT_FOR_USER);
  the stall guard's RestartOnPurpose; the drone frames' thread: the ROS subscription's executor
  thread copies 6 MB per frame under the GIL (17 ms worst stall measured on the main thread; the
  design must move or bound it); the two unused kinds dropped (Q3 a).
- Depends on: the frame buffer, runtime. Parallel with: the recognizer.

**13. the vision jobs.**
- Job: the scheduler (a pool of 8, a stop flag per job, the 9th refused), the pure ops, and the
  three job bodies (highlight, count, describe).
- Design: section 3 (the pool), section 4 (a Decision of a vision kind starts a job; a
  VisionResult updates the view; telemetry at an end state), section 6 (the job holds its slot
  across the request), section 9 (a SAM3 or Gemma failure ends the job FAILED; a bug crashes),
  VIS1, PER2 (a tagged payload per kind), the 2026-09-23 design and the JR rulings (the gate, the
  verify, the count's three frames, the describe's two texts).
- Today: perception2/vision.py (the engine, the dispatcher, the tasks), perception2/engine.py.
- Must settle: the JobScheduler as a ThreadPoolExecutor with a live count and an Event per job
  (the ponytail cut; an exception in a pool job never reaches the crash hook, 11.6: the job body
  catches at its top and posts FAILED, RVW item 13); the VisionJobSpec (the input), the control
  (stop, want masks), the VisionResult (one payload per kind); the views the main thread owns;
  the highlight refresh period (one request outstanding by construction); the boxes converted to
  TelemetryBox and the masks recorded (telemetry_record_vision.h moves here); PERF_SAM3_REQUEST
  and the job steps (perf_record_vision.h moves here); the frame to Gemma for describe as a JPEG
  from the held slot (Q4 a); the dedup of nested boxes (TR17).
- Depends on: the frame buffer, the SAM3 server, telemetry, the llama server. Parallel with: none.

**14. the keys.**
- Job: the keyboard hook process and the keys listener; F1 quit, F2 stop every job, F4 manual
  plus a stop, F5 push-to-talk.
- Design: section 2 (the hook on /keyboard/in/raw), section 4 (the Key message; F5 release is
  the ASR mark), RUN11 (Ctrl+C is the F1 quit).
- Today: keys/keys.py (the spec, the subscription).
- Must settle: the pure spec function (a publisher count on /keyboard/in/raw as the probe,
  SIGINT, BUDGET_SPENT_DIE); the Key message stamped by the listener; the key table; keys without
  window focus (a review MEDIUM item).
- Depends on: runtime. Parallel with: none.

**15. the screen and the app.**
- Job: the main thread's loop (drain the queue, act, read the rows, draw, waitKey), the chat, the
  panes; the app's start and stop order.
- Design: sections 3, 4, 5, 10; every carried item lands here.
- Today: app/main.py, app/ui.py, app/turns.py, app/status pane, the StatusBoard.
- Must settle: the start order (the preflight; perf; the frame size probe; telemetry; the
  supervisor with every spec; ROS; the waits; the warm-up; the hand-over and notify registered
  once the phone client exists); the stop order in reverse; the message queue and its five kinds
  with their stamps; the epoch and the stop rule in the main thread; the rows read each frame
  and the chat line on a change; the turn and event helpers (telemetry_record_dispatch.h moves
  here); PERF_FRAME, PERF_GPU, PERF_MESSAGE, PERF_E2E (perf_record_screen.h and
  perf_record_dispatch.h move here); the quit's airborne behaviour (undecided: does F1 hand
  over?); the design-document edits (SIGCHLD to a pidfd; telemetry not a frame reader; the
  records twice; Die a third sender of the stop; a sixth producer of PlatformReply); the safety
  section once the design is final (RVW4).
- Depends on: everything. Parallel with: none.


### 2a4. THE RECORDER, status 2026-10-21 (read before touching the recorder; the ledger RCD1 to RCD25, PY1 to PY3, GIL2)
- Where: rev5/modules/00-util (fixed_text.h, common_names.h, monotonic_clock.h, frame_types.h,
  index_queue.h, spsc_record_queue.h) and rev5/modules/01-recorder (recorder.h, record_field.h,
  record_span.h, record_event.h, record_frame.h, record_file.h; the actors: recording_thread.h,
  frame_pool.h, record_writer.h, recorder_internal.h; recorder.md; recorder.html; the aggregate
  recorder_aggregate_for_review.md for the owner's Gemini side-checks). All compile with
  -Wextra -pedantic. The review record: rev5/test/recorder-review.md (three reviews, three
  blind reads).
- Decided and applied: one recorder per process, ambient; three contracts (a span, an event, a
  frame) with typed fields whose names are string literals (K1); the Python build is a tuple
  per record in a deque per thread, bounded by count (Q1, PY3, measured 150 ns); the C header
  is the contract and a C build defines its own byte form; Create and Destroy everywhere; the
  writer owns the list of queues; a bounded retry queue of 64 lines in the writer (W1); the
  thread cap is the design's 16 (PRF5); the GPU event is dropped; no registration; no word
  "channel"; the names must describe the intent, in the shared language of the field.
- OPEN with the owner: (1) the drawings: he rejected the four per-contract drawings on
  2026-10-21; the rule he gave is in RCD25: generic data-structure constructs and operations,
  the code names beside them, thread and process boundaries as lanes, nothing that this build
  does not implement; the graphviz-and-cairo pipeline in ~/.claude/skills/diagram-authoring
  renders them; (2) his review of draft 14 itself, then the fold of perf and telemetry (deferred
  by him until the recorder is finished); (3) C1 closed (RCD31): unpadded.
- Carried to later modules (do not raise before the refactoring pass): OsEvent and OsLock in
  runtime (done), the mask limit in config, the session folder's mkdir rule, the GPU reader.
- THE FINAL BUILD IS integration_harden3 (RCD76); OPEN 4 DONE (RCD77), 2026-10-24: perf and telemetry are folded
  into recorder.md section 8; their folders and headers are gone; their documents are frozen records in test/.
  The six commits of the four days are in (032334e to 357dfc8). NEXT: the owner's two leftover points (the frame
  buffer's capture time, the llama server's perf helper); then the second wave of designs in the section-2 form.
- THE RECORDER APPROVED (RCD75), 2026-10-24, draft 31. The drawing sources are in test/recorder-drawings/.
  NEXT, in order: (1) the owner commits (the agent suggested the commands); (2) OPEN 4: fold perf.md and
  telemetry.md into recorder.md (decisions, measurements, tests), delete 01-perf/ and 02-telemetry/ and the
  nine helper headers, update the README table; (3) the second wave of designs, each in the section-2 form
  (scheme, our case, the code in camelCase Python with the objects declared once, the C form, the history),
  reviewed by the owner the same way; (4) the rev5 overview and the generic workspace (DOC2); (5) the build.
- THE LISTS REVIEWED; LOCK-FREE WHERE C CAN BE (RCD73, RCD74), 2026-10-24: the drawings approved; the lists cut;
  registration, the health and the stall read are lock-free; the state lock remains for the stop request. Draft
  31. LEFT: the owner's word on keeping the six .dot sources in test/recorder-drawings/ (they live only in
  the session scratchpad); then the module's approval; then OPEN 4 and the second wave.
- THE CODE OF SECTION 2 APPROVED; THE HISTORY MOVED OUT (RCD72), 2026-10-24: recorder.md has eight sections;
  test/recorder-history-2026-10-24.md holds the old 4, 5, 10 and three notes of 8. Draft 30. LEFT: the prose of
  section 2 (the paragraphs), the six drawings with their html paragraphs, then the module's approval. The
  drawings' .dot sources live only in the session scratchpad rec6/; the owner's word is needed to keep them
  in the repo (DOC1 forbids extra files without it).
- THE CODE REVIEW OF 2.1 TO 2.9 (RCD71), 2026-10-24: 2.2, 2.3, 2.5, 2.6, 2.8 good; 2.1, 2.4, 2.7, 2.9 rewritten
  as named steps; the drop marker is now the drop line the thread builds; no entry reuse ruled. Draft 29.
  OPEN: the fate of sections 3 to 11 (table in RCD71); the prose of section 2 (dense; the owner read the
  code only); the drawings (skimmed). NEXT: the owner's look at the rewritten 2.1, 2.4, 2.7, 2.9.
- SECTION 2.0 APPROVED (RCD70), 2026-10-24; the owner reviewed the rest of section 2 in 15 to 20 minutes and
  flagged the dense snippets of 2.1, 2.4 and 2.6 and the drop-marker mess; both fixed (draft 28). Still open:
  entry reuse after unregistration (his word), the dense prose (lighten after the mechanisms), sections 3 to 11
  (keep, move or cut), the drawings (skimmed only). NEXT: his second look at 2.1, 2.4, 2.6, 2.7; then the
  module's approval from section 2 and the drawings.
- THE FIFTH PASS OF SECTION 2.0 (RCD69), 2026-10-24: the owner's eleven answers and an external review
  applied (see RCD69); draft 27. OPEN: entry reuse after unregistration; the owner asked why the drain
  deadline is a field (answer: an instant set per stop request, not a constant). NEXT: the owner reads
  2.0 once more, then 2.1 onward; then the module's approval from section 2 and the drawings.
- THE FOURTH PASS OF SECTION 2.0 (RCD68), 2026-10-24: six fields removed (a lifetime flag, the burst
  fields, pool counters, a progress stamp, a thread-line flag, a line counter) and the rest renamed by
  role; the instance opens with the producers and the consumer; the pass has seven steps; the thread
  line is a queued record. Draft 26. NEXT: the owner reads 2.0 again, then 2.1 onward.
- THE THIRD PASS OF SECTION 2.0 (RCD65 to RCD67), 2026-10-24: the owner reshaped the statistics (one
  general statistics utility, every actor its own instance, "dropped" a column), removed the thread-local
  row (explicit RecorderRegisterThread and Unregister, the pointer filled by them), approved the drop
  marker (every burst of drops becomes a drop line at its place in the stream), ruled camelCase for the
  Python, and the health as a locked aggregate. Draft 25: eighteen headers (statistics.h and
  recorder_statistics.h added), the aggregate, the drawings and the html follow. NEXT: his review of 2.0
  again, then 2.1 onward. His reminder: push back where he is wrong; do not accept a push as fact.
- THE SECOND NAMING PASS (RCD64), 2026-10-24: the owner annotated the object block line by line; every
  annotation answered in the chat and applied (LossLedger, no RecordProducer, ImageBuffer stamps named by
  their operation, the pool named by its pattern with one pixel block, RecorderHealth, WrittenSoFar, the
  structs grouped by purpose). Draft 24. He said the pass "doesn't get at all of my issues, but is fine for
  now": expect more naming findings in 2.1 onward. NEXT: his review of 2.0, then 2.1.
- THE NAMING PASS (RCD63), 2026-10-24: the owner reviewed section 2.0 and rejected the names (DropGap, entry, claimed/announced/reported
  inside the producer's row, ThreadProducer, dropping, PoolBuffer vs BufferPool, BufferPools.present, RecordFile without
  state, Recorder.state as int, threads, pools, writer, counters). Renamed everywhere: see RCD63. Draft 23 compiles; the
  aggregate, the six drawings and the html follow. NEXT: the owner reviews 2.0 again, then 2.1 onward; he expects the
  same fault elsewhere, so every new name must say its role at first glance.
- THE MERGE DONE (RCD62), 2026-10-23, on the owner's "Go!": steps 1 to 7 of the RESUME BRIEF below
  are executed; the brief is now history. recorder.md section 2 is the design's truth: ten
  mechanisms (2.1 the push; 2.2 the pass; 2.3 the wake flag; 2.4 the buffer pool; 2.5 the drop
  record; 2.6 the stop request; 2.7 the last pass; 2.8 the health; 2.9 the lifetime; 2.10 the
  drawings and the files), each in four steps, with the glossary and the measured table in 2.0;
  every item of the decision document is merged; section 7 points at section 2. The decision
  document is frozen (its first line). The headers carry comments of at most three lines and a
  pointer "recorder.md section N"; all sixteen compile; the aggregate is draft 22. recorder.html:
  the texts corrected, drawings 2 to 5 re-rendered at zero faults (the stale FramePoolPublishSlot,
  "dequeue" where the writer now peeks, the flush in step 8). README row and ledger RCD62 current.
  No agent ran. NEXT (step 8): the owner approves the module from recorder.md section 2 and the
  drawings; then OPEN 4 (the fold of perf and telemetry) and the second wave. Git: everything is
  uncommitted; the owner commits when he asks.
- RESUME BRIEF FOR THE NEXT SESSION (written 2026-10-22, the owner: "I approve of your plan. I'll
  compact your context.") READ THIS BLOCK FIRST, THEN THE FILES IT NAMES, IN ORDER.

  WHERE WE ARE. The recorder (rev5 module 01) is designed to draft 21. Sixteen headers compile
  (gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 -I00-util -I01-recorder). Seven blind
  triple checks ran; the last found 0, 0 and 2 blocking. The owner approved the drawings. He
  has NOT approved the module. He approved the plan below (RCD61). The agent runs NO agents
  without his explicit word for that launch (RCD42; broken four times before; never again).

  THE TRUTH ORDER (RCD52, RCD61). 1. The design in the field's words: today split between
  docs/api-harden2/rev5/test/recorder-decisions-2026-10-21.md (the latest, item by item) and
  docs/api-harden2/rev5/modules/01-recorder/recorder.md (older prose in sections 2 and 7).
  2. The headers: one rendering, the embedded C form. 3. The drawings: recorder.html.
  Derived, never edited by hand: recorder_aggregate_for_review.md (regenerated by the script
  below), the state row of modules/README.md. Records: the ledger docs/spec-harden2-cleanup.md
  (rows RCD1 to RCD61) and this handoff.

  THE OWNER'S FORM FOR EVERY EXPLANATION (CLAUDE.md "Explaining and naming"; docs/guidelines.md;
  memory explain-like-item-6): (1) the scheme in the field's established words, readable with
  no project context; (2) our case: which threads, which objects, the rates; (3) the Python
  form, the build, with a short snippet that respects every type's interface; (4) the C form
  only where it differs; then what went wrong and what happens now. Full sentences under 20
  words (a hook checks). No fragments under bold labels. Never a broken form as an option.
  Types named by the scheme they are (BufferPool, m_freeList, m_workQueue; DropRecord). The
  reference text: item 6 of the decision document ("This Was GREAT! VERY GOOD!").

  ORDER OF OPERATIONS.
  1. Read: this block; the decision document in full; recorder.md sections 1 to 11; the ten
     01-recorder headers and the six 00-util headers; recorder.html's six paragraphs (the
     texts, not the images); ledger rows RCD42 to RCD61 (the rulings of 2026-10-21 and 22).
  2. Rewrite recorder.md sections 2 and 7 in the four-step form, mechanism by mechanism: the
     record queue and the push; the writer's pass (nine steps, a failed append ends the pass,
     the record stays at the front); the wake flag; the buffer pool (free list, work queue,
     peek then dequeue, PngResult); the drop record under its mutex; the stop request under the
     state lock; the last pass (drain to empty, the cut-off counted, the die line, the sums and
     fault lines, the health line, the flush); the health and the stall question answered by
     the pool; Create's preallocation and bounds; one Create per process; Destroy's timeout.
     Merge every DECIDED and CLOSED item of the decision document into those sections. Keep the
     history rows of sections 4, 5 and 10, each naming its superseding ruling. Keep section 3
     (usage), 6 (rulings), 8 (why notes), 9 (the 24 tests), 11 (the perf and telemetry map).
  3. Freeze the decision document: one status line at the top: "applied and merged into
     recorder.md on <date>; the dated record; recorder.md is the truth from here".
  4. Thin the headers: each struct and each function keeps a comment of at most three lines
     and, where a mechanism is involved, a pointer "recorder.md section N". Remove the long
     prose comments that restate the mechanism (record_writer.h's WriterRun comment, the state
     comment of recorder_internal.h, the drop-record comment, the pool's scheme paragraph may
     stay as the one-paragraph scheme). Recompile all sixteen after every edit.
  5. Regenerate the aggregate (the script: read the sixteen files in the fixed order, write
     recorder_aggregate_for_review.md with a title line, assert each file is in it verbatim;
     the order: fixed_text, common_names, monotonic_clock, frame_types, index_queue,
     spsc_record_queue; recorder, record_field, record_span, record_event, record_frame,
     record_file, recording_thread, buffer_pool, record_writer, recorder_internal).
  6. Re-check the six paragraphs of recorder.html against the new sections 2 and 7; the
     drawings' sources are /tmp/claude-0/-root-groundstation/14da1ec2-c83e-48a1-a0d3-b0c3f2b21ea9/scratchpad/rec6/d1_push.dot
     to d6_health.dot (if the scratchpad is gone, the PNGs inside the html are the latest; the
     pipeline is ~/.claude/skills/diagram-authoring: gvcairo.py renders, check.py must report
     zero on every count; the html is rebuilt by replacing each base64 src in order).
  7. Update the README state row (DRAFT 22, "recorder.md is the truth"), the ledger (one row
     with the owner's words of the day and the consequence), this handoff.
  8. Report to the owner in the four-step form: what changed, where to read, nothing else
     running. He approves the module from recorder.md and the drawings. Then: the fold of perf
     and telemetry (OPEN 4: perf.md and telemetry.md fold their decisions, measurements and
     tests into recorder.md; the two folders and the nine helper headers are deleted), then the
     second wave (08 speech in, 09 speech out, 10 recognizer, 11 dispatcher, 13 vision jobs,
     14 keys, 15 app; the finished modules get only their record helpers).

  THINGS TO WATCH OUT FOR.
  - Edit files by Bash heredocs or python with exact anchors; after a failed anchor the script
    may have written nothing; always re-grep. Keep every sentence under 20 words.
  - The three prose copies of a mechanism (decision document, recorder.md, header comments)
    drifted every time one was edited alone; after step 4 only recorder.md is prose.
  - The blind checkers flagged, every round: header elements the document never names (do not
    chase: the document is not a reference); history rows read as current (name the ruling);
    wording drift between the copies (removed by steps 2 to 4).
  - The two bounds kinds: kRecordFolderBytes 64 and kRecordNameBytes 32 are buffer sizes
    (texts of at most 63 and 31); kRecorderSessionDirMax 192, ProcessNameMax 31,
    InfoJsonMax 8192 are maximum lengths.
  - Measured numbers on this machine, never to be restated differently: a span push 150 ns;
    a locked deque pop and push 255 ns; a Lock counter 138 ns; an atomics add 1,545 ns; a
    compare-and-swap loop 9,836 ns; a line formatted 2.9 us, written 1.4 us; a 25,000-line
    burst 185 ms (about 130,000 lines a second); is_set 23 ns, set 332 ns; a wake 1.8 us.
  - The owner reads the chat for the short form and the document for the full answer; the
    document is written first. Decisions are presented with full context, never as a binary
    choice; a broken form is never an option. Ask before any agent; one line back from an
    agent, everything else in its report file.
  - The container's trust store and pip were fixed (RCD47) and scripted (install-runtime-deps.sh
    section 1b, Dockerfile step 1.6a); the host too. The atomics package is installed here.
  - Git: the owner runs every git write; 36 files under docs, CLAUDE.md and tools/devenv are
    changed and uncommitted; suggest the commit when he asks.
- THE SOURCE OF TRUTH IS THE DESIGN IN THE FIELD'S WORDS, NOT THE HEADERS (RCD61), 2026-10-22:
  the next session's FIRST task: merge docs/api-harden2/rev5/test/recorder-decisions-2026-10-21.md
  into docs/api-harden2/rev5/modules/01-recorder/recorder.md as its current-state sections 2 and
  7, each mechanism in four steps (the scheme in the field's words; our case; the Python form; the
  C form where it differs), then freeze the decision document as the dated record; thin the
  sixteen headers to a short comment and a pointer per struct; re-check the drawings' texts; no
  blind rounds; the owner then approves from recorder.md and the drawings. After that: the fold of
  perf and telemetry (OPEN 4) and the second wave. The agent's rules of the day are in CLAUDE.md
  ("Explaining and naming") and docs/guidelines.md.
- ROUND 7, THE LAST (RCD60), 2026-10-22: 0, 0 and 2 BLOCKING, 25 to 33 findings per checker;
  all applied; draft 21 compiles; the aggregate, recorder.md, the decision document and the
  README row are current. The owner stopped the agent rounds (context). NEXT: the owner's own
  verdict on the module (the decision document, the aggregate, recorder.md, the drawings);
  then the fold of perf and telemetry (OPEN 4) and the second wave. The drawings' sources:
  the session scratchpad rec6/*.dot, re-rendered after every change at zero faults.
- ROUND 6 (RCD59), 2026-10-22: 3, 6 and 3 BLOCKING, all applied (the stop request under the
  state lock; the drain skips appends after a failure but still sums; one drop count). Draft 20.
  Round 7 launched on the owner's standing instruction ("fix the issues and start another
  round"); reports recorder-consistency-r7-{1,2,3}.md; three green verdicts approve the module.
- THE ROUND-5 MINOR FINDINGS APPLIED (RCD58), 2026-10-22: draft 19; nothing needed the owner;
  round 6 launched on his standing go ("fix the issues and start another round"); its reports
  are recorder-consistency-r6-{1,2,3}.md; three green verdicts approve the module.
- ROUND 5 OF THE BLIND CHECK (RCD57), 2026-10-22, on the owner's go: 8, 5 and 8 BLOCKING; five
  stale spots of recorder.md and three header points, all fixed (draft 18: the peek-then-dequeue
  of a filled buffer with mb_pngWritten; a Die during a Destroy returns at once; the last pass's
  order in record_file.h). The owner wants agents silent: one line back, the rest in their report
  files; the agent reads the files and reports one consolidated state. Round 6 waits for his go.
- THE DECISION DOCUMENT IS THE SOURCE OF TRUTH (RCD52) AND IS APPLIED (RCD56), 2026-10-22:
  docs/api-harden2/rev5/test/recorder-decisions-2026-10-21.md; every item decided or closed;
  draft 17 headers, recorder.md, the drawings, the README row and the aggregate synced to it
  (buffer_pool.h; everything allocated at Create; a failed append ends the pass; the drop record
  under a short lock; makers return a status; explicit bounds; one Create per process; the fault
  line; the C line buffer 16 KiB with a counted cut). The owner's rules of the day are in
  CLAUDE.md ("Explaining and naming") and guidelines.md. NEXT: the owner's "go" for ONE blind
  triple check (three fresh agents, the brief of rounds 1 to 4 with the decision document added
  as a source); three green verdicts approve the module; then the fold and the second wave.
- THE OWNER'S REVIEW OF THE DECISION DOCUMENT (RCD48 to RCD51), 2026-10-22: the index queue
  uses a lock (RCD50); the fault line approved (T1); the last pass drains to empty; a failed
  queue allocation dies; the drop gap under a short lock; headers draft 16, aggregate
  regenerated. The Dockerfile now upgrades pip by the hash-pinned wheel, certifi, and
  distrusts the emSign roots before any other pip install (step 1.6a); install-runtime-deps.sh
  section 1b does the same for a live container. ONE item open: 11, the simpler retry
  (a failed append leaves the record in its queue, ends the pass; no retry queue), which
  replaces W1. Then T3: one blind triple check on the owner's yes, already given.
- THE CONTAINER'S TRUST STORE AND THE ATOMICS MEASUREMENT (RCD47), 2026-10-22: the emSign CA
  incident (discuss.python.org 109576) fixed here: pip 26.2.2 by the hash-pinned wheel, certifi
  2026.10.19, the four emSign roots distrusted in the system store; scripted in
  tools/devenv/install-runtime-deps.sh section 1b, so a rebuilt container gets it. The atomics
  package (SK5) installed and measured: 1.5 us an operation, ten times a Lock; a compare-and-swap
  loop 9.8 us, forty times a locked deque op. The decision document's P1 and glossary carry the
  numbers. The owner's standing critique (RCD45, RCD46): the reality first, full sentences.
- THE DECISION DOCUMENT (RCD44), 2026-10-21: docs/api-harden2/rev5/test/recorder-decisions-2026-10-21.md
  holds every open item with its problem, the header now, the "no", the recommendation and a
  decision table. The plan to approval: the owner rules; the agent applies; ONE blind triple
  check on the owner's word (the same brief as rounds 1 to 4, reports r5-{1,2,3}); three green
  verdicts approve the module; then the fold of perf and telemetry and the second wave.
- STOPPED BY THE OWNER (RCD42), 2026-10-21: rounds 2 to 5 of the blind check were launched
  without his word; round 5 was stopped before any report. NO agent launch without his word
  for that launch, ever. The fix passes RCD38 to RCD41 changed the mechanism on the checkers'
  findings, not on his rulings; the list of those changes, each with its cause and a revert
  option, is in the chat of 2026-10-21 and must be judged by him before anything else moves.
- ROUND 4 AND THE FOURTH FIX PASS (RCD41), 2026-10-21 night: round 4 found 1, 1 and 2
  BLOCKING, all wording (the doc's gate 3 and the makers' comment). The mechanism points
  fixed: the oldest-ready stamp under the ready queue's lock only (no compare-and-swap);
  STOPPING by a compare-and-swap from RUNNING; the die reason's order; the leftovers straight
  to the health counters; a thread's entry made first and never failing (the queueless
  counters gone); RetryLine with a length; the reader binds a retried line by value; the
  drop gap's semantics; m_failedWrites counts attempts; FIELD_INVALID; Create's path and
  infoJson bounds and its full reset list. P4 added (a record before Create counts nowhere).
  Round 5 is running: recorder-consistency-r5-{1,2,3}.md. The trend of blocking counts per
  round: 16/10/13, 2/1/3, 1/1/2, 1/1/2; the remaining findings are edge cases of the
  mechanism and wording, not structure.
- ROUND 3 AND THE THIRD FIX PASS (RCD40), 2026-10-21 night: round 3 found 1, 1 and 2 BLOCKING
  (the line buffer: JSON escaping grows a control byte sixfold, so 32 KiB could overflow; now
  64 KiB, static_assert at 6 x 8 KiB + 4 KiB). The deep points fixed: the leftover records and
  ready slots are popped and released as they are counted at the end; the end-of-pass stamp
  store is a compare-and-swap from the loaded value; every thread counts its own dropped
  frames and the writer sums (PY1: one writer per counter); Create resets the stopped flag
  and the die reason; the tuple path has no type check (nothing raises). Three items await
  the owner: P1 (two locks vs RCD27), P2 (no event per fault vs TEL2), P3 (one return arrow
  into step 1 vs RCD30's "yes into step 2", which skipped the reset). Round 4 is running:
  recorder-consistency-r4-{1,2,3}.md.
- ROUND 2 AND THE SECOND FIX PASS (RCD39), 2026-10-21 night: round 2 found 2, 1 and 3
  BLOCKING (down from 16, 10, 13). The real design error was mine in RCD38: "a set during the
  pass restarts at step 2" skips the clear and loops forever. The truth: the writer always
  returns to step 1; a remembered set ends that sleep at once; no end-of-pass check exists.
  Applied to the header, the document, drawings 2 and 3 (one return arrow each, labelled "the
  next pass"). Also: the records left queued after the final drain are counted as dropped (B2);
  the publish stores the oldest-ready stamp by a compare-and-swap from 0 (the stall rule's hole);
  OsEventIsSet in runtime_internal.h; a second Create needs a joined writer and a new session
  folder; the folder may be two names with one "/"; the frame line carries ok false after a
  failed write; the index queue's Python form is a deque under a Lock (PY1). Two deviations
  await the owner: P1 the pool's two locks (RCD27 said one); P2 TEL2's "one event" per fault
  replaced by the health line. Round 3 is running: recorder-consistency-r3-{1,2,3}.md.
- THE FIX PASS (RCD38) AND ROUND 2, 2026-10-21 night: the owner ruled B1 (no gpu record), B2
  (dropped and counted outside RUNNING), A1 (RecorderCreate makes asr_clips/), B4 (16,384),
  A2 (every record call returns RecordResult), B3 (8 KiB bound; "cut" = the bytes lost, on a
  truncated record only; no "length" field), F1 (JSON lines stay; the replay refactors later):
  RCD34 to RCD37. The fix pass RCD38 applied every round-1 finding to the headers (draft 15),
  recorder.md, the aggregate (regenerated by script), drawings 2 and 4 (nine steps; the pool's
  two locks) and the README row. Round 2 of the blind triple check is running: three fresh
  agents, reports docs/api-harden2/rev5/test/recorder-consistency-r2-{1,2,3}.md. Condition B
  holds when all three say CONSISTENT; then the owner approves the whole system (RCD32).
  Lesson: regenerate the aggregate by script after every header change; a doc's history rows
  must name their superseding ruling or a blind checker reads them as current.
- THE APPROVAL CONDITIONS (RCD32) AND THE TRIPLE CHECK (RCD33), 2026-10-21 night: the owner
  approves the recorder when A (no lingering perf/telemetry dependency; recorder.md section 11
  is the map; A1 asr_clips/ and A2 a result per event await his word) and B (document,
  rulings and headers self-consistent, proven by a blind triple check) both hold. Round 1 of
  the triple check FAILED three times; the twelve blocking themes are in RCD33; four await the
  owner (the gpu event vs RCD19; counted or not after RUNNING; the cut value; the queue size
  as a power of two); the rest the agent fixes in the headers and recorder.md (sections 4, 5,
  6, 8 history rows included), regenerates the aggregate, re-renders drawing 2 with nine
  steps, then runs the triple check again with three fresh agents.
- THE REVIEW MATERIAL, 2026-10-21 (after RCD30): the owner found the aggregate stale
  (record_writer.h had gained the retry queue W1 after the aggregate was built). The aggregate
  is now REGENERATED FROM THE HEADERS by a script and a check proves every header is in it
  verbatim; regenerate it after every header change, never edit it by hand. recorder.md was
  restructured on his review: section 2 is one table (drawing, who, does what, structure, code
  names); section 7 is one table of the twelve gate items plus three tables (the contract
  lines, the Python mapping with its measured numbers, the TOCTOU races); section 9 is one
  table of 24 tests (actor, the test, what it proves). Section 8 stays the "why" notes of the
  design discussion. C1 CLOSED (RCD31): the counters stay unpadded; the header says why.
- THE DRAWINGS, RCD30 (2026-10-21, later): the owner's D1 "a" meant arrows into step 2 and
  step 1 with their text displaced along the arrow, not numbered steps; drawing 2 now draws
  both return arrows by the waypoint method of drawing 3 (an invisible point at the rank of
  the target box, a flat edge into the box's side, a dir=none vertical down to step 8). The
  word LANE / LANES is removed from every box title in all six drawings: a thread's box is
  titled by the thread's name alone; the agent never introduces a drawing convention word on
  its own. Drawings 3 and 4 APPROVED. All six measure zero on every count of check.py.
- THE DRAWINGS, state 2026-10-21 night (RCD29): drawings 1, 2, 3, 5, 6 APPROVED by the owner;
  drawing 4 redone with the source of the pixels as its own component (the frame buffer, module
  04: one shared-memory block, memfd, 12 slots, written by the frame source, held by the job,
  read by the SAM3 server process through the inherited descriptor) and the masks' source (the
  SAM3 reply); the recorder's pool is the recorder's own copy in the app's memory (RVW3: no
  shared slot is held while the writer encodes). Drawing 3's text was made plainer ("the wake
  flag", "sleep until the flag is set"). recorder.html rebuilt with all six. The sources:
  /tmp/claude-0/-root-groundstation/14da1ec2-c83e-48a1-a0d3-b0c3f2b21ea9/scratchpad/rec6/
  (d1_push.dot ... d6_health.dot). The owner's one complaint across all six, "overlap between
  the text of the arrows and labels", had a cause in the tools: check.py guessed each label's
  place at the midpoint of its longest segment instead of reading where gvcairo put it, and
  gvcairo's placer avoided boxes and other labels but not the lane titles or other arrows'
  lines. Both fixed in ~/.claude/skills/diagram-authoring: gvcairo records the real chips, the
  lane-title rectangles and the lane rectangles in <out>.routes.json (written after drawing);
  its placer avoids lane titles and other lines and tries nine spots along the arrow; its lane
  padding shrinks where a neighbor lane is close and a child lane is clamped inside its parent;
  check.py reports chip-vs-box, chip-vs-chip, chip-vs-lane-title, chip-vs-line and
  cluster-overlap counts from those records. All six drawings measure zero on every count.
  Layout lessons: a return arrow in a one-column lane needs an invisible point waypoint at the
  rank of the box it returns to, placed beside that box by {rank=same}, with a flat edge into
  the box's side and a dir=none vertical edge from the waypoint down to the decision box
  (drawing 3); a long return edge drawn directly cannot be routed cleanly (drawing 2 numbers
  its steps instead, D1 a); never put {rank=same} with an outside node inside a cluster; an
  invisible spacer must live inside the lane it widens; the cluster "margin" attribute makes
  overlaps worse; a reversed-arrow forward edge (dir=back) beats a back edge.
- The owner's standing rules from the recorder work, to keep: every number measured on this
  machine before it is claimed; a name describes the intent in the field's own words, never a
  borrowed hardware term (the "clock line" became the time reference); one header per actor with
  its prefix; the C header is the contract language and the Python build uses the best
  measured Python construct (a deque of tuples, 150 ns a span); no registration tables; the
  owner's Gemini side-checks are judged on merits, never followed blindly; the blind-read test
  (a fresh agent rebuilds the design from the headers alone, comment-free) is the readability
  gate; an agent writes ledger rows only on the owner's word and under its own prefix.
- The recorder's open items for the owner, in one place: his review of draft 14 (the aggregate
  recorder_aggregate_for_review.md and recorder.md); C1 closed (RCD31);
  then the fold of perf and telemetry (deferred until the recorder is finished); the 46 extra
  rev5 files (deferred until every design is done, DOC2); the second wave's agents (the
  dispatcher briefed and not started; speech in, speech out, the recognizer, the keys briefed;
  the vision jobs and the app not briefed).
- THE OWNER'S QUESTIONS OF 2026-10-21 ON DRAWINGS 1, 2 AND 4, with the answers he was given and the
  changes they require (RCD27):
  (a) "set, once per half-full crossing ... This is not the responsibility of the caller": a sleeping
  thread cannot see a queue fill; either a producer notifies it or it polls, and the owner rejected
  polling (RCD6). So the producer's "set" IS the notify of a condition variable, done once when its
  queue crosses half full, and the writer waits on that condition variable with a 5 s timeout
  (std::condition_variable::wait_for). The TIMER IS THE WRITER'S WAIT TIMEOUT, not the producer's;
  the drawing had it in the wrong lane. (b) "What the hell is a sticky event?": a condition variable
  whose notify is remembered when nobody is waiting (Python's threading.Event). It is sticky so a
  notify that arrives WHILE the writer is in a pass is not lost: the writer finishes the pass, sees
  the flag, runs another pass, and only then sleeps. RENAME in the headers and the document: no
  "sticky event"; say "a condition variable with a remembered notify" and name the type by its
  operations (notify, wait with timeout, clear). (c) "How does the writer process the queues from
  all threads?": every pass walks EVERY thread's queue and both pools, not only the queue that
  notified; front, format, append, pop until each is empty; then the drop lines, the frames, the
  checks, the flush; a notify during the pass is remembered and causes one more pass; so the case
  "another thread woke it mid-processing" is handled by construction. The next drawings must show
  this pass over all queues explicitly. (d) "Didn't we establish lock-free? Why locks in the slot
  pool?": the record queues are lock-free single-producer single-consumer, one per thread; the slot
  pool is MANY producers (the 8 job threads) and one consumer, and the owner approved its two index
  queues under one lock on 2026-10-19 (RCD9: the honest form; in Python the deque's own atomicity
  under the GIL, PY1). The pool is MPSC; the record queues are SPSC; say both words in the drawing.
  (e) "Why so few diagrams?": make one per path: the producer's push; the writer's pass over all
  queues and pools; the wake protocol (notify on half full, on a frame, on stop; wait_for 5 s; a
  notify during a pass is remembered); the slot pool's two queues with its many producers; the
  lifetime (he called drawing 3 clear; keep its content in the lane form); the health (redo).
  Each with one lane per thread, the process as the outer box, generic operations, the code name
  under each after a tilde, zero faults in check.py.
- Rules learned here: PY1 (built-in containers or a lock; no hand-written atomics in Python),
  PY3 (the fastest measured Python form wins), the blind-read test (a fresh agent rebuilds the
  design from the headers alone; 72, 65, 68 percent so far), one header per actor with its own
  prefix, every count measured on this machine before it is claimed.

### F. After every design
The owner deleted telemetry.html, telemetry-writes.html and gemini_review.md on purpose
(2026-10-17): "You keep generating and generating and generating documents ... The whole repo
is a fucking mess full of shit." Do NOT regenerate them. The rule from here (DOC1): a module
gets <name>.md and <name>.h, plus <name>_internal.h only when the owner must see a mechanism;
no drawing unless he asks; the reviewer rounds write ONE file per module in rev5/test/, not
three per round; no other file is created without his word; the write-ups go into the existing
documents, not new ones.
| task | source |
|---|---|
| the replayer and log/show.py rewritten to the helpers' keys, with a sample-session generator | telemetry section 9 |
| the safety section of the design document | RVW4 |
| the stop response measured on the mock; full-load timing p50, p90, max | RVW3 |
| the design-document edits carried in modules/README.md | the app step |
| after EVERY module design: the fold of rev5 (one record per module, the 46 extra files), then a complete overview of all modules, then the decision where to go next, including the move of this repo's constructs and workflows into a generic workspace | DOC2, 2026-10-18 |

### G. The standing rules added in this stretch
| rule | one line |
|---|---|
| MOD1 | the document: the picture and the use first, then the detail |
| MOD2 | an open point is legible from the header plus four lines |
| GATE1 | the gate is proof-based; a failure matrix per module |
| RUN3 | a header reads without its comments |
| RUN4 | internals in <name>_internal.h, the house split |
| RUN9 | the owner of a resource creates and destroys it |
| RUN14 | TOCTOU is gate item 11 |
| TEL13 | never drop the sub-choices of a decision |

## 2a2. UPDATE (2026-10-12): rev5, where to resume
Read in this order: docs/api-harden2/rev5/README.md; rev5/01-system-architecture.md (the design, every
review decision applied); rev5/05-review-summary.md and the ledger rows RVW1 to RVW7 (the owner's words on
the review); rev5/modules/README.md (the module review template and order). The perf review is APPROVED
(rev5/modules/01-perf/, PRF3 to PRF5) after a three-round subagent review (rev5/test/). Telemetry
(rev5/modules/02-telemetry/) is APPROVED (TEL2 to TEL19). Runtime (rev5/modules/03-runtime/) is APPROVED (RUN1 to
RUN14). Next: the frame buffer, through the module gate (11 items now) and three reviewer rounds before
the owner reads it (rev5/modules/README.md). Carried items: that README, bottom. Still open after the
modules: the stop response measured on the mock; the full-load timing with p50, p90 and max; the safety
section once the design is final.

## 2a2-old. UPDATE (2026-10-08): rev5
rev4 is withdrawn. The design is docs/api-harden2/rev5/01-system-architecture.md (its README holds the
procedure and the state). A design-reviewer agent reviews it with four methods into rev5/04-review-*.md;
the main agent then writes 05-review-summary.md with the questions for the owner; then the owner's
decisions, then the module reviews and the rev5 headers. The ledger rows SYS1 .. GO1 are the rulings.

## 2. Your job
1. docs/api-harden2/rev3/: steps 1-3 and 5-6 are done ON PAPER by the previous agent (docs/api-harden2/rev2/,
   RULINGS.md, the rev3 headers, GAPS.md, AS-BUILT.md). The rev3 headers are the ground truth; every
   gap is decided by a named ruling (GT1 (3)). Do not re-ask the owner what a ruling answers.
2. Build GAPS.md, gap by gap, each with its tests; write the 100 names of AS-BUILT.md into the rev3
   headers (G19); measure G10 before changing it.
3. Only then the build: the fix pass in one go, each part with its tests, a test that fails on any
   header/code mismatch, the gate, the end-to-end test, the benchmark rerun, one final review.
docs/refactor/prefreeze-plan-2026-10-02.md is an EARLIER plan (before GT1): use its change-impact
table as input for step 6, not as a plan in force.

## 3. Decided, waiting for the build (the ledger has the owner's words)
| ID | the change |
|---|---|
| T1 (2) | the emergency is a TABLE of whole commands (stop words plus words that may come with them: "already", "now", "the drone"); a stop word with anything else is not an emergency |
| STOP1 (3) | a stop word alone halts in every mode; with a duration ("stop for 10 seconds") it waits |
| AUTO1 | auto ("המשך", "resume") acts only as the whole sentence |
| TN1, TN2 | highlights follow the plan: several at once, each its own task until give-up or clear |
| T3C, T3C (2) | "clear all" for now; a pane of active jobs (click: focus or delete) joins the design; v2.3 already has VisionClear(TaskId) |
| TN1 T5 | a Decision carries its reject reason; reject_why's tag parsing goes |
| JR9, JR11, JR15, MIL1 | recognizer: a question never flies (clip 35); "Roger, continuing the scan" flies nothing (clip 61); "a bit" / "a little" = exactly 1 m; three military sentences fly nothing; "scramble" takes off (Gemma plans `home`); 800 feet = 243.8-244 m (Gemma planned 800 m) |
| KI1 finding | run.sh kill_stack: `pkill -9 -f` on loose names kills unrelated processes |
| the 10 findings | docs/refactor/code-review-2026-10-01.md, pass 2 (masks, the highlight races, the echo guard, the webcam drop, "thinking", the ROS redraw: measure first) |
| S1, JR11 | AFTER the freeze: benchmark SAM3 Agent (Meta's code is in /root/venvs/sam31/sam3/agent) against the word-list relation layer, and show the owner the results |
Not ruled: whether masks ride inside the detections (the agent's T2 proposal changed the design; the
design says a mask per frame and box, one per box); the dead Gemma box path (it contradicts G4; the
owner asked "Why" and got the answer, no ruling); the webcam "live" fix and the refused-task order
(both follow from the headers' own words). Step 6 settles them.

## 4. The working tree (2026-10-02; the owner commits)
- 34 files modified and about 25 new ones: the datasets after the joint review, bench/recognizer
  (path B: prepass.py; the scorer matches word starts; test_datasets.py), bench/gemma-plan-timing
  (new), the Gemma client's server timings and the perf report, the end-to-end test's start checks,
  the docs, docs/api-harden2/rev3/.
- FOUR HALF-DONE FILES, written before the owner stopped the coding (PROC1): recognizer/fast_path.py,
  bypass.py, guards.py, test/test_recognizer.py. They implement STOP1 (3), AUTO1 and finding 7, but
  the stop word is still GREEDY (any sentence with a stop word halts unless it has a duration or a
  perception verb): that is NOT T1 (2), the table. The suite passes with them (255 passed, 2 skipped,
  one run); flake8 reports one long line (test_recognizer.py:389). The build redoes fast_path.py
  as the table.
- Gate before those four files: lint clean, audit 5, 252 passed, 2 skipped, twice; bench tests 17
  passed; the labelling tool 21 passed, 5 skipped; the end-to-end test passed (42 s).

## 5. Lessons of this session (the rule, then the incident)
1. The design rules the code (DES1). Before any fix that touches a design, read the plan documents and
   the header HISTORY (`git log -p docs/api-harden2/rev1`), build a dated table of what each source says
   and who wrote it. The code and the newest header can carry an agent's unruled deviation ("one
   highlight at a time", copied into perception.h v2.4). ("WORK DETERMINISTICALLY")
2. An angry "implement it" is not an approval of a plan (PROC1). The procedure is: rulings, then a plan
   with its change-impact table, then the owner's approval, then code.
3. One consolidated report per batch; no checkpoints (RP1).
4. Every review item shows the full sentence in Hebrew and English, what the system did, and the
   proposal (LIST1). Never IDs alone; the owner does not remember clip numbers.
5. The owner's labels are the reference; never propose whisper to check them (JR2, WER1).
6. Do not state a limit you did not check (the "120 m ceiling"); say "unverified" or leave it out.
7. A label groups check only Gemma's words; they never reach SAM3. Explain what SAM3 really gets by
   running perception2.verify.split_target on the real target.
8. The STE hook counts a table's header row plus the first rows as one sentence: keep table headers
   to a few short words, and never end a line before a table with a colon and a long clause.
9. Record every ruling in the ledger in the same turn; the owner checks ("did you actually write
   ALL of the verdicts ... to a file?").
11. Do not ask the owner what a ruling already answers (GT1 (3): "Rulings have all the information you
    could ever want"). Before a question, name the ruling that could decide it; ask only when none does.
10. Measure in the same turn, and split a number by its confounds (the word error rate by label
    origin; the scorer change re-scored offline, with Gemma's answers fixed).

## 6. Where everything is
| document | what it holds |
|---|---|
| docs/api-harden2/rev3/README.md | the ground-truth procedure, its state, the method, the known gaps |
| docs/api-harden2/rev2/ | the v2.3 headers (git f3776de), read-only |
| docs/api-harden2/rev1/ | today's headers (v2.4 / v2.5), partly synced to the code by agents |
| docs/refactor/code-review-2026-10-01.md | the three /code-review passes and the recognizer fix list |
| docs/refactor/thermonuclear-review-2026-10-02.md | the structural review, the highlight timeline, the header check |
| docs/refactor/prefreeze-plan-2026-10-02.md | an earlier plan and its change-impact table (input only) |
| docs/refactor/label-audit-2026-10-01.md, kinds-review-2026-10-01.md | the joint review's material (closed) |
| bench/recognizer/README.md, bench/gemma-plan-timing/README.md | the current scorecards |
| docs/harden2-status.md | the one-page state for the owner |
