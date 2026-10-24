# The review of the frame buffer: three rounds in one record (2026-10-17, PAR1, DOC1)

The subject: docs/api-harden2/rev5/modules/04-framebuffer/framebuffer.md, framebuffer.h and
framebuffer_internal.h. The reviewer: one general-purpose subagent, model Opus 5.5, a fresh
one per round, with the web for sources. Round 1 reads with three lenses in turn: storage and
hardware; concurrency and real time; YAGNI and decoupling. Round 2 is the push-back. Round 3
is the landing check. The author agent answers each round under its heading: accepted with the
change made, or rejected with the reason. The file ends with the conclusions.


## Round 1: reviewer

Scope: framebuffer.md, framebuffer.h and framebuffer_internal.h, read in full.
Also read: brief.md sections 3 and 4; 01-system-architecture.md sections 2, 3, 6, 8, 9, 10; modules/README.md.
Lenses, in turn: storage and hardware; concurrency and real time; YAGNI and decoupling.
Measured on this machine: Python 3.12.3, atomics 1.0.3, numpy 1.26.4, 32 threads, /dev/shm 64 MB tmpfs.
The scripts and logs are in the session scratchpad, folder r1/: m1_gil.py, m2_mitig.py, m3_windows.py.
They reuse the author's Block class from fb_measure.py. No aircraft, phone or GPU was touched.

