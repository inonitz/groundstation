# Recorder consistency check, round 4, checker 3 (2026-10-21)

**Verdict: NOT CONSISTENT: 2 BLOCKING, 21 MINOR, 22 NOTE** (45 findings; each defect is counted once, in the first table that holds it; a row marked "= Xn" is a cross-reference and is not counted; OPEN P1, P2, P3 are not findings).

Sources: the 16 headers (00-util 6, 01-recorder 10), runtime_internal.h, runtime.h:18, recorder.md (464 lines), docs/spec-harden2-cleanup.md. The aggregate matches all 16 headers byte for byte (script check). gcc run: 10 of 10 01-recorder headers pass with no warning. Measured with gcc: struct Recorder 1408 B; SpscRecordQueue 256 B, head/tail/drop at 64/128/192; RecorderCounters 28 B.

Abbreviations: md = 01-recorder/recorder.md; ledger = docs/spec-harden2-cleanup.md; header paths are relative to rev5/modules.

## A. Document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | Test 5: "a maker given a bad value returns INVALID_ARG and counts a drop". The makers return a RecordField. They have no result code and no thread entry to count in. This follows the header comment that E1 flags. | md:327; record_field.h:91-94 | MINOR |
| A2 | The line buffer: the document says "at least twice the record bound plus 1 KiB". The static_assert checks 6 x bound + 4096. The document never states kWriterLineBytes = 65536. | md:212; record_writer.h:42,128 | MINOR |
| A3 | The document (gate item 3) says "A wrong-typed value in Python: drop, count, no try". The header says the tuple path has no type check and writes any other value as its text. | md:205; record_field.h:86-89 | BLOCKING |
| A4 | TOCTOU: "RUNNING records, anything else drops and counts". The headers say NOT_CREATED returns NOT_CREATED and counts nothing. | md:247; record_field.h:69-71; recorder_internal.h:20-21 | MINOR |
| A5 | The document says the writer thread is the only one that touches the file. In fact RecorderCreate, on the caller's thread, creates the file and writes the time reference and info lines. | md:33, md:208; recorder.h:28-29; record_writer.h:59-61,72-73 | MINOR |
| A6 | PNG name clash cause: "a pass number reused after a re-Create in the same folder". The headers make a re-Create in the same folder fail with EEXIST, so this cause cannot happen. | md:274; recorder.h:33-34; md:273 | MINOR |
| A7 | Drawing 3: the writer "passes, checks the flag again". The header says "nothing is checked at the end of a pass". | md:22; record_writer.h:165 | NOTE |
| A8 | Functions the document never names or describes: IndexQueueCreate/Destroy/Push/Pop/Front; SpscRecordQueueCreate/Destroy, SpscProducerPush, SpscProducerRecordsQueued/Dropped, SpscConsumerFront/Pop; FramePoolCreate/Destroy, FramePoolsCreate/Destroy; RecordFileCreate, RecordFileWriteHeader, RecordFileClose; ProducerPushEvent; FieldInt/Float/Bool/Text (only "the makers"). | index_queue.h:32-38; spsc_record_queue.h:37-66; frame_pool.h:64-93; record_writer.h:71-77; recording_thread.h:98; record_field.h:91-94 | NOTE |
| A9 | Types the document never names: RecordSlot, RingPosition, ByteOffset, RecordBytes, RecordKind, SlotIndex, SlotCount, FrameSlot, FolderName, FrameName, LineText, DieReasonText, FileDescriptor, ByteCount, PathText, ProcessName, ThreadName, ThreadCount, RecordCount, FieldName, FieldCount, FieldType, FieldValue, TextValue, TextLength, RecordField, RecordTopic, LineKind, RecorderState, RecorderHealth, OsLock, OsThread. | all 16 headers | NOTE |
| A10 | Values the document never states: kRecordFolderBytes 64; kRecordNameBytes 32; kRingBytesPerRecordExpected 64; kCacheLineBytes; PathText 256, ProcessName 32, ThreadName 32; kWriterExpectedPassesPerMinute 30; WRITER_PNG_BYTES_PER_RAW_BYTE 0.45 (named at md:431, value absent); QUEUED_SPAN/QUEUED_EVENT; SLOT_NONE. | record_frame.h:11-12; spsc_record_queue.h:74-75; common_names.h:10-12; record_writer.h:44,52; recording_thread.h:36-37; index_queue.h:15 | NOTE |
| A11 | Members the current-state sections never describe: m_droppedSpansWithoutQueue/m_droppedEventsWithoutQueue (only in the history row md:158-159); mb_queueTried and mb_dropping (only in history D4). | record_writer.h:120-121; recording_thread.h:79-80 | NOTE |
| A12 | Who makes a PNG's folder (the writer, before the PNG) is not in the document. Its only folder rules cover the session folder (the app) and asr_clips (Create). | record_file.h:16; record_writer.h:150; md:29-30, md:458 | NOTE |
| A13 | Three mechanisms from RCD39/RCD40 that the document never describes: Create's resets of the stopped flag and the die reason; the writer releasing leftover ready slots into dropped frames; the publish's compare-and-swap from 0 on the oldest-ready stamp. | recorder.h:34-35; record_writer.h:171-172; record_frame.h:25-26 | NOTE |

