# Recorder consistency check, round 4, checker 2 (2026-10-21)

**Verdict: NOT CONSISTENT. 41 findings: 1 BLOCKING, 17 MINOR, 23 NOTE.**

Sources: 16 headers (00-util 6, 01-recorder 10); runtime_internal.h:78-86 (OsEvent); recorder.md; docs/spec-harden2-cleanup.md rows PRF1-7, TEL1-19, RVW1-7, REV7, REV8, RUN3, RCD1-40, PY1-3, GIL2.
Compile: all 10 recorder headers pass `gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11`, with no output.
Aggregate: all 16 headers appear verbatim in recorder_aggregate_for_review.md (checked by script).
Measured with gcc: SpscRecordQueue 256 B (head 64, tail 128, dropped 192); RecorderCounters 28 B; struct Recorder 1408 B. These match recorder.md:153, recorder.md:305 and RCD31.
OPEN items P1, P2 and P3 (recorder.md:134-136) are not counted.

## A. Document vs headers

| # | what | where | severity |
|---|---|---|---|
| A1 | Doc: static_assert pins line buffer to "twice the record bound plus 1 KiB". Header: `6 * kRecordMaxRecordBytes + 4096` | recorder.md:212; record_writer.h:128 | MINOR |
| A2 | Doc: "A wrong-typed value in Python: drop, count, no try". Header: the tuple path has no type check; any other value is written as its text; nothing raises. Doc test 5 agrees with the header | recorder.md:205; record_field.h:86-89; recorder.md:327 | BLOCKING |
| A3 | SAM3 sample ignores RecorderCreate's false. Header: "the caller dies at start" | recorder.md:83; recorder.h:31-32 | MINOR |
| A4 | Doc: "only it touches the file" / "written by its one writer thread". Header: Create writes the time reference and info lines from the caller's thread, before the writer exists | recorder.md:33, 208; recorder.h:28-29; record_writer.h:61, 72-73 | MINOR |
| A5 | Drawing 3: the writer "resets, passes, checks the flag again". Header: "nothing is checked at the end of a pass" | recorder.md:22; record_writer.h:165 | MINOR |
| A6 | The header says the writer makes a frame's folder. The doc never says who makes it (it names only the session folder and asr_clips/) | record_file.h:16; record_writer.h:150; recorder.md:23, 29, 458 | NOTE |
| A7 | No current-state text for a thread that got no queue (mb_queueTried, m_dropped*WithoutQueue, DROPPED "no queue"). It appears only in history rows D2 and D4 | recording_thread.h:71-72; record_writer.h:95-96, 120-121; record_field.h:67-68; recorder.md:158-160 | NOTE |
| A8 | RecorderHealth is never named; the doc says only "nine values" | recorder.h:87-99; recorder.md:62 | NOTE |
| A9 | RecorderNameThisThread appears only in a section 4 history row, not in sections 2, 3, 7 or 11 | recorder.h:57; recorder.md:173 | NOTE |
| A10 | index_queue.h never named: IndexQueueCreate, IndexQueueDestroy, IndexQueuePush, IndexQueuePop, IndexQueueFront, SlotIndex, SlotCount, SLOT_NONE | index_queue.h:12-38 | NOTE |
| A11 | spsc_record_queue.h never named: SpscRecordQueueCreate, SpscRecordQueueDestroy, SpscProducerPush, SpscProducerRecordsQueued, SpscProducerRecordsDropped, SpscConsumerFront, SpscConsumerPop, RecordSlot, RingPosition, ByteOffset, RecordBytes, RecordKind, kCacheLineBytes, kRingBytesPerRecordExpected (64 B of byte area per slot) | spsc_record_queue.h:19-113 | NOTE |
| A12 | frame_pool.h and record_frame.h never named: FramePoolCreate, FramePoolDestroy, FramePools, FramePoolsCreate, FramePoolsDestroy, FrameSlot, FolderName, FrameName, the kFramePool* names. kRecordFolderBytes 64 and kRecordNameBytes 32: no value given in the doc | frame_pool.h:22-93; record_frame.h:10-13 | NOTE |
| A13 | record_field.h never named: FieldInt, FieldFloat, FieldBool, FieldText, FieldType, FieldValue, TextValue, FieldName, FieldCount, TextLength, RecordField, FIELD_NAME_CUT, kRecordMax* (the values are described) | record_field.h:11-94 | NOTE |
| A14 | record_writer.h never named: RecordFileCreate, RecordFileWriteHeader, RecordFileClose, LineText, DieReasonText (256), FileDescriptor, ByteCount, kWriterRetryLines, the WRITER_*_NS names. kWriterLineBytes (64 KiB) and kWriterExpectedPassesPerMinute (30): no value given in the doc | record_writer.h:30-76 | NOTE |
| A15 | Never named: ProducerPushEvent, QUEUED_SPAN, QUEUED_EVENT, ThreadCount, kRecordQueueRecords, kRecordQueueWatermark; RecorderState and its enumerators; the record_file.h macros (shown only as sample lines); PathText, ProcessName, ThreadName, RecordCount | recording_thread.h:26-38, 98; recorder_internal.h:29-34; record_file.h:14-112; recorder.md:218-226; common_names.h:10-14 | NOTE |

