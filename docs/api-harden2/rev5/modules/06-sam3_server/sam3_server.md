# sam3_server: the SAM3 detector process and its client (rev5 module 6, 2026-10-18)

The headers are `sam3_server.h` (the spec, the two messages, the client, the record) and
`sam3_server_internal.h` (the server's state, its one loop, the pass as steps, the TOCTOU
list). The design document is `../../01-system-architecture.md` (sections 2, 6, 8, 9).
Below it: the recorder, runtime and the frame buffer. Its one caller: the vision jobs
(module 13). The review record is `../../test/sam3_server-review.md`. State: see the brief's
progress log.

## 1. The job, in one sentence
The module is the app's one path to SAM3: from the process's launch spec to each detect.

## 2. The picture
```
 THE APP PROCESS                                    THE SAM3 SERVER (python3 -m sam3.server)
 +---------------------------------------------+    +------------------------------------------+
 | supervisor thread (runtime)                 |    | ONE thread, the main thread:             |
 |   launch with pass_fds=[memfd]; pidfd ------+--->|  1 Die hooks, SIGINT handler, wake pipe  |
 |   probe: a connect, 200 ms cap, 500 ms -----+--->|  2 RecorderCreate(D, "sam3", no frames)  |
 |   stop: SIGINT; the kill after 10 s         |    |  3 FramebufferOpen(fd): read-only map    |
 |   writes the "sam3" row                     |    |  4 load nf4 (6.3 s); warm pass (1.3 s)   |
 |                                             |    |  5 unlink, bind, listen: <D>/sam3.sock   |
 | 8 pool threads (module 13), one request     |    |  6 the loop, one poll on: the wake pipe, |
 | each, the slot held across it (RVW3):       |    |    the listen socket, the unread         |
 |   AcquireLatest -> slot (seq)               |    |    connections (at most 9):              |
 |   Sam3ClientDetect -- a new connection ---->+--->|     accept -> the unread set (no read)   |
 |     1040-byte request: seq, concepts,       |    |     bytes in -> read the request ->      |
 |     priority, floor, max masks              |    |       the priority queue (8 entries;     |
 |   <-- ONE read: 8-byte header, 128 boxes, --+<---+       command before refresh; arrival    |
 |       masks (the caller's buffer)           |    |       order within a class)              |
 |   Release (after the record copied)         |    |     0 bytes (the probe) -> close         |
 |   SPAN_SAM3_REQUEST (req) in record-app     |    |     a request queued: pop the best,      |
 |                                             |    |       Find(seq) in the block:            |
 | main thread: reads the "sam3" row each      |    |       miss -> FRAME_GONE                 |
 |   frame (one atomic load); sends nothing    |    |       hit  -> the pass -> the reply      |
 +---------------------------------------------+    |     SPAN_SAM3_PASS (req, wait, boxes)    |
          | writes (frame source)                   |       in record-sam3-<pid>.jsonl         |
          v                                         |  7 SIGINT: the pass ends, answered; exit 0|
 +--------------------------------------------+     |  any exception (a GPU out-of-memory): Die |
 | THE FRAME BLOCK (a nameless memfd, 12 slots)|<----+    = the record's flush, then _exit(1)    |
 +--------------------------------------------+     |  reads pixels only, by the sequence       |
                                                    +------------------------------------------+
```
1. **The process.** The supervisor owns it (RUN9). This module gives one pure function
   that returns the ProcessSpec. The spec passes the frame block's descriptor (RUN15).
2. **The socket.** A Unix domain socket in the session folder, as llama-server has (LLM1
   D4). The server binds it only after the load and the warm pass. So a completed connect
   means ready, and a refused one means loading, relaunching or down.
3. **The queue.** The server accepts a connection at once and reads its request when the
   bytes arrive. Each request goes into a heap. A command runs before a refresh. One pass
   runs at a time; threads and batching give no throughput gain (measured 2026-09-22).
   The heap holds at most 8: one request per pool thread, since a request blocks its
   thread.
4. **The frame.** The request names the frame by its sequence number. The job holds the
   slot until the reply. The server finds the slot and reads the pixels in place. It
   touches no count (RVW3).
5. **The reply.** One fixed layout: a status, 128 box places (the first ones valid),
   then the masks. Boxes are corners with a score and a concept index, sorted by score,
   duplicates merged (TR17). Masks for the first boxes only, at most 3 (OPEN 1). One
   connection per request, so no id is echoed.
6. **The record.** The server records SPAN_SAM3_PASS in its own file. The job records
   SPAN_SAM3_REQUEST in the app's file. The two join by req (RVW5, RCD1).

## 3. How a caller uses it: two instances, in the Python of the build
**Instance 1: the app's start and stop.**
```python
# app/main.py, the services, in order; the frame block exists before the supervisor
frames = framebuffer_create(size)
fd = framebuffer_descriptor(frames)
settings = sam3_server_settings_from_config(session.dir, fd)    # the socket path inside
specs = [sam3_server_process_spec(settings, log_dir), ...]      # pure: a spec out
supervisor = supervisor_create(specs)                   # launches it; the probe runs
sam3 = sam3_client_create(settings.socket_path)

# false only for FAILED; a laptop part's spent budget is the supervisor's Die
if not supervisor_wait_until_ready(supervisor, supervisor_process(supervisor, SAM3_SERVER_NAME)):
    die("the SAM3 server failed at start")
# no warm-up here: the server warms itself before it binds, also after every relaunch

# app shutdown: the modules first, so every pool thread is joined; then the services
sam3_client_destroy(sam3)
supervisor_destroy(supervisor)                          # SIGINT; the kill after 10 s
framebuffer_destroy(frames)
```
**Instance 2: one highlight pass on a pool thread (module 13), and the server's side.**
```python
# perception/jobs.py, a pool thread; the slot is held across the request (RVW3)
with framebuffer_latest(frames) as slot:
    if slot is None:
        return NOT_READY
    request = Sam3Request(
        priority=SAM3_PRIORITY_REFRESH,                 # a gate or a count: COMMAND
        frame_sequence=slot.sequence,
        concepts=("dresser", "chest of drawers", "cabinet"),
        score_floor=config.DETECT_FLOOR,                # 0.12
        max_masks=3 if job.masks_on else 0,             # the per-job switch (VIS2)
    )
    masks = np.empty((request.max_masks, size.height, size.width), np.uint8)   # new each time
    t0 = monotonic_now()
    reply = sam3_client_detect(sam3, request, config.VISION_SAM3_TIMEOUT_NS, masks)
    record_span(SPAN_SAM3_REQUEST, t0, monotonic_now(),
                f'"req":{reply.request_id},"prio":1,"ok":{int(reply.result is SAM3_OK)}')
    if reply.result in (SAM3_FRAME_GONE, SAM3_INVALID_REQUEST, SAM3_INVALID_REPLY):
        die(f"sam3: {reply.result.name} on a held slot")   # our bug (RVW4)
    if reply.result is SAM3_REFUSED:
        return NOT_READY                                # loading or relaunching: never "absent"
    if reply.result is not SAM3_OK:                     # CLOSED, TIMEOUT
        return VisionResult(job, FAILED, reply.result.name)   # architecture section 9
    record_vision_pass(...)                             # the recorder copies the frame and masks
# released here: after the reply and the copy

# sam3/server.py, inside RunOne: one pass, then one span (record_sam3)
ref = framebuffer_find(view, request.frame_sequence)
if ref is None:
    reply_status(conn, SAM3_STATUS_FRAME_GONE)
    return
start = monotonic_now()
header, boxes, masks = model.detect(ref.pixels, request)
end = monotonic_now()
send_reply(conn, header, boxes, masks)                  # a failed send: the client gave up
record_sam3_pass(start, end, request.request_id, (start - pending.read_at) / 1e6, header.box_count)
```

