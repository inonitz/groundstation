# Brief: the recognizer design agent (harden2 rev5, module 10)

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

Design the recognizer module of harden2 and deliver two files the owner can review in 15
minutes: `recognizer.md` and `recognizer.h` in this folder. The job in one sentence is in
section 3. You design from the owner's words and the architecture document. You do not transcribe
today's code into C. You do not copy the rev4 sketch; it was rejected.

## 2. Read first, in this order

1. /root/groundstation/CLAUDE.md and /root/groundstation/docs/guidelines.md (the house rules; the drone safety rules first).
2. /root/groundstation/docs/api-harden2/rev5/modules/README.md: the document order (MOD1), the open-point form (MOD2), the twelve-point
   gate (item 12 is new), the house split, the state table, the carried items.
3. /root/groundstation/docs/api-harden2/rev5/01-system-architecture.md: section 4 (the trigger table: emergency, manual, auto, clear act now; anything else to the route queue; the stop rule and the epoch counter; RVW6, RVW7), section 3 (the recognizer worker thread), section 8 (a plan 0.5 to 1.5 s), section 10.
4. /root/groundstation/docs/task-active-harden2-handoff-2026-10-02.md, section 2a3: part C (the procedure),
   part D (what each review taught), part E item 10 (this module), and item 5 (the llama server, finished), part F.
5. The finished modules, as the reference for the shape and the depth, and as your contracts:
   - 05-llama_server/llama_server.md and llama_server.h: your one service; LlamaClientCreate(socket path); one request function with a result enum, never an exception; 9 slots, one per caller (LLM1 D2); the warm-up messages are built by YOU and sent by the app (REC1)
   - 01-recorder, record_frame.h: RecorderCreate takes the frame size, so the size probe runs BEFORE
     the recorder and the buffer exist (the start order, carried in modules/README.md)
   - 01-recorder (read it first, as the UPDATE above says): the spans and events you own, with their
     typed fields; MonotonicNow for every timestamp
   - 03-runtime/runtime.md: nothing of yours is a process
6. The ledger rows that bind this module, in /root/groundstation/docs/spec-harden2-cleanup.md:
   REC1, RVW6, RVW7, TR16, TR17, LLM1, REV8, PRF7, MOD1, MOD2, GATE1, DOC1, PAR2, and the recognizer rows of the ledger (search "recognizer", "fast path", "bypass", "guards", "rewrites", "lexicon"). Quote the owner's words in the document's rulings section.
