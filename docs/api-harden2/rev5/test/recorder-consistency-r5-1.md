# Recorder consistency check, round 5, reader 1 (2026-10-22)

**Verdict: NOT CONSISTENT. 45 unique findings: 8 BLOCKING, 27 MINOR, 10 NOTE.**
A row marked "= Xn" repeats a finding listed in another table. It is not counted twice.

Sources: D = test/recorder-decisions-2026-10-21.md; M = modules/01-recorder/recorder.md; headers by file name.
Paths are under docs/api-harden2/rev5/.

Mechanical checks:
- gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11: 10 of 10 recorder headers clean, 0 warnings, 0 FAIL.
- recorder_aggregate_for_review.md: 16 of 16 headers present verbatim (scripted block compare).
- Leftover names in the headers: FramePool, frame_pool, retry queue, RetryLine, FIELD_INVALID, ready queue, reset, abandoned: 0 hits.
- runtime_internal.h:83-86 has OsEventSet, OsEventClear, OsEventIsSet, OsEventWait.

## A. Decision document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | Item 1, index queue under a lock, two queues with their own locks: OK | D:41; index_queue.h:1-5; buffer_pool.h:55-58 | OK |
| A2 | Item 2, wait, clear, one pass, back to step 1: OK | D:45; record_writer.h:132,153-154 | OK |
| A3 | Item 3, NOT_CREATED before Create, counts nowhere: OK | D:49; record_field.h:70-72; recorder_internal.h:22-24 | OK |
| A4 | Item 4, C line buffer 16 KiB, cut at its end, counted; Python has no buffer: OK | D:57; record_writer.h:34-42,56,115-116; recorder.h:88-89 | OK |
| A5 | Item 5 wants records pushed during a Die in the file ("They must reach the file"). The headers drop every record call once the state is STOPPING, and FlushInDie stores STOPPING first. Records pushed during the drain never reach a queue, so the "again and again" drain has nothing new to take | D:61-63; record_span.h:38-39; recorder_internal.h:23-24; record_frame.h:18-19; record_field.h:66-67; record_writer.h:155-158 | BLOCKING |
| A6 | Item 5 says the only hole is the records pushed after the drain. In the header the deadline's cut-off is counted AFTER the last health line, so those counts never reach the file either | D:65-67; record_writer.h:159-161 | MINOR |
| A7 | Item 6, names: BufferPool, m_freeList, m_workQueue, m_buffers, the five operations, m_framePool, m_maskPool, 8 and 24: OK | D:73-75; buffer_pool.h:1-10,25-29,63-68,75-88,98-103 | OK |
| A8 | Item 6: the main thread "calls that function on each pool and nothing else. No field is shared". The header's stall test also reads the writer's _Atomic m_lastProgressAt on the main thread | D:81; record_writer.h:108,126-129; recorder.h:92-94 | MINOR |
| A9 | Item 6 measures a stall from "the writer's last finished buffer". The header also stores progress at the end of every pass | D:77; record_writer.h:88-89,150 | MINOR |
| A10 | Item 7 says a job thread adds with "a plain += 1". The header takes the drop record's mutex (item 12). The decision document disagrees with itself | D:94 vs D:155-158; recording_thread.h:74-76 | MINOR |
| A11 | Item 8, all allocated at Create, claim by index, 17th dies, Create false on failure: OK | D:100; recording_thread.h:3-6; recorder_internal.h:53-63; recorder.h:32-33,41 | OK |
| A12 | Item 9, CAS from RUNNING, terminate then join: OK | D:106-108; recorder_internal.h:24-28; record_writer.h:162-165 | OK |
| A13 | Item 10 puts the release store on "the stop request". The header puts it on m_stopDeadline; the state is a CAS | D:125; record_writer.h:84-87; recorder_internal.h:25-26 | MINOR |
| A14 | Item 10's corner (a Die during a Destroy's last pass) cannot happen as written: FlushInDie returns at once when not RUNNING | D:127; = E1 | = E1 |
| A15 | Item 10 is DECIDED in the status block and PROPOSED in its own heading | D:9 vs D:121 | MINOR |
| A16 | Item 11, failed append ends the pass, record stays at the front, no retry queue, failed_writes counts attempts: OK | D:133-149; record_writer.h:60-65,136-138; record_file.h:23-24; recorder.h:85-87,95-96 | OK |
| A17 | Item 11, a buffer returns only after its frame line is appended: OK for success. For a failed append there is no rule | D:151; record_writer.h:140-144; = E3 | = E3 |
| A18 | Item 12 names "the count ... three values". The header holds three counts and two times, "the five values" | D:155,158; recording_thread.h:56-78 | MINOR |
| A19 | Item 12 names the Python operations note_drop and take_drop_gap. The header says DropRecordNote and DropRecordTake and names no Python form | D:157-158; recording_thread.h:76-78 | NOTE |
| A20 | Item 13, a maker returns bool, out unchanged on false, None in Python, FIELD_INVALID gone: OK | D:164-170; record_field.h:81-95 | OK |
| A21 | Item 14, session path and info JSON bounds, Create false, 64 and 32 in RecordFrame: OK | D:176; recorder.h:25-30,39-40; record_frame.h:10-17 | OK |
| A22 | Item 15, one Create, Destroy false past timeout, stores nothing, daemon writer: OK | D:184-186; recorder.h:32,50-53; record_writer.h:27,163-165; recorder_internal.h:27-28 | OK |
| A23 | Item 16, is-set before set: OK | D:190; runtime_internal.h:85; recording_thread.h:137-139 | OK |
| A24 | T1, the fault line with at, what, count at the end of each pass: OK for normal passes. The last pass skips it | D:194; record_file.h:34,94-99; record_writer.h:150-152; = E4 | = E4 |
| A25 | T2, retry queue gone: OK | D:198; no hit in any header | OK |
| A26 | Item 1 still names the queues "free and ready". Item 6 says "ready" is gone | D:41 vs D:75 | MINOR |

