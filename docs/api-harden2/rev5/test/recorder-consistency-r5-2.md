# Recorder consistency check, round 5, reader 2 (2026-10-22)

**Verdict: NOT CONSISTENT. 47 findings: 5 BLOCKING, 26 MINOR, 16 NOTE.**

Abbreviations. DEC = docs/api-harden2/rev5/test/recorder-decisions-2026-10-21.md. MD = 01-recorder/recorder.md. Header paths are relative to docs/api-harden2/rev5/modules/. A row marked "=Xn" repeats a finding counted under Xn; it is not counted again. OK rows are not findings.

Sources read: DEC (210 lines); the 6 util headers; the 10 recorder headers; runtime_internal.h:76-88 (OsEvent); MD (466 lines); ledger rows RCD40-RCD56, PY1-PY3, TEL2/7/10/11/13/17, RVW3/4, PRF4/5. The aggregate's 16 code blocks were diffed against the 16 headers: all 16 are identical.

## A. Decision document against the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | item 1, the index queue uses a lock: done | DEC:39-41; 00-util/index_queue.h:1-5,17,24; 01-recorder/buffer_pool.h:55-58 | OK |
| A2 | item 2, one return arrow, reset in step 1: done | DEC:45; record_writer.h:132,153-154 | OK |
| A3 | item 3, a call before Create returns NOT_CREATED and counts nowhere: done | DEC:49; record_field.h:70-72; recorder_internal.h:22-23 | OK |
| A4 | item 4, C line buffer 16 KiB, cut at its end, counted: done | DEC:57; record_writer.h:34-46,53,56,116; recorder.h:88-89; record_file.h:115 | OK |
| A5 | item 5, drain to empty, then die line, time ref, health, flush: done in the writer. But record_file.h puts "the remaining frame lines until the deadline" AFTER the health line | DEC:65; record_writer.h:155-161 against record_file.h:21-23 | MINOR |
| A6 | item 5, Die's flush step waits for the drain. FlushInDie "returns at once when the state is not RUNNING", so a Die during a Destroy (STOPPING) does not wait for the drain | DEC:65-67; recorder.h:59-61 | MINOR |
| A7 | item 6, the names BufferPool, m_freeList, m_workQueue, m_buffers, the 5 operations, m_framePool, m_maskPool, the scheme in the first comment: done | DEC:75; buffer_pool.h:1-10,63-68,75-88,98-103 | OK |
| A8 | item 6, "slot ... gone": the util index queue still names "slot indexes", SlotIndex, SlotCount, SLOT_NONE | DEC:75; index_queue.h:1,12-15,25-38 | NOTE |
| A9 | item 6, "No field is shared": m_lastProgressAt is an atomic the writer stores and the main thread reads for the stall; record_writer.h:90 says "The stall question has no field here". DEC itself needs it ("5 s past the writer's last finished buffer") | DEC:77,81; record_writer.h:88-91,108,126-129; recorder.h:92-94 | MINOR |
| A10 | item 7 says a plain "+= 1"; item 12 (later) puts the count under a mutex. Headers follow 12. DEC states both as current | DEC:94 vs DEC:157; recording_thread.h:74-76 | NOTE |
| A11 | item 8, everything at Create, claim by index, 17th dies: done | DEC:100; recording_thread.h:3-8; recorder_internal.h:53-64; recorder.h:32-33 | OK |
| A12 | item 9, STOPPING by one internal function under the state lock / CAS: done | DEC:106,110-116; recorder_internal.h:24-28 | OK |
| A13 | item 10: DEC says the release/acquire pair is on the stop request; the header puts it on m_stopDeadline. DEC heading says "PROPOSED" while the status block and table say "DECIDED" | DEC:9,121,125,209; record_writer.h:82-87 | NOTE |
| A14 | item 11, a failed append leaves the record at the front: done for queues. For a frame line it cannot hold: see E1 | DEC:151; record_writer.h:136-144 | =E1 |
| A15 | item 12, the drop record: DEC has one count and "copies the three values"; the header has three counts by kind and copies "the five values" | DEC:155,158; recording_thread.h:56-78 | MINOR |
| A16 | item 13, maker returns bool, out unchanged, FIELD_INVALID gone: done. But the header says the stopped helper's call "returns INVALID_ARG, counted in the thread's drop record"; DEC says the helper stops and returns the code. A helper that stops makes no record call and cannot reach the drop record | DEC:166-170; record_field.h:81-95 | MINOR |
| A17 | item 14, explicit bounds: session dir and info JSON checked. processName (ProcessName, 32 bytes) has no length check in Create's false list | DEC:176; recorder.h:25-30,39-45; common_names.h:11 | MINOR |
| A18 | item 15, one Create, a second returns false, Destroy false stores nothing, daemon: done | DEC:184-186; recorder.h:32,39,50-55; record_writer.h:162-165 | OK |
| A19 | item 16, OsEventIsSet before set: done | DEC:190; recording_thread.h:137-140; 03-runtime/runtime_internal.h:85 | OK |
| A20 | T1, fault line per changed counter: done. FAULT_KEY_COUNT "count" also holds a flag's new value (under_reserve) | DEC:194; record_file.h:34,94-99; record_writer.h:150-152 | NOTE |
| A21 | T2 and item 11 "what goes": no retry queue, RetryLine, step 7 or reader rule in any header | DEC:149,198; grep over 16 headers | OK |

