# Recorder consistency check, round 2, checker 3

**Verdict: NOT CONSISTENT. 43 findings: 3 BLOCKING, 19 MINOR, 21 NOTE.**

Sources: the 16 headers (00-util x6, 01-recorder x10); recorder.md (461 lines); the ledger
docs/spec-harden2-cleanup.md (rows 908-1062). Paths below: `md` = 01-recorder/recorder.md;
`.h` paths are relative to docs/api-harden2/rev5/modules/; `ledger` = docs/spec-harden2-cleanup.md.

Mechanical checks (not findings):
- gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11, all ten 01-recorder headers: 0 errors, 0 warnings.
- recorder_aggregate_for_review.md: all 16 headers present verbatim.
- Measured (gcc, x86-64): sizeof(struct Recorder) 1408; RecorderCounters 28; SpscRecordQueue 256
  (head 64, tail 128, dropped 192); RecordingThread 384; Writer 656.

## A. Document vs headers

| # | what | where | severity |
|---|---|---|---|
| A1 | Pass step 2 differs. md: step 2 = "reset the flag"; "yes: step 2". Header: step 1 = wait + clear; step 2 = queue-list snapshot. "Resume at step 2" means different things | md:21; 01-recorder/record_writer.h:136-137,151-152 | BLOCKING |
| A2 | Sample frame line folder "perception/0001-highlight" holds a path separator; the header returns INVALID_ARG for that | md:222; 01-recorder/record_frame.h:15-17 | BLOCKING |
| A3 | Sample `recorder_create(dir, "app", RecorderFrameConfig(FrameSize(..), models_json))` (3 args, info inside the config); `recorder_create(dir, "sam3", None)`. Header: 4 args, infoJson separate, config holds m_size only | md:42,84; 01-recorder/recorder.h:20-22,34-39 | MINOR |
| A4 | "draft 14 has seven ... 1336 bytes measured". Measured sizeof(struct Recorder) = 1408 | md:150-152; 01-recorder/recorder_internal.h:50-58 | MINOR |
| A5 | Test 4: "33 fields returns INVALID_ARG". Caller cap is 31; 32 already invalid; boundary not pinned | md:323; 01-recorder/record_field.h:24-25 | MINOR |
| A6 | Failure matrix: failed line "appended again next pass". Header: step 7 of the same pass retries it | md:263; 01-recorder/record_writer.h:139,145 | MINOR |
| A7 | Drawing 3 names OsEventSet, OsEventWait, OsEventClear: not in the 16 headers (only in 03-runtime/runtime_internal.h:82-84); record_writer.h has the opaque type only | md:22; 01-recorder/record_writer.h:23-28 | NOTE |
| A8 | "up to 8 job threads", "Eight threads": no header constant; 8 is the slot count | md:23,303; 01-recorder/frame_pool.h:23 | NOTE |
| A9 | "line buffer to twice the record bound". Header: >= 2 x 8192 + 1024; value 32768 never stated in md | md:211; 01-recorder/record_writer.h:40,119 | NOTE |
| A10 | kWriterExpectedPassesPerMinute = 30 and WRITER_PNG_BYTES_PER_RAW_BYTE = 0.45: values never stated; md gives "4 to 32 passes a minute" only | 01-recorder/record_writer.h:42,50; md:196-197,428 | NOTE |
| A11 | kRingBytesPerRecordExpected = 64 (byte area per slot): not described | 00-util/spsc_record_queue.h:73-76,94 | NOTE |
| A12 | QUEUED_SPAN / QUEUED_EVENT kind byte: not described | 01-recorder/recording_thread.h:34-38 | NOTE |
| A13 | kRecordFolderBytes 64, kRecordNameBytes 32: md says "length" only, in a HISTORY row | 01-recorder/record_frame.h:10-13; md:161-162 | NOTE |
| A14 | RecorderNameThisThread: named only in a HISTORY row; absent from sections 2, 3, 7, 11 | 01-recorder/recorder.h:50-53; md:172 | NOTE |
| A15 | C makers FieldInt/FieldFloat/FieldBool/FieldText never named (md uses Python field_int etc.) | 01-recorder/record_field.h:87-90 | NOTE |
| A16 | Stop-deadline rule (CAS from 0; Die unconditional; Create stores 0): described only in a HISTORY row | 01-recorder/record_writer.h:78-80; md:161 | NOTE |
| A17 | Queueless-thread path (mb_queueTried, m_droppedSpansWithoutQueue/EventsWithoutQueue): md only in HISTORY D2/D4, which says "the thread table" | 01-recorder/recording_thread.h:67-68,75; 01-recorder/record_writer.h:111-112; md:157-159 | NOTE |
| A18 | Never named in md: SLOT_NONE, IndexQueue*, Spsc* functions, FramePoolCreate/Destroy, FramePoolsCreate/Destroy, RecordFileCreate/WriteHeader/Close, LineKind, RecordSlot, RingPosition, DieReasonText (256), aligned_alloc(64) | 00-util/index_queue.h:15,32-38; 00-util/spsc_record_queue.h:37-66,70,84-89; 01-recorder/frame_pool.h:64-93; 01-recorder/record_writer.h:53,68-74; 01-recorder/recording_thread.h:41 | NOTE |
| A19 | Frame line sample `"ok":1`; health booleans are true/false; header gives no type for FRAME_KEY_OK | md:222,224; 01-recorder/record_file.h:88 | NOTE |

