# perf: the timing record of a run (rev5 module review, started 2026-10-12)

> **FOLDED into the recorder (RCD1, 2026-10-18; the fold approved as O4, RCD2).** The perf module's
> mechanisms live on in `../01-recorder/recorder.md`; the contracts there replace the ones below.
> This document stays until the recorder is approved, for its measurements, its rejected
> alternatives and its tests, which the fold carries over.

The header is `perf.h`. The design document is `../../01-system-architecture.md` (sections 7, 8).
The state of this review: APPROVED 2026-10-12 (ledger PRF3 to PRF5): every open point is closed.
The review experiment is in `../../test/` (rounds 1 to 3, and one external review).

## 1. The job, in one sentence
Perf records how long each step of a run took, from any thread, and writes the records to disk.

## 2. The picture
```
   THE APP PROCESS                                        THE SAM3 PROCESS
   main thread  ──record──► ring 0 ─┐                      server thread ──record──► ring 0 ─┐
   frame source ──record──► ring 1 ─┤                      queue thread  ──record──► ring 1 ─┤
   recognizer   ──record──► ring 2 ─┤  one SPSC ring                                          │
   platform     ──record──► ring 3 ─┤  per thread                        writer thread ◄──────┘
   emergency    ──record──► ring 4 ─┤  (4096 records,                        │ every 5 s,
   voice x2     ──record──► ring 5,6┤   drop + count                         │ one write, one fsync
   job pool x8  ──record──► ring 7..┤   when full)                           ▼
   supervisor   ──record──► ring 15─┘                      <session>/perf-sam3-<pid>.jsonl
                                    │
                     writer thread ◄┘ every 5 s; die(): flush, 1 s timeout
                            │
                            ▼
              <session>/perf-app-<pid>.jsonl
                            │                                         │
                            └──────────────► run.sh perf ◄────────────┘
                              reads every perf-*.jsonl; converts by each file's clock line;
                              sorts by start; percentiles per span stage; the GPU samples;
                              the 20 slowest frames; the drop total
```
A record is (stage, start, end, payload). The caller takes `PerfNow()` before and after a
step and calls `PerfRecord` once. Nothing blocks, nothing locks, nothing allocates in C. The
drawing is `perf.html` (checked by tools/style/svg_text_check.py).

## 3. How a caller uses it: two instances, in the Python of the build
**Instance 1: the main thread's frame loop (PERF_FRAME every frame, PERF_GPU once a second).**
```python
# app/main.py, once per process, the first service
perf = perf_create(session.dir, "app")               # PerfCreate; PERF_NONE in tests

# app/screen.py, the main thread, every frame
previous_end = perf_now()
while not quit:
    t0 = perf_now()
    frame = frames.acquire_latest()                    # the frame buffer (another module)
    t_read = perf_now()
    draw(frame, views, panes)
    t_draw = perf_now()
    cv2.waitKey(1)
    t_end = perf_now()
    frames.release(frame)
    if perf is not PERF_NONE:                          # build no payload for nothing
        perf_record(perf, FRAME, previous_end, t_end,
                    f'"read":{ms(t_read - t0)},"draw":{ms(t_draw - t_read)},'
                    f'"show":{ms(t_end - t_draw)}')
    if frame_no % 30 == 0:                             # the GPU sample: start == end
        perf_record(perf, GPU, t_end, t_end,
                    f'"mem":{gpu.mem_mib()},"load":{gpu.load_pct()}')
    previous_end = t_end
```
**Instance 2: one SAM3 request, timed in the app and in the server, joined by `req`.**
```python
# perception/jobs.py, a job on a pool thread (the app process)
req = next(request_ids)                                # the join key
slot = frames.acquire_latest()                         # held across the request (RVW3)
t0 = perf_now()
reply = sam3.detect(req, slot.seq, concepts, priority) # blocks 0.4 to 1.9 s
t1 = perf_now()
frames.release(slot)
perf_record(perf, SAM3_REQUEST, t0, t1,
            f'"req":{req},"prio":{priority},"ok":{int(reply.ok)}')

# sam3/server.py, its own process, its own tracer, its own file
perf = perf_create(session_dir, "sam3")
while running:
    request = queue.get()                              # command before refresh
    t_start = perf_now()
    boxes = model.detect(frames.pixels(request.seq), request.concepts)
    t_end = perf_now()
    perf_record(perf, SAM3_PASS, t_start, t_end,
                f'"req":{request.req},"wait":{ms(t_start - request.enqueued_at)},'
                f'"boxes":{len(boxes)}')
    send_reply(request, boxes)
```
The report then shows `sam3_request` (what the job waited) and `sam3_pass` (what the model
took) and can subtract them per `req`: the socket plus the queue wait.

