# Recorder consistency check, round 4, checker 1 (2026-10-21)

**Verdict: NOT CONSISTENT: 48 findings: 1 BLOCKING, 22 MINOR, 25 NOTE.**
Each finding is counted once. A row that says "see X" repeats a finding from another table and is not counted again. OPEN P1, P2 and P3 are not findings.

Sources: the headers 00-util/*.h (6) and 01-recorder/*.h (10), plus 03-runtime/runtime_internal.h:78-88 for OsEvent. The document 01-recorder/recorder.md. The ledger docs/spec-harden2-cleanup.md:908-1064.
Mechanical checks:
- recorder_aggregate_for_review.md holds all 16 headers byte-identical (script diff, 16 of 16 SAME).
- gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on the 10 recorder headers: 0 errors, 0 warnings.
- Struct sizes measured with gcc: Recorder 1408, RecorderCounters 28, SpscRecordQueue 256 (head 64, tail 128, dropped 192). These match recorder.md:153, recorder.md:305 and RCD31.

## A. Document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | The line-buffer static_assert. The doc says "at least twice the record bound plus 1 KiB". The header asserts `6 * kRecordMaxRecordBytes + 4096` (RCD40). | recorder.md:212; record_writer.h:128, :42 | BLOCKING |
| A2 | A wrong-typed value in Python. The doc says "drop, count". The header says the tuple path has no type check: the value is written as its text and nothing raises. | recorder.md:205; record_field.h:86-89 | MINOR |
| A3 | When the frame line is written. The doc says "after the PNG landed". The header says after the PNG attempt, with ok true or ok false. | recorder.md:127; record_file.h:84-86, record_frame.h:22-25 | MINOR |
| A4 | The stall rule. The doc says it is "computed at read from the oldest ready slot". The header reads two atomics and never a slot. | recorder.md:265; record_writer.h:104-105, :116, :140-142 | MINOR |
| A5 | The lock on the record path. Gate item 1 says "No lock on the record path". RecordFrame, which is a record call, takes the free queue's lock and the ready queue's lock (the one-or-two-locks question is P1; whether a lock exists is not). | recorder.md:203; record_frame.h:20-22, frame_pool.h:49-51 | MINOR |
| A6 | SPAN_ASR ("asr") is never mentioned in the doc. Section 11 gives it no helper and no home. | record_span.h:20, record_file.h:43; recorder.md:433-453 | NOTE |
| A7 | The counters of a thread that got no queue are absent from the doc's current state. They appear only in history row D2, as "the thread table". | record_writer.h:95-96, :120-121; recorder.md:158 | NOTE |
| A8 | The index-queue functions and types are never named: IndexQueueCreate, IndexQueueDestroy, IndexQueuePush, IndexQueuePop, IndexQueueFront, SLOT_NONE, SlotIndex, SlotCount. | index_queue.h:12-38 | NOTE |
| A9 | The SPSC queue functions are never named: SpscRecordQueueCreate, SpscRecordQueueDestroy, SpscProducerPush, SpscProducerRecordsQueued, SpscProducerRecordsDropped, SpscConsumerFront, SpscConsumerPop. The doc says only "front ... pop". | spsc_record_queue.h:37-66; recorder.md:21 | NOTE |
| A10 | The C storage is never described: RecordSlot, RingPosition, ByteOffset, kCacheLineBytes, and kRingBytesPerRecordExpected = 64 (the byte area's size). | spsc_record_queue.h:70-113 | NOTE |
| A11 | The frame-pool lifecycle and types are never named: FramePoolCreate, FramePoolDestroy, FramePools, FramePoolsCreate, FramePoolsDestroy, FrameSlot, FolderName, FrameName. | frame_pool.h:28-93 | NOTE |
| A12 | kRecordFolderBytes = 64 and kRecordNameBytes = 32 are never given. The doc says only "length". | record_frame.h:10-13; recorder.md:163 | NOTE |
| A13 | The field types and makers are never named: FieldType, FieldValue, TextValue, FieldName, TextLength, FieldInt, FieldFloat, FieldBool, FieldText. The doc says "the makers". | record_field.h:11-94; recorder.md:238 | NOTE |
| A14 | Three values are never given: kWriterLineBytes 65536, kWriterExpectedPassesPerMinute 30, and WRITER_PNG_BYTES_PER_RAW_BYTE 0.45. The doc names only the PNG constant. | record_writer.h:42, :44, :52; recorder.md:431 | NOTE |
| A15 | RecordFileCreate, RecordFileWriteHeader and RecordFileClose are never named. | record_writer.h:71-77 | NOTE |
| A16 | ProducerPushEvent, QUEUED_SPAN, QUEUED_EVENT and kRecordQueueWatermark are never named. The doc says only "half full". | recording_thread.h:29, :35-38, :98 | NOTE |
| A17 | These types are described by role, never by name: RecorderHealth, RecorderState, struct Recorder, ThreadCount, ByteCount, FileDescriptor, LineText, DieReasonText, PathText, ThreadName, OsThread. | recorder.h:87; recorder_internal.h:29, :52; record_writer.h:27-31, :54-55 | NOTE |
| A18 | OsEventIsSet appears only as Python's is_set(). Drawing 3's code names list Set, Wait and Clear only. | runtime_internal.h:85, recording_thread.h:106; recorder.md:22, :237 | NOTE |

## B. Decisions vs headers (the latest ruling per subject)

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | PY1: "no check-then-act on shared state unless one side alone can run ... or a lock is held". RCD40: "so no counter has two writers (PY1)". m_droppedSpansWithoutQueue and m_droppedEventsWithoutQueue are written by every thread that got no queue, with no lock stated. | spec:1041, :1064; record_writer.h:95-96, :120-121 vs recorder.h:67-69 | MINOR |
| B2 | RCD40: "every thread counts its dropped frames in its own entry". The entry exists only after a RecordSpan or RecordEvent. A thread that only calls RecordFrame has no counter. | spec:1064; recording_thread.h:1-4, :40-41, :51-53 | MINOR |
| B3 | RCD19 item 4 moved the clock to monotonic_clock.h. recorder.h's top comment still says "its clock". | spec:1039; recorder.h:1 | NOTE |
| B4 | RCD1, PRF7: ambient, no handle, three contracts. | recorder.h:3; record_span.h:40, record_event.h:12, record_frame.h:27 | OK |
| B5 | RCD5, RCD19 T1: FrameSize and FrameView live in frame_types.h; util has monotonic_clock.h and common_names.h. | frame_types.h:9-25; monotonic_clock.h:9-12; common_names.h:10-14 | OK |
| B6 | RCD4, RCD19 item 7, RCD34 B1: no sample and no GPU record. | record_span.h:16-33 (15 stages, no GPU) | OK |
| B7 | RCD6, RCD27: the writer sleeps on a condition variable with a remembered notify, with a 5 s timer, and does not poll. | record_writer.h:23-28, :49, :145; runtime_internal.h:78-86 | OK |
| B8 | RCD7: the mask limit per pass comes from config. | frame_pool.h:20-25 | OK |
| B9 | RCD9: typed SPSC endpoints; head, tail and the drop count each on its own line; the pool is two index queues. | spsc_record_queue.h:26-32, :110-112; frame_pool.h:56-61 | OK |
| B10 | RCD11 (survivors): the makers, the watermark wake, the time reference at every fsync, the drop gap. | record_field.h:91-94; recording_thread.h:105-107; record_writer.h:158; recording_thread.h:43-47 | OK |
| B11 | RCD12: the cut rule on text fields; the last pass is the normal pass with the die line; no cached indexes; one snapshot per pass. | record_field.h:84-86; record_writer.h:146, :166-169; spsc_record_queue.h:95-97 | OK |
| B12 | RCD16: LINE_KIND_NAMES, SPAN_STAGE_NAMES, the open flags, EVENT_KEY_FIELDS, unusedCtx. | record_file.h:14-17, :38-45, :82; recorder.h:52 | OK |
| B13 | RCD17, RCD37: 31 caller fields plus 1. | record_field.h:24-25 | OK |
| B14 | RCD20 (K1): names are string literals; no registration. | record_field.h:1-3, :11; record_event.h:9 | OK |
| B15 | PY3 (Q1): a deque of tuples (stage, start, end, names, values). | spsc_record_queue.h:5-6; record_field.h:80-82; record_span.h:35-36 | OK |
| B16 | RCD21, RCD22, RCD23: actor headers, the names, and the C ring of slots plus a byte area. The thread table is folded into the Writer. | recorder_internal.h:1-8; spsc_record_queue.h:78-113; record_writer.h:117-119 | OK |
| B17 | RCD25 (W1): the 64-line retry queue, step 7, a full queue dropped and counted. | record_writer.h:43, :92-95, :123-125, :154 | OK |
| B18 | RCD27: "the slot pool is MPSC under one lock". The headers use two locks. | frame_pool.h:49-51 | OPEN P1 |
| B19 | RCD30: drawing 2's loop goes into step 2 (yes) and step 1 (no). The header always returns to step 1. | record_writer.h:162-165 | OPEN P3 |
| B20 | TEL2: "one event" per fault. The writer never records. | record_writer.h:1-5 | OPEN P2 |
| B21 | RCD31, FB8: the counters are unpadded and the comment states the rates. | recorder_internal.h:36-49 (28 bytes measured) | OK |
| B22 | RCD34: B1 no GPU; B2 dropped and counted outside RUNNING; A1 asr_clips. | recorder_internal.h:20-22; record_span.h:38-39; recorder.h:26-28, :46-47 | OK |
| B23 | RCD35: 16384 entries; RecordResult returned by the three calls. | recording_thread.h:28; record_field.h:72-78 | OK |
| B24 | RCD36, RCD37: an 8192-byte bound; "cut" (the bytes lost) appears only on a cut record. | record_field.h:26, :29-31 | OK |
| B25 | RCD38 (not superseded by later rows): infoJson; WriteHeader takes the frame; Destroy stores STOPPED; the name lives in ThreadProducer; the Reported counts; two queueless counts; PNG level 1. | recorder.h:39, :44; record_writer.h:73, :120-121; recording_thread.h:65-66, :78; record_frame.h:1-2 | OK |
| B26 | RCD39: always back to step 1; the leftovers are counted; the publish CAS from 0; OsEventIsSet; Create needs a joined writer; two-name folders; ok false; NOT_CREATED counts nowhere; the index queue's Python form. | record_writer.h:162-172; record_frame.h:17, :25-26; runtime_internal.h:85; recorder.h:32-35; record_file.h:84-85; record_field.h:70-71; index_queue.h:4-5 | OK (E5 covers the CAS) |
| B27 | RCD40: 64 KiB with an assert at six times plus 4 KiB; the leftovers popped; the end-of-pass CAS; the Python lock; Create resets the stopped flag and the die reason; the pid; no type check on the tuple path. | record_writer.h:42, :128, :87-89, :169-172; recorder.h:35; record_field.h:86-89 | OK (see E1, E5) |
| B28 | PRF5, RCD19 item 2, RVW4: the cap is the design's count, 16, from config and never nproc; a 17th thread dies. | recording_thread.h:20-22, :27 | OK |
| B29 | GIL2: the recorder creates no thread except the writer. | recording_thread.h:1-3, :21 | OK |
| B30 | TEL5, TEL16: lossless PNG level 1 at the source's size. | record_frame.h:1-2; frame_types.h:8 | OK |
| B31 | TEL7: full queues and pools drop and count. | spsc_record_queue.h:46; frame_pool.h:68 | OK |
| B32 | TEL10: the stall rule is computed at read. | record_writer.h:140-142 | OK (see E10) |
| B33 | TEL13, TEL17: the 40-minute start reserve; the 5-minute frame reserve; W x H x 3 x 0.45 x 30 x minutes. | recorder.h:31-32; record_writer.h:44-46, :52; recorder_internal.h:62-64 | OK |
| B34 | RUN3: RecorderFlushInDie fits DieActionFn. | recorder.h:50-52; runtime.h:18 | OK |
| B35 | Superseded, or about the doc only, with no header duty: RCD2, RCD3, RCD8, RCD10, RCD13 to RCD15, RCD18, RCD24, RCD26, RCD28, RCD29, RCD32, RCD33, PY2, PRF2 to PRF4, PRF6, TEL1, TEL3, TEL4, REV7, REV8. | spec:920-1061 | n/a |

## C. Decisions vs document

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | REV8 requires a cause before any mechanism. The PNG-clash row cites "DESIGNED (D10: a pass number reused after a re-Create in the same folder)". A re-Create in the same folder fails with EEXIST, so the cited cause cannot occur. | spec:1014; recorder.md:274 vs :273, recorder.h:32-34 | MINOR |
| C2 | RCD40's assert: six times plus 4 KiB. The doc says twice plus 1 KiB (RCD38's form). | see A1 | - |
| C3 | RCD40: "the tuple path has no type check and nothing raises". The doc says drop and count. | see A2 | - |
| C4 | RCD39: "the frame line carries ok false after a failed write". The doc says "after the PNG landed". | see A3 | - |
| C5 | PY1. The doc says "never a shared += (PY1)", but the queueless counters are shared. | recorder.md:241; see B1 | - |
| C6 | RCD27, TEL2, RCD30 against the doc. | recorder.md:134-136 | OPEN P1, P2, P3 |
| C7 | Checked with no contradiction: RCD1, RCD2 (superseded by RCD5), RCD19, RCD20, RCD25, RCD31, RCD34, RCD35, RCD36, RCD37, PRF5, PRF7, PY3, GIL2, TEL13, TEL16, TEL17, RVW3, RVW4, RUN3. | recorder.md:96-136, :186-195, :412-464 | OK |

## D. Internal consistency of the document

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | The heading says "all four closed". The same section holds three OPEN items, P1, P2 and P3. | recorder.md:93 vs :134-136 | MINOR |
| D2 | The doc says "each is a decision, not a drift". Three rows of that table are OPEN. | recorder.md:115 vs :134-136 | NOTE |
| D3 | The doc says the 17th-thread die is "a change against TEL2, in section 4's table". Section 4's table has no such row; the row is in the failure matrix. | recorder.md:204 vs :116-136, :275 | MINOR |
| D4 | The failure matrix has two rows for the 17th recording thread. | recorder.md:275, :276 | NOTE |
| D5 | The doc says a helper "builds no text". Instance 2's helper builds an f-string name and boxes_json(reply). | recorder.md:91 vs :78-80 | MINOR |
| D6 | A wrong-typed value: "drop, count" in one place; "written as its text" and "never raises" in others. | recorder.md:205 vs :327, :238; see A2 | - |
| D7 | The stall rule: "a frame waited ... past the last progress", "a READY slot older than 5 s past ...", and "from the oldest ready slot" against "never a slot". | recorder.md:25, :133, :265 vs :161; see A4 | - |
| D8 | The frame line: "after the PNG landed" against "the frame line carries ok false". | recorder.md:127 vs :274; see A3 | - |
| D9 | "No lock on the record path" against pools under locks. | recorder.md:203 vs :240, :306; see A5 | - |
| D10 | Checked and consistent: thread cap 16; queue 16,384; pools 8 and 24; wake by 4 sources with a 5 s timer; the file name; retry 64 lines; "cut" = the bytes lost; 9 steps and back to step 1; the session folder (app), asr_clips (Create); drop totals per thread entry; sizes 1408 and 256. | recorder.md:20-27, :121, :132, :264-269, :296, :305, :458, :464 | OK |

## E. Internal consistency of the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | The comment says "eight times the bound always fits (the static_assert below)". The assert checks six times plus 4096. | record_writer.h:36-37 vs :128 | MINOR |
| E2 | "A line always fits" is unproven. The C record carries name pointers, so the 8 KiB bound does not count the printed names. infoJson has no bound at all. | record_writer.h:33-37, :131; record_field.h:2-3, :16-17; recorder.h:29-30 | MINOR |
| E3 | WriterFormatRecord is called "the only place text is made". RecordFileWriteHeader also makes lines, and so do the writer's thread, drop, frame, health and die lines. | record_writer.h:130-131 vs :73, :147-158 | MINOR |
| E4 | A retry slot is a bare LineText that keeps no length. RecordFileAppendLine needs one. | record_writer.h:92-95, :123 vs :75 | MINOR |
| E5 | The end-of-pass oldest-ready CAS gives no new value. Suppose a publish lands during the pass: the value is nonzero, so its CAS from 0 fails. A store of 0 at the end of the pass then erases it. This contradicts "never erased". | record_writer.h:85-88; record_frame.h:25-26 | MINOR |
| E6 | Every queueless thread writes the two queueless counters. This contradicts "no counter has two writers". | see B1 | - |
| E7 | A frame-only thread has no entry for its dropped frames. | see B2 | - |
| E8 | The makers return RecordField, but the comment says they "return INVALID_ARG" and count a drop. | record_field.h:91-94 vs :89-90 | MINOR |
| E9 | m_dieReason is a plain char array. FlushInDie writes it while the writer may be in a last pass that Destroy started, and reading it. No ordering is stated. | record_writer.h:81-83, :114, :166-167 | MINOR |
| E10 | The stall rule is stated two ways: "older than WRITER_STALL_NS with no writer progress" and "waited over WRITER_STALL_NS past the writer's last progress". | recorder.h:80 vs record_writer.h:140-141 | MINOR |
| E11 | Die after Destroy is unstated. "Destroy or FlushInDie stores STOPPING (idempotent)" would turn STOPPED back into STOPPING. The runtime has no way to remove a flush. | recorder_internal.h:22-25; runtime.h:29 | MINOR |
| E12 | A re-Create resets the flags, the deadline and the die reason. It does not reset RecorderCounters or the threads' drop counts. The writer stores sums each pass, so a new session starts at the old totals. | recorder.h:34-35; recorder_internal.h:27-28; record_writer.h:161-162 | MINOR |
| E13 | The counter that receives the leftover drops is unstated. In RecorderCounters, the next sum overwrites them. In the thread's entry, there is a second writer while threads still push during Die. | record_writer.h:169-172; recording_thread.h:51-53 | MINOR |
| E14 | The last health line comes before the deadline frame loop and the leftover counts. The file never carries those drops. | record_writer.h:167-172; record_file.h:21-23 | NOTE |
| E15 | m_firstDropAt restarts at the first drop after a successful push. A drop line covering two episodes shows only the later "from". This contradicts "since its last drop line, and when". | recording_thread.h:43-47 vs record_file.h:92 | MINOR |
| E16 | OsLock is called "the runtime's mutex (runtime_internal.h)". runtime_internal.h declares the type and no operations. | index_queue.h:17; runtime_internal.h:88 | NOTE |
| E17 | The comments say the publish wakes the writer and does the stamp CAS. FramePoolPublishSlot(pool, slot) has no writer or event argument, so the actor is unstated. | frame_pool.h:3-4, :69-70; record_frame.h:25-26 | NOTE |
| E18 | Whether NO_FRAME_POOLS is counted is unstated. The comment lists only DROPPED, INVALID_ARG and NOT_CREATED. | record_field.h:69-71 | NOTE |
| E19 | How a thread claims its index in m_queues, and who fills m_queueEnds[i] with which ordering, is unstated. | record_writer.h:90-91, :117-119; recording_thread.h:40-43 | NOTE |
| E20 | The comment says "copied into the run". No run exists since RCD23. | record_field.h:45 | NOTE |
| E21 | A comment wrap is broken: "A / record is never refused for its / text". | record_field.h:83-86 | NOTE |
| E22 | Compiled alone, fixed_text.h gives a -Wpedantic "empty translation unit" warning. The doc claims gcc is clean on all sixteen. | 00-util/fixed_text.h:11; recorder.md:212 | NOTE |
| E23 | A processName over 31 bytes, which overflows ProcessName, is not among Create's false cases. | common_names.h:11; recorder.h:30-32, :38 | NOTE |
| E24 | The clock's home is stale in recorder.h's top comment. | see B3 | - |
| E25 | gcc on the 10 recorder headers is clean. Every include resolves. No constant has two values. Each flag is cleared in step 1. | record_writer.h:145 | OK |
