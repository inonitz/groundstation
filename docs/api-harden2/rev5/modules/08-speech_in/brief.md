# Brief: the speech in design agent (harden2 rev5, module 8)

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

Design the speech in module of harden2 and deliver two files the owner can review in 15
minutes: `speech_in.md` and `speech_in.h` in this folder. The job in one sentence is in
section 3. You design from the owner's words and the architecture document. You do not transcribe
today's code into C. You do not copy the rev4 sketch; it was rejected.

## 2. Read first, in this order

1. /root/groundstation/CLAUDE.md and /root/groundstation/docs/guidelines.md (the house rules; the drone safety rules first).
2. /root/groundstation/docs/api-harden2/rev5/modules/README.md: the document order (MOD1), the open-point form (MOD2), the twelve-point
   gate (item 12 is new), the house split, the state table, the carried items.
3. /root/groundstation/docs/api-harden2/rev5/01-system-architecture.md: section 2 (the ASR node; the phone's TCP line in), section 3 (the mic listener, the phone listener), section 4 (the Transcript message), section 9 (an "ok" line per transcript back; the socket keepalive), section 10.
4. /root/groundstation/docs/task-active-harden2-handoff-2026-10-02.md, section 2a3: part C (the procedure),
   part D (what each review taught), part E item 8 (this module), and item 7 (the phone client, finished), part F.
5. The finished modules, as the reference for the shape and the depth, and as your contracts:
   - 03-runtime/runtime.md, runtime.h, runtime_internal.h: the supervisor owns the ASR node; your pure spec function returns its ProcessSpec; the mic listener is a RosSubscription on its own executor thread (RosSubscriptionCreate, the callback stamps with PerfNow)
   - 07-phone_client/phone_client.md, phone_client.h, phone_mock.h: the client is blind to its server; speech in OWNS the phone's TCP line listener (PHN5 D3, the owner: "Speech In owns this module, ITS IN THE GOD DAMN NAME"); the mock's spec is there
   - 01-recorder, record_frame.h: RecorderCreate takes the frame size, so the size probe runs BEFORE
     the recorder and the buffer exist (the start order, carried in modules/README.md)
   - 01-recorder (read it first, as the UPDATE above says): the spans and events you own, with their
     typed fields; MonotonicNow for every timestamp
6. The ledger rows that bind this module, in /root/groundstation/docs/spec-harden2-cleanup.md:
   AUD3, RVW5, TEL8, PHN5, PHN7, RUN9, RUN14, RUN16, REV8, PRF7, MOD1, MOD2, GATE1, DOC1, PAR2. Quote the owner's words in the document's rulings section.
7. Today's code, to describe what is wrong with it, not to copy it:
   - /root/groundstation/projects/integration_harden2/audio/asr_ros.py (the ASR spec, the ROS subscription)
   - /root/groundstation/projects/integration_harden2/audio/asr_phone.py (asyncio today; a plain TCP thread in rev5)
   - /root/groundstation/projects/llm_to_action/source/asr/asr_node.cpp (the owner's C++ ASR node: its arguments, its topic, the clip log line he added on 2026-10-16)
   - /root/groundstation/projects/integration_harden2/config/ for every value (PULSE_SERVER, the model path, the capture id)
8. One finished review record, as the model for yours:
   /root/groundstation/docs/api-harden2/rev5/test/phone_client-review.md (its conclusions and the note on the
   owner's six reviews) and /root/groundstation/docs/api-harden2/rev5/test/runtime-round-1-reviewer.md.

## 3. The facts you start from (handoff part E, item 8, and the rulings)

- Two transcript inputs, both visible in the code (AUD3): the laptop mic through the owner's whisper ASR node and ROS 2; the phone's own recognizer through one persistent TCP line the phone dials into a laptop listener.
- The ASR node is the owner's C++ (llm_to_action_asr_server): F5 starts a recording, F5 again stops it, whisper runs, the clip is written to asr_clips/, the text is published on /asr_server/transcribe.
- The mic listener is a RosSubscription; its callback stamps the Transcript with PerfNow and carries the newest clip name ("" when unchanged, TEL8); the join between clip and transcript is the owner's C++ side (he added a log line on 2026-10-16).
- The phone line: one persistent TCP socket; an "ok" line back per transcript; a keepalive; its own status row; a plain thread, no asyncio (today's asyncio goes).
- The Transcript message goes to the app's queue with its input kind, text, stamp and clip name; the recognizer decides; speech in decides nothing.
- The emergency budget: a stop said into the mic must reach the phone within 1 s; whisper's time is part of that budget (RVW item 15).

## 4. What you must settle (each one lands in the document and the header)

1. The ASR node's pure spec function: argv from config, env additions (PULSE_SERVER), the clip folder, a publisher count on /asr_server/transcribe as the probe, SIGINT, BUDGET_SPENT_DIE, the log path.
2. The mic listener: the RosSubscription, the Transcript fields as code, the clip-name rule, and what the listener does on a transcript that arrives while the previous is still in the queue.
3. The phone TCP line: the listener socket (bind, port from config), one connection at a time or more, the "ok" line, the keepalive and its timeout, the status row the module owns, the thread and its stop in Destroy.
4. The Transcript message: one struct for both inputs, with the input kind; its stamp; its clip name.
5. Whisper's time against the emergency budget: measure on a one-word and a five-word utterance if the ASR node runs in this container; if the mic or the model is not available here, mark it unverified and say what is missing.
6. TOCTOU (gate item 11): the phone reconnects while the old connection's thread still reads; the clip name read before the file is closed; name each window and what closes it.
7. The failure matrix with gate item 12: the phone line drops (SEEN in sessions), the ASR node dies (the supervisor relaunches it), a transcript with no clip; each row with its cause.

## 5. The rules of the deliverable

- Only `speech_in.md` and `speech_in.h` in this folder, plus `speech_in_internal.h` only if the owner must see a
  mechanism to judge the design (RUN4). No drawing. No other file (DOC1). The brief stays.
- `speech_in.md` follows the MOD1 order in modules/README.md: the job, the picture (one text
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
  and only under your prefix `SIN`. Never RUN, PRF, TEL, FB, LLM or PHN. A change you need in an
  approved module is an open point carried to the manager, never an edit of that module (PAR2).
- Mark every number you did not measure "unverified".

## 6. The procedure

1. Read everything in section 2. Write the full picture of the module in the system before
   any design: the threads, the processes, the queues, the rates, the sizes.
2. Design. Reason from the forces to one proposal per point in section 4. Where the owner must
   choose, write the four-line form. Where the design is clear, decide and state the reason.
3. Write `speech_in.md` and `speech_in.h`. Run the layout tool and gcc.
4. Run the twelve-point gate yourself. Each item gets the failure you tried and the mechanism
   that stops it, written in the document's gate section. Item 9 needs measurements (section
   7). Put the numbers and the commands in the document. Do not add scripts to the repo.
5. Three reviewer rounds with subagents, one at a time. Each round: spawn one subagent
   (general-purpose, model opus, maximum care, the web for sources). Give it the module's files,
   this brief's sections 3 and 4, gate item 12, and the three lenses of round 1 (storage and
   hardware; concurrency and real time; YAGNI and decoupling). It writes only its section into
   /root/groundstation/docs/api-harden2/rev5/test/speech_in-review.md under
   "## Round N: reviewer". You answer under "## Round N: answer": accepted with its cause and
   the change made, or rejected with the cause and the generic handling that covers it. Rounds
   2 and 3 first re-check the cause behind every mechanism added since round 1. End the file
   with "## Conclusions": agreed, open, changed, every item the review added with its cause, and
   the counts accepted, narrowed, rejected.
6. Update the document and the header after every round. Re-run the layout tool and gcc.
7. Write the progress log below at every checkpoint. The owner reviews in your session; write
   his words into the log verbatim. Return one line to the chat when done.

## 7. The machine and the measurements

- The ASR node needs the microphone through PulseAudio and may need the GPU. Check whether it runs in this container before you promise a measurement. Take the GPU if you load whisper:
  `/root/groundstation/tools/lock.sh wait speech_in gpu`, and release with `/root/groundstation/tools/lock.sh release speech_in all`.
- The phone line can be measured with the mock or a plain socket client from your scratch folder: the "ok" round trip, the keepalive, a reconnect. Record the numbers and the commands in the document.
- Other agents work at the same time on other modules. You do not edit their folders, the
  approved modules, the handoff, or modules/README.md. The manager records the owner's rulings
  there and carries your items to the approved modules.

## 8. Done when

- Both files exist, the header compiles, the layout tool ran clean, every gate item has its
  proof in the document, the review record holds three rounds and the conclusions, every open
  point is in the four-line form with an OPEN mark in the header, and the log below says so.

## Progress log (newest at the end)