## 4. The open points for the owner
**OPEN 1. The mask limit: 3 masks a reply.** (the header: kSam3MaxMasks)
- The problem. The handoff (part E, item 6) says "masks ... at most 3". No ruling of
  yours sets it. Today's code masks every kept box, up to HL_MAX (128): its comment says
  "highlight all the cars" needs many masks. The recorder's mask pool is 24, sized for 8
  passes of 3.
- The facts. 47 logged passes with two or more concepts: after this design's merge the top
  3 boxes cover 2.98 distinct objects on average (round 2, R2-1). Measured 2026-10-18
  (section 6): "cable" on market-0.jpg at the 0.12 floor gives 82 hits at 1080p, 18 after
  the merge. Today's post-process brings every mask to the CPU: 1224 ms, and 1816 MiB of
  GPU memory over the pass. Masks for 3 boxes only: 2.2 ms and 43 MiB. 3 masks at 1080p
  are 6.2 MB on the socket: 0.50 ms p50 with the app idle. A box beyond the third gets no
  mask, so the vision job cannot tighten it to its mask or drop its garbage mask.
- Now: kSam3MaxMasks = 3; a request asks 0 to 3 (m_maxMasks). Every box comes back.
- On "no": a higher cap, for example 32. The reply grows by 2.07 MB per mask at 1080p
  (about 1 ms per 6 MB, measured). The recorder's mask pool (24) changes with it: an
  approved contract, carried to the manager.
- Recommended: 3. The best three boxes carry masks; every box is drawn.

Settled here, with the reason (no ruling needed):
- **One thread in the server.** The priority needs the waiting requests read before the
  next pass starts, not during a pass: a request waits for the GPU anyway. So one loop
  polls the wake pipe, the listen socket and the unread connections, then pops the best.
  No lock, no condition variable, no second thread. A round that accepted a connection
  pops nothing; it polls again at once, so the new request is read before the next pop.
  Without that rule a command that arrived during a pass ran one pass late: 0.90 s against
  0.50 s in the reviewer's run (R3-1).
- **Accept now, read when the bytes are there (R2-3).** A client connects, then takes the
  GIL back before it sends. A blocking read in the server waited for it: 5 ms per request
  beside one busy app thread, and a lost request at a 1 s read limit beside two
  (measured). So an accepted connection waits in the poll, and the read never waits.
- **The probe is a bare connect (R1-5).** The kernel completes it in the listen backlog,
  also during a pass. The server later reads 0 bytes and closes it.
- **Who drops.** Nobody. A refresh waits behind commands. Commands come from speech, at
  most 3 passes per vision sentence (the gate, the verify's two nouns; or the count's 3
  frames). The heap never holds more than the 8 pool threads' requests. A refresh that
  waits past its own timeout is the job's TIMEOUT (module 13 decides what the job does).
- **The merge (TR17) lives in the server.** The mask choice is "the first m_maxMasks
  boxes". It is right only after the merge: a duplicate must not take a mask from a second
  object. So the merge runs before the cut. The rule: IoU over 0.5 across all the
  request's concepts; containment over 0.7 within one concept only. A synonym finds the
  same object with a near-identical box, so IoU merges it (the logged cabinet, dresser and
  chest of drawers on one box). A part inside its whole is a second object (the logged
  drawers inside a dresser, for "highlight drawer"). On the 47 logged passes, the top 3
  then hold 2.98 distinct objects. Per concept, as today, they hold 1.43. With containment
  across the concepts, they hold 2.91, and only 2 of 16 drawer boxes stay (R1-1, R2-1).
  Its CPU test on real boxes from past runs (TR17 (3)) moves here, with those passes.
- **The client bounds the user's words (R1-2, R2-4).** A spoken attribute phrase reached 65
  bytes ("man in the yellow jacket with the black backpack and the blue cap"). A concept
  holds 128 bytes; the client cuts a longer one at its last word boundary and sends at most
  8 concepts. That bounds the message. SAM3's own limit is 32 tokens, and the processor's
  call does not truncate: 42 tokens went through and the model raises at 33 (measured). So
  the server calls the tokenizer itself with truncation at 32. No logged concept passes 10
  tokens.
- **The whole reply is one read (R1-3, R2-2).** A read loop took the GIL back about 30 times
  per 6.2 MB reply. The server's send then took 173 ms beside one busy app thread. Beside
  two, it hit its 1 s limit. One read per part still lost 4 of 40 replies beside two. So
  the reply has one fixed layout. The client reads it with one recvmsg with MSG_WAITALL,
  into the header, the boxes and the caller's mask buffer. The reviewer measured 0 of 80
  lost, the send 1.4 ms p50 and 154 ms at worst. The socket stays blocking, with
  SO_SNDTIMEO and SO_RCVTIMEO. A Python settimeout makes the read return early (219264 of
  6220800 bytes, measured), so the client never calls it.
- **The server's own post-process.** It keeps the scores and boxes of every hit, merges,
  cuts, and upsamples only the masks it sends. The measured reason is OPEN 1's facts. A pass
  with no box asks no upsample: torch's interpolate raises on an empty tensor, and 72 of 877
  logged passes had no hits (R1-4, R2).
- **Corners are clamped to the frame.** 580 of 4296 logged boxes have a negative corner.
  One has y2 = 732 on a 720-row frame. A uint16_t cannot hold either (R1-13, R2).
- **The colour conversion.** cv2.cvtColor into a kept buffer: 0.21 ms at 1080p. Today's PIL
  path: 24.7 ms (measured, section 6; the reviewer: 49.5 against 26.9 ms with the processor,
  the same pixels).
- **The frame size.** From the frame block's header (FramebufferViewSize), never from
  config. The warm pass uses it too.
- **"Not ready".** No status: the socket exists only when ready. A request before that is
  SAM3_REFUSED in under 0.1 ms; the job says "not ready", never "absent" (2026-09-23).