## B. Decisions vs headers (latest ruling)

| # | what | where | severity |
|---|---|---|---|
| B1 | PY1: "no check-then-act on shared state unless one side alone ... or a lock is held". m_stopDeadline is set by Destroy's compare-and-swap from 0 and by Die's unconditional store. The Python form is stated only for the oldest-ready stamp's two compare-and-swaps, not for this one | spec:1041; record_writer.h:81-83, 88-89 | MINOR |
| B2 | PY1 and recorder.h's "no counter has two writers": m_droppedSpansWithoutQueue and m_droppedEventsWithoutQueue are incremented by every thread that has no queue | recorder.h:67-69; record_writer.h:120-121 | MINOR |
| B3 | RCD39/RCD40: "the records left queued after the final drain are added to the dropped counts". The header does not say which counter. If it is the thread entry, that entry has a second writer next to a live producer. If it is the health counter, the next Create's first summing pass overwrites it. recorder.h also says a slot still ready at the deadline is "counted in the job thread's own entry", but the writer counts it | record_writer.h:169-172; recorder.h:70-73 | MINOR |
| B-ok | Implemented as ruled. PRF1: SpanStage plus SPAN_STAGE_NAMES (record_span.h:16-33; record_file.h:42-45). PRF5: cap 16, never nproc (recording_thread.h:20-27). PRF7, RCD1: ambient, no handle (recorder.h:3). RUN3: FlushInDie fits DieActionFn (recorder.h:50-52; runtime.h:18) | as cited | OK |
| B-ok | RVW4, RCD19 item 2: the 17th thread dies (recording_thread.h:21-22). RVW7: one file per process, pid in the name (record_file.h:14). TEL5, TEL13, TEL16: lossless PNG level 1, frames and masks (record_frame.h:1-2). TEL10: stall computed at read (record_writer.h:140-142) | as cited | OK |
| B-ok | TEL17: 30 passes a minute, 40 and 5 minutes, ratio 0.45, uint64 bytes (record_writer.h:44-46, 52; recorder_internal.h:62-64). TEL12: 64-bit and float values as macros (record_writer.h:49-52). TEL14: no codec, no knob, no blob call | as cited | OK |
| B-ok | RCD4, RCD19 item 7, RCD34 B1: no sample, no GPU (grep: no "gpu" in any header). RCD5, RCD19 T1: frame_types.h, monotonic_clock.h, common_names.h. RCD6, RCD7: OsEvent in runtime_internal.h:78-86; timer and counters are locals (record_writer.h:159); mask limit read from config (frame_pool.h:20-21) | as cited | OK |
| B-ok | RCD9: SPSC endpoints (spsc_record_queue.h:24-32); head, tail and drop count on their own lines (measured 64/128/192); pool is two index queues with no per-slot state (frame_pool.h:5-6, 56-61) | as cited | OK |
| B-ok | RCD11, RCD12: typed fields, four makers, watermark at half (recording_thread.h:29), time reference again at every fsync, drop gap, one snapshot (step 2), no cached index (spsc_record_queue.h:96-97) | as cited | OK |
| B-ok | RCD20 (K1): literal names (record_field.h:11; record_event.h:9). PY3 (Q1): tuple deque (spsc_record_queue.h:5-6; record_field.h:80-83). RCD21-23: actor headers; ring of record slots plus byte area; RecordFileCreate(sessionDir, process); queue list in the Writer (record_writer.h:117-119) | as cited | OK |
| B-ok | RCD25 (W1): 64-line retry queue under two index queues; step 7 (record_writer.h:43, 92-96, 123-125, 154). RCD27: every pass walks every queue and both pools; a set during a pass gives one more pass (record_writer.h:148-165). RCD31: unpadded, 28 B (recorder_internal.h:36-39) | as cited | OK |
| B-ok | RCD34: dropped and counted outside RUNNING (recorder_internal.h:20-22); asr_clips/ with EEXIST allowed (recorder.h:26). RCD35: 16384 entries; RecordResult returned by all three calls. RCD36, RCD37: 8192 bytes, "cut" only, no "length", 31+1 fields (record_field.h:23-31) | as cited | OK |
| B-ok | RCD39, RCD40: OsEventIsSet (runtime_internal.h:85); a folder of two names; ok false; NOT_CREATED counts nowhere; publish compare-and-swap from 0; 64 KiB buffer with assert 6x+4K; leftovers popped; Create resets the stopped flag and the die reason (recorder.h:33-35) | as cited | OK |
| B-open | RCD27 "one lock" (P1); TEL2 "one event" (P2); RCD30 loop drawing (P3) | recorder.md:134-136 | OPEN |

