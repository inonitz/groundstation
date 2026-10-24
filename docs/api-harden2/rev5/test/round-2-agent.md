# perf (rev5), round 2: the manager agent's answer (2026-10-12)

All ten findings are accepted. Two of them change an earlier decision and go to the owner.
The revised perf.md and perf.h carry every accepted change; round 3 reviews the revision.

- **R2-1 die() order.** Accepted. The hand-over to the RC runs first: the stop, then manual
  mode. The perf flush runs second, with its 1 s timeout. Then notify, then exit. This reverses
  the 2026-09-22 order "perf registers first". Open point for the owner.
- **R2-2 the SAM3 file under a restart.** Accepted. The file name carries the pid:
  `perf-sam3-<pid>.jsonl`. PerfCreate writes and fsyncs the clock line before any record. The
  app's request record carries `"ok":0` and the request key when the reply never came.
- **R2-3 the file contract.** Accepted. perf.h states the four line kinds as structs with the
  JSON key names: the clock line, the thread line, the drop line, the record. PerfEvent is
  marked as the C build's in-memory layout. PerfRing leaves the header.
- **R2-4 the short keys.** Accepted now. One size test per stage, with the largest values.
- **R2-5 the report's merge.** Accepted: read every file, convert by its clock line, sort by
  start, skip a torn last line with a count, name a missing process, group by (pid, thread).
- **R2-6 the thread line.** Accepted, with the given format and order: the thread line, the
  drop lines, the records; only rings new since the last drain.
- **R2-7 the deque.** Accepted with the three conditions: no maxlen; the drain pops a counted
  n; the drop counter is monotonic and only the producer writes it.
- **R2-8 PERF_MESSAGE.** Accepted. The producer stamps before put(). A wait on a full queue is
  inside the span, on purpose: it is real latency on the path. The payload carries the kind and
  the turn or request key.
- **R2-9 span or sample.** Accepted. The stage table marks each stage; the report skips samples
  by the mark.
- **R2-10 allocation in Python.** Accepted as one sentence for the owner: the allocation-free
  property holds in the C design only; pack_into would buy it for 115 ns per record.

## Answers to the reviewer's questions
1. Open for the owner, recommended yes: the hand-over first.
2. The pid in the name. Segments are a second mechanism for the same thing.
3. One struct per line kind, with the JSON key names.
4. Yes, now.
5. Inside the span, stated in the stage table.
6. Open for the owner, with both numbers.

## For round 3
The revised perf.md and perf.h. Check that every accepted change landed, that the document and
the header agree, and that nothing new contradicts a ruling. List what stays open for the owner.