## B. Decision document vs recorder.md (current-state text only)

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | Item 3 is CLOSED. M still says "OPEN P4" in the change table and in the TOCTOU table | D:11,47; M:136, M:250 | MINOR |
| B2 | T1 is CLOSED: there is a fault line. M sections 4 and 6 say "no event ... the health line ... carry it", "OPEN ... P2" | D:194; M:137, M:197 (M:21 and M:466 are correct) | MINOR |
| B3 | Item 8: all at Create. M gate item 1 says "the thread's entry and queue are made at its first record" | D:100; M:206 | BLOCKING |
| B4 | Item 8: the Python entries and deques exist from Create. The Python mapping says the table is "a list, appended last" | D:102; M:239 | BLOCKING |
| B5 | Item 8: the claim takes an index. TOCTOU says "the table entry is an atomic pointer ... NULL until then". The header uses a fixed array with mb_claimed | D:100; M:255; recording_thread.h:84-85,96; recorder_internal.h:63 | BLOCKING |
| B6 | Item 12: the drop record is under a mutex. TOCTOU describes a lock-free release and acquire order on first, last and the count | D:155-160; M:260 | BLOCKING |
| B7 | Item 15: Destroy past its timeout stores nothing. TOCTOU says "STOPPED has two [writers] ... Destroy past its deadline, and Create then needs a joined writer" | D:184-186; M:261 | BLOCKING |
| B8 | Item 15: one Create per process. Test 21 ("a second Create on the same file name fails, O_EXCL") and the failure matrix ("O_EXCL guards ... a re-Create by the same process") describe a second Create that cannot reach O_EXCL | D:186; M:345, M:276 | MINOR |
| B9 | Item 5: drain to empty, then the die line, time reference, health, flush. Drawing 5 says "the die line ..., frames until the deadline, one more flush" | D:65; M:24 | MINOR |
| B10 | Item 6: "slot", "publish" are gone. M still uses them for the pool: "two slot pools", "a pool slot", "a pool has 8 slots", "a published frame" | D:75; M:189, M:291, M:309, M:130 | MINOR |
| B11 | Item 12: the drop record, its mutex and its two operations are not described in M | D:155-160; M (no hit for DropRecord, mutex) | NOTE |
| B12 | Item 14: the Create bounds (session dir 192, info JSON 8192, Create false) are not described in M | D:176; recorder.h:27-30; M (no hit) | NOTE |
| B13 | Item 12 makes a drop take a mutex. Drawing 1 and gate item 1 say the record path has "no lock" | D:157; M:20, M:206 | MINOR |

## C. Headers vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | M says the health is "nine values". RecorderHealth has ten fields | M:62; recorder.h:100-111 | MINOR |
| C2 | The health example line has no "truncated_lines" | M:228; record_file.h:115 | MINOR |
| C3 | The contract's example lines have no "fault" line | M:219-230; record_file.h:34,94-99 | MINOR |
| C4 | Drawing 5 says "a push after STOPPED: drop, count". The headers drop from STOPPING on | M:24; record_span.h:38-39; recorder_internal.h:23-24 | MINOR |
| C5 | Drawing 5's last-pass order | = B9 | = B9 |
| C6 | TOCTOU atomic pointer | = B5 | = B5 |
| C7 | IndexQueueFront (used by BufferPoolOldestFilledAt) is not described in M | index_queue.h:37-38; M (no hit) | NOTE |
| C8 | The queue kind byte QUEUED_SPAN and QUEUED_EVENT is not described in M | recording_thread.h:37-41; M (no hit) | NOTE |
| C9 | Section 11's health mapping lists lastWriteFailed, underReserve, pngNameClashes, droppedSpans, but not truncatedLines | M:419; recorder.h:88-89,105 | NOTE |
| C10 | The numbers checked and equal: 16 threads, 16,384 records, 8 KiB, 16 KiB, 31+1 fields, 8 and 24 buffers, 100 lines, 5 s, 40 and 5 minutes, 16 headers | M:7,20-23,196,215; headers | OK |