## C. Decisions vs document

| # | what | where | severity |
|---|---|---|---|
| C1 | PNG clash cause: "a pass number reused after a re-Create in the same folder". RCD39: a second Create needs a new session folder. recorder.md:273 itself says a re-Create in the same folder fails. As stated, the cause cannot occur | recorder.md:274; spec:1063; recorder.h:32-34 | MINOR |
| C2 | Item 3 contradicts RCD40 "the tuple path has no type check and nothing raises". Counted once, as A2 | recorder.md:205; spec:1064 | (=A2) |
| C3 | PRF4 cited for the "cut":N rule. PRF4's consequence has no cut rule (RCD12 credits it to PRF4) | recorder.md:137; spec:956 | NOTE |
| C4 | PRF4 cited for drop-new at the bound. PRF4's consequence covers the fill time and the cost; drop-new is TEL7 | recorder.md:324; spec:956, 966 | NOTE |
| C5 | TEL16 cited for the PNG ratio. TEL16 covers the resolution and PNG level 1; the 0.45 is TEL11, TEL14 and TEL17 | recorder.md:431; spec:975 | NOTE |

## D. Internal consistency of the document

| # | what | where | severity |
|---|---|---|---|
| D1 | Item 2 says the 17th-thread die is "a change against TEL2, in section 4's table". The change table has no such row; it is only in the failure matrix | recorder.md:204; recorder.md:116-136, 275 | MINOR |
| D2 | Wrong-typed value: "drop, count" (item 3) against "written as its text" (test 5) and "the makers check" (mapping). Counted once, as A2 | recorder.md:205, 238, 327 | (=A2) |
| D3 | Two failure-matrix rows for the 17th recording thread | recorder.md:275-276 | NOTE |
| D4 | Two change-table rows titled "the writer's wake" | recorder.md:123, 129 | NOTE |
| D5 | History change 2 gives "the measured 437 ns of a Python span". Current text: the pre-R4 span was 723 to 804 ns. The disclaimer does not name this number | recorder.md:385-386; recorder.md:295, 234 | NOTE |
| D-ok | Each value is stated the same way everywhere: cap 16; queue 16,384; pools 8/24; retry 64; wake (half full, frame, Destroy, Die, 5 s); file name; nine steps; "cut" = bytes lost; app makes the session folder and Create makes asr_clips/; per-thread drop counts summed by the writer | sections 2, 4, 6, 7, 8, 9, 11 | OK |

