# The recorder: consistency check 1 (headers, document, decisions), 2026-10-21

**Verdict: NOT CONSISTENT. 84 findings: 16 BLOCKING, 46 MINOR, 22 NOTE (24 rulings PASS, not counted).**

Sources: the 16 headers in `modules/00-util/` and `modules/01-recorder/`, `modules/01-recorder/recorder.md`,
the ledger `docs/spec-harden2-cleanup.md`, D1 to D14 in `test/recorder-review.md:1268-1281`.
The ledger paths are `spec:<line>`. `md` is recorder.md. Header paths are the file name only.
`recorder.html` was not read.
Severity: BLOCKING = a reader would build the wrong thing. MINOR = a wording or number drift.
NOTE = a gap in description only. PASS = consistent (not counted).

## A. Document against headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | The document's file list names `recorder_registeral.h`, "the mechanism in nine parts" (registered names, packed run layout). No such header. The mechanism is split by actor: recorder_internal.h (instance, 7 members), recording_thread.h, frame_pool.h, record_writer.h. md:7 lists none of the last three | md:7; recorder_internal.h:1-8, 49-57 | BLOCKING |
| A2 | md:7 describes spsc_record_queue.h as "a byte ring ... written in place by reserve and commit, runs rounded to 8 bytes". The header pushes a whole record; C storage is a slot ring plus a byte area; no reserve, commit or rounding | md:7; spsc_record_queue.h:1-7, 46-51, 77-96 | BLOCKING |
| A3 | The value of "cut" differs. The document says the original length (test 3 expects "cut":5849 for a 5849-byte text). The header says the total bytes cut | md:122, 267, 320; record_field.h:61-62 | BLOCKING |
| A4 | Test 4 says "a 2048-byte text field is refused and counted". The header never refuses a record for its text, and no header has a 2047 or 2048 text bound | md:321; record_field.h:60-62 | BLOCKING |
| A5 | The sample event line puts fields at the top level ("seq","phase","kind"). The header puts them in an object under "p", "like a span" | md:219; record_file.h:75, 79 | BLOCKING |
| A6 | The sample info line puts "models" at the top level. The header puts the caller's info object under the key "info" | md:216; record_file.h:58, 62 | MINOR |
| A7 | A record after the last pass: the document says "lost, not counted". The headers say any call in a state other than RUNNING is "dropped and counted" | md:121, 244; record_span.h:38-39; recorder_internal.h:20-21 | BLOCKING |
| A8 | A failed write: the document keeps the line for retry (W1, 64 lines). The RecordFile comment says "that line is lost" | md:202, 330, 416, 455; record_writer.h:54-57 | BLOCKING |
| A9 | The retry queue the document describes has no storage in any header. Writer holds only `m_line`. `kWriterRetryLines` is never used. Rest in B19 | md:202, 455; record_writer.h:37, 94-107 | BLOCKING |
| A10 | "static_asserts pin the record bound and the field count": no header has a static_assert (grep: 0) | md:209 | MINOR |
| A11 | The instance: "nine named parts", "1360 bytes measured". The headers give 7 members; sizeof(struct Recorder) measured 1336 bytes (gcc, x86-64) | md:146-148; recorder_internal.h:49-57 | MINOR |
| A12 | "seven counters" in the health read. RecorderHealth has 10 fields: 6 counts, 3 flags, 1 float | md:61; recorder.h:65-76 | MINOR |
| A13 | Drawing 2 says "8 steps" and loops "flag set during the pass? yes: step 2; no: step 1". WriterRun has 9 steps (snapshot and thread lines are their own steps) and no end-of-pass flag check; step 1 waits then clears | md:21; record_writer.h:124-137 | MINOR |
| A14 | The pool: "two index queues under ONE lock". Each IndexQueue owns its own `m_lock`; FramePool holds two IndexQueues | md:23, 237; index_queue.h:24; frame_pool.h:52-57 | MINOR |
| A15 | "a half PNG unlinked" and "a failed PNG write is unlinked and counted". No header states the unlink or which counter | md:129, 171, 202; record_writer.h:130-132; record_frame.h:28-32 | MINOR |
| A16 | Test 1 compares "the C packed layout" with the Python tuple. No header defines a packed layout ("a C build defines its own byte form") | md:318; recording_thread.h:74-75 | MINOR |
| A17 | "Destroy and FlushInDie set STOPPING, wake it, join with the timeout". The headers: FlushInDie never joins; only Destroy joins | md:120; recorder.h:37-43; record_writer.h:141-142 | MINOR |
| A18 | Section 4 states, as fixes now in the headers: Register, PackedSpanHeader, PackedEventHeader, PackedFieldHeader, PackedTextHeader, RegisteredNames, "15 fields", "key 1, registered at Create", names giving NONE. None exist. The header has 31 caller fields, "No table, no id" | md:142-143, 155, 165-166; record_field.h:3, 21-22 | MINOR |
| A19 | Test 10's line order after FlushInDie omits the die line, which the last pass writes after step 6 | md:327; record_writer.h:138-139 | MINOR |
| A20 | Health flag name: the document says "lastWriteFailed". RecorderHealth names it `mb_writePaused` | md:408; recorder.h:60-61, 73 | MINOR |
| A21 | The document names OsEventSet, OsEventWait, OsEventClear. They are in none of the 16 headers (OsEvent is opaque here; runtime_internal.h only) | md:22; record_writer.h:22-27 | NOTE |
| A22 | Header constants the document never names or gives a value for: kFieldNameBytes 32, kRingBytesPerRecordExpected 64, kCacheLineBytes, QUEUED_SPAN, QUEUED_EVENT, kRecordFolderBytes 64, kRecordNameBytes 32 (md:159 says "length" only), SLOT_NONE, the 9 health keys and 5 drop keys by name | record_field.h:20; spsc_record_queue.h:72-75; recording_thread.h:34-37; record_frame.h:8-11; index_queue.h:15; record_file.h:88-104 | NOTE |
| A23 | Header functions the document never names: SpscRecordQueueCreate/Destroy, SpscProducerPush, SpscProducerRecordsQueued/Dropped, SpscConsumerFront/Pop (only "front, pop"), IndexQueueCreate/Destroy/Push/Pop/Front, FramePoolCreate/Destroy, FramePoolsCreate/Destroy, ProducerPushEvent, RecordFileCreate, RecordFileWriteHeader, RecordFileClose, FieldInt/Float/Bool/Text (only the Python field_int forms) | spsc_record_queue.h:36-65; index_queue.h:32-38; frame_pool.h:60-89; recording_thread.h:86; record_writer.h:65-71; record_field.h:65-68 | NOTE |
| A24 | Header types and fields the document never describes: RecordSlot, ByteOffset, RingPosition (md:122 "a slot plus a byte area" only), FolderName, FrameName, FrameSlot, DieReasonText, `m_droppedByThreadsWithoutQueue` (md:152 says "the thread table"), `m_droppedKeys`, `mb_dropping`, `mb_present` | spsc_record_queue.h:69-88; frame_pool.h:27-46, 82; record_writer.h:49, 105; recorder.h:69; recording_thread.h:69 | NOTE |
| A25 | "PNG level 1" (TEL16): no header states the compression level | md:189; record_frame.h:1 | NOTE |