## B. Decisions vs headers (latest ruling)

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | RCD34 B2: "a record in any state but RUNNING is dropped and counted". The header says "NOT_CREATED counts nowhere". RCD39, an agent fix pass, changed it, and the document does not mark it OPEN (md:134-136). | ledger:1058,1063; record_field.h:70-71 | MINOR |
| B2 | TEL3 (2): "fsync the trace handle only, never the PNGs". No header says whether a PNG is fsynced. MISSING. | ledger:962; record_file.h:17; record_writer.h:150-153 | NOTE |
| B3 | PY1: "no check-then-act on shared state unless one side alone can run ... or a lock is held". Implemented: index_queue.h:4-5; record_writer.h:88-89. Violated by the queueless counters (= E6) and Destroy's compare-and-swap (= E10). | ledger:1041 | = E6, E10 |
| B4 | RCD40: "every thread counts its dropped frames in its own entry". Only threads that call RecordSpan or RecordEvent get an entry (= E5). | ledger:1064; recording_thread.h:1-4,51-53 | = E5 |
| B5 | RCD40: "the static_assert at six times the record bound plus 4 KiB". The static_assert is right; its comment says eight times (= E2). | ledger:1064; record_writer.h:36-37,128 | = E2 |
| B6 | RCD27: "the slot pool is MPSC under one lock". The header has two locks. | ledger:1051; frame_pool.h:49-51 | OPEN P1 (md:135) |
| B7 | RCD30: the loop as "arrows into step 2 (yes) and step 1 (no)". The header goes "back to step 1, always". | ledger:1054; record_writer.h:162-165 | OPEN P3 (md:136) |
| B8 | TEL2: "one event" per fault. The writer never records. | ledger:958; md:309 | OPEN P2 (md:134) |
| B9 | OK, RCD1: "one ambient record service per process (no handle)" | ledger:1021; recorder.h:3 | - |
| B10 | OK, RCD2/RCD5/RCD22: FrameSize, PixelFormat, FrameView in frame_types.h; RecordFrame(folder, name, at, const FrameView*) | ledger:1022,1025,1046; frame_types.h:9-25; record_frame.h:27-32 | - |
| B11 | OK, RCD3: "the pid in the file name ... the session folder made before any child" | ledger:1023; record_file.h:14; recorder.h:27-28 | - |
| B12 | OK, RCD4 + RCD19 item 7 + RCD34 B1: no sample contract; no GPU record | ledger:1024,1039,1058; no such type in any header | - |
| B13 | OK, RCD6: "sleeps on one wake-up object (OsEvent) with a 5 s timer"; "timer and counters are locals" | ledger:1026; record_writer.h:49,111,159 | - |
| B14 | OK, RCD7: OsEvent "(sticky, set, clear, timed monotonic wait) into runtime_internal.h"; "the mask limit per pass from config" | ledger:1027; runtime_internal.h:82-86; frame_pool.h:20-24 | - |
| B15 | OK, RCD9: two endpoint types; head, tail and drop count on separate 64-byte lines; the pool as two index queues with no per-slot state | ledger:1029; spsc_record_queue.h:26-32,110-112; frame_pool.h:56-61 | - |
| B16 | OK, RCD11 (as superseded): four makers; "watermark wake once per crossing at half"; time reference "at every fsync"; "drop line with the gap" | ledger:1031; record_field.h:91-94; recording_thread.h:29,105-107; record_writer.h:50,158; record_file.h:92-97 | - |
| B17 | OK, RCD12: the cut rule on text fields; "the last pass ... the normal pass with the die line"; one snapshot per pass; no cached index | ledger:1032; record_field.h:29-31,85-86; record_writer.h:146,166-169; spsc_record_queue.h:95-97 | - |
| B18 | OK, RCD16: LINE_KIND_NAMES, SPAN_STAGE_NAMES, RECORD_FILE_OPEN_FLAGS, RECORD_PNG_OPEN_FLAGS, EVENT_KEY_FIELDS, mb_lastWriteFailed, m_oldestReadyFramePublishedAt, unusedCtx | ledger:1036; record_file.h:15,17,38-45,82; recorder_internal.h:46; record_writer.h:116; recorder.h:52 | - |
| B19 | OK, RCD17/RCD37: 31 caller fields plus "cut" | ledger:1037,1061; record_field.h:24-25 | - |
| B20 | OK, RCD19: the time reference line (time, monotonic_ns, wall_us, boot_ns); a cap of 16, and a 17th thread dies; the three util headers | ledger:1039; record_file.h:25,39,56-58; recording_thread.h:20-27; 00-util/*.h | - |
| B21 | OK, RCD20: "FieldName and RecordTopic are const char* to literals" | ledger:1040; record_field.h:11; record_event.h:9 | - |
| B22 | OK, GIL2: "none exists to record" | ledger:1042; recording_thread.h:2-3 | - |
| B23 | OK, PY3: "a deque of record tuples bounded by a count; a span is (stage, start, end, names, values)" | ledger:1044; spsc_record_queue.h:5-6; record_field.h:81-82; record_span.h:36 | - |
| B24 | OK, RCD21/RCD22: actor headers with prefixes; Create/Destroy; SpscConsumerFront/Pop; IndexQueueFront; FramePool* names; WriterIsStalled with no stamp | ledger:1045-1046; recording_thread.h; frame_pool.h:64-75; index_queue.h:32-38; record_writer.h:142 | - |
| B25 | OK, RCD23: "a ring of record slots (offset, length, kind) and a separate byte area"; the pool picked by format; RecordFileCreate(sessionDir, process); m_queues, m_queueEnds, m_queueCount in the writer | ledger:1047; spsc_record_queue.h:84-97; record_frame.h:20; record_writer.h:71,117-119 | - |
| B26 | OK, RCD25 W1: "a bounded retry queue of 64 lines (two index queues over LineText slots) ... step 7 ... oldest first, until one fails; a full retry queue drops, counted" | ledger:1049; record_writer.h:43,92-95,123-125,154 | - |
| B27 | OK, RCD31: "RecorderCounters stays unpadded (28 bytes)" (28 measured) | ledger:1055; recorder_internal.h:36-49 | - |
| B28 | OK, RCD34 A1: "RecorderCreate makes <sessionDir>/asr_clips/" | ledger:1058; recorder.h:26-28 | - |
| B29 | OK, RCD35: kRecordQueueRecords = 16384; RecordResult in record_field.h, returned by all three contracts | ledger:1059; recording_thread.h:28; record_field.h:72-78; record_span.h:40; record_event.h:12; record_frame.h:27 | - |
| B30 | OK, RCD36/RCD37: 8192; "length" removed; "cut" (the bytes lost) only on a cut record | ledger:1060-1061; record_field.h:26,29-31 | - |
| B31 | OK, RCD39: OsEventIsSet; a second Create only with a joined writer and a new folder; two names joined by one "/"; ok false; the index queue as a deque under a Lock | ledger:1063; runtime_internal.h:85; recorder.h:32-35; record_frame.h:16-17; record_file.h:84-86; index_queue.h:4-5 | - |
| B32 | OK, RCD40 (rest): 64 KiB; the leftover pop and release; the compare-and-swap from the loaded value; Create's resets; the pid stated; the tuple path with no type check | ledger:1064; record_writer.h:42,60-61,87-88,169-172; recorder.h:34-35; record_field.h:86-89 | - |
| B33 | OK, PRF1/PRF2/PRF3: the stage enum, its names as text, raw-ns stamps the caller holds, Create(sessionDir, processName) | ledger:908,920,955; record_span.h:16-46; record_file.h:42-45; monotonic_clock.h:9 | - |
| B34 | OK, PRF4/PRF5/RVW4: the thread past the cap dies; the cap is the design's count, from config | ledger:956,957,948; recording_thread.h:20-27 | - |
| B35 | OK, PRF7/TEL1/RVW7: no handle; one instance and one file per process | ledger:1018,919,951; recorder.h:3; record_file.h:14 | - |
| B36 | OK, TEL2 (rest): "Create still dies when the session folder cannot be written" | ledger:958; recorder.h:30-32 | - |
| B37 | OK, TEL3/TEL4: no domain type in the sink | ledger:959-960; no domain type in any header | - |
| B38 | OK, TEL3 (2): separate pools of 8 and 24 | ledger:962; frame_pool.h:23-25 | - |
| B39 | OK, TEL5/TEL13/TEL14/TEL16: lossless PNG level 1 at the source resolution; no codec; refuse the start under the reserve | ledger:961,972,973,975; record_frame.h:1-2; recorder.h:31-32 | - |
| B40 | OK, TEL7: full queues and pools drop and count | ledger:966; spsc_record_queue.h:46; frame_pool.h:68; record_frame.h:18 | - |
| B41 | OK, TEL10: "the stall rule computed at read" | ledger:969; record_writer.h:140-142 | - |
| B42 | OK, TEL17/TEL18: bytes = W x H x 3 x 0.45 x 30 x minutes; 40 and 5 minutes; uint64 product | ledger:976-977; record_writer.h:44-46,52; recorder_internal.h:62-64 | - |
| B43 | OK, RVW3: the pixels copied during the call, while the job holds the slot | ledger:947; record_frame.h:20-22 | - |
| B44 | OK, RUN3: a typed DieActionFn | ledger:982; runtime.h:18; recorder.h:50-52 | - |
| B45 | No header consequence, or superseded: TEL6, TEL8, TEL9, TEL11, TEL12, TEL15, TEL19, RVW1, RVW2, RVW5, RVW6, PRF6, REV7, REV8 (document only), PY2 (document only, md:240), RCD8 (superseded by RCD9), RCD10, RCD13-15, RCD18 (superseded by PY3), RCD24, RCD26, RCD28, RCD29, RCD32, RCD33, RCD38 (superseded by RCD39/RCD40) | ledger | - |

## C. Decisions vs document

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | The 17th-thread die is a change against TEL2. Gate item 2 says it is "in section 4's table", but section 4's change table has no such row. REV8 requires "every change to an approved contract is an open point read once at the end". | md:204; md:116-136; ledger:1014 | MINOR |
| C2 | Test 2 cites PRF4 for "drop-new at the bound". PRF4's consequence has no drop rule; TEL7 has it. | md:324; ledger:956,966 | NOTE |
| C3 | RCD40: "the tuple path has no type check and nothing raises". The document says drop and count. | ledger:1064; md:205 | = A3 |
| C4 | RCD34 B2 was changed by RCD39 (NOT_CREATED counts nowhere) and is not marked OPEN. | ledger:1058,1063; md:134-136 | = B1 |
| C5 | Consistent with the latest ruling: RCD19 item 7 / RCD34 B1 (md:98,310,444,463); RCD35 (md:121,269,296,324); RCD36/RCD37 (md:121,205,270,325); RCD25 W1 (md:128,264,335,464); RCD31 (md:212); PRF5 (md:20,137,429); TEL17 (md:193); TEL16 (md:192); RCD34 A1 (md:458); RCD35 A2 (md:425,461); PRF7 (md:188); RVW3 (md:23,206); RCD29 drawing 4 (md:23); RUN3 (md:416); TEL10 (md:265); TEL7 (md:269,271) | md | - |

## D. Internal consistency of the document

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | The failure matrix has two rows for one failure, the 17th recording thread, with differently worded causes. | md:275, md:276 | MINOR |
| D2 | "The hot path ... builds no text" and "The helper ... builds no text". But the record_vision_pass helper builds boxes_json(reply). | md:37-38, md:90-91; md:80 | MINOR |
| D3 | Section 4's change table has two rows titled "the writer's wake". | md:123, md:129 | NOTE |
| D4 | Drawing 5's last pass leaves out what drawing 2 and the header list: the retry step 7, the unconditional time reference and health line, and the count of leftover records and slots. | md:24; md:21; record_writer.h:166-173 | NOTE |
| D5 | Wrong-typed value: drop and count (md:205) against written as its text (md:327). | md:205; md:327 | = A3 |
| D6 | A record before Create: "anything else drops and counts" (md:247) against "a no-op" (md:330, md:418). | md:247; md:330; md:418 | = A4 |
| D7 | The 17th thread is said to be in section 4's table and is not. | md:204; md:116-136 | = C1 |
| D8 | A re-Create in the same folder: EEXIST (md:273) against a clash cause (md:274). | md:273-274 | = A6 |
| D9 | Checked and consistent across the document: the thread cap 16; the queue 16,384 with the half-full wake; the pools 8 and 24; the file name; the 64-line retry queue; the "cut" field; the 9 pass steps (md:21); the drop counting per entry (md:25, md:241). | md | - |

## E. Internal consistency of the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | The comment says the makers "check the type and range and return INVALID_ARG". The signatures return RecordField. Nothing says how a maker's failure reaches the record call or which counter it hits. | record_field.h:89-90; record_field.h:91-94 | BLOCKING |
| E2 | The comment says "eight times the bound always fits (the static_assert below)". The static_assert checks 6 x bound + 4096. | record_writer.h:36-37; record_writer.h:128 | MINOR |
| E3 | record_span.h: "a call while the recorder is not RUNNING is dropped and counted". The other headers return NOT_CREATED and count nothing before Create. | record_span.h:38-39; record_field.h:69-71; recorder_internal.h:20-21 | MINOR |
| E4 | "DROPPED and INVALID_ARG are counted in the health". But m_droppedSpans and m_droppedEvents list only "too many fields" among the INVALID_ARG causes; "a bad value" is in no counter. Whether NO_FRAME_POOLS is counted is not stated. | record_field.h:66-71; recorder.h:64-69 | MINOR |
| E5 | A frame drop is counted "in the job thread's own entry". An entry is made only at a thread's first RecordSpan or RecordEvent. A thread that only calls RecordFrame has no entry, and nothing says whether RecordFrame makes one (which would take one of the 16). | recorder.h:73; recording_thread.h:1-4,51-53 | MINOR |
| E6 | The queueless counters are incremented by every thread that got no queue. In the Python build that is several writers with a bare +=. This contradicts "no counter has two writers (PY1)". | record_writer.h:95-96,120-121; recorder.h:66-69 | MINOR |
| E7 | The oldest-ready stamp race. A publish's compare-and-swap from 0 fails while the stamp is non-zero, so it leaves no trace. The writer's end-of-pass compare-and-swap from its loaded value then succeeds. A frame published after the ready queue emptied can then wait with the stamp at 0, and the stall rule cannot see it. The value the writer stores is not stated. | record_writer.h:85-88; record_frame.h:25-26 | MINOR |
| E8 | m_oldestReadyFramePublishedAt is stored "at the end" of step 6 and again among the end-of-pass stores. It is not stated whether that is one store or two. | record_writer.h:153; record_writer.h:160-161 | NOTE |
| E9 | m_dieReason is non-atomic text. During a Destroy, the writer's last pass reads it ("the die line if m_dieReason is set") while a concurrent Die may still be writing it. Die's store order is stated; the writer's load order is not. | record_writer.h:81-83,114,167; recorder.h:51 | MINOR |
| E10 | Destroy's compare-and-swap on m_stopDeadline has no stated Python form. The Python compare-and-swap is stated only for the stamp. Done unguarded, Destroy can overwrite Die's deadline, against "Die wins". | record_writer.h:81-82; record_writer.h:88-89 | MINOR |
| E11 | RecordFile.m_path is 256 bytes and must hold sessionDir + "/record-" + process + "-" + pid + ".jsonl". RecorderCreate does not reject a long sessionDir. The PNG path (sessionDir + a 63-byte folder + a 31-byte name + ".png") has no buffer type. Truncation and overflow are not covered. | common_names.h:10; record_writer.h:67; recorder.h:30-32; record_frame.h:11-12; record_file.h:16 | MINOR |
| E12 | m_firstDropAt is stored only at the first drop after a successful push. A drop run that spans two passes gives the second drop line a "from" earlier than the first line's "to", against "losses since its last drop line, and when they happened". | recording_thread.h:43-47; record_file.h:92 | MINOR |
| E13 | m_failedWrites counts a failed append, and counts the same line again when a full retry queue drops it. Whether a failed retry in step 7 counts is not stated, so the count is neither a line count nor an attempt count. | record_writer.h:62,94-95,154; recorder.h:75-76 | MINOR |
| E14 | The final pass "adds them to the dropped counts by kind". The target is not stated: the thread's entry, which a late producer also writes, or RecorderCounters. | record_writer.h:169-171; recorder.h:66-69 | MINOR |
| E15 | When mb_lastWriteFailed clears is not stated. | recorder.h:81-83; recorder_internal.h:46 | NOTE |
| E16 | Step 8 compares against bytes(kWriterReserveMinutes), which needs a FrameSize. A process with RECORDER_NO_FRAMES has none. | record_writer.h:155-157; recorder_internal.h:62-64; recorder.h:24 | NOTE |
| E17 | The line order puts the time reference and health right after the die line. WriterRun puts the step-7 retry lines in between. | record_file.h:21-23; record_writer.h:166-168 | NOTE |
| E18 | A re-Create resets the flags, the deadline, the stopped flag and the die reason. It does not reset RecorderCounters, the entries' drop counts or the reported counts. The health after a re-Create carries the earlier session's totals, and this is not stated. | recorder.h:34-35; recorder_internal.h:27-28,40-49; recording_thread.h:60-66 | NOTE |
| E19 | The Python queue is bounded by count only (16,384 records of up to 8 KiB each). The C form also has a byte bound. | spsc_record_queue.h:5-6,93-94; record_field.h:26 | NOTE |
| E20 | FramePoolPublishSlot(pool, slot) cannot reach the writer's stamp or m_wake. Which function does "the publish also stores" is not stated. | frame_pool.h:69-70; record_frame.h:25-26 | NOTE |
| E21 | The health line's "stalled" is written by the writer. WriterIsStalled is described only for the main thread's read. | record_file.h:105; record_writer.h:140-142 | NOTE |
| E22 | Entries are never freed ("the threads ... survive"). Each thread that exits and is replaced uses up a new entry of the 16, and the 17th dies. | recorder_internal.h:26-27; recording_thread.h:20-22 | NOTE |
| E23 | In C, a field name counts as a pointer inside the 8 KiB bound but "the names print in full". So "a line always fits" rests on the spare 16 KiB, not on any bound. | record_field.h:2-3; record_writer.h:35-36,131 | NOTE |
| E24 | gcc: 01-recorder 10 of 10 pass with no warning. 00-util/fixed_text.h compiled alone gives "ISO C forbids an empty translation unit" under -pedantic (md:212 says all sixteen are clean). | 00-util/fixed_text.h:12; md:212 | NOTE |
| E25 | No type is used without a definition. Every include exists. No constant has two values. LINE_KIND_NAMES and SPAN_STAGE_NAMES match their enums in order and count (9, 15). The aggregate is verbatim. | all 16 headers | - |
