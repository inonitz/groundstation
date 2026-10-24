# the framebuffer: the shared-memory ring of frames (rev5 module review, started 2026-10-17)

The headers are `framebuffer.h` (the public contract and the block layout) and
`framebuffer_internal.h` (the state behind the handles, the writer's choice as a pure
function, the steps of every call, the TOCTOU list). The design document is
`../../01-system-architecture.md` (sections 2, 3, 6, 8, 9). Below it: perf (approved).
Above it: the frame source (module 12), the vision jobs (module 13), the SAM3 server
(module 6), the screen (module 15). The state: designed by the owner-launched agent (PAR1).
Three reviewer rounds (`../../test/framebuffer-review.md`: 46 findings, 44 taken). Then the
owner's review, 2026-10-18: the block is nameless and passed at launch; the claim is
approved; the SAM3 server stays its own process. Open: the slot count, the draw's copy, the
field widths, the padding (section 4).

## 1. The job, in one sentence
A shared-memory ring of the newest frames, from which every reader takes the latest.

## 2. The picture
```
 THE APP (one process)                                     THE SAM3 SERVER (our process)
 ---------------------                                     -----------------------------
 frame source thread    main thread      8 job threads       at a request carrying seq:
 the only writer        the draw         one hold each         Find(seq) in the slot headers
   |                       |                 |                 read the pixels in place
   | BeginWrite            | Acquire         | Acquire         answer the job
   | copy the pixels in    | copy to canvas  | send seq ------>  (touches no count)
   | EndWrite              | Release         | wait the reply        |
   |                       |                 | Release               |
   v writes                v reads           v reads               v reads, read-only map
 +------------------------------------------------------------------------------------+
 |  ONE NAMELESS SHARED-MEMORY BLOCK (a memfd; the server inherits its descriptor)    |
 |  header : width, height, slots, latestIndex                                         |
 |  slot[i]: sequence (a dword), count (a dword), capturedAt   i = 0 .. 11                   |
 |  pixels[i]: one frame, 1920 x 1080 x 3 bytes          12 x 6.2 MB = 75 MB           |
 +------------------------------------------------------------------------------------+

 The writer takes the oldest slot whose count is 0, never the latest slot.
 A reader takes the latest slot: count + 1, use the pixels, count - 1.
 The writer claims a slot by one compare-and-swap of its count dword: 0 -> WRITING.
 No free slot is a bug: Die (FR1). Every atomic call and every copy keeps the GIL.
```
The threads that touch a slot: the frame source thread (the writer), the main thread (the
draw), the 8 job threads (the holds). The processes: the app (read-write), the SAM3 server
(read-only). The rates: the writer and the draw at 30 a second. A job acquires once per
pass, at most 8 a second over all jobs. The sizes: a slot is 6.22 MB at 1080p (the drone)
and 2.76 MB at 720p (the webcam by config). The block is 74.7 MB and 33.2 MB.

## 3. How a caller uses it: two instances, in the Python of the build
**Instance 1: the app's start, then the two frame sources writing.**
```python
# app/main.py, at start: the size first, then the buffer, then telemetry, then the supervisor
width, height = probe_source_size(config.VIDEO)      # the webcam: open, read one; the drone: 1920x1080
frames = framebuffer_create(FrameSize(width, height))   # a nameless block
if frames is None:                                   # the pages, or the atomics package
    die("framebuffer: cannot reserve 75 MB of shared memory")
telemetry = telemetry_create(session_dir, width, height, info)
fd = framebuffer_descriptor(frames)
specs.append(sam3_process_spec(log_dir, frames_fd=fd))   # pass_fds=[fd]; "--frames-fd", str(fd)
supervisor = supervisor_create(specs)                # the server inherits the descriptor

# video/frame_source.py, the webcam: its own thread, the only writer
def _run(self):
    while not self._stop.is_set():
        ok, image = self._capture.read()             # OpenCV's own array, 30 a second
        if not ok:
            continue
        if image.shape != (self.height, self.width, 3):
            self._rejected += 1                      # a camera fault is not our bug: dropped, counted
            continue
        at = perf_now()
        w = framebuffer_begin_write(frames)          # the oldest free slot, claimed; Die when none
        copy_pixels(w.pixels, image)                 # 0.7 ms at 1080p; the GIL is kept (section 8)
        framebuffer_end_write(frames, w, at)         # sequence, capturedAt, the bit off, then latest

# video/frame_source.py, the drone: the callback runs on the ROS executor thread
def _on_image(self, msg):                            # the main thread plays no part
    if (msg.height, msg.width, msg.encoding) != (self.height, self.width, "bgr8"):
        self._rejected += 1                          # a wrong frame is the source's drop, counted
        return
    if msg.step != self.width * 3 or len(msg.data) != msg.height * msg.step:
        self._rejected += 1                          # a padded step is not copied: dropped, counted
        return                                       # checked BEFORE the claim: no claim is left open
    w = framebuffer_begin_write(frames)
    copy_pixels(w.pixels, np.frombuffer(msg.data, np.uint8).reshape(self.height, self.width, 3))
    framebuffer_end_write(frames, w, perf_now())     # 0.7 ms at 1080p, on this thread
```
**Instance 2: a job holds its slot across the SAM3 request; the draw; the server's read.**
```python
# perception/jobs.py, a highlight pass on a pool thread
# framebuffer_latest(frames) is the with-block over AcquireLatest and Release
with framebuffer_latest(frames) as slot:             # __exit__ releases, also on an error
    if slot is None:
        return NOT_READY                             # no frame yet, or 8 misses in a row
    reply = sam3.detect(req, slot.sequence, concepts, priority, timeout=SAM3_TIMEOUT)
    telemetry_vision_pass(telemetry, VisionPass(..., frame=slot.sequence,
        captured_at=slot.captured_at, bgr=slot.pixels, width=w, height=h,
        stride=w * 3, ...))                          # the sink copies during the call
# released here: the server answered, failed, or the timeout passed; 0.4 to 4 s held
# a reply that lands after the timeout is dropped by its request id (module 6)

# app/screen.py, the main thread, every frame; the canvas is exactly w wide (module 15)
with framebuffer_latest(frames) as slot:
    if slot is not None:
        copy_pixels(canvas[:h], slot.pixels)         # the one copy on the main thread (FB6)
draw_views(canvas, views)
cv2.imshow(WINDOW, canvas)
health = framebuffer_read_health(frames)             # four plain loads; a change -> a chat line

# sam3/server.py, our process: the view once at start, then per request
view = framebuffer_open(args.frames_fd)              # read-only; None -> exit 1; relaunched
...
ref = framebuffer_find(view, request.sequence)       # None: the job released, or under write, or 0
if ref is None:
    reply_stale(request)
    return
boxes, masks = model.detect(ref.pixels, concepts)    # the preprocess reads the pixels in place
```

