# Recorder consistency check 3 (blind): document, decisions, headers (2026-10-21)

**Verdict: NOT CONSISTENT. 75 findings: 13 BLOCKING, 40 MINOR, 22 NOTE.**

Sources. md = `docs/api-harden2/rev5/modules/01-recorder/recorder.md`. Headers by file name (00-util/ and 01-recorder/). ledger = `docs/spec-harden2-cleanup.md`. review = `docs/api-harden2/rev5/test/recorder-review.md`. The aggregate (`recorder_aggregate_for_review.md`) holds all 16 headers byte-identical to the files (checked by script). A cell "(see X)" is counted under X only.

## A. Document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | md: spsc queue is "a byte ring ... written in place by reserve and commit, runs rounded to 8 bytes", and "the ring stays in the C header". Header: a ring of record slots plus a byte area; Push, Front, Pop; no reserve, commit or rounding (RCD23) | md:7, md:285-289; spsc_record_queue.h:46-65, 77-96 | BLOCKING |
| A2 | md: "registered keys", Register, RegisteredNames, PackedSpan/Event/Field/TextHeader, "same name registered twice gives the same id", key NONE. Header: "No table, no id"; none of these names exist (K1, RCD20) | md:7, 142-145, 165-166; record_field.h:1-3, 11 | BLOCKING |
| A3 | md: "cut" carries the original length; test 3 expects "cut":5849 for a 5849-byte text. Header: the cut field holds "the total bytes cut" | md:122, 267, 320; record_field.h:61-62 | BLOCKING |
| A4 | md: "the caller gets 15 fields and the recorder one cut field, key 1, registered at Create" (the only field-cap statement in md). Header: 31 caller fields + 1 (also RCD17, RCD20) | md:155-156; record_field.h:21-22 | BLOCKING |
| A5 | md info line puts the caller's object at top level (`"models":{...}`). Header: the caller's object goes under key "info" | md:216; record_file.h:58-62 | BLOCKING |
| A6 | md event line puts fields at top level (`"seq":12,"phase":...`). Header: event fields go under "p", "like a span" | md:219; record_file.h:75-79 | BLOCKING |
| A7 | md names `recorder_registeral.h`, "the mechanism in nine parts" incl. registered names, packed layout, the writer's function. Header: `recorder_internal.h`, 7 members; WriterRun lives in record_writer.h | md:7; recorder_internal.h:49-57; record_writer.h:144 | MINOR |
| A8 | md: OsEvent "carried to runtime_registeral.h". Header: runtime_internal.h | md:130; record_writer.h:22-23 | MINOR |
| A9 | md: the pass has "8 steps" with no thread-line step. Header: 9 steps; step 3 is the thread line | md:21; record_writer.h:124-137 | MINOR |
| A10 | md: pool = "two index queues under ONE lock"; Python "under one Lock". Header: two IndexQueue members, each with its own `m_lock`; no shared lock stated | md:23, 237; frame_pool.h:52-57; index_queue.h:23-29 | MINOR |
| A11 | md: read health = "seven counters". Header: RecorderHealth has 10 fields (6 counts, 3 flags, 1 float); md's health line has 9 keys | md:61, 222; recorder.h:65-76 | MINOR |
| A12 | md usage builds `field_float(...)` makers in a tuple every frame. Header: "no field object and no list is made on the hot path; these makers exist there only for odd shapes" | md:48-51; record_field.h:57-60 | MINOR |
| A13 | md: instance "nine named parts ... 1360 bytes measured". Header: 7 members; sizeof(struct Recorder) = 1336 measured (gcc, x86-64) | md:146-148; recorder_internal.h:49-57 | MINOR |
| A14 | md: D11 "the packed bool is a uint64"; test 1 "the C packed layout". Header: no packed layout; "a C build defines its own byte form" | md:160, 318; recording_thread.h:74-75 | MINOR |
| A15 | md: "static_asserts pin the record bound and the field count". No static_assert in any of the 16 headers | md:209 | MINOR |
| A16 | md: "Three lines per queue, 16 queues at most: 3 KiB". Header layout: read-only fields + 3 aligned lines; sizeof = 256 B (head 64, tail 128, dropped 192) = 4 lines, 4 KiB | md:300; spsc_record_queue.h:103-112 | MINOR |
| A17 | md: "No writer bookkeeping lives in the instance". Header: the instance holds Writer (queue list, queue ends, progress stamps, deadline) | md:303; recorder_internal.h:55; record_writer.h:94-107 | MINOR |
| A18 | md failure matrix leaves "failed_writes, degraded". Header: no "degraded"; two flags (D13) | md:265; recorder.h:60-63 | MINOR |
| A19 | md D2: ringless drops "counted in the thread table". Header: `m_droppedByThreadsWithoutQueue` in Writer; no thread table type (RCD23) | md:152-153; record_writer.h:105 | MINOR |
| A20 | md D12: "Create resets every thread's announced flag". No header states it | md:160; recording_thread.h:48-50; recorder_internal.h:20-25 | NOTE |
| A21 | md: "the claim counter", "a fork without exec is unsupported", "a failed PNG write is unlinked", "the unlink of a half PNG". No header holds these | md:129, 168-171, 202 | NOTE |
| A22 | md names OsEventSet, OsEventWait, OsEventClear. No header declares them (only "set, clear, wait" in a comment) | md:22; record_writer.h:22-27 | NOTE |
| A23 | md's file list omits the actor headers recording_thread.h, frame_pool.h, record_writer.h | md:7 | NOTE |
| A24 | Never described in md: SpscRecordQueueCreate/Destroy, SpscProducerPush, SpscConsumerFront/Pop, SpscProducerRecordsQueued/Dropped, RecordSlot, kRingBytesPerRecordExpected | spsc_record_queue.h:36-88 | NOTE |
| A25 | Never described in md: IndexQueueCreate/Destroy/Push/Pop/Front, SLOT_NONE | index_queue.h:15, 32-38 | NOTE |
| A26 | Never named in md: FramePoolCreate/Destroy, FramePools, FramePoolsCreate/Destroy, FrameSlot, kFramePoolFrames/MasksPerPass/Masks (values 8, 3, 24 are in md) | frame_pool.h:21-89 | NOTE |
| A27 | Never named in md: RecordFileCreate, RecordFileWriteHeader, RecordFileClose | record_writer.h:65-71 | NOTE |
| A28 | Never named in md: kWriterFreeSpaceCheckEveryLines, kWriterLineBytes, kWriterRetryLines, kWriterExpectedPassesPerMinute, kWriterFlightMinutes, kWriterReserveMinutes, WRITER_WAKE_EVERY_NS, WRITER_FLUSH_TO_DISK_EVERY_NS, WRITER_STALL_NS (values match md) | record_writer.h:34-46 | NOTE |
| A29 | Never named in md: LineKind, LINE_*, LINE_KIND_NAMES, SPAN_STAGE_NAMES, every *_KEY_* macro, RECORD_FILE_NAME_FORMAT, RECORD_*_OPEN_FLAGS, RECORD_FRAME_PATH_FORMAT (values shown by the example lines) | record_file.h:14-108 | NOTE |
| A30 | Never named in md: RecorderState values, kRecordQueueRecords, kRecordQueueWatermark, QUEUED_SPAN/EVENT, ProducerPushEvent, ThreadCount, FieldType values, TextValue, FieldValue, kFieldNameBytes, kRecordMaxRecordBytes, the C makers FieldInt/Float/Bool/Text | recorder_internal.h:26-31; recording_thread.h:25-37, 86; record_field.h:11-68 | NOTE |

