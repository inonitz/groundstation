# The SAM3 server review record (rev5 module 6)

The module's files: `../modules/06-sam3_server/sam3_server.md`, `sam3_server.h`,
`sam3_server_internal.h`. The brief: `../modules/06-sam3_server/brief.md`. Three reviewer
rounds, each answered by the author agent, then the conclusions.

## Round 1: reviewer

Read in full: sam3_server.md, sam3_server.h, sam3_server_internal.h, the brief (sections 3
and 4), gate item 12. Read as contracts: runtime.h and runtime_internal.h, framebuffer.h and
framebuffer_internal.h, recorder.h, frame_types.h, record_span.h, recorder.md, runtime.md
(the probe). Read as today's code: sam3/model.py, perception2/vision.py, perception2/concept.py,
config/constants.py. The scripts and their output sit in the reviewer's scratch folder
(.../scratchpad/review1/: backlog.py, gil.py, gil_waitall.py, gpu.py). The GPU runs were
under tools/lock.sh (sam3_review), with the GPU otherwise idle at 159 MiB.

### R1-1. The per-concept merge lets synonym duplicates of one object take all three masks
- **Severity:** HIGH.
- **Cause:** SEEN. The session logs hold 47 passes with two or more concepts
  (logs/sessions/*/perception/*/pass_*.json, raw_dets). I ran today's merge rule (same label
  only, IoU over 0.5 or containment over 0.7) on them, then took the first 3 boxes. In 47 of
  47 passes the top 3 held a duplicate of one object under another concept. Example,
  session-20260919-151639-rog, 0003-describe, pass 1: cabinet 0.856, dresser 0.848, chest of
  drawers 0.762, all at [680, 278, 872, 524]. The top 3 covered 1.06 distinct objects on
  average. With the merge across the request's concepts they covered 2.91. In 46 of 47 passes
  an object lost its mask.
- **Where:** sam3_server_internal.h, Sam3MergeNested ("a kept box of the same concept");
  sam3_server.md section 4, "The nested-box merge (TR17) lives in the server".
- **What is wrong:** The request's concepts are the synonym fan-out of one user noun
  (concept.py: "dresser" -> dresser, chest of drawers, cabinet). SAM3 finds the same object
  under each synonym. The merge keeps one box per concept, so the cut to kSam3MaxMasks hands
  all 3 masks to one object. The document's own reason for merging before the cut ("a nested
  duplicate must not take a mask from a second object") fails for the main input. The usage
  instance in section 3 is this exact case. Today the loss is hidden, since every box gets a
  mask (HL_MAX 128). OPEN 1's recommendation "the best three boxes carry masks" rests on it.
- **The smallest fix:** Merge across all concepts of one request: drop the same-concept
  condition, keep the higher score's concept index. One request carries one noun's
  synonyms, so this merges duplicates, not neighbours. Record the behaviour change in the
  change-impact table. TR17's test on past boxes gets these 47 passes as its cases.

### R1-2. A long spoken description or a long list crashes the app through the bug path
- **Severity:** HIGH.
- **Cause:** DESIGNED. The trace: the operator says "highlight the man in the yellow jacket
  with the black backpack and the blue cap". phrase_concepts() keeps attributes and strips
  only relational clauses; "with" is not one. It returns "man in the yellow jacket with the
  black backpack and the blue cap", 65 bytes (run on today's concept.py). The client packs
  it with "64s". struct.pack truncates to 64 bytes with no error and no NUL (run:
  len 64, last byte not 0). The server's Sam3CheckRequest refuses "a concept without its NUL":
  INVALID_REQUEST. Gate item 3 says the vision job raises on INVALID_REQUEST and the crash
  hook runs Die: the hand-over to the RC mid-flight. A list of 9 or more comma-separated
  nouns takes the same path: struct.pack raises struct.error for a ninth "64s" argument.
- **Where:** sam3_server.h, kSam3ConceptBytes and kSam3MaxConcepts; the Python mapping
  struct.Struct("<BBBBIIf" + "64s" * 8); sam3_server.md section 7, "an attribute phrase is
  under 40" (unverified, and false for the sentence above); gate item 3.
- **What is wrong:** Both bounds hold the user's words, not our code. A user's sentence
  reaches the "our bug" path, and that path ends the flight.
- **The smallest fix:** The client bounds its input before the pack. It cuts a concept at
  the last word boundary within 63 bytes, and it sends at most kSam3MaxConcepts concepts. The
  server's check stays for real bugs. Add a test with the 65-byte concept above and one with
  9 concepts. No new status is needed.

