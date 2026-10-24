# perf (rev5), round 2: the reviewer's push-back and the parts round 1 did not reach (2026-10-12)

Answers round-1-agent.md. Measured on this machine: Python 3.12.3 (GIL build), ext4 on NVMe.
Agreed points from round 1 are not repeated.

## Sources
1. https://docs.python.org/3/c-api/long.html : "The current implementation keeps an array of integer objects for all integers between -5 and 256." Larger ints, such as a monotonic_ns value, are new objects.
2. https://docs.python.org/3/library/collections.html : "Deques support thread-safe, memory efficient appends and pops from either side of the deque." With maxlen set, "when new items are added, a corresponding number of items are discarded from the opposite end."
3. https://docs.kernel.org/trace/ring-buffer-design.html : in producer/consumer mode a full buffer "will lose most recent events"; dropping is "usually with some kind of warning to the user."
4. https://perfetto.dev/docs/reference/trace-packet-proto : packets from different writers arrive "in arbitrary order"; the consumer re-establishes a total order "using the packet timestamps, after having synchronized the different clocks onto a global clock."
5. https://perfetto.dev/docs/instrumentation/track-events : each thread has its own TraceWriter; "Flows can be used to link two (or more) events ... to mark them as related."
6. https://raw.githubusercontent.com/gabime/spdlog/v1.x/include/spdlog/async_logger.h : the overflow policies "block", "overrun_oldest", "discard_new"; the thread pool keeps overrun and discard counters.
7. https://man7.org/linux/man-pages/man2/clock_gettime.2.html : CLOCK_MONOTONIC "does not count time that the system is suspended."

## Findings

**R2-1. die() flushes perf before it hands control to the RC, so a stuck flush delays the hand-over.** (high)
- Claim: runtime/fatal.py runs perf's flush first (`on_die(fn, first=True)`). The accepted R1-6 gives that flush a 1 s timeout. Section 9 says die mid-flight is: the stop, manual mode, notify, then crash.
- Claim: a writer stuck in fsync holds the lock. die() then waits 1 s before the stop is sent.
- Why it matters: the emergency budget is command to action under 1 s (section 8). A 1 s wait spends the whole budget before the stop leaves.
- Evidence: measured, idle disk: one drain of 500 lines, write plus fsync, p50 0.71 ms, p95 0.85 ms, max 1.57 ms over 40 runs. Under GPU and disk load: unverified. The 1 s timeout exists only for the stuck case, and that case is the one that costs the full budget.
- Evidence: "first=True" dates from 2026-09-22 (fatal.py docstring). The hand-over to the RC came later (RVW4). The order was never re-decided.
- Change: die() sends the stop and the manual switch first. The perf flush runs second, then notify, then exit. The perf flush keeps its timeout. A test registers a hand-over cleanup and checks it runs before the perf flush.

**R2-2. The SAM3 server's restart overwrites its file or merges two lives without a boundary, and loses the crashing pass.** (high)
- Claim: the file name is `perf-sam3.jsonl`. A restarted server opens the same name. Opened for write, it truncates the first life's records. Opened for append, the file holds two lives, two pids, two clock lines.
- Claim: the pass that triggered the restart is the most wanted record. A kernel OOM kill or SIGKILL after the graceful timeout skips Destroy. Up to 5 s of server records are lost, including that pass.
- Why it matters: section 9 names "SAM3 out of GPU memory: its process dies and restarts". That is the expected failure of this process.
- Evidence: perf.md section 4 ("the same session folder"; one file per process). The SAM3 pass runs 0.41 to 1.9 s (section 8), so one lost drain window holds 2 to 12 passes.
- Change: the file name carries the pid: `perf-sam3-<pid>.jsonl`. One clock header per file, written and fsynced in PerfCreate, before any record. The app's PERF_SAM3_REQUEST for the failed request carries `"ok":false` and the "req" key. That record lives in the app and survives the kill. The report lists each req with no matching pass.

**R2-3. PerfEvent is not the file record contract; the file is JSON lines.** (high)
- Claim: round 1's answer keeps PerfEvent public "as the file record contract". The file holds JSON lines (perf.md section 4). The Python ring holds tuples (R1-13 accepted). No byte of the file and no object of the Python build has the PerfEvent layout.
- Why it matters: CODE1 wants the shape in code. The shape a reader of the file needs is the JSON line, its keys and its header lines. A 128-byte struct in the header describes a third format that exists nowhere.
- Evidence: the agreed lines: the clock header (R1-10), the thread table (R1-5), the drop line (R1-11), the record. None is described in perf.h.
- Change: perf.h states the file contract as code: one example line per line kind, or a struct per line kind with the JSON key names. PerfEvent moves out with PerfRing, or is marked as the C build's in-memory layout only.

**R2-4. With the "req" key, the gemma payload is 129 bytes: `"cut":N` becomes the normal path of a stage.** (medium)
- Claim: R1-8 adds "req" to PERF_LLAMA_REQUEST. With today's key names the payload is 129 bytes. With short keys (cn, pn, pm, gn, gm, ok as 1) it is 89 bytes.
- Claim: `"cut":N` is right for an unforeseen payload. For a known stage it silently deletes the server timings on every request. The report's rows "of which the server's prompt" and "the server's answer" then vanish.
- Why it matters: those two rows split the plan latency, 0.5 to 1.5 s, the largest step of a turn (section 8).
- Evidence: measured byte lengths above, with realistic values (cache_n 1234, prompt_ms 1234.5, req 123456).
- Change: adopt the short keys now; this is not a design change. Add one test per stage that builds its payload with the largest values and asserts it fits. A cut in a known stage is then a test failure, not a run-time event. The 128-byte question still goes to the owner with both numbers.