One change to an approved contract, an item for the owner at the end (gate item 12):
- The frame buffer (module 4): FramebufferOpen closes the inherited read-write descriptor
  after its read-only reopen. Until then a writable map through the inherited one succeeds,
  and only our own bug would make one (R1-10, R2-10).

Carried to the manager (PAR2):
- The frame buffer's internal header: "dropped by its request id (module 6)" becomes
  "dropped because its connection is closed" (R1-6).
- config: PROJECT_DIR, the project folder, for the child's PYTHONPATH (R1-11); and
  SAM3_MASK_THRESHOLD, 0.5, today a default argument in sam3/model.py (R3-8).
- recorder.md, instance 2: the client allocates req and its reply has a result, not ok;
  the example becomes `reply = sam3_client_detect(sam3, request, timeout, masks)` with
  reply.request_id (R3-9).
- The vision module's timeout: VISION_SAM3_TIMEOUT_NS 15 s recommended (section 7).
- recorder.md names a file record_<owner>.h; DOC1 allows this module two headers. The one
  helper sits in section 4 of sam3_server.h. A move is one cut and paste.
- recorder.h and framebuffer.h both define FrameSize; one file cannot include both until
  the fold (RCD2). The internal header declares FramebufferView by its tag meanwhile.
- The architecture document, section 2: "it holds a frame slot by its count" is
  superseded by RVW3 (the job holds it); section 8: "1.9 s for three concepts" is from
  before S1 (one encoding; now 527 ms alone).

## 5. Today
The code: `sam3/model.py` (243 lines), `sam3/loader.py` (87), `sam3/contract.py` (23),
`perception2/sam3_lock.py` (55), `perception2/vision.py` (436, the callers).
- loader.py loads Sam3Backend on a thread of the app, then one warm pass on a black frame
  of config.CAM_W x CAM_H. Until then detect() answers DETECT_NOT_READY.
- model.py encodes the frame once per call (S1), runs the text and detector per concept,
  unions, sorts, merges nested boxes per label (TR17), and caches every mask by its box
  tuple. mask_for_box() reads that cache.
- sam3_lock.py is a priority lock: a heap of tickets under a Condition. vision.py takes it
  for each detect at the thread's priority: COMMAND for a new job, REFRESH in the track.

What is wrong with it against rev5:
1. It runs in the app's process (T6, S2 a, FB4 rule its own process). The load stalls the
   frame loop: 8 and 10 frames over 100 ms (assessment R9). A GPU out-of-memory ends the
   app.
2. The mask cache races. The priority lock covers detect() only. mask_for_box() takes the
   backend's own lock later. Another job's detect() between the two replaces the cache. A
   box of the same corners then gets the other frame's mask, or none.
3. The post-process brings every hit's mask to the CPU at full size: 1224 ms and 1816 MiB
   of GPU memory for 82 hits at 1080p (measured). The engine then masks up to 128 boxes.
4. The merge per label keeps one object's synonyms as separate boxes: 1.43 distinct objects
   in the top 3 of 47 logged passes (R2-1).
5. The BGR to RGB copy goes through PIL: 9.3 ms at 720p, 24.7 ms at 1080p (measured).
6. The warm frame's size is config's, not the source's.
7. A failure has two codes: OK and NOT_READY. A GPU fault is an exception that kills the
   app; nothing tells "loading" from "dead".
8. The record "sam3" times the forward and the lock wait in the app; rev5 records the pass
   in its own process (RCD1).

## 6. The rulings that bind it, and the forces
| ID | the owner's words | what it fixes here |
|---|---|---|
| T6 | "Agreed. Surely there is a way that we don't have to send 2.7MiB Per request" | the frame by its sequence in the shared block, never sent |
| S2 | "Option A needs to be kept in the backburner ... a new python process API for us, a way to sync & retrieve image data from a memory ring" | option A, its own process with a shared ring, is the rev5 design |
| FB4 (2026-10-18) | "I understand. In that case, lets stick to what we have so far." | SAM3 stays its own process |
| FB2 (2026-10-18) | "Good! keep it nameless and pass it on launch." | the memfd's descriptor in m_passFds; FramebufferOpen(fd) |
| RUN15 (2026-10-18) | "keep it nameless and pass it on launch" | ProcessSpec.m_passFds |
| S1 | the owner: S1 a | one image encoding per pass, then one detection per concept |
| S4 | "no, that is stupid. Let the GPU do the scheduling as it knows." | no pause while Gemma answers; the 51 % slowdown is accepted |
| L1 | "Why isn't this done already?" | the warm pass before ready, at every launch |
| RVW3 (2026-10-12) | "concurrent data structures have clear acquire() and release() operations to claim a resource before actually comitting to it." | the job holds the slot; the server touches no count; one refresh outstanding per job |
| RVW4 (2026-10-12) | mid-flight: hand control to the RC, notify the operator, then crash | the budget spent: the supervisor's Die, the hand-over first |
| RVW5 (2026-10-12) | "You can measure the C++ processes from our end" | SAM3 is ours: it records its pass; the job times the request; the two join by req |
| SYS1 (2026-10-04) | "One owner thread for all app state" | the client returns a reply and touches no app state |
| RUN9 (2026-10-17) | "The supervisor is the owner ... Who is the owner here!?" | a pure spec function; the module launches nothing |
| RUN14 (2026-10-17) | "Make sure TOCTOU Doesn't fall inbetween the cracks." | gate item 11; W1 to W10 in the internal header |
| RUN16 (2026-10-18) | "the env vars should be empty in the initial process, unless we set the env char array to an addition" | one env addition, PYTHONPATH |
| LLM1 D3 (2026-10-18) | "D3 - Drop." | no hang mechanism: a request ends at its timeout |
| LLM1 D4 (2026-10-18) | "I agree. Approved." | the precedent: a Unix domain socket in the session folder |
| REV8 (2026-10-18) | "R2 - I fully agree with everything here! APPROVED!" | every failure-matrix row names its cause |
| PRF7, RCD1 (2026-10-18) | "Why do you hold a handle to m_perf?"; "Call it RecorderCreate() and destroy(), recordSpan()" | no recorder handle; the helper takes no recorder argument |
| TR17 | "If this function is CPU only, then you can look at past runs, copy the bboxes' data and check that our function works against them, no gpu no nothing." | Sam3MergeNested is pure and tested on real boxes |
| 2026-09-23 | "SAM3: load failure -> die; GPU out of memory -> die (no retry for now) ... "Not ready" and "no hits" are not failures." | rev5 section 9 moves "die" to the server's process: it exits, the supervisor relaunches |
| MOD1, MOD2, GATE1, DOC1, PAR2 | the document order; OPEN n; the proof-based gate; two files; the agent writes no shared ledger row | this document, the OPEN 1 mark, section 7b |