## B. Decisions vs headers

| # | what | where | severity |
|---|---|---|---|
| B1 | RCD1/PRF7 "one ambient record service ... no handle": "Ambient: created once per process, no handle" | ledger:1021,1018; 01-recorder/recorder.h:3 | OK |
| B2 | RCD2 FrameView; RecordFrame(channel..) superseded by RCD22 (folder): RecordFrame(folder, name, at, FrameView*) | ledger:1022,1046; 01-recorder/record_frame.h:24-29 | OK |
| B3 | RCD3 "the pid in the file name ... session folder made before any child" | ledger:1023; 01-recorder/record_file.h:14; 01-recorder/recorder.h:27-28 | OK |
| B4 | RCD4 no sample contract (gpu event superseded by RCD19, RCD34 B1): spans only; no gpu anywhere | ledger:1024; 01-recorder/record_span.h:16-33 | OK |
| B5 | RCD5 the split; frame_types.h holds FrameSize, PixelFormat, FrameView | ledger:1025; 00-util/frame_types.h:9-25 | OK |
| B6 | RCD6/RCD7 OsEvent "(sticky, set, clear, timed monotonic wait)", 5 s timer; mask limit from config | ledger:1026-1027; 01-recorder/record_writer.h:23-28,47; 01-recorder/frame_pool.h:20-25 | OK |
| B7 | RCD9 typed endpoints, head/tail/drop on own lines, index queue, pool = two index queues | ledger:1029; 00-util/spsc_record_queue.h:26-32,110-112; 01-recorder/frame_pool.h:56-61 | OK |
| B8 | RCD12 cut rule; last pass = normal pass + die line; drop-gap protocol; one snapshot per pass | ledger:1032; 01-recorder/record_field.h:82-84; 01-recorder/record_writer.h:137,153-155; 01-recorder/recording_thread.h:43-47 | OK |
| B9 | RCD15/RCD16 record_file.h: name pattern, PNG path, kinds, keys, LINE_KIND_NAMES, SPAN_STAGE_NAMES, open flags | ledger:1035-1036; 01-recorder/record_file.h:14-17,37-44 | OK |
| B10 | RCD17/RCD20/RCD37 "31 plus the cut field"; literals; 8192; "length" removed | ledger:1037,1040,1061; 01-recorder/record_field.h:11,24-31 | OK |
| B11 | RCD18 then PY3 "deque of record tuples bounded by a count" | ledger:1038,1044; 00-util/spsc_record_queue.h:5-6 | OK |
| B12 | RCD19 "cap is 16 ... a 17th thread ... dies"; T1 util headers | ledger:1039; 01-recorder/recording_thread.h:20-27; 00-util/ | OK |
| B13 | PY1 built-in container or lock; GIL2 "none exists to record" | ledger:1041-1042; 00-util/index_queue.h:4-5; 01-recorder/recording_thread.h:2-3 | OK |
| B14 | RCD21/RCD22 one header per actor, prefixes, names (Front/Pop, IndexQueueFront, FramePool*Slot, WriterIsStalled with no stamp, m_queueEnds) | ledger:1045-1046; 01-recorder/recorder_internal.h:1-8; 01-recorder/record_writer.h:110,133 | OK |
| B15 | RCD23 slots + byte area; RecordFileCreate(sessionDir, process); queue list in the Writer | ledger:1047; 00-util/spsc_record_queue.h:78-113; 01-recorder/record_writer.h:68,108-110 | OK |
| B16 | RCD25 W1 "retry queue of 64 lines (two index queues over LineText slots)" | ledger:1049; 01-recorder/record_writer.h:41,83-87,114-116 | OK |
| B17 | RCD25 "appended again at the end of each pass". Header: step 7 of 9 (free space and flush follow) | ledger:1049; 01-recorder/record_writer.h:145 | NOTE |
| B18 | RCD27 "a notify during a pass causes one more pass": stated (see E1 for its defect) | ledger:1051; 01-recorder/record_writer.h:151-152 | OK |
| B19 | RCD27 "the slot pool is MPSC under one lock". Header: two queues, each its own lock (RCD38, an agent row, says two) | ledger:1051,1062; 01-recorder/frame_pool.h:49-51 | MINOR |
| B20 | RCD31 "RecorderCounters stays unpadded (40 bytes, one cache line)". Unpadded: yes. Measured size 28 bytes | ledger:1055; 01-recorder/recorder_internal.h:34-47 | MINOR |
| B21 | RCD34 B1 no gpu; B2 "dropped and counted"; A1 asr_clips made by Create | ledger:1058; 01-recorder/recorder_internal.h:20-21; 01-recorder/recorder.h:26-28 | OK |
| B22 | RCD35 kRecordQueueRecords = 16384; RecordResult in record_field.h returned by all three | ledger:1059; 01-recorder/recording_thread.h:28; 01-recorder/record_field.h:70-76; record_span.h:40; record_event.h:12; record_frame.h:24 | OK |
| B23 | RCD38 fix-pass items present: infoJson, WriteHeader frame size, static_assert, Destroy stores STOPPED, Create resets, split counts | ledger:1062; 01-recorder/recorder.h:37; 01-recorder/record_writer.h:70,111-112,119,157-158; 01-recorder/recorder_internal.h:24-25 | OK |
| B24 | PRF5 cap = the design's count, config; PRF4/RVW4 thread past cap dies | ledger:957,956,948; 01-recorder/recording_thread.h:20-23 | OK |
| B25 | RVW3 slot held across request; recorder copies during the call | ledger:947; 01-recorder/record_frame.h:19-21 | OK |
| B26 | TEL2 "drop, count ..., one event, a chat line": drops counted; "one event" MISSING (writer never records; amended in md:193 with no ruling) | ledger:958; 01-recorder/recorder.h:57-85 | NOTE |
| B27 | TEL3(2) fsync the trace only, pools 8 and 24, 64-bit constants outside the enum | ledger:962; 01-recorder/record_writer.h:47-49,73; 01-recorder/frame_pool.h:23-25 | OK |
| B28 | TEL5/TEL16 PNG level 1, source resolution; TEL7 drop and count (pause superseded by RCD25) | ledger:961,975,966; 01-recorder/record_frame.h:1-2; 00-util/frame_types.h:8 | OK |
| B29 | TEL13/TEL17 "W x H x 3 x 0.45 x 30 ... 40 minutes ... 5 minutes" | ledger:972,976; 01-recorder/recorder_internal.h:60-62; 01-recorder/record_writer.h:42-44,50 | OK |
| B30 | RUN3 typed Die actions: RecorderFlushInDie fits DieActionFn (runtime.h:18) | ledger:982; 01-recorder/recorder.h:46-48 | OK |
| B31 | PRF2, PRF3 (128-byte record) superseded by RCD11/PY3; PRF6 flush under the cap: "Die step 3" | ledger:920,955,979; 01-recorder/recorder.h:46 | OK |

