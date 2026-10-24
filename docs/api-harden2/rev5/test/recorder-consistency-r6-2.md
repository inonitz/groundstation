# Recorder consistency check, round 6, agent 2 (2026-10-22)

**Verdict: NOT CONSISTENT: 6 BLOCKING, 22 MINOR, 14 NOTE.**

Sources: recorder-decisions-2026-10-21.md (D), the 16 headers (H), recorder.md (M), runtime_internal.h, the ledger rows up to RCD58.
Mechanical checks: gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on the ten 01-recorder headers: 10 of 10 pass, zero warnings. The aggregate holds all 16 headers verbatim (16 of 16 code blocks equal). No leftover name of a removed mechanism (FramePool, FIELD_INVALID, retry queue, RetryLine, ready queue, lazy allocation, second Create, abandoned writer, shared stall field) in any header.
A cross-reference "(= Xn)" carries no severity, so each finding counts once.

## A. Decision document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | Item 1, the index queue under a lock: present (OsLock* m_lock; two queues, two locks) | index_queue.h:1-5,24; buffer_pool.h:60-63 | OK |
| A2 | Item 2, one return arrow (wait, clear, pass, back to step 1): present | record_writer.h:134,157-158 | OK |
| A3 | Item 3, a call before Create returns NOT_CREATED, counts nothing: present | record_field.h:70-72; recorder_internal.h:22-23 | OK |
| A4 | Item 4, a 16 KiB C buffer, twice the bound, cut, the reader skips, the writer counts: present | record_writer.h:34-43,57,118; recorder.h:91-92 | OK |
| A5 | Item 5, the last pass repeats steps 2 to 6 until empty or the deadline: present | record_writer.h:159-171 | OK |
| A6 | Item 5: "For a Destroy that deadline is the app's timeout" (D:65). No header states the value Destroy stores in m_stopDeadline | record_writer.h:83-87; recorder.h:51-56 | MINOR |
| A7 | Item 5: "A Die during a Destroy waits for the Destroy's drain" (D:63). Contradicted by record_writer.h:88 | (= E1) | — |
| A8 | Item 6, the operations list (D:75) names five; the header has six: BufferPoolPeekFilled (RCD57) is not in the decision document | D:75; buffer_pool.h:89 | MINOR |
| A9 | Item 6, the pool answers the stall question under its own lock; no shared stall field: present | buffer_pool.h:94-99; record_writer.h:90-93,128-131 | OK |
| A10 | Item 7, every thread counts its own dropped frames; the writer sums: present | recording_thread.h:43-48; recorder.h:83-87 | OK |
| A11 | Item 8, the table of 16 entries with their queues allocated at Create; a claim is an index; the 17th dies: present | recording_thread.h:1-8,29-31; recorder_internal.h:53-57 | OK |
| A12 | Item 9, four states; STOPPING only by the recorder's two functions; terminate and join: present | recorder_internal.h:22-34; record_writer.h:171-176 | OK |
| A13 | Item 10: "Die stores the reason first, and asks the recorder to stop second" (D:125). The headers do the reverse: the compare-and-swap to STOPPING comes first, then the reason, then the deadline. The writer enters its last pass on seeing STOPPING (step 1), so it can load the deadline (acquire) before it is stored: deadline 0 cuts everything off, and the reason can be incomplete | D:125; record_writer.h:83-87,134,159; recorder.h:59-60 | BLOCKING |
| A14 | Item 10, the one corner: D:127 says the die line is lost only when the writer is past its die-line step. The header says a Die during a Destroy never gets a die line | D:127; recorder.h:61-62 | MINOR |
| A15 | Item 11, the queue rule: a failed append ends the pass, the record stays at the front: present | record_writer.h:61-66,138-140; buffer_pool.h:84-88 | OK |
| A16 | Item 11 with line 7: "the producers drop and count ... the health and the chat line show it" (D:7). The header says a failed append "ends the pass". Step 9, which sums the drop records into the health counters, is "the end of the pass". Read literally, step 9 is skipped while the disk is dead, so the health's drop counts freeze | D:7,143; record_writer.h:138-140,154-156 | BLOCKING |
| A17 | Item 11: "The writer's own lines. The same rule holds for them" (D:151). Only the thread line's rule is stated (step 3), and it does not say whether that failure ends the pass. The rule is MISSING for the drop line (step 5), the health line (step 8) and the fault line (step 9) | record_writer.h:136-137,141,152-156 | MINOR |
| A18 | Item 12, the drop record: three counts, two times, one mutex, two operations: present | recording_thread.h:54-85 | OK |
| A19 | Item 13, a maker returns bool with an out parameter, unchanged on false: present; FIELD_INVALID absent | record_field.h:81-95 | OK |
| A20 | Item 14, "Every limit lives in config ... checked": the session folder, the process name, the info JSON, the folder and the name are present. MISSING: a rule for ThreadName (32) and DieReasonText (256), so a longer thread name or die reason has no stated check or cut | recorder.h:25-31,40-41; common_names.h:12; record_writer.h:55; recorder.h:66-69,64 | MINOR |
| A21 | Item 15, one Create; Destroy returns false past its timeout and stores nothing; daemon: present | recorder.h:33,51-56; record_writer.h:173-176; recorder_internal.h:27-28 | OK |
| A22 | Item 16, is-set before set; OsEventIsSet declared: present | recording_thread.h:146-149; runtime_internal.h:85 | OK |
| A23 | T1, the fault line (LINE_FAULT; at, what, count; step 9): present | record_file.h:35,95-100; record_writer.h:154-156 | OK |
| A24 | T2 gone: no retry queue or depth anywhere in the headers | grep, all 16 headers | OK |

