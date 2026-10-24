# rev5 module reviews: one document and one header per module (started 2026-10-12)

The order, bottom-up by dependency: perf, telemetry, runtime (die, the supervisor, ROS2), the
frame buffer, the llama server, the SAM3 server, the phone-app client and its mock, speech in,
speech out, the recognizer, the platform dispatcher, the frame source, the vision jobs, the
keys, the screen and the app. The next module starts only after the owner approved the previous.

Each module gets its own folder here, `<name>/`, with `<name>.md` and `<name>.h` only (plus
`<name>_internal.h` when the owner must see a mechanism). No other file without his word (DOC1). This README stays the index and the template (owner, 2026-10-12).

`<name>.md`, the review document, in this order (the owner, 2026-10-12, MOD1: a human must
be able to review it in 15 minutes, so the picture and the use come first):
1. The job of the module, in one sentence. If it needs "and", the module splits.
2. The picture: one text diagram of the module in the system (threads, queues, files) inside
   the document. No HTML drawing unless the owner asks (DOC1, 2026-10-17).
3. How a caller uses it: two instances in pseudocode, in the Python of the build.
4. The open points for the owner (MOD2): each with the question, what the header shows now,
   what changes on "no", and the recommendation. The header marks each one with `OPEN n`.
5. Today: how the code does it now, with the file names, and what is wrong with it.
6. The rulings that bind it (the ledger IDs, the owner's words quoted) and the forces it must
   meet (the numbers from 01-system-architecture.md section 8).
7. The design gate: who creates, holds and destroys it; the data in and out; every piece of
   mutable state and its owner; every thread and its stop; the process and its stop protocol.
8. The notes that did not make the header: each rejected alternative with its reason, the
   costs of the choices, the mapping to Python.
9. The tests the module ships with, named.

Before a module's files are shown to the owner, the author agent passes this gate. A box is
never ticked with "yes": each item is answered with the failure tried and the mechanism that
stops it, in the module's document (the owner, 2026-10-14; the Gemini review of this file:
"proof-based rather than assertion-based").
1. The real-time path. The capacity and the drop policy of every queue the main thread
   touches, and the worst case of one call on the main thread, with the number (SYS1).
2. A logger or a sink: no domain type, no app state, no die() (TEL1 to TEL3). Proof: the
   header's types and calls, listed.
3. Fault containment. Every die() in the module traced to RVW4 (our own bug mid-flight: the
   hand-over) or to a start-up check; everything else degrades to a health value. Not every
   module is a logger: a client may still die on our own bug; the trace says which.
4. Buffer lifetimes. Every frame slot the module touches: taken where, released where, held
   across which call; never held for a logger (RVW3).
5. Types and units. Every constant in config, with its unit; a value past 2^31 outside an
   enum; every timestamp compare written for unsigned values.
6. One home. Every struct, helper and key: its owning module named; nothing twice.
7. The contract. Every file, line and key as code; every reader file named in the
   change-impact table.
8. The Python mapping as code. Thread-local visibility; what a frozen object freezes; a put
   that can block; an exception that can leave the module; where the GIL is released. Python
   allocates on every call (an int above 256 is an object), so the rule is not "zero
   allocations" but "no allocation that grows, and the cost measured" (item 9).
9. The cost budget. Rate times cost for the hottest thread, measured on this machine, against
   1 % of the 33 ms frame (330 us). Unmeasured means marked unverified.
10. Deterministic checks. gcc -fsyntax-only -Wall on every header; svg_text_check.py on the
    drawing; the document, the headers and the drawing agree on every name and number.
