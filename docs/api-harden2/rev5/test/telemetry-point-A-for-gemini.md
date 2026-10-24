# Telemetry write path: the design, explained from scratch (for an outside reviewer, 2026-10-16)

## The system
A Python 3 drone ground station. One process, about 21 threads. A main thread draws the screen
every 33 ms and owns all app state. Eight worker threads run vision jobs: each job sends a
1280x720 BGR frame to a SAM3 server (a separate process) and gets boxes back, 0.4 to 1.9 s per
pass, at most 3 passes a second in all. One emergency thread sends the stop command. Frames
live in a shared-memory buffer of 32 slots with a reference count each; a job holds its slot
while SAM3 works on it and must release it right after.

## What telemetry must do
Write a replayable record of the run to disk: every turn (what was heard, decided, sent,
said), every vision pass with its frame, boxes and masks, every job's start and end, and the
events (keys, stops, manual mode, drops). Constraints: the main thread never blocks; a job
never holds its frame slot for the record; the frames must be lossless, because the replay
re-runs SAM3 on them; the module never terminates the app, whatever the disk does; the app
has no exceptions (status returns only).

## The design
Ten threads record: the main thread (turn, job, event lines, about 2 a second), the
emergency thread (the stop and its reply, rare), the eight job threads (one pass line each, 3
a second in all, plus the frame and up to 3 masks per pass).

Each recording thread owns one ring of 256 preallocated event records. The thread writes it;
one writer thread reads it. One writer and one reader per ring: no lock, no shared index. A
full ring drops the new event and increments a counter; the caller returns at once.

Two pools hold pixels: 8 frames of 2.6 MiB and 24 masks of 0.9 MiB, preallocated at start
(43 MiB). A job thread copies its frame and masks into them during the call (0.18 ms per
frame, measured) and then releases its shared-memory slot. A full pool drops the frame,
increments a counter, and the pass line records that the frame is missing.

One writer thread is the only consumer. Its loop: drain each ring, writing one JSON line per
event to trace.jsonl, which stays open; take a frame or mask from a pool, encode it as a
lossless PNG at compression level 1 (38 ms, measured; the encoder releases the GIL), write it
as a new file, free the pool slot; every 5 s, flush and fsync trace.jsonl (0.6 ms); every 100
records, read the free space and pause when it is under the reserve; on a failed write,
count it, pause, and retry later; when idle, sleep until work arrives. At 3 passes a second
the thread is busy about 12 % of the time. It never calls the app's die().

Six counters report back, one per cause: dropped events (a ring was full), dropped frames
(a pool was full or the size was wrong), failed writes (the disk refused), stalled (work is
pending and nothing finished for 5 s), degraded (the writer is paused), free space. Each has
one writer and one reader, so each is an atomic store. The main thread reads them every
frame, like a status row, and prints a chat line when one changes.

The disk: trace.jsonl holds every line with a topic key (turn, job, pass, event, health).
Each frame or mask is one PNG under perception/<job>-<kind>/. A reader skips a torn last
line or a torn PNG. At full load the PNGs cost about 12 GB an hour; the start check refuses
to run when less than one busy hour of space is free, computed from the frame size, not
fixed for one machine.

## Why these choices
- A ring per thread, not one shared queue: no lock on the recording path; the same shape the
  app's perf tracer already uses.
- Pools and a copy, not holding the frame slot until written: the frame buffer has 32 slots
  for the whole app; a stalled disk must not hold any of them.
- One writer thread: a disk write can block for seconds; one consumer keeps every ring
  single-reader; the main thread is never on the disk path.
- Drop and count, never wait or die: the record is observability; a bad disk must not
  ground the aircraft; the counters make every loss visible.
- fsync the trace every 5 s, never the PNGs: an app crash loses nothing written (the kernel
  keeps the page cache); only a power cut loses data: under 5 s of lines and the PNGs not
  yet written back by the kernel's own timer (about 35 s). An fsync per file would be up to
  10 per pass, 30 a second, each forcing the drive to flush its cache.
- PNG, not JPEG: PNG is lossless; the replay feeds SAM3 the exact frame it saw. JPEG at
  quality 95 was 2 ms and 0.25 MB but changes pixels; lossless WebP was 300 ms, too slow.

## The one open question
Is "fsync the trace every 5 s, never the PNGs" the right durability for this record, given
that an app crash loses nothing and only a power cut loses up to 5 s of lines and 35 s of
frames?