## B. Decisions against headers

| # | ruling: its consequence (quoted, short) | header line | severity |
|---|---|---|---|
| B1 | RCD5: "recorder.h holds the clock, the lifetime and the health; record_span.h, record_event.h and record_frame.h hold one contract each; frame_types.h holds FrameSize, PixelFormat and FrameView" | recorder.h:1-6; record_span.h:1; record_event.h:1; record_frame.h:1; frame_types.h:8-25 | PASS |
| B2 | RCD6 + RCD11: wake by a frame, Destroy, Die, and "a half-full watermark wake"; 5 s timer; no poll | record_writer.h:4-5, 43; recording_thread.h:24, 93-95 | PASS |
| B3 | RCD7: "the mask limit per pass from config" | frame_pool.h:20-23: a compile-time enum 3, the comment says "from config" | MINOR |
| B4 | RCD8/RCD9: SPSC endpoints by type; head, tail, drop count each on its own 64-byte line; index_queue.h "under one lock, safe for any threads, Push, Pop and Peek"; no per-slot state | spsc_record_queue.h:23-31, 109-111; index_queue.h:1-5, 35-38; frame_pool.h:1-7 | PASS |
| B5 | RCD11: "the health gains dropped_keys" | superseded by RCD20 (see B10) | PASS |
| B6 | RCD12: "the cut rule on text fields"; "the last pass ... the normal pass with the die line"; "the cached ring indexes deleted" | record_field.h:60-62; record_writer.h:138-140; spsc_record_queue.h:94-96 | PASS |
| B7 | RCD12: "the run heads pinned by offset asserts" | no static_assert in any header; the packed heads were later deleted (RCD23) | NOTE |
| B8 | RCD16: names LINE_KIND_NAMES, SPAN_STAGE_NAMES, RECORD_FILE_OPEN_FLAGS, RECORD_PNG_OPEN_FLAGS, EVENT_KEY_FIELDS, mb_lastWriteFailed, m_oldestReadyFramePublishedAt, unusedCtx | record_file.h:15, 17, 36, 40, 79; recorder_internal.h:43; record_writer.h:101; recorder.h:43 | PASS |
| B9 | RCD17: "raised to 31 callers' fields plus the cut field (the 4096-byte run is the real bound)" | record_field.h:21-23 | PASS |
| B10 | RCD20 (K1): "RECORD_KEY_NONE and the registers-refused counter are gone" | recorder.h:54-55, 69 still has `m_droppedKeys` "registers refused: the table was full or the name too long"; record_field.h:20 `kFieldNameBytes` left over | MINOR |
| B11 | RCD20 (K1): "FieldName and RecordTopic are const char* to literals" | record_field.h:11; record_event.h:9 | PASS |
| B12 | RCD18 + PY3 (Q1): "a collections.deque of record tuples bounded by a count"; "no reserve and commit in the contract" | spsc_record_queue.h:5-6, 46-51 | PASS |
| B13 | RCD19 point 1: "'clock line' is now the time reference line" | record_file.h:3 "re-emits the clock line" | MINOR |
| B14 | RCD19 point 2: "the recorder's cap is 16 ... a 17th thread is a design drift that dies (RVW4)" | recording_thread.h:20-26 | PASS |
| B15 | RCD19 point 7 (G2): "the GPU event dropped" | record_event.h:11 "the GPU's memory and load" as an event | MINOR |
| B16 | RCD21: one header per actor, a prefix per role | recording_thread.h:76-95; frame_pool.h:60-71; record_writer.h:65-71, 112-144 | PASS |
| B17 | RCD22: Create/Destroy names; SpscConsumerFront and Pop; IndexQueueFront; FramePool names; m_queueEnds in the Writer; WriterIsStalled takes no stamp | spsc_record_queue.h:36-65; index_queue.h:38; frame_pool.h:60-71; record_writer.h:104, 122 | PASS |
| B18 | RCD23: slots and a byte area, "no in-band header, no padding record"; RecordFrame picks the pool by format; RecordFileCreate takes the session folder and the process name; the thread table folded into the writer | spsc_record_queue.h:77-112; record_frame.h:28; record_writer.h:65, 102-104 | PASS |
| B19 | RCD25 (W1): "a bounded retry queue of 64 lines (two index queues over LineText slots) ... a full retry queue drops, counted" | `kWriterRetryLines` 64 at record_writer.h:37 and step 7 at :133 only. MISSING: the two index queues, the LineText slots, the full-queue drop and its counter (Writer, record_writer.h:94-107). record_writer.h:54-57 still states RCD23's "the line lost" | BLOCKING |
| B20 | RCD27: "the record queues are lock-free SPSC, the slot pool is MPSC under one lock"; a notify during a pass causes one more pass | spsc_record_queue.h:1-4, 94-96; index_queue.h:1-3 (one lock per queue, two queues per pool: see A14); record_writer.h:22-25, 125 | PASS |
| B21 | RCD31: "RecorderCounters stays unpadded (40 bytes, one cache line); the header comment states the rates and the rule (FB8)" | unpadded and commented at recorder_internal.h:33-46; sizeof measured 28 bytes, not 40 | MINOR |
| B22 | PY1: "the C headers keep real atomics with their orderings" | spsc_record_queue.h:94-96, 109-111; recording_thread.h:39-47; record_writer.h:75-76 | PASS |
| B23 | GIL2: "the sixteen recording threads are the app's working threads, none exists to record" | recording_thread.h:1-3 | PASS |
| B24 | PRF5: "the table size is a config constant of the design's thread count" | recording_thread.h:20-21, 26 | PASS |
| B25 | PRF4: "the 33rd thread is a bug and dies (RVW4), no drop branch" | recording_thread.h:22; but record_writer.h:105 keeps a count for threads without a queue, its cause not stated (RCD17 says a failed allocation) | NOTE |
| B26 | PRF6 + RUN3: the flush is Die step 3, a DieActionFn | recorder.h:41-43 | PASS |
| B27 | PRF7/RCD1: "no handle returned, none passed" | recorder.h:3 | PASS |
| B28 | TEL2: no die after start; Create fails at start | recorder.h:28-30; the one die at recording_thread.h:22 (RVW4) | PASS |
| B29 | TEL5/TEL13/TEL16: lossless PNG level 1; refuse start under the reserve | record_frame.h:1; recorder.h:28-29; level 1 not stated | NOTE |
| B30 | TEL7: "full rings and pools drop and count" | record_frame.h:17-18; record_span.h:37 | PASS |
| B31 | TEL17: "W x H x 3 x 0.45 x 30 passes a minute x minutes"; 40 minutes; 5 minutes; the rates as config values | recorder_internal.h:59-61; record_writer.h:38-40, 46; but :33 says "config values read at Create" over compile-time enums :34-41 | MINOR |
| B32 | RVW3: the job copies, then releases the shared slot | record_frame.h:28-29 | PASS |
| B33 | RVW4: "perf = one tracer, a ring per thread"; die mid-flight | recording_thread.h:3, 22 | PASS |
| B34 | D2, D3, D4, D5, D7, D9, D10, D14 (recorder-review.md:1269-1281) | record_writer.h:75, 77-78, 105, 120-122, 140; recording_thread.h:63, 68; spsc_record_queue.h:105; record_frame.h:15-16; record_file.h:17 | PASS |
| B35 | D8: "only Die writes the deadline, by a compare-and-swap from 0" | record_writer.h:75-76: Destroy does the compare-and-swap; Die stores unconditionally (md:157 agrees with the header, not with D8) | MINOR |
| B36 | D12: "Create resets every mb_announced" | not stated; recorder_internal.h:23-24 and recording_thread.h:49-50 are silent on the reset | MINOR |
| B37 | D13: "two flags: mb_writePaused and mb_underReserve" | recorder.h:73-74 has both; recorder_internal.h:43 names the first `mb_lastWriteFailed`; record_file.h:102 "last_write_failed" | MINOR |
| B38 | D1, D6, D11: the held run, 15 fields, the packed bool | superseded by W1, RCD17, RCD23; no header element left | NOTE |