The ledger's R2 is the unified bench, not SAM3. The rows that rule the own process are T6,
S2 and FB4.

The forces. The design document, section 8: 410 ms a pass alone, 630 ms with Gemma busy,
1.9 s for three concepts (that last one from before S1). Measured on this machine on
2026-10-18 (RTX 5070 Laptop, 8151 MiB; torch 2.11.0+cu128, transformers 5.17.0; the nf4
weights at /root/models/vision/sam3-nf4; under tools/lock.sh; the GPU otherwise idle at
159 MiB). The scripts sit in the agents' scratch folders, not in the repo; each line below
names what it ran.
| what | measured |
|---|---|
| import torch; the model load from the nf4 folder | 1195 ms; 6263 ms |
| the warm pass (the first after the load), then the second pass | 1330 ms; 383 ms |
| a pass, 1 concept, desk_0015.jpg: 720p; 1080p (16 passes) | 405 ms p50, 440 max; 418 ms p50, 428 max |
| a pass, 3 concepts: 720p; 1080p | 527 ms p50, 542 max; 543 ms p50, 567 max |
| a pass, 7 concepts ("all the vehicles"), market-0.jpg: 720p; 1080p (12 passes) | 799 ms p50, 817 max; 818 ms p50, 841 max |
| the steps of a 1-concept pass at 720p: the PIL colour copy, the encode, one concept, post | 9.3, 335.9, 61.2, 0.5 ms |
| the same at 1080p | 24.7, 326.5, 63.4, 0.4 ms |
| cv2.cvtColor BGR to RGB into a kept buffer: 720p; 1080p | 0.071 ms; 0.215 ms |
| "cable", market-0.jpg, floor 0.12: hits before the merge; after it (720p; 1080p) | 85, 19; 82, 18 |
| the library's post-process, then every mask to the CPU: 720p; 1080p | 5.1 + 482 ms; 10.6 + 1224 ms |
| the GPU memory the library's post-process adds: 720p; 1080p | 854 MiB; 1816 MiB |
| the masks of the 3 best boxes only, upsampled and copied: 720p; 1080p | 24 MiB; 2.2 ms and 43 MiB |
| the GPU peak of a pass with no hits; with 82 hits through the library's post-process | 958 MiB allocated; 3877 MiB |
| the socket round trip, a new connection each, 128 boxes, 3 masks, the client idle: 720p (2.77 MB); 1080p (6.22 MB); 300 each | 0.25 ms p50, 0.42 p95, 1.43 max; 0.50 ms p50, 0.76 p95, 2.55 max |
| the same with no masks | 0.019 ms p50, 0.037 max |
| connect to a stale socket file; to no file | ECONNREFUSED in 15 us; ENOENT in 73 us |
| the memfd in a child: reopen read-only, fstat, map populated: 720p (33.2 MB); 1080p (74.7 MB) | 16.9 ms; 38.4 ms; a writable map of the reopened descriptor refused |
| one slot read in the child: the array view; a full copy; the PIL colour copy (720p; 1080p) | 10 us, 0.14 ms, 8.8 ms; 13 us, 0.56 ms, 20.1 ms |
| SIGINT to a handler that sets an Event: the waiting main thread wakes; select on the wake pipe wakes | 48 us; 130 us |
| the client's Python under the GIL: pack the request; unpack the header; 19 boxes by np.frombuffer; np.empty for 3 masks at 1080p | 0.23, 0.10, 0.22, 0.83 us p50 |
| a blocking connect with SO_SNDTIMEO 0.3 s to listen(8), nobody accepting: connects 1 to 9; the 10th | at once; BlockingIOError after 305 ms |
| recv_into with MSG_WAITALL and SO_RCVTIMEO 0.3 s: 100 of 1000 bytes sent; none; the peer closed | returns 100 after 305 ms; BlockingIOError after 303 ms; returns 0 |
| the processor's text call with a 42-token phrase, with and without truncation=True | 42 tokens both times: the processor ignores it |
| from the assessment (2026-09-28): Gemma busy slows a pass | 630 against 417 ms: x1.51 |
| the reviewer (R1-3): the server's send of 3 masks at 1080p, the client reading in a recv_into loop: client idle; one busy Python thread; two | 0.88 ms p50; 173 ms p50; every send at its 1 s limit |
| the reviewer (R2-2): the same, one read per part; one busy thread; two (run 1) | 11.0 ms p50; 72.4 ms p50, 4 of 40 lost |
| the reviewer (R2-2): the same, one recvmsg for the whole reply; one busy thread; two (two runs) | 1.45 ms p50; 1.36 and 1.49 ms p50, 154 ms worst, 0 of 80 lost |
| the reviewer (R2-3): the server's blocking read of the request after its accept, one busy thread; two | 5.05 ms p50; up to 1000.9 ms, one request lost |
| the reviewer (R1-4): torch interpolate on a [1, 0, 288, 288] tensor | RuntimeError |
| the reviewer (R1-5): a connect to a listener that does not accept; the server's later read | completes in 5 us; reads 0 bytes in 6 us |
| the reviewer (R1): the server process after load; after an 8-concept pass at 1080p with the top-3 masks; with the library's post-process | 768 MiB; 1192 MiB; 2980 MiB |
| the reviewer (R1): the first masked pass after the warm pass; the second | 413 ms; 408 ms |
| the reviewer (R2-7): MSG_WAITALL on a socket with a Python settimeout | 219264 of 6220800 bytes |
| the reviewer (R2-5): SAM3's text model at 33 tokens | ValueError |
| the reviewer (R3-1): a command sent during a 0.4 s stand-in pass beside two refreshes; the loop that pops in an accepting round; the loop that does not | answered after 0.90 s; 0.50 s |
| the reviewer (R3-2): the server's os._exit with a client in the backlog; unread; queued; sending after the exit | ECONNRESET; ECONNRESET; 0 bytes; EPIPE |
| the reviewer (R3): one recvmsg_into, 1 mask into a 3-mask buffer; masks off | 2075656 bytes at the close; 2056 bytes at once |
| the reviewer (R3): the server's highest descriptor after the load, a pass and 11 sockets | 55, against select's FD_SETSIZE 1024 |
| the reviewer (R3): 17 of 877 logged passes have over 20 hits; the most | 95 |

The commands, in short. pass.py: Sam3Backend() from the project, then detect() 17 times
per size and phrase, the first dropped, torch.cuda.synchronize() around each. masks.py and
post.py: the outputs of one encode and one concept, then the library's
post_process_instance_segmentation against a top-3 upsample with
torch.nn.functional.interpolate, torch.cuda.reset_peak_memory_stats() before each.
sock.py: an AF_UNIX server in a second process, a new connection per request, recv_into a
new np.empty. memfd.py: os.memfd_create, subprocess.run with pass_fds, the child opens
/proc/self/fd/N with O_RDONLY and maps it with MAP_POPULATE. stop.py and wake.py:
os.kill(SIGINT) from a second thread. block.py: listen(8), twelve blocking connects with
SO_SNDTIMEO; a socketpair with SO_RCVTIMEO and MSG_WAITALL. The reviewers' scripts:
scratchpad/review1/ and review2/.

