# Recorder consistency check, round 2, checker 1 (2026-10-21)

**Verdict: NOT CONSISTENT. 2 BLOCKING, 29 MINOR, 17 NOTE (48 findings).**

Sources: the 16 headers (00-util x6, 01-recorder x10); recorder.md; docs/spec-harden2-cleanup.md
lines 908-1062. The aggregate's 16 code blocks are byte-identical to the 16 headers (scripted
compare). Sizes measured with gcc on x86-64: struct Recorder 1408 B, RecorderCounters 28 B,
SpscRecordQueue 256 B (head 64, tail 128, drop 192). Rows marked OK in table B are not findings.

## A. Document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | The pass steps differ. Doc: step 1 sleep, step 2 reset the flag; a set during the pass goes to step 2, so the re-pass clears. Header: step 1 is wait, clear, load; step 2 is the queue snapshot; a set during the pass goes to step 2, so the re-pass does not clear | recorder.md:21; record_writer.h:136-137, 151-152 | BLOCKING |
| A2 | Python Create sample: infoJson passed inside RecorderFrameConfig (2 args); SAM3 sample passes 3 args. Header: 4 params; RecorderFrameConfig has only m_size | recorder.md:42, 84; recorder.h:20-22, 34-39 | MINOR |
| A3 | Instance size "1336 bytes" stated as draft 14's current state; current headers measure 1408 B | recorder.md:152; recorder_internal.h:50-58 | MINOR |
| A4 | Retry: doc "appended again next pass"; header step 7 of the same pass (and doc's own drawing 2 says step 7) | recorder.md:263; record_writer.h:145; recorder.md:21 | MINOR |
| A5 | Line buffer "pinned to twice the record bound"; header asserts >= 2 x 8192 + 1024 and sets 32768 (4x) | recorder.md:211; record_writer.h:40, 119 | MINOR |
| A6 | Python pools: "two deques of indexes, each under its own Lock"; util header: Python deque, atomic under the GIL, no lock | recorder.md:239; index_queue.h:4-5 | MINOR |
| A7 | Destroy always joins in the doc; header abandons the writer without a join when the deadline passes; the abandon path is not in the doc | recorder.md:24, 121; record_writer.h:157-158; recorder_internal.h:25-26 | MINOR |
| A8 | Tests 4 and 5: INVALID_ARG and a bad value "counted"; RecorderHealth drop causes list neither | recorder.md:323-324; recorder.h:60-61 | MINOR |
| A9 | Drawing 6: "the recording threads add drops"; header: the writer sums the threads' counts each pass (doc line 240 agrees with header) | recorder.md:25; recorder_internal.h:34-35 | NOTE |
| A10 | SPAN_ASR / "asr" never named; no helper row in section 11 | record_span.h:20; record_file.h:42; recorder.md:431-450 | NOTE |
| A11 | QUEUED_SPAN, QUEUED_EVENT (the kind byte) not described | recording_thread.h:35-38 | NOTE |
| A12 | kRecordFolderBytes 64, kRecordNameBytes 32: doc says "length" only | record_frame.h:10-13; recorder.md:161-162 | NOTE |
| A13 | RecordSlot, RingPosition, ByteOffset, kRingBytesPerRecordExpected 64: doc says only "a ring of record slots plus a byte area" | spsc_record_queue.h:70-89; recorder.md:7 | NOTE |
| A14 | kWriterExpectedPassesPerMinute 30 (a factor of the reserve) never stated | record_writer.h:42; recorder_internal.h:60-62; recorder.md:192, 428 | NOTE |
| A15 | FramePoolCreate/Destroy, FramePoolsCreate/Destroy, FrameSlot m_capturedAt/m_publishedAt not described | frame_pool.h:41-47, 64-65, 92-93 | NOTE |
| A16 | The no-queue path (mb_queueTried, m_dropped*WithoutQueue) described only in a history row | recording_thread.h:67-68, 75; record_writer.h:111-112; recorder.md:157-159 | NOTE |
| A17 | IndexQueue functions, SLOT_NONE, SpscProducerRecordsDropped not named | index_queue.h:15, 32-38; spsc_record_queue.h:55 | NOTE |

## B. Decisions vs headers

| # | what (latest ruling: its consequence -> the header) | where (file:line) | severity |
|---|---|---|---|
| B1 | RCD31 "unpadded (40 bytes, one cache line)" -> unpadded, but measures 28 B | spec:1055; recorder_internal.h:38-47 | MINOR |
| B2 | TEL2 "drop, count ..., one event, a chat line" -> no event per fault; no ruling supersedes it | spec:958; recorder.h:57-58 | MINOR |
| B3 | TEL3 (2) "fsync the trace handle only, never the PNGs" -> MISSING (step 6 silent on PNG fsync) | spec:962; record_writer.h:141-144 | NOTE |
| B4 | RCD5 "recorder.h holds the clock" superseded by RCD19 T1 -> recorder.h:1 still says "its clock" | spec:1025, 1039; recorder.h:1 | NOTE |
| B5 | RCD37 "cut (bytes lost) on a truncated record only; 31 plus 1" -> kRecordMaxCallerFields 31, FIELD_NAME_CUT | spec:1061; record_field.h:24-31 | OK |
| B6 | RCD36 8192 bound -> kRecordMaxRecordBytes 8192 | spec:1060; record_field.h:26 | OK |
| B7 | RCD35 16384, RecordResult returned by all three -> present | spec:1059; recording_thread.h:28; record_field.h:70-76; record_span.h:40; record_event.h:12; record_frame.h:24 | OK |
| B8 | RCD34 B1 no gpu; B2 dropped and counted outside RUNNING; A1 asr_clips/ | spec:1058; grep: no gpu; recorder_internal.h:20-21; recorder.h:26-28 | OK |
| B9 | RCD38 item list (retry storage, flags, RecordCount home, infoJson, header frame size, 32 KiB + assert, Destroy STOPPED, resets, name in ThreadProducer, reported counts, split queueless counts, two locks, PNG level 1, no gpu/packed/RECORDER_STALL_NS/clock line) -> all present; "a set during the pass: step 2" present but see E1 | spec:1062; record_writer.h:83-119, 151-152; recording_thread.h:61-77; frame_pool.h:49-51; record_frame.h:1-2 | OK |
| B10 | RCD25 W1: 64 lines, two index queues, retried oldest first until one fails, full drops counted | spec:1049; record_writer.h:41, 83-86, 114-116, 145 | OK |
| B11 | RCD23 slot ring + byte area; RecordFrame picks pool by format; RecordFileCreate(dir, process); queue list in Writer | spec:1047; spsc_record_queue.h:78-97; record_frame.h:19; record_writer.h:68, 108-110 | OK |
| B12 | RCD22 names (Front/Pop, RecordsQueued/Dropped, IndexQueueFront, FramePool* names, RecordFile* names, WriterIsStalled no stamp) | spec:1046; spsc_record_queue.h:54-66; index_queue.h:38; frame_pool.h:64-75; record_writer.h:68-74, 133 | OK |
| B13 | RCD21 one header per actor, a prefix per role | spec:1045; recorder_internal.h:1-8 | OK |
| B14 | RCD20 / K1 names as literals, no registration | spec:1040; record_field.h:11; record_event.h:9 | OK |
| B15 | PY3 / Q1 tuple deque; PY1 built-in container or lock; GIL2 no thread exists to record | spec:1044, 1041, 1042; spsc_record_queue.h:5-6; index_queue.h:4-5; recording_thread.h:2-3 | OK |
| B16 | RCD19 time reference names; cap 16, 17th dies; T1 util headers | spec:1039; record_file.h:23-24, 53-57; recording_thread.h:20-27 | OK |
| B17 | RCD12 last pass = normal pass + die line; one snapshot; drop gap protocol; no cached indexes; makers validate | spec:1032; record_writer.h:137, 153-155; recording_thread.h:43-47; spsc_record_queue.h:95-97; record_field.h:84-86 | OK |
| B18 | RCD9 typed endpoints, own cache lines, index queue, no per-slot state | spec:1029; spsc_record_queue.h:26-32, 110-112; frame_pool.h:5-6 | OK |
| B19 | RCD6 + RCD11 event-driven writer, watermark wake | spec:1026, 1031; record_writer.h:4-5; recording_thread.h:25, 100-102 | OK |
| B20 | RCD7 OsEvent in runtime_internal.h; mask limit from config | spec:1027; record_writer.h:23-28; frame_pool.h:20-21 | OK |
| B21 | RCD4 no sample; RCD2 FrameView, FrameSize uint16 | spec:1024, 1022; frame_types.h:9-25; record_frame.h:24-29 | OK |
| B22 | RCD1 / PRF7 ambient, no handle | spec:1021, 1018; recorder.h:3 | OK |
| B23 | PRF1 stage enum, name as text; PRF2 caller holds the start stamp | spec:908, 920; record_span.h:16-46; record_file.h:41-44 | OK |
| B24 | PRF4 / RVW4 the over-cap thread dies; PRF5 cap = design count from config, never nproc | spec:956, 948, 957; recording_thread.h:20-22 | OK |
| B25 | TEL5, TEL13, TEL16 lossless PNG level 1 at the source size | spec:961, 972, 975; record_frame.h:1-2; frame_types.h:8 | OK |
| B26 | TEL17 W x H x 3 x 0.45 x 30 x minutes; 40 and 5 minutes | spec:976; recorder_internal.h:60-62; record_writer.h:42-50 | OK |
| B27 | TEL7 full queues and pools drop and count (pause superseded by RCD25) | spec:966; record_span.h:37; frame_pool.h:68 | OK |
| B28 | TEL12 64-bit and float values as macros; TEL18 free-space product in uint64 | spec:971, 977; record_writer.h:31, 47-50 | OK |
| B29 | RUN3 / PRF6 FlushInDie fits DieActionFn, Die step 3 | spec:982, 979; recorder.h:46-48; 03-runtime/runtime.h:18 | OK |
| B30 | FB8 / RCD31 unpadded counters with the rate comment | spec:1004; recorder_internal.h:34-37 | OK |
| B31 | RVW3 the job holds the shared slot; the copy during the call | spec:947; record_frame.h:19-21 | OK |
| B32 | REV7, REV8, RCD13-17, RCD24, RCD26-30, RCD32-33: process, drawings, history; nothing for the headers | spec:996, 1014, 1033-1037, 1048, 1050-1057 | OK |

## C. Decisions vs document

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | Full queue "drop-new, by ruling (TEL7, RCD12)": RCD12's consequence holds no drop-new rule | recorder.md:268; spec:1032 | MINOR |
| C2 | "TEL3's JSON string became typed fields (K1)": typed fields are RCD11 (R4); K1 (RCD20) is the literal names | recorder.md:190; spec:1031, 1040 | MINOR |
| C3 | Stall row cause "(TEL, the owner's)": no ID, no SEEN/DESIGNED/FORCED; the ruling is TEL10 | recorder.md:264, 213; spec:969, 1014 | MINOR |
| C4 | TEL2 "amendment" (no event per fault) presented as decided; no ruling cited | recorder.md:193; spec:958 | MINOR |
| C5 | Shared-mutex deque 429 ns, with notify 758; RCD22 has 264 and 593; basis not stated | recorder.md:280; spec:1046 | MINOR |
| C6 | Native thread id "dropped" as a verdict, with no ruling | recorder.md:457 | NOTE |
| C7 | The cut rule and drop-new cited to PRF4; PRF4's consequence holds neither (only RCD12 names "PRF4's cut rule") | recorder.md:137, 321, 358; spec:956, 1032 | NOTE |

## D. Internal consistency of the document

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | Time reference line "unchanged" against perf; the change table says once at Create became every fsync | recorder.md:189 vs 126 | MINOR |
| D2 | Wake cost "about a microsecond" vs "a wake 1.8 us" | recorder.md:304 vs 236 | MINOR |
| D3 | record_span in Python: names + values tuples vs a tuple of field makers (header: makers only for odd shapes) | recorder.md:51-52 vs 71-72; record_field.h:78-81 | MINOR |
| D4 | "packed bytes 241" vs "212 to 241" vs "pack_into numpy byte ring 241" | recorder.md:233 vs 279 vs 286 | MINOR |
| D5 | Record call "no lock" vs the half-full set taking the event's lock | recorder.md:20, 202 vs 173-174, 236 | MINOR |
| D6 | "Two processes open one file": Create fails on O_EXCL; but the name carries the pid and the app's mkdir fails first | recorder.md:272 vs 27, 29-31, 207 | MINOR |
| D7 | Test 22 (second Create succeeds) vs test 21 (same file name fails): the same process and folder give the same name | recorder.md:340-341; record_file.h:14-15 | MINOR |
| D8 | The event's "png" key named as the request; neither the pass sample nor the contract sample carries it | recorder.md:129, 227 vs 80-81, 221 | NOTE |
| D9 | Frame line "ok":1 (integer) vs booleans in the health line; no type stated | recorder.md:222 vs 224 | NOTE |
| D10 | A record pushed after the last pass "counted as queued"; no health field counts it; drawing 5 says drop, count | recorder.md:246 vs 24 | NOTE |

## E. Internal consistency of the headers

gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on the 10 recorder headers: all pass, no
output, no FAIL. The 6 util headers alone: only fixed_text.h warns "ISO C forbids an empty
translation unit" (fixed_text.h:12).

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | The clear is in step 1; a set during the pass restarts at step 2, so the flag stays set; the end-of-pass test cannot tell a new set from the old one: the writer re-passes without end | record_writer.h:136-137, 151-152 | BLOCKING |
| E2 | "Destroy and FlushInDie ... never join; only Destroy joins": one sentence, both ways | record_writer.h:156-157 | MINOR |
| E3 | Destroy "waits ... then joins it" vs abandons without a join past the deadline | recorder.h:41-43 vs record_writer.h:157-158 | MINOR |
| E4 | "One writer per transition" vs Destroy also storing STOPPED; an abandoned writer later stores STOPPED again, after a second Create | recorder_internal.h:21-26; record_writer.h:157-158; recorder.h:32-33 | MINOR |
| E5 | Frame line "written after the PNG landed" vs FRAME_KEY_OK and a frame line after a failed or clashed write | record_file.h:83, 88; record_writer.h:141-143 | MINOR |
| E6 | "Every drop is also counted"; a bad value "counts it" vs the drop causes of RecorderHealth | record_field.h:69, 85-86 vs recorder.h:60-61 | MINOR |
| E7 | m_lastProgressAt stored "at the end of each pass" vs after each released slot | record_writer.h:80-81 vs 143-144 | MINOR |
| E8 | Stall = "a ready frame older than 5 s"; m_oldestReadyFramePublishedAt is stored only by the writer; a frame published while it is stuck is invisible | recorder.h:69; record_writer.h:80-81, 95-96, 131-133, 144 | MINOR |
| E9 | Producer path "Never a lock" vs the half-full set on a condition variable (its mutex) | recording_thread.h:80-81, 100-102; record_writer.h:23-25 | MINOR |
| E10 | fixed_text.h compiled alone: empty translation unit warning under -pedantic | fixed_text.h:12 | NOTE |
