# telemetry (rev5), round 1: the adversarial review of telemetry.md, telemetry.h and telemetry.html (2026-10-12)

Scope: docs/api-harden2/rev5/modules/02-telemetry/telemetry.md, telemetry.h, telemetry.html.
Measured numbers: Python 3.12.3, OpenCV 4.11.0, numpy 1.26.4, this machine (32 threads).
The frames are real 1280x720 session frames from bench/perception/dataset/images/sess_*.jpg.
The bench scripts are m1.py and m2.py in the session scratchpad. The file-write timings ran on
the scratchpad's overlayfs, not on the repo's NVMe partition; treat them as indicative.

## Sources
1. https://man7.org/linux/man-pages/man2/fsync.2.html : "Calling fsync() does not necessarily ensure that the entry in the directory containing the file has also reached disk. For that an explicit fsync() on a file descriptor for the directory is also needed."
2. https://lwn.net/Articles/322823/ : "Applications which want to be sure that their files have been committed to the media can use the fsync() or fdatasync() system calls." The article covers rename-over-write and zero-length files on ext4.
3. https://docs.px4.io/main/en/dev_log/logging.html : SD cards show "a several 100 ms delay during a write command. It causes a dropout if the write buffer fills up during this time." The flight logger drops and counts; it never stalls the flight code.
4. https://github.com/ros2/rosbag2/blob/rolling/README.md : "The cache uses double buffering. In pessimistic cases, memory usage can reach up to 2 x --max-cache-size." rosbag2 publishes lost-message statistics instead of blocking the publisher.
5. https://mcap.dev/spec : "MCAP files can have Schema, Channel, and Message records written directly to the data section, or they can be written into Chunk records." "The optional summary section contains records for fast lookup." One append-only file per recording.
6. https://docs.python.org/3/library/dataclasses.html : "It is not possible to create truly immutable Python objects." frozen=True only adds __setattr__ and __delattr__ that raise.
7. https://docs.python.org/3/library/queue.html : put with a positive timeout "blocks at most timeout seconds and raises the Full exception". Queue.shutdown is "Added in version 3.13."
8. https://numpy.org/doc/stable/reference/generated/numpy.copyto.html : "Copies values from one array to another, broadcasting as necessary."
9. https://arxiv.org/abs/1604.04004 (Dodge and Karam, 2016): five distortions tested on DNN classifiers, among them "JPEG, and JPEG2000 compression". Detector output depends on the encoded input.

## Findings

**R1-1. The main thread can block 5 s in TelemetryRecordTurn; that freezes the emergency path.** (critical)
- Claim: open point 2 makes every caller wait up to 5 s on a full queue, then die. The main thread is a caller (RecordTurn, RecordVisionJob).
- Claim: while the main thread waits, it drains no message. A STOP transcript sits in the message queue. The emergency thread is woken only by the main thread (design section 3).
- Why it matters: the emergency budget is command to action under 1 s (section 8). The frame budget is 33 ms. A 5 s wait is 150 lost frames and a 5 s late stop. telemetry.md section 6 itself says "The main thread must never block on the disk".
- Why it matters: the queue is shared. Eight job threads fill it with passes; the main thread then pays for their backlog.
- Evidence: source 7: put(timeout) blocks the calling thread for the whole timeout. Sources 3 and 4: PX4 and rosbag2 never block the producer; they drop and count, because a storage pause of several 100 ms is normal on real media.
- Evidence: the ruling RVW4 says a disk error crashes. It does not say the main thread waits for the disk.
- Change: the main thread never waits. Its records (turns, job ends, events) go into an unbounded FIFO. They are small: about 4 KB a turn at one turn per 2 s, so a 1-hour stall holds 7 MB.
- Change: stall detection moves to the writer. The writer stores the start time of its current write with an atomic store. The main thread reads it each frame, like a status row. A write older than 5 s means a broken disk: die(), with the hand-over first (RVW4).
- Change: only the job threads (workers) may wait, on the frame pool (see R1-5).