## 7. The design gate
**Ownership.** The supervisor owns the process (RUN9). The app owns the Sam3Client: it
creates it after the supervisor and destroys it after every pool thread is joined. The
app holds the Sam3ServerSpecText until SupervisorDestroy, since the probe reads the socket
path from it. The frame block is the app's (module 4). The server process owns its model,
its socket, its unread set and its queue. The vision jobs own the concepts, the priority,
the floor, the mask switch, the mask buffer and the timeout.

**Data in.** Config: the interpreter, the project folder, the nf4 folder, the warm phrase
(SAM3_WARM_UP_PHRASE), the box cap (SAM3_MAX_BOXES_PER_QUERY, 128), the mask threshold
(SAM3_MASK_THRESHOLD, 0.5; today a default argument in sam3/model.py, carried to config). The app: the session folder and the descriptor. A request: its priority, concepts,
floor, masks wanted, and the frame's sequence.

**Data out.** A ProcessSpec. A Sam3Reply: the result, the client's request number, the
boxes, the masks in the caller's buffer. SPAN_SAM3_PASS in record-sam3-<pid>.jsonl.

The timeout is the caller's config value, carried to module 13:
| config value | owner | value | why |
|---|---|---|---|
| VISION_SAM3_TIMEOUT_NS | the vision module | 15 s | the designed worst wait: 8 requests of 7 concepts with Gemma busy, 8 x 818 ms x 1.51 = 9.9 s (derived from measurements, unverified as a whole); a timeout that fires under designed load would leave passes for nobody |

**Mutable state, and its owner.**
| state | written by | read by | how |
|---|---|---|---|
| m_nextRequestId | every pool thread, one add each | the same | an atomic add (Python: next() on itertools.count, one C call under the GIL) |
| the Sam3Reply and the mask buffer | the request's own thread | the same; then the job's message | the caller's own memory; a new mask array per request |
| the connection | the request's own thread | the same | opened and closed inside one call |
| the server's unread set, queue, model, socket | the server's main thread | the same | one thread: no lock |
| mb_stopping | the SIGINT handler (on the main thread) | the loop | a flag; the wake pipe for the poll |

**Threads.** The module starts no thread in the app. Sam3ClientDetect runs on a pool
thread and blocks up to its timeout per system call. The probe runs on the supervisor
thread under its 200 ms cap. The server has one thread of its own; the recorder adds its
writer. The server's stop: SIGINT; the pass in flight ends (at most 841 ms measured, 1.27
s with Gemma busy, derived) and is answered; the unread and queued connections close; exit
0. The kill after 10 s.

**The process.** One server, launched by the supervisor from the spec:
```
setpriv --pdeathsig TERM --                       (the supervisor's prefix, runtime)
<the app's python3> -m sam3.server
  --session <session dir> --socket <session dir>/sam3.sock
  --frames-fd <n> --weights /root/models/vision/sam3-nf4
pass_fds: [<n>], the frame block's memfd (RUN15)
env: one addition, PYTHONPATH=<config.PROJECT_DIR> (RUN16); no working folder needed
log: <log_dir>/proc-sam3.log
stop: SIGINT, no second signal, the kill after 10 s, logged
```
The header's constants:
| name | value | why |
|---|---|---|
| SAM3_SERVER_READY_TIMEOUT_NS | 120 s | import 1.2 s, load 6.3 s, warm pass 1.3 s, measured (8.8 s); a cold disk is slower (unverified how much) |
| SAM3_SERVER_GRACE_NS | 10 s | one pass is under 1.3 s |
| SAM3_SERVER_SEND_TIMEOUT_NS | 1 s | the reply's send: 154 ms at worst beside two busy threads (measured); only a stopped client reaches it |
| kSam3MaxConcepts | 8 | the synonym table's widest entry is 7 ("all the vehicles") |
| kSam3ConceptBytes | 128 | a spoken attribute phrase reached 65 bytes (R1-2); SAM3 reads 32 tokens; the client cuts at a word boundary within 127 |
| kSam3MaxBoxes | 128 | config SAM3_MAX_BOXES_PER_QUERY; a test holds them equal |
| kSam3MaxMasks | 3 | OPEN 1 |
| kSam3QueueCapacity | 8 | one request per pool thread (config VISION_MAX_ACTIVE_TASKS); a test holds them equal |
| kSam3UnreadCapacity | 9 | the queue's 8 and the probe's connect |
| kSam3ServerSocketPathBytes | 108 | sun_path: 107 characters and the NUL |
| kSam3ServerArgvMax | 16 | the argv has 11 entries plus the NULL |