## C. Decisions against the document

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | RCD19 point 7 (G2) "the GPU event dropped". The document keeps the "gpu" event once a second as the PERF_GPU replacement and as the screen's helper | spec:1039; md:99, 305, 414, 435, 454 | BLOCKING |
| C2 | RCD25 (W1) retry queue. The failure matrix says "the line lost and counted; the writer goes on" | spec:1049; md:261 | BLOCKING |
| C3 | RCD20 (K1) "no registration". The document still says "registered keys" in its file list and lists registration rules as current header answers | spec:1040; md:7, 155, 165-166 | MINOR |
| C4 | RCD18/RCD23 "no reserve and commit in the contract", "no in-band header, no padding record". The file list says reserve and commit, runs rounded to 8 bytes | spec:1038, 1047; md:7 | MINOR |
| C5 | RVW4 "a ring per thread", RCD11 the two rings merged. Section 6 says "two rings per thread" | spec:948, 1031; md:186 | MINOR |
| C6 | Section 6 says PRF2 to PRF6 ("the 128-byte record ... the drain") are "unchanged". PY3 and RCD20 replaced the record; section 4 lists both as changes | spec:1044, 1040; md:187 vs md:120-122 | MINOR |
| C7 | TEL13 "the app refuses to start under the start reserve". Section 6 says the reserve "gates the frame pools only" | spec:972; md:190 | MINOR |
| C8 | The writer is event-driven is cited as RCD7. The ledger rules it in RCD6; RCD7's consequence is the round-2 review | spec:1026-1027; md:421 | MINOR |
| C9 | D8's fix (Die alone writes the deadline by CAS) differs from md:157 (Destroy by CAS, Die unconditional) | recorder-review.md:1275; md:157 | MINOR |
| C10 | D6's fix (15 fields) and RCD17 (31 fields): md:155 states 15 as the current header fix | recorder-review.md:1273; spec:1037; md:155 | MINOR |
| C11 | The cut rule and drop-new are cited as PRF4. PRF4's consequence column states neither; only RCD12 calls the cut rule "PRF4's" | spec:956, 1032; md:122, 136, 266, 319 | NOTE |
| C12 | The counters' unpadded layout cites FB8. FB8 kept the padded frame-buffer layout on a performance tie-break | spec:1004, 1055; md:209; recorder_internal.h:35 | NOTE |
| C13 | ID collisions: ledger rows "W1" (spec:692, 850), "K1" (spec:718), "Q1" (spec:653), "T1" (spec:672) are unrelated. The recorder's W1, K1, Q1, T1 exist only inside RCD25, RCD20, PY3, RCD19. REV7 has no row | spec:653, 672, 692, 718, 850 | NOTE |
| C14 | RCD29 calls the frame buffer "module 06". The document says module 04, which matches the folder 04-framebuffer | spec:1053; md:23 | NOTE |
| C15 | RCD28 "the text and the drawing say the same thing": not checked, recorder.html not read | spec:1052 | NOTE |

