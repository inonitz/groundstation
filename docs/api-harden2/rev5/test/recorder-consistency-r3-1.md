# Recorder consistency check, round 3, checker 1 (2026-10-21)

**Verdict: NOT CONSISTENT: 1 BLOCKING, 13 MINOR, 18 NOTE.**

Paths: `M` = docs/api-harden2/rev5/modules; `L` = docs/spec-harden2-cleanup.md; `doc` = M/01-recorder/recorder.md.
Out of scope: OPEN P1 and P2 (doc:134-135), and HISTORY rows that name their superseding ruling.

Measured on this run:
- gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on the ten 01-recorder headers: 0 errors, 0 warnings.
- The same flags on the six 00-util headers alone: one warning, in fixed_text.h:12 (see A2).
- sizeof: struct Recorder 1408; RecorderCounters 28; SpscRecordQueue 256, with head at 64, tail at 128, dropped at 192. These match doc:152, doc:302 and RCD31.
- The aggregate holds all sixteen headers verbatim (a string compare per file).

## A. The document against the headers

| # | what | where | severity |
|---|---|---|---|
| A1 | The sample frame line has `"ok":1`. The header says ok is true or false. The health sample on doc:224 uses JSON booleans. | doc:222; M/01-recorder/record_file.h:84-85 | MINOR |
| A2 | The document says gcc -pedantic passes on "all sixteen headers". fixed_text.h compiled alone warns: "ISO C forbids an empty translation unit". | doc:211; M/00-util/fixed_text.h:12 | MINOR |
| A3 | The TOCTOU table says "one writer per state transition". The header has two writers for STOPPED (the writer, and Destroy past its deadline) and two for STOPPING (Destroy, FlushInDie). | doc:257; M/01-recorder/recorder_internal.h:22-25 | MINOR |
| A4 | The document calls O_EXCL "the second guard" against a second app in the same folder. The file name carries the pid, so a second process never gets EEXIST. | doc:272; record_file.h:14; recorder.h:33-34 | MINOR |
| A5 | These header functions are never named in the document: SpscRecordQueueCreate, SpscRecordQueueDestroy, SpscProducerPush, SpscConsumerFront, SpscConsumerPop, SpscProducerRecordsQueued, SpscProducerRecordsDropped, IndexQueueCreate, IndexQueueDestroy, IndexQueuePush, IndexQueuePop, IndexQueueFront, FramePoolCreate, FramePoolDestroy, FramePoolsCreate, FramePoolsDestroy, RecordFileCreate, RecordFileWriteHeader, RecordFileClose, ProducerPushEvent. FieldInt, FieldFloat, FieldBool and FieldText appear only as "the makers" (doc:237). OsEventIsSet appears only as "is_set()" (doc:236). | spsc_record_queue.h:37-66; index_queue.h:32-38; frame_pool.h:64-65,92-93; record_writer.h:68-74; recording_thread.h:94; record_field.h:89-92; M/03-runtime/runtime_internal.h:85 | NOTE |
| A6 | These header types are never named in the document: RecordField, FieldType, FieldValue, TextValue, FieldName, FieldCount, TextLength, RecordSlot, RingPosition, ByteOffset, RecordBytes, RecordKind, SlotIndex, SlotCount, SLOT_NONE, FrameSlot, FramePools, FolderName, FrameName, LineKind, LineText, DieReasonText, ByteCount, FileDescriptor, RecorderHealth, RecorderState, PathText, ProcessName, ThreadName, RecordCount, ThreadCount, QUEUED_SPAN, QUEUED_EVENT. | record_field.h; spsc_record_queue.h; index_queue.h; frame_pool.h; record_file.h; record_writer.h; recorder.h; common_names.h; recording_thread.h:32-38 | NOTE |
| A7 | These constants appear in the document by neither name nor value: kRecordFolderBytes 64, kRecordNameBytes 32, kRingBytesPerRecordExpected 64, kWriterLineBytes 32768, kWriterExpectedPassesPerMinute 30. WRITER_PNG_BYTES_PER_RAW_BYTE is named, but its value 0.45 is not given. | record_frame.h:11-12; spsc_record_queue.h:75; record_writer.h:40,42,50; doc:211,428 | NOTE |
| A8 | The current sections never describe the thread that got no queue. That covers mb_queueTried, m_droppedSpansWithoutQueue, m_droppedEventsWithoutQueue, and DROPPED for "the thread got no queue". Only the history row D4 mentions it. | recording_thread.h:67-68,75; record_writer.h:89-90,114-115; record_field.h:67; doc:159 | NOTE |
| A9 | The writer makes the PNG's folder. The document's account of who makes which folder leaves this out. | record_file.h:16; record_writer.h:144; doc:29-34,455 | NOTE |