7. Today's code, to describe what is wrong with it, not to copy it:
   - /root/groundstation/projects/integration_harden2/recognizer/recognizer.py, fast_path.py, bypass.py, guards.py, rewrites.py, lexicon.py
   - /root/groundstation/bench/recognizer/ (the benchmark and the scorer over datasets/recognizer/*.json: your design must keep that benchmark runnable against the pure functions)
   - /root/groundstation/projects/integration_harden2/config/ for every value (the trigger words, the plan timeout, the warm-up sentence)
8. One finished review record, as the model for yours:
   /root/groundstation/docs/api-harden2/rev5/test/phone_client-review.md (its conclusions and the note on the
   owner's six reviews) and /root/groundstation/docs/api-harden2/rev5/test/runtime-round-1-reviewer.md.

## 3. The facts you start from (handoff part E, item 10, and the rulings)

- The recognizer is a bundle of pure functions over data, with NO state (REC1): no Create, no Destroy, no Act. One sentence in, one tagged Decision out.
- The steps, in run order; the first that answers ends it: match a trigger; match a fixed command; only-negation; the Hebrew rewrite; the planner messages and the llama request; parse the plan; the numbers match; the copied example.
- The trigger table: emergency, manual, auto and clear act now, on the receiving thread; anything else goes to the route queue (section 4). The owner asked "Are these the only keywords?": the table is his to see, as code.
- The stop rule and the epoch: a sentence carries the epoch of the turn; a decision from an old epoch is dropped by the main thread (RVW6, RVW7).
- A plan takes 0.5 to 1.5 s (section 8). The recognizer worker thread sends the request and posts the Decision message; the main thread never waits on llama.
- Gemma answers and verifies; it never draws boxes. Boxes come only from SAM3.
- The warm-up: the app sends one planner request built by your messages function after the llama row is UP (REC1: the recognizer warms nothing itself).

## 4. What you must settle (each one lands in the document and the header)

1. The step functions as code, each pure, each with its data in and out; the Decision record (kind, he2, mission JSON, target, reject reason, the two durations) as code.
2. The trigger table's words, as a table in the document and a constant in config; the owner rules on the list.
3. The recognizer worker thread: who owns it (the app), its queue, the Decision message with its stamps and the epoch; the stop rule written as code.
4. The planner request: the messages, the grammar, max tokens, the timeout (PLAN_TIMEOUT_NS 10 s per the llama review) and what a timeout or an invalid reply becomes (DECIDE_PLANNER_FAILED, never an exception).
5. The benchmark path: bench/recognizer runs the same pure functions with a mock planner or a real one; show the call.
6. TOCTOU (gate item 11): a Decision posted after the epoch moved; a second sentence while the planner runs; name each window and what closes it.
7. The failure matrix with gate item 12: llama down or timed out (SEEN: the sessions), a reply the grammar did not constrain (DESIGNED: the parse), a copied example (SEEN: the benchmark); each row with its cause.

## 5. The rules of the deliverable

- Only `recognizer.md` and `recognizer.h` in this folder, plus `recognizer_internal.h` only if the owner must see a
  mechanism to judge the design (RUN4). No drawing. No other file (DOC1). The brief stays.
- `recognizer.md` follows the MOD1 order in modules/README.md: the job, the picture (one text
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
  and only under your prefix `REC`. Never RUN, PRF, TEL, FB, LLM or PHN. A change you need in an
  approved module is an open point carried to the manager, never an edit of that module (PAR2).
- Mark every number you did not measure "unverified".

## 6. The procedure

1. Read everything in section 2. Write the full picture of the module in the system before
   any design: the threads, the processes, the queues, the rates, the sizes.
2. Design. Reason from the forces to one proposal per point in section 4. Where the owner must
   choose, write the four-line form. Where the design is clear, decide and state the reason.
3. Write `recognizer.md` and `recognizer.h`. Run the layout tool and gcc.
4. Run the twelve-point gate yourself. Each item gets the failure you tried and the mechanism
   that stops it, written in the document's gate section. Item 9 needs measurements (section
   7). Put the numbers and the commands in the document. Do not add scripts to the repo.
5. Three reviewer rounds with subagents, one at a time. Each round: spawn one subagent
   (general-purpose, model opus, maximum care, the web for sources). Give it the module's files,
   this brief's sections 3 and 4, gate item 12, and the three lenses of round 1 (storage and
   hardware; concurrency and real time; YAGNI and decoupling). It writes only its section into
   /root/groundstation/docs/api-harden2/rev5/test/recognizer-review.md under
   "## Round N: reviewer". You answer under "## Round N: answer": accepted with its cause and
   the change made, or rejected with the cause and the generic handling that covers it. Rounds
   2 and 3 first re-check the cause behind every mechanism added since round 1. End the file
   with "## Conclusions": agreed, open, changed, every item the review added with its cause, and
   the counts accepted, narrowed, rejected.
6. Update the document and the header after every round. Re-run the layout tool and gcc.
7. Write the progress log below at every checkpoint. The owner reviews in your session; write
   his words into the log verbatim. Return one line to the chat when done.

## 7. The machine and the measurements

- A real planner request needs llama-server on the GPU. Take the lock before a launch:
  `/root/groundstation/tools/lock.sh wait recognizer gpu`, release with `/root/groundstation/tools/lock.sh release recognizer all`. The measured 489 ms alone and 1362 ms under SAM3 exist in section 8; re-measure only what your design changes.
- The benchmark in bench/recognizer must still run at the end of your design against the pure functions; say how, with the command.
- Other agents work at the same time on other modules. You do not edit their folders, the
  approved modules, the handoff, or modules/README.md. The manager records the owner's rulings
  there and carries your items to the approved modules.

## 8. Done when

- Both files exist, the header compiles, the layout tool ran clean, every gate item has its
  proof in the document, the review record holds three rounds and the conclusions, every open
  point is in the four-line form with an OPEN mark in the header, and the log below says so.

## Progress log (newest at the end)