## E. Internal consistency of the headers

| # | what | where | severity |
|---|---|---|---|
| E1 | The comment says "eight times the bound always fits (the static_assert below)". The assert checks six times plus 4096 | record_writer.h:33-37, 128 | MINOR |
| E2 | The writer's end-of-pass compare-and-swap names no new value. If the pass started non-zero, a frame published after step 6 fails its own compare-and-swap from 0 and is then erased. This contradicts "never erased" | record_writer.h:85-88; record_frame.h:25-26 | MINOR |
| E3 | Drop gap. The writer loads count, first, last; acquire on the count does not stop it reading the next gap's first and last. A gap with no successful push in between keeps its old "from" into the next drop line, against "since its last drop line" | recording_thread.h:43-47, 72; record_file.h:92 | MINOR |
| E4 | A retried line is appended in step 7, after later lines of the same pass. A retried thread line or time reference line then lands after the lines it must precede | record_writer.h:92-95, 154; record_file.h:3-4, 19-21 | MINOR |
| E5 | m_dieReason is a plain char array. Die writes it while the writer may read it during a Destroy's last pass ("Die wins"). The race is not covered; only the deadline's order is stated | record_writer.h:81-82, 114, 166-167; recorder.h:51 | MINOR |
| E6 | The comment says "the makers ... return INVALID_ARG". The makers return RecordField | record_field.h:89-90, 91-94 | MINOR |
| E7 | Create's reset list omits RecorderCounters, the threads' drop and reported counts, the queueless counts and both stamps. The new file's health then carries the last session's drops | recorder.h:33-35; recorder_internal.h:26-28 | MINOR |
| E8 | A dropped frame is counted "in the job thread's own entry". A thread gets its entry only at its first RecordSpan or RecordEvent, so a frame drop before that has no counter | recorder.h:70-73; recording_thread.h:1-4, 40-41 | MINOR |
| E9 | Two counts for one dropped record: the queue's m_dropped and the thread's m_droppedSpans/m_droppedEvents. Nothing reads SpscProducerRecordsDropped | spsc_record_queue.h:46, 55, 112; recording_thread.h:60-61 | NOTE |
| E10 | Unstated: how a thread claims its index (m_queueCount) and who writes m_queueEnds[i]. Unstated: whether the cap of 16 counts threads alive or ever created (no slot is reclaimed on thread exit) | record_writer.h:90-91, 117-119; recording_thread.h:20-22 | NOTE |
| E11 | The last pass's first step 6 (inside "steps 2 to 6") has no deadline bound. record_file.h says the frames stop at the deadline | record_writer.h:166-169; record_file.h:21-23 | NOTE |
| E12 | Step 9's health line comes before the end-of-pass sums, so it carries the previous pass's sums. The last health line misses the final pass's drops and the leftover counts | record_writer.h:158-162, 166-172 | NOTE |
| E13 | Python cuts text fields to fit, but its tuple path "has no type check". How it finds the text fields and their UTF-8 lengths is unstated | record_field.h:84-90 | NOTE |
| E14 | A failed append is counted, then counted again if a full retry queue drops it. Unstated whether a failed re-append in step 7 is counted | record_writer.h:62, 94-95, 154; recorder.h:75-76 | NOTE |
| E15 | m_droppedSpans/m_droppedEvents list only "too many fields" as INVALID_ARG. record_field.h also counts "a bad value" INVALID_ARG in the health | recorder.h:64-66; record_field.h:68-71 | NOTE |
| E-ok | gcc on all 10 recorder headers: clean. Every type used is defined or forward-declared (OsLock, OsThread, OsEvent repeated typedefs, legal in C11). No constant has two values. LINE_KIND_NAMES 9 = LineKind 9; SPAN_STAGE_NAMES 15 = SpanStage 15 | all headers | OK |