## D. The document against itself

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | Failed write: "the line kept for retry (W1)" against "the line lost and counted" | md:202, 330, 416, 455 vs md:261 | BLOCKING |
| D2 | A late record: "a push after STOPPED: drop, count" and "a record in any state but RUNNING is dropped and counted", against "lost, not counted" | md:24, 167 vs md:121, 244 | BLOCKING |
| D3 | The text rule: "cut ... never refused" against test 4 "a 2048-byte text field is refused and counted"; and R4's "no record ever cut" | md:122, 202, 320 vs md:321, 110 | BLOCKING |
| D4 | Rings per thread: one queue per thread against "two rings per thread" | md:20, 349 vs md:186 | MINOR |
| D5 | The header set: md:7 (recorder_registeral.h, nine parts) against md:27 (actors Producer, FramePool, Writer, RecordFile) | md:7, 146-148 vs md:27 | MINOR |
| D6 | The C queue: "byte ring, reserve and commit, runs rounded to 8 bytes" against "a slot plus a byte area", "the ring of record slots with its byte area" | md:7 vs md:122, 281-283 | MINOR |
| D7 | FlushInDie: "join with the timeout" against "never join" | md:120 vs md:24 | MINOR |
| D8 | Span cost: "about 1 us" against "150 ns"; the f-string "437 ns" against "723 to 804" | md:193, 290 vs md:208, 231 | MINOR |
| D9 | "Why spans do not wake the writer" against the half-full wake from any queue | md:302 vs md:20, 22, 291 | MINOR |
| D10 | The reserve "gates the frame pools only" against "Create returns false; the app dies at start" | md:190 vs md:272 | MINOR |
| D11 | PRF2 to PRF6 "unchanged" against the change table | md:187 vs md:120-122 | MINOR |
| D12 | "failed_writes, degraded" against "degraded" replaced by two flags | md:265 vs md:161, 408 | MINOR |
| D13 | "seven counters" against a health line of nine keys | md:61 vs md:222 | MINOR |
| D14 | File names `recorder_registeral.h` and `runtime_registeral.h` do not exist (an Intern-to-Register rename hit "internal") | md:7, 130 | NOTE |