**R1-2. Open point 3 says "the files stay as today". They do not; the replayer breaks, and the header has no file contract.** (critical)
- Claim: the replayer (tools/session-replayer/replayer.html) reads five things the design changes.
- The turn's `perception_dir` key: the replayer finds the passes through it (line 107). TurnData has no such field; it has m_visionJob.
- `request.json`: the replayer reads it by name (line 119). The design renames it job.json. Section 9 says "log/show.py reads both names"; show.py reads neither; the replayer is not mentioned.
- The box format: the replayer draws `const [x1,y1,x2,y2]=d.box` from `raw_dets` (lines 145, 146). telemetry.h says Box is "x, y, w, h". Every box would be drawn wrong.
- The pass keys `t`, `forward_ms`, `raw_dets`: the new record has m_ms, m_boxes, m_capturedAt.
- The trace keys: show.py reads `ts`, `kind`, `source`, `heard_he`, `mission`, `action`. TurnData has m_heard, m_input, m_kind (an enum), m_missionJson; no ts, no action. Section 9 claims "trace.jsonl keeps its keys".
- Why it matters: the module's job is replay. The approved perf review fixed the same fault: "The file has a contract in code" (conclusions.md). Telemetry has no such contract.
- Evidence: the sample session tools/session-replayer/sample-session (request.json, pass_00000.json with raw_dets and box [10,20,50,80]).
- Change: the header gets one line struct per file (TraceLine, PassLine, JobLine, MetaLine), each field named with its JSON key, as perf.h does.
- Change: either keep today's keys and box order, or list replayer.html as changed in section 9's change-impact table. A key table beats prose.
- Change on the folder key: a job id is right. A job outlives its turn (a highlight refreshes after the turn ended), and F2 clears jobs, not turns. Name the folder `<job:04d>-<kind>-<slug>`; a human browsing the folder then sees what it is.

