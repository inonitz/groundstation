# The recorder: the history of the rounds (a dated record, moved out of recorder.md on 2026-10-24, RCD72)

**FROZEN.** These sections were the record of the review rounds of 2026-10-18 to 2026-10-22. The owner approved moving them out of recorder.md (2026-10-24: "I trust you. Approved."). recorder.md section 2 is the design's truth; nothing here is current where it differs.

## 4. The open points for the owner: the four of 2026-10-18 closed (RCD2); every item of the decision document closed and applied on 2026-10-22
| point | the owner's words | the result |
|---|---|---|
| OPEN 1, the timestamp type | "Agree. APprove" | `MonotonicNs` and `MonotonicNow()`; one sed over the rev5 headers at the fold |
| OPEN 2, one file per process | "Doesn't seem wrong to me, approve." | record-<process>-<pid>.jsonl, every line with its kind |
| OPEN 3, the GPU sample | "Approved." then: "Is the GPU Sampling different to the way we should sample CPU side code?" then (RCD4): "What is the point of differentiating between samples? ... HOw does it differ from the profiling spans? Each individual datapoint is required to build a span, then record it! Make up your mind!" | no sample contract. A span is a duration of our code between two MonotonicNow() reads. The GPU's memory and load are two gauges read from the driver at one instant: that would be an event, not a sample; the GPU gauges were then DROPPED altogether (RCD19 item 7, RCD34 B1). Nothing is timed on the GPU side; a span around a call that returns the result (SAM3's detect) already includes the GPU work. Three contracts, three data shapes |
| OPEN 4, the fold | "Yes, I agree. The focus should still be on this module, alongside the decisions made along the way from both modules, yes." | perf.md and telemetry.md fold into this document after its approval: their decisions, measurements and tests; the two folders and the nine helper headers go |

