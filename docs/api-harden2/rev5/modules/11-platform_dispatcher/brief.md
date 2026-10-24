# Brief: the platform dispatcher design agent (harden2 rev5, module 11)

The owner asked for this brief on 2026-10-18 ("I want the other subagents that I'd like to run
to do their own thing, along with their respective review agents"). It is the agent's handoff
document: the brief on top, the progress log at the bottom. The agent updates the log at every
checkpoint. The manager agent reads the log and every file this agent writes.


> **UPDATE 2026-10-18 (RCD1, RCD2): perf and telemetry are folded into ONE module, the recorder.**
> Read `01-recorder/recorder.md`, `recorder.h`, `record_span.h`, `record_event.h`, `record_frame.h`,
> `record_file.h`, `frame_types.h`, `recorder_internal.h` and `recorder.html` FIRST among the finished modules. Wherever this brief says perf.h, PerfTimestamp, PerfNow, PERF_<x>,
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

Design the platform dispatcher module of harden2 and deliver two files the owner can review in 15
minutes: `platform_dispatcher.md` and `platform_dispatcher.h` in this folder. The job in one sentence is in
section 3. You design from the owner's words and the architecture document. You do not transcribe
today's code into C. You do not copy the rev4 sketch; it was rejected.

## 2. Read first, in this order

1. /root/groundstation/CLAUDE.md and /root/groundstation/docs/guidelines.md (the house rules; the drone safety rules first).
2. /root/groundstation/docs/api-harden2/rev5/modules/README.md: the document order (MOD1), the open-point form (MOD2), the twelve-point
   gate (item 12 is new), the house split, the state table, the carried items.
3. /root/groundstation/docs/api-harden2/rev5/01-system-architecture.md: section 3 (the platform worker thread, the emergency thread), section 4 (the command queue, the priority queue with the emergency first; 409 in manual; a mission refused while the phone's row is WAITING; no time-to-live; the PlatformReply message), section 9, section 10.
4. /root/groundstation/docs/task-active-harden2-handoff-2026-10-02.md, section 2a3: part C (the procedure),
   part D (what each review taught), part E item 11 (this module), and item 7 (the phone client, finished), part F.
5. The finished modules, as the reference for the shape and the depth, and as your contracts:
   - 07-phone_client/phone_client.md, phone_client.h, phone_client_internal.h: your one service; PhoneSend(route, body, deadline) on the caller's thread with a new connection per request; the emergency thread sends the stop on its own; Die's hand-over is the client's function: the halt (a /c/fly with one 0 s delay) if any motion request left this run, then /c/stop, then /c/stop again (PHN6); read OPEN 1 of phone_client.md section 4 for facts 1 to 6 about the phone app, they bind YOUR manual switch
   - 01-recorder (read it first, as the UPDATE above says): the spans and events you own, with their
     typed fields; MonotonicNow for every timestamp
   - 01-recorder, record_frame.h: RecorderCreate takes the frame size, so the size probe runs BEFORE
     the recorder and the buffer exist (the start order, carried in modules/README.md)
   - 03-runtime/runtime.md: Die runs the hand-over on its own thread, never through your worker
6. The ledger rows that bind this module, in /root/groundstation/docs/spec-harden2-cleanup.md:
   NAM2, D2, PROC2, OWN1, PHN3, PHN4, PHN6, PHN7, PHN8, RVW4, SYS1, SK4, REV8, PRF7, MOD1, MOD2, GATE1, DOC1, PAR2. Quote the owner's words in the document's rulings section.
7. Today's code, to describe what is wrong with it, not to copy it:
   - /root/groundstation/projects/integration_harden2/control/flight.py (manual and auto, the transmit switch, 409)
   - /root/groundstation/projects/integration_harden2/control/ (the rest of the flight dispatch) and /root/groundstation/projects/integration_harden2/app/turns.py (the pieces that send)
   - /root/groundstation/projects/integration_harden2/config/ for every value
8. One finished review record, as the model for yours:
   /root/groundstation/docs/api-harden2/rev5/test/phone_client-review.md (its conclusions and the note on the
   owner's six reviews) and /root/groundstation/docs/api-harden2/rev5/test/runtime-round-1-reviewer.md.

## 3. The facts you start from (handoff part E, item 11, and the rulings)

- The owner's names are the contract (NAM2): PlatformCommandDispatcher, Create and Close, SetManualControlMode, IsManualControlMode, SendEmergencyStop, SendCmdList. No log inside (D2).
- Two threads send: the platform worker (missions, takeoff, land) from a priority queue with the emergency first; the emergency thread for the stop, with its own event and its own connection; the stop never waits behind a mission.
- Manual mode: a state the main thread owns, read by the worker as an atomic; a mission in manual is refused with 409 and a chat line; manual itself sends /c/stop (the aircraft stops, the RC flies).
- A mission is refused while the phone's row is WAITING; no time-to-live on a queued command (section 4).
- The HALT mission in auto: a /c/fly with one 0 s delay pre-empts the running mission (the phone app cancels the previous job only on a new /c/fly, fact 1 of OPEN 1).
- The phone app facts that bind the manual switch: /c/stop gives the sticks to the RC but does not cancel the running job; a later takeoff step takes the sticks back; the RC override is the app's own code past a deviation of 30 (PHN4).
- The stop's reply reaches the main thread as a PlatformReply message from the emergency thread (TEL7); the turn record is written at "ended" with it.
- The groundstation never cuts the motors (PHN2 D6).

## 4. What you must settle (each one lands in the document and the header)

1. The dispatcher struct and the six functions as code, with the owner's names; what Create takes (the client, the queue), what Close joins.
2. The priority queue: its bound, its order (emergency, then commands in arrival order), what a full queue does, and the proof that the main thread never waits on the phone.
3. The emergency path: the event, the thread, its own connection, the PlatformReply message, the measured stop response on the mock (the phone client measured p50 0.21 to 0.37 ms, max 1.07 ms with a mission open).
4. The manual switch: with facts 1 to 6, what SetManualControlMode(true) must send so the pilot really holds the sticks (a halt first, then the stop, like the hand-over), and what it costs; as an open point if the owner must choose.
5. The turn's record of the mission: which fields the dispatch helper gets from you, as code.
6. TOCTOU (gate item 11): manual flipped while a mission is in flight on the worker; a stop while the worker sends; the phone's row read then the send; name each window and what closes it.
7. The failure matrix with gate item 12: the phone WAITING (SEEN), a 409 (SEEN), a timeout mid-mission (SEEN), Die mid-send (DESIGNED); each row with its cause, and whether the aircraft is touched.

## 5. The rules of the deliverable

- Only `platform_dispatcher.md` and `platform_dispatcher.h` in this folder, plus `platform_dispatcher_internal.h` only if the owner must see a
  mechanism to judge the design (RUN4). No drawing. No other file (DOC1). The brief stays.
- `platform_dispatcher.md` follows the MOD1 order in modules/README.md: the job, the picture (one text
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
  and only under your prefix `DSP`. Never RUN, PRF, TEL, FB, LLM or PHN. A change you need in an
  approved module is an open point carried to the manager, never an edit of that module (PAR2).
- Mark every number you did not measure "unverified".

## 6. The procedure

1. Read everything in section 2. Write the full picture of the module in the system before
   any design: the threads, the processes, the queues, the rates, the sizes.
2. Design. Reason from the forces to one proposal per point in section 4. Where the owner must
   choose, write the four-line form. Where the design is clear, decide and state the reason.
3. Write `platform_dispatcher.md` and `platform_dispatcher.h`. Run the layout tool and gcc.
4. Run the twelve-point gate yourself. Each item gets the failure you tried and the mechanism
   that stops it, written in the document's gate section. Item 9 needs measurements (section
   7). Put the numbers and the commands in the document. Do not add scripts to the repo.
5. Three reviewer rounds with subagents, one at a time. Each round: spawn one subagent
   (general-purpose, model opus, maximum care, the web for sources). Give it the module's files,
   this brief's sections 3 and 4, gate item 12, and the three lenses of round 1 (storage and
   hardware; concurrency and real time; YAGNI and decoupling). It writes only its section into
   /root/groundstation/docs/api-harden2/rev5/test/platform_dispatcher-review.md under
   "## Round N: reviewer". You answer under "## Round N: answer": accepted with its cause and
   the change made, or rejected with the cause and the generic handling that covers it. Rounds
   2 and 3 first re-check the cause behind every mechanism added since round 1. End the file
   with "## Conclusions": agreed, open, changed, every item the review added with its cause, and
   the counts accepted, narrowed, rejected.
6. Update the document and the header after every round. Re-run the layout tool and gcc.
7. Write the progress log below at every checkpoint. The owner reviews in your session; write
   his words into the log verbatim. Return one line to the chat when done.

## 7. The machine and the measurements

- No GPU. Measure against the mock only: launch /root/groundstation/tools/dji_mock/mock_apiserver.py on 127.0.0.1:8079 yourself, take the port lock:
  `/root/groundstation/tools/lock.sh wait platform_dispatcher port-8079`, release with `/root/groundstation/tools/lock.sh release platform_dispatcher all`.
- Measure: the queue hand-off cost from the main thread to the worker; the stop's path from the event to the reply with a mission in flight. Never send a motion request to any host but 127.0.0.1.
- Other agents work at the same time on other modules. You do not edit their folders, the
  approved modules, the handoff, or modules/README.md. The manager records the owner's rulings
  there and carries your items to the approved modules.

## 8. Done when

- Both files exist, the header compiles, the layout tool ran clean, every gate item has its
  proof in the document, the review record holds three rounds and the conclusions, every open
  point is in the four-line form with an OPEN mark in the header, and the log below says so.

## Progress log (newest at the end)

