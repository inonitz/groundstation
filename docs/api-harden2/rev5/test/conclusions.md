# The review experiment on perf: conclusions (2026-10-12)

Three rounds, one reviewer (general-purpose agent, model Opus 5.5; the tool sets no effort
level), 38 findings: 20, 10, 8. Every finding was accepted in full or in part. None was
rejected in full. The reviewer measured on this machine where a claim rested on a number.

## What changed in perf.md and perf.h because of the experiment
- The Python mapping was wrong: a thread-local write index is invisible to the writer. Now
  a deque per thread, found through a thread-local reference, drained by a counted pop.
- A payload is never cut: a longer one is replaced by `{"cut":N}`; the keys are short; one
  size test per stage. The payload is nested under `p`, so no key collides with the record.
- The file has a contract in code: the key `k` per line; the clock line first, fsynced; the
  thread line; the drop line; the record. The stage text is lower case without PERF_.
- The file name carries the pid, so a restarted SAM3 server never overwrites its first life.
- One consumer at a time: one lock around the drain and the write; the writer releases it
  before die(); die()'s flush has a 1 s timeout.
- Drops are written in the stream per drain, not printed at close.
- One fsync per drain. A clock line with CLOCK_MONOTONIC, CLOCK_REALTIME and CLOCK_BOOTTIME
  per file; the report converts and flags a suspend or another time namespace.
- The report sorts every record of every file by start; it skips a torn last line; it names a
  missing process; it groups by (pid, thread); it skips sample stages by a mark.
- New stages: PERF_MESSAGE (enqueue to drain), PERF_EMERGENCY (the transcript's receipt to the
  POST reply). Join keys: `req` for requests, `turn` for turns, `key` for keys.
- No sampler thread: the main thread records the gauge every 30 frames (SYS1).
- Thread identity: native id and name in the thread line; a ring is never reused; the 33rd
  thread drops and counts after start-up.
- The die() order mid-flight: stop, manual, notify, flush, exit (open point 5).
- The tests: 23 named, each after a behavior; the report tests are listed as rewritten.

## What stayed open for the owner (perf.md section 5, eight points)
1 the stage enum; 2 the gauge; 3 the 128-byte record; 4 PerfCreate(processName) against
PerfOpen(maxEvents) and "one entry point per process"; 5 the die() order; 6 allocation per
record in Python; 7 the Event in the writer; 8 the 33rd thread.

## What the experiment showed about the method
- The reviewer found a critical fault in the Python mapping that the design document and
  the header could not show: the mapping must be reviewed as code, not as prose.
- Measurements settled four arguments in minutes (the payload sizes, the record cost, the
  thread id recycling, the clock across processes).
- Rounds 2 and 3 cost less than round 1 and found the contract faults (the key collision,
  the restart overwrite). Three rounds were enough; the reviewer said no round 4.
- Cost: about 405k subagent tokens for the three rounds.