## B. Decision document vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | The Python mapping row says the first record claims an index "by an atomic add". In Python the decision allows only a plain int for one writer, a Lock for many writers, and the atomics package for the frame buffer alone (D:31). Many threads claim, so a `+= 1` races (D:17) and two threads can get one SPSC queue. The header gives no Python form for m_claimedCount, unlike its other shared values | M:240; D:17,31; recorder_internal.h:55-56 | BLOCKING |
| B2 | Section 4's title says "P1 to P4 closed ... (the decision document)". The decision document now numbers its items 1 to 16 and T1 to T3; P1 to P4 do not occur in it | M:94 | MINOR |
| B3 | Item 10's rule (the reason first, the stop request second) is stated nowhere in recorder.md | M:24,262 | NOTE |
| B4 | Item 5: a Die during a Destroy waits for the drain; item 10's corner (no die line, the hand-over log has the reason). Neither appears in recorder.md | M:24,251,262 | NOTE |
| B5 | Item 14: the bounds checked at Create (session folder 192, process name 31, info JSON 8192) and in RecordFrame (folder 64, name 32) appear nowhere in recorder.md, not in the failure matrix either | M:265-280 | NOTE |
| B6 | Item 4: the cut line (written cut, skipped by the reader, counted in truncated_lines) is only the gate-10 assert and a sample key; it has no failure-matrix row | M:215,229,265-280 | NOTE |
| B7 | Decided items without a test in section 9: the stall via BufferPoolOldestFilledAt (6), the Create bounds (14), Destroy returning false past its timeout (15), the fault line (T1), the cut line (4, C) | M:324-349 | NOTE |

## C. Headers vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | A maker's bad value. recorder.md says the record call returns INVALID_ARG and it is counted (test 5; gate 3). The headers say the helper stops before any record call, so nothing is counted | M:330, M:208; recorder.h:79-80; record_field.h:83-84 | BLOCKING |
| C2 | Header values not described in sections 2, 3, 7 or 11: kWriterExpectedVisionPassesPerMinute (30), WRITER_PNG_BYTES_PER_RAW_BYTE (0.45), DieReasonText (256), and the bounds of B5 | record_writer.h:44,52,55; recorder.h:27-31; record_frame.h:10-13 | NOTE |
| C3 | "The actors by prefix: Producer, BufferPool, Writer, RecordFile" omits DropRecord (DropRecordNote, DropRecordTake) | M:27; recording_thread.h:83-85 | NOTE |
| C4 | The code names of drawing 3 omit OsEventIsSet, which the producer calls before the set | M:22; recording_thread.h:146-148 | NOTE |
| C5 | Test 10 lists the last pass's lines "in that order" without the fault line. With a drop, step 9 writes a fault line between the die line and the time reference | M:335; record_writer.h:166-168 | NOTE |
| C6 | Drawing 6 lists what the writer stores (failed writes, clashes, free space, reserve flag, progress) without truncated_lines | M:25; recorder.h:91-92 | NOTE |