## 4. The open points for the owner
Decided 2026-10-18 (the owner's words in section 4b, the ledger FB1 to FB8): the block is
nameless and passed at launch; the claim by compare-and-swap; the SAM3 server stays its
own process; the slot count 12 ("OPEN 1 - Approved."); the draw's copy ("I agree.
Closed."); the field widths and the padding by the owner's rule (FB8: performance over
3,840 bytes; the layout stays as the owner's edit has it). Nothing is open.
1. **The slot count: 12, not 32.** The problem: the design says 32. The holders are fewer
   since telemetry copies (RVW3). The count derives from the holders. 8 jobs and the draw
   hold at most 9 slots at once. The writer fills a 10th. The latest slot, which the
   writer never takes, is an 11th. One spare is the 12th. A bigger ring buys nothing. The
   writer always publishes the newest frame, and a slot's age does not matter. A smaller
   ring than 11 makes a legal load die. The derivation rests on ONE hold per thread at a
   time. A thread-local count makes a second hold a bug that dies. So a job that would
   keep a gate frame while it tracks must release first (module 13). config computes
   FRAMEBUFFER_SLOTS from the pool's own entry (pool + 1 + 3). A pool of 10 gives 14
   slots, and the block carries its own count. Decided: `kFramebufferSlots = MaxHolders
   + 3`, 12 for a pool of 8; 75 MB at 1080p (FB5).
2. **Decided: the writer claims a slot in one step.** The owner, 2026-10-18: "I agree with
   your proposal. Approved." The steps, for the record. The Writer is the frame source
   thread. R is one job thread. Slot 5 holds frame 100; its count is 0; the latest slot
   is 5. Without the claim: (1) R reads the latest index, 5, and has not yet added 1. (2)
   The scheduler pauses R; the Writer publishes into other slots; slot 5 becomes the
   oldest free slot. (3) The Writer looks at slot 5: count 0; it decides to write there.
   (4) R wakes, adds 1, re-reads the sequence: still 100; R starts reading. (5) The Writer
   writes over slot 5: R reads a torn frame. The re-read saw nothing, since the write
   had not started. With the claim, step 3 is one compare-and-swap on the count dword:
   "if 0, set WRITING". Timeline A, R first: the count is 1, the swap fails, the Writer
   picks another slot. Timeline B, the Writer first: R's add returns WRITING, R subtracts
   1 and takes the latest slot again. No third timeline exists: both act on one dword,
   one after the other. Section 6 of the design document gets the corrected words at the
   app step.
3. **The draw's copy on the main thread (FB6).** The owner, 2026-10-18: "We said the
   budget is 330 microseconds, and now you tell me that the p99 is 1.2 MILLISECONDS, with
   ~0.4ms ON AVERAGE! How is this acceptable if we have a defined budget?" The facts. The
   buffer's own cost on the main thread is 26 us. The copy is the draw's work: the
   overlays cannot paint into a shared slot, so the frame and the overlays meet in a
   canvas. Measured 2026-10-18 on a virtual screen (xvfb, 1080p, 300 frames, median /
   p99 / max us): the copy with the GIL kept 670 / 1202 / 4376; 30 overlay calls 234 /
   346 / 1130; cv2.imshow 254 / 459 / 730; cv2.waitKey(1) 3332 / 4995 / 5261; the whole
   draw 4621 / 6447 / 9014. So the draw already spends 4.6 ms of every 33 ms frame on the
   main thread today, and the copy is a seventh of it. The 330 us gate is a module's
   overhead per call; it was never the draw's budget. The options. (a) Keep the copy as
   the draw's work, inside the screen module's budget (module 15), and report it in
   PERF_FRAME. (b) Move the whole draw off the main thread: a screen thread owns the
   canvas, gets a copy of the views once a frame, and runs the copy, the overlays, imshow
   and waitKey. The main thread then pays none of the 4.6 ms. This changes section 3 of
   the design (the main thread draws) and belongs to module 15. (c) Make the copy cheaper:
   not possible, it is bound by memory bandwidth at about 0.3 ms for 6 MB. Decided: (a); the owner, "I agree. Closed." Option (b) was withdrawn: the draw
   stays on one thread, the main thread (the owner, the fifth round).
4. **The field widths.** The owner, 2026-10-18: "do images actually go over 64k that they
   actually need 32 bit integers?" No. No source passes 65535. Decided, by the owner's own
   edit: FrameSize holds uint16_t width and height; the slot count, the slot bytes and the
   pixel offset stay 32 bits (6,220,800 slot bytes). The sequence is a dword: at 30 a
   second it lasts 4.5 years (FB7).
5. **The padding.** The owner, 2026-10-18: "Why so much padding? FramebufferHeader could
   easily be < 64Bytes, if not exactly a cache line. Same thing with FrameSlotHeader!"
   The padding puts m_latestIndex and each slot's count on its own cache line, against a
   false share: two atomic words on one 64-byte line written by two cores. Decided by the
   owner's rule (FB8: "performance is more important to me ... If the performance is
   negligible compared to the memory saved ... keep it small. Otherwise, make them as
   fucking large as you want"): the compact layout would save 3,840 bytes of 74.7 MB; the
   performance side is zero in the Python build and the standard cache-line guard in a C
   build; the tie-breaker is performance, so the layout stays: a 128-byte header, 64-byte
   slot headers, the pixels on a page.

## 4b. The owner's review (2026-10-18), verbatim, with the answers
First round, 8 points.
1. "Why would the width and height be 32 bit? do images actually go over 64k that they
   actually need 32 bit integers?" No. Point 4 above.
2. "Why so much padding? FramebufferHeader could easily be < 64Bytes, if not exactly a
   cache line. Same thing with FrameSlotHeader!" Point 5 above.
3. "Did you actually consider YAGNI & KISS when developing the framebuffer, or are all of
   your design decisions delibarate & based on tests made?" For the core (the ring, the
   counts, the claim) the design is as simple as the problem, and each piece closes a
   measured fault. For the edges it was not. Five start-up guards (a lock, an inode
   check, a magic written twice, a stale-file path, a reopen path) existed because the
   block had a name in the file system. The owner's ruling below removed the name, and
   the five guards with it.
4. "Your diagram is extremely condensed and not easy to read at all." Redrawn; "way
   better! Thank you. Understood."
5. "Why do you keep talking about 720p if we use 1080p everywhere?" The config requests
   720p (constants.py: 1280 x 720). The camera delivers 1920 x 1080 when asked, measured
   2026-10-18 under the webcam lock: 19.3 frames a second at both sizes in this room. The
   rate is the room's light, not the size (HISTORY: 15 to 18 dim, 30 in daylight). So 720p
   is a config choice, not a camera limit. The owner: "Good!" The document leads with
   1080p.
6. "What is the idea inside sam3/server.py for the framebuffer?" and "Are we even using a
   separate process for SAM3? Why not just use a different thread ... avoid the
   supervisor completely?" The server does not acquire; the job did. The server maps the
   block once at its start and finds the slot by the request's number. The measured
   facts (research-complete-sam3-assessment.md R9, analysis 8, 9, 14): a SAM3 pass in the
   app's process does NOT slow the frame loop (torch releases the GIL on the GPU); the
   LOAD does (8 to 10 frames over 100 ms, max 1.8 s, at start-up; 0 in its own process);
   a GPU fault in-process ends the app, in its own process it is a restart. The
   supervisor cannot go away: the keyboard hook, the ASR node and the gstreamer receiver
   are C++ ROS 2 nodes and the phone mock is a server. The owner: "I understand. In that
   case, lets stick to what we have so far." Decided: the SAM3 server stays its own
   process.