## B. Decision document against recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | item 8: MD says "the thread's entry and queue are made at its first record" | DEC:100; MD:206 | BLOCKING |
| B2 | item 8: MD's Python thread table is "a list, appended last"; MD's C entry is "an atomic pointer, stored last with release, NULL until then". The headers have inline entries and mb_claimed | DEC:100-102; MD:239,255; recording_thread.h:84-96 | BLOCKING |
| B3 | item 12: MD's drop gap is lock-free ("the producer stores first, last, then the count with release; the writer loads the count with acquire"). It is the only description of the drop record in MD | DEC:155-160; MD:260 | BLOCKING |
| B4 | item 15: MD says STOPPED has two writers, "the writer ... or Destroy past its deadline, and Create then needs a joined writer" | DEC:184-186; MD:261 | BLOCKING |
| B5 | T1 closed: MD says "no event ... the health line and the chat line carry the fault", "OPEN P2" | DEC:194; MD:137,197 | MINOR |
| B6 | item 3 closed: MD still says "OPEN P4"; the section 4 heading says "P1 to P4 open" | DEC:11,49; MD:94,136,250 | MINOR |
| B7 | item 5: MD drawing 5 orders "the die line ..., frames until the deadline, one more flush" (frames after the die line). MD nowhere states the drain to empty | DEC:65; MD:24 | MINOR |
| B8 | item 6 "slot, publish ... gone": MD uses "a published frame", "two slot pools", "a pool slot", "8 slots" | DEC:75; MD:130,189,291,309 | MINOR |
| B9 | item 4: the truncated-line counter is absent from MD's health (see C1, C2) | DEC:57; MD:62,228 | =C1,C2 |
| B10 | item 14: the session-dir and info-JSON bounds are not in MD | DEC:176; MD (no match) | =C13 |
| B11 | items 1, 2, 7, 9, 10, 11, 13, 16: MD matches | MD:138,139,244,261(first clause),24,129,267,337,329,240 | OK |