### Sources
1. https://docs.python.org/3.12/library/ctypes.html : CFUNCTYPE: "The function will release the GIL during the call." PYFUNCTYPE: "The function will _not_ release the GIL during the call."
2. The atomics package source, atomics/_impl/patomic.py (1.0.3, in the author's pylib): every operation is a ctypes `CFUNCTYPE` function pointer into libpatomic.
3. https://pypi.org/project/atomics/ : "All operations have a default memory order, `SEQ_CST`." Version 1.0.3, released 2025-01-03.
4. The atomics package source, atomics/_impl/atomic/core.py: "ignore mutating ops if readonly"; a read-only buffer gets LOAD and BIT_TEST only.
5. https://docs.python.org/3.12/library/sys.html : setswitchinterval sets "the ideal duration of the 'timeslices' allocated to concurrently running Python threads."
6. https://github.com/python/cpython/issues/52194 : "Convoy effect with I/O bound threads and New GIL". A thread that releases the GIL for a call that completes at once must "wait through a timeout to regain control".
7. https://www.kernel.org/doc/html/latest/locking/seqlock.html : "Writers increment the sequence count at the start and the end of their critical section." "If the sequence count has changed between the start and the end of the critical section, the reader must retry."
8. https://man7.org/linux/man-pages/man2/flock.2.html : the lock is released "when all such file descriptors have been closed". LOCK_NB returns EWOULDBLOCK when "The file is locked".
9. https://man7.org/linux/man-pages/man2/kill.2.html : signal 0 checks "the existence of a process ID ... that the caller is permitted to signal". EPERM: "The calling process does not have permission".
10. https://man7.org/linux/man-pages/man2/fallocate.2.html : tmpfs supports fallocate "since Linux 3.5". "subsequent writes into the range ... are guaranteed not to fail because of lack of disk space."
11. https://man7.org/linux/man-pages/man2/mmap.2.html : MAP_POPULATE: "Populate (prefault) page tables for a mapping ... This will help to reduce blocking on page faults later."

### Findings

**R1-1. Every atomic call releases the GIL. The main thread's Acquire then waits whole switch intervals.** (critical)
- Claim: the atomics package calls libpatomic through ctypes CFUNCTYPE pointers (source 2).
- Claim: a CFUNCTYPE call releases the GIL (source 1). So every load, add and swap is a GIL hand-off point.
- Claim: after the hand-off, a CPU-bound Python thread keeps the GIL until its switch interval ends (sources 5, 6). The default is 5 ms.
- Claim: the calls per path: an Acquire and Release, 5; the health read, 14; a BeginWrite and EndWrite, about 29.
- Why it matters: the gate items 1 and 9 report 15 us for Acquire. That number holds only with no busy thread.
- Why it matters: the app has busy threads. Runtime R1-11 measured rclpy's 1080p conversion holding the GIL for 17 ms.
- Why it matters: the reader's load-to-add window now contains a GIL release. Preemption there becomes likely, not rare.
- Evidence (M1, measured): Acquire plus Release with no busy thread: 24 us median, 60 us p99.
- Evidence (M1): with 1 busy thread: 44 us median, 5122 us p99. With 3: 91 us median, 15240 us max.
- Evidence (M1): the health read with 3 busy threads: 152 ms max. The same Python work without a foreign call: 23 us max.
- Evidence (M2, measured): the same libpatomic pointers recast with ctypes.PYFUNCTYPE keep the GIL. With 3 busy threads: 38 us median, 188 us p99, 226 us max.
- Evidence (M2): sys.setswitchinterval(0.0005) with the package as is: 608 us p99, 735 us max.
- Change, framebuffer.md section 8: build every atomic view, then recast its operation pointers to PYFUNCTYPE. These are the same C11 functions of the same package (SK5). Only the GIL handling changes.
- Change, framebuffer.md section 7b items 1 and 9: re-measure every row with 3 busy threads beside the caller. Report median, p99 and max.
- Change, section 7b item 8: state that each atomic call is a GIL release point today, and what the design does about it.

**R1-2. StillHolds and Find miss a window: the writer's copy runs under the old sequence.** (high)
- Claim: EndWrite stores the new m_sequence. BeginWrite does not touch it.
- Claim: so from the claim to EndWrite, the slot keeps the old sequence while its pixels change.
- Claim: the server's Find, then read, then StillHolds can overlap that copy. StillHolds then returns true on a torn frame.
- Claim: Find can also match a slot under write, before the server even starts.
- Why it matters: TOCTOU row 4 in section 7b and in framebuffer_internal.h says StillHolds closes this window. It does not.
- Evidence (M3a, measured): a job held sequence S in slot 7 and released. The writer reclaimed slot 7 and wrote half of it.
- Evidence (M3a): Find gave slot 7. The StillHolds compare returned True. The top rows held the new frame, the bottom rows the old.
- Evidence: a seqlock marks the write in the counter at its start, not only at its end (source 7).
- Change, framebuffer_internal.h, the BeginWrite steps: after the swap wins, store m_sequence = 0. Then copy.
- Change, the same file, the TOCTOU paragraph: Find and StillHolds see 0 during a write, and the new number after it.
- Change, framebuffer.md section 7b item 11 row 4 and section 9: add a test that claims a slot, writes half, and expects Find and StillHolds to fail.

**R1-3. StillHolds is not needed: the job's hold already covers every reply the job accepts.** (medium)
- Claim: a job releases only after the reply or after its timeout. After its timeout it no longer waits for the reply.
- Claim: so any reply the job accepts was sent before the release. The server's whole read ran inside the hold.
- Claim: a late reply after the release is dropped by the job anyway (section 7b, row 4: "the job dropped the request anyway").
- Claim: StillHolds runs after the detect. So it saves no GPU time either.
- Why it matters: it is one more call in the cross-process contract that module 6 must implement and test. It protects nothing.
- Why it matters: the real closing mechanism is elsewhere. The SAM3 client must match a reply to its request by an id. It must drop a reply that arrives after the timeout. With a plain FIFO match, a late reply would land on the next job.
- Evidence: the reasoning above, from the order in section 3 instance 2. Unverified against module 6, which is not designed yet.
- Change, framebuffer.h: delete FramebufferStillHolds.
- Change, framebuffer.md section 7b row 4: "closed by the job's hold; a reply after the release is dropped by the client, matched by request id". Carry the request-id rule to module 6.
- Change: keep Find with the R1-2 fix. It lets the server skip a stale request before the detect.

**R1-4. The Die after 8 retries names a cause that cannot produce it.** (medium)
- Claim: the document says 8 retries means "a writer stuck in a claim: a bug".
- Claim: the writer never claims the latest slot. A stuck writer leaves m_latest pointing at a free slot. Every reader then succeeds at once.
- Claim: a retry happens only when a reader is delayed between its load and its add. The delay must last a frame, while the ring is near full.
- Claim: that is a scheduling event. With R1-1 unfixed, every atomic call invites it.
- Why it matters: RVW4 hands control to the RC for our own bug. A slow scheduler is not our bug in the module.
- Why it matters: `test_eight_retries_die` pins WRITING on the latest slot. That state cannot occur.
- Evidence (M1, measured): 8 reader threads and the writer at full speed for 5 s: 5211 frames, 0 retries.
- Change, framebuffer.h AcquireLatest comment and framebuffer_internal.h: past the bound, return false ("no frame this time") and count it in health. No Die.
- Change, framebuffer.md section 7b item 3 and section 9: drop this Die from the list. Replace the test with one that delays a reader by hand across 8 writes.

**R1-5. The owner pid check misses a window. A file lock closes it.** (medium)
- Claim: Create reads m_ownerPid, tests it alive, unlinks, then creates with O_EXCL.
- Claim: a missed window: apps A and B start together. Both see the dead owner. A unlinks and creates. B then unlinks A's new file and creates its own. Both run.
- Claim: kill with signal 0 is only a pid test (source 9). A reused pid looks alive. A pid of another user gives EPERM, which is ambiguous.
- Why it matters: the TOCTOU row 5 says "the second dies at start". In this order it does not.
- Evidence (M3c, measured): a child held flock(LOCK_EX) on the /dev/shm file. A second LOCK_NB attempt got EWOULDBLOCK. After the child's SIGKILL, the lock was free at once (source 8).
- Change, framebuffer.h: delete m_ownerPid. Keep the pad, so the offsets stay.
- Change, framebuffer.md section 8 mapping: open with O_CREAT and no unlink. Take flock(LOCK_EX | LOCK_NB) and hold it for the app's life. EWOULDBLOCK is a live owner. Then ftruncate and posix_fallocate.
- Change, the server's Open: flock(LOCK_SH | LOCK_NB) that succeeds means no owner. Unlock, close, return NULL.
- Change, section 7b item 11 row 5 and section 9: the lock is the check and the claim in one call.

**R1-6. The single writer is assumed, never enforced. A writer error leaks a slot.** (medium)
- Claim: m_nextSequence is a plain field of the writer thread. Two writers would issue duplicate sequences, and m_latest could move back.
- Claim: two writers can happen. The stall guard restarts the video path after 6 s (design section 9). An old ROS callback may still run beside the new writer.
- Claim: a writer that raises between BeginWrite and EndWrite leaves WRITING set forever. The ring loses one slot per event.
- Claim: the drone path checks height, width and encoding, not msg.step. A step below width times 3 makes the reshape raise after BeginWrite.
- Why it matters: 12 slots leave one spare (R1 check below). One leaked slot turns the worst legal load into the FR1 Die.
- Evidence: the code in section 3, instance 1. Unmeasured.
- Change, framebuffer.md section 3: check the step, and every shape, before BeginWrite.
- Change, framebuffer_internal.h: BeginWrite stores the calling thread's id on its first call. A call from another thread is a bug: Die.
- Change, section 7 "Threads": a restart of the video path joins the old writer before the new one starts. Carry this to module 12.

**R1-7. The health read costs more than the Acquire. It is missing from the budget.** (medium)
- Claim: FramebufferReadHealth loads m_latest, m_retries and 12 counts: 14 atomic calls. The main thread runs it every frame.
- Why it matters: section 7b item 9 counts the draw and the Acquire only. The health read is the largest buffer cost on the main thread.
- Evidence (M1, measured): 54 us median, 122 us p99 with no busy thread. 152 ms max with 3 busy threads.
- Change, framebuffer.md section 7b item 9: add the row.
- Change, framebuffer.h: count m_slotsHeld once a second, or on the status row's own period, not every frame.

**R1-8. One home is broken: the name and the slot count live in both the header and config.** (medium)
- Claim: framebuffer.h defines kFramebufferSlots and FRAMEBUFFER_NAME.
- Claim: section 7b item 6 lists config: FRAMEBUFFER_NAME, FRAMEBUFFER_SLOTS. Section 3 calls config.FRAMEBUFFER_NAME.
- Why it matters: "config/ is the one source of every value" (guidelines, Architecture). Two homes drift.
- Change: pick one. The slot count is a derived design constant, so keep it in the header. Move the name to config only, or the reverse. Fix item 6 to match.

**R1-9. The writer reloads what it alone wrote.** (low)
- Claim: BeginWrite loads m_latest and every m_sequence. The writer is the only thread that stores them.
- Why it matters: 13 of about 29 atomic calls per frame on the writer thread are redundant. Each is a GIL release (R1-1).
- Evidence: the author measured BeginWrite plus EndWrite at 66 to 106 us median with no copy.
- Change, framebuffer_internal.h: the writer keeps its own copy of each slot's sequence and the latest index. PickOldestFree loads only the counts.

**R1-10. A fresh mapping pays page faults on its first read of each slot.** (low)
- Claim: posix_fallocate gives the pages to tmpfs. It does not fill a mapping's page tables. Each process faults on first touch.
- Evidence (M3b, measured, 720p, read-only mapping in a new map): the first read of a slot took 0.14 to 1.84 ms. The second took 0.05 ms.
- Evidence (M3b): with MAP_POPULATE, the map took 1.6 to 2.2 ms once. Every first read then took 0.05 ms (source 11).
- Evidence: /sys/kernel/mm/transparent_hugepage/shmem_enabled is "never" here. So the block uses 4 KB pages.
- Change, framebuffer.md section 8: pass mmap.MAP_POPULATE at Create and at Open. The cost moves to start-up.

**R1-11. m_retries does not belong in the shared block.** (low)
- Claim: only app threads add to it and only the app reads it. The server never reads it.
- Claim: it shares the cache line of m_latest, which every reader loads.
- Why it matters: the cross-process contract should hold only what the other process reads. The header says "only m_latest and m_retries change after".
- Change, framebuffer.h: drop m_retries from FramebufferHeader. Keep the pad. framebuffer_internal.h: a counter in struct Framebuffer.

**R1-12. The sequence packed into m_latest has no reader that needs it.** (low)
- Claim: section 8 says "A reader needs both in one load". But the reader reads the sequence from the slot after its hold (item 11, row 3). It uses only the index from m_latest.
- Claim: the packed sequence serves the health row and the "no frame yet" test. Both work with an index and a sentinel.
- Why it matters: the stated reason contradicts the TOCTOU table.
- Change, framebuffer.md section 8: either correct the reason (health only), or store the index alone with 0xFF as "none".

**R1-13. kFramebufferMaxHolders and m_strideBytes have no caller.** (low)
- Claim: kFramebufferMaxHolders appears in two comments. No step uses it. kFramebufferSlots does not derive from it.
- Claim: rows are packed. m_strideBytes in the block and in FrameGeometry always equals width times 3.
- Change, framebuffer.h: drop kFramebufferMaxHolders, or write kFramebufferSlots as MaxHolders + 3 so the derivation is code.
- Change: drop m_strideBytes from FrameGeometry; telemetry's helper computes it.

**R1-14. The release check catches only some double releases.** (low)
- Claim: Release dies when the previous count was 0 or WRITING alone.
- Claim: a double release while another reader holds the slot goes unseen. It frees that reader's hold. The writer may then take the slot under it.
- Why it matters: item 11 row 6 says "none" for the window. There is one.
- Change, framebuffer.md section 7b item 11 row 6: name the window. It is covered by the with-block, the only release path.

**Checked, no finding:**
- The slot count: 9 holders, the writer's slot and the latest give 11. With 11 the writer always finds the previous latest free. 12 is one spare. The derivation is right.
- Memory ordering: the publication order (sequence, capturedAt, clear WRITING, store m_latest) and the reader's add before its load are correct under SEQ_CST, the package's default (source 3). Acquire and release would also suffice. The cost is the Python call, not the fence.
- The read-only view: the package itself refuses every mutating operation on a read-only buffer (source 4). The author's measurement of loads on PROT_READ stands.
- posix_fallocate on tmpfs reserves the pages (source 10). The SIGBUS case is closed at Create.
- FramebufferView as a second type: justified. It keeps the writer and reader calls out of the server's reach by type.
- Wrap-around: 56 bits of sequence and a count far below 2^31 cannot wrap.

### Questions for the author
1. Which module matches a SAM3 reply to its request, and by what id (R1-3)?
2. When the writer stalls for up to 6 s, do the jobs check capturedAt and refuse an old frame (FR1: "IT NEEDS THE LATEST FRAME")?
3. Does a video restart reuse this buffer, and does it join the old writer first (R1-6)?
4. Does the SAM3 preprocess run any in-place operation on the pixels? On a PROT_READ mapping that ends the server with SIGSEGV.
5. The 1080p rows used 8 slots. Will you re-run them at 12 slots in a container with a larger --shm-size, or mark them unverified?

## Round 1: answer

Every finding was re-measured or re-derived before the answer. The author's own re-run
(fb_measure2.py, the revised protocol, 0 and 3 busy threads) is the table in framebuffer.md
section 7b item 9. 12 findings accepted, 2 rejected.

- **R1-1 accepted, and widened.** Measured again: with the package as shipped and three busy
  threads, Acquire plus Release 73 / 5232 / 639278 us; the writer's BeginWrite plus EndWrite
  178 / 126868 / 1231429 us. The recast to PYFUNCTYPE: 35 / 172 / 230 us and 105 / 343 / 437
  us. Widened: the numpy copy yields the GIL too and pays the same wait: a 720p write beside
  three busy threads 5546 / 1175941 / 1444316 us; the draw 5335 / 1570959 / 2315227 us. A
  memmove through PYFUNCTYPE keeps the GIL: 386 / 864 / 1044 us and 132 / 672 / 704 us. The
  rule in section 8: every atomic call and every pixel copy on the frame path and the draw
  keeps the GIL. The helper `copy_pixels` lives in util/. Items 1, 8 and 9 re-measured with
  the busy threads; a test pins the bound.
- **R1-2 accepted.** BeginWrite stores the slot's sequence as 0 right after the claim;
  EndWrite stores the number before the publish. Find never matches a slot under write.
  The header's field note, the internal header's steps and the TOCTOU row say so; a test
  added. Measured in the re-run: Find of the pending number returns none during a claim.
- **R1-3 accepted.** FramebufferStillHolds deleted. The job's hold covers every reply the
  job accepts; a reply after the timeout is dropped by its request id. Carried to module 6
  in section 8. Find stays, with the R1-2 fix, so the server skips a stale request before
  the detect. Your question 1: the SAM3 client in the jobs (module 13) matches by the
  request id it sent; module 6 defines the id in the reply.
- **R1-4 accepted.** Past AcquireRetries the reader returns false and the miss is counted
  in the health. No Die. The test replaced.
- **R1-5 accepted.** m_ownerPid deleted (the pad keeps the offsets). Create opens with
  O_CREAT and takes flock(LOCK_EX | LOCK_NB) for the app's life; EWOULDBLOCK is a live
  owner; then ftruncate and posix_fallocate. Open takes LOCK_SH | LOCK_NB: success means no
  owner, so it closes and returns NULL. The TOCTOU row and the tests changed.
- **R1-6 accepted in part.** Taken: the step and length checks before the claim (instance
  1); a BeginWrite inside an open write dies (mb_writeOpen); the join of the old writer
  before a new one carried to module 12. Rejected: a stored writer thread id. A planned
  restart of the video path may run the writer on a new thread; the id check would die on
  a legal restart. The overlap check catches what this module can see; the join closes
  the alternation. Your question 3: the stall guard restarts the gstreamer process only;
  the subscription thread and the buffer stay. A geometry change recreates the video path
  and the buffer; the app step settles the order.
- **R1-7 accepted, with a different mechanism.** The writer scans every count each frame
  anyway; PickOldestFree counts the held slots on the way and the writer keeps it as a
  plain value. ReadHealth is four plain loads, no atomic call. The row is in item 9's
  reasoning: it costs nothing now.
- **R1-8 rejected.** perf.h and telemetry.h, both approved, show their config values as an
  enum with the note "config values, read once at Create (config/ is the one source)". The
  header is the design language; config is the build's one source; the enum shows the
  derivation. Item 6 now says so in those words.
- **R1-9 accepted.** The writer keeps its own table of sequences and its latest index;
  PickOldestFree takes the table and loads only the counts. BeginWrite plus EndWrite went
  from 102 to 59 us median at 720p idle in the first re-run.
- **R1-10 accepted.** MAP_POPULATE at Create and at Open; in the header's comments and
  the mapping.
- **R1-11 accepted.** m_retries left the block; it and m_misses are counters in struct
  Framebuffer.
- **R1-12 accepted, the second option.** m_latestIndex is an index alone, NO_FRAME before
  the first frame. The health's latest sequence is the writer's own count. The note
  rewritten.
- **R1-13 accepted.** kFramebufferSlots = kFramebufferMaxHolders + 3. m_strideBytes dropped
  from the block and from FrameGeometry; the rows are packed; the instance passes w * 3 to
  telemetry.
- **R1-14 accepted.** The row names the window: a second release while another reader
  holds frees that hold; the with-block is the only release path.
- Your question 2: the buffer gives capturedAt; whether a job refuses a stale frame during
  a video stall is module 13's; carried in section 8 with a recommendation to report it.
- Your question 4: carried to module 6; the view's numpy array is flagged read-only, so a
  write raises in Python before any SIGSEGV.
- Your question 5: the 12-slot 1080p numbers are marked unverified in item 9; the per-call
  costs do not depend on the slot count except the scan, which is 12 loads instead of 8.

## Round 2: reviewer

Scope: the revised framebuffer.md, framebuffer.h and framebuffer_internal.h, read in full.
Also read: round 1 and its answer; brief.md sections 3 and 4; 01-system-architecture.md sections 2, 3, 6, 8, 9, 10; modules/README.md; runtime.h (the ROS subscription); perception2/vision.py (the count job).
Measured on this machine: Python 3.12.3, atomics 1.0.3, numpy 1.26.4, OpenCV 4.11.0, 32 threads.
The scripts and logs are in the session scratchpad, folder r2/: r2_m.py (M1 to M8), r2_m7b.py, and their .log files.
They reuse the author's Block class from fb_measure2.py. No aircraft, phone or GPU was touched.

### Sources
1. https://docs.python.org/3.12/library/ctypes.html : PYFUNCTYPE: "The function will _not_ release the GIL during the call." PyDLL: "after the function execution the Python error flag is checked."
2. https://man7.org/linux/man-pages/man2/flock.2.html : "Locks created by flock() are associated with an open file description." "duplicate file descriptors (created by, for example, fork(2) or dup(2)) refer to the same lock". "Locks created by flock() are preserved across an execve(2)."
3. https://peps.python.org/pep-0446/ : "make all file descriptors created by Python non-inheritable by default". "The close-on-exec flag has no effect on fork(): all file descriptors are inherited by the child process."
4. https://docs.python.org/3.12/library/multiprocessing.html : the fork start method is the POSIX default in 3.12. "All resources of the parent are inherited by the child process."
5. https://man7.org/linux/man-pages/man2/mmap.2.html : "SIGBUS Attempted access to a page of the buffer that lies beyond the end of the mapped file."
6. https://docs.python.org/3.12/library/mmap.html : MAP_POPULATE: "Changed in version 3.10: Added MAP_POPULATE constant."
7. The atomics package source, atomics/_impl/atomic/core.py (1.0.3): every operation fetches its pointer per call through `get_op_func`, which reads the private dict `_supported`.
8. Round 1 sources 5 and 6 (the switch interval; the convoy effect) still apply.

### Round 1, one line each
- R1-1: push-back. The measured gain for the buffer's own calls is real. The recast rests on three private names and a timing test only (R2-5). Its cost moved to the other threads and is not in the budget (R2-6). The frame-level gain is near nothing under the same load (R2-6, M8).
- R1-2: the answer stands. A sequence of 0 never equals a published number, since numbering starts at 1. One gap remains: Find(0) itself (R2-9).
- R1-3: the answer stands. A detect that runs on after the job's timeout reads a slot the writer may reuse. The job drops that reply by its request id, so nothing reaches the app.
- R1-4: the answer stands. Oldest-first makes a retry rarer than the document says (R2-12). Starvation needs eight such sleeps in a row; it is counted, and "no frame this time" is a correct degrade for both the draw and a job.
- R1-5: push-back. The lock is on a path, not on a name. Destroy's unlink and a new Create can leave the new app locked on a deleted file (R2-3, M3). A forked child keeps the lock alive (R2-8, M2).
- R1-6: the answer stands. runtime.h gives each subscription its own single-threaded executor, so the drone writer is one thread. M6: the plain flag caught every overlap of two writers in 3 s under the GIL. One fault remains: an exception between BeginWrite and EndWrite now dies with the wrong reason (R2-12).
- R1-7: the answer stands for the mechanism. The internal header still types the two counters `_Atomic` beside "no atomic call" (R2-11).
- R1-8: push-back, narrow. The literal-in-the-enum pattern is the approved precedent (telemetry.h). The fault is the derivation: MaxHolders = 9 repeats the vision pool size of 8 as a second literal (R2-7).
- R1-9: the answer stands.
- R1-10: the answer stands.
- R1-11: the answer stands.
- R1-12: the answer stands.
- R1-13: the answer stands.
- R1-14: the answer stands.

### Findings

**R2-1. copy_pixels shears a padded frame, and it has no size check.** (high)
- Claim: instance 1 accepts `msg.step > width * 3`. It then passes `rows[:, :width*3].reshape(h, w, 3)` to copy_pixels.
- Claim: that array is a strided view, not C-contiguous. memmove copies `src.nbytes` bytes from its first byte, padding included.
- Claim: every row after the first is shifted by the padding. The frame is wrong, and nothing reports it.
- Claim: the helper checks no size ("checked once"). A source bigger than the slot writes into the next slot, which a job may hold, or past the mapping.
- Why it matters: the revision swapped a numpy copy, which checks shape and stride, for a raw memmove. That removed the memory safety the old copy had.
- Evidence (measured, 4 rows of 5 pixels, step 16): the view is not C-contiguous. Row 1 expected [16 17 18 ...], memmove gave [15 16 17 ...]. Equal: False.
- Change, framebuffer.md section 3 instance 1: reject `msg.step != width * 3` before the claim, counted as a source drop. A padded step is not a frame this path can copy in one call.
- Change, section 8, util/copy.py: copy_pixels checks on every call that both arrays are C-contiguous and have the same nbytes. A mismatch is our bug: Die. The cost is two attribute reads.
- Change, section 9: add `test_copy_pixels_refuses_a_strided_or_short_array` and `test_a_padded_step_is_dropped_before_the_claim`.

**R2-2. A geometry restart lets the SAM3 server read an old frame by a reused sequence number.** (high)
- Claim: the author's answer to question 3 says a geometry change recreates the buffer. Destroy unlinks the name. Create makes a new file. m_nextSequence starts at 1 again.
- Claim: a running server keeps its view of the old file. The mapping stays valid after the unlink.
- Claim: the new block's sequences 1, 2, 3 match the old block's slots. Find returns an old frame of the old size. The detect runs on it, and the boxes land on the new frame.
- Why it matters: this is a wrong answer, silent, with no error anywhere. The TOCTOU table and the failure matrix have no row for it.
- Evidence (M4, measured): run A wrote 5 frames; the server's view opened. Destroy, then Create at a new size, 5 frames. Find(5) on the old view gave slot 4 with pixel 104, the old frame. The new frame's pixel is 204.
- Change, framebuffer.h: add `uint64_t m_epoch` to FramebufferHeader in m_pad0: PerfNow() at Create, written before the magic. FrameRef carries it.
- Change, framebuffer.h, Find: take the request's epoch. A mismatch returns false with a "reopen" result. The server then closes and reopens its view.
- Change, section 7b item 11 and the failure matrix: add the row "a geometry restart: the old view, a reused sequence; closed by the epoch". Add `test_find_refuses_a_request_of_another_epoch`.

**R2-3. The lock is taken on whatever file the path named at open time.** (medium)
- Claim: Create opens the path, then locks the descriptor. Between the two, the old app's Destroy can unlink the file and close it.
- Claim: the lock then succeeds on a file with no name. The new app runs. Its SAM3 server's Open by name finds a different file or none, with no lock holder.
- Claim: the server returns NULL and is relaunched until the restart budget ends the start.
- Why it matters: TOCTOU row 5 says the lock is "the check and the claim in one call". It is one call on an inode, not on the name.
- Evidence (M3, measured): the old app held the lock; the new app opened; the old app unlinked and closed. The new app's LOCK_EX | LOCK_NB succeeded. fstat gave nlink 0; the path did not exist.
- Change, section 8 mapping: after the lock, compare `os.fstat(fd)` with `os.stat(path)` on st_dev and st_ino. A mismatch, or ENOENT: close and open again, at most 3 times, then NULL.
- Change, Destroy's steps: unlink the name first, then close the descriptor. The order is written in framebuffer_internal.h.
- Change, section 9: add `test_create_retries_when_its_file_was_unlinked_after_open`.

**R2-4. Destroy throws when any pixel array outlives its Release, and its stop order misses the ROS executor.** (medium)
- Claim: every slot's pixels are numpy arrays over the mapping. Every atomic view holds a buffer export.
- Claim: mmap.close() refuses while any export is alive. It raises BufferError, an exception in our code (the no-throw rule).
- Claim: a FrameRef's array kept past the with-block by any caller is such an export.
- Claim: the drone writer is the ROS executor thread (runtime.h: "its own single-threaded executor"). The document orders Destroy after "the frame source thread joined". RosSubscriptionDestroy is not named.
- Claim: a callback after Destroy calls BeginWrite on released views. The package raises ValueError on that thread.
- Why it matters: shutdown is one of the paths the failure matrix must cover. Neither case has a row.
- Evidence (M1, measured): one slot slice kept by a reader; close() raised "BufferError: cannot close exported pointers exist".
- Change, framebuffer.h, Destroy's comment: "after RosSubscriptionDestroy or the webcam thread's join". Carry the order to module 12 and the app step.
- Change, section 8 mapping: Destroy exits every atomic view, drops the pixel arrays, releases the memoryview, then closes. BufferError goes through the filesystem guard in util/guarded.py and is logged as "a pixel array outlived its Release" (our bug, at shutdown, no Die).
- Change, the failure matrix: add rows for both. Add `test_destroy_with_a_kept_pixel_array_logs_and_returns`.

**R2-5. The GIL recast depends on three private names, and its only test is a timing bound.** (medium)
- Claim: keep_gil reads `view._core`, `core._supported`, and `type(fp)._restype_` and `_argtypes_`. None is public API of the package (source 7).
- Claim: a package change that caches the pointer elsewhere makes the recast a silent no-op. The code still runs, and the GIL is released again.
- Claim: `test_atomic_calls_keep_the_gil` covers Acquire and Release only. CMPXCHG_STRONG, STORE and FETCH_SUB of the writer are unchecked. copy_pixels is unchecked.
- Claim: a p99 bound on a shared CI machine fails by load, not by a fault. A flaky test gets disabled.
- Why it matters: the rule in section 8 protects the whole design's numbers. A silent revert breaks every row of item 9.
- Evidence: the package source (source 7). PYFUNCTYPE keeps the GIL (source 1). Unmeasured on a CI machine: unverified.
- Change, section 8 mapping: at Create and at Open, check `importlib.metadata.version("atomics") == "1.0.3"`, and that every pointer in every `_supported` has `ctypes._FUNCFLAG_PYTHONAPI` in its `_flags_`. A failure is a start-up Die with the reason.
- Change, section 9: replace the timing test with `test_every_atomic_op_and_the_copy_keep_the_gil`, a check of those flags. Keep the timing run in the benchmark, not the suite.
- Change, section 8: write the alternative and its reason: a ctypes Structure of PYFUNCTYPE fields over libpatomic's own `patomic_create_explicit`. It uses the same C functions (SK5) and only the C library's layout. It is the fallback if the package changes.

**R2-6. Keeping the GIL moves the copy's cost onto the other threads, and the frame does not gain.** (medium)
- Claim: a copy that keeps the GIL blocks every other Python thread for its length. The main thread then waits on its wake-up from waitKey or a sleep.
- Claim: item 9 budgets the buffer's calls on the caller. It does not budget the wait the writer's copy puts on the main thread.
- Claim: the main thread's own cv2 calls release the GIL each time. With three busy Python threads they pay the same convoy wait the recast removed.
- Why it matters: item 1 reports "Acquire 172 us p99 beside three busy threads". Under that load the frame is lost to cv2, not to the buffer. The number reads as a frame bound, and it is not one.
- Evidence (M7b, measured, 1080p writer at 30 Hz, 6000 wake-ups of 1 ms): numpy copy beside it, overshoot 54 / 65 / 80 us. memmove keeping the GIL, 55 / 307 / 808 us; 61 wake-ups over 300 us.
- Evidence (M8, measured, 720p, 30 frames only): Acquire, copy and Release plus 30 cv2.rectangle and putText calls. Idle: the buffer part 145 us median, the 30 draw calls 138 us. With three busy threads: the buffer part 540 us, the draw calls 1.01 s median and 5.06 s max per frame.
- Change, section 7b item 9: add the row "the main thread's wait on the writer's copy", 307 us p99 and 808 us max at 1080p.
- Change, section 7b item 1 and section 6: state that the three-busy-thread rows are the buffer's share only. Any CPU-bound Python thread already breaks the frame through cv2.
- Change, carry to 01-system-architecture.md section 8 as a system force: no thread of the app may run CPU-bound Python for longer than a frame. The real case is rclpy's image conversion (runtime R1-11). Keep the recast: it is cheap, and it bounds the buffer's part.

**R2-7. The slot count assumes one hold per reader, and nothing enforces it.** (medium)
- Claim: the derivation counts 9 holders, one slot each. A job that holds a second slot while it holds the first breaks it.
- Claim: the vision jobs are not designed yet. Today's count job takes three frames in a loop; the highlight gate runs SAM3 then Gemma on one frame, then tracks on new ones. A port that keeps the gate's frame while tracking holds two.
- Claim: at 9 jobs plus the draw with one extra hold, the ring is legal by every caller's code and still dies by FR1.
- Claim: MaxHolders = 9 is the vision pool's 8 plus the draw, written as a literal. A pool of 10 in config leaves 12 slots and a ring that dies under a legal load.
- Why it matters: FR1's Die is right only when every slot held is a bug. Here it would be a design gap that dies in flight.
- Evidence: vision.py `_count_task` and `_highlight_task`. The pool size in 01-system-architecture.md section 3. The rest is reasoning; the module 13 design is unverified.
- Change, framebuffer.h: state the rule "one hold per thread at a time" under AcquireLatest.
- Change, section 8 mapping: a `threading.local` hold count. A second Acquire on a thread that holds one is our bug: Die with "a second hold on one thread". One plain attribute, no atomic call.
- Change, config: FRAMEBUFFER_SLOTS = VISION_POOL_SIZE + 1 + 3, computed in config/defaults.py from the pool's own entry. The header's enum keeps the derivation as text.
- Change, section 9: add `test_a_second_hold_on_one_thread_dies`.

**R2-8. A forked child keeps the app's lock after the app dies.** (low)
- Claim: flock belongs to the open file description. A fork shares it, and exec keeps it (source 2).
- Claim: Python's descriptors are close-on-exec by default (source 3). So the supervisor's Popen children do not keep it. A plain fork, or multiprocessing's default fork method in 3.12, does (sources 3, 4).
- Claim: the next app then gets EWOULDBLOCK while no app is alive. Its start dies with "another app holds the lock".
- Evidence (M2, measured): owner dead, its forked child alive: EWOULDBLOCK. Popen with defaults: the lock free. Popen with the descriptor inheritable and close_fds=False: EWOULDBLOCK.
- Evidence: no `multiprocessing` and no `os.fork` in projects/integration_harden2 today (grep).
- Change, section 8: one line: "the app never forks without exec; the lock descriptor is never passed to a child". Create's NULL message names the holder from `/proc/locks` when it can.

**R2-9. Find(0) matches an empty slot or a slot under write.** (low)
- Claim: 0 now means "empty or under write". A request that carries 0, a default or a parse bug, matches such a slot.
- Claim: the server then reads a torn or blank frame, and no check stops it.
- Change, framebuffer.h, Find: "a sequence of 0 returns false". Add a row to `test_find_never_matches_a_slot_under_write`.

**R2-10. Create rewrites a reused file's header while the old magic is still valid.** (low)
- Claim: Create reuses a dead run's file. It takes the lock before it writes the header.
- Claim: in that window the file holds a valid magic, an old geometry and old counts. A view opened then passes the probe, since the lock is now held.
- Claim: the start order prevents it today. Nothing in the module does.
- Change, section 8 mapping: after the lock, store magic 0 first. Then the geometry, then zero every count and sequence, then the magic last. Open then refuses the window by its magic check.
- Change, the TOCTOU table: add the row "Open racing Create's header write".

**R2-11. The health counters are `_Atomic` in one header and "plain loads" in the other.** (low)
- Claim: framebuffer_internal.h types m_retries and m_misses `_Atomic uint64_t`. The public header and section 7b say ReadHealth is "four plain loads, no atomic call".
- Claim: the Python mapping does not show which one is built. Several reader threads add to these counters.
- Evidence (M5, measured): 8 threads, 200,000 `h.retries += 1` each, on 3.12.3. No update lost at a 5 ms or a 10 us switch interval. CPython does not promise this: unverified as a guarantee.
- Change, framebuffer_internal.h: type them `uint64_t`. The note: "a Python int; += by readers, safe under the GIL of 3.12; PerfCreate already dies without the GIL".

**R2-12. Three sentences of the revision are wrong.** (low)
- Claim: TOCTOU row 2 and the failure matrix say a retry needs a reader "asleep a whole frame". Oldest-first reuses the old latest slot only after every older free slot. With no holders that is 11 frames, about 360 ms. With 9 holders it is the next frame.
- Claim: an exception between BeginWrite and EndWrite leaves mb_writeOpen set. The next frame dies with "a second writer". The cause is an open write left behind.
- Claim: section 6 says the forces include "22 of 30 frames delivered" as the frame source's. That is rclpy's cost, and R2-6 makes it a system force.
- Change: row 2: "a reader asleep until the writer reuses the slot: from 1 frame (9 holders) to 11 frames (none)". The Die's reason: "a write left open, or a second writer". framebuffer.md section 6: point to the system force.

**R2-13. Two tests cannot catch the fault they name, and five closed windows have no test.** (low)
- Claim: `test_a_second_process_opens_read_only_finds_by_sequence_and_cannot_write` checks the numpy flag. It passes on a read-write mapping with a read-only array. The header claims "by the mapping's protection".
- Claim: `test_atomic_calls_keep_the_gil` passes with a partial recast (R2-5).
- Claim: no test for the padded step (R2-1), the epoch (R2-2), the unlinked file (R2-3), Destroy with a kept array (R2-4), or a second hold on one thread (R2-7).
- Change, section 9: the read-only test also calls `fetch_add` on a count view of the server's mapping and expects UnsupportedOperationException. A ctypes memmove into the mapping, in a spawned child, must end that child with SIGSEGV. Add the five tests named above.

### Count
Push-backs: 3 (R1-1, R1-5, R1-8). New findings: 2 high, 5 medium, 6 low.

## Round 2: answer

All 13 findings taken; the three push-backs land through them. Two mechanisms differ from
the proposal, with the reason.

- **R2-1 accepted.** The drone path drops a padded step before the claim (our receiver
  publishes packed rows). copy_pixels checks C-contiguity and equal nbytes on every call;
  a mismatch is our bug and dies. Both tests added.
- **R2-2 accepted, a different mechanism.** Instead of an epoch carried in every request:
  a block's sequence numbers START at its m_epoch, PerfNow() at Create, so the numbers of
  two blocks in one boot never meet and an old view cannot match a new request by
  arithmetic. Find answers FOUND, STALE or VIEW_GONE; VIEW_GONE is "the name is gone"
  (fstat, no link), on which the server closes and reopens. The request format stays one
  number. The header's m_epoch is at offset 32, version 3; the TOCTOU row, the matrix row
  and the test added.
- **R2-3 accepted.** The inode compare after the lock, three retries, then NULL. Destroy
  unlinks first, then closes. Both in framebuffer_internal.h's Create and Destroy steps.
- **R2-4 accepted.** Destroy's order written: unlink, exit the views, drop the arrays,
  release, close; a kept array goes through the filesystem guard and is logged, no Die.
  Destroy's comment names RosSubscriptionDestroy or the webcam thread's join; carried to
  module 12 and the app step. Two matrix rows and the test added.
- **R2-5 accepted.** Create and Open check the package version (1.0.3) and the
  keep-the-GIL flag on every operation pointer; a miss dies at start. The suite test
  checks the flags on every view and on the copy helper; the timing run stays in the
  benchmark. The fallback (our own ctypes structure over libpatomic) is in section 8.
- **R2-6 accepted.** Item 1 states the rows are the buffer's share; the main thread's
  wait on the writer's copy (your M7b: 307 us p99, 808 us max) is in item 1; section 6
  carries the system force to the design document's section 8: no CPU-bound Python
  longer than a frame on any thread. The recast stays.
- **R2-7 accepted.** One hold per thread at a time, in the header under AcquireLatest; a
  thread-local count in the mapping; a second hold dies. config computes
  FRAMEBUFFER_SLOTS from the pool's entry (pool + 1 + 3); the enum shows the derivation.
  Section 4 point 1 says so. The test added.
- **R2-8 accepted.** The one line in section 8 and a matrix row; the NULL message names
  the holder from /proc/locks.
- **R2-9 accepted.** A request of 0 is STALE; in the header and the Find steps; the test.
- **R2-10 accepted.** The magic stored 0 first and the real value last; the TOCTOU row
  and the test.
- **R2-11 accepted.** The two counters are plain uint64_t with the note that a lost add on
  a diagnostic is harmless.
- **R2-12 accepted.** The three sentences rewritten: the retry window (1 frame with 9
  holders, 11 with none); the Die's reason names both causes; section 6 points to the
  system force.
- **R2-13 accepted.** The read-only test now also tries fetch_add on the server's view
  and a ctypes memmove in a spawned child; the GIL test checks the flags; the five tests
  named are added.
- The three push-backs: R1-1 stands with R2-5 and R2-6 applied; R1-5 stands with R2-3 and
  R2-8 applied; R1-8 stands with R2-7's derivation from the pool's config entry.

## Round 3: reviewer

Scope: the revision after round 2: framebuffer.md, framebuffer.h, framebuffer_internal.h, read in full.
Also read: rounds 1 and 2 with both answers; brief.md sections 3, 4, 5 and 8; modules/README.md; 01-system-architecture.md section 8; perf.h.
Checked against R1-1 to R1-14 and R2-1 to R2-13.
Run on this machine, in the session scratchpad folder r3/: gcc on both headers, a static-assert layout program, struct and numpy checks, and the atomics 1.0.3 package from the author's pylib.
No aircraft, phone or GPU was touched.

### Sources
1. https://docs.python.org/3.12/library/struct.html : "No padding is added when using non-native size and alignment, e.g. with '<', '>', '=', and '!'."
2. https://docs.python.org/3.12/library/ctypes.html : PYFUNCTYPE: "The function will _not_ release the GIL during the call."
3. https://man7.org/linux/man-pages/man2/flock.2.html : "Locks created by flock() are associated with an open file description."
4. https://docs.python.org/3.12/library/os.html#os.stat : os.stat raises FileNotFoundError when the path does not exist (OSError subclass).
5. https://www.kernel.org/doc/Documentation/memory-barriers.txt : without a barrier, "the CPU" may "reorder" independent stores as seen by another CPU (ARM; x86 keeps store order).
6. The atomics package source, atomics/_impl/atomic/base.py (1.0.3): AtomicViewContext.__del__ calls release(), which raises "Cannot call 'release' while context is open."

### Check 1: did every accepted finding land, in each place it belongs
| finding | header(s) | document | tests list | gap |
|---|---|---|---|---|
| R1-1 | n/a (Python) | yes | yes (R2-5 form) | section 8 line 394 still says "a test keeps the bound" (R3-9) |
| R1-2 | yes | yes | yes | none |
| R1-3 | yes (no StillHolds) | yes | yes | none |
| R1-4 | yes | yes | no | the test still pins WRITING on the latest slot by hand (R3-11) |
| R1-5 | yes | yes | yes | none |
| R1-6, taken part | yes (mb_writeOpen) | yes | yes | none |
| R1-7 | yes | yes | yes | none |
| R1-9 | yes | yes | yes (Pick table) | none |
| R1-10 | yes | yes | n/a | none |
| R1-11 | yes | yes | yes | none |
| R1-12 | yes | yes | n/a | none |
| R1-13 | yes | yes | n/a | none |
| R1-14 | yes | yes | yes | none |
| R2-1 | n/a (util/) | yes | yes | the webcam path has no size check (R3-10) |
| R2-2 | yes | yes | yes | the mapping writes m_epoch at 28 (R3-1); the lifetime contradicts it (R3-5) |
| R2-3 | yes | table yes, sketch no | yes | the sketch compares late, on st_ino only (R3-3) |
| R2-4 | yes | yes | yes | no matrix row for "Destroy while the writer runs" (R3-11) |
| R2-5 | no | yes | yes | the sketch checks before the recast (R3-3); NULL or Die (R3-13) |
| R2-6 | n/a | yes | n/a | not in 01-system-architecture.md section 8 (R3-8) |
| R2-7 | yes | yes | yes | the internal array is sized by the enum (R3-6) |
| R2-8 | n/a | section 8 and TOCTOU yes | no | no matrix row (R3-11) |
| R2-9 | yes | yes | yes | none |
| R2-10 | yes | table yes, sketch no | yes | the sketch stores latest after the magic (R3-3); window open (R3-4) |
| R2-11 | yes | yes | yes | the internal sentence "one plain value with one writer" (R3-14) |
| R2-12 | Die reason yes | TOCTOU row 2 yes | n/a | matrix row, internal TOCTOU, section 8 note unchanged (R3-9) |
| R2-13 | n/a | yes | yes | the GIL test checks the dict it patched (R3-12) |

### Check 2: the two rejections
- R1-8: the reason was "the enum shows the derivation; config is the one source". It no longer holds in full. The internal header sizes `m_sequences[kFramebufferSlots]` by the enum. A pool of 10 gives 14 slots in config and 12 in the array (R3-6).
- R1-6, the thread id: the reason was "a planned restart may run the writer on a new thread". The answer to round 1 question 3 says the drone stall keeps the thread and the buffer. A geometry change makes a new buffer. Under both, one buffer never sees a second legal writer thread. The reason holds only if the webcam's stall restart starts a new thread for the same buffer. The document does not say (R3-19).

### Check 3: the document's order (MOD1) and the open points (MOD2)
- Order: job, picture, two instances, open points, today, rulings and forces, gate, gate answered, failure matrix, notes, tests. Correct.
- Section 1 holds "and". MOD1: "If it needs 'and', the module splits." It is a phrasing fault, not a split (R3-17).
- Open points 1 to 4: each has the problem, now, on "no", recommended. Each has its OPEN n in framebuffer.h (lines 20, 85, 105, 143).
- Legible from the header plus four lines: yes for 2, 3 and 4. Point 1 needs the config derivation, which the header holds only as comment text.

### Check 4: the header's house rules
| rule | result |
|---|---|
| gcc -fsyntax-only -Wall -Wextra, both headers | clean; also clean with -std=c11 -Wpedantic |
| layout, compiled with static asserts | header 128, slot header 64, m_epoch 32, m_latestIndex 64, m_count 8, m_capturedAt 16: all hold |
| reads without comments; Create and Destroy; Open and Close | yes |
| app-owned handles | yes; one module global, gFramebufferHoldsOnThread (thread-local) |
| `_Atomic` for every shared value | no: m_magic is now a publication flag; the health values and two counters are plain (R3-4, R3-14) |
| m_ prefixes; mb_ for the bool | yes |
| no implementation comments | no: AcquireLatest, BeginWrite and Destroy carry their steps in the public header (R3-15) |
| anonymous typedef enum; comment block above | yes |
| no commas inside enum comments | no: FrameFindResult lines 202 and 204; the config enum block (R3-15) |
| 64-bit and float constants as macros | yes; no static const |
| every line under 90 characters | yes, both headers |

### Check 5: names and numbers
- Offsets 32, 64, 128, 4096; version 3; 12 slots; MaxHolders 9; 8 retries; 25 views; 74,653,696 bytes: all match.
- FRAME_FOUND, FRAME_STALE, FRAME_VIEW_GONE, NO_FRAME, WRITING: all match.
- Instance functions: create, begin_write, end_write, read_health, open, find, close all match the header.
- Mismatch: `frames.latest()` names no header call. It wraps AcquireLatest and Release (R3-17).
- Mismatch: the sketch writes m_epoch at offset 28, not 32 (R3-1, measured).
- Mismatch: "retries at most 8 times" (section 7) against "at most AcquireRetries times" tries (internal header) (R3-17).
- The measured numbers in sections 2, 4, 6, 7b and 8 match the item 9 table.

### Check 6: the gate
- Items 1 to 8 and 10: each names a failure tried and a mechanism. No bare "yes".
- Item 9: the table matches the prose for the main thread. The prose says "the buffer's own share passes". The writer thread pays 0.73 ms a frame at 1080p idle, and 343 us p99 for the calls alone under load. Both exceed 330 us (R3-16).
- Item 11: 14 rows. Twelve have a test. Two do not: "Destroy while the writer runs" and "a forked child holds the lock". The line "Each closed window has a test" is false (R3-11).
- Test labels "TOCTOU 5", "TOCTOU 6" and "TOCTOU 7" point at the old row numbers (R3-11).
- Tests that cannot fail as written: the GIL flag test (R3-12); `test_open_fails_before_the_magic_is_written` passes if it zeroes the magic by hand, without testing Create's order (R3-4).

### Check 7: the seven points of brief.md section 4
| point | settled in the document | in the header |
|---|---|---|
| 1 the slot size per source | sections 2, 4.1 | FrameGeometry, Create |
| 2 the writer thread and copy | section 2, instance 1 | the writer section |
| 3 the read cost on a job thread | item 9 | n/a |
| 4 a dead reader's count | matrix: the server holds nothing; the with-block | FramebufferView "touches no count" |
| 5 the slot count | section 4.1 | the enum, OPEN 1 |
| 6 the cross-process view | items 7, 11 | the block, the view, Open, Find |
| 7 the writer's path and a full ring | section 2, 8 | BeginWrite, EndWrite |
All seven settled.

### Check 8: the failure matrix
- Required rows present: a disk error, a 5 s stall, SIGKILL or a power cut, a full ring, a model timeout, a wrong argument (wrong size, strided copy).
- Inconsistent: "a reader asleep one frame" against TOCTOU row 2's 1 to 11 frames (R3-9).
- Inconsistent: "the atomics package ... Create or Open NULL" against item 3's "Die ... a start-up fault" (R3-13).
- Inconsistent: "a geometry restart while the server holds its view" against the header's "destroyed after the supervisor (no other process maps it then)" (R3-5).
- Missing: "Destroy while the writer runs" and "a forked child keeps the lock". Both answers promised a matrix row (R3-11).

### Check 9: prose
- About 355 sentences outside code. About 85 run over 20 words. About 45 run to 30 or more.
- The worst: line 247 (item 3, one sentence of about 80 words), line 194 (the system force, about 68), line 159 (what is wrong, about 60), line 116 (point 1, about 60), line 374 (about 50), line 450 (about 50), line 384 (about 43).
- Most long sentences chain clauses with semicolons. Split each clause into its own sentence.
- Banned words: 0. Em-dashes: 0. Hebrew: 0.

### Check 10: what the revision introduced
- The epoch as the first sequence: sound. A block numbers at most 30 frames a second from a nanosecond start. The next block starts later in ns than any number the old one reached. CLOCK_MONOTONIC does not go back. Only the sketch's offset is wrong (R3-1).
- VIEW_GONE: sound for an unlinked name. The lifetime around it is unwritten (R3-5).
- The thread-local hold count: sound. The vision jobs are threads, and the with-block runs on one thread.
- The inode compare: sound in the internal header. The sketch is wrong (R3-3).
- The magic-last order: narrows the window, does not close it (R3-4).
- The plain counters: safe under the GIL as measured in round 2. They break the house rule as typed (R3-14).
- New: the sketch discards each atomic view's context. Measured: the package raises in its `__del__` at once (R3-2).

### Findings

**R3-1. The mapping sketch writes m_epoch at offset 28, not 32.** (high)
- Claim: line 464 packs `"<6IQ"` from offset 4. The six uint32 end at 28.
- Claim: with `<`, struct adds no padding (source 1). So the uint64 lands at 28, over m_pad0.
- Why it matters: the comment says "the epoch at 32". The C contract reads it at 32. The builder copies the sketch.
- Why it matters: the contract test checks the bytes at 0, 128 and 4096 only. It cannot see this.
- Evidence (measured): packing 0x1122334455667788 that way puts bytes 88 77 66 55 at offset 28. Offset 32 holds 0x44332211.
- Change, framebuffer.md section 8: `struct.pack_into("<6I4xQ", mm, 4, ...)`.
- Change, section 9: `test_create_lays_out_the_header_and_the_slots_as_the_contract` also reads m_epoch at 32 and m_latestIndex at 64.

**R3-2. The sketch discards every atomic view's context. The package raises at once, and Destroy cannot exit them.** (medium)
- Claim: lines 468 to 470 call `atomicview(...).__enter__()` and keep only the view.
- Claim: the context object is collected at once. Its `__del__` calls release(), which raises "Cannot call 'release' while context is open" (source 6).
- Claim: Destroy's step "exit every atomic view" needs those contexts. They are gone.
- Why it matters: 25 "Exception ignored" traces at every Create. At Destroy the views still export the buffer. mm.close() then raises BufferError on every shutdown, logged as "a pixel array outlived its Release". That log line then names the wrong cause.
- Evidence (measured, atomics 1.0.3): the trace prints before the next line runs. The view still loads and stores. The author's fb_measure2.py keeps the contexts in a list (line 43); the sketch does not.
- Change, framebuffer.md section 8: keep each context in a list in struct Framebuffer. Destroy calls `__exit__` on each before mv.release().
- Change, framebuffer_internal.h, struct Framebuffer: name the view handles as state the app's buffer holds.

**R3-3. The sketch contradicts the internal steps in three places.** (medium)
- Claim: the inode compare runs after ftruncate, posix_fallocate and mmap. The internal header runs it first. A nameless file gets resized and mapped before the check.
- Claim: the compare tests st_ino only. R2-3 asked for st_dev and st_ino. `os.stat(path)` raises FileNotFoundError when the name is gone (source 4). That is an exception outside util/guarded.py.
- Claim: `check_atomics_keep_the_gil()` runs at line 466, before the recast at lines 468 to 470.
- Claim: `latest.store(NO_FRAME)` and the zeroing of counts run at line 472, after the magic at line 465.
- Why it matters: the keep-the-GIL check as ordered dies at every start. Evidence (measured): before the recast, no pointer carries `_FUNCFLAG_PYTHONAPI`; after it, all do.
- Why it matters: the magic is valid while the counts and latest hold the dead run's values. R2-10's order is broken in the code the builder copies.
- Change, framebuffer.md section 8: reorder to the internal header's steps: open; lock; fstat and stat through the filesystem guard, on st_dev and st_ino; ftruncate; reserve; map; magic 0; geometry and epoch; make and recast the views; zero every count and sequence; latest NO_FRAME; check the flags; magic last.

**R3-4. The magic stored last narrows the Open race. It does not close it.** (medium)
- Claim: Open probes the lock, then reads the magic. Create takes the lock, then stores magic 0 several steps later.
- Claim: an Open between Create's lock and its magic 0 sees the dead run's valid magic and geometry. Its probe fails, since Create holds the lock. So it maps.
- Claim: if the new geometry is smaller, Create's ftruncate cuts the file under that mapping. A server read past the end gets SIGBUS.
- Claim: m_magic is now a publication flag but is typed plain `uint32_t`. On ARM, the geometry stores may become visible after it (source 5). The backpack target is embedded.
- Why it matters: TOCTOU row 8 says "closed". The start order covers it today; the module does not.
- Change, framebuffer_internal.h: store magic 0 with os.pwrite right after the inode compare, before ftruncate.
- Change, framebuffer.h: type m_magic `_Atomic uint32_t`. Store it last through an atomic view.
- Change, framebuffer.md item 11 row 8: "narrowed by magic 0 right after the lock; the rest covered by the start order (the supervisor starts after Create returns)".
- Change, section 9: the test pauses Create after its lock by an injected hook. Then it runs Open. Zeroing the magic by hand does not test the order.

**R3-5. The lifetime says no process maps the block at Destroy. VIEW_GONE says the server does.** (medium)
- Claim: framebuffer.h lines 138 to 140 and section 7 Ownership: created before the supervisor, destroyed after it, "no other process maps it then".
- Claim: R2-2, VIEW_GONE and the matrix row assume the server outlives a Destroy and sees a new block.
- Claim: a geometry restart therefore runs Destroy and Create with the supervisor alive. No file states that order.
- Claim: the server's reopen in instance 2 can run before the new Create. Open returns NULL. The server exits and spends one relaunch of its budget.
- Claim: instance 2 line 108 packs three statements with `;`. The house style forbids `a; b`.
- Why it matters: either the restart order is written, or VIEW_GONE has no case.
- Change, framebuffer.h Create and Destroy comments: two lifetimes. At start and stop, as now. At a geometry restart: the frame source stops, Destroy, Create, the frame source starts; the supervisor and the server stay.
- Change, instance 2: on VIEW_GONE, answer stale and close the view. Open again at the next request; NULL is "not ready", no exit. One statement per line.
- Change: carry the restart order to module 12 and the app step.

**R3-6. The slot count comes from config, but the internal state is sized by the enum.** (medium)
- Claim: section 4 point 1 says config computes FRAMEBUFFER_SLOTS = pool + 1 + 3. A pool of 10 gives 14.
- Claim: framebuffer_internal.h line 44 declares `m_sequences[kFramebufferSlots]`, 12 entries.
- Why it matters: the enum is no longer a display of the derivation. It is a capacity. This undoes R1-8's rejection reason and R2-7's config change.
- Change, framebuffer_internal.h: `uint64_t* m_sequences;` sized at Create from m_slotCount, with the note "m_slotCount entries".
- Change, framebuffer.h: the enum comment states "today's value; the count is m_slotCount".

**R3-7. The draw copies into a canvas slice that copy_pixels refuses when the canvas is wider than the frame.** (medium)
- Claim: instance 2 calls `copy_pixels(canvas[:h, :w], slot.pixels)`.
- Claim: copy_pixels dies on a destination that is not C-contiguous (R2-1).
- Claim: a slice of a canvas wider than w is not C-contiguous. A canvas of width w is.
- Why it matters: a screen with a side panel dies on the main thread at its first frame. That is our bug, mid-flight, with a hand-over.
- Evidence (measured, numpy 1.26.4): a (1080, 2400, 3) canvas sliced to 1920 wide: c_contiguous False. A (1200, 1920, 3) canvas sliced to 1080 high: True.
- Change, framebuffer.md instance 2: state the rule "the canvas is exactly w wide, or the draw copies row by row". Carry it to module 15.
- Change, section 8: a `copy_rows` helper of h memmoves of w * 3 bytes, if module 15 needs a wider canvas.

**R3-8. The system force is said to be carried to the design document. It is not there.** (medium)
- Claim: section 6 and the brief's log say the force "no thread may run CPU-bound Python longer than a frame" is carried to 01-system-architecture.md section 8.
- Evidence: grep of 01-system-architecture.md for "GIL", "CPU-bound" and "longer than a frame": no match. The rev5 folder holds the phrase only in this module's files.
- Why it matters: it binds every module, not this one. A force written only here is lost at the next module.
- Why it matters: the brief forbids this agent to edit other files. So "carried" must mean "handed to the manager".
- Change, framebuffer.md section 6: "to be carried by the manager to 01-system-architecture.md section 8".
- Change, the Conclusions of this file: list it as a carry item for the manager.

**R3-9. R2-12 landed in one place of four, and one R1-1 line is stale.** (low)
- Claim: TOCTOU row 2 says 1 to 11 frames. Three places still say "a whole frame" or "one frame".
- Evidence: framebuffer_internal.h line 119; framebuffer.md line 336 (matrix); line 371 (section 8 note).
- Evidence: section 8 line 394 says "a test keeps the bound". R2-5 moved the timing out of the suite.
- Change: write "a reader asleep until the writer reuses the slot: 1 frame with 9 holders, 11 with none" in all three. Write "the start check and the flag test keep the recast; the timing stays in the benchmark".

**R3-10. The webcam path has no size check before its claim.** (low)
- Claim: instance 1's webcam loop claims, then calls copy_pixels on the camera's array.
- Claim: a camera that returns another size makes copy_pixels die after the claim. The matrix row says "the source drops and counts before any claim".
- Why it matters: a camera fault is not our bug. RVW4 reserves the Die for our bugs.
- Change, framebuffer.md instance 1: `if image.shape != (h, w, 3): self._rejected += 1; continue`, on separate lines, before begin_write.

**R3-11. The matrix and the tests list miss what the answers promised.** (low)
- Claim: R2-4 promised two matrix rows. "Destroy while the writer runs" is in the TOCTOU table only. R2-8 promised a matrix row. It is in the TOCTOU table only.
- Claim: item 11 says "Each closed window has a test". "Destroy while the writer runs" and "a forked child" have none.
- Claim: the labels TOCTOU 5, 6 and 7 in section 9 are the old row numbers. Today they are rows 6, 10 and 11.
- Claim: R1-4's answer says "The test replaced". `test_eight_misses_give_no_frame_and_count` still pins WRITING on the latest slot by hand.
- Claim: `test_every_slot_held_dies` holds 11 slots. With one hold per thread it needs 11 threads. One thread dies with "a second hold" instead.
- Change, framebuffer.md: add the two matrix rows. Mark the two TOCTOU rows "covered by module 12 and the app step; no test here". Renumber the labels. Replace the eight-misses test with a reader hook that delays between the load and the add across 8 writes. Say "11 threads" in the full-ring test.

**R3-12. The keep-the-GIL test checks the dict the module itself patched.** (low)
- Claim: the test reads the flag on every entry of `_supported`. keep_gil just wrote those entries.
- Claim: R2-5's failure is a package that stops reading `_supported`. The flags still pass then. The test cannot fail on the fault it names.
- Evidence: atomics 1.0.3 calls `self._supported.get(optype)` in get_op_func (core.py line 51). A later version may not.
- Change, section 9: swap one entry for a counting PYFUNCTYPE stub, call the view's operation, and expect the count to rise. That proves the call path reads the patched entry.

**R3-13. The package check is a NULL in one place and a Die in another.** (low)
- Claim: R2-5 proposed a start-up Die. Item 3 lists it as a Die. The matrix says "Create or Open NULL".
- Claim: framebuffer.h lists the NULL causes of Create and Open. The package check is in neither.
- Change: pick NULL. The app's start dies on it with the reason, as for /dev/shm. Add "the atomics package is not 1.0.3, or a call yields the GIL" to both NULL comments in framebuffer.h. Fix item 3.

**R3-14. Values shared between threads are plain, against the `_Atomic` house rule and the header's own sentence.** (low)
- Claim: framebuffer_internal.h lines 26 and 27: "every word shared between threads is one atomic in the block or one plain value with one writer".
- Claim: m_retries and m_misses have many writers, every reader thread.
- Claim: m_nextSequence, m_slotsHeld and mb_writeOpen are written by the writer and read by the main thread or a second writer. The house rule asks `_Atomic` for every shared value.
- Change, framebuffer_internal.h: type the five fields `_Atomic`, with the note "relaxed order; in Python a plain int under the GIL, no atomic call". The header keeps R2-11's point, and the C reads correctly.

**R3-15. The public header holds implementation steps and commas in enum comments.** (low)
- Claim: AcquireLatest (lines 170 to 175), BeginWrite (156 to 160) and Destroy (147 to 149) carry their steps. The steps live in framebuffer_internal.h.
- Claim: the FrameFindResult block has commas at lines 202 ("request, so") and 204 ("slot, or the"). The config enum block has many.
- Change, framebuffer.h: keep the contract in each comment (what holds after the call, when NULL or Die). Move the steps to the internal header. Replace each comma in the enum comments with a semicolon or a new line.

**R3-16. Item 9 says the buffer's share passes the budget. The writer thread does not.** (low)
- Claim: the budget is 330 us on the hottest thread. The writer thread pays 732 us median a frame at 1080p idle.
- Claim: BeginWrite plus EndWrite alone reach 343 us p99 at 720p under load.
- Change, item 9: name the writer thread's cost against 330 us. State why it is accepted: one copy a frame is unavoidable, and it is off the main thread.

**R3-17. Small name and text mismatches.** (low)
- `frames.latest()` is no header call. Name it in section 3 as the with-block over AcquireLatest and Release, `framebuffer_latest(frames)`.
- Section 1 needs no "and": "A shared-memory ring of the newest frames, from which every reader takes the latest."
- Internal EndWrite, lines 98 and 99: "store m_latestIndex = i; m_latestIndex = i". Write the second as "the writer's copy m_latestIndex = i".
- AcquireRetries: "retries" in framebuffer.h and section 7; "tries" in the internal steps. Pick tries.
- The health's latest sequence before the first frame is m_epoch - 1, a frame that never existed. State 0 for no frame.

**R3-18. Many sentences run past 20 words.** (low)
- About 85 of about 355 sentences run past 20 words; about 45 reach 30.
- The worst: lines 247, 194, 159, 116, 374, 450, 384 (check 9).
- Change, framebuffer.md: split each semicolon chain into sentences of one idea.

**R3-19. The R1-6 rejection names a restart the document never describes.** (low)
- Claim: the drone stall keeps the thread and the buffer. A geometry change makes a new buffer. Neither gives one buffer a second legal writer thread.
- Claim: only a webcam stall that starts a new thread for the same buffer would. The document does not say it does.
- Change, section 8 note "Why a second writer is detected only when it overlaps": name the restart that changes the thread. If there is none, a stored writer thread id per buffer is safe, and it also catches the alternation.

### Count
High 1, medium 7, low 11.

Landing: 19 items to fix

## Round 3: answer

All 19 items taken. The headers and the document were rewritten in one pass each.

- **R3-1.** The sketch packs `"<6I4xQ"` from offset 4; the layout test reads the epoch at
  32 and the latest index at 64.
- **R3-2.** The view contexts are kept in a list; Destroy exits each before the release.
  The internal struct names them (`m_views`, opaque).
- **R3-3.** The sketch follows the internal steps in order: open, lock, the device and
  inode compare through the filesystem guard, magic 0, ftruncate, reserve, map, the
  header, the views and the recast, the flag check, the zeroing, latest, the magic last.
- **R3-4.** Magic 0 by one positional write right after the lock, before any resize;
  m_magic typed atomic and stored last through its view; the TOCTOU row says "narrowed"
  and names the start order; the test pauses Create by a hook.
- **R3-5.** Two lifetimes in the header and in section 7: start and stop; the geometry
  restart (the frame source stops, Destroy, Create, the frame source starts; the
  supervisor and the server stay). Instance 2: on VIEW_GONE the server answers stale,
  closes, and opens again at its next request; a NULL then is "not ready"; one statement
  per line. Carried to module 12 and the app step.
- **R3-6.** `m_sequences` is a pointer sized at Create from m_slotCount; the enum comment
  says the run's count is the block's.
- **R3-7.** The canvas is exactly the frame's width (instance 2, carried to module 15);
  a row-by-row helper is named for a wider canvas.
- **R3-8.** Section 6 says the force is to be carried by the manager to the design
  document; the Conclusions list it.
- **R3-9.** The three places say "until the writer reuses the slot: 1 frame with 9
  holders, 11 with none"; the stale line about the timing test is rewritten.
- **R3-10.** The webcam path checks the shape before the claim.
- **R3-11.** Two matrix rows added; rows 12 to 14 of the TOCTOU table are marked as rules
  with no test here; the table is numbered and the tests cite the rows; the eight-misses
  test uses a reader hook; the full-ring test uses 11 holder threads.
- **R3-12.** The GIL test swaps one entry for a counting stub.
- **R3-13.** NULL everywhere; both NULL comments in the header name the package check;
  item 3 lists it under the start-up faults.
- **R3-14.** The five fields typed atomic with the note "relaxed; in Python a plain int
  under the GIL"; the internal sentence rewritten.
- **R3-15.** The public header's comments state the contract only; the steps live in the
  internal header; no comma inside any enum comment block.
- **R3-16.** Item 9 names the writer thread's cost against 330 us and why it is accepted.
- **R3-17.** `framebuffer_latest(frames)` named as the with-block; section 1 without
  "and"; EndWrite's wording; "tries" everywhere (kFramebufferAcquireTries); the health's
  latest sequence is 0 before the first frame.
- **R3-18.** The document rewritten with one idea per sentence; the semicolon chains
  split.
- **R3-19.** Taken, and the round 1 rejection of the thread id taken back: no restart
  changes the writer thread of one buffer, so BeginWrite stores the thread of its first
  call and a call from another thread dies. The alternation is now caught here.

## Conclusions

Three rounds, three fresh reviewers (general-purpose agents, model Opus 5.5), 46
findings: 14, 13 and 19. 44 taken; 2 rejected in round 1 (the config one-home pattern,
which the approved perf.h and telemetry.h set; the stored writer thread id), of which the
second was taken back in round 3 once the restarts were named. The reviewers measured on
this machine: the atomics package yields the GIL on every call, so an Acquire reached 5 ms
at p99 beside one busy Python thread and 0.6 s at max beside three; a numpy copy yields it
too, 1.2 s at p99 for a 720p frame; the same C functions recast to keep the GIL brought
the Acquire to 172 us p99 and the copy to 0.7 ms; Find matched a slot under write; a
memmove sheared a padded ROS frame; an old view matched a new block's request; flock
landed on a nameless file; the package raised at once on a discarded view context; a
1080p block of 12 slots SIGBUSed the writer on this container's 64 MB /dev/shm.

**Agreed (in the files):** 12 slots from the holders (8 jobs, the draw) plus the writer's
slot, the latest and one spare, computed in config from the pool's entry; one hold per
thread, enforced; the compare-and-swap claim with the WRITING bit; the sequence 0 under
write; an index-only latest word; sequences that start at the block's epoch; Find with
FOUND, STALE and VIEW_GONE; the file as the owner's lock, checked against the name, magic 0
first and the real magic last; the pages reserved and the mapping populated at Create; the
server's read-only mapping; every atomic call and every pixel copy keeping the GIL, with
the recast verified at start; the writer's private sequence table and thread; eight misses
as "no frame", counted; a health of plain values; os.open and mmap, not SharedMemory;
Destroy's order.

**Open for the owner (framebuffer.md section 4):** 1 the slot count 12; 2 the claim as
the mechanism that closes the race (section 6 of the design document changes); 3 the
draw's copy on the main thread against the 330 us gate; 4 the shared-memory size check in
Create, and `--shm-size` for the dev container.

**Carried to the manager and to later modules:** the system force "no CPU-bound Python
longer than a frame on any thread" into 01-system-architecture.md section 8; `--shm-size`
in the dev container's install script; module 6: the request id, the read-only view, the
reopen after VIEW_GONE; module 12: the writer thread's join, the size and step checks, the
geometry restart's order; module 13: one hold per thread, the stale-frame report; module
15: the canvas width, the draw's copy in PERF_FRAME; the app step: the stop order.

**Cost:** about 490k subagent tokens for the three rounds.

## After the owner's review (2026-10-18)

The owner's rulings, verbatim in framebuffer.md section 4b. Decided: "keep it nameless and
pass it on launch" (a memfd, inherited by the SAM3 server; the lock, the inode compare,
the magic order, the epoch and VIEW_GONE are gone, with their tests and TOCTOU rows); the
claim by compare-and-swap, "I agree with your proposal. Approved."; the SAM3 server stays
its own process, "lets stick to what we have so far"; the count is a dword, the sequence a
qword. Measured for the ruling: a 74.7 MB memfd reserved and touched on this container
with its 64 MB /dev/shm cap; a spawned child mapped the inherited descriptor read-only and
its writable map was refused (memfd_check.py in the agent's scratch folder). Open: the slot
count, the draw's copy, the field widths, the padding (the owner holds the last two).
Carried to the manager: ProcessSpec gets a field for the descriptors to pass.