7. "can you please rename frame_buffer to framebuffer" Done. "Good".
8A. "how many frames can we put into this framebuffer ... How much temporal data can we
   ACTUALLY hold?" One frame, for every reader: the latest. The ring is not a history
   (FR1). The 12 slots exist for holders, not for time. The owner: "Then nevermind, I'm
   just paranoid."
8B. The claim: point 2 above. The owner: "Timeline a - Good; timeline b - Good! Please,
   its not a word. by common convention, its a dword." The count is a dword, the
   sequence a qword, in the header's words now. "I agree with your proposal. Approved."
8C. "Why should it copy? can't it share the data?" Point 3 above. "Damn. I understand."
8D. "Why go through the hoops of the file system?" The hoops came from the name, not
   the descriptor. A nameless block (memfd_create) has no name, dies with its last
   mapping, cannot be stale, cannot collide, and is not under the /dev/shm cap. The SAM3
   server inherits the descriptor at launch and reopens it read-only. "Do we actually
   have such a situation that the framebuffer shape changes?" No. Nothing changes a size
   mid-run; a frame of another size is dropped and counted. So the epoch, the VIEW_GONE
   result and the reopen had no case and are gone. The owner: "keep it nameless and pass
   it on launch" and "I agree with this proposal." Measured 2026-10-18: a 74.7 MB memfd
   reserved and touched on this container with its 64 MB /dev/shm cap; a spawned child
   mapped the inherited descriptor read-only and its writable map was refused.

### The owner's fourth round (2026-10-18), verbatim, with the answers (FB7)
- "I don't see FramebufferDescriptor anywhere in your file." It is at line 147 of the
  header as edited: `FileDescriptorType FramebufferDescriptor(const Framebuffer* f);`.
- "OPEN 1 - Approved." FB5.
- "OPEN 3 - ... How is this acceptable if we have a defined budget?" Point 3 above, FB6.
- "OPEN 4 - I'll edit the file myself. Watch the changes carefully." The edits seen:
  FrameSize with uint16_t fields; FileDescriptorType; m_sequence a dword;
  ReadOnlyFrameReference and ReadWriteFrameReference; FramebufferHealthStatus;
  FramebufferCreate(FrameSize). The comments are rewritten once the edit is done.
- "Why is m_sequence 64 bit? ... Will is ever surpass 2**32 - 1???" No. At 30 a second a
  dword lasts 4.5 years. The owner's dword stands.
- "Framebuffer has so many atomic variables. Are they actually read, that we can have
  false sharing situations? Is this relevant?" Three are shared: m_slotsHeld (the writer
  stores, the main thread loads), m_retries and m_misses (readers add, the main thread
  loads). Three are the writer thread's alone and need no atomic: m_nextSequence,
  m_writerThread, mb_writeOpen. False sharing is not relevant: they live in the app's
  private struct and change at most 30 times a second.
- "there seems to be a lot of redundant design in the framebuffer with regards to
  variables." Yes. The writer's copies (m_sequences, its m_latestIndex, m_nextSequence)
  exist only to save Python atomic loads at 3 to 5 us each: 12 loads a frame, 36 us,
  1 ms a second on the writer thread. Not worth three fields. Proposed: drop all three;
  the writer reads the block; the next sequence is the latest slot's sequence plus 1.
- "What is the layout of the whole data structure in memory?" The byte map is in
  section 7b item 7.
- "Why so many pointers everywhere? is it because everything is inline in the same
  buffer and we need pointers to easily access structures inside the shared memory
  region?" Yes. The three pointers of FramebufferMap are the mapping's base plus two
  offsets the header already holds. Proposed: one base pointer; the offsets from the
  header.
- "Why does the Readonly require the sequence but the writer doesn't?" A reader must
  name the frame it holds: the job sends the number to the SAM3 server and telemetry
  records it. The writer gets the number only at EndWrite, at the publish, so no number
  exists before the frame is complete (the 0-under-write rule rests on that). The
  asymmetry is deliberate.
- "Why does the ROFrameRef need a perf timestamp?" It is the frame's capture time, for
  telemetry's record and for a job to judge a stale frame during a video stall. It is
  copied at Acquire so the reader does not read the slot header again. It can go; the
  reader can read it by the index.
- "Your comments are dogshit. The Code should be self documenting, unless there is
  something non-obvious that happens when using the contract" The rule taken: a comment
  only for a non-obvious effect of a call (a Die, a NULL cause, a kernel fact such as the
  memfd, the read-only reopen, the reserved pages) or a usage pattern.
- "For the manager - No, If we will finish this header, then you should perform this
  yourself, write everything in the ledger" Taken: the ledger rows FB1 to FB7 are mine.

### The owner's fifth round (2026-10-18), verbatim, with the answers
- OPEN 3: "I think you forgot that drawing usually needs to happen on the main thread,
  or at the bare minimum, on a single thread and no where else, with a handoff ..." and
  "I genuinely don't understand what issue the issue here is ... If this is just a fact
  of life that doesn't bother us, I don't see why extra effort needs to be spent on
  this." The owner is right on both. Option (b) is withdrawn. There is no issue: a frame
  with overlays needs one copy per frame on the drawing thread, today as in this
  design. I raised it only because the gate asks the author to prove 330 us per call,
  and the copy is the draw's cost, not this module's. Proposed: close OPEN 3 as
  accepted; the copy is counted in the screen module's budget and shown in PERF_FRAME.
- OPEN 4: the dword sequence "Ok"; the atomics cut to the three shared values "Ok"; the
  three writer copies dropped "Yes"; the pointers kept; the comments rule "Ok". Decided.
  The memory layout and the reference asymmetry: explained again in the reply of
  2026-10-18 and in section 7b item 7. The timestamp in the read-only reference:
  "Clarify": the capture time lives in the slot header; the reference carries the slot
  index; so a reader can read `slots[ref.m_index].m_capturedAt` from the block while it
  holds the slot, since the writer cannot touch a held slot. The field in the reference
  is a copy made at Acquire for convenience. Open until the owner picks: keep the copy,
  or a FramebufferCapturedAt(f, ref) read on demand.

### The owner's sixth round (2026-10-18), verbatim
- "OPEN 3 - I agree. Closed." FB6 closed.
- "OPEN 4 - performance is more important to me. If the performance is negligible
  compared to the memory saved ... then keep it small. Otherwise, make them as fucking
  large as you want, to make sure performance is optimal for mulit-threaded scenarios."
  Applied (FB8): the compact layout would save 3,840 bytes of 74.7 MB. The performance
  side is zero in the Python build (the GIL serializes the app's atomic calls; the
  server only loads) and the standard cache-line guard in a C build. The tie-breaker is
  performance: the layout stays as the owner's edit has it.