**R1-3. The deep copy is not implementable as written: in C the logger cannot copy a type it only declares; in Python a frozen dataclass freezes nothing inside it.** (high)
- Claim (C): `typedef struct Box Box; typedef struct Mask Mask;` are incomplete types. The logger cannot take sizeof(Box) or know a Mask's byte length. It cannot copy `m_boxes` or `m_masks`.
- Claim (order): the SAM3 server is reviewed after telemetry (README, step 2). Telemetry depends on its types, so the bottom-up order is inverted. The same holds for DecisionKind, VisionJobState and SpeechInput: telemetry.h becomes their home by accident.
- Claim (Python): section 8 says "the logger copies the frame and keeps the dataclass (its fields are immutable)". That is false for numpy fields.
- Claim (Python): the kept dataclass still holds `bgr=slot.pixels`, a view into the frame buffer's shared memory. After `frames.release(slot)` that view shows another frame. Any writer code that touches pass.bgr writes the wrong picture, silently.
- Why it matters: section 6, "the caller hands over const data and keeps nothing". The test `test_caller_may_release_its_frame_right_after_the_call` checks the frame only, not the boxes and masks.
- Evidence: measured: a frozen dataclass holding a numpy array; `a[0,0]=7` after construction changes `v.boxes[0,0]` to 7. The mask's pixel changed the same way. Source 6.
- Change: telemetry defines its own complete record types: `TelemetryBox { float x1, y1, x2, y2, score; char label[32]; }` (the replayer's corner order) and `TelemetryMask { uint32_t width, height; const uint8_t* png; size_t pngBytes; }`. The job converts SAM3's types into them.
- Change: in Python the logger builds its own record during the call: the frame into the pool, the boxes as a tuple of tuples of floats, the masks as bytes. It never stores the caller's dataclass.

**R1-4. Masks have no disk format and no memory bound; the obvious JSON encoding stalls the main thread.** (high)
- Claim: today's masks are full-frame boolean arrays, up to 3 per frame (perception2/engine.py, mask_k=3, `mask_for_box` returns a bool mask). One is 1280x720 = 0.92 MB. Three per pass are 2.8 MB, more than the frame.
- Claim: the pool bounds frames only. Masks are "copied into the record" outside the pool. 64 queued passes with 3 masks hold 177 MB.
- Claim: telemetry.md never says how a mask is written. Today it is not written at all.
- Why it matters: the writer must serialize them somehow. `json.dumps(mask.tolist())` is the path of least resistance.
- Evidence: measured: json.dumps of one mask's list is 6.3 MB and 16.7 ms, holding the GIL. With that writer running, the main thread's 1 ms sleep woke at p99 13.6 ms and max 20.0 ms (idle: max 1.07 ms).
- Evidence: measured: the same mask as a 1-bit-style PNG (uint8 0/255) is 3.4 KB and 1.6 ms. np.packbits gives 115 KB.
- Evidence: measured: the frame copy and the JPEG writer do not disturb the main thread (max 1.08 ms against 1.07 idle). The design's split is sound for frames.
- Change: the header fixes the mask format: one PNG per mask, `pass_<n>_mask_<k>.png`, encoded on the writer. The pass line lists the mask files.
- Change: the pool holds a mask budget beside each frame (3 masks of the frame's size), so masks are bounded with their frame.

**R1-5. The frame pool's empty case is undefined, and it makes the queue's 64 a fiction for passes.** (high)
- Claim: the header defines what a full queue does. It does not define what an empty pool does. With 8 frames in the pool, the 9th pass finds no frame long before the queue holds 64.
- Claim: section 8 says "a full queue at 4 records a second means the disk has stalled for over 15 s". For passes the true threshold is 8 passes: at 3 passes a second, 2.7 s.
- Claim: the job thread calls RecordVisionPass while it holds its frame-buffer slot (RVW3). A job blocked on the pool holds that slot for the whole wait. Eight blocked jobs hold 8 of 32 slots.
- Claim: the pool is sized for 1280x720x3. telemetry.h carries m_width and m_height, so other sizes are expected. A 1920x1080 webcam frame (6.2 MB) does not fit a 2.6 MiB pool frame.
- Why it matters: section 6: "from up to 8 job threads". The pool equals the job count, so one writer pause of 2.7 s at full load blocks every job.
- Change: state the empty-pool rule in the header: the job thread waits on the pool with the same writer-stall rule as R1-1, then dies.
- Change: TelemetryCreate takes the frame geometry (width, height, channels) from the frame buffer, and sizes the pool from it. A pass with a larger frame is our own bug: die.
- Change: drop the "64 records" story for passes. Name the real bounds: 8 passes in flight; the main thread's records unbounded (R1-1).

**R1-6. TelemetryDrain inside die() makes a second consumer, recurses from the writer, and its 5 s cap cannot interrupt a blocked syscall.** (high)
- Claim: die() can run on the main thread, a job thread, or the writer itself (a failed write, section 7). Drain "writes what the queue holds" on die's thread. The writer may still be running. Two consumers then pop the same queue and write the same files.
- Claim: on the writer's own die(), Drain retries writes on a disk that just failed. The next failed write calls die() again: re-entry.
- Claim: a write or fsync on a stalled disk blocks in the kernel. A Python "5 s cap" cannot interrupt it. Only a join with a timeout bounds the wait.
- Why it matters: the perf review found the same fault (R1-6 there). Its fix is approved: one consumer at a time; die()'s flush has a timeout (conclusions.md).
- Change: Drain puts the stop sentinel and joins the writer with a 5 s timeout. The writer stays the only consumer.
- Change: when die() runs on the writer thread, Drain does nothing: the disk is known bad.
- Change: the writer writes the die reason as the last trace line when it can. The replayer then knows why the run ended.

**R1-7. The record misses the events that explain a run: the stop, the manual switch, the keys, the dropped sentence, the status changes, the end.** (high)
- Claim: there are three record kinds; none is an event. F1 quit, F2 stop every job, F4 manual plus a stop, F5 release: none is recorded. A stop from a key leaves no trace.
- Claim: the design document requires a record that the API cannot express. Section 4 (RVW6, RVW7): the sentence in planning "is dropped, with a chat line and a log line". DecisionKind has no DROPPED or CANCELLED value. A cancelled mission has no state.
- Claim: a mission refused while the phone's row is WAITING, and a 409 in manual mode, have no field. m_platformStatus 0 means "no request".
- Claim: the status row changes (phone WAITING, a child restart, the video restart) are chat lines only. They are the cause of most failures a replay is for.
- Claim: no line marks a clean end. A replayer cannot tell a clean exit from a crash.
- Why it matters: the replayer must explain why a job ended CLEARED and why a mission stopped. The emergency budget (section 8) can be checked only if the stop's send and reply are recorded.
- Evidence: source 5: MCAP and rosbag2 record a stream of time-stamped messages, not aggregated records. The events are the record.
- Change: add `TelemetryRecordEvent(t, const EventData*)`, main thread only: (time, kind, turn or job, detail). Kinds: key, stop sent, stop reply, manual on, manual off, mission cancelled, sentence dropped, mission refused, status change, end, die.
- Change: this is a fourth call beside TEL1's API. TEL1 accepted additions with a reason (RecordVisionPass, ClaimMicClip); this needs the owner's acceptance the same way.

**R1-8. A turn is written only when it ends, and a job folder gets its identity only at the job's end: a crash loses exactly the records a post-mortem needs.** (high)
- Claim: RecordTurn is called on the PlatformReply. A mission waits up to 3 s on a dead phone (section 8). If the app dies in that window, the turn that caused it is never written.
- Claim: job.json is written "once at the job's end". A crash mid-job leaves pass files with no kind, phrase or turn. Today's code writes request.json at the start and rewrites it at the end (session.py begin_request, end_request).
- Why it matters: section 6: "a crash keeps every record that reached the writer". A record that never reached the writer is the in-flight one, the most important one.
- Change: RecordTurn is called twice: at the Decision (heard, decided, mission) and at the end (status, spoken). The trace gets two lines per turn, joined by seq, with a `phase` key.
- Change: RecordVisionJob is called at the start (state TRACKING, already in the enum) and at the end. job.json is written at the start and replaced at the end.

**R1-9. "One atomic write + fsync per file" is not durable for new files without a directory fsync.** (medium)
- Claim: every pass creates new names: pass_<n>.jpg, pass_<n>.json, and a new folder perception/<job>/. util/guarded.py atomic_write fsyncs the temp file, then renames. It never fsyncs the directory.
- Claim: after a power loss or a kernel crash, the rename may be lost. The file then never existed, despite its fsync.
- Claim: for an app crash (die, a Python exception, SIGKILL) the page cache survives anyway. The per-file fsync protects only against power loss and kernel crashes, and without the directory fsync it does not deliver that either.
- Why it matters: the design pays for a guarantee it does not get. trace.jsonl is created once, so its directory entry also needs one directory fsync at Create.
- Evidence: source 1, quoted above. Source 2: rename-over-write needs fsync for durability.
- Evidence: measured on overlayfs: an atomic 246 KB JPEG write p50 0.89 ms; with the directory fsync p50 1.42 ms. The cost is 0.5 ms a pass, under 2 ms a second at full load.
- Change: atomic_write fsyncs the parent directory after the rename. TelemetryCreate fsyncs the session folder and the perception folder after mkdir; the writer fsyncs perception/ after each new job folder.

**R1-10. The mic clip claim runs disk operations on the main thread, guesses by mtime, and holds a claimed set.** (medium)
- Claim: ClaimMicClip globs asr_clips/, stats every file for its mtime, and renames, on the main thread. A rename is a journaled metadata write. During a disk stall it blocks like any write.
- Claim: the ASR node names each clip with a monotonic index: `audio_%06u_<date>_<time>.wav` (projects/llm_to_action/source/asr/asr_node.cpp line 234). "Newest by mtime" guesses what the name already states.
- Claim: the index restarts at 0 when the supervisor restarts the ASR node. The time part has 1 s resolution. A restart in the same second as a previous clip overwrites that clip.
- Claim: a failed transcription leaves an orphan (no publish; asr_node.cpp after "Transcribe failed"). The newest rule handles it. A transcript the app filters out before the claim also leaves an orphan. That is correct only while every claim runs before the next clip lands.
- Why it matters: section 6: the main thread never blocks on the disk. TEL1: "NO app state"; the claimed set is state about turns.
- Change: the mic listener (a producer thread, allowed to block) reads the clip name when it receives the transcript, and puts it in the Transcript message. The ASR node writes the clip before it publishes, so the listener sees transcripts in clip order.
- Change: no rename at all. The turn line carries the ASR's file name. The claimed set and ClaimMicClip go away.
- Change, better and outside this module: the ASR node publishes the clip name with the transcript. That is the exact join; record it as an item for the speech-in module.

**R1-11. The fixed char arrays truncate silently, cut UTF-8 mid-letter, and contradict the const char* fields of VisionPassData.** (medium)
- Claim: Hebrew is 2 bytes a letter in UTF-8. m_heard[512] holds about 250 letters. m_spoken[256] holds about 125 letters. m_rejectReason[64] and m_why[96] are shorter still.
- Claim: a cut can split a letter, and it can cut m_missionJson[2048] mid-structure. The line is then undecodable JSON. The perf review proved this exact fault (R1-2 there).
- Evidence: measured: the longest dataset sentence (datasets/recognizer, `he`) is 277 bytes. It fits. A whisper segment of 30 s of continuous Hebrew speech would exceed 512 bytes (an estimate, unverified). A spoken describe answer of two sentences exceeds 256 bytes (an estimate, unverified).
- Evidence: the logger deep-copies anyway (TEL1). Fixed arrays buy nothing in C, and they are fiction in Python, where the fields are str.
- Change: every text field is `const char*`, copied during the call, as VisionPassData already does. If a cap stays, the header states the rule: never cut; write the length instead, as perf does with `{"cut":N}`.

**R1-12. The pass record cannot be placed on the run's timeline or joined to perf.** (medium)
- Claim: VisionPassData has m_capturedAt and m_ms. It has no start or end time of the pass. The replayer cannot say when a pass ran, or how stale its frame was when SAM3 got it.
- Claim: it has no request id. Perf joins sam3_request and sam3_pass by `req` (perf.md, instance 2). A pass in telemetry cannot be joined to its timing.
- Claim: m_capturedAt is undefined: the camera's time, the gstreamer decode, or the frame source's receipt.
- Why it matters: the brief asks for the frame's capture time against the pass time. Section 8 lists SAM3 passes of 410 ms to 1.9 s: the frame age is the number a highlight's lag depends on.
- Change: replace m_ms by m_startedAt and m_endedAt (PerfTimestamp). Add m_req, the perf join key. Define m_capturedAt as the frame source's PerfNow() when it published the slot.

**R1-13. meta.json's clock pair differs from perf's approved clock line, and the session has no end record.** (medium)
- Claim: meta.json holds "the start wall-clock and the monotonic clock". Perf's approved PerfClockLine holds three: monotonic, realtime, boottime. The boottime detects a suspend (perf R1 sources 12, 13).
- Claim: a laptop lid closed mid-session stops CLOCK_MONOTONIC. Telemetry's pair then converts every later timestamp wrongly. Perf would flag it; telemetry would not.
- Why it matters: every TurnData timestamp is a PerfTimestamp. The replayer converts them with meta.json's pair. Two modules, two conversions of one clock: one home per value is a house rule.
- Change: meta.json embeds the same three clocks through the same function as PerfClockLine. Destroy and die() write an end line (R1-7).

**R1-14. 3.1 GB an hour needs a rule: a full disk is a predictable death mid-flight.** (medium)
- Claim: at full load the record writes about 3 passes a second. A full disk gives ENOSPC. RVW4 makes that a crash, and mid-flight a crash is the hand-over to the RC.
- Claim: nothing checks the free space. The death is predictable and avoidable.
- Evidence: measured: OpenCV's default JPEG quality is 95; real 720p session frames encoded at 154 to 283 KB. At 3 a second that is 1.7 to 3.1 GB an hour. The design's top number holds.
- Evidence: measured: this machine's repo partition has 394 GB free. That is over 100 hours. The laptop's free space is unknown (unverified).
- Evidence: the file count: 3 passes a second for an hour is 10,800 passes, 21,600 files, plus temp files and masks. Source 5: MCAP writes one append-only file, chunked, readable without its summary.
- Change: TelemetryCreate dies when the free space is under a config floor, for example 2 hours at full load (6 GB). The start-up death is allowed; the mid-flight one is not.
- Change, optional: one passes.jsonl per job folder, one fsynced line per pass, like trace.jsonl. That halves the files and needs no temp file per pass. The JPEGs stay separate for the browser replayer. A move to MCAP is not justified: the replayer reads plain files.

**R1-15. The JPEG choice is right, but two numbers are wrong and one claim of the replayer becomes false.** (low)
- Claim: open point 4 says PNG takes 23 ms and 1.3 MB. Measured on real session frames: 34 to 41 ms and 0.8 to 1.2 MB at compression 1; 47 to 64 ms at level 3.
- Claim: the replayer README promises "the same frames can later be re-scored by a different model". A JPEG is not the frame SAM3 saw. A re-score is close, not equal.
- Evidence: measured: JPEG quality 95 on these frames: PSNR 48 to 59 dB, max pixel error 4 to 10. Caveat: the source frames were already JPEGs, so the true loss on a raw frame is larger. Source 9: detector and classifier output varies with JPEG compression.
- Evidence: measured: JPEG encode 1.5 to 2.3 ms here (design: 2.6 ms); the frame copy 0.05 ms (design: 0.18 ms). Both support the design's budget.
- Change: keep JPEG at quality 95, named in config. Correct the PNG numbers. State in the replayer README that a re-score on JPEG is approximate.

**R1-16. The writer counts passes per job, the app counts them too, and the order of the last pass against the job end is unstated.** (low)
- Claim: section 7: the writer keys a pass counter by job id; VisionJobData carries m_passes from the app. Two owners of one number can disagree.
- Claim: the writer's map is state about jobs. It leaks an entry when a job end never arrives (a bug, a crash of the job thread).
- Claim: job.json is correct only if the job thread records its last pass before it posts the VisionResult. Instance 2 shows that order; the header does not require it.
- Change: the job thread numbers its passes (m_index in VisionPassData). The writer keeps nothing per job. The header states: record the pass, then post the result.

**R1-17. The crash guarantee is overstated.** (low)
- Claim: section 6: "a crash keeps every record that reached the writer". It holds only on the die() path. A SIGKILL, the OOM killer, or a segfault in a C extension (cv2, the SAM3 client) runs no die(). The queue's records are lost.
- Why it matters: the claim will be cited later as a guarantee.
- Change: state it plainly: every record the writer wrote survives an app crash; the queue is the loss window; at under 4 records a second it holds 0 or 1 record (writer idle 99 %).

**R1-18. The Python mapping uses an exception and a version feature the house rules do not allow as written.** (low)
- Claim: put with a timeout raises queue.Full. The house rule: a try exists only in util/guarded.py. The mapping does not say where Full is caught.
- Claim: Queue.shutdown exists from Python 3.13; this machine runs 3.12.3. The sentinel stop is therefore right; it must stay a sentinel.
- Evidence: source 7; measured: `hasattr(queue.Queue(), "shutdown")` is False here; put(timeout=0.2) raised Full after 200 ms.
- Change: with R1-1 the main thread's put never blocks and never raises. The job thread's pool wait uses a Condition with a timeout, which returns a bool and raises nothing.

**R1-19. The header has local defects.** (low)
- VisionJobData's comment lacks @m_phrase.
- VisionJobData.m_kind is a DecisionKind, so it admits EMERGENCY or MANUAL. A job kind needs its own three-value enum.
- VisionJobState includes JOB_TRACKING, not an end state. It is right only with R1-8's start record; say so.
- VisionPassData has no pixel format or row stride. A view with a stride (a crop, a padded slot) would be copied wrong.
- m_frame is uint64_t; every other sequence number is uint32_t. Pick one.
- telemetry.md section 3 calls ClaimMicClip's argument `out`; the header has `clipPath, cap`.

**R1-20. The tests miss the behaviors that can fail.** (medium)
- Missing: the main thread's record returns in under 1 ms while the writer is blocked (R1-1).
- Missing: the pool empty case, with 8 job threads and a blocked writer (R1-5).
- Missing: mutate the boxes and the masks after the call; the written files keep the originals (R1-3). The listed test checks the frame only.
- Missing: die() on the writer thread does not drain and does not re-enter (R1-6).
- Missing: a 1000-byte Hebrew heard text and a 3000-byte mission round-trip unchanged (R1-11).
- Missing: a crash mid-job leaves a folder whose job.json names its kind and turn (R1-8).
- Missing: the replayer's reads. test_show_reads_a_session covers show.py, which reads neither job.json nor the passes. A Python test must read a written session with the replayer's key table (R1-2).
- Fault: test_full_queue_blocks_then_dies waits the real 5 s. The cap must be a config value; the test sets it to 50 ms.
- Fault: test_pass_cost_on_the_caller_under_one_ms runs one thread. Run it with 8 job threads recording at once.

## Questions for the manager agent
1. RVW4 rules that a disk error crashes. Is a stalled disk (no error, a write older than 5 s) the same case? R1-1 assumes yes, detected by the writer's heartbeat, never by a blocked main thread.
2. TEL1 fixes the API's calls. Does the owner accept a fourth call, TelemetryRecordEvent (R1-7), and two calls per turn and per job (R1-8), on the same terms as RecordVisionPass?
3. RVW6 and RVW7 require "a log line" for a dropped sentence. Is that line telemetry's, perf's, or stdout's? The design does not say.
4. Open point 3 cannot hold as worded (R1-2). Does the owner prefer today's keys kept, or a new key table with replayer.html changed in the same commit?
5. Telemetry needs the SAM3 box and mask shapes before the SAM3 server is reviewed. Do telemetry's own record types (R1-3) settle that, or does the review order change?
6. Is the mic clip rename worth keeping at all (R1-10)? Dropping it removes ClaimMicClip and the claimed set.
7. Does the owner want a free-space floor at start-up (R1-14), and at what number of hours?
