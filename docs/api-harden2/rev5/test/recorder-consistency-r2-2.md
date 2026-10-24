# Recorder consistency check, round 2, checker 2 (2026-10-21)

**Verdict: NOT CONSISTENT: 1 BLOCKING, 23 MINOR, 25 NOTE.**

Sources: the 16 headers (6 in 00-util, 10 in 01-recorder), recorder.md (md), docs/spec-harden2-cleanup.md (ledger).
Paths: hdr = docs/api-harden2/rev5/modules/{00-util,01-recorder}/; md = 01-recorder/recorder.md.

Mechanical checks run:

| check | result |
|---|---|
| gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11, the 10 recorder headers | 10 of 10 pass; 0 warnings; 0 errors |
| recorder_aggregate_for_review.md against the 16 headers | 16 of 16 code blocks verbatim |
| sizeof, gcc x86-64 (a test file in the session scratchpad) | struct Recorder 1408; RecorderCounters 28; SpscRecordQueue 256 (m_head 64, m_tail 128, m_dropped 192); Writer 656; RecordingThread 384 |
| opaque types referenced (OsLock, OsThread, OsEvent, DieActionFn) | defined in 03-runtime/runtime_internal.h:76-86 and runtime.h:18 |

## A. Document against headers

| # | what | where | severity |
|---|---|---|---|
| A1 | RecorderCreate called with 3 arguments; infoJson put inside RecorderFrameConfig. The header takes 4 parameters; RecorderFrameConfig holds only m_size. md:411 has the 4-argument form | md:42, md:84; recorder.h:20-22, 34-39 | BLOCKING |
| A2 | Drawing 2's nine steps: step 2 = "reset the flag", no snapshot step. Header: step 1 = wait and clear, step 2 = the queue-list snapshot. "yes: step 2" lands on different steps | md:21; record_writer.h:136-137, 151-152 | MINOR |
| A3 | "the recording threads add drops" to the counters. Header: the writer sums the threads' drop counts each pass | md:25; recorder_internal.h:34-35 | MINOR |
| A4 | A failed line "appended again next pass". Header: step 7 of the same pass, after the drain | md:263; record_writer.h:145 | MINOR |
| A5 | Python index queues "each under its own Lock". Header Python form: "a collections.deque, whose append and popleft are atomic under the GIL" (no lock) | md:239; index_queue.h:4-5 | MINOR |
| A6 | The instance "1336 bytes measured". Measured now: 1408 | md:152; recorder_internal.h:50-58 | MINOR |
| A7 | "the headers of draft 14" named as current. The aggregate says draft 15 | md:143, md:150; recorder_aggregate_for_review.md:1 | NOTE |
| A8 | "the line buffer to twice the record bound". Header: 32768 = 4x; the assert is 2x + 1024 | md:211; record_writer.h:40, 119 | NOTE |
| A9 | OsEventSet, OsEventWait, OsEventClear, DieActionFn named. Not in the 16 headers; defined in 03-runtime | md:22, md:413; runtime_internal.h:82-84; runtime.h:18 | NOTE |
| A10 | "up to 8 job threads": no header constant. kFramePoolFrames = 8 counts slots | md:23; frame_pool.h:23 | NOTE |
| A11 | Functions never named in md: IndexQueueCreate/Destroy/Push/Pop/Front; SpscRecordQueueCreate/Destroy, SpscProducerPush, SpscProducerRecordsQueued/Dropped, SpscConsumerFront/Pop; FramePoolCreate/Destroy, FramePoolsCreate/Destroy; RecordFileCreate/WriteHeader/Close; ProducerPushEvent; FieldInt/Float/Bool/Text (only the Python field_int etc.) | index_queue.h:32-38; spsc_record_queue.h:37-66; frame_pool.h:64-65, 92-93; record_writer.h:68-74; recording_thread.h:93; record_field.h:87-90 | NOTE |
| A12 | Types never named in md: RecorderHealth, RecorderState, FrameSlot, FramePools, RecordSlot, RecordField, FieldType, FieldValue, TextValue, LineKind, LineText, DieReasonText, PathText, ProcessName, ThreadName, FolderName, FrameName, RecordTopic, FieldName, FieldCount, TextLength, RecordBytes, RecordKind, RecordCount, SlotIndex, SlotCount, RingPosition, ByteOffset, ByteCount, FileDescriptor, ThreadCount | recorder.h:75-85; recorder_internal.h:27-32; frame_pool.h:28-90; spsc_record_queue.h:19-89; record_field.h:11-63; record_file.h:23-34; record_writer.h:30-53; common_names.h:10-14; index_queue.h:12-13; recording_thread.h:32 | NOTE |
| A13 | Constants with neither name nor value in md: kWriterExpectedPassesPerMinute 30 (and the reserve formula); kRecordFolderBytes 64, kRecordNameBytes 32; kRingBytesPerRecordExpected 64; DieReasonText 256; PathText 256; ThreadName and ProcessName 32; SLOT_NONE; QUEUED_SPAN, QUEUED_EVENT; SPAN_STAGE_COUNT; LINE_KIND_COUNT | record_writer.h:42, 53; recorder_internal.h:60-62; record_frame.h:11-12; spsc_record_queue.h:75; common_names.h:10-12; index_queue.h:15; recording_thread.h:35-38 | NOTE |
| A14 | SPAN_ASR has no helper row and no home in section 11. SPAN_LLAMA_REQUEST appears only through RecordLlamaRequest | record_span.h:20, 22; md:431-450 | NOTE |
| A15 | The record_file.h key and format macros are never named. Their values match the sample lines: all 9 line kinds, every key | record_file.h:14-110; md:217-225 | NOTE |
| A16 | Who makes a PNG folder (the writer) is never said in md | record_file.h:16; record_writer.h:141 | NOTE |
| A17 | The mid-run refusal under the reserve has no failure-matrix row | record_frame.h:17; record_writer.h:146-148; md:260-274 | NOTE |
| A18 | "the event's png key": no such key in record_file.h; the section 3 pass event carries no png field | md:129, md:227, md:80-81; record_file.h:83-84 | NOTE |