Two more rulings of the same review. A struct for a frame and one for its size ("there should
be a dataclass for Frames, also for their sizes"): `FrameSize` and `FrameView` are in
`frame_types.h`, and RecordFrame takes one `FrameView*` ("Why not take a struct and call it a day?").
The drawing `recorder.html` ("Please also create an html diagram").
`FrameSize` has one home, `frame_types.h`; the frame buffer's own copy goes at the fold (carried).

**R4, the field survey applied (the owner, 2026-10-19: "Alright. Finally you're speaking some
sense. Approved! Go! be thorough with your design").** Section 10 holds the survey. The five
changes: one bounded queue per thread (a byte ring then; a deque of tuples since PY3, by
measurement), no record refused (a text past the bound is cut, RCD12); typed fields with their names passed by the hot path, the JSON
made by the writer; a half-full wake per queue; the time reference line re-emitted at every fsync; the drop
line with the gap's first and last time.

**Changes against the approved perf and telemetry contracts (gate item 12: the owner reads
them once, here).** Found by the one-round review (R1-13); each is a decision, not a drift.
| change | approved | here | why |
|---|---|---|---|
| the file names | perf-<process>-<pid>.jsonl, trace.jsonl, meta.json | record-<process>-<pid>.jsonl; the info line inside it | OPEN 2, approved 2026-10-18 |
| Destroy's drain | the caller drains under a drain lock (perf) | the writer alone drains; Destroy and FlushInDie set STOPPING and wake it; Destroy waits then joins; FlushInDie waits and never joins | one consumer per queue, one writer per file (R1-5) |
| a late record after the last drain | counted as a drop (perf) | dropped and counted, like any record outside RUNNING (RCD34 B2); the queues and the pools are empty at STOPPED | no second consumer (R1-5) |
| the record's shape | 128-byte spans, 4096-byte events, a payload over the limit replaced by {"cut":N} (perf, telemetry) | one record per queue entry (a tuple in Python; in C a slot plus a byte area), at most 8 KiB (RCD36), 16,384 entries per queue; a text that does not fit is cut at a character and the record gains "cut", the bytes lost (RCD12, RCD36, RCD37); a record is never refused for its text (R3-2: 12 of 845 recorded passes carry a detection list over 2047 bytes) | the field: eBPF, Perfetto, LTTng, NanoLog write in place (R4) |
| the payload | a JSON string built by the caller (perf, telemetry) | typed fields with their names as string literals (K1); the writer makes the JSON | NanoLog, ULog: numbers on the hot path, text offline (R4) |
| the writer's wake | (see below) | plus: a queue past half full notifies it once per crossing | perf's watermark, OpenTelemetry's half-full wake (R4) |
| the time reference line | once at Create (perf) | again at every fsync | Perfetto's clock snapshots (R4) |
| the drop line | a count per ring (perf) | the count and the gap's first and last time | ULog's dropout duration (R4) |
| the pool buffer's state | one in-use flag (telemetry) | no ownership state per buffer: an index is on the free list, on the work queue, or held by the thread that took it (RCD9); a buffer carries only its own data, the stamps and the PNG-written mark | the writer never encodes a half-copied frame (R1-2) |
| the frame line | none; the event names the PNG | a frame line after the PNG attempt, ok true or false; the event's png key is the request | the full disk that was seen (R1-7) |
| a short write | pause, count, resume (telemetry) | ftruncate to the last whole line; the record stays at the front of its queue and the pass ends; the next pass retries it; the unlink of a half PNG; no pause, no copy (the owner, 2026-10-22, replaces W1) | no torn line mid-file (R1-6) |
| the writer's wake | a 10 ms poll, 50 ms when idle (telemetry); a 5 s sleep on an Event (perf) | one condition variable with a remembered notify: a filled buffer, a queue past half full, Destroy or Die wakes it; a 5 s timer otherwise; no poll; the object (OsEvent) is carried to runtime_internal.h; no measured rate reaches the watermark (R3-4), it stands on R4 | the owner, RCD6: "Why is the recorder polling?" |
| one write per drain | one write and one fsync per drain (perf) | one write per line, about 250 a drain; a short write truncates to the line's start | the torn-line rule needs line granularity (R2-15) |
| FlushInDie on the writer's own thread | appends once (telemetry) | returns at once; the writer's last pass writes what it can | one thread never joins itself (R2-10) |
| the mask pool | the frame pool times the perception's mask limit (telemetry) | the same: 8 times 3, 24; the design's constant, read from config/ in Python | restored (R2-15) |
| the stall rule | computed at read from atomics (telemetry) | the same, frames only: a filled buffer older than 5 s past the writer's last progress, its fill time read from the pool itself (BufferPoolOldestFilledAt); spans and events wait for the timer by design | R2-4 |
| the 17th recording thread (TEL2: "no die after start") | the thread past the cap is dropped and counted (telemetry, TEL11) | it dies: a bug of ours, found at once | RVW4, RCD19 item 2 |
| a record before Create (RCD34 B2 "any state but RUNNING is dropped and counted") | (a ruling on Destroy) | NOT_CREATED returns NOT_CREATED and counts nowhere: no instance exists to count in | closed: "can you record something when you don't exist yet?" (2026-10-22) |
| the "one event" per fault (TEL2) | the sink writes one event when it degrades (telemetry) | the writer writes a fault line (LINE_FAULT) at the end of a pass in which a counter or flag changed; never a record call, since that would be a recursive call into the queues it drains | the owner, 2026-10-22: "the fault line is approved" (T1) |
| the pool's lock (RCD27 "under one lock") | one lock over the slot pool (telemetry) | two index queues, the free list and the work queue, each under its own lock, as the util type carries one | the owner, 2026-10-22: "Lock it is" (RCD50) |
| the loop of drawing 2 (RCD30: arrows into step 2 "yes" and step 1 "no") | (a drawing ruling) | one return arrow into step 1: the reset lives in step 1, and a set remembered during the pass ends that sleep at once; no end-of-pass check exists (the "yes into step 2" form skipped the reset and looped forever, found by the second blind check) | the owner, 2026-10-22: "P3 - Good" |
Unchanged and restored where the first draft had drifted: the thread cap as the design's count, 16 (PRF5), the cut
rule with "cut":N (PRF4, now on a text field), the ring per thread (allocated at Create since 2026-10-22).

**Draft 9 (2026-10-19, RCD13 to RCD15): the two blind reads applied.** Two readers rebuilt the
design from the headers alone, one with the comments and one without (test/recorder-review.md,
"The blind read" and "The second blind read"): 72 % and 65 %. What they could not get, and the
fix for each. HISTORY: these rows say what draft 9 changed at the time; where a name or a number
below differs from the headers of draft 15, the headers are the truth (the registers, the packed
layouts, the 15-field cap, the "nine parts" and the byte ring were all removed later by K1,
RCD17, RCD20 and RCD23; see sections 2 and 7):
- The owner could not read six names. Draft 9 renamed them (Register for Intern, the Packed*
  headers, RegisteredNames); K1 and RCD23 then removed registration and the packed layouts
  altogether. What stayed: RecordingThread (one thread's queue, not a ring of threads);
  ThreadProducer; MonotonicNs and MonotonicNow, so the clock is in the type; SPAN_QUEUE_MESSAGE.
- The instance was twenty fields. Draft 9 made it nine named parts (1360 bytes); draft 14 has
  seven: the state, the process name, the session folder, the file, the frame pools, the writer,
  the counters (RCD23; 1408 bytes measured by the round-2 consistency check).
- The file was in prose only. `record_file.h` holds the file name pattern, the PNG path pattern,
  every line kind, every key, and the stage name table. The writer and the readers share it.
- Fourteen defects the reads found, each fixed at the time (D1 and D11 were superseded by RCD23
  and RCD25; D6's 15 fields by RCD17's 31): the held line kept its thread and the run stayed in
  the ring until written (D1); drops of a thread without a ring were counted in
  the thread table (D2; superseded: every entry and queue exists from Create, 2026-10-22), and a claim at the cap dies; Destroy's deadline is now plus its timeout,
  so the pending frames are encoded (D3); a failed ring Init was tried once (D4; superseded: everything is allocated at Create, 2026-10-22); the ring keeps
  its run bound (D5); the caller got 15 fields and the recorder one cut field (D6; 31 since RCD17); the stall rule read two atomics the writer stored at each pass end (D7; superseded: the pool answers the oldest fill time, 2026-10-22); the review wrote D8 as "only Die writes the deadline"; draft 14 had Destroy by a compare-and-swap and Die unconditional; since 2026-10-22 the stop request stores the reason, the deadline and STOPPING under the state lock, whoever comes first (D8, superseded); one more fsync after the last frames (D9); a folder and a name are checked for
  separators, ".." and length, and a PNG is opened exclusively, a clash counted (D10); the packed
  bool is a uint64 of 0 or 1 (D11); Create reset every thread's announced flag (D12; superseded: one Create per process, 2026-10-22); degraded
  is two flags, last write failed and under reserve, each with its recovery (D13); the stale comment
  gone (D14).
- The twenty-three unanswered questions, answered in the headers at the time (the registration
  answers went with K1; the run and the reserved byte with RCD23; the line cut with RCD36): a
  BGR24 view goes to the frame pool and a GRAY8 view to the mask pool; INVALID_ARG covers the
  size, the stride, the format and a bad folder or name; a record while STOPPING or STOPPED is
  dropped and counted (before Create: NOT_CREATED, counted nowhere, 2026-10-22); the record bound covers the whole record (8 KiB since RCD36); the drop
  stamps are MonotonicNow() at the drop; the free check counts lines; a thread names itself by
  RecorderNameThisThread, else "thread-N"; the thread cap; NaN and infinity are null; a failed
  PNG write is unlinked and counted; the wake-up set takes the event's own lock once per
  crossing; the reserve as a function.


## 5. Today
log/perf.py (208 lines: a dict per event, a lock in record, marks by name that two threads
overwrite), log/session.py (265), log/disk.py, log/session_files.py, log/show.py. Two modules,
two lifetimes, two files, two readers. The vision pass encodes a JPEG on the job thread. The
perf and telemetry documents (sections 5) list every fault; nothing here is new.


## 8 (history). The notes that moved out of the why notes
- **Why a byte ring was designed, then dropped (R4, then PY3).** The field writes
  variable-length records in place (eBPF, Perfetto, LTTng, NanoLog), so R4 designed one byte
  ring per thread with reserve and commit, runs rounded to 8 bytes and a padding run before the
  end. In Python every one of those steps is interpreted: 646 ns against 150 for a tuple in a
  deque. The ring stays in the C header as the embedded form; the Python build takes the deque.
- **Why the pool is a buffer pool with a free list and a work queue, not a state array.** The first draft had a per-buffer state with a compare-and-swap in C and a deque in Python: two different mechanisms for one model. The honest model is the field's: a fixed set of buffers, a free list, a work queue. A buffer in neither queue belongs to the thread that holds it, so no per-buffer state exists. Eight threads at three takes a second need no lock-free queue; a lock held for one deque operation is the house default, and the lock-free form measured forty times slower in Python (RCD50). C and Python say the same thing.
- **Why there is no sample contract, and no GPU record.** The first draft had a sample for the GPU gauges. The owner asked what it adds over a span and an event: nothing, a gauge read at one instant is an event. He then dropped the GPU gauges altogether (RCD19 item 7; RCD34 B1: "Not relevant"). Nothing is timed on the GPU side: a span around a call that returns its result on the CPU includes the GPU work.

## 10. The field, surveyed (2026-10-19, the owner: "Reflect on the SOTA ... figure it out")
Twelve designs read at their source. The table says what each one does on the seven questions that
decide a recorder. "us" is this document before the survey.

| question | the field | us |
|---|---|---|
| where a record is written | a per-thread staging buffer, single producer, one background consumer: NanoLog, Tracy, Perfetto (one TraceWriter per thread), LTTng (per-CPU), Quill | the same |
| the record's shape | VARIABLE length with a small header, rounded: eBPF ringbuf (an 8-byte header: length, busy, discard; every record rounded to 8 bytes; its pages mapped twice so no padding), Perfetto (proto packets in 4 KB chunks), LTTng (padding at a sub-buffer's end), NanoLog (compact binary), perf_event (a header per record) | fixed 128 and 4096 bytes; a payload over the limit is cut |
| how the producer writes | reserve, then write IN PLACE, then commit: eBPF ("avoids the extra copy of memory by providing a memory pointer directly to ring buffer memory"), LTTng, Perfetto ("directly serialize ... onto it"), NanoLog | build a struct, then copy it into the ring |
| what the hot path formats | numbers only; the text is made offline: NanoLog ("deferring formatting to an offline process", 7 ns median), ULog (binary, a decoder), Perfetto (protos, registered strings), LTTng (CTF binary) | a JSON string built by the caller before the call |
| static information | written once, referenced by id: NanoLog's dictionary, Perfetto's registering ("emitted only once and later referred to using a monotonic ID"), ULog's definitions section, LTTng's metadata | the time reference line and the thread line once; the stage name as text in every line |
| loss accounting | in the stream: LTTng's lost-events count per sub-buffer, Perfetto's previous_packet_dropped per sequence, perf's PERF_RECORD_LOST, ULog's dropout message with a duration, rosbag2's drops per topic | a drop line per ring with the count |
| the wake of the consumer | adaptive: eBPF notifies only when the consumer caught up; perf wakes at a watermark; OpenTelemetry exports at a timer or early at a batch size (512 of a 2048 queue) | a frame wakes; spans never; a 5 s timer |
| the fill policy | discard-new for a profiler (LTTng discard, Perfetto DISCARD, OpenTelemetry drops at maxQueueSize 2048); overwrite-oldest for a black box (Perfetto RING_BUFFER, perf read-only) | drop-new, counted (TEL7) |
| the file | self-synchronizing: ULog's sync message and "parsers must handle logs that end abruptly"; Perfetto's atomic packets | newline-delimited JSON; a torn tail skipped; ftruncate keeps the middle whole |
| the clock | re-sampled during the run: Perfetto's ClockSnapshot packets (Tracy calibrates once at start) | one clock line at Create |
| frames | compressed off the hot path with size limits: Tracy's frame images on their own thread; rosbag2's double-buffered cache, drops counted | pools, PNG in the writer, drops counted |
| the false-sharing of head and tail | padded to the cache line, with cached copies of the other index: rigtorp, Disruptor (56 bytes each side), eBPF (separate pages) | padded since RCD9; no cached copies |
| shutdown | a bounded flush: OpenTelemetry ForceFlush and Shutdown "SHOULD complete or abort within some timeout"; OnEnd "should not block or throw" | the same |

**What holds.** The shape is the field's: per-thread single-producer rings, one writer, per-process
files, loss counted in the stream, a remembered notify, bounded shutdown, frames off the hot path. Two
things are beyond most of the field: the health counters as a status row the operator sees (the
OpenTelemetry processor drops silently), and the file opened exclusively with a torn-line rule.

**What is below par, and the change for each.**
(The five changes as R4 made them, HISTORY. Change 1 was superseded by measurement, PY3: the
Python build stores a tuple in a bounded deque; the C header keeps a ring of record slots as the
embedded form; and RCD12 restored the cut rule, so "no record is ever cut" below is not the rule.
Change 2's registered keys and definitions preamble were removed by K1: the names travel as
literals and the writer formats them.)
1. Fixed-size records, built then copied. The field reserves space in the ring and writes in
   place, with a length header. Change: ONE byte ring per thread (not two), variable-length
   records, reserve then commit. No record is ever cut. The span ring and the event ring merge.
2. The hot path formats JSON. The field packs numbers and formats offline. Change: a record's
   payload is typed fields with registered keys: a key id, a type byte, a value. The owner's helper
   header defines its key ids; the names are written once in a definitions preamble; the WRITER
   turns records into the JSON lines the readers already expect. The measured 437 ns of a Python
   span is mostly the f-string; the pack of three numbers is well under 200 ns (unverified until
   built).
3. No watermark wake. A burst of 4096 spans in 5 s drops. Change: the producer sets the wake-up
   object when its ring crosses half full. A notify is one store when already remembered.
4. One clock line. Change: the writer re-emits the time reference line at every fsync, so a stepped
   wall clock is visible in the file.
5. The drop line carries a count. ULog carries a duration. Change: the producer keeps the first and
   the last dropped timestamps; the drop line shows the gap. Cheap, and it tells the reader WHEN.
Kept on purpose against the field: drop-new rather than overwrite-oldest (a queue holds 5 s of
records in normal flow, minutes at its bound; overwrite needs lap detection); JSON lines on disk rather than a binary file (one reader, no
decoder tool; the hot path no longer pays for it under change 2); per-process files rather than a
central service (no shared-memory arbiter; the owner's ruling).

**Sources.** Perfetto buffers and dataflow (perfetto.dev/docs/concepts/buffers); the BPF ring
buffer (docs.kernel.org/bpf/ringbuf.html); NanoLog (USENIX ATC 2018; github.com/PlatformLab/NanoLog);
LTTng channel modes (man lttng-enable-channel); the ULog file format (docs.px4.io/main/en/dev_log/
ulog_file_format.html); rosbag2 MessageCache (rosbag2_cpp/cache/message_cache.hpp); the
OpenTelemetry trace SDK spec, the batching processor (opentelemetry.io/docs/specs/otel/trace/sdk);
perf_event_open(2), the mmap layout; rigtorp SPSCQueue (github.com/rigtorp/SPSCQueue); the LMAX
Disruptor; the Tracy manual (github.com/wolfpld/tracy, manual/tracy.tex).