## 4. The open points for the owner: all closed (PRF3 to PRF5)
Settled 2026-10-12 (ledger PRF3, PRF4): the picture; the usage pattern; the header shape and
its lifetime comment; the stage enum (1); the 128-byte record (3); Create's arguments (4);
the die() order stop, manual, notify, flush, exit (5, "You're correct in every step"); the
bytearray ring with struct.pack_into (6, "Sure"); the writer's Event (7, "Accepted").

**The cost of recording, as the owner asked (3B).** A 5-minute session at full load:
| what | per second | in 5 minutes |
|---|---|---|
| records, all threads | about 50 | about 15,000 |
| records, the main thread | about 40 | about 12,000 |
| the record itself (pack_into, two clock reads; the reviewer measured 330 + 115 ns) | 22 us | 6.7 ms |
| the payload f-string before it (about 400 ns) | 20 us | 6.0 ms |
| the main thread's share, per frame (1.3 records; 33 ms per frame) | about 1 us per frame | 0.003 % of a frame |
Dividing by threads: the main thread carries 80 % of the records; the other 15 threads share
the rest, under 1 us per second each.

**Open 4, the fill time, corrected.** 250 records is one drain of 5 s, not one second. The
main thread's ring holds 4096 at 40 per second: it fills after about 100 s without a drain.
One ring with all 50 per second fills after 82 s. The owner's conclusion stands: in theory no
record is ever dropped; the drop line exists only to prove it.

**Open 2, re-answered on the merits: the gauge shrinks to the GPU sample.** What was proposed:
once a second, the queue depths, the live jobs, the held slots, the GPU memory and load. What
they have to do with performance: a span says how long a step took; these say what the load
was at that instant, the cause side. Checked against this design, most of them carry nothing:
the route queue holds at most one sentence at speech rate (RVW5); the main queue sees under
one message per frame; the command queue holds at most one mission; a depth of 0 or 1 is no
information. The live jobs are in the jobs pane already. The held slots are a leak detector,
not a timing. What stays: the GPU memory and load. They explain the measured contention: a
plan takes 489 ms alone and 1362 ms while SAM3 runs; 410 ms against 630 ms for a pass. That
sample exists today (Q3 a, once a second through pynvml, 0.018 ms). The proposal: the stage is
`PERF_GPU`, a sample of `mem` (MiB) and `load` (percent), recorded by the main thread once a
second; no queue depths; no sampler thread. The owner decides.

**Open 8, closed: no sink thread; a bug is a bug; the table size is the design's count.**
The owner first proposed the table size as nproc; the agent pushed back (threads wait on
blocking calls and do not scale with cores; a 4-core laptop runs the 16 threads); the owner
conceded (PRF5). `kPerfMaxThreads` is a config constant of the design's thread count. The
nproc check (nproc below the machine's logical cores means a container limit or an affinity
mask) goes to the runtime module's review as a preflight check.
The earlier explanation: The owner's objection: "instead of
making sure we never recreate new threads in our design we keep a dummy thread that acts as
a sink for bugs?" Correct. The design creates every thread at start: the listeners, the
workers, the pool of 8, the frame source, the supervisor; 16 in the app, 2 in the SAM3 server.
No thread is created later. So a 33rd thread cannot happen by construction. If it happens, it
is our own bug, and RVW4 already says what our own bug does mid-flight: hand control to the
RC, notify, crash. No special branch: `kPerfMaxThreads` is the budget (32, twice the design),
and the 33rd thread calls die() like any other bug. The drop-and-count branch is gone.

**The helpers (TEL4, 2026-10-14).** The owner: "we should also have, say, helper functions
for performance logs." Perf records a stage, two timestamps and a payload, so it logs; the
payload keys per stage are the contract the report reads. Each stage gets one helper
(PerfFrame, PerfSam3Request, ...) that builds the payload and calls PerfRecord once. The helper
lives in the module that owns the stage and is written at that module's review: the frame
and gpu helpers in the screen, the sam3 request in the vision jobs, the sam3 pass in the SAM3
server, the llama request in the llama module, the dji request and the emergency in the
platform client, the turn and message and e2e in the app's dispatch, say in speech out. They
are defined now, one header per owner: `perf_record_screen.h`, `perf_record_dispatch.h`,
`perf_record_vision.h`, `perf_record_sam3.h`, `perf_record_llama.h`, `perf_record_platform.h`,
`perf_record_speech_out.h`; each moves into its module's header at that review (TEL3 (3)). The usage
instances of section 3 call PerfRecord directly; the build calls the helpers.