## B. The decisions against the headers

OK means the header does what the latest ruling says.

| # | ruling (L:line), the consequence | header line | severity |
|---|---|---|---|
| B1 | RCD1 (L:1021): "one ambient record service ... no handle" | recorder.h:3 "Ambient ... no handle" | OK |
| B2 | RCD2 (L:1022): FrameSize, FrameView. The home and the channel are superseded by RCD5 and RCD22. | frame_types.h:9-25; record_frame.h:27-32 | OK |
| B3 | RCD3 (L:1023): the pid in the file name; the session folder made before any child | record_file.h:14; recorder.h:27-28 | OK |
| B4 | RCD4 (L:1024): no sample contract. The gpu event is superseded by RCD19 and RCD34 B1. | record_span.h:16-33 (no sample, no GPU stage) | OK |
| B5 | RCD5 (L:1025): one contract per header; frame_types.h | record_span.h, record_event.h, record_frame.h; frame_types.h | OK |
| B6 | RCD6 (L:1026): one wake object (OsEvent) with a 5 s timer; the timer and the counters are locals | record_writer.h:47,105,153 | OK |
| B7 | RCD7 (L:1027): OsEvent carried into runtime_internal.h; the mask limit from config | runtime_internal.h:78-86; frame_pool.h:20-21 | OK |
| B8 | RCD9 (L:1029): endpoint types; head, tail and the drop count on their own lines; two index queues; no per-slot state | spsc_record_queue.h:26-32,110-112; frame_pool.h:56-61 | OK |
| B9 | RCD11 (L:1031): the half-full wake; the time reference at every fsync; the drop gap | recording_thread.h:29,101-103; record_writer.h:152; recording_thread.h:43-47 | OK |
| B10 | RCD12 (L:1032): the cut rule on texts; the last pass is the normal pass plus the die line; no cached indexes; one snapshot per pass | record_field.h:84-87; record_writer.h:140,157-160; spsc_record_queue.h:104-113 | OK |
| B11 | RCD15, RCD16 (L:1035-1036): the renames; LINE_KIND_NAMES, SPAN_STAGE_NAMES, the open flags, EVENT_KEY_FIELDS, unusedCtx | record_file.h:15-17,38-45,82; recorder.h:52 | OK |
| B12 | RCD17, RCD20, RCD37 (L:1037,1040,1061): 31 caller fields plus "cut"; names as literals | record_field.h:11,24-25; record_event.h:9 | OK |
| B13 | RCD19 (L:1039): the cap is 16 and a 17th thread dies; T1 util headers; the time reference naming | recording_thread.h:20-27; M/00-util/*; record_file.h:25,52-58 | OK |
| B14 | RCD21, RCD22, RCD23 (L:1045-1047): actor headers and prefixes; Create and Destroy; a ring of slots plus a byte area; the queue list in the writer | recording_thread.h:84-103; frame_pool.h:64-75; spsc_record_queue.h:84-113; record_writer.h:111-113 | OK |
| B15 | RCD25 W1 (L:1049): "a bounded retry queue of 64 lines (two index queues over LineText slots) ... appended again at the end of each pass" | record_writer.h:41,86-89,117-119. It runs as step 7 of 9, and step 9 appends lines after it (record_writer.h:148,152). | NOTE |
| B16 | RCD27 (L:1051): "the slot pool is MPSC under one lock" | frame_pool.h:49-51: two locks. This is OPEN P1, not counted. | OK (OPEN) |
| B17 | RCD30 (L:1054), the owner's instruction: "the loop as arrows into step 2 (yes) and step 1 (no)" | record_writer.h:153-156: "back to step 1, always ... nothing is checked at the end of a pass". This came from RCD39 (L:1063), an agent fix pass, not an owner ruling. It is not marked OPEN. The behaviour is the same, because the remembered set makes the wait return at once. | MINOR |
| B18 | RCD31 (L:1055): RecorderCounters unpadded, 28 bytes | recorder_internal.h:35-48 (28 measured) | OK |
| B19 | RCD34 B1, B2, A1 (L:1058): no gpu; dropped and counted outside RUNNING; modules closed before Destroy; asr_clips/ made at Create | record_span.h:38-39; recorder_internal.h:20-22; recorder.h:46-47,26-28 | OK |
| B20 | RCD35 (L:1059): 16384 records; RecordResult returned by the three record calls | recording_thread.h:28; record_field.h:72-78; record_span.h:40; record_event.h:12; record_frame.h:27 | OK |
| B21 | RCD36, RCD37 (L:1060-1061): 8 KiB; "cut" only on a truncated record; no "length" | record_field.h:26,29-31 | OK |
| B22 | RCD38 (L:1062): the line buffer 32 KiB with a static_assert, no line-level cut | record_writer.h:40,122. The "always fits" claim is false; see E1. | see E1 |
| B23 | RCD39 (L:1063): the leftover records counted; the publish CAS from 0; OsEventIsSet; a second Create needs a joined writer and a new folder; folder "a/b"; ok false; NOT_CREATED counts nowhere | record_writer.h:160-166; record_frame.h:25-26; runtime_internal.h:85; recorder.h:32-35; record_frame.h:17; record_file.h:84-85; record_field.h:70-71 | OK |
| B24 | PY1 (L:1041): the Python form is a built-in container or a Lock; real atomics in C | index_queue.h:4-5; spsc_record_queue.h:95-97 | OK |
| B25 | PY3 (L:1044): a deque of tuples bounded by a count; a span is (stage, start, end, names, values) | spsc_record_queue.h:5-6; record_field.h:80-82 | OK |
| B26 | GIL2 (L:1042): the recording threads are the app's working threads; none exists to record | recording_thread.h:1-3 | OK |
| B27 | PRF1, PRF2 (L:908,920): the stage is an enum and the file keeps its name; no marks; the caller holds the start | record_span.h:16-33,40-46; record_file.h:42-45 | OK |
| B28 | PRF4 (L:956): "the 33rd thread is a bug and dies (RVW4), no drop branch" | recording_thread.h:21-22 (17th) | OK |
| B29 | PRF4, cited for the cut rule | record_field.h:86 cites PRF4. The PRF4 row (L:956) states no cut rule; only RCD12 (L:1032) attributes it to PRF4. | NOTE |
| B30 | PRF5 (L:957): the table size is the design's count, from config, never nproc | recording_thread.h:20-22 | OK |
| B31 | PRF6, RUN3 (L:979,982): the flush is Die step 3 and a DieActionFn | recorder.h:50-52; M/03-runtime/runtime.h:18 | OK |
| B32 | PRF7 (L:1018): no module holds a handle | recorder.h:3 | OK |
| B33 | TEL2 (L:958): "one event" per fault | Absent from the headers. This is OPEN P2, not counted. | OK (OPEN) |
| B34 | TEL5, TEL14, TEL16 (L:961,973,975): lossless PNG level 1 at the source's resolution | record_frame.h:1-2; recorder.h:19-22 | OK |
| B35 | TEL7 (L:966): full rings and pools drop and count | spsc_record_queue.h:46; frame_pool.h:68 | OK |
| B36 | TEL10, TEL11, TEL12 (L:969-971): the stall rule computed at read; fsync every 5 s; PNG 0.45; 64-bit values as macros | record_writer.h:134-136,47-50 | OK |
| B37 | TEL17, TEL18 (L:976-977): 30 passes a minute; 40 minutes at start; 5 minutes reserve; the product in 64 bits | record_writer.h:42-44,31; recorder_internal.h:61-63 | OK |
| B38 | RVW3, RVW4 (L:947-948): the job holds its slot and the pool copies during the call; one tracer with a queue per thread | record_frame.h:20-22; recording_thread.h:1-5 | OK |
| B39 | These rows have no header consequence of their own, or are superseded in full: RCD8, RCD10, RCD13, RCD14, RCD18, RCD24, RCD26, RCD28, RCD29, RCD32, RCD33, PY2, PRF3, TEL1, TEL3, TEL4, TEL6, TEL8, TEL9, TEL13, TEL15, TEL19, RVW1, RVW2, RVW5, RVW6, RVW7, REV7. REV8 is checked in C. | L:1028-1057; L:945-978; L:996 | OK |

## C. The decisions against the document

| # | what | where | severity |
|---|---|---|---|
| C1 | The TEL2 row calls TEL2 "unchanged" while adding a die for the 17th thread. TEL2 says "after start-up no path ... calls die()", and TEL11 says "past it, dropped and counted, TEL2". The die (RCD19) is a change to an approved telemetry contract. It is missing from section 4's change table, which REV8 requires. | doc:193,136; L:958,970,1039,1014 | MINOR |
| C2 | Drawing 2's cell says "then back to step 1, always". The owner's RCD30 asked for arrows into step 2 (yes) and step 1 (no). The change came from an agent fix pass (RCD39), and the document does not mark it OPEN. | doc:21; L:1054,1063 | MINOR |
| C3 | The document cites PRF4 for the cut rule and for drop-new at the bound. The PRF4 row holds neither. | doc:136,321; L:956 | NOTE |
| C4 | The document cites OPEN 1 for "MonotonicNow, MonotonicNs in 00-util". OPEN 1 gave RecorderTimestamp and RecorderNow. The names come from RCD15, and the util home from RCD19 item 4. | doc:416; L:1022,1035,1039 | NOTE |

## D. The document against itself

| # | what | where | severity |
|---|---|---|---|
| D1 | Gate item 2 says "no die() after start", then names "the one die: the 17th recording thread". That thread arrives after start. | doc:203 | MINOR |
| D2 | The document says "every folder has one writer". The session folder holds one file per process (doc:31), and the ASR node writes into asr_clips/ (doc:455). | doc:32-33 | MINOR |
| D3 | The headers are called "draft 14" as the current truth. The aggregate is draft 15. | doc:143,150; M/01-recorder/recorder_aggregate_for_review.md:1 | NOTE |
| D4 | "44 MB" holds at 720p only (8 x 1280 x 720 x 3 + 24 x 1280 x 720 = 44.2 MB), and no resolution is given. At 1080p, which doc:270 uses, it is 99.5 MB. | doc:309 | NOTE |
| D5 | "the lazy ring per thread" is given as current. The current form is a deque of tuples, or in C a ring of record slots. | doc:136-137 against doc:121 | NOTE |

## E. The headers against themselves

| # | what | where | severity |
|---|---|---|---|
| E1 | The header claims "its JSON escaping at most doubles it, so a line always fits", and pins the claim with a static_assert at 2 x 8192 + 1024. The claim is false: (1) a control byte escapes to \u00XX, 6 bytes; (2) an invalid UTF-8 byte becomes U+FFFD, 3 bytes; (3) in C a name travels as an 8-byte pointer but prints in full. A text of 8192 control bytes formats to 49152 bytes. RCD38 removed the line-level cut, so the 32768-byte buffer overflows. | record_writer.h:33-35,122,125; record_field.h:2-3 | BLOCKING |
| E2 | A comment says the open flags mean "a second process with the same name fails". The name carries the pid, so a second process never clashes. | record_writer.h:57-58; record_file.h:14 | MINOR |
| E3 | Two stores the comments assign to "each pass" are missing from WriterRun's nine steps: m_lastProgressAt "at the end of each pass", and the sum of the threads' drop counts into the counters. | record_writer.h:80-81,138-156; recorder_internal.h:35-36; recorder.h:67-68 | MINOR |
| E4 | The writer stores m_oldestReadyFramePublishedAt at the end of each pass with a plain store, which can be 0. A publish between the writer's look at the ready queue and that store loses its CAS-from-0 stamp. The TOCTOU table does not cover this. | record_writer.h:82-84; record_frame.h:25-26; doc:243-258 | MINOR |
| E5 | recorder.h counts "a bad value or too many fields (INVALID_ARG, Python)", so the Python build only. record_field.h counts every INVALID_ARG in the health, in either build. Where C's too-many-fields drop is counted is undefined. | recorder.h:65-66; record_field.h:68-71 | MINOR |
| E6 | A frame call while STOPPING or STOPPED returns DROPPED, and DROPPED "is counted". m_droppedFrames lists no such cause. Whether NO_FRAME_POOLS is counted is not stated. | record_frame.h:18-19; record_field.h:66-71; recorder.h:69-71 | NOTE |
| E7 | A second Create resets "every announced flag and the stop deadline" only. These are not reset: m_stopped (set by the last pass), m_wake, m_dieReason, the counters, m_lastProgressAt and m_oldestReadyFramePublishedAt. A still-set m_stopped lets the next Destroy's wait return at once. | recorder.h:33-35; recorder_internal.h:26-27; record_writer.h:105-110,162 | NOTE |
| E8 | Two steps of queue registration are unstated. (1) How a thread claims its index (m_queueCount). (2) How the consumer endpoint, which Create hands to the creating thread, reaches m_queueEnds before the release store of the pointer. | record_writer.h:111-113; spsc_record_queue.h:34-43; recording_thread.h:40-42 | NOTE |
| E9 | One drop is counted twice: in the queue's m_dropped, and in RecordingThread.m_droppedSpans or m_droppedEvents. Only the second has a stated reader. | spsc_record_queue.h:46,55,112; recording_thread.h:57-58 | NOTE |
| E10 | record_file.h puts the die line "after that pass's records". The last pass appends the retry lines (step 7) after the die line. | record_file.h:21-22; record_writer.h:157-158 | NOTE |
| E11 | Every include exists, and every type used is defined. One pedantic warning, when fixed_text.h is compiled alone (A2). | M/00-util/fixed_text.h:12 | NOTE |
