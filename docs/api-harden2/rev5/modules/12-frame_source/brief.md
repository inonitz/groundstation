# Brief: the frame source design agent (harden2 rev5, module 12)

The owner asked for this brief on 2026-10-18 ("I want the other subagents that I'd like to run
to do their own thing, along with their respective review agents"). It is the agent's handoff
document: the brief on top, the progress log at the bottom. The agent updates the log at every
checkpoint. The manager agent reads the log and every file this agent writes.


> **UPDATE 2026-10-18 (RCD1, RCD2): perf and telemetry are folded into ONE module, the recorder.**
> Read `01-recorder/recorder.md`, `recorder.h`, `record_span.h`, `record_event.h`, `record_frame.h`,
> `record_file.h`, `frame_types.h`, `recorder_internal.h` and `recorder.html` FIRST among the finished modules. Wherever this brief says perf.h, MonotonicNs, MonotonicNow, PERF_<x>,
> perf_record_<owner>.h, telemetry.h or telemetry_record_<owner>.h, read instead: recorder.h,
> MonotonicNs, MonotonicNow, SPAN_<x>, record_<owner>.h, RecordEvent and RecordFrame.
> The contracts: RecordSpan(stage, start, end, fields, count), RecordEvent(topic, at, fields, count) with typed fields
> (record_field.h: a key REGISTERED once at your module's start by RecordKeyRegister, a type, a
> value; NEVER a JSON string on the hot path); the file's keys and line kinds: record_file.h,
> RecordFrame(channel, name, at, const FrameView*). No sample contract: a gauge is an event. No handle:
> RecorderCreate once per process, no recorder argument anywhere. The parked rule "keep the
> tracer as the first parameter" is VOID. Your helpers live in `record_<owner>.h` inside your
> module and take no recorder argument; carry the keys of the former perf_record_<owner>.h and
> telemetry_record_<owner>.h into them. General structures with one home in `00-util/`:
> `spsc_record_queue.h` (a byte ring with one producer and one consumer, written in place by reserve
> and commit, typed endpoints), `index_queue.h` (a bounded queue of slot indexes under one
> lock, safe for any threads) and `fixed_text.h` (a named fixed-size text). A type's name and
> its endpoints must say its concurrency contract; a comment is not enough (RCD9). Use them instead of writing your own; a structure two modules need goes to
> util, carried to the manager, never a second copy. The frame types `FrameSize`, `PixelFormat` and `FrameView` live in `frame_types.h`, one home.

## 1. Your job

Design the frame source module of harden2 and deliver two files the owner can review in 15
minutes: `frame_source.md` and `frame_source.h` in this folder. The job in one sentence is in
section 3. You design from the owner's words and the architecture document. You do not transcribe
today's code into C. You do not copy the rev4 sketch; it was rejected.

## 2. Read first, in this order

1. /root/groundstation/CLAUDE.md and /root/groundstation/docs/guidelines.md (the house rules; the drone safety rules first).
2. /root/groundstation/docs/api-harden2/rev5/modules/README.md: the document order (MOD1), the open-point form (MOD2), the twelve-point
   gate (item 12 is new), the house split, the state table, the carried items.
3. /root/groundstation/docs/api-harden2/rev5/01-system-architecture.md: section 3 (the frame source thread writes a slot and publishes latest), section 6 (the frame buffer), section 8 (the ROS listener cost at 1080p), section 9 (a video stall: a planned restart after 6 s), section 10.
4. /root/groundstation/docs/task-active-harden2-handoff-2026-10-02.md, section 2a3: part C (the procedure),
   part D (what each review taught), part E item 12 (this module), and item 4 (the frame buffer, finished), part F.
5. The finished modules, as the reference for the shape and the depth, and as your contracts:
   - 04-framebuffer/framebuffer.md, framebuffer.h, framebuffer_internal.h: your one sink; you are its ONLY writer; the writer claims a slot by compare-and-swap (FB3), fills it, publishes the sequence as latest; 12 slots (FB5); the block is a nameless memfd the app creates (FB2); the owner edited the header himself (FB7): take every name from it
   - 03-runtime/runtime.md, runtime.h, runtime_internal.h: the supervisor owns the gstreamer receiver node; your pure spec function returns its ProcessSpec; the drone frames arrive through a RosSubscription on its own executor thread; the stall guard calls SupervisorRestartOnPurpose
   - 01-recorder (read it first, as the UPDATE above says): the spans and events you own, with their
     typed fields; MonotonicNow for every timestamp
   - 01-recorder, record_frame.h: RecorderCreate takes the frame size, so the size probe runs BEFORE
     the recorder and the buffer exist (the start order, carried in modules/README.md)
   - /root/groundstation/docs/api-harden2/rev5/modules/README.md carried items: the GIL1 row (the owner asked about a free-threaded Python for the 6 MB copy under the GIL)
6. The ledger rows that bind this module, in /root/groundstation/docs/spec-harden2-cleanup.md:
   FR1, FB2, FB3, FB5, FB7, GIL1, RVW5, Q3, RUN9, RUN14, RUN16, REV8, PRF7, MOD1, MOD2, GATE1, DOC1, PAR2. Quote the owner's words in the document's rulings section.
7. Today's code, to describe what is wrong with it, not to copy it:
   - /root/groundstation/projects/integration_harden2/video/video.py (the webcam, MJPG 720p 30 fps), ros_stream.py (the gstreamer spec and the ROS subscription), cam_list.py
   - /root/groundstation/projects/llm_to_action/ (the owner's gstreamer receiver node llm_to_action_gstreamer_rx: its arguments and its topic camera/stream)
   - /root/groundstation/projects/integration_harden2/config/ for every value
8. One finished review record, as the model for yours:
   /root/groundstation/docs/api-harden2/rev5/test/phone_client-review.md (its conclusions and the note on the
   owner's six reviews) and /root/groundstation/docs/api-harden2/rev5/test/runtime-round-1-reviewer.md.

## 3. The facts you start from (handoff part E, item 12, and the rulings)

- Three kinds, one per source: the webcam (OpenCV, MJPG 1280x720 today); the drone stream (the phone streams H.264 over TCP; the owner's native ROS 2 node receives it and publishes bgr8 images on camera/stream; a RosSubscription copies each into a slot); a video file. The two unused kinds of today's code are dropped (Q3 a).
- The frame size is fixed per run and probed before telemetry and the buffer exist: the webcam by opening it and reading one frame; the drone is 1920x1080, a given; a file is probed. A geometry change mid-run is a planned restart of the video path, never a new size.
- The stall guard: no frame for 6 s is a planned restart of the receiver through SupervisorRestartOnPurpose (section 9).
- The measured cost today: the ROS executor thread copies 6 MB per 1080p frame under the GIL, with a 17 ms worst stall on the main thread and 22 of 30 frames delivered. The design must move or bound that copy (GIL1 is the owner's question about a free-threaded Python).
- The writer's contract with the buffer: claim a free slot by compare-and-swap, copy the pixels in, stamp captured-at, publish the sequence; when no slot is free that is a bug, not a drop (FR1).

## 4. What you must settle (each one lands in the document and the header)

1. FrameSourceCreate and Destroy per kind, with one handle the app holds by value; the size probe as its own call that runs before Create of telemetry and the buffer; the start order written as code.
2. The webcam thread: the read into the claimed slot without a second copy (OpenCV writes into a destination array; whether the V4L2 backend avoids its own copy is unverified: measure it).
3. The drone frames: the thread that copies the 6 MB and the bound on its stall of the main thread; measure the copy at 1080p on this machine with and without the GIL held by a busy main thread.
4. The gstreamer receiver's pure spec function: argv from config, env additions, a publisher count on camera/stream as the probe, SIGINT, BUDGET_SPENT_WAIT_FOR_USER (a phone-side part), the log path.
5. The stall guard: the 6 s rule, who checks it (the main thread reads the row each frame), and the planned restart.
6. TOCTOU (gate item 11): a slot claimed then the read fails; Destroy while the thread holds a claim; the probe's size against the first frame's size; name each window and what closes it.
7. The failure matrix with gate item 12: the stream stalls (SEEN: the sessions), the webcam is unplugged (SEEN), a frame of the wrong size (DESIGNED: the probe), the receiver node dies (the supervisor); each row with its cause.

## 5. The rules of the deliverable

- Only `frame_source.md` and `frame_source.h` in this folder, plus `frame_source_internal.h` only if the owner must see a
  mechanism to judge the design (RUN4). No drawing. No other file (DOC1). The brief stays.
- `frame_source.md` follows the MOD1 order in modules/README.md: the job, the picture (one text
  diagram), the usage (two pseudocode instances in the Python of the build), the open points
  (MOD2, the four-line form: the problem, now, on "no", recommended), then today, the rulings,
  the gate answers with the failure matrix, the notes, the tests.
- The gate has TWELVE items now. Item 12, "Need" (REV8, 2026-10-18): every failure-matrix row
  and every accepted finding names its cause, SEEN, DESIGNED or FORCED. A forced failure, or a
  row with no cause, gets the generic handling only and no mechanism. Read item 12 in full
  before you write the failure matrix. The owner dropped a whole hang mechanism for breaking it.
- The header reads without its comments (RUN3). Create and Destroy; handles the app owns;
  `_Atomic` types for every shared value; m_ prefixes; no implementation comments. Anonymous
  `typedef enum {`; comment blocks above enums; no commas inside enum comments; 64-bit and
  float constants as macros (`UINT64_C`), never `static const`.
- Record helpers (RCD1, RCD11): your `record_<owner>.h` interns its keys and topics once at your
  module's start and offers one function per span or event that packs typed fields; no
  recorder argument, no JSON string, never on the hot path a text of your own making.
- The supervisor OWNS every process (RUN9). A module gives a pure spec function that returns a
  ProcessSpec; it never launches, stops or restarts its process. The environment in a spec
  lists only the additions (RUN16). Descriptors to pass go in m_passFds (RUN15).
- Lay the header out with `python3 /root/groundstation/tools/style/header_layout.py <file>`.
  The tool reflows comments and realigns spacing; edit with line ranges, not exact strings.
  Compile with `gcc -fsyntax-only -Wall -x c <file>` with the folders of the modules you include
  on the include path (-I.../modules/00-util -I.../modules/01-recorder and so on).
- Prose in STE: one idea per sentence, under 20 words. Standard field terms. Banned words:
  wire, seam, load-bearing, sieve. No em-dashes. No Hebrew inside an English sentence.
- No git write of any kind. No file outside this folder and your one record file.
- The ledger (docs/spec-harden2-cleanup.md): you write a row only when the owner tells you to,
  and only under your prefix `FSRC`. Never RUN, PRF, TEL, FB, LLM or PHN. A change you need in an
  approved module is an open point carried to the manager, never an edit of that module (PAR2).
- Mark every number you did not measure "unverified".

## 6. The procedure

1. Read everything in section 2. Write the full picture of the module in the system before
   any design: the threads, the processes, the queues, the rates, the sizes.
2. Design. Reason from the forces to one proposal per point in section 4. Where the owner must
   choose, write the four-line form. Where the design is clear, decide and state the reason.
3. Write `frame_source.md` and `frame_source.h`. Run the layout tool and gcc.
4. Run the twelve-point gate yourself. Each item gets the failure you tried and the mechanism
   that stops it, written in the document's gate section. Item 9 needs measurements (section
   7). Put the numbers and the commands in the document. Do not add scripts to the repo.
5. Three reviewer rounds with subagents, one at a time. Each round: spawn one subagent
   (general-purpose, model opus, maximum care, the web for sources). Give it the module's files,
   this brief's sections 3 and 4, gate item 12, and the three lenses of round 1 (storage and
   hardware; concurrency and real time; YAGNI and decoupling). It writes only its section into
   /root/groundstation/docs/api-harden2/rev5/test/frame_source-review.md under
   "## Round N: reviewer". You answer under "## Round N: answer": accepted with its cause and
   the change made, or rejected with the cause and the generic handling that covers it. Rounds
   2 and 3 first re-check the cause behind every mechanism added since round 1. End the file
   with "## Conclusions": agreed, open, changed, every item the review added with its cause, and
   the counts accepted, narrowed, rejected.
6. Update the document and the header after every round. Re-run the layout tool and gcc.
7. Write the progress log below at every checkpoint. The owner reviews in your session; write
   his words into the log verbatim. Return one line to the chat when done.

## 7. The machine and the measurements

- The webcam probe and the webcam read need the webcam lock:
  `/root/groundstation/tools/lock.sh wait frame_source webcam`, release with `/root/groundstation/tools/lock.sh release frame_source all`. The frame buffer agent took it before you; check the table.
- Measure, in your scratch folder: one slot copy at 720p and 1080p; the webcam read cost; the 1080p copy with a busy main thread (a tight Python loop) against the 330 us budget. The drone stream is measured only with the phone, so mark it unverified unless the mock's video server (tools/dji_mock/video_tcp_mock.py) serves it.
- Other agents work at the same time on other modules. You do not edit their folders, the
  approved modules, the handoff, or modules/README.md. The manager records the owner's rulings
  there and carries your items to the approved modules.

## 8. Done when

- Both files exist, the header compiles, the layout tool ran clean, every gate item has its
  proof in the document, the review record holds three rounds and the conclusions, every open
  point is in the four-line form with an OPEN mark in the header, and the log below says so.

## Progress log (newest at the end)


### Checkpoint 1 (2026-10-18): the reading and the measurements
- Read: CLAUDE.md, guidelines.md, modules/README.md (gate items 1 to 12), the architecture
  document sections 3, 6, 8, 9, 10, handoff 2a3 (C, D, E items 4 and 12, F), the recorder
  (recorder.md, recorder.h, recorder_internal.h), the frame buffer (all three files), runtime
  (both headers, runtime.md), the ledger rows of section 6, today's video/ code, the owner's
  receiver node (rx_node.cpp), config, the phone client review's conclusions, the runtime
  round-1 record. Q3 a: the options are in rev4/REVIEW-4-answers.md section 18; the owner's
  verbatim answer is not in the ledger (the handoff records "Q3 a").
- Measured (scratch folder fs/, commands in frame_source.md section 7b item 9):
  - the webcam (lock taken and released by tools/lock.sh run): cv2 read(dst) writes into the
    slot 120 of 120 at 720p and 1080p; OpenCV's V4L2 backend decodes into its own buffer and
    then copies (cap_v4l.cpp 4.11.0 line 2082); that copy runs without the GIL; a read plus
    our copy stalls the main thread up to +1 ms at 1080p; a wrong-size destination is left
    untouched and OpenCV returns its own array.
  - the drone path, the real receiver against tools/dji_mock/video_tcp_mock.py on loopback
    (no phone, no aircraft): rclpy's take holds the GIL 9 to 10 ms per 1080p frame (typed or
    raw, every Fast DDS transport); the main thread's p99 gap is 11 ms, its max 15 to 16 ms.
    A child bridge process removes it: the app's max gap 1549 us against a 1120 us baseline.
  - the receiver: no server at launch or after an end of stream: alive, never reconnects;
    SIGINT stops it in 124 ms; after a relaunch a live subscriber gets frames in 1 to 3 s.
- Next: the design, frame_source.md, frame_source.h, frame_source_internal.h.

### Checkpoint 2 (2026-10-18): the design written
- The owner's note for this agent, verbatim (2026-10-18): "The recorder is bound to change and
  its contract is still volatile. Please be wary of that when writing your definitions. Not
  only that, perf & telemetry are effectively redundant due to their replacement, recorder.
  That doesn't mean that the insights are invalid, though." Applied: the module uses
  FrameSize, MonotonicNs, MonotonicNow and one RecordEvent call site (RecordVideoRow).
- Written: frame_source.md (460 lines, the MOD1 order), frame_source.h, frame_source_internal.h.
  gcc -Wall -Wextra -std=c11 -Wpedantic clean on both; header_layout.py: no change; no line
  over 89 characters. The layout tool cannot parse an anonymous union: the handle holds two
  pointers instead.
- Decided with reasons (frame_source.md): the webcam and the file read into the claimed slot;
  the claim stays open across a failed read; the stall guard on the main thread once a
  second, by the latest sequence; only the receiver restarted; no span, one "video" event.
- Open for the owner: OPEN 1 the frame bridge process; OPEN 2 a frame buffer writer handle
  for another process (carried, PAR2); OPEN 3 runtime's graph query call (carried); OPEN 4 no
  reopen of a lost webcam (its SEEN not found).
- Next: reviewer round 1.

### Checkpoint 3 (2026-10-18): round 1 done
- The reviewer: 10 findings, 0 high, 4 medium, 6 low. All accepted; R1-2 and R1-4 narrowed;
  R1-9 in part (the device hand-over rejected). The record: test/frame_source-review.md.
- Re-measured R1-1 myself: the take 8866 us, 1864 us with the glibc tunables; in the app the
  main thread still 3.1 ms p99, so OPEN 1 stands.
- Added since round 1, for round 2 to re-check: the GLIBC_TUNABLES env addition of the
  bridge; the frame buffer health fix carried in OPEN 2; option (d) in OPEN 1.
- Next: reviewer round 2.

### Checkpoint 4 (2026-10-18): round 2 done
- The reviewer: 6 findings, 0 high, 2 medium, 4 low; all accepted. The three round-1
  mechanisms re-checked: each keeps its cause.
- The finding that matters for the owner: option (d) of OPEN 1, OpenCV reading the phone's
  TCP stream with one decoder thread, has 13 ms latency against the bridge path's 31 ms, at
  49 % against 78 % of one core. The recommendation stays the bridge because RVW5 stands and
  the owner's C++ fmu_node reads camera/stream; the document says (d) is the author's pick if
  the owner revisits RVW5.
- Added since round 1, for round 3 to re-check: the tunables (32 MiB threshold); the held-slot
  scan carried in OPEN 2, once a second.
- Next: reviewer round 3, the landing check.

### Checkpoint 5 (2026-10-18): round 3 done; the review closed
- The reviewer: 15 findings, all low; all applied, R3-13 narrowed (no log-rate field: no cause).
- The record ends with its conclusions: 31 findings, 27 accepted, 4 narrowed, 0 rejected.
- Final state: frame_source.md, frame_source.h, frame_source_internal.h. Both headers compile
  with -Wall -Wextra -std=c11 -Wpedantic; header_layout.py makes no change; no header line
  over 89 characters; no banned word; no em-dash.
- Open for the owner, each in the four-line form with its OPEN mark in the header: OPEN 1 the
  frame bridge (option (d), OpenCV on the phone's stream, is the author's pick if RVW5 is
  revisited); OPEN 2 a frame buffer writer handle (carried); OPEN 3 runtime's graph query
  call (carried); OPEN 4 no reopen of a lost webcam; OPEN 5 the frame buffer's held-slot scan
  (carried).
- No ledger row written (the owner has not ruled). No git write. No file outside this folder
  and test/frame_source-review.md. Scratch scripts: the session scratchpad, fs/ and review1/
  to review3/.
- Done. The owner reviews in this session.
