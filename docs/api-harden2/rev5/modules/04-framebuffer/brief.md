# Brief: the frame buffer design agent (harden2 rev5, module 4)

The owner asked for this file on 2026-10-17 ("prepare their prompts and files"). It is the
agent's handoff document: the brief on top, the progress log at the bottom. The agent updates
the log at every checkpoint. The manager agent reads the log and every file this agent writes.

## 1. Your job

Design the frame buffer of harden2 and deliver two files the owner can review in 15 minutes:
`framebuffer.md` and `framebuffer.h` in this folder. The module's job, in one sentence: the
shared-memory ring of frames that every reader takes the latest frame from.

You design from the owner's words and the architecture document. You do not transcribe
today's code into C. You do not copy the rev4 sketch; it was rejected.

## 2. Read first, in this order

1. /root/groundstation/CLAUDE.md and /root/groundstation/docs/guidelines.md (the house rules).
2. /root/groundstation/docs/api-harden2/rev5/modules/README.md: the document order (MOD1),
   the open-point form (MOD2), the eleven-point gate, the house split, the state table.
3. /root/groundstation/docs/api-harden2/rev5/01-system-architecture.md: section 6 (the frame
   buffer), sections 2 and 3 (the processes and threads that touch it), section 8 (the timing
   forces), section 9 (the failure handling), section 10 (the inherited rules).
4. /root/groundstation/docs/task-active-harden2-handoff-2026-10-02.md, section 2a3: part C
   (the procedure), part D (what each review taught), part E item 4 (this module), part F.
5. The three approved modules, as the reference for the shape and the depth:
   /root/groundstation/docs/api-harden2/rev5/modules/01-perf/perf.md and perf.h (you use
   PerfTimestamp and PerfNow); /root/groundstation/docs/api-harden2/rev5/modules/02-telemetry/
   telemetry.md and telemetry.h (a frame reaches telemetry as pixels with a stride; the size is
   fixed per run); /root/groundstation/docs/api-harden2/rev5/modules/03-runtime/runtime.md,
   runtime.h and runtime_internal.h (the house split done right; the SAM3 server is a child
   the supervisor relaunches).
6. The ledger rows that bind this module, in /root/groundstation/docs/spec-harden2-cleanup.md:
   SK4, SK5, FR1, RVW3, RVW4, SYS1, RUN3, RUN4, RUN14, MOD1, MOD2, GATE1, DOC1. Quote the
   owner's words in the document's rulings section.
7. Today's code, to describe what is wrong with it, not to copy it:
   /root/groundstation/projects/integration_harden2/perception2/vision.py (the snapshot per
   request), /root/groundstation/projects/integration_harden2/video/video.py and ros_stream.py
   (the frame path).
8. One finished review record, as the model for yours:
   /root/groundstation/docs/api-harden2/rev5/test/runtime-conclusions.md and
   runtime-round-1-reviewer.md.

## 3. The facts you start from (handoff part E, item 4)

- Design, section 6: 32 slots; a sequence number and a reference count per slot; C11 atomics,
  in Python through the `atomics` package (measured 4 us an operation); "latest" is set after a
  slot is complete; the frame source is the only writer and takes the next slot whose count is
  zero; a reader acquires before use (read latest, increment, re-read the sequence, retry); a
  vision job holds its slot across the SAM3 request and releases after the reply; the SAM3
  server reads pixels only.
- Rejected by the owner: a mutex per slot (SK4); hazard pointers (SK5); the server claiming the
  slot (RVW3); copy and release (RVW3). Do not propose them again.
- FR1 (the owner): no old frames lie around; the writer overwrites the oldest slot no reader
  holds; a reader uses "latest" only; the design must say how "latest" is guaranteed.
- Today: perception2 keeps frames in-process and takes a snapshot per request.

## 4. What you must settle (each one lands in the document and the header)

1. The slot size per source. The size is known before telemetry and the buffer are created:
   the webcam is probed (1280x720 today); the drone stream is 1920x1080, a given; a file is
   probed. A geometry change is a planned restart of the video path, never a new size mid-run.
2. The frame path's thread and copy. The measured 1080p ROS listener cost today: a 17 ms worst
   stall on the main thread and 22 of 30 frames delivered. Your design names the thread that
   copies into the slot and shows the main thread never copies.