## C. Decisions vs document

| # | what | where | severity |
|---|---|---|---|
| C1 | PY3 "a span is (stage, start, end, names, values)"; header: makers only for odd shapes. md instance 2 builds plain spans with field makers | ledger:1044; 01-recorder/record_field.h:78-81; md:71-72,88-89 | MINOR |
| C2 | RCD34 B2 "dropped and counted". md TOCTOU: a late push "stays in its queue, counted as queued, never written"; no health field counts it | ledger:1058; md:246; 01-recorder/recorder.h:75-85 | MINOR |
| C3 | TEL2's "one event" per fault amended in md with no ruling; absent from the section 4 change table that REV8 requires | ledger:958,1014; md:116-135,193 | MINOR |
| C4 | REV8 cause (SEEN/DESIGNED/FORCED or a ruling ID). Stall row cause: "the telemetry stall rule (TEL, the owner's)", no class, no ID | ledger:1014; md:264 | MINOR |
| C5 | RCD27 "slot pool is MPSC under one lock"; md: two queues "each under its own lock" | ledger:1051; md:23,239 | MINOR |

## D. Internal consistency of the document

| # | what | where | severity |
|---|---|---|---|
| D1 | Time reference line: "unchanged" (PRF2-PRF6 row) against "again at every fsync" (change table, R4) | md:189 vs md:113,126,424 | MINOR |
| D2 | "The event's png key is the request"; the pass event sample has no png key | md:129,227 vs md:80-81 | MINOR |
| D3 | "the one die is the 17th thread"; Create failure dies at start (gate item 2 says "after start") | md:193 vs md:42-43,203,272,274 | NOTE |
| D4 | "the lazy ring per thread" as current; current form is a deque (Python) or slot ring + byte area (C) | md:136 vs md:7,233 | NOTE |
| D5 | Label T1 defined, used nowhere | md:405 | NOTE |

