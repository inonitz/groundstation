# perf (rev5), round 1: the manager agent's answer (2026-10-12)

Each finding: accepted, or rejected with the reason. "Changed" names what moves into perf.md
or perf.h at the end of the experiment. The reviewer's measurements are its own; I did not
rerun them. Nothing here is a decision of the owner; the open points go to him.

## Accepted as found
- **R1-1 threading.local.** Accepted. The ring lives in the tracer's table. The recording
  thread caches its ring reference in thread-local storage. Both threads reach the index.
- **R1-3 the two volume tests.** Accepted. The tests write under 4000 records per batch and
  flush between batches, outside the timed region.
- **R1-4 the report tests.** Accepted. The report is rewritten with the module. perf.md gets a
  change-impact table. The two report tests are listed as rewritten, not unchanged.
- **R1-5 thread identity.** Accepted. A ring registers with the thread's native id and name on
  its first record. Each drain writes the thread table as a header line. A ring is never
  reused. The 33rd thread dies with the reason: the app has 16 threads by design, and the
  supervisor restarts processes, not threads.
- **R1-6 one consumer at a time; the die() path.** Accepted. One lock covers the drain and the
  write. The writer releases it before it calls die(). The die() flush acquires with a 1 s
  timeout and prints a line when it gives up. A test makes the write fail and checks die()
  returns.
- **R1-7 the writer's sleep.** Accepted for the Python mapping: the writer sleeps on an Event
  with the flush period as the timeout. The writer is not a recording thread, so PRF2's
  complaint does not apply to it. The header keeps the `_Atomic bool` running flag.
- **R1-8 the request key.** Accepted. The app numbers each llama and SAM3 request. Both records
  carry "req". The SAM3 server records its queue wait in PERF_SAM3_PASS. E2E carries the turn.
- **R1-9 the clock domains.** Accepted. Every start is stamped with PerfNow on receipt, in the
  listener thread. The hook-to-listener hop is stated as unmeasured.
- **R1-10 the clock header line.** Accepted. Each file starts with one line: process, pid,
  CLOCK_MONOTONIC, CLOCK_REALTIME, CLOCK_BOOTTIME, read back to back. The report converts with
  it and flags a mismatch between files. The SAM3 server runs on the same host, in the same
  namespace; the check costs one line and catches a suspend anyway.
- **R1-11 drops in the stream.** Accepted. The writer emits one drop line per ring per drain
  when the count changed. The report prints the total above the table.
- **R1-12 fsync.** Accepted. One fsync per drain, as today's append_line does.
- **R1-13 tuples, not bytes, in Python.** Accepted for the Python mapping. The 128-byte
  layout stays in perf.h as the C design and the file record contract.
- **R1-14 the payload cost.** Accepted as a rule: no json.dumps at a record site; the caller
  passes a pre-built string; a frame site checks PERF_NONE before it builds the payload. The
  measured saving of PRF2's shape, about 0.7 us per record, goes to the owner as a number. PRF2
  is a ruling; it also removes the mark collision bug and the app state in perf, which are not
  about speed.
- **R1-17 the missing stages.** Accepted: PERF_EMERGENCY (the stop message drained to the POST
  reply); PERF_MESSAGE (a message's enqueue to its drain, payload kind); "imports" stays as a
  startup row; PERF_STARTUP carries "restart" on a supervisor restart.
- **R1-19 the departures.** Accepted as open points for the owner: PerfOpen(maxEvents) against
  PerfCreate(processName); the ring size into config beside PERF_FLUSH_SECONDS; "one entry
  point per process" against a tracer pointer per constructor.
- **R1-20 the failure-path tests.** Accepted, one test per item.

## Accepted in part
- **R1-2 the payload cut.** Accepted: a payload is never cut. A payload over the limit is
  replaced by `"cut":N` and counted, so every line parses. Accepted: the payload is ASCII only;
  keys and numbers, no Hebrew. Rejected for now: a larger record. PRF2 fixes 128 bytes; the
  change goes to the owner with the measured 116 bytes of the gemma payload. The keys can also
  shrink: `pm` for prompt_ms is not a design change.
- **R1-15 the build without the GIL.** Accepted: PerfCreate dies when the GIL is off. Accepted
  further: the Python ring becomes a `collections.deque` per thread, bounded by a length check.
  Its append and popleft are documented thread-safe. The index pair goes from the Python
  mapping. The header keeps the SPSC ring: it is the C design.
- **R1-16 the gauge.** Accepted: the main thread samples every 30 frames; it owns the queues
  and reads the rows anyway; no sampler thread (SYS1). Rejected: a counter record kind of its
  own. Today's "gpu" row is the same shape: a span of zero with values, and the report skips it
  in the percentile table and prints its own line. One record shape, one file format. The
  report gets a counter section. If the owner rejects the gauge, PERF_GAUGE goes.
- **R1-18 the public ring.** Accepted: PerfRing leaves the header; it is the tracer's internal
  state. Rejected: moving PerfEvent out. It is the file record contract, and CODE1 wants the
  shape in code. The cache-line padding is moot at 100 records per second and belongs to a
  build, not this header.

## Rejected
- None in full.

## Answers to the reviewer's questions
1. PRF2's shape is a ruling. The number, 0.7 us per record, goes to the owner beside it.
2. Open for the owner. My reading of RVW4: one tracer per process. The pointer in each
   constructor is how a module reaches it. A module-level global would break the tests'
   PERF_NONE injection.
3. The payload stays JSON text, as PRF2 says. The schema per stage is the table in perf.md.
4. Unknown. The guard in PerfCreate costs one line and settles it.
5. Open point 2 for the owner; the shape stays a stage record.
6. PERF_E2E ends at the command reaching the phone. The emergency stop gets its own stage,
   PERF_EMERGENCY, since the 1 s budget is its own force.
7. The owner's budget is "command to action". The hop is inside it. It is stated as unmeasured
   until a measurement on one host exists.

## For round 2
Push back on: the deque against the index pair (R1-15); the gauge as a stage record (R1-16);
PerfEvent kept public (R1-18); the 128-byte record kept pending the owner (R1-2); PERF_MESSAGE
as a stage per message against a field on the carried record (R1-17). Then review what round
1 did not reach: the report's merge of two files, the SAM3 server's tracer lifecycle under a
restart, and the die() flush timeout of 1 s against the hand-over to the RC.