3. The cost of a read on a job thread (today's telemetry copy at 720p: 0.05 to 0.18 ms). Measure
   acquire, release and one slot copy at 720p and 1080p on this machine (gate item 9).
4. A dead reader's count. The SAM3 server can die while it holds a slot; the supervisor
   relaunches it. The design says who clears the count and when. This is a TOCTOU item (gate
   item 11): name every check-then-act and the mechanism that closes it.
5. The slot count. Derive it again: 8 jobs, the screen's draw, no telemetry copy (RVW3). State
   the holders, the worst case, and the number. 32 is not a given.
6. The cross-process view. The SAM3 server opens the block by name and reads a slot by its
   sequence number. The header must define that view: the name, the layout of the slot
   headers and the pixel area, the atomics in shared memory, and the open and close calls.
   Module 6 (the SAM3 server) designs against your header.
7. The writer's path: begin write (the oldest slot with a zero count), end write (the sequence
   becomes latest), and what happens when no slot is free (the owner's rule from FR1: that is
   a bug, not a drop; say what the writer does).

## 5. The rules of the deliverable

- Only `framebuffer.md` and `framebuffer.h` in this folder, plus `framebuffer_internal.h`
  only if the owner must see a mechanism to judge the design (RUN4). No drawing. No other file
  (DOC1).
- `framebuffer.md` follows the MOD1 order in modules/README.md: the job, the picture (one
  text diagram), the usage (two pseudocode instances in the Python of the build), the open
  points (MOD2, the four-line form: the problem, now, on "no", recommended), then today, the
  rulings, the gate answers with the failure matrix, the notes.
- The header reads without its comments (RUN3). Create and Destroy; handles the app owns;
  `_Atomic` types for every shared value; m_ prefixes; no implementation comments. Anonymous
  `typedef enum {`; comment blocks above enums; no commas inside enum comments; 64-bit and
  float constants as macros (`UINT64_C`), never `static const`.
- Lay the header out with `python3 /root/groundstation/tools/style/header_layout.py <file>`.
  The tool reflows comments and realigns spacing; edit with line ranges, not exact strings.
  Compile with `gcc -fsyntax-only -Wall -x c <file>` from the perf folder on the include path.
- Prose in STE: one idea per sentence, under 20 words. Standard field terms (a reference
  count, a sequence number, a single-producer ring). Banned words: wire, seam, load-bearing,
  sieve. No em-dashes. No Hebrew inside an English sentence.
- No git write of any kind. No file outside this folder and your one record file.
- Mark every number you did not measure "unverified".

## 6. The procedure

1. Read everything in section 2. Write the full picture of the module in the system before
   any design: the threads that touch a slot, the processes, the rates, the sizes.
2. Design. Reason from the forces to one proposal per point in section 4. Where the owner must
   choose, write the four-line form. Where the design is clear, decide and state the reason.
3. Write `framebuffer.md` and `framebuffer.h`. Run the layout tool and gcc.
4. Run the eleven-point gate yourself. Each item gets the failure you tried and the mechanism
   that stops it, written in the document's gate section. Item 9 needs measurements; run them
   with a small script in your scratch folder, and put the numbers and the command in the
   document. Do not add the script to the repo.
5. Three reviewer rounds with subagents, one at a time. Each round: spawn one subagent
   (general-purpose, model opus, maximum care, the web for sources). Give it the module's files,
   this brief's section 3 and 4, and the three lenses of round 1 (storage and hardware;
   concurrency and real time; YAGNI and decoupling). It writes only its section into
   /root/groundstation/docs/api-harden2/rev5/test/framebuffer-review.md under
   "## Round N: reviewer". You answer under "## Round N: answer": accepted with the change made,
   or rejected with the reason. Rounds 2 and 3 are the push-back and the landing check. End the
   file with "## Conclusions": agreed, open, changed.
6. Update the document and the header after every round. Re-run the layout tool and gcc.
7. Write the progress log below. Return one line to the chat.

## 7. The machine

- Measurements run on this machine, in your scratch folder. No GPU is needed for this module.
- Shared files between agents (the webcam, the GPU, a config file) go through
  /root/groundstation/LOCK.md: `/root/groundstation/tools/lock.sh wait framebuffer webcam` before, `/root/groundstation/tools/lock.sh release framebuffer all` after. The webcam probe needs
  the webcam lock.
