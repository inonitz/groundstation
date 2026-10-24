# The review experiment on telemetry: conclusions (2026-10-12)

Three rounds, one reviewer (general-purpose agent, model Opus 5.5; the tool sets no effort
level), 41 findings: 20, 11, 10. Every finding was accepted. None was rejected. The reviewer
measured on this machine where a claim rested on a number, and simulated the stall rule.

## What changed in telemetry.md and telemetry.h because of the experiment
- The main thread never waits: its records go on an unbounded queue; a stall is detected
  from the writer's progress (queued, written, last finished, pending since), never by a
  blocked main thread. The first draft blocked every caller up to 5 s.
- The file contract is in the header, one place: every file and every key; the endings; the
  write order (files, then the line); a reader skips a torn last line. The first draft said
  "the files stay as today", which the replayer's reads disproved.
- Telemetry owns its box and mask types; the logger builds its own record and never keeps
  the caller's object; the Python frozen dataclass was shown to freeze nothing inside it.
- Masks are PNGs encoded on the writer (3.4 KB, 1.6 ms) after a measured 6.3 MB, 16.7 ms
  JSON path that stalled the main thread's sleep to 20 ms.
- A turn is written twice (decided, ended) and a job twice (started, ended), so a crash keeps
  the record in flight. A fourth call, RecordEvent, records the stop, the keys, manual mode,
  the dropped sentence, the status changes, the end and the die reason.
- The directory fsync after each rename; a free-space floor at Create and a low-water event;
  passes.jsonl per job instead of a json per pass; the pid-free folder `<job:04d>-<kind>`.
- No clip rename: the mic listener carries the clip name; the exact join is a precondition
  of the speech-in module.
- Destroy joins with a timeout and dies past it; the writer's own failed write attempts one
  direct append of the die line.
- The vocabularies are constant tables; a value outside one dies.
- Items carried to later modules: the ASR clip name in the transcript; the fixed frame
  geometry; the die() order in runtime; three statements of the design document for the
  app step.

## What stayed open for the owner (telemetry.md section 4, thirteen points)
1 the main thread never waits; 2 a stalled disk is a broken disk; 3 RecordEvent; 4 two lines
per turn and job; 5 the new file keys and the replayer; 6 no clip rename; 7 the free-space
floor and the low-water mark; 8 what happens under the mark; 9 the copy on the caller; 10
JPEG; 11 masks as PNG; 12 a mask is 0 or nonzero; 13 the stop's reply as a PlatformReply.

## What the experiment showed about the method
- Round 1 overturned two of the five first-draft open points (the bounded wait, the files
  unchanged) and found the deep-copy contract unimplementable as written.
- Round 2 found the heartbeat's false positive on an idle writer; round 3 found the next
  rule's false positive on the first record after a pause, by simulation. Two rounds were
  needed for one rule; a third was needed to catch the fix.
- Cost: about 545k subagent tokens for the three rounds.