**R2-5. The report's merge: unsorted files, a torn last line, a missing file, and the thread key.** (medium)
- Claim: a ring is drained in record order. A record is written at its end. A long span starts before a short span recorded earlier. So each file is not in start order either. The report must sort all records, not merge sorted files.
- Claim: a kill can leave a partial last line, for example on a full disk. Today's report calls json.loads on every line and stops on the first bad one.
- Claim: SAM3 off, or a server that died before its first drain, leaves no file or a header-only file. The report must say so, not fail.
- Claim: the thread index is per process. Two files both have index 0. The merge key is (pid, index).
- Why it matters: C.1: the report is where every number is computed. One torn line must not hide a run.
- Evidence: Perfetto states that packets of different writers arrive "in arbitrary order" and the consumer re-orders by timestamp (source 4). log/perf_report.py report(): `rows = [json.loads(line) for line in fh ...]`.
- Change: the report reads every `perf-*.jsonl`, converts each record by its file's clock header, sorts by start. It skips a final unparseable line and prints a count. It prints one line per expected process with no file. Records group by (pid, thread index). A test feeds a torn last line and a missing SAM3 file.

**R2-6. The thread table line needs a format and an order.** (medium)
- Claim: the agreed "thread table as a header line of each drain" has no format. A thread registered and drained in the same drain must have its table entry before its records. A thread's name can change after start; the name at first record is the one written.
- Why it matters: without the order, the report meets an index it cannot name.
- Change: each drain writes, in order: the table line, the drop lines, the records. The table line is one JSON object, for example
  `{"threads":[[0,412233,"MainThread"],[1,412240,"recognizer"]],"pid":412233}`.
  It lists only rings new since the last drain, so 16 threads cost one line once. A test registers a thread and records in the same drain, then checks the table line precedes the record.

**R2-7. The deque per thread: agreed, with three conditions on the drain and the drop count.** (medium)
- Agreed: the check `len(d) >= cap` then append has no harmful race. The ring has one producer. The consumer only removes. Between the check and the append, the length can only fall. The deque therefore never exceeds cap.
- Condition 1: no `maxlen`. A deque with maxlen discards from the opposite end, which is overrun-oldest with no count (source 2). The design chose drop-new (source 3; source 6, discard_new).
- Condition 2: the drain takes `n = len(d)` once, then pops n items. A `while d:` loop races a fast producer and may never end.
- Condition 3: the drop count is a monotonic counter. Only the producer increments it. The writer keeps the last value it saw and writes the difference. A writer that resets the counter does a read-modify-write from a second thread, and loses counts.
- Evidence: measured: the capped deque append costs 328 ns per record with two PerfNow calls, against 214 ns for the index-pair ring. The 110 ns is not worth the index pair's code.

**R2-8. PERF_MESSAGE as a stage: agreed, if it carries the turn key and a stated start.** (medium)
- Agreed: a record per message is fine at under one message per frame (section 4). A field on the carried record would miss messages that end no turn.
- Condition 1: the start is stamped by the producer before put(). The bounded queue's put may block when full. State whether that wait is inside the span; today it would be.
- Condition 2: the payload carries the kind and the "req" or turn key. Without it, the report cannot add a turn's queue wait to that turn's E2E (source 5, flows).

**R2-9. The gauge as a stage record: agreed, if the report excludes it by a flag, not by name.** (low)
- Agreed: one record shape keeps one file format. Today's "gpu" row is the precedent.
- Condition: the stage table in perf.h marks each stage as a span or a sample. The report skips samples in the percentile table by that mark. A test adds a sample stage and checks it never enters the table. Today's report skips "gpu" by a string compare; a new sample stage would leak in.

**R2-10. In Python, every record allocates; PRF2's "dynamic allocation" bullet cannot be met by the deque or the tuple ring.** (low; for the owner, not a design fault)
- Claim: each record creates a tuple and two int objects. A monotonic_ns value is far above 256, so it is never a cached int (source 1). The deque also allocates a block per 64 items.
- Claim: only struct.pack_into into a preallocated bytearray keeps no new live object per record (measured: 0.0001 live blocks per record, against 1.2 for the tuple ring). It still allocates the two ints transiently.
- Why it matters: PRF2 lists dynamic allocation as a fault of today's perf. The accepted Python mapping keeps it. The owner should hear that, with the cost of the alternative (115 ns per record, R1-13).
- Change: perf.md section 5 states it in one sentence: the allocation-free property holds in the C design only.

## Questions for the manager agent
1. R2-1: may die()'s order change to hand-over first, perf second? That reverses the 2026-09-22 "perf registers first".
2. R2-2: is a pid in the SAM3 file name acceptable, or does the owner want one file per process name with segments?
3. R2-3: what does perf.h state as the file contract: example lines, or one struct per line kind?
4. R2-4: may the short payload keys go in now, with a size test per stage?
5. R2-8: is the time a producer blocks on a full message queue part of PERF_MESSAGE, or recorded apart?
6. R2-10: does the owner accept that the Python build allocates per record, or does he want pack_into for that reason alone?