- Two other agents work at the same time on the llama server and the phone client. You do not
  edit their folders, the ledger, the handoff, or modules/README.md. The manager records the
  owner's rulings there.

## 8. Done when

- Both files exist, the header compiles, the layout tool ran clean, every gate item has its
  proof in the document, the review record holds three rounds and the conclusions, every open
  point is in the four-line form with an OPEN mark in the header, and the log below says so.

## Progress log (newest at the end)

- 2026-10-17, checkpoint 1: read everything in section 2; measured on this machine (the
  atomics package installed in the scratch folder; /dev/shm is 64 MB here, so the 1080p
  block of 12 slots SIGBUSed the writer, a real finding); wrote framebuffer.md,
  framebuffer.h and framebuffer_internal.h; the layout tool and gcc clean; the gate
  answered. Round 1 of the reviewer: 14 findings (1 critical: the atomics package yields
  the GIL per call, 5 ms p99 beside one busy thread; 1 high: Find matched a slot under
  write); 12 taken, 2 rejected (the config one-home pattern of perf.h and telemetry.h; a
  stored writer thread id). Re-measured with 3 busy threads; the GIL rule added (every
  atomic call and every pixel copy keeps the GIL). Open points: 4 (OPEN 1 to 4 in the
  header). Next: round 2.
- 2026-10-17, checkpoint 2: round 2 (the push-back): 3 push-backs, 13 findings (2 high: a
  memmove that shears a padded ROS frame; a video restart that lets an old server view
  match a new request's small sequence number), all taken. Changes: the sequences start
  at the block's epoch (PerfNow at Create) and Find answers FOUND, STALE or VIEW_GONE; the
  lock checked against the name's inode; Destroy's order; the copy helper checks on every
  call; one hold per thread, enforced; the recast verified at start; the magic written
  last; the counters plain. The system force (no CPU-bound Python longer than a frame)
  carried to the design document. Layout tool and gcc clean. Next: round 3.
- 2026-10-17, checkpoint 3, done: round 3 (the landing check): 19 items (1 high: the
  mapping sketch put the epoch at offset 28), all taken; the round 1 rejection of the
  stored writer thread id taken back (no restart changes the writer thread of one
  buffer). Both headers and the document rewritten in one pass each; gcc with
  -std=c11 -Wpedantic clean; the layout tool clean; the sizes asserted (128, 64, the
  epoch at 32, the latest index at 64). The record ends with the conclusions. Done
  criteria of section 8: both files exist (plus the internal header, RUN4); the header
  compiles; the layout tool ran clean; every gate item has its proof in section 7b with
  the failure matrix; the record holds three rounds and the conclusions; the four open
  points are in the four-line form with OPEN 1 to 4 in the header. Items for the
  manager: the system force into the design document's section 8; --shm-size for the
  dev container; the carry list in the conclusions. No git write was run.
- 2026-10-18: the owner's review, 8 points. Renamed to framebuffer (the folder
  04-framebuffer, the files, the record, every identifier). The picture redrawn. The
  questions and answers in framebuffer.md section 4b with decisions D1 to D6 (field
  widths, padding, a nameless memfd instead of a named file, temporal depth, the draw's
  copy, 1080p first). OPEN 2 rewritten. The header waits for the rulings.
- 2026-10-18, the owner's rulings: nameless memfd passed at launch (approved); the claim
  (approved; "dword"); SAM3 stays its own process. Headers and document rewritten: no
  name, no lock, no inode compare, no magic order, no epoch, no VIEW_GONE; Find returns
  a bool; FramebufferDescriptor added; Open takes the descriptor. Measured: a 74.7 MB
  memfd under the 64 MB cap, a child's writable map refused. gcc -std=c11 -Wpedantic and
  the layout tool clean. Open: OPEN 1 (slots), 3 (the draw's copy), 4 (widths), 5
  (padding). Carried to the manager: a pass-descriptors field in ProcessSpec.
- 2026-10-18, closing: the owner's header edit applied with intent-only comments (the
  slot pad 56 -> 64 fixed); the document's names aligned; runtime.h ProcessSpec gained
  m_passFds and m_nPassFds (RUN15, by this agent on the owner's word); the ledger rows
  FB1 to FB8, GIL1 and RUN15 written by this agent. Open for the owner: the capture time
  field in ReadOnlyFrameReference (keep, or read on demand). Everything else decided.
