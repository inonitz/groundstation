# Recorder consistency, round 6, checker 1 (2026-10-22)

**Verdict: NOT CONSISTENT. 37 unique findings: 3 BLOCKING, 17 MINOR, 17 NOTE.** A row marked "(same as Xn)" repeats a finding from another check and is not counted again.

Sources: D = test/recorder-decisions-2026-10-21.md; md = modules/01-recorder/recorder.md; headers by file name; RT = modules/03-runtime/runtime_internal.h.

## A. Decision document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | Item 10: "Die stores the reason first, and asks the recorder to stop second ... the stop request is an atomic store with release order". Headers reverse it: the stop request is a compare-and-swap on m_state, then the winner stores the reason, then the deadline with release. | D:125; recorder.h:58-60; record_writer.h:83-87; recorder_internal.h:24-26 | BLOCKING |
| A2 | Item 5: "A Die during a Destroy waits for the Destroy's drain until its own deadline". record_writer.h says the Die "returns at once". This is the RCD57 form that RCD58 reversed. recorder.h:61-62 and record_writer.h:171-173 follow the decision. | D:63; record_writer.h:87-88 | BLOCKING |
| A3 | Item 10's corner: "The writer may be past its die-line step. Then the file gets no die line" (so an earlier Die could still write one). The headers say a Die during a Destroy stores nothing, so there is never a die line. | D:127; recorder.h:60-62 | MINOR |
| A4 | Item 6 lists five operations. The header adds BufferPoolPeekFilled and PoolBuffer.mb_pngWritten, which item 11's last paragraph requires. The decision's list is incomplete. | D:75, D:151; buffer_pool.h:46-47, 56, 89 | MINOR |
| A5 | Item 6 says "free" is gone. The decided names use it: m_freeList, TakeFree, ReturnFree. | D:75; buffer_pool.h:69, 80, 92 | NOTE |
| A6 | Item 12: note_drop "stores the two times". The header stores the first time only when newGap is set. | D:157; recording_thread.h:81-83 | NOTE |
| A7 | Item 13: the helper stops and returns the error code itself. record_field.h lists "a maker returned false" as a cause of a record call's INVALID_ARG, and counts INVALID_ARG in the health. recorder.h:79-80 says nothing is counted. | D:168; record_field.h:68, 71; recorder.h:79-80 | MINOR |
| A8 | Item 11: "the pass ends" for every queue, and "the producers drop and count ... the health ... show it". The header does not say whether steps 5, 7, 8 and 9 run after a failed append. If they are skipped, the drop sums and m_lastProgressAt never update while the disk is dead. | D:7, D:141; record_writer.h:139-140, 146-147, 154-156 | MINOR |
| A9 | Item 1 matches: an index queue under one lock, and two queues. | index_queue.h:1-5, 24; buffer_pool.h:60-63 | - |
| A10 | Item 2 matches: wait, clear, pass, back to step 1. | record_writer.h:134, 157-158 | - |
| A11 | Item 3 matches: NOT_CREATED, counted nowhere. | record_field.h:70-72; recorder_internal.h:22-23 | - |
| A12 | Item 4 matches: 16 KiB, twice the bound, a cut line counted. | record_writer.h:34-43, 57; recorder.h:91-92 | - |
| A13 | Item 5's drain-to-empty matches. Only A2 is off. | record_writer.h:159-171 | - |
| A14 | Item 6's mechanism matches: the pool answers the stall question, and no stall field is shared. | buffer_pool.h:94-99; record_writer.h:90-93, 128-131 | - |
| A15 | Item 7 matches: drops are summed at the end of each pass. | record_writer.h:154-155; recorder.h:80-81 | - |
| A16 | Item 8 matches: 16 entries with their queues allocated at Create, a claim by index, the 17th claim dies. | recording_thread.h:3-6, 29-33; recorder_internal.h:53-57; recorder.h:33-34 | - |
| A17 | Item 9 matches: STOPPING from RUNNING only, the writer alone stores STOPPED, terminate then join. | recorder_internal.h:24-28; record_writer.h:171-176 | - |
| A18 | Item 11 matches: front, format, append, pop; the record stays at the front; failed writes count attempts. | record_writer.h:61-66, 138-140; recorder.h:88-90 | - |
| A19 | Item 12 matches: three counts, two times, one mutex, two operations. | recording_thread.h:54-85 | - |
| A20 | Item 13 matches: bool, an out parameter, out unchanged on false; FIELD_INVALID absent. | record_field.h:81-95 | - |
| A21 | Item 14 matches: the session dir, process name and info JSON bounds are checked by Create; folder 64 and name 32. | recorder.h:25-43; record_frame.h:10-13 | - |
| A22 | Item 15 matches: a second Create returns false; past its timeout Destroy returns false and stores nothing; the writer is a daemon thread. | recorder.h:33, 51-56; record_writer.h:27 | - |
| A23 | Item 16 matches: OsEventIsSet exists, and the producer skips the set. | RT:85; recording_thread.h:146-149 | - |
| A24 | T1 matches: LINE_FAULT with at, what and count, written at step 9. | record_file.h:35, 95-100; record_writer.h:154-156 | - |
| A25 | T2 matches: no retry queue, no RetryLine, no step "retry" in any header (grep). | 01-recorder/*.h | - |

## B. Decision document vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | Item 13: a maker's false stops the helper before any record call. Test 5 says "the helper stops, and the record call returns INVALID_ARG, counted". | D:168; md:330 | BLOCKING |
| B2 | The same item 13 drift in gate item 3: "a maker's bad value gives INVALID_ARG, counted". | md:208 | MINOR |
| B3 | Item 10's order (the reason first, the stop second) is nowhere stated as the rule. md:262 states the compare-and-swap first, as the headers do. md:24 lists "the reason, Die's deadline, the flag". | D:125; md:24, md:262 | MINOR |
| B4 | Item 14's bounds are missing: no session-dir, process-name or info-JSON limit anywhere in md (grep for 192, 8192, "longer" in that sense: 0). | D:176; md (absent) | MINOR |
| B5 | Item 8 says Python is "bounded, not static": the deque grows by one tuple per record. md says "no allocation at all" on the record path. | D:102; md:206 | MINOR |
| B6 | The rule at D:31 says a value with many writers gets a Lock. The Python mapping claims the thread index "by an atomic add". | D:31; md:240 | MINOR |
| B7 | Item 5's "a Die during a Destroy waits for the Destroy's drain" and item 10's corner are absent ("during a Destroy" and "hand-over log": 0 hits). | D:63, D:127; md (absent) | NOTE |
| B8 | Item 15: the daemon writer thread is not mentioned (0 hits). The state rule is at md:262. | D:182-184; md:262 | NOTE |
| B9 | Item 4: the C line cut is only in gate item 10. There is no failure-matrix row for a line over the buffer. | D:57; md:215, md:265-280 | NOTE |
| B10 | "About 250 [writes] a drain" against item 8's "about 200 records between two passes". | D:102; md:131 | NOTE |
| B11 | These items match. 1: md:138, 244, 309. 2: md:21, 139. 3: md:136, 251. 6: md:23, 134, 269. 7: md:245. 9: md:262. 11: md:129, 208, 268, 338. 12: md:261. 15 (test 22): md:347. 16: md:241. T1: md:137, 197. | md as listed | - |

## C. Headers vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | md says "no per-buffer state" and "no per-buffer state exists". PoolBuffer carries m_filledAt and mb_pngWritten. | md:127, md:309; buffer_pool.h:44-47, 52-56 | MINOR |
| C2 | md: "A frame wakes the writer every time". No header function says who sets m_wake on a frame: EnqueueFilled and RecordFrame are silent; only the wake-source lists name it. | md:310; buffer_pool.h:81-82; record_frame.h:20-28; record_writer.h:4, 96 | NOTE |
| C3 | Header elements not described in md sections 2, 3, 7 or 11: kRecorderSessionDirBytes 192, kRecorderProcessNameBytes 31, kRecorderInfoJsonBytes 8192; the 64 and 32 of kRecordFolderBytes and kRecordNameBytes; DieReasonText 256; kRingBytesPerRecordExpected 64; SpscProducerRecordsQueued and SpscProducerRecordsDropped; kWriterExpectedVisionPassesPerMinute 30; RecorderNameThisThread (only in the section-4 history, md:176). | recorder.h:27-31, 69; record_frame.h:11-12; record_writer.h:44, 55; spsc_record_queue.h:54-55, 75 | NOTE |
| C4 | Drawing 6 lists the writer's counts as "failed writes and PNG name clashes". m_truncatedLines is missing. | md:25; recorder.h:91-92; recorder_internal.h:46 | NOTE |
| C5 | Test 10's order (thread, drop, die, time reference, health) omits the fault line. The last pass writes it between the die line and the time reference whenever a drop changed a count. | md:335; record_writer.h:166-168 | NOTE |
| C6 | Every code name md uses exists in a header with that name: the Producer*, BufferPool*, Writer*, RecordFile*, Recorder* functions, SpanStage (15), kRecordingThreadsMax 16, the 16384 queue, 8 and 24 buffers, the 8 KiB bound, 16 KiB, every key of the md:221-230 sample, is_set 23 ns and set 332 ns. | md:20-25, 221-230, 241, 426-434 | - |

## D. Internal consistency of recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | "T1 is RCD19's util headers", while sections 4 and 6 use T1 for the fault line, as the decision document does. | md:411 vs md:137, md:197 | MINOR |
| D2 | A history row in the present tense: "the header does it the other way, Destroy by a compare-and-swap from 0 and Die unconditionally, so Die wins (D8 as built)". The superseding rulings (RCD41, RCD58) are not named. It contradicts md:262 (one winner by a compare-and-swap from RUNNING). | md:165 | MINOR |
| D3 | History rows D4 ("a failed ring Init is tried once"), D7 ("two atomics the writer stores at each pass end") and D12 ("Create resets every thread's announced flag") are superseded by items 8, 6 and 15. The banner names only K1, RCD17, RCD20 and RCD23. | md:146-149, 163-167 | NOTE |
| D4 | The time a dead disk takes to fill the queues: "about seven minutes" and "over six minutes" (16,384/40 = 6.8 min; both true). | md:268, md:273 | NOTE |

## E. Internal consistency of the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | A Die during a Destroy "returns at once" against "waits for the Destroy's drain" (same as A2). | record_writer.h:87-88 vs record_writer.h:171-173, recorder.h:61-62 | (A2) |
| E2 | The stop handshake cannot work as written (same root as A1). The CAS to STOPPING comes first; the reason and the release-stored deadline come after. The writer loads the state at step 1 and the deadline once at the start of its last pass. It can see STOPPING, read a deadline of 0 (cut everything at once), and read DieReasonText with no happens-before, a data race. "The writer's last pass sees a complete reason" is not guaranteed. | recorder_internal.h:25; record_writer.h:84-87, 134, 159; recorder.h:59-60 | (A1) |
| E3 | "INVALID_ARG: a maker returned false" and "INVALID_ARG counted in the health", against "a maker that returned false stops the helper before any record call, so nothing is counted" (same as A7). | record_field.h:68, 71 vs recorder.h:79-80 | (A7) |
| E4 | "no state per buffer exists" against the per-buffer m_filledAt and mb_pngWritten. | buffer_pool.h:6 vs buffer_pool.h:44-47, 52-56 | MINOR |
| E5 | Two drop counters per thread. The queue counts in m_dropped (SpscProducerRecordsDropped); the producer also counts in its DropRecord. Which one feeds the health is not stated. D item 12 says only the drop record's two operations touch the drops. | spsc_record_queue.h:46, 55, 101-102, 112; recording_thread.h:63-85 | MINOR |
| E6 | IndexQueueFront's locking contract is not stated. Push and Pop take the one lock. If Front also takes it, the documented sequence (IndexQueueLock, then IndexQueueFront) deadlocks. If it does not, BufferPoolPeekFilled reads the front without a stated lock. | index_queue.h:1-2, 35-43; buffer_pool.h:89, 95-97 | MINOR |
| E7 | The deadline's cut-offs are "counted by kind into the health counters"; then step 9 puts "the sums of every entry's drop record into the health counters". Add or store is not stated. With a store, the cut-off counts are overwritten. | record_writer.h:154-155, 164-168; recorder_internal.h:36-37 | MINOR |
| E8 | The file order omits the fault line. The last-pass order (die, then time reference and health) skips step 9's fault lines. The normal order lists no fault line either. | record_file.h:19-25 vs record_writer.h:154-156, 166-168 | MINOR |
| E9 | The @ block documents two of the three "Reported" fields. m_droppedFramesReported is undocumented. | recording_thread.h:94-98, 107 | NOTE |
| E10 | The writer's health line has "stalled", but the stall is computed on the main thread. RecorderCounters has no stalled field. The writer's source for the key, and for its fault line, is not stated. | record_file.h:119; recorder.h:95-97; recorder_internal.h:41-51; record_writer.h:131 | NOTE |
| E11 | OsLock is typedef'd twice (legal in C11). OsEventWait is declared apart from the other OsEvent operations. There is no create or destroy for OsEvent or OsLock, although Create allocates them. | RT:87, 90, 92; recorder.h:33-34 | NOTE |
| E12 | With a dead disk the last pass repeats steps 2 to 6 with no sleep until the deadline, a busy loop of up to 5 s. This is not stated. | record_writer.h:159-161 | NOTE |
| E13 | DieReasonText holds 256 bytes. What happens to a longer reason is not stated. | record_writer.h:55 | NOTE |
| E14 | gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11: all 10 01-recorder headers pass with 0 warnings and 0 FAIL. fixed_text.h alone gives a pedantic empty-unit warning (outside the loop). | 01-recorder/*.h | - |
| E15 | No leftover names: no retry queue, RetryLine, FramePool, FIELD_INVALID, lazy allocation, second Create, abandoned writer or shared stall field. "slot" appears only for the SPSC ring and the frame buffer's slot; "ready" only for an entry's claim. | spsc_record_queue.h:78-107; record_frame.h:23; recording_thread.h:92 | - |
| E16 | The aggregate holds all 16 headers verbatim (a substring check per file). | recorder_aggregate_for_review.md | - |