11. TOCTOU. Every check-then-act in the module is named with the mechanism that closes it,
    or the window is named and what covers it (the owner, 2026-10-17: "Make sure TOCTOU
    doesn't fall inbetween the cracks"). Each closed window gets a test.
12. Need (the owner, 2026-10-18, REV8: "I fully agree with everything here! APPROVED!"). Every failure-matrix row and every accepted finding names its cause:
  - SEEN: a session log line, a measurement in normal use, or the owner naming the failure
    as seen;
  - DESIGNED: the trigger is named as something that happens in a flight or a session,
    and a trace or a test runs from it through our design;
  - FORCED: someone made it by hand (SIGSTOP, a kill, a cut cable, a full disk).
  A ruling of the owner that requires a handling is a requirement, not evidence. It stands
  on his authority, outside this test.
  A FORCED row, or a row with no cause, gets the generic handling only: the supervisor's
  restart on exit, or a request timeout that returns false. It becomes a test of that
  handling. No mechanism is built for it.
  Answers take two forms. "Accepted: cause, evidence, change." "Rejected: cause, the
  generic handling that covers it."
  A finding against a mechanism that an earlier round added sends the author back to the
  first finding's cause, before any new code.
  Reviewer side: a finding is high or medium only for SEEN or DESIGNED. Rounds 2 and 3
  first re-check the cause behind every mechanism added since round 1.
  Conclusions: list every item that review added, each with its cause, and count findings
  accepted, narrowed and rejected. An added thread, callback, counter with a policy, or
  restart path is an open point for the owner, whatever its cause. So is a change to an
  approved module's contract. The owner reads them once, at the end.
  The manager checks that list before the owner reads. He stops the review for any item
  without SEEN or DESIGNED.
    The record of how this item came to be: 05-llama_server/brief.md, section "REV7 RECORD".
Then the reviewer agent runs three rounds before the owner reads anything. Round 1 reads with
three lenses in turn: storage and hardware (stalls, wear, starvation); concurrency and
real time (preemption, the GIL, wrap-around, priority inversion); YAGNI and decoupling (every
field, constant and abstraction justified). Rounds 2 and 3 are the push-back and the landing
check, as in the perf and telemetry experiments (rev5/test/).

The document's section 7 ends with a failure matrix: one row per failure (a disk error, a 5 s
stall, SIGKILL or a power cut, a full ring or pool, a model timeout, a wrong argument), with
the module's state, the health value or the record it leaves, and whether the aircraft is
touched (never, for a logger).

The Python mapping of every module follows PY1 (2026-10-19): a shared structure is a built-in
container touched one operation at a time, or a lock; never hand-written atomics; the C header keeps
the real atomics as the truth for a later C++ build.

A header reads without its comments: the names, the types and the visible state carry the design;
an internal mechanism the owner must understand is a visible struct and an ordered list of
functions in `<name>_internal.h` beside the thin public header (the house split; the owner,
2026-10-17, RUN3 and RUN4).

`<name>.h`, the header: code only, the house rules of the rev5 README (Create and Destroy,
app-owned handles, `_Atomic` types, the m_ prefixes, no implementation comments), laid out by
tools/style/header_layout.py, compiled with `gcc -fsyntax-only -x c`.

The owner reviews both files. His verdicts go into the ledger in the same turn. Then the next
module. The method for writing them: /superpowers:brainstorming, with the module's full picture
first (CTX1, BRN2).