## E. The headers against themselves

gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11: the 10 recorder headers, 0 FAIL, 0 warnings.
The 6 util headers alone: 0 FAIL; fixed_text.h:12 warns "empty translation unit" (macro-only header).
The aggregate holds all 16 headers verbatim (16 of 16 matched).

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | The RecordFile comment says a failed append's line is lost. The writer's step 7 retries kept lines. `kWriterRetryLines` has no storage | record_writer.h:54-57 vs :37, :133, :94-107 | BLOCKING |
| E2 | The queue cannot hold exactly 20,000. The slot count must be a power of two, masked by the count. The bound is kRecordQueueRecords = 20000, and the struct has no maxRecords field (test md:319 pins 20,000) | spsc_record_queue.h:33-35, 69, 98-99, 103-112; recording_thread.h:27 | BLOCKING |
| E3 | `RECORDER_STALL_NS` is used in a comment but defined nowhere; the constant is `WRITER_STALL_NS` | recorder.h:59; record_writer.h:45 | MINOR |
| E4 | `m_droppedKeys`: "the table was full or the name too long". record_field.h has "No table, no id". No counter feeds it, and no health key exists | recorder.h:54-55, 69; record_field.h:3; recorder_internal.h:37-46; record_file.h:95-104 | MINOR |
| E5 | One flag, three names: `mb_writePaused`, `mb_lastWriteFailed`, "last_write_failed" | recorder.h:60, 73; recorder_internal.h:43; record_file.h:102 | MINOR |
| E6 | kRecordMaxRecordBytes is "the whole run on the ring: header, payload, rounding". The queue has no header, no run, no rounding | record_field.h:16-17; spsc_record_queue.h:77-96 | MINOR |
| E7 | "under the pool's lock" (one lock). Each of the pool's two IndexQueues owns a lock | record_frame.h:28-30; index_queue.h:24; frame_pool.h:53-54 | MINOR |
| E8 | Comments say "config values read at Create" and "from config". The values are compile-time enums | record_writer.h:32-41; frame_pool.h:20-25 | MINOR |
| E9 | "clock line" in one comment; "time reference" everywhere else | record_file.h:3 vs :23, :50 | MINOR |
| E10 | `RecordCount` is typedef'd in two headers (legal C11, two homes) | recorder.h:16; spsc_record_queue.h:17 | NOTE |
| E11 | `kFieldNameBytes` is defined and used nowhere | record_field.h:20 | NOTE |
| E12 | Broken comment layout: the actor list runs together (line 4 lacks " *"); two comments for one function; a missing full stop ("flush to disk The timer"); broken indentation | recorder_internal.h:3-8; record_writer.h:63-64, 137; recording_thread.h:42-47 | NOTE |
| E13 | RecorderNameThisThread: the name lives in RecordingThread.m_name, made at the first record. ThreadProducer has no name field. Where a name set before the first record is kept is not stated | recorder.h:45-47; recording_thread.h:39, 53, 65-70 | NOTE |
| E14 | A PNG name clash is "a dropped frame, counted". Which counter (m_droppedFrames, m_pngNameClashes or both) is not stated | record_frame.h:30-32; recorder.h:56-57 | NOTE |
| E15 | RecordResult has RECORD_NOT_CREATED but no value for STOPPING or STOPPED | record_frame.h:20-26; recorder_internal.h:20-21 | NOTE |
| E16 | `m_droppedByThreadsWithoutQueue` is one count. The health splits spans and events | record_writer.h:105; recorder.h:66-67 | NOTE |