## D. recorder.md against itself

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | T1 is defined as "RCD19's util headers" (M:411). The same document uses T1 for the fault line | M:411 vs M:137,197 | MINOR |
| D2 | A history row presents D8 in the present tense: "the header does it the other way, Destroy by a compare-and-swap from 0 and Die unconditionally, so Die wins". Today Die loses the compare-and-swap. No superseding ruling is named | M:165 | MINOR |
| D3 | A history row: "the stall rule reads two atomics the writer stores at each pass end" (D7). Superseded by item 6 (the pool answers); not named as superseded | M:164 | MINOR |
| D4 | A history row: "a failed ring Init is tried once" (D4). Superseded by item 8 (everything allocated at Create); not named | M:163 | MINOR |
| D5 | A history row: "Create resets every thread's announced flag" (D12). Superseded by item 15 (the reset list gone); not named | M:167 | MINOR |
| D6 | A history row: "drops of a thread without a ring are counted in the thread table" (D2). Superseded by item 8 (RCD51: that branch removed); not named | M:161-162 | MINOR |
| D7 | A history row: "a record in any state but RUNNING is dropped and counted". Superseded for NOT_CREATED by item 3; not named there. The caveat at M:146-147 points at "the headers of draft 15", not the current draft 19 | M:173, M:146-147 | MINOR |
| D8 | "the frame pools" names the type BufferPools / the pools ("Why the frame pools is optional") | M:211,314 | NOTE |

## E. The headers against themselves

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | A Die during a Destroy: "loses the compare-and-swap and returns at once" (record_writer.h:88). The same header and recorder.h say it waits for the Destroy's drain until its deadline. RCD57 wording, left in after RCD58 | record_writer.h:88 vs record_writer.h:171-173, recorder.h:60-62 | BLOCKING |
| E2 | The IndexQueueFront locking contract is unstated. Push and Pop take the queue's one lock. BufferPoolOldestFilledAt calls Front while it holds IndexQueueLock, and OsLock is a plain mutex. If Front locks, it deadlocks there. If it does not, BufferPoolPeekFilled reads the queue unlocked while producers push | index_queue.h:1-2,35-43; buffer_pool.h:89,94-99 | BLOCKING |
| E3 | The stop order: the compare-and-swap comes before the deadline store, so the writer's acquire load of the deadline does not order anything | (= A13) | — |
| E4 | The scheme comment says "the consumer dequeues it, processes it, and returns it". The same header says it peeks, encodes, appends the line, and only then dequeues | buffer_pool.h:4-5 vs 84-88 | MINOR |
| E5 | RecordFrame's comment: "The writer dequeues the filled buffer, encodes the PNG ... appends the frame line". Step 6 peeks first and dequeues last | record_frame.h:23-27 vs record_writer.h:142-148 | MINOR |
| E6 | "no state per buffer exists", yet PoolBuffer carries mb_pngWritten and m_filledAt per buffer | buffer_pool.h:6 vs 44-58 | MINOR |
| E7 | FieldInt fails on "NaN where an int is expected", but it takes an int64_t, which cannot be NaN | record_field.h:83 vs 92 | MINOR |
| E8 | INVALID_ARG lists "a maker returned false" as a record-call result, and "INVALID_ARG [is] counted in the health". Yet a maker's false stops the helper before any record call, and nothing is counted | record_field.h:68,71 vs record_field.h:83-84, recorder.h:79-80 | MINOR |
| E9 | The file-order comment never places the fault lines: not among the pass lines, and not in the last pass (die line, then the time reference). Step 9 and the last pass write them between those two | record_file.h:19-25 vs record_writer.h:154-156,166-168 | MINOR |
| E10 | "a stop request in any other state returns at once". FlushInDie in STOPPING waits for the drain until its deadline | recorder_internal.h:25-26 vs recorder.h:60-62 | MINOR |
| E11 | Step 9 "the sums of every entry's drop record into the health counters". The last pass first adds the deadline cut-off counts to those counters, then runs step 9. If the sum is a store, which is undefined, it erases the cut-off counts before the final health line | record_writer.h:154-155,164-168; recorder_internal.h:36 | MINOR |
| E12 | The writer drains until the deadline, then writes the die, fault, time and health lines, flushes, and stores STOPPED. Destroy waits on m_stopped only until that same deadline. A drain cut at the deadline makes Destroy return false, and the pools are not freed | record_writer.h:159-176; buffer_pool.h:10-11 | MINOR |
| E13 | The comment on RecordingThread names m_droppedSpansReported and m_droppedEventsReported only; m_droppedFramesReported is undocumented | recording_thread.h:96-97 vs 107 | NOTE |
| E14 | The last pass runs step 8 ("then the flush to disk"), then "one more flush": two fsyncs, or one; ambiguous | record_writer.h:152-153,167-168 | NOTE |
| E15 | "slot" survives for the SPSC ring's record slots (util) and module 04's frame buffer slot, not for the pool. "a retry of the frame line" names the pass-level retry. Neither is a removed mechanism | spsc_record_queue.h:7,70-94; record_frame.h:23; buffer_pool.h:47 | NOTE |
| E16 | gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11: 10 of 10 pass, no warning; every include exists; every type used is defined or declared opaque | 01-recorder/*.h | OK |
