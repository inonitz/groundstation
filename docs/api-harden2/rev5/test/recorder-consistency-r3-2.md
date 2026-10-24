# Recorder consistency check, round 3, checker 2

**Verdict: NOT CONSISTENT: 1 BLOCKING, 13 MINOR, 31 NOTE.**

gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 over the ten 01-recorder headers: 10 of 10 pass, 0 warnings.
Sizes measured with gcc: struct Recorder 1408, RecorderCounters 28, SpscRecordQueue 256, RecordField 32, RecordSlot 8.
Abbreviations: md = 01-recorder/recorder.md; ledger = docs/spec-harden2-cleanup.md; header paths are under docs/api-harden2/rev5/modules/.

## A. Document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | The frame line sample has `"ok":1`. The header says ok is true or false. The health sample uses true/false. | md:222; record_file.h:84-85 | MINOR |
| A2 | The TOCTOU row says "one writer per state transition". The header names "the one case with two writers" (Destroy past its deadline and the abandoned writer both store STOPPED). | md:257; recorder_internal.h:23-25 | MINOR |
| A3 | The document never describes Destroy past its deadline: STOPPED stored by Destroy, the thread abandoned, a later Create returning false. | md:24; recorder.h:43-45; record_writer.h:163-166; recorder_internal.h:23-27 | NOTE |
| A4 | The document never says the writer makes the PNG's folder. | md:21 (step 6); record_file.h:16; record_writer.h:144 | NOTE |
| A5 | OsEventIsSet is not named. Drawing 3 names only Set, Wait and Clear. md:236 gives only the Python is_set(). | md:22; recording_thread.h:101-102; runtime_internal.h:85 | NOTE |
| A6 | The value of kWriterLineBytes (32768) is not in the document. Only the static_assert relation is stated. | md:211; record_writer.h:40 | NOTE |
| A7 | kWriterExpectedPassesPerMinute (30) and the reserve formula are not in the document. md:428 names only RecorderReserveBytes. | md:428; record_writer.h:42; recorder_internal.h:61-63 | NOTE |
| A8 | kRecordFolderBytes (64) and kRecordNameBytes (32) are not in the document. It says only "length". | md:171; record_frame.h:10-13 | NOTE |
| A9 | The C queue storage is described only as "a slot plus a byte area". RecordSlot, RingPosition, ByteOffset and kRingBytesPerRecordExpected (64) are not described. | md:121; spsc_record_queue.h:70-113 | NOTE |
| A10 | Util functions are not named: IndexQueueCreate/Destroy/Push/Pop/Front, SLOT_NONE, SpscRecordQueueCreate/Destroy, SpscProducerPush, SpscProducerRecordsQueued/Dropped, SpscConsumerFront/Pop. | md:21, md:300-301; index_queue.h:15,32-38; spsc_record_queue.h:37-66 | NOTE |
| A11 | Actor functions are not named: RecordFileCreate, RecordFileWriteHeader, RecordFileClose, FramePoolCreate/Destroy, FramePoolsCreate/Destroy, ProducerPushEvent. | record_writer.h:68-74; frame_pool.h:64-65,92-93; recording_thread.h:94 | NOTE |
| A12 | Types are not named: RecorderHealth, RecorderState, RecordField, FieldType, FieldValue, TextValue, FieldName, FieldCount, TextLength, RecordTopic, RecordKind, RecordBytes, RecordCount, LineText, DieReasonText, FolderName, FrameName, PathText, ProcessName, ThreadName, ThreadCount, FileDescriptor, ByteCount, FrameSlot, FramePools, LineKind, QUEUED_SPAN/QUEUED_EVENT. | recorder.h:83-93; recorder_internal.h:28-33; record_field.h:11-63; record_writer.h:30-31,52-53; frame_pool.h:28-29,41-47,85-90; recording_thread.h:32-38; record_file.h:24-35 | NOTE |
| A13 | FieldInt, FieldFloat, FieldBool and FieldText are not named. md:237 says only "the makers". | md:237; record_field.h:89-92 | NOTE |
| A14 | SPAN_ASR and SPAN_LLAMA_REQUEST are not named. Section 11 has no ASR helper row. | md:420,431-450; record_span.h:20,22 | NOTE |
| A15 | The retry queue's storage is not described: LineText slots and two index queues, m_retryFree and m_retryReady. | md:461; record_writer.h:86-89,117-119 | NOTE |
| A16 | These are described only in history rows D2 and D4: mb_queueTried, mb_dropping, m_droppedSpansWithoutQueue and m_droppedEventsWithoutQueue. | md:158-159; recording_thread.h:66-77; record_writer.h:89-90,114-115 | NOTE |