## C. Headers against recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | MD "nine values"; RecorderHealth has 10 fields | MD:62; recorder.h:100-111 | MINOR |
| C2 | MD's health line lacks "truncated_lines" | MD:228; record_file.h:115 | MINOR |
| C3 | MD's contract lines ("the lines below") have no fault line; the fault keys at, what, count are described nowhere in MD | MD:212,220-230; record_file.h:34,94-99 | NOTE |
| C4 | MD: "a record pushed after the writer's final drain is added to the dropped counts by the writer after its last pass". No such step in the header | MD:250; record_writer.h:155-165 | MINOR |
| C5 | MD: "the queues stay in memory" after the last drain; header: "so the queues and the pools are empty" | MD:121; record_writer.h:159-161 | MINOR |
| C6 | MD drawing 6: "atomic counters and flags ... no lock"; the drop counts live in DropRecord under a mutex | MD:25; recording_thread.h:47-63 | MINOR |
| C7 | MD drawing 5 order against the writer's order | MD:24; record_writer.h:155-161 | =B7 |
| C8 | MD TOCTOU entry "atomic pointer" against mb_claimed | MD:255; recording_thread.h:84-96 | =B2 |
| C9 | MD drop gap form against DropRecordNote/Take | MD:260; recording_thread.h:74-78 | =B3 |
| C10 | MD STOPPED by Destroy against "stores nothing" | MD:261; recorder.h:50-52; recorder_internal.h:27-28 | =B4 |
| C11 | MD names DropRecord, DropRecordNote, DropRecordTake, DropGap nowhere | recording_thread.h:45-78 | NOTE |
| C12 | MD names m_truncatedLines / kWriterLineBytes nowhere (only "16 KiB" at 215) | recorder.h:88-89; record_writer.h:42 | =C1,C2 |
| C13 | MD names kRecorderSessionDirBytes 192, kRecorderInfoJsonBytes 8192 and their Create checks nowhere | recorder.h:25-42 | NOTE |
| C14 | MD names kRecordFolderBytes 64, kRecordNameBytes 32 nowhere | record_frame.h:10-13 | NOTE |
| C15 | MD names the queue's own drop count (SpscProducerRecordsDropped, m_dropped) nowhere; it duplicates the DropRecord count | spsc_record_queue.h:46,55,102,112 | NOTE |
| C16 | MD names checked and found in headers with the same value: OsEventSet/Wait/Clear, WriterRun, WriterFormatRecord, RecordFileAppendLine, RecordFileFlushToDisk, WriterIsStalled, RecorderCounters, the 5 BufferPool operations, ProducerForThisThread, ProducerPushSpan, ProducerWakeWriterIfHalfFull, RecorderReserveBytes, WRITER_PNG_BYTES_PER_RAW_BYTE, kRecordingThreadsMax 16, 16,384, 8 KiB, 31 fields, 15 stages, 8/24 buffers, 100 lines, 5 s, 40/5 min, 16 KiB, sixteen headers | MD:7,21-25,133,215,326-328,425,431,433 | OK |
| C17 | (moved to E20) gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on the 10 recorder headers: 0 FAIL, 0 warnings | 01-recorder/*.h | OK |

## D. recorder.md against itself

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | entry "made at its first record" against "allocated at Create" | MD:206 vs MD:141,310 | =B1 |
| D2 | thread table "appended" / "atomic pointer" against "claims the next entry ... an index" | MD:239,255 vs MD:310 | =B2 |
| D3 | "no event ... OPEN P2" against "a fault line per changed counter" | MD:137,197 vs MD:21,466 | =B5 |
| D4 | "OPEN P4", "P1 to P4 open" against "a no-op (NOT_CREATED)" and P1, P3 ruled | MD:94,136,250 vs MD:138,139,420 | =B6 |
| D5 | drawing 5 (frames after the die line) against test 10 (die, time ref, health last) | MD:24 vs MD:334 | =B7 |
| D6 | "slot"/"published" against the buffer-pool terms | MD:130,189,291,309 vs MD:23,127,308 | =B8 |
| D7 | test 21 "a second Create on the same file name fails (O_EXCL)" and "O_EXCL guards ... a re-Create by the same process" against one Create per process: a second Create returns false before any open | MD:276,345 vs MD:346; recorder.h:32,39 | MINOR |
| D8 | label T1 = "RCD19's util headers" in MD; T1 = the fault line in DEC | MD:410; DEC:192 | NOTE |
| D9 | no test pins the decided items: drain to empty (5), the fault line (T1), the pool's stall answer (6), the C cut count (4), the Create bounds (14) | MD:323-348 | NOTE |

## E. Headers against themselves

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | a failed frame-line append: the buffer is already dequeued (no peek on the work queue), the PNG is already on disk (exclusive create clashes on retry), and the Writer has no field to hold it. "The record stays at the front" cannot apply; the buffer leaks off both queues and the stall check stops seeing it | record_writer.h:136-144,102-111; buffer_pool.h:77-88; record_file.h:23-24 | BLOCKING |
| E3 | the last-pass order: record_file.h puts frame lines after the health line; record_writer.h drains frames (step 6) before the die line | record_file.h:21-23 vs record_writer.h:155-161 | =A5 |
| E4 | DropRecordNote takes a RecordKind; only QUEUED_SPAN and QUEUED_EVENT exist, so a frame drop has no kind | recording_thread.h:37-41,74-76; record_frame.h:27-28 | MINOR |
| E5 | DropGap carries m_droppedFrames, but the drop line has no frames key and the entry has no frames-reported count; a frame-only gap has no defined line | recording_thread.h:65-72,89-98; record_file.h:101-108; record_writer.h:139 | MINOR |
| E6 | the deadline is loaded "once, at the die-line step", but the drain loop before that step is bounded by it | record_writer.h:85-87 vs record_writer.h:155-157 | MINOR |
| E7 | BufferPoolOldestFilledAt reads the front's m_filledAt "under the work queue's lock"; IndexQueueFront takes and drops the lock inside, so the front index and its fill time cannot be read under one hold through the declared API | buffer_pool.h:84-88; index_queue.h:35-38 | MINOR |
| E8 | OsLock is "the runtime's mutex (runtime_internal.h)", but runtime_internal.h declares only the opaque type, no lock or unlock | index_queue.h:17; recording_thread.h:43; 03-runtime/runtime_internal.h:88 | MINOR |
| E9 | "the one lock the producer ever meets there is the condition variable's"; DropRecordNote takes the drop record's lock on every drop | recording_thread.h:115-118 vs recording_thread.h:47-49,74-76; MD:206 | MINOR |
| E10 | Die during a Destroy: if the writer loaded Destroy's deadline, it may read m_dieReason (a plain 256-byte array) while Die writes it; no ordering covers that read | record_writer.h:82-87,97-98,107,159; recorder.h:59-61 | MINOR |
| E11 | "pass" names two things: the writer's loop iteration and the vision pass rate in kWriterExpectedPassesPerMinute (used by the reserve) | record_writer.h:43,131 vs recorder_internal.h:70-72 | MINOR |
| E12 | buffer_pool.h: the pools are "destroyed at Destroy"; a Destroy past its timeout leaves the writer running and "stores nothing"; whether it frees the pools under a live writer is unstated | buffer_pool.h:9-10; recorder.h:50-52; record_writer.h:163-165 | MINOR |
| E13 | a push between the writer's final empty check and the STOPPED store stays in its queue, never written and never counted (the state was loaded as RUNNING) | record_writer.h:159-161; record_span.h:38-39; recorder_internal.h:22-24 | MINOR |
| E14 | m_claimedCount: "a value past kRecordingThreadsMax dies"; the 17th claim gets index 16, equal to the max, not past it | recorder_internal.h:55-57; recording_thread.h:30 | NOTE |
| E15 | the last pass runs "step 8 unconditionally, one more flush"; step 8 already ends with the flush | record_writer.h:148-149,159 | NOTE |
| E16 | recorder.h (public) refers to bytes(kWriterFlightMinutes), defined in record_writer.h (internal), which it does not include | recorder.h:41-42; record_writer.h:44 | NOTE |
| E17 | with a dead disk, the last pass repeats steps 2 to 6 with failing appends until the deadline; whether step 6 runs after a step-4 failure inside that loop is unstated | record_writer.h:136-138,155-157 | NOTE |
| E18 | the PNG path: 192 + 1 + 63 + 1 + 31 + 4 = 292 bytes, over PathText 256; no type or bound names the PNG path buffer | recorder.h:28; record_frame.h:10-13; record_file.h:16; common_names.h:10 | NOTE |
| E19 | removed names: no FramePool, ready queue, retry queue, RetryLine, FIELD_INVALID, lazy allocation, second Create, abandoned writer or shared stall-time field in any header. "slot" survives only in the util index queue (=A8) and in the SPSC ring's RecordSlot (a current mechanism) | grep over 16 headers | OK |
| E20 | gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on the 10 recorder headers (with -I 00-util and 01-recorder): 0 FAIL, 0 warnings; the aggregate equals the 16 headers byte for byte | 01-recorder/*.h; recorder_aggregate_for_review.md | OK |

## Counts

| severity | rows |
|---|---|
| BLOCKING (5) | E1, B1, B2, B3, B4 |
| MINOR (26) | A5, A6, A9, A15, A16, A17, B5, B6, B7, B8, C1, C2, C4, C5, C6, D7, E4, E5, E6, E7, E8, E9, E10, E11, E12, E13 |
| NOTE (16) | A8, A10, A13, A20, C3, C11, C13, C14, C15, D8, D9, E14, E15, E16, E17, E18 |