### The owner's seventh round (2026-10-18): the header edit done, applied
The owner: "I'm done with the editing". Watched and kept: FrameSize with uint16_t fields;
FileDescriptorType; the dword sequence; ReadOnlyFrameReference and
ReadWriteFrameReference; FramebufferHealthStatus; FramebufferDimensions and
FramebufferViewSize; Create by FrameSize. One slip fixed: the slot header summed to 56
bytes (4 + 4 + 8 + 40); the pad is 48, so the slot header is 64 bytes again (asserted by
the compiled size program: header 128, slot 64, the sequence at 0, the count at 4, the
capture time at 8). Applied: the atomics in struct Framebuffer cut to the three shared
values; the writer's three copies dropped (the next sequence is the latest slot's plus
1); the pointers kept; every comment rewritten to intent only; Find and the health take
a dword sequence. The timestamp stays in the read-only reference (no ruling yet; "Clarify"
answered in the fifth round).

## 5. Today
- `video/video.py`: `_latest` under a lock. `read()` runs on the main thread each frame.
  `snapshot()` copies the whole frame for every request, on the caller's thread.
- `video/ros_stream.py`: the ROS callback reshapes the message under the lock. `read()`
  copies the frame on the main thread: 6 MB per frame at 1080p.
- `perception2/vision.py`: `_submit` takes a snapshot per request on the main thread. The
  count job takes one more per frame. The frame then travels by reference into the
  in-process SAM3 model.
What is wrong: a copy per frame and per request on the main thread. No "latest" exists
across a process boundary, so the SAM3 server cannot be a process. Frames live as long as
any Python reference does, so old frames lie around (FR1). Nothing bounds the holders. The
frame size is free per message, so telemetry cannot size its pools.

## 6. The rulings that bind it, and the forces
- SK4 (2026-10-06): "NO! USING A MUTEX FOR A SINGLE INTEGER IS LIKE USING A FUCKING NUCLEAR
  WARHEAD TO KILL A COCKROACH! NO! ... WE ARE NOT USING MUTEXES FOR SIMPLE SHIT LIKE THIS!"
  Here: no lock anywhere. Every shared word is one atomic.
- SK5 (2026-10-06): "surely there is a way to perform atomic operations in python." The
  `atomics` package wraps C11 atomics on a buffer. Measured then at about 4 us an
  operation. Measured now at 3 to 5 us (section 7b).
- FR1 (2026-10-04): "WHICH FRAME? THE OLD ONE OR THE NEW ONE? ... we don't need old frames
  laying around in the Ring buffer" + "How do you guarantee that the frames served to all
  of our systems are indeed the latest available frames?" + "IT NEEDS THE LATEST FRAME!"
  Here: the writer takes the oldest free slot. A reader loads `m_latestIndex` only. No
  slot free is a bug and dies. The guarantee is in section 7b item 11.
- RVW3 (2026-10-12): "concurrent data structures have clear acquire() and release()
  operations to claim a resource before actually comitting to it." Here: Acquire and
  Release. A job holds across the request. The server touches no count, and its mapping
  is read-only so it cannot.
- RVW4 (2026-10-12): mid-flight "hand control to the RC, notify the operator, then crash";
  "We will never reach 8 simultaneous highlights, so this is a non issue." Here: every Die
  is our own bug (section 7b item 3). The holders are sized for 8 jobs anyway.
- SYS1 (2026-10-04): "One owner thread for all app state". Here: the buffer holds no app
  state. The draw reads a slot and writes its own canvas.
- S2 (2026-09): the owner chose SAM3 in-process "for now" with its own process "on the
  back burner"; T6: "Surely there is a way that we don't have to send 2.7MiB Per request";
  the rev5 sketch made the server a process; 2026-10-18: "lets stick to what we have so
  far."
- The owner, 2026-10-18: "keep it nameless and pass it on launch"; the claim: "I agree
  with your proposal. Approved."; "its not a word. by common convention, its a dword."
- RUN3, RUN4 (2026-10-17): the header reads without its comments. The mechanism is in
  `framebuffer_internal.h`.
- RUN14 (2026-10-17): "Make sure TOCTOU Doesn't fall inbetween the cracks." Here: item 11.
- TEL17 (2026-10-16): the frame size is probed or given before the buffer and the logger
  are created. No size changes mid-run (the owner, 2026-10-18, 8D).
- MOD1, MOD2, GATE1, DOC1: this document's shape; two files plus the internal header.
The forces (section 8 of the design): a screen frame 33 ms. A SAM3 pass 410 ms to 1.9 s,
and a request may wait behind others in the server's queue. At most 8 vision results a
second. A system force, measured in rounds 1 and 2. A call that yields the GIL must wait to
get it back. The wait lasts up to a switch interval (5 ms) while any Python thread runs
CPU-bound code. With three such threads a yielding copy reached 1.2 s at p99. The draw's
own cv2 calls reached 1 s a frame (round 2, M8). So no thread of the app may run CPU-bound
Python for longer than a frame. The real case today is rclpy's 1080p image conversion
(runtime R1-11). It stalls the main thread 17 ms and delivers 22 of 30 frames. The frame
source owns it. This force binds every module. It is to be carried by the manager to the
design document's section 8 (this agent edits no other file). This module bounds its own
share under that load. It cannot bound the frame.

FB9 (2026-10-22): the atomics package is this module's alone, for the counts two processes share; measured 1,545 ns an operation single-threaded, 3,602 ns under eight threads; every in-process module uses locks and plain ints.

## 7. The design gate
**Ownership.** The app's main thread creates the buffer after perf and before telemetry
and the supervisor. The SAM3 server's spec carries the descriptor. The app destroys the
buffer after the supervisor, after the frame source thread joined and after the pool
joined. The frame source thread is the only writer, the same thread for the buffer's life.
The SAM3 server maps the inherited descriptor read-only once at its start and closes it at
its exit. Nobody else can reach the block: it has no name.

**Data in.** The geometry at Create; pixels from the writer; a sequence number from a
request. **Data out.** A ReadOnlyFrameReference: the index, the sequence, the capture time,
read-only pixels; the health: four plain values; the descriptor for the server's spec.

**Mutable state, and its owner.** `m_latestIndex`: one store by the writer at EndWrite,
loads by every reader. A slot's `m_count`: a compare-and-swap by the writer, add and
subtract by readers. A slot's `m_sequence` and `m_capturedAt`: stores by the writer (0 at
the claim, the number before the publish), loads by readers after their hold and by the
server's Find. The writer's thread, its write-open flag and its last count of held slots:
the writer thread's; the next sequence is the latest slot's sequence plus 1, no copy. The
health read loads them. The retry and miss counters: added by readers; a lost add is
harmless. The per-thread hold count: thread-local, 0 or 1, set by Acquire and Release.
Every value shared between threads is typed atomic in the internal header. The ones
outside the block are relaxed, and in Python a plain int under the GIL.

**Threads.** None of its own. The writer thread and the reader threads are their modules'.
Their stops are their modules'. No call blocks. A reader tries at most 8 times, then
reports no frame.

**Processes.** The SAM3 server maps the block read-only. Its stop is the supervisor's. Its
death leaves no count. A dead app leaves nothing: the kernel frees the block with the last
mapping, and the server's mapping goes with the server (the parent-death signal).