## B. Decisions vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | RCD25 says the retry queue is "appended again at the end of each pass". The header runs it at step 7 of 9. On the last pass it runs before the time reference, the health line and the frame tail. | ledger:1049; record_writer.h:148,157-160 | MINOR |
| B2 | The writer constants say "the Python build reads them from config/ (PRF5)". PRF5 rules only the thread-table size. | record_writer.h:36-37; ledger:957 | MINOR |
| B3 | The cut rule is cited as PRF4. The PRF4 row holds no cut rule. RCD12 is the source ("restoring PRF4's cut rule"). | record_field.h:86; ledger:956,1032 | NOTE |
| OK | RCD1 ambient, three contracts: recorder.h:3-4, record_span/event/frame.h. | ledger:1021 | OK |
| OK | RCD2/RCD5 FrameSize uint16 and FrameView in frame_types.h. | ledger:1022,1025; frame_types.h:9-25 | OK |
| OK | RCD3 pid in the name; only the app has pools. | ledger:1023; record_file.h:14; recorder.h:24 | OK |
| OK | RCD4/RCD19 item 7/RCD34 B1: no sample and no GPU anywhere. | grep: 0 hits in the headers | OK |
| OK | RCD6/RCD27/RCD39 wake: OsEvent, timer, remembered set, back to step 1 always. | ledger:1026,1051,1063; record_writer.h:138-156 | OK |
| OK | RCD7 mask limit from config. | ledger:1027; frame_pool.h:20-25 | OK |
| OK | RCD9/RCD12 endpoint types; head, tail and drops on their own lines; read-only fields first; no cached index. | ledger:1029,1032; spsc_record_queue.h:26-32,104-113 | OK |
| OK | RCD17/RCD20/RCD37 31 caller fields plus "cut"; literal names. | ledger:1037,1040,1061; record_field.h:11,23-31 | OK |
| OK | RCD19 cap 16, a 17th dies; time reference line; T1 util headers. | ledger:1039; recording_thread.h:20-27; record_file.h:52-58 | OK |
| OK | RCD21/RCD22/RCD23 actor headers, Create/Destroy names, slot ring plus byte area, queue list in the Writer. | ledger:1045-1047; record_writer.h:62-120; spsc_record_queue.h:84-113 | OK |
| OK | RCD25 W1: 64 LineText slots, two index queues, full drops counted. | ledger:1049; record_writer.h:41,86-89 | OK |
| OK | RCD31 unpadded counters, 28 bytes measured. | ledger:1055; recorder_internal.h:35-48 | OK |
| OK | RCD34 A1 asr_clips/; RCD34 B2 dropped and counted. | ledger:1058; recorder.h:26-27; recorder_internal.h:20-22 | OK |
| OK | RCD35 16384; RecordResult from all three calls. | ledger:1059; recording_thread.h:28; record_field.h:72-78 | OK |
| OK | RCD36/37 8192, "cut" only. | ledger:1060-1061; record_field.h:26,29-31 | OK |
| OK | RCD38/RCD39 item list: STOPPED by Destroy; Create resets; ok false; CAS on publish; NOT_CREATED counts nowhere; IndexQueue under a Lock in Python. | ledger:1062-1063; recorder_internal.h:20-27; record_file.h:84-85; record_frame.h:25-26; record_field.h:70-71; index_queue.h:4-5 | OK |
| OK | PRF1 stage enum with its name as text; PRF2 the app holds stamps; PRF3 Create(sessionDir, process); PRF4/RVW4 the cap dies; PRF5 the cap is config, not nproc; PRF6 Die step 3; PRF7 no handle. | ledger:908,920,955-957,979,1018; record_span.h:16-33; record_file.h:42-45; recorder.h:36-52; recording_thread.h:20-22 | OK |
| OK | TEL2 Create dies on an unwritable folder (the die at the cap is superseded by RCD19 item 2); TEL5/TEL14/TEL16 PNG level 1; TEL7 drop and count; TEL10 stall rule at read; TEL12 macros; TEL17 30 passes, 40 and 5 minutes, 0.45; TEL18 uint64 product. | ledger:958-976; recorder.h:30-32; record_frame.h:1-2; record_writer.h:39-50; recorder_internal.h:61-63 | OK |
| OK | PY1 deque under a Lock; PY3 tuple (stage, stamps, names, values); GIL2 no recorder thread records. | ledger:1041-1044; index_queue.h:4-5; record_field.h:80-82; recording_thread.h:1-3,21 | OK |
| OK | RVW3 copy during the call; RUN3 DieActionFn signature matches runtime.h:18. | ledger:947,982; record_frame.h:20-22; recorder.h:50-52 | OK |
| OK | RCD27 "one lock" (P1) and TEL2 "one event" (P2) are OPEN, so they are not findings. | md:134-135 | OK |