## E. Internal consistency of the headers

| # | what | where | severity |
|---|---|---|---|
| E1 | Restart "at step 2" skips step 1's clear, so m_wake stays set. The OsEvent ops are set, clear, timed wait: no is-set test exists for "was m_wake set during the pass". A literal build re-enters step 2 forever | 01-recorder/record_writer.h:23-26,136,151-152 (03-runtime/runtime_internal.h:82-84) | BLOCKING |
| E2 | "the set is skipped when the writer's wake-up object is already set": needs an is-set op not in the listed ops | 01-recorder/recording_thread.h:100-101; 01-recorder/record_writer.h:23-26 | MINOR |
| E3 | Destroy "waits ... then joins it" vs a Destroy past its deadline "abandons the writer" (no join) | 01-recorder/recorder.h:41-43 vs 01-recorder/record_writer.h:157-158 | MINOR |
| E4 | Create accepts STOPPED after an abandoned writer, and the queues survive: a second writer consumes queues the abandoned one may still read; SPSC states one consumer | 01-recorder/recorder_internal.h:23-26; 00-util/spsc_record_queue.h:1; 01-recorder/recording_thread.h:4 | MINOR |
| E5 | Last-pass order: record_file.h puts the final frame lines before the time reference and health; WriterRun runs steps 7 and 9 (time ref, health) before the extra frames, then "one more flush" | 01-recorder/record_file.h:21-22 vs 01-recorder/record_writer.h:153-156 | MINOR |
| E6 | "a record call before Create is a no-op" and "any state but RUNNING is dropped and counted" (NOT_CREATED is such a state); record_field.h: "Every drop is also counted" | 01-recorder/recorder_internal.h:20-21; 01-recorder/record_field.h:69 | MINOR |
| E7 | RECORD_DROPPED causes omit the free-space reserve and the queueless thread | 01-recorder/record_field.h:66-67 vs 01-recorder/record_frame.h:17-18, 01-recorder/recorder.h:61 | MINOR |
| E8 | "wait on m_stopped ... and never join; only Destroy joins": self-contradicting wording | 01-recorder/record_writer.h:156-157 | NOTE |
| E9 | C byte area = 64 B per slot; a record may be 8192 B; the "16,384 records" bound holds in C only if records average <= 64 B; the C byte form is undefined (unverified) | 00-util/spsc_record_queue.h:94; 01-recorder/record_field.h:26; 01-recorder/recording_thread.h:23-24,81-82 | NOTE |
| E10 | Comment wrapped mid-sentence ("A" / "record is never refused for its" / "text") | 01-recorder/record_field.h:80-83 | NOTE |