## 7b. The gate, answered (modules/README.md, items 1 to 11)
1. The real-time path: no queue. The main thread's worst call, beside three busy Python
   threads: Acquire plus Release 35 us median, 172 us p99. The draw's copy with the GIL
   kept: 0.38 ms median, 1.2 ms p99 at 1080p (FB6, closed). The health read: four plain loads.
   These rows are the buffer's share only. Under that load the draw's cv2 calls take 1 s
   a frame (round 2, M8). So the frame is lost elsewhere (the system force in section 6).
   The main thread's wait while the writer's copy holds the GIL: 307 us p99, 808 us max
   at 1080p (round 2, M7b, measured by the reviewer). Tried: a reader that sleeps between
   the load and the add; it tries once more. Tried: three busy threads beside the main
   thread with the package as shipped; Acquire reached 5 ms at p99 and 0.6 s at max. The
   recast (item 8) brought it to 172 us.
2. Not a sink. The types: FrameSize, the two references, the health status; pixels only. No app
   state. No module calls back.
3. Fault containment. Every Die, each our own bug: no free slot (FR1, the owner's rule); a
   release without a hold; a BeginWrite inside an open write (a write left open); a
   BeginWrite from another thread (a second writer); a second hold on one thread;
   copy_pixels given arrays of a different size or a strided view. Each mid-flight Die
   runs the hand-over first (RVW4). Start-up faults return NULL from Create, and the app
   dies on NULL: the pages cannot be reserved; the package not 1.0.3 or a call that yields
   the GIL. Eight misses in a row degrade to "no frame this time", counted. A stale
   request degrades to a "stale" reply. The server's Open NULL ends the server, and the
   supervisor relaunches it. Destroy with a pixel array kept past its Release logs and
   returns, no Die (shutdown).
4. Buffer lifetimes. The draw: Acquire, copy, Release, 0.1 to 0.4 ms on the main thread.
   A job: Acquire, the request, telemetry's copy, Release, 0.4 to 4 s. Never held for the
   logger (RVW3). The server: no hold. The writer: claim, copy, publish, 0.4 to 0.8 ms.
   Both sources check the frame's size before the claim, so no claim is left open by a
   bad frame.
5. Types and units. Sequence uint32, a dword, from 1 (4.5 years at 30 a second; the owner, 2026-10-18). The count uint32, a dword, with
   WRITING at 2^31, a macro. NO_FRAME at 2^32 - 1, a macro. capturedAt a MonotonicNs in
   ns. The block size uint64 (74,653,696 at 1080p; a 4K source would pass 2^31). Every
   compare of counts is on the previous value an atomic returns, never a second read.
6. One home. The two references, the block layout: here. The jobs, the draw and
   telemetry's helper read ReadOnlyFrameReference's fields. config holds FRAMEBUFFER_SLOTS (computed
   from the pool's entry). The header's enum shows the derivation, as recorder.h and
   telemetry.h do for their config values (the approved pattern: "read once at Create").
   The block carries its own count, and the writer's table is sized by it.
7. The contract. The two structs in the header are the block's bytes. The byte map, as
   the owner's edit of 2026-10-18 stands (FB8: kept):
   | offset | bytes | what |
   |---|---|---|
   | 0 | 4 | FrameSize: width, height (uint16_t each) |
   | 4 | 4 | m_slotCount |
   | 8 | 4 | m_slotBytes |
   | 12 | 4 | m_pixelsAt |
   | 16 | 48 | pad |
   | 64 | 4 | m_latestIndex, atomic |
   | 68 | 60 | pad |
   | 128 + 64 i | 4 | slot i: m_sequence, atomic, a dword |
   | 132 + 64 i | 4 | slot i: m_count, atomic, a dword |
   | 136 + 64 i | 8 | slot i: m_capturedAt |
   | 144 + 64 i | 48 | pad |
   | 896 | 3200 | pad to the page |
   | 4096 + i x m_slotBytes | m_slotBytes | slot i: the pixels, packed BGR24 |
   The layout stays so by the owner's rule (FB8). The
   descriptor: the server's spec lists it among the descriptors to pass and puts its
   number on the server's command line. Readers: the SAM3 server (module 6). The runtime
   module's ProcessSpec needs one field for the descriptors to pass (carried to the
   manager; runtime is approved).
8. The Python mapping, as code, in section 8. The GIL rule: every atomic call and every
   pixel copy on the frame path and the draw keeps the GIL. Measured: the package's calls
   yield the GIL (ctypes CFUNCTYPE). A yielding call beside a busy Python thread waits up
   to a switch interval to get the GIL back. The recast to PYFUNCTYPE removes the wait
   (round 1, R1-1). The same for the copy: a numpy copy yields; a PYFUNCTYPE memmove
   keeps. Create and Open check the package version (1.0.3) and that every operation
   pointer carries the keep-the-GIL flag; a miss is NULL (round 2, R2-5). The copy helper
   checks both arrays are C-contiguous and of one size on every call (round 2, R2-1).
   Nothing blocks. Nothing grows. The 25 atomic views are made once at Create, and their
   contexts are kept for Destroy.
9. The cost budget, measured 2026-10-17 on this machine (Ryzen 9 8940HX, 32 threads,
   Python 3.12.3, atomics 1.0.3 recast to keep the GIL, numpy 1.26.4; the block in
   /dev/shm then, a memfd now, the same tmpfs pages; 2000 samples 1 ms apart for the small
   calls, 300 for the copies; "busy" is three Python threads in a counting loop; the
   command in section 8):
   | operation, median / p99 / max us | 1080p, 8 slots, idle | 1080p, 3 busy | 720p, 12 slots, idle | 720p, 3 busy |
   |---|---|---|---|---|
   | writer BeginWrite + EndWrite, no copy | 54 / 141 / 268 | 89 / 267 / 359 | 107 / 199 / 226 | 105 / 343 / 437 |
   | writer BeginWrite + copy + EndWrite, the copy keeps the GIL | 732 / 1195 / 1205 | 795 / 1615 / 1899 | 387 / 683 / 820 | 386 / 864 / 1044 |
   | the same with a numpy copy, which yields the GIL (rejected) | 755 / 1250 / 1319 | 5955 / 1793923 / 2046733 | 384 / 635 / 714 | 5546 / 1175941 / 1444316 |
   | reader Acquire + Release | 25 / 73 / 171 | 33 / 172 / 215 | 26 / 70 / 141 | 35 / 172 / 230 |
   | draw Acquire + copy + Release, the copy keeps the GIL | 230 / 489 / 720 | 379 / 1179 / 1289 | 119 / 397 / 574 | 132 / 672 / 704 |
   | the same with a numpy copy (rejected) | 234 / 453 / 2341 | 5629 / 679780 / 973519 | 116 / 322 / 2443 | 5335 / 1570959 / 2315227 |
   | Find by sequence, the server's read-only view | 43 / 91 / 139 | 46 / 188 / 1193 | 44 / 94 / 193 | 31 / 167 / 233 |
   The package as shipped, 720p, 3 busy threads: Acquire plus Release 73 / 5232 / 639278;
   BeginWrite plus EndWrite 178 / 126868 / 1231429 (rejected, R1-1). The 1080p runs used
   8 slots since the block lived in /dev/shm then, capped at 64 MB here. The scan scales
   with the slot count. The 12-slot 1080p numbers are unverified. Rate times cost: the
   writer 30 x 0.8 ms = 24 ms a second on the frame source thread. The draw 30 x (0.03 +
   0.38) ms = 12 ms a second on the main thread. The jobs 8 x 0.03 ms a second. Against
   330 us a call: the buffer's own calls pass on every thread (343 us p99 for the
   writer's two calls under load is the one exception, by 13 us). The pixel copies do not
   pass: the writer's 0.73 ms a frame at 1080p and the draw's 0.38 ms under load. The
   writer's copy is one copy a frame, unavoidable, off the main thread: accepted. The
   draw's copy is the screen's work (FB6, closed).
10. `gcc -fsyntax-only -Wall -Wextra -std=c11 -Wpedantic` on both headers.
    `header_layout.py` on both. No drawing (DOC1). The sizes asserted by a compiled
    program: the header 128 bytes, a slot header 64, `m_latestIndex` at 64. The document
    and the headers agree on every number.
11. TOCTOU, every check-then-act (the list in `framebuffer_internal.h`):
   | n | check, then act | the window | closed by |
   |---|---|---|---|
   | 1 | the writer: count is 0, then write | a reader adds 1 between | the compare-and-swap: check and claim in one instruction |
   | 2 | a reader: load latest, then add 1 | the writer claims that slot between | impossible: the writer never takes the latest slot; a reader asleep until the writer reuses that slot (1 frame with 9 holders, 11 frames with none) meets WRITING and tries again |
   | 3 | a reader asleep past the ring's turnover | the slot holds a newer frame | harmless: a complete frame; the sequence is read after the hold |
   | 4 | the server: Find, then read the pixels | the job's timeout passes, the writer reuses the slot | the job's hold covers every reply the job accepts; the sequence is 0 under write and a request of 0 is stale, so Find never matches a slot under write; a late reply is dropped by its request id (module 6) |
   | 5 | Create, then the server's Open | the server reads a half-written header | impossible: the server is launched after Create returned, with the descriptor of a block already written; no name exists for an earlier open |
   | 6 | a second hold on one thread | a job acquires while it holds | the thread-local count: the second Acquire dies |
   | 7 | Release twice | a second release while another reader holds frees that hold | the subtract's previous value catches 0 and WRITING alone; the rest is not seen, so the with-block is the only release path |
   | 8 | a second writer, or a write left open | two writers alternate; an exception between BeginWrite and EndWrite | the stored writer thread: a call from another thread dies; the flag: a write left open dies |
   | 9 | Destroy while a slot is held | a job still running | the app's stop order: the pool joined before Destroy; a held slot is logged; covered by the app step, no test here |
   | 10 | Destroy while the writer runs | a callback after Destroy calls BeginWrite on released views | the app's stop order: the writer thread's join before Destroy; covered by module 12 and the app step, no test here |
   Rows 1 to 8 have a test in section 9. Rows 9 and 10 are rules of the app step and of
   module 12.

The failure matrix:
| failure | the module's state | what the record shows | the aircraft |
|---|---|---|---|
| a disk error | none: RAM only | nothing | never |
| the writer stalls 5 s | `m_latestIndex` stays; readers hold the last frame; the source's stall guard restarts the video | PERF_FRAME shows the same sequence | never |
| SIGKILL or a power cut of the app | the kernel frees the block with the last mapping; the server's goes with the server | nothing | the phone's own failsafe |
| every slot held | a bug: Die (FR1) | the "die" event | the hand-over first (RVW4) |
| the SAM3 server dies | it held nothing; the job's request fails; the job ends FAILED and its with-block releases; the relaunched server inherits the same descriptor | the job's record | never |
| the server answers after the job's timeout | the job drops the reply by its request id | the job's record: a timeout | never |
| a model timeout | the job releases at its timeout | the job's record | never |
| a reader asleep until the writer reuses its slot (1 to 11 frames) | one more try, counted | the health's retries | never |
| eight misses in a row | no frame this time, counted; the draw keeps its canvas; a job reports NOT_READY | the health's misses | never |
| three busy Python threads beside the main thread | Acquire 172 us p99; the draw's copy 1.2 ms p99 at 1080p; the frame is lost to cv2 (section 6) | PERF_FRAME | never |
| the pages cannot be reserved | Create NULL; the app dies at start with the reason | the banner | none: at start |
| the atomics package not 1.0.3, or a call that yields the GIL | Create or Open NULL; the app dies at start with the reason | the banner | none: at start |
| the server launched without the descriptor (a spec bug) | Open NULL; the server exits; relaunched three times; a laptop part: Die at start | the row; the banner | none: at start |
| a frame of a wrong size or a padded step | the source drops and counts before any claim | the source's row | never |
| copy_pixels given a strided view or a short array | a bug: Die; no byte lands outside the slot | the "die" event | the hand-over first |
| a second hold on one thread | a bug: Die | the "die" event | the hand-over first |
| a release without a hold | a bug: Die | the "die" event | the hand-over first |
| a second writer, or a write left open | a bug: Die | the "die" event | the hand-over first |
| Destroy while the writer runs | prevented by the stop order: the writer thread joins first (module 12) | nothing | never |
| Destroy with a pixel array kept past its Release | logged; the mapping closes when the array is collected | one log line | never |

## 8. The notes that did not make the header
- **Why a nameless block (the owner, 2026-10-18).** A named file under /dev/shm can be
  opened by any process by name. That needed a lock against a second app, an inode check
  against a swap of the name, a magic written twice against an early open, a stale-file
  path after a crash, and it sat under this container's 64 MB cap. A memfd has no name.
  Only a child that inherits the descriptor can map it. The kernel frees it with the last
  mapping. Measured: 74.7 MB reserved and touched under the 64 MB cap; a child's writable
  map refused. Rejected: the named file; multiprocessing.shared_memory (no read-only
  mapping; its resource tracker may unlink a block, CPython gh-82300).
- **Why no epoch and no reopen.** Both existed for a block recreated mid-run. No size
  changes mid-run (the owner, 2026-10-18, 8D), so the block lives as long as the app.
  Rejected: the epoch; VIEW_GONE.
- **Why a claim bit and not the sequence re-read.** The re-read checks the slot after the
  reader's add. It cannot stop a writer that checked the count before the add. The swap
  is the only step that is both the check and the claim. Approved 2026-10-18. Rejected:
  the re-read alone.
- **Why the sequence is 0 under write.** Find runs in another process with no hold of its
  own. Without the 0, a slot under write keeps its old number and Find matches a torn
  frame (round 1, R1-2, measured). Rejected: the number kept until the publish.
- **Why the writer never takes the latest slot.** A claim on it would make every reader
  try again for the whole write, 0.7 ms. With oldest-first it is a candidate only when
  every other slot is held, which is the FR1 bug. Rejected: latest as a candidate.
- **Why `m_latestIndex` is an index alone.** A reader uses only the index. It reads the
  sequence from the slot after its hold. The health's latest sequence is the writer's own
  count. Rejected: a packed word of sequence and index (round 1, R1-12).
- **Why 12 slots, not 32.** Section 4 point 1. A slot is held for a hold, never for age.
  Rejected: 32 (200 MB at 1080p, 20 slots nobody can hold).
- **Why no plain ring (slot = sequence mod N).** A job holds a slot up to 4 s, 120
  frames. The writer would block on it. Rejected.
- **Why the writer keeps no copies of the block's values.** A first draft kept the
  writer's own table of sequences and its latest index, to save Python atomic loads at
  3 to 5 us each: 12 loads a frame, 36 us. Three fields for 1 ms a second was not worth
  it (the owner, FB7: "redundant design"). The writer reads the block; the next sequence
  is the latest slot's sequence plus 1. PickOldestFree loads the counts and the
  sequences, and counts the held slots on the way, which is the health's number.
- **Why eight misses give no frame instead of a Die.** A retry comes only from a reader
  asleep until the writer reuses its slot. That is 1 frame with 9 holders and 11 frames
  with none. It is a scheduling event, not our bug. The writer cannot pin WRITING on the
  latest slot (round 1, R1-4). Rejected: the Die.
- **Why the pages are reserved at Create, and the mapping populated.** tmpfs allocates a
  page at its first write. A short memory kills the writer with SIGBUS mid-run
  (measured: 75 MB on a 64 MB tmpfs). posix_fallocate returns ENOSPC at Create
  (measured). MAP_POPULATE moves the first-touch page faults (0.14 to 1.84 ms a slot,
  round 1, R1-10) to Create and Open. Rejected: a lazy block.
- **Why every atomic call keeps the GIL.** The package calls C through ctypes CFUNCTYPE,
  which yields the GIL per call. A yielding thread waits for a busy Python thread's
  switch interval (5 ms) to get it back. Measured (round 1, R1-1, and section 7b): 5 ms
  p99 with one busy thread, 0.6 s max with three. The same C functions recast through
  PYFUNCTYPE keep the GIL: 172 us p99. The package stays the package (SK5). The pin is
  1.0.3. The start check and the flag test keep the recast honest; the timing stays in
  the benchmark. Rejected: sys.setswitchinterval(0.0005) (608 us p99 and a change to the
  whole app's scheduling); a C extension of our own.
- **Why the recast is verified at start, not timed in the suite.** The recast touches
  three private names of the package. A package change would turn it into a silent
  no-op. Create and Open check the version and the keep-the-GIL flag on every pointer.
  The suite swaps one entry for a counting stub and expects the call to reach it (round
  3, R3-12). The fallback if the package changes: our own ctypes structure of PYFUNCTYPE
  fields over libpatomic's `patomic_create_explicit`, the same C functions (SK5).
- **If the build ever runs on a free-threaded Python (GIL1, 2026-10-18).** The GIL rule
  becomes moot: no call waits for the GIL, and the recast and the PYFUNCTYPE memmove are
  no longer needed. The atomics and the claim stay exactly as they are, since they never
  relied on the GIL. Blocked today by opencv, rclpy, atomics and numpy 1.26 (the ledger).
- **Why the pixel copy keeps the GIL too.** A numpy copy yields the GIL and pays the same
  wait. Measured: 1.2 s p99 for a 720p frame beside three busy threads (section 7b). A
  memmove through PYFUNCTYPE holds the GIL for the copy's 0.1 to 0.8 ms and never waits.
  The helper lives in util/ (the frame source and the screen use it). Rejected:
  np.copyto on the frame path.
- **Why the copy helper checks on every call.** A memmove has no shape. A strided view
  (a padded ROS step, or a canvas wider than the frame) shears the frame silently. A
  bigger source writes into the next slot (round 2, R2-1, measured). Two attribute reads
  per call close both. The drone path drops a padded step before the claim; our receiver
  publishes packed rows. The canvas is exactly the frame's width (module 15); a wider
  canvas would need a row-by-row helper, h memmoves of w * 3 bytes (round 3, R3-7).
- **Why one hold per thread is enforced.** The slot count counts one hold per holder. A
  job that keeps one frame while it acquires another breaks the proof, and FR1's Die
  would then fire on a legal load (round 2, R2-7). A thread-local count costs one
  attribute and makes the second hold a bug that dies at once.
- **Why the writer's thread is stored.** No restart changes the writer thread of one
  buffer. The drone stall restarts the gstreamer process and keeps the subscription
  thread. The webcam's reopen runs on its own thread. No size changes mid-run. So a
  BeginWrite from another thread is always a second writer, and the stored thread
  catches it even when the two alternate (round 3, R3-19). The flag catches a write left
  open on the same thread.
- **Why the server copies nothing.** The job's hold keeps the pixels stable for every
  reply the job accepts. Rejected: a 6 MB copy per pass; the server claiming the slot
  (RVW3); StillHolds after the detect (it protected nothing; round 1, R1-3).
- **Why no wait for a frame.** The draw runs on its own 33 ms. A job takes what is there.
  "No frame yet" is a false. Rejected: a condition variable; a blocking Acquire.
- **Why no drop path for the writer.** FR1: every slot held is a bug, and a bug dies.
- **Why the health is plain values.** The writer scans every count each frame anyway and
  keeps the result. The main thread reads four plain values, no atomic call (round 1,
  R1-7). Rejected: 14 atomic loads per frame on the main thread.
- **Why SAM3 stays its own process (the owner, 2026-10-18).** Measured (the SAM3
  assessment, R9): a pass in the app's process does not slow the frame loop; the load
  does (8 to 10 frames over 100 ms, max 1.8 s; 0 in its own process); a GPU fault
  in-process ends the app, in its own process it is a restart. The supervisor stays for
  the four children that are programs by nature. Rejected: SAM3 on a thread; llama
  through the Python bindings (Gemma 4 with images through them is unverified).
- **A second writer in the C++ receiver.** The gstreamer receiver could write the block
  itself and skip rclpy's 17 ms conversion. RVW5 keeps it a ROS node for one uniform
  image source. The writer calls work from any process that maps read-write, so module
  12 can raise this with the owner. The buffer does not decide it.
- **Carried to other modules and to the manager.** Module 6: the descriptor's number on
  the command line; a reply is matched to its request by an id; a reply after the
  timeout is dropped; the view's numpy array is read-only, so a write in the preprocess
  raises before any SIGSEGV. Module 12: the writer thread's join before Destroy; the size
  and step checks before the claim. Module 13: one hold per thread; a job can compare
  capturedAt with now and report a stale frame during a video stall. Module 15: the
  canvas exactly the frame's width; the draw's copy in PERF_FRAME. The app step: the stop
  order (the pool and the writer joined before Destroy). The manager: ProcessSpec gets a
  field for the descriptors to pass (runtime is approved; one line); the system force of
  section 6 into the design document's section 8; section 6 of the design document gets
  the claim's words.
- **The costs of the choices.** 75 MB of RAM at 1080p. 3 to 5 us per atomic operation,
  26 us an Acquire. The draw's copy (section 4 point 3). The GIL held for 0.1 to 0.8 ms
  per copy on the writer and the draw.
- **The Python mapping, as code.**
  ```python
  # framebuffer/framebuffer.py: Create, in the order of framebuffer_internal.h
  fd = os.memfd_create("harden2_frames", 0)        # the name is a label only; no path exists
  os.ftruncate(fd, total)
  os.posix_fallocate(fd, 0, total)                 # ENOSPC -> close -> None
  mm = mmap.mmap(fd, total, flags=mmap.MAP_SHARED | mmap.MAP_POPULATE)
  struct.pack_into("<2H3I", mm, 0, w, h, SLOTS, slot_bytes, 4096)   # FrameSize is two uint16_t
  mv = memoryview(mm)
  contexts = []                                    # kept: Destroy exits them
  def view(lo, hi):
      ctx = atomics.atomicview(buffer=mv[lo:hi], atype=atomics.UINT)
      contexts.append(ctx)
      return keep_gil(ctx.__enter__())
  latest = view(64, 68)
  seq    = [view(128 + 64 * i, 132 + 64 * i) for i in range(SLOTS)]   # a dword at +0
  count  = [view(132 + 64 * i, 136 + 64 * i) for i in range(SLOTS)]   # a dword at +4; capturedAt at +8
  check_atomics_keep_the_gil(contexts)             # 1.0.3; every pointer PYTHONAPI; else None
  pixels = [np.frombuffer(mm, np.uint8, slot_bytes, 4096 + i * slot_bytes)[:h*w*3].reshape(h, w, 3)
            for i in range(SLOTS)]
  for i in range(SLOTS):
      seq[i].store(0)
      count[i].store(0)
  latest.store(NO_FRAME)

  def keep_gil(view):                              # the package's C functions, GIL kept (R1-1)
      core = view._core
      core._supported = {op: ctypes.cast(fp, ctypes.PYFUNCTYPE(type(fp)._restype_, *type(fp)._argtypes_))
                         for op, fp in core._supported.items()}
      return view

  # the server's spec, in sam3/server.py: pass_fds=[fd] and "--frames-fd", str(fd) on argv
  # the server's Open: a read-only reopen, so a writable map is refused by the kernel
  ro = os.open(f"/proc/self/fd/{fd}", os.O_RDONLY)
  total = os.fstat(ro).st_size                     # 0 or under 4096: not ours -> None
  mm = mmap.mmap(ro, total, prot=mmap.PROT_READ, flags=mmap.MAP_SHARED | mmap.MAP_POPULATE)
  ...                                              # the views as above; the numpy views read-only

  # util/copy.py: a memcpy that keeps the GIL; the frame source and the draw use it
  _memmove = ctypes.PYFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t)(
      ctypes.cast(ctypes.memmove, ctypes.c_void_p).value)
  def copy_pixels(dst, src):                       # checked on EVERY call: a mismatch is our bug
      if not (dst.flags.c_contiguous and src.flags.c_contiguous and dst.nbytes == src.nbytes):
          die("copy_pixels: a strided view or a different size")
      _memmove(dst.ctypes.data, src.ctypes.data, src.nbytes)

  _holds = threading.local()                       # one hold per thread
  class framebuffer_latest:                        # the with-block over Acquire and Release
      def __enter__(self):
          if getattr(_holds, "n", 0):
              die("framebuffer: a second hold on one thread")
          ...                                      # Acquire; on success _holds.n = 1
      def __exit__(self, *exc):
          ...                                      # Release; _holds.n = 0

  # Destroy: ctx.__exit__ for each context; the pixel arrays dropped; mv.release(); mm.close()
  # (BufferError through the filesystem guard: "a pixel array outlived its Release", logged);
  # os.close(fd) last
  # Find: 0 -> None; scan the 12 sequence dwords; a match -> the ref; none -> None
  ```
  The measurement command: `KEEP_GIL=1 PYTHONPATH=<scratch>/pylib python3 -u fb_measure2.py`
  with `SLOTS=8 GEOM=1920x1080` for the 1080p run, in the agent's scratch folder. The
  package installed there with `pip install --target <scratch>/pylib atomics==1.0.3`.
  `KEEP_GIL=0` gives the package-as-shipped rows. The memfd checks: `memfd_check.py` there.

## 9. The tests the module ships with (`test/test_framebuffer.py`)
- `test_create_lays_out_the_header_and_the_slots_as_the_contract`: the bytes at 0, 64
  (the latest index), 128 and 4096.
- `test_writer_takes_the_oldest_free_slot_and_never_the_latest`: a table over PickOldestFree.
- `test_a_held_slot_is_skipped_by_the_writer`: 12 writes after one Acquire; the held slot
  keeps its pixels.
- `test_a_reader_that_adds_after_the_claim_tries_again_and_gets_the_new_latest` (rows 1,
  2): the claim set by hand, the add sees WRITING, the next try lands on the published
  slot.
- `test_a_reader_that_added_first_makes_the_claim_fail` (row 1): count 1, the swap
  fails, Pick moves on.
- `test_a_reader_asleep_past_the_turnover_holds_a_newer_complete_frame` (row 3).
- `test_find_never_matches_a_slot_under_write` (row 4): a claim, half the pixels
  written, Find of the old number is None.
- `test_find_of_zero_is_none` (row 4).
- `test_a_child_opens_the_inherited_descriptor_read_only_and_cannot_map_it_writable`
  (row 5, RVW3): a spawned child with pass_fds; Find by sequence; a write to the view
  raises on the read-only array; fetch_add on a count view raises the package's
  unsupported-operation error; a writable mmap raises PermissionError.
- `test_a_second_hold_on_one_thread_dies` (row 6).
- `test_release_without_a_hold_dies` (row 7).
- `test_a_second_writer_thread_dies` and `test_a_write_left_open_dies` (row 8).
- `test_every_slot_held_dies` (FR1): 11 holder threads, one hold each, then the writer's
  claim; Die called with the reason.
- `test_eight_misses_give_no_frame_and_count`: a reader hook sleeps between the load and
  the add across 8 writes of a ring with 9 holders; the ninth try is skipped and the miss
  counted.
- `test_open_returns_none_on_a_bad_descriptor_or_a_short_file`.
- `test_create_returns_none_when_the_pages_cannot_be_reserved`: ENOSPC injected at the
  guarded call.
- `test_create_returns_none_on_a_wrong_package_or_a_yielding_pointer`.
- `test_every_atomic_op_reaches_the_patched_entry`: one entry of a view swapped for a
  counting PYFUNCTYPE stub; the view's operation raises the count; the copy helper's
  pointer carries the keep-the-GIL flag.
- `test_copy_pixels_refuses_a_strided_or_short_array` and
  `test_a_padded_step_is_dropped_before_the_claim`.
- `test_destroy_logs_a_held_slot_and_frees_the_block`: after Destroy and the child's exit
  the memory is returned (the child's /proc map gone).
- `test_destroy_with_a_kept_pixel_array_logs_and_returns`.
- `test_health_counts_retries_misses_and_held_slots`: the latest sequence is 0 before the
  first frame.
- `test_a_with_block_releases_on_an_error_in_the_body`.