## C. Decisions vs document

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | TEL2 is called "unchanged" while the 17th thread dies after start. TEL2 says "after start-up no path ... calls die()". The superseding RCD19 item 2 is not named. | md:193; ledger:958,1039 | MINOR |
| C2 | Drop-new is cited as PRF4. The PRF4 row has no drop-new. TEL7 carries "full rings and pools drop and count". | md:321,358; ledger:956,966 | MINOR |
| C3 | The retry queue runs "in step 7 of the same pass". RCD25 says "at the end of each pass". This is the same drift as B1. | md:263; ledger:1049 | MINOR |
| C4 | PRF2 to PRF6 are mapped to "the time reference line, the drain". No PRF row holds either. | md:189; ledger:920,955-957,979 | NOTE |
| C5 | History row D7 says "two atomics the writer stores at each pass end". RCD39 added the publish's CAS. The row does not name RCD39. | md:160; ledger:1063 | NOTE |
| C6 | "40 minutes of frames" is cited as TEL13. The 40 minutes come from TEL17. | md:192; ledger:972,976 | NOTE |

## D. Internal consistency of the document

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | Gate item 2 says "no die() after start", then "The one die: the 17th recording thread", which happens after start. | md:203 | MINOR |
| D2 | "every folder has one writer" sits in a paragraph where several processes write one session folder. "Folder" is ambiguous here. | md:29-34 | NOTE |
| D3 | These labels are used but not defined: R4, R1-n, R2-n, R3-n, A2, B1, B2, C1. R4 also collides with ledger row R4 ("log readers"). | md:107-133,405; ledger:665 | NOTE |
| D4 | "the lazy ring per thread" is stated as current. md:121 and md:283 call it a tuple deque in Python and a ring of slots only in C. | md:137 | NOTE |
| D5 | SIGKILL loses "at most 5 s of records". The retry queue holds up to 64 lines across passes while the disk fails, so the lines lost can be older. | md:263,265 | NOTE |

## E. Internal consistency of the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | "a line always fits" rests on "JSON escaping at most doubles it". A control byte escapes to 6 bytes (\u00XX). An invalid UTF-8 byte becomes U+FFFD (3 bytes). An 8 KiB text of control bytes needs about 48 KiB, more than kWriterLineBytes 32768. | record_writer.h:33-35,122,125 | BLOCKING |
| E2 | Destroy past its timeout says "health shows stalled". mb_stalled needs a ready frame: "frames only". | recorder.h:44-45,76-77; record_writer.h:49,134-135 | MINOR |
| E3 | record_field.h says "DROPPED and INVALID_ARG are counted in the health". recorder.h counts a span or event INVALID_ARG only as "(INVALID_ARG, Python)". C is left open. | record_field.h:70-71; recorder.h:64-66 | MINOR |
| E4 | mb_lastWriteFailed says "its line waits in the retry queue". A full retry queue drops that line. | recorder.h:78-79; record_writer.h:88-89 | MINOR |
| E5 | The final pass adds the remaining records to the dropped counts but does not pop them. A re-Create "reuses the queues", so the new writer would also write records already counted as dropped. | record_writer.h:160-162; recorder_internal.h:26-27; md:341 | MINOR |
| E6 | The writer's end-of-pass store of m_oldestReadyFramePublishedAt is a plain store. A publish CAS between the writer's ready check and that store is erased. The stall rule then misses that frame if the next pass hangs on it. | record_writer.h:80-84,147; record_frame.h:25-26 | MINOR |
| E7 | No header says how a thread takes its index in m_queues: the m_queueCount increment, and where the 17th thread is caught. | record_writer.h:111-112; recording_thread.h:40-43 | NOTE |
| E8 | There are two drop counts per queue: SpscRecordQueue.m_dropped (SpscProducerRecordsDropped) and RecordingThread.m_droppedSpans/Events. Only the second is said to feed the health. | spsc_record_queue.h:55,112; recording_thread.h:57-58; recorder.h:67-68 | NOTE |
| E9 | The C byte area is 64 B per slot. A C RecordField is 32 B (measured), so a 3-field span needs over 64 B. The bytes fill before 16,384 slots. "16,384 holds over six minutes" holds for the slot count only. | spsc_record_queue.h:75,94; recording_thread.h:23-24 | NOTE |
| E10 | A comment is broken mid-sentence ("A / record is never refused for its / text"). | record_field.h:83-86 | NOTE |
| E11 | The top comment says "its clock". The clock lives in monotonic_clock.h (RCD19 T1). | recorder.h:1-2 | NOTE |
| E12 | The file-order comment omits retried lines. They come back older than the lines around them, and after the die line on the last pass. | record_file.h:19-23; record_writer.h:148,157-158 | NOTE |
| E13 | FramePoolPublishSlot's comment says only "stamps, queues". The file comment says the publish also "wakes the writer". The oldest-ready CAS is RecordFrame's. Who wakes is not stated per function. | frame_pool.h:3,69-70; record_frame.h:25-26 | NOTE |
| E14 | The writer reads m_dieReason, a plain 256-byte text, "if set". No header orders that read behind an acquire load of m_stopDeadline. A Die during Destroy's last pass can be read torn. | record_writer.h:78-79,96-97,108,157-158 | NOTE |
| E15 | Twelve header lines exceed 90 characters (up to 129). | record_file.h:16; recording_thread.h:21,82; record_frame.h:22; spsc_record_queue.h:70; record_writer.h:47-49; recorder.h:24; record_event.h:9; record_file.h:4,44 | NOTE |