### R1-3. The reply's drain waits on the app's GIL about 30 times, and the server's one thread waits with it
- **Severity:** MEDIUM.
- **Cause:** DESIGNED. The trigger is every reply with masks while another Python thread of
  the app runs. The size of the effect in the real app is unverified; the mechanism is
  measured. gil.py: a server process sends header, 19 boxes and 3 masks at 1080p (6.22 MB) by
  sendall with the design's 1 s timeout. The client reads with recv_into in a loop on a
  socket with settimeout(15), as section 8 has it. SO_SNDBUF is 212992 bytes, so the reply
  needs about 30 reads. Results, 40 replies each:
  | client process | server sendall p50 | p95 | max |
  |---|---|---|---|
  | idle | 0.88 ms | | 2.47 ms |
  | one CPU-bound Python thread | 173 ms | 209 ms | 219 ms |
  | two CPU-bound Python threads | 1000 ms: every send timed out | | |
  Each read must take the GIL back, and a busy holder keeps it up to the 5 ms switch interval.
  The server's one thread is blocked for the whole drain, so the GPU idles. With two busy
  threads every reply was lost at the 1 s total sendall timeout (Python 3.5 and later: "the
  socket timeout is now the maximum total duration to send all data",
  https://docs.python.org/3/library/socket.html#socket.socket.sendall). The client then sees
  SAM3_CLOSED.
- **Where:** sam3_server.md section 6 (the 0.50 ms round trip, measured with an idle client),
  gate item 8 ("held for the pack and unpack (under 1.5 us)"), gate item 9 (the cost budget);
  sam3_server.h, Sam3ClientDetect ("one socket timeout of timeoutNs for each step").
- **What is wrong:** The cost budget counts the client's GIL time but not its GIL waits. The
  waits land on the server's single thread, which is the GPU's only feeder.
- **The smallest fix:** Read each part in one system call. Keep the client socket blocking,
  set SO_RCVTIMEO to the timeout, and read the boxes and the masks with
  recv_into(view, n, socket.MSG_WAITALL). The kernel then fills the whole buffer with one GIL
  release. gil_waitall.py measured: one busy thread 5.9 ms p50, 6.5 ms max; two busy threads
  6.2 ms p50, 76 ms p95, 629 ms max. It removes the Python read loop; it adds nothing. Then
  measure the round trip in the app itself (the frame loop, the recorder writer and the pool
  running) before the number goes into gate item 9.

### R1-4. A pass with no hits and masks on raises in the upsample and kills the server
- **Severity:** MEDIUM.
- **Cause:** DESIGNED. "No hits" is a normal result (2026-09-23: "'Not ready' and 'no hits'
  are not failures"). A live highlight with masks on gets no hits whenever its object leaves
  the view. gpu.py ran the pass as section 3 of the internal header lists it. On zero kept
  hits, torch.nn.functional.interpolate raised "RuntimeError: Non-empty 4D data tensor
  expected but got a tensor with sizes [1, 0, 288, 288]". In the server that exception runs
  Die and exit 1. Three such passes within 60 s spend the budget, and BUDGET_SPENT_DIE ends
  the app.
- **Where:** sam3_server_internal.h, Sam3ModelDetect ("the low-resolution masks of the first
  m_maxMasks boxes upsampled"); sam3_server.md section 9 (no test covers it). The warm pass
  asks no masks on a black frame, so it never runs this step.
- **What is wrong:** The pass steps state no case for zero boxes, and the tests miss it.
- **The smallest fix:** One sentence in Sam3ModelDetect: the mask count is the minimum of
  m_maxMasks and the kept boxes, and a count of 0 skips the upsample. Add
  test_a_pass_with_no_hits_and_masks_on_replies_ok_with_no_boxes. It needs the GPU, or a
  CPU stand-in tensor of shape [1, 0, 288, 288].

### R1-5. The STATUS probe races passes after every relaunch; a bare connect is the whole probe
- **Severity:** LOW.
- **Cause:** DESIGNED. runtime.md: the probe runs after every launch until UP. The trace: a
  GPU out-of-memory, then exit 1, then the relaunch. A live highlight keeps asking (REFUSED)
  until the bind. Its first DETECT starts a pass of 400 to 1270 ms. A probe that connects
  during that pass is answered only after it, past the 200 ms cap, so it is false. The UP row
  waits for a probe that lands in a gap. That costs seconds, not a failure.
- **Where:** sam3_server.md section 4 ("The probe runs only before UP, when no pass runs"),
  gate item 11 W5 ("closed"); sam3_server.h, SAM3_REQUEST_STATUS, SAM3_STATUS_READY,
  Sam3ServerStatusProbe; the STATUS branch of _accept_pending.
- **What is wrong:** The claim is false after a relaunch. The message kind it relies on is
  also not needed: the socket exists only after the warm pass, so a completed connect already
  means ready.
- **The smallest fix:** Remove SAM3_REQUEST_STATUS, SAM3_STATUS_READY and the STATUS branch.
  The probe is connect() then close(). backlog.py measured: a connect to a listener that
  never accepts completes in 5 us, and the server's later recv on it returns 0 bytes in 6 us
  (the existing "short read: close" path). m_kind can then go too; keep the byte as padding
  so the request stays 528 bytes.

### R1-6. The echoed request id guards a window one connection per request already closes
- **Severity:** LOW.
- **Cause:** none. A reply on a connection can only answer that connection's request (W3).
  A timed-out client has closed its socket, so a late reply reaches nobody.
- **Where:** sam3_server.h, Sam3ReplyHeader.m_requestId; SAM3_INVALID_REPLY ("a request id
  not ours"); the internal header, W3 ("the client also checks the echoed id");
  framebuffer_internal.h ("dropped by its request id (module 6)").
- **What is wrong:** A second mechanism for a closed window, with a crash path (INVALID_REPLY
  raises) that only our bug can reach.
- **The smallest fix:** Remove m_requestId from the reply header (it becomes 8 bytes) and the
  id check. The client copies its own req into Sam3Reply.m_requestId. The server keeps req
  from the request for its span. Carry the one-line correction of the frame buffer's comment.

### R1-7. A connection past the listen backlog fails at once; it does not wait
- **Severity:** LOW.
- **Cause:** none. Live connections are at most 8 pool threads and 1 probe; the kernel holds
  backlog + 1 = 9.
- **Where:** gate item 1 ("a 9th connection waits in the listen backlog inside its client's
  timeout"); sam3_server_internal.h, Sam3PendingQueue ("waits in the listen backlog inside its
  own client's timeout").
- **What is wrong:** backlog.py, listen(8), no accept: connections 1 to 9 succeeded; the 10th
  raised BlockingIOError (EAGAIN) in 13 us. Python's settimeout makes the socket non-blocking,
  and an AF_UNIX connect on a full backlog then returns EAGAIN (connect(2): "For nonblocking
  UNIX domain sockets, the socket is nonblocking, and the connection cannot be completed
  immediately"). The text describes a wait that never happens.
- **The smallest fix:** Correct the two sentences. Name the mapping in the client: EAGAIN on
  connect is SAM3_REFUSED. No mechanism.

### R1-8. Two failure classes contradict each other
- **Severity:** LOW.
- **Cause:** FORCED for the first; none for the second.
- **Where:** sam3_server.h, Sam3Result: SAM3_CLOSED ("closed before the whole reply") and
  SAM3_INVALID_REPLY ("a short header"); sam3_server.md section 3, instance 2, against gate
  item 3.
- **What is wrong:** A stream socket gives a short header only when the server's side closed
  mid-header, which is a server SIGKILL mid-send. That is CLOSED, the generic handling. Filed
  under INVALID_REPLY it raises and runs Die, so a FORCED kill of the server would end the
  flight. Second: instance 2 returns FAILED for every result but OK and REFUSED, while gate
  item 3 says FRAME_GONE, INVALID_REQUEST and INVALID_REPLY raise. Module 13 needs one answer.
- **The smallest fix:** "a short header" moves to SAM3_CLOSED. Instance 2 raises on the three
  bug results, as gate item 3 says.

### R1-9. Two header constants restate config values
- **Severity:** LOW.
- **Cause:** none.
- **Where:** sam3_server.h, kSam3QueueCapacity = 8 (config VISION_MAX_ACTIVE_TASKS) and
  kSam3MaxBoxes = 128 (config SAM3_MAX_BOXES_PER_QUERY); _accept_pending's
  "len(s.pending) < SAM3_QUEUE_CAPACITY".
- **What is wrong:** Gate item 6 says "Every value: config", yet two values have two homes. In
  Python the heap is a list and the cap guards nothing: the clients bound it.
- **The smallest fix:** The Python build reads both from config. Drop the cap check in
  _accept_pending. Keep the C constants only as array sizes, with a test that they equal
  config.

### R1-10. The inherited read-write descriptor stays open in the server
- **Severity:** LOW.
- **Cause:** none. Only our own bug could map it writable.
- **Where:** sam3_server.md section 2 item 4 and framebuffer.h section 4 ("the kernel refuses
  a writable mapping: the server cannot touch a count (RVW3)").
- **What is wrong:** memfd_create returns a read-write descriptor, and pass_fds hands that
  descriptor to the child as it is. FramebufferOpen reopens /proc/self/fd/N read-only, but
  N itself stays open and read-write. A writable map through N succeeds. The guarantee holds
  for the new descriptor only.
- **The smallest fix:** FramebufferOpen closes N after the read-only reopen. One line in
  module 4, carried to the manager (PAR2).

### R1-11. The launch depends on the app's working folder
- **Severity:** LOW.
- **Cause:** none in flight (run.sh starts the app in the project folder). The tests that
  launch a real server (W4, W6, W7) run wherever pytest runs; test/support.py fixes sys.path,
  not the child's.
- **Where:** sam3_server.md section 7, "cwd: the app's, the project folder (run.sh starts the
  app there)"; ProcessSpec has no working-folder field.
- **What is wrong:** `python3 -m sam3.server` finds the sam3 and config packages only when
  the working folder is the project folder. From any other folder the child fails at import,
  is relaunched three times, and the app dies at start.
- **The smallest fix:** One env addition, which RUN16 allows: PYTHONPATH=<the project
  folder>, from config.

### R1-12. The TOCTOU list misses the idle wait
- **Severity:** LOW.
- **Cause:** DESIGNED (every stop while the server is idle). The mechanism exists and works;
  it is only missing from the list gate item 11 requires.
- **Where:** sam3_server_internal.h, the TOCTOU list.
- **What is wrong:** "The flag is clear, then the wait in poll" is a window. A SIGINT between
  the two would sleep forever without the wake pipe. The wake pipe closes it (the signal's
  byte makes the poll return), but no W names it.
- **The smallest fix:** Add W8 with that sentence. No code change.

### Checked and sound
- The byte layouts. gcc -fsyntax-only -Wall -Wextra -std=c11 -pedantic on both headers with
  the recorder, runtime and perf folders: clean. Python: struct "<BBBBIIf" + "64s" * 8 is 528
  bytes, "<IBBBxHH" is 12 bytes, the box dtype is 16 bytes; the offsets match the C structs.
- The FrameSize clash. Including framebuffer.h beside sam3_server_internal.h fails with
  "conflicting types for FrameSize", as the document says; the tag declaration avoids it.
- The server's GPU footprint (gpu.py, 1080p, market-0.jpg). After the load the process used
  768 MiB. After an 8-concept pass by the design's own post-process (87 hits at 0.12, the top
  3 masks) it used 1192 MiB, with a reserve of 1020 MiB. The library path on the same request
  took the process to 2980 MiB. With llama-server's 4.2 GiB the design leaves about 2.6 GiB
  of the 7.96 GiB.
- The warm pass covers the mask path's cold cost. The first masked pass after the black-frame
  warm pass took 413 ms; the second took 408 ms.
- The 8-concept pass took 797 ms, consistent with the table's 818 ms p50 for 7 concepts.
- select with set_wakeup_fd. The C-level handler writes the byte; PEP 475 retries the select
  after the Python handler returns; the byte then wakes it. The flag and the poll run on one
  thread, so no lock is needed.
- The reply to a client that gave up. CPython ignores SIGPIPE at start, so the send raises
  BrokenPipeError and the server goes on. The 1 s sendall limit is a total, not per chunk
  (measured 1004 ms on a slow reader).
- The relaunch and the record file. The file name carries the pid (recorder.md, OPEN 2), so
  a relaunched server never finds its file existing.
- The numbers. 8 x 818 x 1.51 = 9.9 s. 841 x 1.51 = 1.27 s. 2^32 requests at 8 a second last
  17.0 years. 3 masks at 1080p are 6,220,800 bytes. The block is 12 x 6,220,800 = 74.6 MB at
  1080p. The argv has 11 entries. 192 ns is 0.06 % of the 330 us budget.
- Freezing the boxes into a tuple costs 2.2 us for 19 boxes and 12.5 us for 128 (measured).
  That is above the stated 1.5 us but still negligible.
- The slot count. 8 pool holds, the draw, the writer, the latest and a spare fit the 12
  slots (FB5).

Counts: HIGH 2, MEDIUM 2, LOW 8.

## Round 1: answer
The author checked three claims before the answer: the R1-1 example pass (cabinet, dresser and
chest of drawers on one box, as cited), a blocking connect past the backlog (R1-7), and
MSG_WAITALL with a kernel timeout (R1-3). The checks found one more fault, R1-13 below.

| finding | answer | cause and evidence | change made |
|---|---|---|---|
| R1-1 | Accepted | SEEN: 47 logged passes; the author read session-20260919-151639-rog, 0003-describe, pass 1 | Sam3MergeNested spans the request's concepts; section 4 says why; the change-impact row; the test gets the 47 passes |
| R1-2 | Accepted | DESIGNED: the 65-byte phrase traced through concept.py and the "64s" pack | the client cuts a concept at its last word boundary within 63 bytes and sends at most 8; the constants table; a test |
| R1-3 | Accepted | DESIGNED: every masked reply beside a busy app thread; measured 173 ms and lost replies | Sam3ClientDetect: a blocking socket, SO_SNDTIMEO and SO_RCVTIMEO, one recv_into with MSG_WAITALL per part; gate items 8 and 9; a test. The author's check: a partial read returns its count at the timeout (100 of 1000 bytes after 305 ms), so a short count maps to SAM3_TIMEOUT and 0 bytes to SAM3_CLOSED |
| R1-4 | Accepted | DESIGNED: a highlight whose object left the view, with masks on | the mask count is the smaller of m_maxMasks and the boxes; 0 skips the upsample; a failure-matrix row; a test |
| R1-5 | Accepted | DESIGNED: the probe after a relaunch while a pass runs | SAM3_REQUEST_STATUS, SAM3_STATUS_READY and the STATUS branch removed; Sam3ServerConnectProbe is a connect and a close; m_kind is m_pad0; W5 corrected |
| R1-6 | Accepted | none: one connection per request closes W3 | m_requestId left the reply header (8 bytes now); the client keeps its own number in Sam3Reply; the frame buffer's comment carried to the manager |
| R1-7 | Narrowed | none for the 10th connect; the text was wrong for a non-blocking socket | with R1-3's blocking socket the wait is real: the author measured the 10th connect fail with EAGAIN after 305 ms for a 300 ms SO_SNDTIMEO. The text now says so; EAGAIN on connect maps to SAM3_TIMEOUT. No mechanism |
| R1-8 | Accepted | FORCED for a short header (a server kill mid-send) | a short header is SAM3_CLOSED; usage instance 2 raises on FRAME_GONE, INVALID_REQUEST and INVALID_REPLY, as gate item 3 says; Sam3ClientDetect's comment says it |
| R1-9 | Narrowed | none | the C constants stay as array sizes, named as config's values, with a test that holds them equal; the Python heap has no cap check (the clients bound it) |
| R1-10 | Accepted, carried | none: only our own bug maps it writable | carried to the manager for module 4 (PAR2): FramebufferOpen closes the inherited descriptor after the reopen. This module's text no longer claims more than the reopened descriptor gives |
| R1-11 | Accepted | none in flight; DESIGNED for every test that launches a real server outside the project folder | one env addition, PYTHONPATH=config.PROJECT_DIR; Sam3ServerSpecText gains m_env and the entry; config.PROJECT_DIR carried |
| R1-12 | Accepted | DESIGNED: every stop while idle | W8 in the internal header and gate item 11; a test |

**R1-13 (the author's, from the R1-1 check). A box past the frame's edge.** Cause: SEEN. The same
logged pass holds a dresser box [-12, 704, 1264, 720]. The header's corners are uint16_t, so -12
would store as 65524. Change: the pass clamps the corners to the frame before the store; a
failure-matrix row; test_corners_past_the_frame_are_clamped.

Counts: 12 findings; 10 accepted (one of them carried), 2 narrowed, 0 rejected; one added by the
author. Added for a cause: the merge across the concepts, the concept bound, one read per part,
no upsample for no box, the clamp. Removed: the STATUS message, the echoed id.

## Round 2: reviewer

Read in full: sam3_server.md, sam3_server.h, sam3_server_internal.h, round 1 and its answer,
the brief (sections 3 and 4), gate item 12. Read as contracts: runtime.h, runtime_internal.h,
framebuffer.h, framebuffer_internal.h, recorder.h, recorder.md, runtime.md (the child's
environment). Read as today's code: sam3/model.py, sam3/loader.py, perception2/concept.py,
vision.py, engine.py, verify.py, counting.py, config/constants.py. The logs: all 877
logs/sessions/*/perception/*/pass_*.json and their request.json. The scripts and their output
sit in the reviewer's scratch folder (.../scratchpad/review2/: merge.py, tokens.py,
textlen.py, sock2.py with out_sock2.txt and out_sock2_run2.txt, waitall_timeout.py,
scatter.py, preproc.py). Every run was on the CPU; no GPU was needed.

### Round-1 mechanisms re-checked
| mechanism | cause holds? | evidence | verdict |
|---|---|---|---|
| the merge across the request's concepts | half. The IoU half: SEEN, 39 passes with cabinet, dresser and chest of drawers on one box. The containment half: no; it drops distinct objects, SEEN | merge.py on the 47 passes; R2-1 | narrow: IoU across the concepts, containment within one concept |
| the client's bound of the concepts | yes, DESIGNED: R1-2's 65-byte phrase. The logged concepts top at 42 bytes and 10 tokens | tokens.py over the 99 highlight and count requests | keep; the size in R2-4, the token limit in R2-5 |
| one MSG_WAITALL read per part | the cause holds (DESIGNED, R1-3). The mechanism does not close it: 4 of 80 replies lost beside two busy threads | sock2.py; R2-2 | narrow: one read for the whole reply |
| no upsample for no box | yes, and it is SEEN: 72 of 877 logged passes have no hits | the pass files, raw_dets empty | keep |
| the clamp of the corners | yes, SEEN: 580 of 4296 logged boxes have a negative corner; y2 = 732 on a 720-row frame (session-20260912-183503-rog, 0002-highlight-drawer) | the pass files | keep |
| PYTHONPATH as the one env addition | yes, DESIGNED for the tests. The child needs nothing from the inherited ROS PYTHONPATH | torch, transformers, cv2 and bitsandbytes sit in /usr/local/lib/python3.12/dist-packages; runtime/__init__.py imports nothing; rclpy is imported inside RosCreate (runtime.md) | keep |
| removed: the STATUS message | the removal holds: a bare connect is honest also after a crash | a stale socket file refuses (ECONNREFUSED, 15 us); the new process unlinks only before its bind | keep removed; two "kind" leftovers in R2-9 |
| removed: the echoed id | the removal holds: one connection per request closes W3 | a client that gave up closed its socket; the late send fails | keep removed |

### R2-1. The merge's containment across concepts drops the drawers the user asked for
- **Severity:** HIGH.
- **Cause:** SEEN. session-20260912-183503-rog, 0002-highlight-drawer, request "highlight
  drawer". concept.py fans "drawer" out to drawer and dresser. Pass 2 holds dresser 0.918 at
  [724, 258, 904, 528], then drawers 0.875 at [768, 320, 900, 376] and 0.848 at
  [804, 374, 896, 430]. Each drawer lies inside the dresser box, over 0.7 of its area. Under
  the round-1 rule every drawer goes; the top 3 become the dresser and two dressers of
  score 0.14 to 0.17 along the floor's edge. Six passes of that request and two more in the
  same session show it.
- **Where:** sam3_server_internal.h, Sam3MergeNested ("of any concept of the request ...
  so a cross-concept overlap is one object"); sam3_server.h, the Sam3Box comment;
  sam3_server.md section 2 item 5, section 4 (the merge bullet and OPEN 1's facts, 2.91),
  the failure-matrix row "one object found under each synonym", section 9's
  test_merge_spans_the_concepts_of_one_request.
- **What is wrong:** The premise "one request is one noun's synonyms" is false for the
  synonym table. "drawer" maps to a part and its whole. "vehicle" maps to 7 distinct
  classes, so a motorcycle in front of a bus sits inside the bus's box. R1-2's own trigger
  is a comma list of distinct nouns in one request. Round 1's numbers also count a box
  inside another as the same object, so they measure the rule by itself. With an object
  defined as boxes of IoU over 0.5, merge.py gives:
  | rule | distinct objects in the top 3 (47 passes) | drawer boxes in the top 3 (8 drawer passes) |
  |---|---|---|
  | per concept (today) | 1.43 | 16 |
  | round 1: IoU or containment, across the concepts | 2.91 | 2 |
  | IoU across the concepts, containment within one concept | 2.98 | 16 |
  The synonym duplicates are near-identical boxes, so IoU alone merges them.
- **The smallest fix:** Narrow the rule. A box is dropped when a kept box of higher score of
  any concept overlaps it by IoU over 0.5, or a kept box of the same concept holds over 0.7
  of it. One condition moves. The test takes the 47 passes, with the drawer passes as the
  cases where the drawers must stay. OPEN 1's facts and the test name take 2.98.

### R2-2. One read per part still loses masked replies beside two busy threads
- **Severity:** MEDIUM.
- **Cause:** DESIGNED, R1-3's own trigger: a masked reply while app threads run Python.
  sock2.py: the server is a second process; after a 50 ms stand-in pass it sends the header,
  19 boxes and 3 masks at 1080p with a 1 s sendall limit. The client reads as the design
  says: a blocking socket, SO_RCVTIMEO, one recv_into with MSG_WAITALL per part. 40
  requests per row:
  | busy threads in the client | reads | replies lost | server sendall p50 | p95 | max |
  |---|---|---|---|---|---|
  | 1 | one per part | 0 | 11.0 ms | 12.0 ms | 12.8 ms |
  | 1 | one for the whole reply | 0 | 1.45 ms | 1.82 ms | 2.07 ms |
  | 2, run 1 | one per part | 4 | 72.4 ms | 1001 ms | 1001 ms |
  | 2, run 1 | one for the whole reply | 0 | 1.36 ms | 6.90 ms | 154 ms |
  | 2, run 2 | one per part | 0 | 22.0 ms | 346 ms | 463 ms |
  | 2, run 2 | one for the whole reply | 0 | 1.49 ms | 2.53 ms | 27.6 ms |
- **Where:** sam3_server.h, Sam3ClientDetect ("each part of the reply is one read");
  sam3_server.md section 4 ("one read: 5.9 ms and 6.2 ms"), gate items 8 and 9, the
  failure-matrix row "a masked reply while app threads hold the GIL", section 8's
  sam3_exchange comment, section 9's R1-3 test.
- **What is wrong:** The client takes the GIL back twice inside the reply: after the header
  and after the boxes. Meanwhile the server's send of the masks blocks on the full socket
  buffer. With two busy threads one wait passed the 1 s limit; the client got SAM3_CLOSED.
  Round 1's 5.9 and 6.2 ms are medians; the tail decides the loss.
- **The smallest fix:** One read for the whole reply. The server always sends the boxes
  padded to kSam3MaxBoxes (2048 bytes), so the masks start at byte 2056. The client reads
  header, boxes and masks with one recvmsg_into([header, boxes, masks], 0, MSG_WAITALL); the
  read ends at the server's close (scatter.py: 4149256 of 4149256 bytes for two masks in a
  three-mask buffer). The caller gives the mask buffer before the call, as Sam3MaskBuffer
  already does in C; the Python client needs the frame size up front. Three reads become
  one.

### R2-3. The server's one thread waits for the client's GIL between its connect and its send
- **Severity:** MEDIUM.
- **Cause:** DESIGNED: every request while an app thread runs Python. The client's connect
  completes in the backlog and returns. The client must take the GIL back before its
  sendall. The server has already accepted and blocks in its 528-byte read. sock2.py, the
  server's time from accept to the whole request:
  | busy threads in the client | p50 | p95 | max |
  |---|---|---|---|
  | 1 | 5.05 ms | 5.07 ms | 5.08 ms |
  | 2, run 1 (the two read modes) | 5.04 ms | 157 ms and 436 ms | 790 ms and 1000.9 ms |
  | 2, run 2 | 5.04 ms | 5.06 ms and 45.6 ms | 15.2 ms and 172 ms |
  The 1000.9 ms is the server's 1 s read limit: the request was dropped and the client saw
  SAM3_CLOSED. The GPU idles for every one of these waits.
- **Where:** sam3_server_internal.h, Sam3ServerAcceptPending ("read sizeof(Sam3Request)");
  sam3_server.md section 8, _accept_pending; the constants table,
  SAM3_SERVER_IO_TIMEOUT_NS ("a request arrives in microseconds ... only a stopped client
  reaches it").
- **What is wrong:** The claim "a request arrives in microseconds" holds only for an idle
  client. One busy thread costs 5 ms of GPU time per request; two can drop the request.
  AF_UNIX has no TCP_DEFER_ACCEPT, so the kernel cannot hold the accept until the data comes.
- **The smallest fix:** Accept without reading. An accepted connection joins the one poll
  with the listen socket and the wake pipe, at most 9 of them. The server reads its 528 bytes
  when poll reports it readable; end of file (the probe, a client that gave up) closes it.
  The blocking read and its 1 s limit go; the reply's send keeps the limit. The cost: a
  command whose bytes arrive after the pop waits one pass. The weaker alternative is one
  constant: the read's limit at the job's timeout; it ends the loss and keeps the stall.

### R2-4. The 63-byte cut drops words that SAM3 can read
- **Severity:** LOW.
- **Cause:** DESIGNED, R1-2's phrase. SAM3's tokenizer (CLIPTokenizer, model_max_length 32,
  /root/models/vision/sam3-nf4) makes 15 tokens of the whole phrase. The cut sends "man in the
  yellow jacket with the black backpack and the blue": SAM3 sees a colour with no noun.
- **Where:** sam3_server.h, kSam3ConceptBytes; sam3_server.md, the constants table.
- **What is wrong:** The bound sits at half of SAM3's own limit, and it cuts the very phrase
  it was sized for. The effect on the score is unverified.
- **The smallest fix:** kSam3ConceptBytes = 128. R1-2's phrase passes whole; the request is
  1040 bytes; the static_assert and the "64s" change with it. No new mechanism.

### R2-5. A byte bound does not bound SAM3's tokens
- **Severity:** LOW.
- **Cause:** none traced. tokens.py: within 63 bytes, a spoken digit string is 26 tokens, a
  digit run 62, Hebrew letters 56. processing_sam3.py tokenizes with padding="max_length",
  max_length=32 and no truncation. textlen.py: a CLIP text model built from SAM3's text config
  raises ValueError ("Sequence length must be less than max_position_embeddings") at 33
  tokens. In the server that is Die and a relaunch. But every logged highlight or count
  concept is 10 tokens or fewer. The Hebrew targets in the logs belong to "describe", which
  runs no SAM3 pass (vision.py).
- **Where:** sam3_server.md section 4, "The client bounds the user's words".
- **What is wrong:** The text implies that the bound keeps a user's words off the crash path.
  It bounds the message, not SAM3's 32 tokens.
- **The smallest fix:** One sentence: the byte cut bounds the message; SAM3's own limit is
  32 tokens, and no logged concept comes near it. No mechanism: the generic handling (the
  supervisor's restart) covers it.

### R2-6. The caller's timeout is per system call, not per request
- **Severity:** LOW.
- **Cause:** none. Under designed load a reply ends inside 9.9 s of the 15 s.
- **Where:** sam3_server.h, SAM3_TIMEOUT ("no whole reply within the caller's timeout") and
  Sam3ClientDetect.
- **What is wrong:** SO_SNDTIMEO and SO_RCVTIMEO apply to each call: the connect, the send
  and each read may each wait timeoutNs. The text promises a total.
- **The smallest fix:** The text: "each system call waits up to timeoutNs". With R2-2 the
  reply is one call, so the read's limit covers the whole wait after the send.

### R2-7. A Python timeout on the client socket would break every masked reply
- **Severity:** LOW.
- **Cause:** none: a slip in the build, not a flight event.
- **Where:** sam3_server.md section 8, the client sketch; sam3_server.h, Sam3ClientDetect.
- **What is wrong:** CPython's settimeout puts the socket in non-blocking mode internally
  (the socket module's "Notes on socket timeouts"). MSG_WAITALL then returns what is
  queued: waitall_timeout.py returned 219264 of 6220800 bytes. The design maps a short count
  to SAM3_TIMEOUT. The server's own conn.settimeout in the sketch makes the slip easy to copy.
- **The smallest fix:** One line in the Python mapping: the client never calls settimeout;
  both timeouts are set by setsockopt. The R1-3 test then catches a slip.

### R2-8. OPEN 1 has no mark in the header
- **Severity:** LOW.
- **Cause:** none; a rule of the deliverable (brief section 8, MOD2).
- **Where:** sam3_server.h, kSam3MaxMasks = 3.
- **What is wrong:** No header line carries "OPEN 1". The other modules mark theirs (for
  example llama_server.h, "OPEN 1 (P1)").
- **The smallest fix:** A comment above the enum: "OPEN 1: kSam3MaxMasks, the masks a reply
  carries".

### R2-9. The document and the headers disagree on five names and rules
- **Severity:** LOW.
- **Cause:** none; leftovers of round 1.
- **Where and what:**
  - sam3_server.md section 7, Data in: "A request: its kind". The kind is gone (m_pad0).
  - sam3_server.h, SAM3_STATUS_INVALID_REQUEST: "a kind or a priority out of range".
  - sam3_server.md, the RUN14 row and gate item 11: "W1 to W7". The list ends at W8.
  - sam3_server.md section 8, _accept_pending: "len(s.pending) < SAM3_QUEUE_CAPACITY".
    R1-9's answer and the internal header say the Python heap has no cap check.
  - The same sketch: send_status(...) then continue, with no close. The internal header
    says "reply INVALID_REQUEST, close".
- **The smallest fix:** Correct the five lines.

### R2-10. "Changes to approved contracts: none" contradicts the carried items
- **Severity:** LOW.
- **Cause:** none; a statement of the document.
- **Where:** sam3_server.md section 4, "Changes to approved contracts: none. Carried to the
  manager".
- **What is wrong:** FramebufferOpen closing the inherited descriptor changes module 4's
  contract. Gate item 12 makes such a change an open point for the owner, read at the end.
- **The smallest fix:** Name it as a change to module 4 and list it for the conclusions.

### R2-11. The out-of-memory row borrows its cause from another model
- **Severity:** LOW.
- **Cause:** none for this design. The cited bench is SAM3.1 video tracking. This design's
  pass peaks at 1192 MiB for the process, with about 2.6 GiB free beside llama-server (round 1).
- **Where:** sam3_server.md, the failure matrix, the first row.
- **What is wrong:** The handling rests on the owner's ruling of 2026-09-23. Gate item 12
  calls a ruling a requirement, not evidence. The row reads as SEEN for this server.
- **The smallest fix:** The cause cell: "the ruling (2026-09-23); not seen with this
  post-process". The handling is the generic one already: Die, then the relaunch.

### Checked and sound
- The bare-connect probe after a crash. The supervisor relaunches only after the old
  process exited (pidfd); its listener closed with it. A connect to the stale file is
  refused until the new bind. During the old process's Die flush its listener still
  completes connects; those clients see SAM3_CLOSED at _exit, the generic handling.
- MSG_WAITALL with SO_RCVTIMEO. With no Python timeout CPython calls recv once with the GIL
  released. A timeout returns the partial count (the author's run: 100 bytes after 305 ms).
  recv(2) also returns short "if a signal is caught". The app's handled signal is SIGINT,
  at stop only, so it has no cause in a flight.
- The scatter read ends at end of file with the full count (scatter.py).
- The colour copy. At 1080p on the CPU, the PIL copy and the processor took 49.5 ms p50;
  cv2.cvtColor and the processor took 26.9 ms. The pixel values match exactly (preproc.py).
  The document's 24 ms saving holds.
- The verify step sends its head and its related noun as two requests (verify.py, lines
  222 and 233). R2-1's rule never sees them together.
- W2's kept window is narrower than written: the pass copies the slot first (0.2 ms), so a
  torn read needs the job's release inside that copy.
- The span's wait starts at the server's read. A request queued in the backlog during a pass
  is not counted. The app's SPAN_SAM3_REQUEST holds the total; the join by req gives both.
- The supervisor copies the spec's strings at Create, but not the probe's context. Holding
  Sam3ServerSpecText until SupervisorDestroy is required; the document says so.
- Today's box cap: loader.py passes topk=config.HL_TOPK (128) and the engine masks up to
  HL_MAX (128). OPEN 1's "today" holds. The recorder's mask pool is 8 times 3, 24.
- The layouts: gcc -fsyntax-only -Wall -Wextra -std=c11 -pedantic on both headers is
  clean; "<xBBBIIf" + "64s" * 8 is 528 bytes; "<BBBxHH" is 8.
- The numbers: 8 x 818 x 1.51 = 9.9 s; 841 x 1.51 = 1.27 s; 2^32 requests at 8 a second
  last 17.0 years; 3 masks at 1080p are 6,220,800 bytes; the argv has 11 entries.
- MOD1's order holds. OPEN 1 has the problem, now, on "no" and recommended, plus a facts
  line.
- The removals: no STATUS kind, no 12-byte header and no echoed id remain, apart from the
  two "kind" lines in R2-9.

Counts: HIGH 1, MEDIUM 2, LOW 8.

## Round 2: answer
First, the round-1 mechanisms. The reviewer's table holds. Two of them went back to their
round-1 cause before any new code (gate item 12):
- The merge (R1-1 against R2-1). R1-1's cause stands for the IoU half: SEEN, 39 passes with
  three synonyms on one box. Its containment half had no cause across concepts and drops
  distinct objects (SEEN, the drawer passes). Narrowed, not replaced.
- One read per part (R1-3 against R2-2). R1-3's cause stands: DESIGNED, every masked reply
  beside a busy app thread. The mechanism was too weak. Narrowed to one read for the whole
  reply.

The author checked one claim before the answer: the SAM3 processor ignores truncation. A
42-token phrase came out as 42 tokens with and without truncation=True (processing_sam3.py
line 152 hard-codes padding="max_length", max_length=32). So the server calls the tokenizer
itself.

| finding | answer | cause and evidence | change made |
|---|---|---|---|
| R2-1 | Accepted, narrows R1-1 | SEEN: session-20260912-183503-rog, "highlight drawer" | Sam3MergeNested: IoU over 0.5 across the request's concepts; containment over 0.7 within one concept only; the Sam3Box comment; section 4 with the reviewer's table (2.98, 16 of 16 drawers); OPEN 1's facts; the failure matrix gets the drawer row; the test takes the drawer passes |
| R2-2 | Accepted, narrows R1-3 | DESIGNED: R1-3's trigger; 4 of 40 lost beside two busy threads | the reply has one fixed layout (128 box places, the masks from byte 2056); the client reads it with one recvmsg_into with MSG_WAITALL into the header, the boxes and the caller's mask buffer; Sam3ClientDetect and the Python mapping say so; the caller passes the mask array (instance 2) |
| R2-3 | Accepted | DESIGNED: every request beside a busy app thread; 5 ms of idle GPU, one request lost at the 1 s read limit | the server accepts into an unread set (kSam3UnreadCapacity 9) that waits in the one poll; Sam3ServerReadRequest reads only when the poll says the bytes are there, without waiting; the read limit is gone; SAM3_SERVER_IO_TIMEOUT_NS is SAM3_SERVER_SEND_TIMEOUT_NS, the reply's send only; W9 |
| R2-4 | Accepted | DESIGNED: R1-2's phrase cut to "... and the blue" | kSam3ConceptBytes = 128; the request is 1040 bytes; the static_assert and "128s" |
| R2-5 | Accepted, with one argument more than asked | none in the logs (10 tokens at most); but the chain after it is DESIGNED: a refresh repeats its concepts every second, so a phrase over 32 tokens would kill the server three times in 60 s, and BUDGET_SPENT_DIE ends the flight | the text says the byte cut bounds the message; the server calls the tokenizer with truncation at 32 tokens. No new code path: one argument on the call the pass makes anyway. A test |
| R2-6 | Accepted | none | SAM3_TIMEOUT and Sam3ClientDetect say "each system call waits up to timeoutNs"; the reply is one call |
| R2-7 | Accepted | none | the Python mapping and the header: the client never calls settimeout; a test |
| R2-8 | Accepted | none | "OPEN 1: kSam3MaxMasks" in the comment above the enum. The layout tool had dropped the inline mark |
| R2-9 | Accepted | none | the five lines corrected: no "kind"; W1 to W9; no cap check in the sketch; the close after the status |
| R2-10 | Accepted | none | section 4 names FramebufferOpen's close as a change to an approved contract, for the owner at the end |
| R2-11 | Accepted | none for this design | the cause cell: the ruling (2026-09-23); not seen with this post-process (1192 MiB at worst) |

The reviewer's stronger causes are taken: no upsample for no box is SEEN (72 of 877 passes);
the clamp is SEEN (580 of 4296 boxes).

Counts: 11 findings; 9 accepted, 2 accepted as narrowings of round-1 mechanisms, 0 rejected.
Added for a cause: the unread set and the read after the poll (R2-3), the fixed reply
layout and its one read (R2-2), the tokenizer's truncation (R2-5). Narrowed: the merge
(containment within one concept). The document was rewritten whole with rounds 1 and 2 in
it; both headers compile and the layout tool ran.

## Round 3: reviewer

Read in full: sam3_server.md, sam3_server.h, sam3_server_internal.h, rounds 1 and 2 with their
answers, the brief (sections 3 to 5), gate item 12. Read as contracts: recorder.h,
record_span.h, frame_types.h, recorder.md (instance 2), runtime.h, runtime.md (the child's
state), framebuffer.h, framebuffer_internal.h. Read as today's code: sam3/model.py,
perception2/vision.py, config/. The logs: all 877 pass files. The scripts sit in
.../scratchpad/review3/: loop.py, loop_one.py, sock3.py, tok.py, fds.py. One GPU run (fds.py)
was under tools/lock.sh (sam3_review), released after; no process was left running.

### Mechanisms re-checked
| mechanism | cause holds? | evidence | verdict |
|---|---|---|---|
| the top-3 mask post-process | yes, SEEN, now also in the session logs | 17 of 877 logged passes have over 20 hits; the most is 95 (session-20260912-183503-rog, 0018-highlight-fingertips); 82 measured on market-0.jpg | keep |
| the merge: IoU across the concepts, containment within one | yes, SEEN | review2/merge.py rerun: 1.43, 2.91, 2.98 distinct objects in the top 3; 16, 2, 16 drawer boxes. Its third rule is the design's rule | keep |
| the clamp of the corners | yes, SEEN | 580 of 4296 logged boxes (round 2) | keep |
| no upsample for no box | yes, SEEN | 72 of 877 logged passes have no hits (round 2) | keep |
| the client's byte bound and 8 concepts | yes, DESIGNED; the cited trace is stale (R3-6) | an utterance's length is the user's; "128s" truncates without a NUL, then INVALID_REQUEST, then the bug path. tok.py: a plausible attribute phrase reaches 112 bytes | keep |
| the tokenizer's truncation at 32 | yes, DESIGNED at the edge | tok.py: 111 and 112 bytes of plain words make 26 and 25 tokens; digits make 44 tokens in 100 bytes. Truncation changes nothing below 32 (the ids and mask of "dresser" are identical) and keeps EOS (49407) last. The 28 logged labels top at 7 tokens: no logged concept changes. It is one argument on a call the pass makes anyway | keep |
| the fixed reply layout and one recvmsg_into | yes, DESIGNED (R2-2) | sock3.py: 1 mask into a 3-mask buffer returns 2075656 bytes at the server's close (2056 + 2073600); masks off returns 2056 at once, without waiting for the close; the numpy array passes directly. SO_RCVTIMEO is a total for the call: a 100-byte trickle every 200 ms returned 1600 bytes at 3002 ms for a 3 s limit | keep |
| the unread set and the read after the poll | the cause holds, DESIGNED (R2-3); the loop order defeats the queue (R3-1) | loop.py; MSG_DONTWAIT on the accepted socket returns at once; select is safe: fds.py, the highest descriptor is 55 after the load, a 3-concept pass at 1080p and 11 more sockets, against FD_SETSIZE 1024 | narrow: R3-1 |
| the socket unlink before the bind | yes, DESIGNED | a listener ended by os._exit leaves its file; a new bind fails with EADDRINUSE (98) | keep |
| PYTHONPATH, the one env addition | yes, DESIGNED for every test that launches a real server outside the project folder | RUN16 merges the additions over the current environment; the child needs nothing from the app's PYTHONPATH (round 2) | keep |

### R3-1. A request that arrives during a pass is read only after the next pass, so a command waits behind a refresh
- **Severity:** MEDIUM.
- **Cause:** DESIGNED. The trigger is speech while two jobs refresh. Up to 8 vision tasks
  live at once (VISION_MAX_ACTIVE_TASKS), and each live highlight keeps one refresh
  outstanding (RVW3). The trace through the loop (the internal header, steps 1 to 4):
  - During pass k, the command's connect and its bytes wait in the listen backlog.
  - After pass k, the poll of step 1 reports the listen socket.
  - Step 3 accepts the command into the unread set. It is not read in this round.
  - Step 4 pops the best request already read: the other job's refresh. Pass k+1 runs it.
  - The command is read in the next round and runs in pass k+2.
  loop.py runs the design's loop with a 0.4 s stand-in pass, two refresh clients and one
  command sent at 1.70 s, during a pass:
  | loop | the pass after the command arrived | the command's pass starts | the command answered after |
  |---|---|---|---|
  | the design | refresh 202, at 1.80 s | 2.20 s | 0.90 s |
  | the fix below (loop_one.py) | the command, at 1.80 s | 1.80 s | 0.50 s |
- **Where:** sam3_server_internal.h, Sam3ServerLoop, steps 3 and 4; sam3_server.md section 4,
  "One thread in the server" ("The priority needs the waiting requests read before the next
  pass starts"); section 8, _loop.
- **What is wrong:** R2-3 accepted one cost: a command whose bytes arrive after the pop waits
  one pass. Here the bytes arrived before the pop. Under load the server is in a pass most of
  the time, so nearly every request arrives during one. While two requests are outstanding,
  the priority then orders almost nothing. The cost is one pass: 0.4 to 0.84 s, and 1.27 s
  with Gemma busy.
- **The smallest fix:** One rule in the loop. Step 3 accepts one connection. A round that
  accepted a connection goes back to step 1 with timeout 0. Step 4 runs only in a round that
  accepted none. Add W10, "the accept, then the pop", closed by that rule. Its test: a command
  sent during a pass, beside a refresh already read, runs in the next pass.

### R3-2. A server exit resets the waiting connections, and the client's mapping has no kind for it
- **Severity:** LOW. Gate item 12 allows no more: the server's exit mid-flight has no SEEN
  or DESIGNED trigger. Its effect is still a Die in the app, mid-flight.
- **Cause:** the ruling of 2026-09-23 for the out-of-memory; FORCED for a kill. sock3.py ends
  a server process with os._exit(1):
  | the client's connection when the server exits | what the client gets |
  |---|---|
  | its connect still in the listen backlog | ConnectionResetError (ECONNRESET) from recvmsg_into, after 252 ms |
  | accepted, its request unread | ECONNRESET, after 302 ms |
  | its request read (queued) | 0 bytes, after 302 ms |
  | its connect completed, its send after the exit | BrokenPipeError (EPIPE) |
  loop.py showed the same ECONNRESET when its listener closed with clients waiting.
- **Where:** sam3_server.md section 8, the sam3_exchange comment (it names ECONNREFUSED,
  ENOENT, EAGAIN, a timeout, a short header and 0 bytes); sam3_server.h, SAM3_CLOSED; the
  failure matrix, first row ("every waiting client SAM3_CLOSED"); sam3_server_internal.h,
  Sam3ServerMain ("their clients see SAM3_CLOSED").
- **What is wrong:** ECONNRESET and EPIPE have no kind in the mapping. A build that maps only
  the named errors lets the exception leave the client. On a pool thread the crash hook then
  runs Die: the hand-over mid-flight. The ruling handles this exit by a relaunch and FAILED
  jobs. The server's own stop also closes unread connections that hold data. The kernel
  reports those as ECONNRESET, not as end of file.
- **The smallest fix:** The mapping names ECONNRESET and EPIPE as SAM3_CLOSED. The test
  test_an_exception_in_a_pass_exits_1_and_every_client_sees_closed puts one client in the
  backlog and one in the unread set. No mechanism.

### R3-3. The length of a status reply is not stated
- **Severity:** LOW.
- **Cause:** none. FRAME_GONE and INVALID_REQUEST come only from our bugs.
- **Where:** sam3_server.h, the Sam3ReplyHeader comment ("one fixed layout"); sam3_server.md
  section 3, reply_status; section 8, send_status and the sam3_exchange comment.
- **What is wrong:** The design does not say whether a status reply is 8 bytes or 2056. It
  also does not give the count the client checks for a whole reply. sock3.py: an 8-byte
  status reply, then the close, returns a count of 8. A client that expects 2056 reads that
  as CLOSED. The job then returns FAILED, and our bug stays hidden.
- **The smallest fix:** One sentence in the header. A status other than OK is the 8-byte
  header alone. An OK reply is 2056 + m_maskCount x width x height bytes. A count short of
  its status's length is SAM3_CLOSED.

### R3-4. "Accept until it is not" needs a non-blocking listen socket, and the design gives none
- **Severity:** LOW.
- **Cause:** DESIGNED, if built as written: every request. On a blocking listen socket the
  second accept blocks the one thread until the next connect. The wake pipe and the queue
  wait with it. The first test would show it.
- **Where:** sam3_server_internal.h, Sam3ServerLoop, step 3 ("accept until it is not, or the
  unread set is full").
- **What is wrong:** The step needs a non-blocking listen socket. Neither header nor the
  Python mapping says so.
- **The smallest fix:** R3-1's fix: one accept per round. loop_one.py runs it on a blocking
  listen socket. No other change.

### R3-5. The usage raises an exception for our bug; the house rule says die()
- **Severity:** LOW.
- **Cause:** none. A rule of the project (docs/guidelines.md, Errors: "Our code never throws:
  die() on a fatal error"). The approved frame buffer dies on its bugs
  (framebuffer.md: die("framebuffer: a second hold on one thread")).
- **Where:** sam3_server.md section 3, instance 2 (raise BugInSam3Use); gate item 3 ("the
  vision job raises"); the failure matrix, last row; sam3_server.h, Sam3ClientDetect ("the
  caller raises (RVW4)").
- **What is wrong:** Our code throws on purpose to reach the crash hook.
- **The smallest fix:** die(f"sam3: {reply.result.name} on a held slot"); the three texts
  say "the caller dies (RVW4)". Die runs the hand-over first either way.

### R3-6. The cause cells of the byte and token bounds cite a sentence that reaches neither bound
- **Severity:** LOW.
- **Cause:** none; a text left from round 1.
- **Where:** the failure matrix, the row "a spoken phrase over 127 bytes, over 8 concepts, or
  over 32 tokens" ("DESIGNED (R1-2's sentence)"); gate item 12 ("DESIGNED: a 65-byte spoken
  phrase").
- **What is wrong:** R1-2's sentence is 65 bytes and 15 tokens. Since R2-4 it passes whole.
  The cells name a trace that no longer runs. Gate item 12 asks for a trace that does.
- **The smallest fix:** Rewrite both cells with the traces that hold. The bytes: an
  utterance's length is the user's; "128s" truncates without a NUL. The concepts: R1-2's list
  of 9 nouns. The tokens: tok.py, 112 bytes of plain words make 25 tokens, and digits make 44
  tokens in 100 bytes. The mechanisms stay.

### R3-7. Sam3MergeNested returns a uint8_t count for a uint32_t input
- **Severity:** LOW.
- **Cause:** none. The logs top at 95 hits in one pass, under 256.
- **Where:** sam3_server_internal.h, Sam3MergeNested(Sam3Box* boxes, uint32_t count),
  returning Sam3Count.
- **What is wrong:** The merge runs before the cut to 128, on the hits of up to 8 concepts.
  Its kept count can pass 255, and the return type wraps without a sign.
- **The smallest fix:** Return uint32_t.

### R3-8. The mask threshold is called a config value, but config has none
- **Severity:** LOW.
- **Cause:** none.
- **Where:** sam3_server.md section 7, Data in ("Config: ... the mask threshold 0.5").
- **What is wrong:** Today 0.5 is a default argument in sam3/model.py (mask_threshold=0.5).
  config/ has no such name. The rule: config/ is the one source of every value.
- **The smallest fix:** Name it (for example SAM3_MASK_THRESHOLD). Carry it to the manager
  beside PROJECT_DIR.

### R3-9. recorder.md still shows the old client call, and the carried list omits it
- **Severity:** LOW.
- **Cause:** none.
- **Where:** 01-recorder/recorder.md, instance 2: sam3.detect(req, slot.seq, concepts,
  priority) and reply.ok.
- **What is wrong:** This module's client allocates req itself. Its reply has a result, not
  ok. The recorder is volatile, per the owner, so its example follows this module.
- **The smallest fix:** Carry a one-line correction of recorder.md instance 2 to the manager.

### Checked and sound
- Both headers compile clean with gcc -fsyntax-only -Wall -Wextra -std=c11 -pedantic. The
  layout tool leaves a copy of each unchanged. No header line passes 90 characters.
- The sizes. Sam3Request is 1040 bytes, Sam3Box 16, Sam3ReplyHeader 8. The masks start at
  8 + 128 x 16 = 2056. "<xBBBIIf" + "128s" x 8 is 1040; "<BBBxHH" is 8.
- The names agree across the three files. kSam3UnreadCapacity is the queue's 8 plus 1 in the
  internal header, section 7 and the picture. SAM3_SERVER_SEND_TIMEOUT_NS is 1 s in the
  header, section 7 and RunOne. W1 to W9 match in the internal header, gate item 11, the
  RUN14 row and the tests. Sam3ServerConnectProbe matches the names table.
- Nothing of the removed design is left: no STATUS kind, no echoed id, no 528, no 64-byte
  concept, no IO timeout. The words appear only in the notes on what round 1 removed.
- MOD1's order holds. OPEN 1 carries its OPEN mark in the header comment. It has the problem,
  now, on "no" and recommended, plus the facts line round 2 accepted.
- The change to an approved contract (FramebufferOpen closes the inherited descriptor) is
  listed for the owner.
- Every failure-matrix row names a cause. The FORCED and no-cause rows get the generic
  handling only.
- The tests cover W1 to W9 and every accepted finding of rounds 1 and 2.
- No ruling the document cites is contradicted, apart from the house rule in R3-5. Checked:
  S4, L1, RVW3, RUN9, RUN15, RUN16, LLM1 D3 and D4, the 2026-09-23 ruling.
- The extra pass after a SIGINT. A SIGINT that lands in the zero-timeout poll lets one more
  pass run before the flag is read. That is at most 1.27 s inside the 10 s grace. No cause for
  a change.
- W6's margin. The load and the warm pass take 8.8 s (measured), under the 10 s grace. A cold
  disk past it gets the kill, logged: the generic handling.
- The span payloads stay under the recorder's 104 bytes.
- A build note, not a finding. recvmsg_into takes the numpy mask array directly. A memoryview
  cast of a zero-length array raises TypeError, so the build must not cast.

Counts: HIGH 0, MEDIUM 1, LOW 8.

Landing verdict: not ready. R3-1 (MEDIUM) makes the queue's priority order almost nothing
under load. Its fix is one rule in the loop. R3-2 to R3-9 are text and type corrections, with
no new mechanism. With those, the design is ready for the owner.

## Round 3: answer
First, the mechanisms. The reviewer kept nine and narrowed one. R3-1 is against R2-3's
mechanism, so the author went back to R2-3's cause first. It stands: DESIGNED, a client
waits for its GIL between its connect and its send. The mechanism kept its purpose; its
loop order changed.

| finding | answer | cause and evidence | change made |
|---|---|---|---|
| R3-1 | Accepted, narrows R2-3 | DESIGNED: speech while two jobs refresh; 0.90 s against 0.50 s in the reviewer's run | step 3 accepts one connection; a round that accepted goes back to the poll with the timeout 0; step 4 runs only in a round that accepted none; W10 with its kept window; section 4; the Python sketch; a test |
| R3-2 | Accepted | the ruling (2026-09-23) for the out-of-memory; FORCED for a kill; the effect would be Die in the app | ECONNRESET and EPIPE map to SAM3_CLOSED in the header and the sketch; a failure-matrix row; the exit test puts clients in the backlog, unread and queued |
| R3-3 | Accepted | none | the reply header's comment: an OK reply is 2056 + masks bytes; any other status is the 8-byte header alone; a short count is SAM3_CLOSED; a test |
| R3-4 | Accepted, closed by R3-1 | DESIGNED if built as written | one accept per round after the poll said readable: the blocking listen socket never waits; the loop's comment says so |
| R3-5 | Accepted | none: the house rule ("Our code never throws: die() on a fatal error") | instance 2 calls die() on the three bug results; gate item 3, the failure matrix and Sam3ClientDetect say "the caller dies" |
| R3-6 | Accepted | none: a stale trace | the failure-matrix cell and gate item 12 name the traces that hold: an utterance's length, 9 nouns in one list, 44 tokens in 100 bytes of digits |
| R3-7 | Accepted | none | Sam3MergeNested returns uint32_t; the test covers the 95-hit pass |
| R3-8 | Accepted, carried | none | SAM3_MASK_THRESHOLD, 0.5, carried to config beside PROJECT_DIR |
| R3-9 | Accepted, carried | none | recorder.md's instance 2 carried to the manager with the new call |

Counts: 9 findings; 9 accepted (one narrows R2-3's mechanism, two carried), 0 narrowed, 0
rejected.

## Conclusions
**Agreed.** The server is its own process with one thread: a poll on the wake pipe, the
listen socket and the unread connections; a priority queue of at most 8; one pass at a
time. The frame goes by its sequence in the shared block; the job holds the slot (RVW3).
The probe is a bare connect after the warm pass. The reply has one fixed layout and is one
read. The merge runs in the server (TR17): IoU across the concepts, containment within one.
Masks only for the first boxes; no upsample for no box; corners clamped. The client bounds
the bytes; the server's tokenizer bounds the tokens. A GPU out-of-memory is Die in the
server and a relaunch; every client sees SAM3_CLOSED. Every FORCED or no-cause row has the
generic handling only.

**Open, for the owner (read once, at the end).**
1. OPEN 1, the mask limit: 3 masks a reply (the header: kSam3MaxMasks). The recommendation:
   3. The full context is in sam3_server.md section 4.
2. A change to an approved contract (module 4): FramebufferOpen closes the inherited
   read-write descriptor after its read-only reopen (R1-10). Until then the server's
   writable map through the inherited descriptor succeeds; only our own bug would make one.

**Changed against the brief's facts (for the manager).**
- No request id is echoed in the reply (R1-6): one connection per request binds a reply to
  its request. The client keeps its own number for the span's join.
- No "not ready" status and no STATUS line (R1-5): the socket exists only after the warm
  pass, so a completed connect is the probe and a refused one is SAM3_REFUSED.
- Up to 8 concepts of 128 bytes, not 3 (the synonym table makes 7; R2-4).
- The masks are per request, 0 to 3 (the per-job switch, VIS2).
- The PRF7 rule of the brief's section 5 is void (the brief's UPDATE): the helper takes no
  recorder argument.

**Every item the review added, with its cause.**
| item | cause |
|---|---|
| the merge across the concepts, by IoU only (R1-1, narrowed by R2-1) | SEEN: 47 logged passes; the drawer passes |
| the client's bound of the bytes and the concepts (R1-2, R2-4) | DESIGNED: an utterance's length is the user's; 9 nouns in one list |
| the tokenizer's truncation at 32 (R2-5) | DESIGNED: a refresh repeats a phrase over 32 tokens until the budget is spent |
| one read for the whole reply, with the fixed layout (R1-3, narrowed by R2-2) | DESIGNED: every masked reply beside a busy app thread, measured |
| no upsample for no box (R1-4) | SEEN: 72 of 877 logged passes |
| the clamp of the corners (R1-13, the author) | SEEN: 580 of 4296 logged boxes |
| the unread set and the read after the poll (R2-3), one accept per round (R3-1) | DESIGNED: a client waits for its GIL; a command arrives during a pass |
| PYTHONPATH as the one env addition (R1-11) | DESIGNED: every test that launches a real server outside the project folder |
| W8, W9, W10 (R1-12, R2-3, R3-1) | the windows of the mechanisms above |
| ECONNRESET and EPIPE as SAM3_CLOSED (R3-2) | the ruling for the out-of-memory exit; a mapping, no mechanism |
| removed: the STATUS message and READY (R1-5); the echoed id (R1-6) | no cause: windows already closed |
No thread, callback, counter with a policy or restart path was added. The server's one
thread is the process's main thread. The SIGINT handler is the brief's. The request
number is a counter without a policy.

**Carried to the manager (PAR2).** The frame buffer's comment on the request id (R1-6).
config: PROJECT_DIR and SAM3_MASK_THRESHOLD (R1-11, R3-8). The vision module's
VISION_SAM3_TIMEOUT_NS, 15 s. recorder.md's instance 2 (R3-9). The helper's file name
(record_sam3.h against DOC1). The FrameSize clash of recorder.h and framebuffer.h until the
fold. The architecture document's two stale lines (section 2, the slot by its count;
section 8, 1.9 s from before S1).

**Counts.** Round 1: 12 findings, 10 accepted, 2 narrowed, 0 rejected, and one more from
the author. Round 2: 11 findings, 11 accepted (two narrow round-1 mechanisms), 0 rejected.
Round 3: 9 findings, 9 accepted (one narrows a round-2 mechanism), 0 rejected. In all: 32
findings, 30 accepted, 2 narrowed, 0 rejected; 1 by the author. The round-3 reviewer's
landing verdict was "ready once R3-1 to R3-9 are corrected"; they are.