## D. recorder.md internal consistency

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | Section 4's heading says "P1 to P4 open". Its own rows mark P1 ("Lock it is") and P3 ("P3 - Good") closed | M:94 vs M:138-139 | MINOR |
| D2 | Fault line present vs absent | M:21, M:466 vs M:137, M:197; = B2 | = B2 |
| D3 | Allocation at Create vs at the first record | M:141, M:310 vs M:206, M:239, M:255; = B3-B5 | = B3 |
| D4 | Destroy waits then joins vs Destroy stores STOPPED | M:24, M:120 vs M:261; = B7 | = B7 |
| D5 | Drops after STOPPED vs after STOPPING | M:24 vs M:250; = C4 | = C4 |
| D6 | The queue holds "over six minutes" vs "about seven minutes". Both fit 409 s | M:272 vs M:267 | NOTE |
| D7 | Test 10 says "a queue made, a drop". The queues are made at Create | M:334 vs M:310 | NOTE |

## E. Header internal consistency

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | RecorderFlushInDie "returns ... at once when the state is not RUNNING". The next sentence says "Die during a Destroy: its deadline replaces Destroy's". The writer header says Die stores its deadline "unconditionally ... so Die wins". During a Destroy the state is STOPPING, so Die can never do either | recorder.h:59-61; record_writer.h:82-84; recorder_internal.h:25-27 | BLOCKING |
| E2 | The writer loads m_stopDeadline "once, at the die-line step". The drain loop before that step already runs "until ... the clock passes m_stopDeadline" | record_writer.h:85-86 vs record_writer.h:155-157 | MINOR |
| E3 | A failed frame-line append: step 6 has already dequeued the buffer. The work queue has no front-peek, so the buffer cannot "stay at the front". It returns to the free list only after its line is in the file. No rule says who holds it, so a dead disk takes the 8 buffers out of the pool | record_writer.h:136-144; buffer_pool.h:75-82 | BLOCKING |
| E4 | The last pass repeats steps 2 to 6, then the die line and step 8. Step 9 does not run: the drop records are not summed and no fault line is written before the final health line | record_writer.h:150-152 vs record_writer.h:155-161 | MINOR |
| E5 | The file order says "then the remaining frame lines until the deadline" after the last health line. The writer drains the frames before the die line | record_file.h:21-23 vs record_writer.h:155-159 | MINOR |
| E6 | DropRecordNote takes a RecordKind, and only QUEUED_SPAN and QUEUED_EVENT exist, yet it counts m_droppedFrames. The drop line has no frames key, and the entry has no m_droppedFramesReported | recording_thread.h:38-41,60,76,97-98; record_file.h:104-108 | MINOR |
| E7 | SpscRecordQueueCreate fills both endpoints at Create. RecordingThread has no SpscProducer member, so the producer endpoint has no home between Create and the claim | spsc_record_queue.h:34-43; recording_thread.h:92-100,108-111 | MINOR |
| E8 | "the one lock the producer ever meets there is the condition variable's". A drop takes the drop record's mutex | recording_thread.h:116-118 vs recording_thread.h:47-49,74-76 | MINOR |
| E9 | FieldText fails on "a text longer than TextLength". Its length parameter IS a TextLength, so no such text can be passed | record_field.h:83 vs record_field.h:95 | MINOR |
| E10 | "the file holds whole lines". A C line cut at the buffer end is "written as far as it got". The closing newline is unspecified | record_writer.h:64-65 vs record_writer.h:35-37,116 | MINOR |
| E11 | The PNG path is at most 192+1+63+1+31+4 = 292 bytes, past PathText's 256. No header names the type that holds it | record_file.h:16; recorder.h:28; record_frame.h:11-12; common_names.h:10 | NOTE |
| E12 | The pool's indexes are typed SlotIndex, SlotCount, SLOT_NONE, "slot indexes". Item 6 says "slot" is gone from the pool | index_queue.h:1,12-15; D:75 | NOTE |
| E13 | Includes, types, constants: every include resolves and every type is defined (gcc clean); no constant has two values | all 16 headers | OK |

## Count by severity (unique)

| severity | A | B | C | D | E | total |
|---|---|---|---|---|---|---|
| BLOCKING | 1 | 5 | 0 | 0 | 2 | 8 |
| MINOR | 8 | 6 | 4 | 1 | 8 | 27 |
| NOTE | 1 | 2 | 3 | 2 | 2 | 10 |