## 5. Today
The code: `projects/integration_harden2/log/perf.py` (208 lines) and `log/perf_report.py` (135).
One `Perf(folder)` object is built by the app and handed to every part it times. A part built
without one gets `NO_PERF`, which records nothing.

How it records. `record(stage, ms, **fields)` builds a dict and appends it to a list under a
lock. A writer thread encodes the list as JSON lines every 5 s (`PERF_FLUSH_SECONDS`, R7).
`die()` flushes first, so a crash keeps its timings. `run.sh perf` computes the percentiles
later (C.1: "Record everything and calculate metrics later!").

How it measures a span. The caller takes `time.monotonic()` before and after, and records the
difference. For a span that starts in one part and ends in another, perf keeps named marks:
`mark("e2e")`, `move_mark("e2e", "e2e_box")`, `end("e2e_box", "e2e")`, `take_since("ptt_release")`.

The record sites today, with their stage names:
- `app/main.py`: "startup" (imports); the F5 release mark; the GPU sampler start.
- `app/turns.py`: "asr", "turn"; the e2e marks (three start kinds: ptt, phone, transcript).
- `app/ui.py`: "frame" every frame (gap, read, draw, show); the e2e end at the first box.
- `dji_app/client.py`: the e2e end at the command.
- `gemma/client.py`: "gemma" (label plan or vision; the server's own token timings).
- `perception2/vision.py`: "sam3" (lock wait + forward), "highlight_gate", "count", "describe".
- `audio/speech_out.py`: "say".
- inside perf itself: "gpu" every 1 s through pynvml; "startup" per status row, by polling.

What is wrong with it (PRF2, the owner's five bullets, 2026-10-04):
- Every record allocates a dict and takes a lock. The frame loop pays that 30 times per second.
- The marks are a dict by name. Two turns on two threads both mark "e2e". The second overwrites
  the first. That is a real bug today.
- The running flag is not atomic. The stop goes through `threading.Event`, which takes a lock.
- Perf polls app state: `watch_startup` reads the status rows. A logger must hold no app state.
- The stage is a string. A typo makes a new stage that no report row shows (PRF1).
- SAM3 runs inside the app today. In rev5 it is its own process. Today's perf cannot record
  from a second process.

## 6. The rulings that bind it, and the forces
| ID | the owner's words | what it fixes here |
|---|---|---|
| C.1 (2026-09-28) | "Record everything and calculate metrics later! Keep P25, P50, P75, P95, P99, min & max." | perf stores raw spans; the report computes |
| R7 (2026-09-28) | "Make this configurable inside the config folder, default to 5s." | the flush period |
| V1 (2026-09-28) | "Option A" | the report lists the 20 slowest frames |
| PRF1 (2026-10-02) | "PerfEvent@stage shouldnot be a string, unless you plan on chaining subEvents from each system" | the stage is an enum; no chaining is planned |
| PRF2 (2026-10-04) | opaque PerfLogger; "PerfTimestamp = raw ns"; "API does not track this. App does."; PerfOpen, PerfNow, PerfRecord(p, stage, start, end, payloadJson), a fixed 128-byte copy; "Nobody actually writes a marker system like this." | the API shape; no marks; the app holds every start timestamp |
| RVW4 (2026-10-12) | "Yes, this is correct" (one process-wide tracer with a ring per thread) + "What about DLL/process Boundaries?" | one tracer per process; a ring per thread |
| RVW5 (2026-10-12) | "You can measure the C++ processes from our end, measuring the time it takes for them to process + the time it takes for the request to be met together as a single metric." | llama-server, the phone app and the keyboard hook are timed request to reply, from the app |
| RVW6, RVW7 (2026-10-12) | "Perfect." (a tracer per process, a file per process, merged by the shared monotonic clock) | the SAM3 server writes its own file; the report merges |
| TEL1, OWN1 | "NO app state"; the app owns every handle | the GPU sampler and the startup watcher leave perf |

The forces, from `../01-system-architecture.md` section 8:
- The frame loop records once per 33 ms. A record must cost microseconds, with no lock.
- The threads that record: the main thread, the frame source, the recognizer worker, the
  platform worker, the emergency thread, two voice workers, up to 8 job threads, the supervisor.
  That is up to 16 threads in the app, plus the threads of the SAM3 server.
- The rates are small: under 100 records per second in the app at full load (30 frames, 8
  passes, a few requests). A 5 s flush period holds under 500 records per thread.
- `time.monotonic_ns()` reads CLOCK_MONOTONIC. On Linux that clock is the same for every
  process on the machine. Two processes can stamp with it and be merged (verified: the Linux
  man page clock_gettime(2); measured on this machine, section 5).
- A crash must keep the records: die() flushes perf after the hand-over and the notify
  (section 9, RVW4; the order is section 4, point 5).

## 7. The design gate
**Ownership.** The app calls `PerfCreate` once, at its first step, and `PerfDestroy` last. The
SAM3 server calls the same pair in its own process, with the same session folder. Each process
holds one `PerfTracer`. No module holds it or takes it at Create (the owner, 2026-10-18, PRF7:
"Why do you hold a handle to m_perf?"); how a caller reaches it is OPEN (PRF7, two forms).
`PERF_NONE` is a tracer that records nothing, for tests and benchmarks.

**Data in.** A record: the stage (an enum), the start and the end (`PerfTimestamp`, raw
nanoseconds of CLOCK_MONOTONIC from `PerfNow`), and a payload of at most 104 bytes of ASCII
JSON keys. The tracer copies the payload into the record. The caller keeps nothing. Every
start is stamped with `PerfNow` on receipt, in the thread that receives the event. A payload
is keys without braces: `"read":10.2,"draw":5.1`. The writer wraps it in braces under `p`.
A payload is never cut: a payload over the limit is replaced by `"cut":N` and counted; a size test per
stage makes that a test failure, never a run-time event.

**Data out.** `<session>/perf-<process>-<pid>.jsonl`, one JSON object per line. Its first
key `k` names the line kind: clock, thread, drop, rec. A record's payload is nested under the
key `p`, so a payload key can never collide with the record's own keys. The stage is written
as the enum name without `PERF_`, in lower case (`frame`). Four line kinds, stated as structs
in perf.h: the clock line (first in the file, written and fsynced by
`PerfCreate`), the thread line (the rings new since the last drain), the drop line (per ring
whose drop count changed), the record. A drain writes them in that order. The report
(`log/perf_report.py`) reads every `perf-*.jsonl` of the session, converts each record by its
file's clock line, sorts all records by start, groups threads by (pid, index), skips a torn
last line with a count, and names a process whose file is missing. It prints the percentile
table of the span stages, the sample stages in their own section, the drop total, and the 20
slowest frames.

**Mutable state, and its owner.** Per thread: one ring of fixed 128-byte records; a write
index stored by the recording thread; a read index stored by the writer thread; a monotonic
drop counter written by the recording thread only. This is a single-producer single-consumer
ring: no lock, no compare-and-swap. Per tracer: the table of rings, filled on a thread's first
record under a lock taken once per thread; the running flag (`_Atomic bool`); one lock around
the drain and the file write, so one consumer runs at a time.

**Threads.** One writer thread per tracer. It wakes every `PERF_FLUSH_SECONDS` (5 s), takes
the drain lock, drains every ring, encodes the lines, appends them with one write and one
fsync, releases the lock. `PerfFlush` does the same from the calling thread. On a disk error
the writer releases the lock, then calls die() (RVW4). Inside die(), `PerfFlush` acquires the
lock with a 1 s timeout and prints one line when it gives up. The stop: `PerfDestroy` clears
the running flag, wakes the writer, joins it, drains once more, closes the file.

**Processes.** None of its own. The SAM3 server creates its own tracer at start and destroys
it in its graceful stop. A killed server loses at most one flush period; its file keeps its
pid, so a restarted server never overwrites it. The app's request record for a reply that
never came carries `"ok":0` and the request key, so the report lists the lost pass.

**What leaves perf.** The GPU sample: the main thread records `PERF_GPU` once a second; no
sampler thread exists (SYS1). The
startup timing: the first time a row reads UP, the main thread records `PERF_STARTUP` with
the launch time as the start. The end-to-end spans: the app holds every start. The F5 release
arrives as a Key message stamped by the keys listener. A transcript, a decision and a platform
reply carry their times. A job's view holds its request time. No mark exists anywhere.

**The order inside die(), changed (section 4, point 5).** Mid-flight, die() sends the stop and the
manual switch first, then notifies the operator, then flushes perf, then exits. Today perf
flushes first (2026-09-22). The flush is one lock with a 1 s timeout; the stuck case would
spend the whole emergency budget before the stop left, and the operator must hear at once.

## 8. The notes that did not make the header
**Why a ring per thread, not one shared array.** One shared array needs one atomic fetch-add on
the index by every thread. A ring per thread needs no shared write: each thread writes its own
slots and its own write index. Rejected: the one shared array, by RVW4 ("a ring per thread" is
the owner's confirmed shape).

**Why not shared memory for the records.** A shared-memory ring would let the SAM3 server
write into the app's tracer. It adds a cross-process protocol for records of 128 bytes. A file
per process and one merge by the clock give the same report. Rejected by RVW6 and RVW7.

**Why a file per process, merged by the clock.** CLOCK_MONOTONIC is shared by every process of
one host in one time namespace. Verified 2026-10-12: a child process stamped inside its
parent's window. The clock stops during a suspend. So each file starts with the three clocks
read back to back; the report converts with them and flags a file whose boot-time offset
differs from the others (a suspend, or another namespace). The report sorts all records, since
a long span is written after a shorter one that started later.

**Why JSON lines, not a binary file.** The report, the tests and `run.sh perf` read JSON lines
today. A binary record saves disk, not time: the writer thread encodes off the recording
thread. Rejected: a binary file (no measured need).

**The ring overflow.** A ring holds 4096 records. At 100 records per second a ring fills in
40 s; the writer drains every 5 s. A full ring drops the new record and increments the ring's
drop counter. The writer writes a drop line per drain. Rejected: blocking the recording thread
(a timing tool must never slow the step it times). Rejected: dropping the oldest (the count
would be lost; ftrace and spdlog's discard_new drop the new one).

**The record layout (PerfEvent), 128 bytes, the C build only.** stage 1 byte; the thread
index 1 byte; padding 6; start 8; end 8; the payload 104 bytes. The file holds JSON lines,
not this layout.

**The thread table.** A ring registers on the thread's first record with the thread's native
id and name. Thread identifiers are recycled, by Python and by Linux after pid_max, so a ring
is found through the thread's own thread-local reference, never through an id lookup. A new
thread finds its thread-local empty, takes a new ring, and the ring joins a list. A ring is
never reused. Every thread is created at start, 16 in the app; a 33rd thread is our own bug
and dies like every bug (RVW4; section 4, point 8).

**The stages and their payload keys.** The keys are short on purpose: the longest payload,
the llama request with seven keys, is 89 bytes with short keys and 129 with long ones. A size
test per stage asserts the largest payload fits.
| stage | kind | start -> end | payload keys |
|---|---|---|---|
| PERF_STARTUP | span | the launch -> a status row first UP | row, restart |
| PERF_ASR | span | the F5 release -> the transcript | turn, chars |
| PERF_TURN | span | the transcript -> the decision | kind, turn |
| PERF_MESSAGE | span | a message's enqueue -> its drain; a wait on a full queue is inside | kind, turn or req or key |
| PERF_LLAMA_REQUEST | span | the request -> the reply, in the app | req, label, ok, cn, pn, pm, gn, gm (pm, gm in ms) |
| PERF_SAM3_REQUEST | span | the request -> the reply, in the app | req, prio, ok |
| PERF_SAM3_PASS | span | the forward pass, in the SAM3 server | req, wait (ms), boxes |
| PERF_DJI_REQUEST | span | the request -> the reply, in the app | path, status |
| PERF_EMERGENCY | span | the stop transcript's receipt -> the POST reply; one span, command to action | turn, status |
| PERF_VISION_GATE, PERF_COUNT, PERF_DESCRIBE | span | one job step | job, result |
| PERF_SAY | span | one sentence on one voice | output |
| PERF_E2E | span | the command -> the action | turn, from, to |
| PERF_FRAME | span | the previous frame's end -> this frame's end | read, draw, show (ms) |
| PERF_GPU | sample | one sample, start = end, once a second | mem (MiB), load (percent) |

The request key `req` joins the app's request record to the server's pass record; `turn`
joins a turn's records to its E2E; a Key message carries a key sequence number. Every
duration inside a payload is in milliseconds. The C++ processes get no stage of their own: they are timed
in the app, request to reply (RVW5).

**The GPU sample.** The pre-mortem asked for queue depths next to the timings; in this design
every queue holds 0 or 1, so only the GPU sample stays (section 4, point 2).

**The Python mapping, honest.** `PerfTimestamp` is `time.monotonic_ns()`. A ring is a
`collections.deque` per thread, without `maxlen`; its append and popleft are documented
thread-safe. The producer checks `len(d) >= 4096` and drops; the length can only fall between
the check and the append, so the deque never exceeds the cap. The drain takes `n = len(d)` once
and pops n records. The ring is a preallocated `bytearray(4096 * 128)`; a record is packed at a
fixed offset with `struct.pack_into` (the C layout, built); the writer reads with
`struct.unpack_from` (section 4, points 3 and 6). A thread finds its deque in `threading.local`; on a miss it creates one and appends it to
the tracer's list under a lock, once per thread. The writer sleeps on an `Event` with the
flush period as timeout; that lock is taken only by the writer and by Destroy, never by a
recording thread, and Python has no atomic bool (section 4, point 7). `PerfCreate` dies when the GIL is off:
`getattr(sys, "_is_gil_enabled", lambda: True)()` (the function exists from Python 3.13).
The measured build is 3.12 with the GIL. The reviewer
measured (2026-10-12, Python 3.12, this machine): a record costs about 330 ns with the deque,
about 210 ns with an index pair, about 960 ns today; building the payload costs more than the
record, so no record site calls json.dumps, and a frame site checks PERF_NONE before it builds
the payload. With `struct.pack_into` no object lives past the call; the two ints from the clock are
transient. The tuple ring was the first proposal; the owner asked for linear memory and no
allocation, so the bytearray ring is the proposal (section 4).

## 9. The tests the module ships with (`test/test_perf.py`)
Change impact: `log/perf_report.py` is rewritten (new file names, start and end instead of ms,
the clock line, the thread key, short payload keys). Its two tests are rewritten, not kept.
- `test_record_from_sixteen_threads_lands_every_record_once`: 16 threads, 4000 records each,
  a flush between batches; the file holds every line, each thread's lines in order.
- `test_ring_overflow_drops_and_writes_a_drop_line`: 5000 records with the writer paused;
  4096 written, 904 in the drop line.
- `test_flush_then_destroy_writes_everything`: records, flush, records, destroy; nothing lost.
- `test_destroy_returns_at_once`: destroy during the writer's sleep returns under 100 ms.
- `test_die_flushes_with_a_timeout`: a write that blocks; die() returns after about 1 s.
- `test_die_hands_over_before_the_flush`: a registered hand-over cleanup runs first.
- `test_payload_over_the_limit_is_replaced_and_parses`: a 200-byte payload lands as
  `"cut":200`; json.loads reads the line.
- `test_e2e_line_keeps_its_timestamps`: the payload is nested; both timestamps are integers.
- `test_writer_disk_error_releases_the_lock_then_dies`.
- `test_create_dies_without_the_gil`.
- `test_report_lists_a_request_with_no_pass`.
- `test_every_stage_payload_fits`: the largest payload per stage, under 104 bytes.
- `test_clock_line_is_first_and_fsynced`: the first line holds the three clocks.
- `test_thread_line_precedes_the_thread_records`: register and record in one drain.
- `test_recycled_thread_ident_gets_a_new_ring`: 50 threads in turn, 50 rings.
- `test_thirty_third_thread_dies`: the reason names the thread budget.
- `test_none_tracer_records_nothing`: `PERF_NONE` writes no file and starts no thread.
- `test_two_processes_merge_by_the_clock`: a child process records with its own tracer; the
  report merges both files in start order, grouped by (pid, thread).
- `test_report_skips_a_torn_last_line_and_names_a_missing_file`.
- `test_report_skips_sample_stages_in_the_table`: a sample stage never enters the table.
- `test_report_percentiles_on_known_values`, `test_report_slowest_frames`: rewritten (C.1, V1).
- `test_record_cost`: 4000 records per batch, the mean under 1 us (the reviewer's number is
  330 ns; the test's bound is set after the first run on the build machine).