## 7b. The gate, answered (modules/README.md, items 1 to 12)
1. **The real-time path.** Tried: a SAM3 call on the main thread. Stopped: no call of this
   module runs there; the main thread reads the "sam3" row, one atomic load (192 ns,
   runtime's measurement). The queue the module owns is inside the server; the main
   thread never touches it. Its capacity is 8 and its drop policy is none. The listen
   backlog holds 9 more connects; a later one waits its client's SO_SNDTIMEO, then fails
   as SAM3_TIMEOUT (measured: 305 ms for a 300 ms limit). Only timed-out requests can fill
   it.
2. **A logger or a sink.** This module is a client and a server, not a logger. Its types
   hold a socket path, a counter and the two messages. It holds no recorder handle; the
   server calls RecordSpan through its helper.
3. **Fault containment.** Tried: every failure of the server. In the app, each becomes a
   Sam3Result and a false return; the module calls no die() in the app but one: a socket
   path past 107 characters at start (our bug). In the server: RecorderCreate false,
   FramebufferOpen NULL, the load, and any exception in a pass (a GPU out-of-memory) run
   Die there: the record's flush, then _exit(1). The supervisor relaunches it; after three
   failures within 60 s each comes BUDGET_SPENT_DIE, and mid-flight the app's Die hands
   over first (RVW4). FRAME_GONE, INVALID_REQUEST and INVALID_REPLY on a held slot are our
   bugs: the vision job dies (RVW4; the house rule, our code never throws). A user's words
   never reach that path: the client bounds the bytes and the server's tokenizer the
   tokens. A reset connection (ECONNRESET, EPIPE) is SAM3_CLOSED, never an exception (R3-2).
4. **Buffer lifetimes.** Tried: the server reads a slot the writer reuses. Stopped: the job
   acquires before the request and releases after the reply and the record's copy. The
   server never acquires: Find matches the held slot by its sequence. A slot is held for
   the queue wait plus the pass: 0.4 s to 9.9 s (derived worst). The slot count is set by
   the holders, not the time (FB5: 12 for 9 holders). The kept window is W2. The mask
   buffer is a new array per request, so a mask in a VisionResult is never overwritten by
   the next request.
5. **Types and units.** Every duration is a uint64_t of nanoseconds, a macro with UINT64_C.
   The corners are uint16_t pixels, as FrameSize, clamped to the frame before the store.
   The score is a float from 0 to 1. The request id is a uint32_t: at 8 requests a second
   it lasts 17 years. The sequence is the frame block's dword. The span's wait is float
   ms, as the former helper had it. The static_asserts pin 1040, 16 and 8 bytes.
6. **One home.** The messages and the client: here. The frame and its sequence: module 4.
   The spans' enum: the recorder. The merge (TR17): here, moved from sam3/model.py. The
   IoU and containment helpers: util/boxes.py. The relative-confidence gate, the mask
   hygiene, the views: module 13. The socket's one try: util/guarded.py. Every value:
   config. The record helper: section 4 of this header (the former perf_record_sam3.h).
7. **The contract.** The request, the box and the reply header are byte layouts in the
   header, little-endian, sizes asserted. The order on a connection: the client sends one
   request; the server sends the header, 128 box places and the masks, from byte 2056; the
   server closes. The probe's connection sends nothing; the server reads 0 bytes and
   closes it. The span:
   `{"k":"span","t":0,"s":"sam3_pass","a":...,"b":...,"p":{"req":41,"wait":12.5,"boxes":3}}`.
   The log: proc-sam3.log. The readers that change: section 9's table.
8. **The Python mapping.** Section 8. Thread-local state: none. A put that can block: none;
   the heap is a list. An exception that can leave the client: only our own bug. The GIL:
   released once for the whole reply, by one recvmsg_into with MSG_WAITALL on a blocking
   socket. Held for the pack and unpack (under 1.5 us) and the box tuple (2.2 us for 19,
   12.5 us for 128). The client never calls settimeout (R2-7).
9. **The cost budget.** The hottest app thread this module touches is a pool thread. A
   request costs it 0.50 ms at 1080p p50 with the app idle. Beside one or two busy Python
   threads, the server's send takes 1.4 ms p50 and 154 ms at worst (one read, R2-2). The
   pool thread holds the GIL under 15 us per request. At 8 requests a second, that is 120
   us a second. The main thread pays the
   row's load, 192 ns a frame: 0.06 % of 330 us. The full app's number is unverified until
   the build measures it. The server's main thread is the GPU's pace: 383 to 841 ms a pass.
10. **Deterministic checks.** `gcc -fsyntax-only -Wall -Wextra -std=c11 -pedantic -x c
    -I01-recorder -I03-runtime -I01-perf -I06-sam3_server` on both headers: clean.
    `tools/style/header_layout.py`: ran. No drawing. The names: section 8's table.
11. **TOCTOU.** W1 to W10 in the internal header, each with its test in section 9:
    - W1, the row says UP, then the request: closed; the client reads no row.
    - W2, Find, then the read: closed by the job's hold; kept: the job's timeout inside the
      pass's 0.2 ms slot copy; the torn result goes to a closed socket.
    - W3, the reply after the job gave up: closed; one connection per request.
    - W4, the stale socket file, then the bind: closed by the order (exit, relaunch,
      unlink, bind); kept: another process of this user in the session folder.
    - W5, the probe, then a pass: closed; the bind follows the warm pass, and the kernel
      completes the probe's connect in the backlog, also during a pass.
    - W6, SIGINT during the load: closed; the flag is read after the load.
    - W7, a pop, then SIGINT: closed; the flag is read after each pass.
    - W8, the flag is clear, then the poll: closed; SIGINT's byte on the wake pipe makes
      the poll return.
    - W9, the accept, then the request's bytes: closed; the read waits for the poll, never
      on the client.
    - W10, the accept, then the pop: closed; a round that accepted pops nothing, so the new
      request is read first; kept: a client whose bytes come after that poll waits one
      pass.
12. **Need.** Every row below names its cause. The mechanisms this design adds, each with
    its cause:
    - the top-3 mask post-process: SEEN, 82 hits measured;
    - the merge by IoU across the concepts: SEEN, 47 logged passes;
    - containment kept within one concept: SEEN, the logged drawers;
    - the clamp of the corners: SEEN, 580 of 4296 logged boxes;
    - no upsample for no box: SEEN, 72 of 877 logged passes;
    - the client's byte bound and the tokenizer's token bound: DESIGNED, an utterance's
      length is the user's; 9 nouns in one list; 44 tokens in 100 bytes of digits;
    - one read for the whole reply: DESIGNED, every masked reply beside a busy app thread;
    - the read only after the poll, and no pop in a round that accepted: DESIGNED, a client
      waits for its GIL; a command arrives during a pass;
    - the socket unlink before the bind: DESIGNED, a crashed listener leaves its file, and
      the next bind fails with EADDRINUSE (measured).
    Round 1 removed two: the STATUS message and the echoed id. Everything else is the
    generic handling.

**The failure matrix.**
| failure | cause | the module's state | the record | the aircraft |
|---|---|---|---|---|
| a GPU out-of-memory in a pass | the ruling (2026-09-23, section 9); not seen with this post-process (1192 MiB at worst, 2.6 GiB free beside llama-server) | Die in the server, exit 1; the supervisor relaunches after 1.5 s; ready again in about 9 s | the server's traceback in proc-sam3.log; every waiting client SAM3_CLOSED; the jobs FAILED | never touched |
| many hits at a low floor | SEEN (82 hits, measured) | masks only for the first 3 boxes: 43 MiB, 2.2 ms | | never touched |
| one object found under each synonym | SEEN (47 logged passes) | one box: the merge by IoU across the concepts | | never touched |
| a part inside its whole (a drawer in a dresser) | SEEN (session-20260912-183503-rog) | both kept: containment merges within one concept only | | never touched |
| a box past the frame's edge | SEEN (580 of 4296 logged boxes) | the corners clamped | | never touched |
| a pass with no box and masks on | SEEN (72 of 877 logged passes with no hits) | no upsample; SAM3_OK with 0 boxes | | never touched |
| a spoken phrase over 127 bytes, over 8 concepts, or over 32 tokens | DESIGNED: an utterance's length is the user's, and "128s" truncates without its NUL; R1-2's list of 9 nouns; 112 bytes of plain words make 25 tokens, digits 44 tokens in 100 bytes (R3-6) | the client cuts at a word boundary and keeps 8; the server's tokenizer truncates at 32 | | never touched |
| a masked reply while app threads hold the GIL | DESIGNED (every pass beside the frame loop) | one read for the whole reply: 1.4 ms p50, 0 of 80 lost | | never touched |
| a client slow to send its request (it waits for the GIL) | DESIGNED (every request beside a busy app thread) | the connection waits in the poll; the server never blocks on it | | never touched |
| a request while the server loads or relaunches | DESIGNED (every launch) | SAM3_REFUSED in under 0.1 ms; false | the job says not ready | never touched |
| the restart budget spent | DESIGNED (three failures within 60 s each) | the supervisor's Die (BUDGET_SPENT_DIE) | the die event | mid-flight: the hand-over first (RVW4) |
| the load or the frame block fails at start | DESIGNED (a missing file, a wrong package: the preflight's job) | Die in the server; relaunched three times; then the app dies at start | proc-sam3.log | none yet at start |
| a stale socket file at a relaunch | DESIGNED (every crash) | the server unlinks it, then binds | | never touched |
| Gemma busy slows a pass | SEEN (x1.51, assessment R2) | accepted (S4); the timeout covers it | the span's duration | never touched |
| a refresh waits behind commands | DESIGNED (speech during a highlight) | it waits; the order is the design | the span's wait key | never touched |
| the job's timeout during the wait or the pass | no cause in designed load (15 s against 9.9 s) | generic: SAM3_TIMEOUT, false; the pass runs for nobody; the send fails and is dropped | the app's span, ok 0 | never touched |
| a 9th request on a full queue | no cause (8 by construction) | generic: the backlog holds 9; past it the connect waits its SO_SNDTIMEO, then SAM3_TIMEOUT | | never touched |
| a pass that never ends (a GPU hang) | no cause (never recorded) | generic: every client times out (LLM1 D3) | ok 0 spans | never touched |
| a client stopped mid-request (SIGSTOP) | FORCED | generic: its connection waits in the poll until it closes; the reply's send times out at 1 s | | never touched |
| SIGKILL of the server; a power cut | FORCED | generic: the supervisor's restart | the recorder's last 5 s lost | never touched |
| the server exits with connects in the backlog or unread | the ruling (2026-09-23) for the out-of-memory; FORCED for a kill | each client gets ECONNRESET or EPIPE: SAM3_CLOSED (R3-2) | the jobs FAILED | never touched |
| a malformed request or reply | DESIGNED only as our bug | INVALID_REQUEST or INVALID_REPLY; the job dies (RVW4) | the die event | the hand-over (RVW4) |

## 8. The notes that did not make the header
- **Why not a listener thread beside a GPU thread.** It reads requests during a pass, so
  a command that arrives mid-pass is ordered before the pass ends. The single loop orders
  it at the pass's end, which is when the GPU frees anyway. The second thread would add a
  lock, a condition variable and a stop for each. Rejected.
- **Why one connection per request.** A connect costs microseconds on this socket; a pass
  costs 400 ms. One connection binds one reply to one request (W3). Rejected: a kept
  connection per pool thread, which needs a reader per connection in the server.
- **Why no STATUS message and no echoed id (round 1).** The socket exists only after the
  warm pass, so a completed connect already says ready. One connection per request binds a
  reply to its request. Both were mechanisms for windows already closed (R1-5, R1-6).
- **Why a fixed reply layout.** The client must place every byte before the one read. So
  the boxes take their 128 places (2048 bytes) even when few are valid, and the masks start
  at byte 2056. The 2 KB cost nothing beside 6.2 MB of masks.
- **Why no deadline in the request.** A deadline lets the server skip a pass whose client
  gave up. Its cause would be a timeout under designed load; the 15 s timeout leaves none
  (gate item 12). Rejected until a session log shows a SAM3 timeout.
- **Why no re-check of the sequence after the copy.** It would catch a slot overwritten
  during the colour copy. That happens only after the job released, so nobody reads that
  reply. Rejected (gate item 12).
- **Why the client allocates the request id.** The join of the two spans needs one number
  per request, not per job. The caller learns it from the reply.
- **Why the boxes carry a concept index, not a label.** The caller holds the concepts. One
  byte per box, no string on the socket.
- **Why masks are bytes, not bits.** The recorder takes GRAY8 at the frame size (FrameView);
  the draw blends a byte mask. Bits would add a pack in the server and an unpack in the job
  for 6.2 MB that cross in 0.50 ms.
- **Why the server reuses runtime's Die.** One home for "an uncaught exception ends the
  process". In the server only the record's flush is registered, so Die is the flush and
  _exit(1). The hand-over and the notify are the app's alone.
- **Why the server unlinks its own socket file.** It created the path, and it runs after the
  old process exited. llama-server cannot do it, so it needs the supervisor's
  m_removeBeforeLaunch (carried in LLM1); this module does not.
- **The cold first pass of more concepts.** The warm pass has one concept. The first 7-concept
  pass after it took 766 ms against 799 ms p50: no extra cold cost measured. The first
  masked pass took 413 ms against 408 ms (the reviewer).
- **The names, C and Python.**
  | C (the header) | Python (the build) |
  |---|---|
  | Sam3ServerSettingsFromConfig(sessionDir, framesFd) | sam3_server_settings_from_config(session_dir, frames_fd) |
  | Sam3ServerProcessSpec(settings, logDir, text) | sam3_server_process_spec(settings, log_dir) |
  | Sam3ServerConnectProbe(ctx) | sam3_server_connect_probe(socket_path), bound by partial |
  | kSam3ServerStopPolicy | SAM3_SERVER_STOP_POLICY |
  | Sam3Request, Sam3Box, Sam3ReplyHeader | struct.Struct("<xBBBIIf" + "128s" * 8), a numpy dtype of 16 bytes, struct.Struct("<BBBxHH") |
  | Sam3ClientCreate, Sam3ClientDetect, Sam3ClientDestroy | sam3_client_create, sam3_client_detect(client, request, timeout_ns, masks), sam3_client_destroy |
  | Sam3Result, SAM3_OK ... | an enum.Enum Sam3Result |
  | RecordSam3Pass(start, end, req, waitMs, boxes) | record_sam3_pass(...), in sam3/record_sam3.py |
  | Sam3ServerMain, Loop, ReadRequest, RunOne | sam3/server.py: main(), _loop(), _read_request(), _run_one() |
  | Sam3ModelDetect, Sam3MergeNested | sam3/model.py: detect(), merge_nested() |

**The Python mapping.** `sam3/server.py` about 160 lines, `sam3/client.py` about 80,
`sam3/model.py` about 160 (no lock, no cache).
```python
# sam3/server.py: the one loop
def _loop(s):
    while not s.stop.is_set():
        watch = [s.wake_r] + s.unread
        if len(s.unread) < SAM3_UNREAD_CAPACITY:
            watch.append(s.listen)
        wait = 0 if s.pending else None                 # a request queued: do not sleep
        readable = select.select(watch, [], [], wait)[0]
        accepted = False
        for conn in readable:
            if conn is s.listen:
                s.unread.append(s.listen.accept()[0])   # one; the poll said readable
                accepted = True
            elif conn is s.wake_r:
                os.read(s.wake_r, 64)                   # SIGINT's byte; the flag is set
            else:
                _read_request(s, conn)
        if accepted:
            continue                                    # read the new request before a pop (R3-1)
        if s.pending:
            _run_one(s)
    return

def _read_request(s, conn):
    s.unread.remove(conn)
    raw = recv_now(conn, REQUEST.size)                  # util/guarded.py: MSG_DONTWAIT; bytes or None
    if raw is None or len(raw) != REQUEST.size:         # the probe, a client gone, a short read
        conn.close()
        return
    request = unpack_request(raw)
    status = check_request(request)                     # pure
    if status is not SAM3_STATUS_OK:
        send_status(conn, status)
        conn.close()
        return
    entry = Pending(request, conn, monotonic_now(), next(s.arrivals))
    heapq.heappush(s.pending, (request.priority, entry.arrival, entry))
    return

# sam3/client.py
def detect(self, request, timeout_ns, masks):
    req = next(self.ids)
    raw = pack_request(bounded(request), req)           # concepts cut to 127 bytes, 8 at most
    # util/guarded.py, the socket domain's one try: a blocking socket with SO_SNDTIMEO and
    # SO_RCVTIMEO (never settimeout); connect, sendall, then ONE recvmsg_into([header,
    # boxes, masks], 0, MSG_WAITALL) ended by the server's close; it returns the count and
    # the failure kind: ECONNREFUSED and ENOENT are REFUSED, EAGAIN on connect or a
    # timeout is TIMEOUT; 0 bytes, a count short of its status's length, ECONNRESET and
    # EPIPE are CLOSED. The numpy mask array goes in as it is (a memoryview cast of a
    # zero-length array raises)
    count, failure = sam3_exchange(self.socket_path, raw, self.header, self.boxes, masks, timeout_ns)
    return reply_from(req, self.header, self.boxes, masks, count, failure)   # pure
```
- The header and box buffers in the sketch are per call in the build (a bytearray of 8 and
  of 2048), so two pool threads never share them.
- The server's GIL: one Python thread and the recorder's writer. torch releases the GIL in
  its kernels.
- signal.set_wakeup_fd needs a non-blocking pipe and the main thread; both hold here.
- The masks: the caller's np.empty((n, h, w), np.uint8) per request; a fixed size, never
  growing; 0.83 us to allocate, the page faults inside the read.

## 9. The tests the module ships with (`test/test_sam3_server.py`)
Change impact:
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| SAM3 in its own process; the frame by its sequence | where a pass runs; the app no longer imports torch | yes, on purpose (T6, S2 a, FB4) | test_vision's SAM3 tests rewritten against the server |
| DETECT_NOT_READY becomes SAM3_REFUSED; a failure has a kind | the job's "not ready" | no visible change | the vision call sites rewritten |
| masks only for the first 3 boxes (OPEN 1) | a highlight with more than 3 objects | yes: boxes 4 and on show no mask | new |
| mask_for_box and its cache go; masks come in the reply | the engine's apply_masks | no visible change for the first 3 boxes | the engine tests rewritten |
| the merge (TR17) runs in the server: IoU across the request's concepts, containment within one | one object found under several synonyms | yes: one box, not one per synonym (R1-1, R2-1) | test_merge_nested moves here, with new cases |
| the colour copy by cv2.cvtColor | about 24 ms less per 1080p pass | no | new: the boxes against today's within 2 px |
| the tokenizer truncates at 32 tokens | a phrase over 32 tokens | yes: today it raises | new |
| the record "sam3" becomes SPAN_SAM3_PASS in the server and SPAN_SAM3_REQUEST in the app | log/perf_report.py | yes, on purpose (RCD1) | the report tests rewritten |

The tests:
- `test_request_box_and_header_sizes_match_the_c_layout`: 1040, 16, 8.
- `test_header_constants_equal_config`: kSam3MaxBoxes, kSam3QueueCapacity.
- `test_check_request_refuses_each_bad_field`.
- `test_pending_queue_pops_commands_before_refreshes_in_arrival_order`.
- `test_merge_on_real_boxes_from_past_runs` (TR17 (3), no GPU): the 47 logged passes give
  2.98 objects in the top 3; the drawer passes keep all 16 drawer boxes (R1-1, R2-1); the
  95-hit pass keeps a count past 255 safe (R3-7).
- `test_a_long_concept_is_cut_at_a_word_and_9_concepts_send_8` (R1-2, R2-4).
- `test_a_phrase_over_32_tokens_is_truncated_not_raised` (R2-5).
- `test_a_masked_reply_beside_two_busy_threads_is_never_lost` (R1-3, R2-2).
- `test_a_client_slow_to_send_never_blocks_the_server` (R2-3, W9).
- `test_a_command_sent_during_a_pass_runs_before_a_refresh_read_earlier` (R3-1, W10).
- `test_an_ok_reply_and_a_status_reply_have_their_stated_lengths` (R3-3).
- `test_a_pass_with_no_hits_and_masks_on_replies_ok_with_no_boxes` (R1-4).
- `test_corners_past_the_frame_are_clamped`.
- `test_a_short_header_is_closed_not_invalid` (R1-8).
- `test_the_client_socket_has_no_python_timeout` (R2-7).
- `test_spec_is_pure_and_passes_the_memfd`: argv, pass_fds, the PYTHONPATH addition, the
  probe, the stop policy, BUDGET_SPENT_DIE, the log path; a 108-character socket path dies.
- `test_probe_is_false_before_the_bind_and_true_during_a_pass` (W5).
- `test_request_to_a_dead_server_is_refused_in_under_1_ms` (W1).
- `test_reply_after_the_client_gave_up_is_dropped_and_the_next_request_is_served` (W3).
- `test_frame_gone_when_no_slot_holds_the_sequence`.
- `test_held_slot_is_never_torn_during_a_pass`: a writer at 30 frames a second, 8 jobs
  holding; every reply's frame matches its sequence (W2).
- `test_relaunch_after_a_stale_socket_file_comes_up` (W4).
- `test_sigint_during_the_load_exits_0_without_a_bind` (W6).
- `test_sigint_during_a_pass_answers_it_then_exits_0` (W7).
- `test_sigint_while_idle_wakes_the_poll_and_exits_0` (W8).
- `test_an_exception_in_a_pass_exits_1_and_every_client_sees_closed`: the generic handling
  of the out-of-memory row, by an injected exception; one client in the backlog, one
  unread, one queued (R3-2).
- `test_masks_only_for_the_first_max_masks_boxes_at_the_block_size`.
- `test_span_has_req_wait_and_boxes` and the join with the app's span by req.
- `test_gpu_one_pass_matches_todays_boxes_within_2_px` (GPU, opt-in, under tools/lock.sh).