## B. Decisions against headers

Findings:

| # | what | where | severity |
|---|---|---|---|
| B1 | RCD31: "RecorderCounters stays unpadded (40 bytes, one cache line)". Unpadded holds; size measured 28 | ledger:1055; recorder_internal.h:38-47 | MINOR |
| B2 | PY1: "no check-then-act on shared state unless one side alone can run ... or a lock is held". The free queue has many poppers, and Pop returns SLOT_NONE when empty (a check-then-act). The header's Python form names no lock | ledger:1041; index_queue.h:4-5, 36; frame_pool.h:49-51 | MINOR |
| B3 | TEL2: "drop, count (frames and records), one event, a chat line". No event per fault in any header; the writer never records. The amendment exists only in md:193, with no ruling | ledger:958; record_writer.h:1-5; md:193 | MINOR |
| B4 | RCD27: "the slot pool is MPSC under one lock". Header: two locks, one per IndexQueue. The two-lock form comes from RCD38 (the agent's fix pass, not an owner ruling) | ledger:1051, 1062; frame_pool.h:49-51 | NOTE |
| B5 | RCD34 B2: "If the destroy() can't wait for them ... drop them and count accordingly". A record left in a queue after the last drain, or at an abandoned Destroy, is neither written nor counted. Only "the app closes its modules first" covers it | ledger:1058; recorder.h:41-44; record_writer.h:153-158 | NOTE |

Rulings checked; each holds against the latest ruling unless listed above:

| ruling | the consequence (quoted, short) | header line | verdict |
|---|---|---|---|
| RCD1 | "one ambient record service per process (no handle returned, none passed)" | recorder.h:3 | holds; two rings superseded by RCD11, PY3; "one clock line" superseded by RCD11 |
| RCD2 | "FrameView (format, size, stride, pixels)"; "RecorderFrameConfig takes a FrameSize" | frame_types.h:20-25; recorder.h:20-22 | holds; FrameSize home by RCD5; names by RCD15; channel by RCD22 |
| RCD3 | "one instance and one file per process, the pid in the file name, the app the only frame channel" | record_file.h:14; recorder.h:24 | holds; RecordSample removed by RCD4 |
| RCD4 | "the timing record is a span only"; "nothing is timed on the GPU side" | record_span.h:16-33 | holds; the "gpu" event removed by RCD19 item 7 |
| RCD5 | "record_span.h, record_event.h and record_frame.h hold one contract each"; "frame_types.h holds FrameSize, PixelFormat and FrameView" | record_span.h:1; record_event.h:1; record_frame.h:1; frame_types.h:9-25 | holds; the clock moved by RCD19 (T1) |
| RCD6 | "sleeps on one wake-up object (OsEvent ...) with a 5 s timer"; "timer and counters are locals of its one function" | record_writer.h:27-28, 47, 150 | holds; "never by a span" superseded by RCD11 |
| RCD7 | "OsEvent (sticky, set, clear, timed monotonic wait) into runtime_internal.h; the mask limit per pass from config" | record_writer.h:23-26; frame_pool.h:20-21 | holds |
| RCD8 | "fixed_text.h (DEFINE_FIXED_TEXT)" | fixed_text.h:6-9 | holds; ring_buffer.h, slot_pool.h removed by RCD9 |
| RCD9 | "two endpoint types (SpscProducer, SpscConsumer)"; "index_queue.h ... under one lock"; "no per-slot state" | spsc_record_queue.h:26-43; index_queue.h:1-2, 23-29; frame_pool.h:5-6 | holds; offsets 0/64/128 superseded by RCD12 (64/128/192 measured) |
| RCD10 | proposals, OPEN | none | superseded by RCD11 |
| RCD11 | "FieldType int, float, bool, text, RecordField with a FieldValue union, the four makers"; "the watermark wake once per crossing at half"; "the clock line again at every fsync"; "the drop line with the gap" | record_field.h:36-63, 87-90; recording_thread.h:29, 100-102; record_writer.h:149; record_file.h:90-95 | holds; byte ring by RCD23, PY3; keys by RCD20; caps by RCD20, RCD36 |
| RCD12 | "restoring PRF4's cut rule on text fields"; "the normal pass with the die line"; "cached ring indexes deleted"; "one thread-table snapshot per pass"; "the ring's read-only fields off the index lines"; "FieldCount and TextLength"; "the makers validating in Python" | record_field.h:12-13, 83-86; record_writer.h:137, 153-155; spsc_record_queue.h:104-113 | holds; 8-byte rounding by RCD23; Struct by PY3 |
| RCD13 to RCD16 | "LINE_KIND_NAMES and SPAN_STAGE_NAMES as macros, RECORD_FILE_OPEN_FLAGS and RECORD_PNG_OPEN_FLAGS, EVENT_KEY_FIELDS ... mb_lastWriteFailed ... m_oldestReadyFramePublishedAt, unusedCtx" | record_file.h:14-17, 37-44, 81; recorder.h:48, 82; record_writer.h:107 | holds; m_registersRefused by RCD20; LineAwaitingRetry by RCD25 |
| RCD15 | "RecordingThread; ThreadProducer; MonotonicNs and MonotonicNow; DurationNs; SPAN_QUEUE_MESSAGE" | recording_thread.h:54-77; monotonic_clock.h:9-12; record_span.h:19 | holds |
| RCD17 | "raised to 31 callers' fields plus the cut field"; "the ringless counter is for a failed allocation" | record_field.h:24-25; record_writer.h:86-87, 111-112 | holds; the 33rd thread is the 17th by RCD19 |
| RCD18 | "push ..., peek and release, drop-new counted, a fill for the watermark" | spsc_record_queue.h:46-66 | holds; bytes deque by PY3 |
| RCD19 | "LINE_TIME_REFERENCE, "time", monotonic_ns, wall_us, boot_ns"; "the recorder's cap is 16 ... a 17th thread ... dies"; "monotonic_clock.h, frame_types.h and common_names.h in 00-util"; "the GPU event dropped" | record_file.h:24, 38, 53-57; recording_thread.h:20-27; 00-util | holds |
| RCD20 | "FieldName and RecordTopic are const char* to literals"; "the caller's field cap is 31 plus the cut field" | record_field.h:11, 24-25; record_event.h:9 | holds; packed headers by RCD23 |
| PY1 | "the C headers keep real atomics with their orderings" | spsc_record_queue.h:95-97, 110-112; recording_thread.h:43-47 | holds; see B2 |
| GIL2 | "the sixteen recording threads are the app's working threads, none exists to record" | recording_thread.h:1-3 | holds |
| PY2 | "Numpy stays for the frame pixel copy" | no Python note in frame_pool.h | no header consequence (md:239) |
| PY3 | "a collections.deque of record tuples bounded by a count; a span is (stage, start, end, names, values)" | spsc_record_queue.h:5-6; record_field.h:78-81; record_span.h:36 | holds |
| RCD21 | "recording_thread.h (Producer* ...)", "record_writer.h (Writer* ...; and RecordFile* ...)", "recorder_internal.h (the instance, its state, its counters)" | recording_thread.h:83-102; record_writer.h:62-74, 123-160; recorder_internal.h:27-58 | holds; packed_record.h by RCD23 |
| RCD22 | "Create and Destroy everywhere"; "SpscConsumerFront and Pop"; "maxRecords"; "kRingBytesPerRecordExpected"; "IndexQueueFront"; "FramePoolClaimFreeSlot, PublishSlot (the stamp taken inside), OldestReadySlot, ReleaseSlot"; "m_queueEnds"; "WriterIsStalled takes no stamp" | spsc_record_queue.h:37-66, 75; index_queue.h:32-38; frame_pool.h:64-75; record_writer.h:110, 133 | holds; ForFormat, the registry by RCD23 |
| RCD23 | "a ring of record slots (offset, length, kind) and a separate byte area; full means no free slot or no free bytes"; "RecordFrame picks the pool by format"; "RecordFileCreate takes the session folder and the process name"; "m_queues, m_queueEnds, m_queueCount" | spsc_record_queue.h:84-97; record_frame.h:19; record_writer.h:68, 108-110 | holds; "the line lost" by RCD25 |
| RCD25 (W1) | "a bounded retry queue of 64 lines (two index queues over LineText slots) ... appended again ... oldest first, until one fails; a full retry queue drops, counted" | record_writer.h:41, 83-86, 114-116, 145 | holds |
| RCD24, RCD26, RCD28 to RCD30 | the drawings | none | no header consequence |
| RCD27 | "a notify during a pass causes one more pass" | record_writer.h:151-152 | holds; see B4 |
| RCD31 | "stays unpadded" | recorder_internal.h:34-37 | holds; see B1 |
| RCD32, RCD33 | the conditions; the themes. Checked: retry storage, "p" and "info", 16384, no m_droppedKeys, no "precompiled", nine steps, WRITER_STALL_NS | record_writer.h:49, 114-116, 136-152; record_file.h:64, 81; recording_thread.h:28 | holds |
| RCD34 | B1 "no gpu event anywhere"; B2 "dropped and counted"; A1 "RecorderCreate makes <sessionDir>/asr_clips/ (mkdir, EEXIST allowed)" | no gpu in any header; recorder_internal.h:21; recorder.h:26-28, 42-43 | holds; see B5, E3 |
| RCD35 | "kRecordQueueRecords = 16384"; "RecordResult ... returned by RecordSpan, RecordEvent and RecordFrame"; DEGRADED gone | recording_thread.h:28; record_field.h:70-76; record_span.h:40; record_event.h:12; record_frame.h:24 | holds |
| RCD36, RCD37 | "kRecordMaxRecordBytes = 8192"; ""length" removed; "cut" (the bytes lost) stays on a truncated record only; kRecordMaxFields = the caller's 31 plus 1"; JSON lines stay | record_field.h:24-31; record_file.h:2 | holds |
| RCD38 | the 20 header fixes | record_writer.h:40, 70, 111-119, 151-158; recorder.h:32-37; recording_thread.h:61-62, 74; frame_pool.h:49-51; record_frame.h:2; recorder_internal.h:3-7; common_names.h:14 | holds, 20 of 20 |
| PRF1 | "the stage becomes an enum ...; the file keeps the stage's name as text" | record_span.h:16-33; record_file.h:41-44 | holds |
| PRF2 | "the app holds every start timestamp" | record_span.h:40-46 | holds; the 128-byte record by RCD11 |
| PRF3 | "PerfCreate(sessionDir, processName)"; "the lifetime comment" | recorder.h:1-6, 34-39 | holds; bytearray by PY3 |
| PRF4 | "the 33rd thread is a bug and dies (RVW4), no drop branch" | recording_thread.h:21-22 | holds (17th by RCD19); PERF_GPU removed by RCD19 |
| PRF5 | "the table size is a config constant of the design's thread count" | recording_thread.h:20-21, 27 | holds |
| PRF6 | "step 3 ... of Die" | recorder.h:46 | holds |
| PRF7 | "no module holds a tracer handle" | recorder.h:3 | holds |
| TEL1 | "Logger deep-copies" | record_field.h:44-45; record_frame.h:19-21 | holds; the opaque logger by RCD1 |
| TEL2 | "no path ... calls die()"; "count" | recorder.h:76-78 | the 17th-thread die by RCD19; see B3 |
| TEL3, TEL4 | a generic sink; helpers in the owners | record_event.h:9-17 | holds; the JSON payload by RCD20 |
| TEL5, TEL13, TEL16 | "the source's resolution; PNG level 1 for frames and masks" | record_frame.h:1-2; recorder.h:19-22 | holds |
| TEL7 | "full rings and pools drop and count" | spsc_record_queue.h:46; frame_pool.h:68 | holds; the pause superseded by RCD25 (W1) |
| TEL9, TEL14, TEL17 | "bytes = W x H x 3 x 0.45 x 30 passes a minute x minutes; ... 40 minutes, ... 5 minutes" | record_writer.h:42-44, 50; recorder_internal.h:60-62 | holds |
| TEL10 | "fsync the trace every 5 s"; "the stall rule computed at read" | record_writer.h:48, 131-133 | holds |
| TEL11, TEL12 | "PNG 0.45 of raw"; "the 64-bit and float values as macros" | record_writer.h:47-50 | holds; the poll by RCD6; 4 KiB by RCD36 |
| TEL18 | "the free-space product computed in uint64_t" | recorder_internal.h:62; record_writer.h:31 | holds |
| TEL6, TEL8, TEL15, TEL19 | rounds, approval | none | no header consequence |
| RVW3 | "a job acquires its slot ... releases after the reply" | record_frame.h:19-21 | holds |
| RVW4, RVW6, RVW7 | "one tracer, a ring per thread"; "tracing per process and per thread, merged at the end" | recording_thread.h:1-5, 21-22; record_file.h:14 | holds; RVW5's shared memory superseded by RVW6, RVW7 |
| RVW1, RVW2, RVW5 | the system review | none | no header consequence |
| REV7, REV8 | gate item 12 | none | no header consequence |
| RUN3 | "typed function pointers" | recorder.h:46-48 | holds |
| FB8 | the performance tie-breaker | recorder_internal.h:34-37 | holds via RCD31 |

## C. Decisions against document

| # | what | where | severity |
|---|---|---|---|
| C1 | PRF4 cited for drop-new and the cut rule. PRF4's consequence names neither. RCD12 attributes the cut rule to PRF4; drop-new is TEL7 | md:137, md:321, md:358; record_field.h:84; ledger:956 | MINOR |
| C2 | RCD12 cited for drop-new. RCD12's consequence is the cut rule, the pass, the cached indexes | md:268; ledger:1032 | MINOR |
| C3 | TEL2 amended ("no one event per fault") with no ruling. TEL2: "one event, a chat line" | md:193; ledger:958 | MINOR |
| C4 | "a record pushed after the last pass stays in its queue, counted as queued, never written". RCD34 B2: "drop them and count accordingly" | md:246; ledger:1058 | MINOR |
| C5 | record_span and record_event called with field makers on the hot path. PY3: "a span is (stage, start, end, names, values)"; the header: makers "only for odd shapes" | md:71, md:80-81, md:88; ledger:1044; record_field.h:78-81 | MINOR |
| C6 | Stall row cause "(TEL, the owner's)": no row ID. REV8 asks for the cause. The stall rule is TEL10 | md:264; ledger:969, 1014 | NOTE |
| C7 | OPEN 1 cited for MonotonicNs and MonotonicNow. OPEN 1 (RCD2) named RecorderTimestamp and RecorderNow; the names are RCD15's | md:98, md:416; ledger:1022, 1035 | NOTE |
| C8 | Shared-mutex deque 429 ns, notify 758 ns. RCD22: 264 and 593 net, own deque 94 net. The clock offsets differ (56 against 165 ns): two runs, not reconciled | md:279-281; ledger:1046 | NOTE |
| C9 | "about 250 a drain". RCD35: "the normal fill of 200 records" | md:132; ledger:1059 | NOTE |
| C10 | "clock line" in section 10's "us" column, with no superseding ruling named. RCD19 item 1 retired the term | md:360, md:387; ledger:1039 | NOTE |

## D. The document against itself

| # | what | where | severity |
|---|---|---|---|
| D1 | A helper's home: "that module's record_<owner>.h" against "its owner's header", RecordLlamaRequest in llama_server.h, RecordVideoRow in frame_source_internal.h | md:91; md:430, md:437, md:450 | MINOR |
| D2 | Two Python forms of record_span: names and values tuples, against a tuple of field makers | md:51; md:71, md:88 | MINOR |
| D3 | "no lock" on the record path, against "set 332 ns (it takes a lock)" and "takes the event's own lock once per crossing" | md:20, md:202; md:173, md:236 | MINOR |
| D4 | Test 21: "a second Create on the same file name fails". Test 22: "a second Create after Destroy succeeds". Same process, name and pid give the same file under O_EXCL; neither test changes the folder | md:340-341 | MINOR |
| D5 | The helper "builds no text", against field_text("boxes", boxes_json(reply)) inside the helper | md:38, md:93; md:81 | NOTE |

Values checked and held in every current-state place: the thread cap 16, the 17th dies (md:20, 136, 193, 203, 273, 326, 426); the queue 16,384 (md:123, 268, 293, 321); the pools 8 and 24 (md:23, 134, 265); the retry queue 64 (md:461); the wake sources: half full, a frame, Destroy, Die, the 5 s timer (md:22, 131, 304); the file name record-<process>-<pid>.jsonl (md:27, 99, 120, 423); "cut" = the bytes lost (md:123, 204, 269, 322); the session folder made by the app, asr_clips/ by RecorderCreate (md:29, 207, 455).

## E. The headers against themselves

| # | what | where | severity |
|---|---|---|---|
| E1 | "One writer per transition ... the writer stores STOPPED", against "Destroy stored STOPPED itself". STOPPED has two writers. An abandoned writer's late store can overwrite a re-Create's RUNNING | recorder_internal.h:21-26; record_writer.h:157-158; recorder.h:32-33 | MINOR |
| E2 | Destroy "waits ... then joins it", against "abandons the writer" when the deadline passes. One sentence also says "Destroy and FlushInDie ... never join; only Destroy joins" | recorder.h:41; record_writer.h:156-158 | MINOR |
| E3 | Before Create: "a no-op", against "any state but RUNNING is dropped and counted". The result: DROPPED "not RUNNING" against NOT_CREATED "a call before Create" | recorder_internal.h:20-21; record_field.h:67-69; record_span.h:38-39 | MINOR |
| E4 | The producer's path says "Never a lock". It ends in the half-full wake, which sets a condition variable; the set takes its mutex | recording_thread.h:80, 100-102; record_writer.h:23-25; runtime_internal.h:78-82 | MINOR |
| E5 | "A second Create after Destroy is allowed", against the file name (process, pid) opened with O_EXCL: the same folder and name give EEXIST | recorder.h:32-33; record_file.h:14-15; record_writer.h:57-58 | MINOR |
| E6 | The last pass runs "steps 7 and 9", but step 9 runs only "every WRITER_FLUSH_TO_DISK_EVERY_NS". record_file.h puts a time reference and a health line after the die line every time | record_writer.h:149, 153-155; record_file.h:21-22 | MINOR |
| E7 | The die line "before its final frame lines". WriterRun writes step 6's frame lines first, then the die line; only the deadline loop's frames follow | record_file.h:21-22; record_writer.h:153-155 | NOTE |
| E8 | Public recorder.h comments name kWriterFlightMinutes, WRITER_STALL_NS and kWriterReserveMinutes, which it does not include | recorder.h:32, 69, 73; record_writer.h:43-49 | NOTE |
| E9 | Two drop counts per thread: the queue's m_dropped, and RecordingThread's m_droppedSpans and m_droppedEvents. No comment says which one feeds the health | spsc_record_queue.h:55, 112; recording_thread.h:57-58; recorder_internal.h:34-35 | NOTE |
| E10 | The DROPPED causes in record_field.h leave out "the free space under the reserve", which record_frame.h adds | record_field.h:66-67; record_frame.h:17 | NOTE |
| E11 | Whether a retry that fails again is counted again in failed_writes is not stated | record_writer.h:59-61, 145; recorder.h:64-65 | NOTE |