| module | document | header | state |
|---|---|---|---|
| util (the general structures) | | 00-util/spsc_record_queue.h (a bounded queue of records with ONE producer and ONE consumer; typed endpoints; Front and Pop; in Python a deque of tuples, in C a slot ring and a byte area), index_queue.h (a bounded first-in first-out queue of slot indexes under one lock, safe for any threads), fixed_text.h (a named fixed-size text) | DRAFT 2026-10-19 (RCD8 to RCD12), carved out of the recorder; reviewed in round 3; one home each; any module may use them |
| the recorder (perf + telemetry, RCD1 to RCD75, PY1 to PY3, GIL2) | 01-recorder/recorder.md: the source of truth of the design (section 2, each mechanism in four steps; RCD61); eight sections; the dated records: ../test/recorder-decisions-2026-10-21.md (frozen) and ../test/recorder-history-2026-10-24.md (the rounds, moved out, RCD72) | 00-util: fixed_text.h, common_names.h, monotonic_clock.h, frame_types.h, statistics.h, index_queue.h, spsc_record_queue.h; 01-recorder: recorder_statistics.h, recorder.h, record_field.h, record_span.h, record_event.h, record_frame.h, record_file.h, recording_thread.h, image_buffer_pool.h, record_writer.h, recorder_internal.h; all -Wextra -pedantic clean; short comments with a pointer to recorder.md; recorder.html (six drawings, approved); recorder_aggregate_for_review.md regenerated | APPROVED 2026-10-24 (RCD75; draft 31): recorder.md section 2 is the design's truth, the eighteen headers its C rendering, the six drawings its pictures (sources in ../test/recorder-drawings/). NEXT: the fold of perf and telemetry (OPEN 4), then the second wave; the headers are one rendering; awaiting the owner's approval of the module from recorder.md and the drawings; then OPEN 4 (the fold of perf and telemetry) and the second wave |
| perf | 01-perf/perf.md | 01-perf/perf.h; perf_record_<owner>.h x7 | APPROVED 2026-10-12 (PRF3 to PRF5); FOLDING into the recorder (RCD1, O4 approved): kept until the recorder is approved, for its measurements, alternatives and tests; its mechanisms live on in 01-recorder |
| telemetry | 02-telemetry/telemetry.md | 02-telemetry/telemetry.h; telemetry_record_dispatch.h, telemetry_record_vision.h | APPROVED 2026-10-16 (TEL2 to TEL19); FOLDING into the recorder (RCD1, O4 approved): kept until the recorder is approved, for its measurements, alternatives and tests |
| runtime | 03-runtime/runtime.md | 03-runtime/runtime.h (the contract), runtime_internal.h (the state, the policy, Die's step 4); runtime.html | APPROVED 2026-10-17 (RUN1 to RUN14) |
| the frame buffer | 04-framebuffer/framebuffer.md | 04-framebuffer/framebuffer.h, framebuffer_internal.h; brief.md (the agent's log) | FINISHED 2026-10-18 by its agent, reviewed by the owner in that session (FB1 to FB8); one point left for the owner: the capture time field in the read-only frame reference; record: test/framebuffer-review.md |
| the llama server | 05-llama_server/llama_server.md | 05-llama_server/llama_server.h; brief.md (the agent's log, the REV7 record) | FINISHED 2026-10-18 by its agent, reviewed by the owner in that session (LLM1); pending from P1 (PRF7, parked): the perf helper's tracer parameter; record: test/llama_server-review.md |
| the phone client and its mock | 07-phone_client/phone_client.md | 07-phone_client/phone_client.h (the contract), phone_client_internal.h (the struct, the send steps), phone_mock.h (the mock's spec); brief.md (the agent's log, section 9: what the rulings superseded) | APPROVED 2026-10-18 (PHN1 to PHN8); record: test/phone_client-review.md; pending from P1 (PRF7): the perf helpers' tracer parameter |
| the SAM3 server | 06-sam3_server/brief.md | | BRIEFED 2026-10-18 (PAR2); the owner launches the agent; record: test/sam3_server-review.md |
| speech in | 08-speech_in/brief.md | | BRIEFED 2026-10-18 (PAR2); the owner launches the agent; record: test/speech_in-review.md |
| speech out | 09-speech_out/brief.md | | BRIEFED 2026-10-18 (PAR2); the owner launches the agent; record: test/speech_out-review.md |
| the recognizer | 10-recognizer/brief.md | | BRIEFED 2026-10-18 (PAR2); the owner launches the agent; record: test/recognizer-review.md |
| the platform dispatcher | 11-platform_dispatcher/brief.md | | BRIEFED 2026-10-18 (PAR2); the owner launches the agent; record: test/platform_dispatcher-review.md |
| the frame source | 12-frame_source/brief.md | | BRIEFED 2026-10-18 (PAR2); the owner launches the agent; record: test/frame_source-review.md |
| the keys | 14-keys/brief.md | | BRIEFED 2026-10-18 (PAR2); the owner launches the agent; record: test/keys-review.md |

Items carried to later modules: the runtime module's preflight asserts that nproc equals the
machine's logical core count; a lower value means a container limit or an affinity mask (the
owner, 2026-10-12, PRF5).
- Every module that owns a record or a perf stage takes its `telemetry_record_<owner>.h` or
  `record_<owner>.h` into its own header at its review (TEL3 (3), TEL4); the keys do not
  change in the move.
- The speech-in module: the ASR node publishes the clip's file name with the transcript (the
  exact join; until then the mic listener carries the newest clip name, "" when unchanged);
  the mic listener puts that name in the Transcript message (telemetry R1-10, R2-3).
- The frame buffer and the frame source: the slot geometry is fixed for a run; a geometry
  change is a planned restart of the video path, never a new size mid-run (telemetry R3-7).
- The runtime module owns the die() order: stop, manual, notify, then the perf flush and the
  telemetry drain in parallel, then the children, exit (perf point 5; telemetry R3-8;
  runtime R2-14).
- The app step (step 3): design section 6 lists telemetry as a frame-buffer reader; it no
  longer is (the job copies). Section 4 says telemetry(turn) and telemetry(job) once; both
  are twice. Section 7 says "from any thread"; three of four calls are main thread only.
  Section 4 gets a sixth producer of PlatformReply if telemetry point 13 is accepted.
  Sections 2 and 3: "SIGCHLD → its own queue" becomes "a pidfd per child" if runtime point 4
  is accepted; section 3 gains a third sender of the stop: Die's hand-over, from its step
  thread (runtime R3-7).
- The app's start order: the frame source's size is probed (the webcam, a file) or given (the
  drone, 1920x1080) before the frame buffer and telemetry are created (telemetry TEL17).
- The build, after every design: the replayer and log/show.py rewritten to the helpers' keys,
  with a sample-session generator (telemetry section 9).
 From the phone client review (PHN3, 2026-10-18): runtime.h line 25 ("the stop, then manual") changes with the owner's ruling on Die's hand-over; module 11 (the platform dispatcher) gets facts 1 to 5 of phone_client.md OPEN 1 for its own manual switch. From the llama server review (LLM1, 2026-10-18): runtime: ProcessSpec gains m_removeBeforeLaunch, a path the supervisor removes before each launch (a stale socket file blocks the relaunch, measured); runtime: m_env lists only the additions, merged over the current environment (RUN16); util/guarded.py: the HTTP helper returns the failure kind, not a repr, and connects to a Unix domain socket path; config: LLAMA_SERVER_SLOTS = VISION_POOL_SIZE + 1, PLAN_TIMEOUT_NS 10 s, VISION_LLAMA_TIMEOUT_NS 20 s, PLAN_WARM_UP_TIMEOUT_NS 30 s, LLAMA_CACHE_RAM_MIB 512; the vision review: 8 image requests at once took 10.7 s without SAM3 and may pass the 20 s timeout under SAM3 (unverified); perf: perf_record_llama.h is deleted when llama_server.h is approved. From the phone client review (PHN5, 2026-10-18): module 15's start script: run.sh starts the mock, then the app, through tmux -e, with no written file (the owner: "I don't like that we write to app.sh"); module 8 (speech in) owns the phone's TCP line listener; the hand-over text of runtime.h line 25 waits on R1 (a, b or c). From the phone client review (PHN7, 2026-10-18): module 15's start script has no "kill the old stack" and no port freeing; the design document's section 9 line "the client refuses a non-loopback host without allowReal" is stale: the client is agnostic of its server and the launcher picks mock or real from config CONTROL; the hand-over text of runtime.h line 25 is done ("halt, stop, stop", PHN6). From the phone client approval (PHN8, 2026-10-18): module 15's start order registers PhoneMockProcessSpec with the supervisor when config CONTROL is "mock" (BUDGET_SPENT_DIE), and picks the client's server from config; run.sh starts the stack through tmux -e with no written file and no kill step. From the recorder reviews (RCD7, 2026-10-18): runtime_internal.h gains OsEvent, a sticky flag with set, clear and a timed wait on the monotonic clock (a threading.Event); config holds the mask limit per pass (3); the app makes the session folder with a mkdir that fails on EEXIST; the screen picks the GPU reader per vendor; the frame buffer drops its FrameSize copy and includes frame_types.h at the fold.