## B. Decisions vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | RCD25 (W1 a): "a bounded retry queue of 64 lines (two index queues over LineText slots) ... a full retry queue drops, counted". Header: 64 and step 7 present; NO retry storage in Writer (one `m_line`), NO retry-drop counter. MISSING | ledger:1049; record_writer.h:37, 94-107, 133 | BLOCKING |
| B2 | RCD20 (K1): "the registers-refused counter [is] gone". Header keeps m_droppedKeys "registers refused" (see E2) | ledger:1040; recorder.h:54-55, 69 | (see E2) |
| B3 | PY3 (Q1): "a span is (stage, start, end, names, values); no packing on the hot path". Header: tuple in recording_thread.h, but "packs them with its one precompiled struct.Struct" in two others (see E3) | ledger:1044; record_field.h:57-59; record_span.h:35-36 | (see E3) |
| B4 | RCD19 item 7 (G2): "the GPU event dropped". Header still lists "the GPU's memory and load" as an event | ledger:1039; record_event.h:11-12 | MINOR |
| B5 | RCD31: "RecorderCounters stays unpadded (40 bytes, one cache line)". Header unpadded: holds; sizeof = 28 measured, not 40 | ledger:1055; recorder_internal.h:33-46 | MINOR |
| B6 | TEL2: a fault degrades to "drop, count (frames and records), one event, a chat line". Header: counts and the app's chat line; no event (the writer never records) | ledger:958; recorder.h:51-52 | MINOR |
| B7 | TEL14/TEL16: "PNG level 1 fixed" for frames and masks. No header states the level ("lossless PNG" only). MISSING | ledger:973, 975; record_frame.h:1 | MINOR |
| B8 | D8 fix: "only Die writes the deadline, by a compare-and-swap from 0". Header: Destroy uses the CAS from 0; Die stores unconditionally | review:1275; record_writer.h:75-76 | MINOR |
| B9 | D12 fix: "Create resets every mb_announced". MISSING from headers | review:1279; recording_thread.h:48-50 | MINOR |
| B10 | Held. RCD1 ambient, no handle, three contracts, one writer, one file per process: recorder.h:1-6, 31-47. (Its "span ring and event ring per thread", "one clock line" superseded by RCD11/RCD19) | ledger:1021 | - |
| B11 | Held. RCD2 FrameSize uint16, FrameView, RecorderFrameConfig takes FrameSize: frame_types.h:9-25; recorder.h:21-24. (Home recorder.h superseded by RCD5; channel by RCD22; RecorderTimestamp by RCD15) | ledger:1022 | - |
| B12 | Held. RCD3 one instance and one file per process, pid in the name, the app the only frame process: record_file.h:14; recorder.h:26. (RecordSample superseded by RCD4) | ledger:1023 | - |
| B13 | Held. RCD4 no sample contract; three contracts: record_span.h, record_event.h, record_frame.h. (GPU event superseded by RCD19) | ledger:1024 | - |
| B14 | Held. RCD5 header split by group; frame_types.h shared: recorder.h:3-6; frame_types.h:1-2 | ledger:1025 | - |
| B15 | Held. RCD6 one wake-up object, 5 s timer, opaque OsThread/OsEvent, WriterRun: record_writer.h:22-27, 43, 144. ("never by a span" superseded by RCD11 watermark) | ledger:1026 | - |
| B16 | Held. RCD7 OsEvent carried to runtime_internal.h; atomic thread pointer; Die reason and deadline homes; mask limit "from config": record_writer.h:22-23, 98-99, 103; frame_pool.h:20 | ledger:1027 | - |
| B17 | Held. RCD8/RCD9 util homes, SPSC endpoint types, head/tail/drop on own lines, index queue, pool = free + ready queues, no per-slot state: spsc_record_queue.h:25-31, 109-111; frame_pool.h:52-57. (Offsets 0/64/128 superseded by RCD12: now 64/128/192) | ledger:1028-1029 | - |
| B18 | Held. RCD11 superseded by RCD18, RCD20, RCD23 except: cut field, typed fields, watermark, time reference at every fsync, drop gap: record_field.h:26, 51-55; recording_thread.h:24-28, 42-47; record_file.h:3-4 | ledger:1031 | - |
| B19 | Held. RCD12 cut rule on text, last pass = normal pass + die line, no cached indexes, gap protocol, one snapshot per pass, FieldCount/TextLength, makers validate in Python: record_field.h:12-13, 60-64; record_writer.h:126, 138-140; recording_thread.h:42-47. ("one precompiled Struct" superseded by PY3, see E3) | ledger:1032 | - |
| B20 | Held. RCD14/RCD15/RCD16 names RecordingThread, ThreadProducer, MonotonicNs/Now, DurationNs, SPAN_QUEUE_MESSAGE, record_file.h, LINE_KIND_NAMES, SPAN_STAGE_NAMES, open flags, EVENT_KEY_FIELDS, mb_lastWriteFailed, m_oldestReadyFramePublishedAt, unusedCtx | monotonic_clock.h:9-12; record_file.h:15-17, 36-43, 79; recorder_internal.h:43; record_writer.h:101; recorder.h:43 | - |
| B21 | Held. RCD17 31 + 1 fields; die at the cap; ringless counter: record_field.h:21-22; recording_thread.h:20-22; record_writer.h:105 | ledger:1037 | - |
| B22 | Held. RCD18 "no reserve and commit in the contract"; queued count for the watermark: spsc_record_queue.h:46-65. (Bytes deque superseded by PY3) | ledger:1038 | - |
| B23 | Held. RCD19 items 1, 2, 4: LINE_TIME_REFERENCE "time" with monotonic_ns, wall_us, boot_ns; cap 16 dies; util headers | record_file.h:23, 52-56; recording_thread.h:20-26 | - |
| B24 | Held. RCD21/RCD22/RCD23 actor headers with prefixes; Create/Destroy names; SpscConsumerFront/Pop; RecordsQueued/Dropped; maxRecords; IndexQueueFront; FramePool slot functions; m_queueEnds in Writer; slots + byte area; queue list in the writer. (RCD23's "line lost" superseded by RCD25, see E1) | spsc_record_queue.h:36-65, 83-112; index_queue.h:38; frame_pool.h:60-71; record_writer.h:102-104 | - |
| B25 | Held. RCD24 "every header compiles": gcc -std=c11 -Wall -Wextra -pedantic, 10/10 recorder headers clean | ledger:1048 | - |
| B26 | Held. RCD27 record queues lock-free SPSC; pool under a lock (one lock not expressed, see A10/E7) | ledger:1051; index_queue.h:1-3 | - |
| B27 | Held. PY1 C keeps real atomics, Python built-in containers; PY2 no numpy queue; GIL2 the recorder creates no recording thread, 16 | spsc_record_queue.h:94-111; index_queue.h:4-5; recording_thread.h:1-3 | - |
| B28 | Held. PRF1 stage enum + name text; PRF2 no marks, caller's timestamps; PRF3 Create(sessionDir, process); PRF4 the over-cap thread dies; PRF5 cap = design count 16; PRF6 FlushInDie as Die step 3; PRF7 no handle | record_span.h:16-46; record_file.h:40-43; recorder.h:31-43; recording_thread.h:20-26 | - |
| B29 | Held. TEL3 generic sink; TEL5/TEL13 lossless, refuse start under reserve; TEL7 full rings and pools drop and count; TEL17 30 passes/min, 40 min, 5 min, 0.45 | recorder.h:28-30; record_frame.h:1, 17-18; record_writer.h:38-46; recorder_internal.h:59-61 | - |
| B30 | Held. RVW3 the pixels copied during the call; RVW4 one instance, one queue per thread, die past the cap; RVW6 a file per process | record_frame.h:28-32; recording_thread.h:3-4, 20-22; record_file.h:14 | - |
| B31 | Held. D2, D3, D4, D5, D6 (as amended to 31), D7, D9, D10, D13 (names drift, see E5), D14 | record_writer.h:75, 77-79, 105, 140; recording_thread.h:63-68; spsc_record_queue.h:105; record_frame.h:14-16, 30-32; recorder.h:56-63 | - |
| B32 | Superseded, no header consequence: TEL1, TEL9-TEL12, TEL15, TEL19 (by RCD1, PRF5, RCD6, RCD12, TEL14, TEL16, TEL17); RVW5 (by RVW6); D1, D11 (by RCD23, RCD25) | ledger:919, 968-971, 974, 978, 949; review:1268, 1278 | - |
| B33 | No header consequence (process, drawings or doc rules): RCD10, RCD13, RCD26, RCD28, RCD29, RCD30, TEL4, TEL6, TEL8, RVW1, RVW2, RVW7, REV7, REV8 | ledger:1030, 1033, 1050, 1052-1054, 960, 965, 967, 945-946, 951, 996, 1014 | - |

## C. Decisions vs document

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | md: the GPU gauges are an event, topic "gpu", once a second; PERF_GPU "became the event topic gpu". RCD19 item 7: "the GPU event dropped"; no later row restores it | md:99, 305, 414, 435; ledger:1039 | BLOCKING |
| C2 | md failure matrix: a failed write: "the line lost and counted; the writer goes on". RCD25 (W1 a): the line goes to the retry queue | md:261; ledger:1049 | BLOCKING |
| C3 | md cites PRF4 for the cut rule and for drop-new. PRF4's decision column holds neither (cost table, die order, bytearray, PERF_GPU, the 33rd thread) | md:122, 136, 266, 319, 356; ledger:956 | MINOR |
| C4 | md: PRF2 to PRF6 incl. "the 128-byte record ... the drain" are "unchanged". RCD11 replaced the 128-byte record; md:120-122 itself changes the drain and the shape | md:187; ledger:1031 | MINOR |
| C5 | md: RVW4 gives "two rings per thread". RVW4: "a ring per thread"; header: one queue per thread | md:186; ledger:948; recording_thread.h:3-4 | MINOR |
| C6 | md: TEL2 "unchanged". TEL2 requires "one event" per degrade; md says the writer never records | md:191, 304; ledger:958 | MINOR |
| C7 | md cites RCD2 for "no handle". The ambient ruling is RCD1; RCD2 is FrameSize, FrameView, OPEN 1-4 | md:409; ledger:1021-1022 | MINOR |
| C8 | md cites RCD7 for the event-driven writer. RCD6 ruled it | md:421; ledger:1026-1027 | MINOR |
| C9 | md cites RCD3 for RecordFrame(folder, name, at, FrameView*). FrameView came in RCD2, folder in RCD22 | md:413; ledger:1022, 1046 | MINOR |
| C10 | md D8: Destroy stores by CAS from 0, Die unconditionally. Review D8: "only Die writes the deadline, by a compare-and-swap from 0" | md:157-158; review:1275 | MINOR |
| C11 | md: R4's change "no record ever cut" stated as applied. RCD12 restored the cut rule on text fields | md:110-111, 373; ledger:1032 | MINOR |
| C12 | md: R4 change 2 ("registered keys ... a definitions preamble") not marked superseded; only change 1 is. RCD20/K1 removed registration | md:369-379; ledger:1040 | MINOR |
| C13 | Ledger ID collision: md's W1, K1, Q1, T1 are sub-labels inside RCD25, RCD20, PY3, RCD19; the ledger rows `\| W1 \|` (692 "grading a live session", 850 "kill-shot"), `\| K1 \|` (718), `\| Q1 \|` (653), `\| T1 \|` (672) are unrelated | md:7, 123, 202, 290, 314, 416; ledger:653, 672, 692, 718, 850 | NOTE |
| C14 | RCD29 names the frame buffer "module 06"; md says module 04; folders: 04-framebuffer, 06-sam3_server (ledger drift, md matches the folders) | md:23; ledger:1053 | NOTE |

## D. Internal consistency of the document

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | Test 4: "a 2048-byte text field is refused and counted". Elsewhere: "a record is never refused for its text"; "a text past the bound: cut, never refused" (header agrees) | md:321 vs md:122, 202; record_field.h:60-62 | BLOCKING |
| D2 | A failed line: "kept for retry (W1)" / the retry test / "the retry queue of 64 lines" vs "the line lost" (see C2) | md:202, 330, 416, 455 vs md:261 | (see C2) |
| D3 | "Destroy and FlushInDie set STOPPING, wake it, join with the timeout" vs FlushInDie "never join" | md:120 vs md:24, 132; record_writer.h:141-142 | MINOR |
| D4 | "Why spans do not wake the writer" vs the half-full wake set by span pushes | md:302 vs md:20, 124, 291 | MINOR |
| D5 | A record outside RUNNING: "drop, count" / "dropped and counted" vs "anything else returns; ... lost, not counted" (header: dropped and counted) | md:24, 167 vs md:121, 244; recorder_internal.h:20-21; record_span.h:38-39 | MINOR |
| D6 | Writer cost: "250 lines ... 0.74 ms; a 25,000-line burst 185 ms" vs the per-line numbers 2.9 us format + 1.4 us write (= 1.08 ms and 107 ms) | md:208 vs md:236 | MINOR |
| D7 | The old Python span cost: "437 ns" vs "the pre-R4 f-string 723 to 804" | md:290, 377 vs md:231 | MINOR |

Checked and consistent across md sections: the thread cap 16 (md:20, 135, 324, 420); the queue size 20,000 (md:122, 266, 291, 319); the 5 s wake and fsync (md:21-22, 33, 418); the pools 8 + 24 (md:23, 133, 263); the file name record-<process>-<pid>.jsonl (md:27, 98, 119, 417); the folders: the app makes the session folder, the writer the frame folders (md:29, 205, 449).

## E. Internal consistency of the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | RecordFile comment: "A failed append is counted and that line is lost ... the writer goes on with the next record" vs step 7 retry queue, kWriterRetryLines, and mb_writePaused "the writer retries" | record_writer.h:54-57 vs record_writer.h:37, 133; recorder.h:60-61 | BLOCKING |
| E2 | RecorderHealth.m_droppedKeys "registers refused: the table was full or the name too long" vs "No table, no id"; no matching RecorderCounters field; no health key | recorder.h:54-55, 69 vs record_field.h:3; recorder_internal.h:37-46; record_file.h:95-104 | BLOCKING |
| E3 | Python record form: "packs them with its one precompiled struct.Struct" / "packed ... with one precompiled struct" vs "the record is a tuple appended to the thread's deque" / "a deque of record tuples" (PY3) | record_field.h:57-59; record_span.h:35-36 vs recording_thread.h:74-75; spsc_record_queue.h:5 | BLOCKING |
| E4 | RECORDER_STALL_NS used in a comment, defined nowhere; the constant is WRITER_STALL_NS | recorder.h:59; record_writer.h:45 | MINOR |
| E5 | One flag, three names: mb_writePaused (health), mb_lastWriteFailed (counters), "last_write_failed" (file key) | recorder.h:73; recorder_internal.h:43; record_file.h:102 | MINOR |
| E6 | RecordCount typedef'd in two homes (same type, legal C11) | recorder.h:16; spsc_record_queue.h:17 | MINOR |
| E7 | "under the pool's lock" (one lock) vs a pool of two IndexQueue, each with its own m_lock | record_frame.h:29 vs frame_pool.h:53-54; index_queue.h:24 | MINOR |
| E8 | Comments say "from config" / "a config constant" / "config values read at Create"; the values are compile-time enum constants | frame_pool.h:20-25; recording_thread.h:20-27; record_writer.h:32-41 | MINOR |
| E9 | RecordFileWriteHeader(f, infoJson) takes no FrameSize, yet the info line carries "frame" w/h; under RECORDER_NO_FRAMES no infoJson exists | record_writer.h:66-67; record_file.h:58-62; recorder.h:20-26 | MINOR |
| E10 | m_droppedByThreadsWithoutQueue maps to no RecorderHealth field and no health key | record_writer.h:105; recorder.h:65-76 | NOTE |
| E11 | A PNG name clash is "a dropped frame, counted" and also m_pngNameClashes; which counter(s) increment is unstated | record_frame.h:30-32; recorder.h:56-57 | NOTE |
| E12 | kFieldNameBytes defined, used nowhere (names are pointers) | record_field.h:20 | NOTE |
| E13 | index_queue.h included by record_writer.h; Writer has no IndexQueue member | record_writer.h:14, 94-107 | NOTE |
| E14 | Comment layout: actor list broken (line 4 lacks " * "); two path comments for one function; missing period before "The timer" | recorder_internal.h:1-8; record_writer.h:63-64, 137 | NOTE |
| E15 | RECORD_INVALID_ARG list omits a wrong pixel format; the pool comment says the format is checked | record_frame.h:13-16; frame_pool.h:30-31 | NOTE |
| E16 | Declared or referenced, defined outside the 16 headers: OsLock, OsThread, OsEvent (runtime_internal.h), DieActionFn | index_queue.h:17; record_writer.h:26-27; recorder.h:41 | NOTE |
| E17 | m_stopDeadline is set by CAS from 0; its reset at a second Create is unstated | record_writer.h:75-76; recorder_internal.h:23-25 | NOTE |
| E18 | gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11: all 10 01-recorder headers pass with zero diagnostics (no FAIL). 00-util/fixed_text.h alone: "ISO C forbids an empty translation unit" | 00-util/fixed_text.h:12 | NOTE |
