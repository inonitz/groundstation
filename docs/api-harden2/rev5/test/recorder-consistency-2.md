VERDICT: NOT CONSISTENT. 89 findings: 10 BLOCKING, 50 MINOR, 29 NOTE.

# The recorder: consistency check 2 (2026-10-21)

Sources: the 16 headers (00-util 6, 01-recorder 10; the aggregate holds all 16 verbatim, checked by script), recorder.md (455 lines), the ledger docs/spec-harden2-cleanup.md, test/recorder-review.md:1268-1281 (the recorder's D1-D14).
Abbreviations: md = 01-recorder/recorder.md; paths without a folder are in 01-recorder/ or 00-util/; L = the ledger.
Each defect is counted once; a row marked "(see Xn)" is a cross-reference, not counted.

## A. Document vs headers

| # | what | where | severity |
|---|---|---|---|
| A1 | md lists `recorder_registeral.h` (nine parts: registered names, packed layout of a run); no such header; the real ones are recorder_internal.h, recording_thread.h, frame_pool.h, record_writer.h | md:7; recorder_internal.h:1-8 | BLOCKING |
| A2 | "cut" field value: md says the original length (`"cut":5849`); header says the total bytes cut | md:122, md:267, md:320; record_field.h:62 | BLOCKING |
| A3 | test 4: a 2048-byte text is "refused and counted"; header: a record is never refused for its text | md:321; record_field.h:60-62 | BLOCKING |
| A4 | info line example has key `"models"`; header key for the caller's object is `"info"` | md:216; record_file.h:58-62 | BLOCKING |
| A5 | event line example puts fields at top level; header puts them under `"p"` | md:219; record_file.h:75-79 | BLOCKING |
| A6 | spsc_record_queue.h described as a byte ring with reserve/commit and 8-byte runs; header is a ring of record slots plus a byte area with Push/Front/Pop | md:7; spsc_record_queue.h:1-7, 46-65, 77-111 | MINOR |
| A7 | record_field.h described as "registered keys"; header: "No table, no id" | md:7; record_field.h:1-3 | MINOR |
| A8 | `runtime_registeral.h` does not exist; header names runtime_internal.h | md:130; record_writer.h:22-23 | MINOR |
| A9 | names Register, PackedSpanHeader, PackedEventHeader, PackedFieldHeader, PackedTextHeader, RegisteredNames, "nine named parts", "1360 bytes": none in headers; struct Recorder has 7 parts, 1336 bytes measured | md:7, md:142-148; recorder_internal.h:49-57 | MINOR |
| A10 | caller field cap 15; header 31 | md:155; record_field.h:21 | MINOR |
| A11 | registration rules (same id twice, name over 31 bytes gives NONE, full table, key NONE left out) | md:165-167; record_field.h:1-3, 11 | MINOR |
| A12 | pass = "8 steps", no thread-line step, loop "yes: step 2"; header has 9 steps, step 3 thread lines, every pass starts at step 1 (wait, clear) | md:21; record_writer.h:124-137 | MINOR |
| A13 | "seven counters"; RecorderHealth has 6 counts, 3 flags, 1 float | md:61; recorder.h:65-76 | MINOR |
| A14 | FlushInDie "join with the timeout"; header: FlushInDie never joins | md:120; record_writer.h:141-142 | MINOR |
| A15 | a late record "lost, not counted"; header: any state but RUNNING is "dropped and counted" | md:121, md:244; recorder_internal.h:20-21; record_span.h:38-39 | MINOR |
| A16 | health flag named `lastWriteFailed`; RecorderHealth field is `mb_writePaused` | md:408; recorder.h:60, 73 | MINOR |
| A17 | "static_asserts pin the record bound and the field count"; no static_assert in any header | md:209; all 16 headers | MINOR |
| A18 | "Three lines per queue ... 3 KiB"; struct is 4 lines (read-only fields + head + tail + dropped), 256 bytes measured, 4 KiB for 16 | md:300; spsc_record_queue.h:103-111 | MINOR |
| A19 | health "degraded"; no such field or key (two flags since D13) | md:265; recorder.h:65-76; record_file.h:95-104 | MINOR |
| A20 | test 1 compares "the C packed layout"; no packed layout in headers | md:318; recording_thread.h:74-75 | MINOR |
| A21 | D11 "packed bool is a uint64 of 0 or 1": no packed form in headers | md:160; recording_thread.h:74-75 | NOTE |
| A22 | drawing 1 code names omit ProducerPushEvent | md:20; recording_thread.h:86-92 | NOTE |
| A23 | OsEventSet/OsEventWait/OsEventClear named; only `OsEvent` forward-declared here (home 03-runtime) | md:22; record_writer.h:26-27 | NOTE |
| A24 | util APIs never named: IndexQueueCreate/Destroy/Push/Pop/Front, SLOT_NONE, SpscRecordQueueCreate/Destroy, SpscProducerPush, SpscProducerRecordsQueued/Dropped, SpscConsumerFront/Pop, RecordSlot, kRingBytesPerRecordExpected | index_queue.h:12-38; spsc_record_queue.h:36-93 | NOTE |
| A25 | frame_pool.h never named beyond 4 functions: FramePoolCreate/Destroy, FramePools, FramePoolsCreate/Destroy, FrameSlot; kRecordFolderBytes 64, kRecordNameBytes 32 | frame_pool.h:40-89; record_frame.h:8-11 | NOTE |
| A26 | RecordFileCreate/WriteHeader/Close, LineText, DieReasonText, m_droppedByThreadsWithoutQueue not in sections 2, 3, 7, 11 (last only in history md:153) | record_writer.h:48-49, 65-71, 105 | NOTE |
| A27 | LINE_* and *_KEY_* constants appear only via example lines; O_CLOEXEC of both open flags never mentioned (md lists O_CREAT, O_EXCL, O_APPEND) | md:205, md:215-223; record_file.h:15-17, 22-108 | NOTE |
| A28 | type name RecorderHealth never used in md | recorder.h:65-76 | NOTE |
| A29 | "No allocation beyond the record"; the queue is aligned_alloc'd at a thread's first record | md:200; recording_thread.h:39-40 | NOTE |
| A30 | "at most 5 s of runs lost": "run" is the dropped byte-ring term | md:263 | NOTE |
| A31 | a half PNG "unlinked and counted": no header states the unlink or the counter | md:129, md:171; record_frame.h:28-32 | NOTE |

## B. Decisions vs headers

| # | what (ruling: consequence -> header) | where | severity |
|---|---|---|---|
| B1 | RCD1 ambient, no handle -> "Ambient: created once per process, no handle" | L:1021; recorder.h:3 | OK |
| B2 | RCD2 FrameSize, FrameView -> defined (home moved to util by T1) | L:1022; frame_types.h:9-25 | OK |
| B3 | RCD3 one file per process, pid in name -> `"record-%s-%d.jsonl"` | L:1023; record_file.h:14 | OK |
| B4 | RCD4 no sample contract, GPU as an event -> record_event.h names "the GPU's memory and load"; but RCD19 point 7 "(G2): the GPU event dropped" | L:1024, L:1039; record_event.h:11 | MINOR |
| B5 | RCD5 one contract per header; clock, lifetime, health in recorder.h | L:1025; recorder.h:1-6; record_span.h:1; record_event.h:1; record_frame.h:1 | OK |
| B6 | RCD6 "never by a span or an event" -> superseded by RCD10/11 watermark; header has the watermark | L:1026; recording_thread.h:93-95 | OK |
| B7 | RCD7 OsEvent carried to runtime_internal.h; mask limit from config | L:1027; record_writer.h:22-27; frame_pool.h:20 | OK |
| B8 | RCD8 fixed_text.h, util homes | L:1028; fixed_text.h:6-9 | OK |
| B9 | RCD9 two endpoint types; head, tail, drop each own line "measured offsets 0, 64, 128" -> lines present; offsets now 64, 128, 192 (measured) after RCD12 | L:1029; spsc_record_queue.h:25-31, 109-111 | NOTE |
| B10 | RCD12 cut rule restored; one snapshot per pass; drop-gap protocol; normal last pass with die line | L:1032; record_field.h:60-62; record_writer.h:126, 138-140; recording_thread.h:42-47 | OK |
| B11 | RCD15 "the instance in nine named parts (1360 bytes)" -> 7 parts, 1336 bytes (superseded by RCD20, RCD23, not stated) | L:1035; recorder_internal.h:49-57 | NOTE |
| B12 | RCD16 mb_lastWriteFailed -> in RecorderCounters; RecorderHealth still mb_writePaused (see E6) | L:1036; recorder_internal.h:43; recorder.h:73 | (E6) |
| B13 | RCD17 "31 callers' fields plus the cut field" | L:1037; record_field.h:21-22 | OK |
| B14 | RCD18 / PY3 (Q1) "a collections.deque of record tuples bounded by a count"; C packed form only | L:1038, L:1044; spsc_record_queue.h:5-6; recording_thread.h:74-75 | OK |
| B15 | RCD19 cap 16, 17th dies (RVW4); time reference naming; T1 util headers | L:1039; recording_thread.h:20-26; record_file.h:23, 50-56 | OK |
| B16 | RCD20 (K1) "the registers-refused counter [is] gone" -> RecorderHealth keeps m_droppedKeys "registers refused" (see E3) | L:1040; recorder.h:53-55, 69 | (E3) |
| B17 | RCD21 one header per actor with prefixes | L:1045; recording_thread.h; frame_pool.h; record_writer.h | OK |
| B18 | RCD22 names (SpscConsumerFront/Pop, IndexQueueFront, FramePool*, RecordFile*, WriterIsStalled without stamp) | L:1046; spsc_record_queue.h:59-65; index_queue.h:38; frame_pool.h:60-71; record_writer.h:65-71, 122 | OK |
| B19 | RCD23 slots plus byte area; table folded into the writer; RecordFileCreate(dir, process) | L:1047; spsc_record_queue.h:77-111; record_writer.h:65, 102-104 | OK |
| B20 | RCD25 (W1) "a bounded retry queue of 64 lines (two index queues over LineText slots) ... a full retry queue drops, counted" -> storage and counter MISSING (see E1, E2) | L:1049; record_writer.h:37, 94-107, 133 | (E1, E2) |
| B21 | RCD27 CV with remembered notify; queues lock-free SPSC; pool under one lock | L:1051; record_writer.h:22-25, 125; index_queue.h:1-2 | OK |
| B22 | RCD31 "unpadded (40 bytes, one cache line)" -> unpadded; sizeof(RecorderCounters) = 28 measured | L:1055; recorder_internal.h:33-46 | MINOR |
| B23 | PY1 built-in container or lock; C keeps atomics with orderings | L:1041; spsc_record_queue.h:94-96; recording_thread.h:40-46 | OK |
| B24 | PY2 numpy only for the pixel copy: no header states it | L:1043 | NOTE |
| B25 | GIL2 the 16 recording threads are the app's working threads | L:1042; recording_thread.h:1-3, 20-21 | OK |
| B26 | PRF1 stage enum, file keeps the name | L:908; record_span.h:16-33; record_file.h:40-43 | OK |
| B27 | PRF4 cited for the cut rule; PRF4's consequence has no cut rule (cost table, 33rd thread dies, PERF_GPU) | L:956; record_field.h:62 | NOTE |
| B28 | PRF5 design's count as config constant, never nproc | L:957; recording_thread.h:20-21 | OK |
| B29 | PRF6 flush is Die step 3 | L:979; recorder.h:41 | OK |
| B30 | PRF7 no handle | L:1018; recorder.h:3 | OK |
| B31 | TEL2 no die after start; "one event, a chat line" on a fault -> chat line only; the writer never records | L:958; recorder.h:28-30, 51-52 | NOTE |
| B32 | TEL5/TEL13/TEL16 "PNG level 1" -> header says "lossless PNG"; level 1 MISSING | L:961, L:972, L:975; record_frame.h:1 | MINOR |
| B33 | TEL3(2) fsync the trace only, never PNGs | L:962; record_writer.h:70 | OK |
| B34 | TEL7 full rings and pools drop and count | L:966; spsc_record_queue.h:45; frame_pool.h:64; record_frame.h:17-18 | OK |
| B35 | TEL12 64-bit and float values as macros | L:971; record_writer.h:43-46 | OK |
| B36 | TEL14 masks beside the frame on the frame's path | L:973; record_file.h:16 | OK |
| B37 | TEL17 "start check covers 40 minutes, the pause reserve 5 minutes" -> constants present; which minutes Create uses not stated ("under the reserve") | L:976; record_writer.h:38-40; recorder.h:28-29; recorder_internal.h:59-61 | MINOR |
| B38 | TEL18 free-space product in uint64 | L:977; record_writer.h:30; recorder_internal.h:61 | OK |
| B39 | RVW3 job holds the slot; copy during the call | L:947; record_frame.h:28-30 | OK |
| B40 | RVW4 a ring per thread; die = hand-over | L:948; recording_thread.h:3, 20-22 | OK |
| B41 | RVW5 shared-memory rings drained by the app -> superseded by RVW6 and RCD3 (file per process) | L:949-950; record_file.h:14 | OK |
| B42 | FB8 / RCD31 unpadded counters with the rule stated | L:1004; recorder_internal.h:34-36 | OK |
| B43 | RUN3 typed die function pointers -> "fits DieActionFn" (03-runtime/runtime_internal.h:19-26) | L:982; recorder.h:41-43 | OK |
| B44 | D1 "the run is released only when its line is written" -> header pops after append and keeps a retry copy (superseded by RCD23, RCD25; unstated) | recorder-review.md:1268; record_writer.h:128, 133 | NOTE |
| B45 | D2 one atomic for queueless drops | recorder-review.md:1269; record_writer.h:105 | OK |
| B46 | D3 deadline = now plus timeout | recorder-review.md:1270; record_writer.h:75 | OK |
| B47 | D4 tried flag | recorder-review.md:1271; recording_thread.h:68 | OK |
| B48 | D5 the queue keeps its record bound | recorder-review.md:1272; spsc_record_queue.h:105 | OK |
| B49 | D6 "one cut field with the total bytes cut" | recorder-review.md:1273; record_field.h:62 | OK |
| B50 | D7 atomic oldest-ready stamp | recorder-review.md:1274; record_writer.h:101 | OK |
| B51 | D8 "only Die writes the deadline, by a compare-and-swap from 0" -> header: Destroy uses the CAS from 0, Die stores unconditionally | recorder-review.md:1275; record_writer.h:75-76 | MINOR |
| B52 | D9 final fsync after the frames | recorder-review.md:1276; record_writer.h:140 | OK |
| B53 | D10 names checked, O_EXCL, clash counted | recorder-review.md:1277; record_frame.h:13-16; record_file.h:17; recorder.h:56-57 | OK |
| B54 | D11 "the packer zero-extends" -> no packer in headers | recorder-review.md:1278; recording_thread.h:74-75 | NOTE |
| B55 | D12 "Create resets every mb_announced" -> MISSING from Create's and the state's comments | recorder-review.md:1279; recorder_internal.h:20-25; recording_thread.h:49-50 | MINOR |
| B56 | D13 two flags with recovery | recorder-review.md:1280; recorder.h:60-63; record_writer.h:134-135 | OK |
| B57 | D14 stale definition-line comment gone | recorder-review.md:1281; record_event.h:1-18 | OK |
| B58 | RVW1, RVW2, RVW6, RVW7, REV7, REV8, TEL1, TEL3, TEL4, TEL6, TEL8-TEL11, TEL15, TEL19, PRF2, PRF3, RCD10, RCD11, RCD24, RCD26, RCD28-RCD30, RCD32: superseded, process or drawing rulings; no header consequence | L:945-1056 | OK |

## C. Decisions vs document

| # | what | where | severity |
|---|---|---|---|
| C1 | "three buffer kinds" (RCD1) vs one queue per thread plus pools (RCD11, RCD18, PY3) | md:183; L:1031, L:1038, L:1044 | MINOR |
| C2 | RVW4 row "two rings per thread" vs RVW4 "a ring per thread" and md:20 | md:186; L:948 | MINOR |
| C3 | "PRF2 to PRF6 ... the 128-byte record ... unchanged" vs the 4096-byte record (md:122) and PY3 replacing PRF3's bytearray | md:187; L:920, L:955, L:1044 | MINOR |
| C4 | "TEL1 to TEL3 ... unchanged" vs TEL1's opaque logger and TEL3's JSON RecordEvent, both replaced (RCD1, RCD20) | md:188; L:919, L:959 | MINOR |
| C5 | TEL17 "gates the frame pools only" vs TEL13 start refusal and md:272 (Create returns false) | md:190; L:972, L:976 | MINOR |
| C6 | GPU event "gpu" once a second, carried to the screen, vs RCD19 point 7 "(G2): the GPU event dropped" | md:99, md:305, md:435; L:1039 | MINOR |
| C7 | short write row: "pause, count, resume ... the same" vs RCD25 (W1) retry queue and md:455 | md:129; L:1049 | MINOR |
| C8 | D1 stated as current ("the run stays in the ring until written") vs RCD23, RCD25 | md:151-152; L:1047, L:1049 | MINOR |
| C9 | frame buffer "module 04" (folder 04-framebuffer) vs RCD29 "module 06" (06 is the SAM3 server) | md:23; L:1053 | MINOR |
| C10 | change 2 (registered keys, definitions preamble) not marked superseded; only change 1 is | md:369-379; L:1032, L:1040 | MINOR |
| C11 | failed write "lost" vs RCD25 (W1) retry (see D1) | md:261; L:1049 | (D1) |
| C12 | 15 fields, registration, "cut" = original length vs RCD20 and D6 (see A2, A10, A11) | md:122, md:155, md:165-166 | (A2, A10, A11) |
| C13 | D8 in md (Destroy CAS, Die unconditional) differs from the D8 row (see B51) | md:157 | (B51) |
| C14 | PRF4 cited for the cut rule and drop-new; PRF4's consequence holds neither | md:136, md:266, md:319, md:356; L:956 | NOTE |
| C15 | W1, K1, Q1, T1 cited as recorder rulings; ledger rows with these IDs are unrelated; the meanings sit inside RCD25, RCD20, PY3, RCD19 | L:653, L:672, L:692, L:718, L:850 | NOTE |
| C16 | D1-D14 cited; ledger D1-D14 are unrelated; the recorder's are in recorder-review.md | L:638-651; recorder-review.md:1268-1281 | NOTE |
| C17 | "PRF7 parked" vs PRF7 "ESTABLISHED: no module holds a tracer handle" | md:409; L:1018 | NOTE |
| C18 | RecordFrame(folder, name, at, FrameView*) credited to RCD3; FrameView is RCD2, folder is RCD22 | md:413; L:1022, L:1046 | NOTE |
| C19 | event-driven writer credited to RCD7; it is RCD6 | md:421; L:1026-1027 | NOTE |
| C20 | "RCD5: one header per actor"; RCD5 splits by logical group, per-actor is RCD21 | md:424; L:1025, L:1045 | NOTE |
| C21 | "pngNameClashes and droppedSpans added" credited to D10, D13; neither adds droppedSpans | md:408; recorder-review.md:1277, 1280 | NOTE |

## D. The document against itself

| # | what | where | severity |
|---|---|---|---|
| D1 | a failed write: kept for retry vs "the line lost and counted; the writer goes on" | md:202, md:330, md:416, md:455 vs md:261 | BLOCKING |
| D2 | Python span cost: "about 1 us" vs 150 ns vs 437 ns | md:193 vs md:208, md:231, md:275 vs md:290 | MINOR |
| D3 | writer cost: 250 lines 0.74 ms (2.96 us a line) and 25,000 lines 185 ms (7.4 us a line) vs 2.9 + 1.4 us a line (1.08 ms, 107 ms) | md:208 vs md:236 | MINOR |
| D4 | queue hold time: over 8 minutes / minutes vs "the ring holds 5 s, then disk" | md:266, md:295 vs md:386 | MINOR |
| D5 | the wake: a half-full queue wakes the writer vs "Why spans do not wake the writer" | md:20, md:22, md:291 vs md:302 | MINOR |
| D6 | "no record ever cut" / "No record is ever cut" vs a text is cut and marked | md:110, md:373 vs md:122, md:136, md:200, md:267 | MINOR |
| D7 | write flag name: "write paused" vs "last_write_failed" vs "lastWriteFailed" | md:161 vs md:222 vs md:408 | MINOR |
| D8 | test 10: FlushInDie with a reason expects thread, drop, time reference, health; omits the die line md:24 places in the last pass | md:327 vs md:24 | MINOR |

## E. The headers against themselves

gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11: all 10 01-recorder headers clean. 00-util alone: fixed_text.h warns "ISO C forbids an empty translation unit" (macro-only header); the other 5 clean. Every forward-declared type (OsLock, OsThread, OsEvent, DieActionFn) exists in 03-runtime/runtime_internal.h:76-86 and :19-26.

| # | what | where | severity |
|---|---|---|---|
| E1 | a failed append: "that line is lost; ... the writer goes on" vs step 7 "the retry queue: every kept line appended again" and "the writer retries on its next wake" | record_writer.h:54-57 vs record_writer.h:133; recorder.h:60-61 | BLOCKING |
| E2 | the retry queue has no storage: Writer has no queue or LineText slots; kWriterRetryLines used nowhere; no counter for a full retry queue | record_writer.h:37, 94-107; recorder_internal.h:37-46 | BLOCKING |
| E3 | RecorderHealth.m_droppedKeys ("registers refused: the table was full"): no counter feeds it, no health key, registration gone | recorder.h:53-55, 69; recorder_internal.h:37-46; record_file.h:95-104; record_field.h:1-3 | BLOCKING |
| E4 | m_slotCount "a power of two" vs kRecordQueueRecords = 20000 passed as maxRecords ("at most maxRecords records"); no rounding rule | spsc_record_queue.h:33-35, 98-99; recording_thread.h:27 | BLOCKING |
| E5 | comment names RECORDER_STALL_NS; the constant is WRITER_STALL_NS | recorder.h:59; record_writer.h:45 | MINOR |
| E6 | one flag, three names: mb_writePaused, mb_lastWriteFailed, "last_write_failed" | recorder.h:60, 73; recorder_internal.h:43; record_file.h:102 | MINOR |
| E7 | "die last on a Die" vs the last pass writing steps 7, 9 (time reference, health) and step 6 frame lines after the die line | record_file.h:19-21; record_writer.h:138-140 | MINOR |
| E8 | RecordCount typedef'd in two homes | recorder.h:16; spsc_record_queue.h:17 | MINOR |
| E9 | "config values read at Create" / "from config" / "a config constant" vs compile-time enum values | record_writer.h:32-41; frame_pool.h:20-25; recording_thread.h:20-29 | MINOR |
| E10 | a name set by RecorderNameThisThread before the first record has no home: RecordingThread (m_name) is made at the first record; ThreadProducer has no name | recorder.h:45-47; recording_thread.h:39, 53, 65-70 | MINOR |
| E11 | m_droppedByThreadsWithoutQueue is one count; health splits spans and events; the bucket is unstated | record_writer.h:105; recorder.h:66-67 | MINOR |
| E12 | RecordFrame's result in STOPPING or STOPPED unstated (RECORD_DROPPED or RECORD_NOT_CREATED) | record_frame.h:20-26; recorder_internal.h:20-21 | MINOR |
| E13 | with RECORDER_NO_FRAMES: no way to pass infoJson, the info line's content is undefined, and RecorderReserveBytes(FrameSize) has no size, yet Create checks the reserve | recorder.h:20-30; record_file.h:58-62; recorder_internal.h:59-61 | MINOR |
| E14 | Create accepts only NOT_CREATED and STOPPED, yet "an old writer that never stopped is abandoned" leaves the state STOPPING (only the writer stores STOPPED) | recorder_internal.h:20-25; recorder.h:37-39 | MINOR |
| E15 | the writer "keeps the count it last wrote per entry": no field holds it | recording_thread.h:44-46, 52-60; record_writer.h:94-107 | MINOR |
| E16 | header comment layout broken: line 4 `frame_pool.h` outside the star column; the actor list runs together | recorder_internal.h:1-8 | MINOR |
| E17 | kFieldNameBytes = 32 used by nothing; FieldName is a pointer to a literal | record_field.h:11, 20 | NOTE |
| E18 | two meanings of "cut": a FIELD_NAME_CUT field inside "p" and a line-level "cut" key from WriterFormatRecord | record_field.h:26, 60-64; record_writer.h:32-33, 109-111 | NOTE |
| E19 | RecordFileCreate carries two overlapping comments | record_writer.h:63-64 | NOTE |

## Counts

| check | BLOCKING | MINOR | NOTE |
|---|---|---|---|
| A | 5 | 15 | 11 |
| B | 0 | 6 | 7 |
| C | 0 | 10 | 8 |
| D | 1 | 7 | 0 |
| E | 4 | 12 | 3 |
| total | 10 | 50 | 29 |
