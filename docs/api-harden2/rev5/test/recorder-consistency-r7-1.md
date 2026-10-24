# Recorder consistency check, round 7, reader 1 (2026-10-22)

**Verdict: NOT CONSISTENT. 0 BLOCKING, 9 MINOR, 20 NOTE.**

Sources: recorder-decisions-2026-10-21.md (abbrev. DEC), the 16 headers (00-util 6, 01-recorder 10),
runtime_internal.h, recorder.md (abbrev. MD), the ledger rows RCD40..RCD59.
Paths: util = docs/api-harden2/rev5/modules/00-util/, rec = docs/api-harden2/rev5/modules/01-recorder/.

Mechanical results:
- gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on all 10 rec/*.h: 10 pass, 0 warnings.
- recorder_aggregate_for_review.md: 16 of 16 header blocks byte-identical to the files.
- sizeof, measured with gcc on x86-64: SpscRecordQueue 192, RecordingThread 384, struct Recorder 7360, Writer 432.
- Leftover-name scan of all 16 headers: no FramePool, RetryLine, retry queue, FIELD_INVALID, lazy
  allocation, second Create, abandoned writer, shared stall field, or state compare-and-swap.
  "slot" appears only for the C record ring (util/spsc_record_queue.h:7,69-95) and the frame
  buffer's shared slot (rec/record_frame.h:23-24), never for the pool.

## A. Decision document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | Item 12 says only the two drop-record operations touch it: "Two operations exist on it, and only they touch it". The header repeats it: "nothing else touches its fields". The writer's last pass also writes cut-off counts into the drop records: "counted by kind into the entries' drop records (the writer holds each record's lock for that)". No third operation is declared. | DEC:155-160; rec/recording_thread.h:54-56,83-85; rec/record_writer.h:168-170 | MINOR |
| A2 | Item 9: "Both go through one internal function under the state lock". No header declares that function. The behaviour itself is stated. | DEC:106; rec/recorder_internal.h:24-29; rec/record_writer.h:83-91 | NOTE |
| A3 | Item 12 names `note_drop` and `take_drop_gap`. The headers use DropRecordNote and DropRecordTake. No header maps the Python names to the C names. | DEC:157-158; rec/recording_thread.h:83-85 | NOTE |
| A4 | Item 5's final order ("the die line, the time reference, the health line, and flushes") leaves out the fault lines. The header puts step 9 and its fault lines between the die line and the health line, as T1 requires. | DEC:65; rec/record_writer.h:171-174; rec/record_file.h:22-24 | NOTE |
| A-1 | Item 1, the index queue uses a lock: "a deque under one threading.Lock" | util/index_queue.h:1-5,24 | OK |
| A-2 | Item 2, one return arrow: "wait on m_wake ... clear it ... Then back to step 1, always" | rec/record_writer.h:136,159-160 | OK |
| A-3 | Item 3: NOT_CREATED, counts nowhere | rec/record_field.h:69-71; rec/recorder_internal.h:22-24 | OK |
| A-4 | Item 4: 16 KiB, twice the bound, a cut counted | rec/record_writer.h:34-43,57; rec/recorder.h:91-92 | OK |
| A-5 | Item 5: drain to empty or the deadline; Destroy deadline now+timeout; Die's own | rec/record_writer.h:163-176,86 | OK |
| A-6 | Item 6: BufferPool, m_freeList, m_workQueue, m_buffers, the six operations, m_framePool and m_maskPool, 8 and 24 buffers, mb_pngWritten, OldestFilledAt under the work-queue lock, 0 when the queue is empty | rec/buffer_pool.h:1-14,29-33,53-116 | OK |
| A-7 | Item 7: each thread counts its own drops; the writer sums them | rec/recorder.h:80-81,86; rec/record_writer.h:156-157 | OK |
| A-8 | Item 8: 16 entries at Create; a claim is an index; the 17th claim dies; Create false on an allocation failure | rec/recording_thread.h:3-6,30; rec/recorder_internal.h:54-58; rec/recorder.h:42 | OK |
| A-9 | Item 9: the four states; STOPPING only from RUNNING under the lock | rec/recorder_internal.h:22-35 | OK |
| A-10 | Item 10: reason, deadline, then STOPPING under the lock; release and acquire order | rec/recorder.h:58-63; rec/record_writer.h:83-91 | OK |
| A-11 | Item 11: a failed append ends the pass; the record stays at the front; later appends are skipped; step 9 still sums | rec/record_writer.h:140-142,160-162 | OK |
| A-12 | Item 12: three counts, two times, one mutex | rec/recording_thread.h:63-70 | OK, apart from A1 |
| A-13 | Item 13: `bool FieldInt(RecordField* out, ...)`, out unchanged on false | rec/record_field.h:80-94 | OK |
| A-14 | Item 14: session dir, process name and info JSON bounds checked in both builds; folder 64, name 32 | rec/recorder.h:25-31,39-41; rec/record_frame.h:10-13 | OK |
| A-15 | Item 15: once per process; Destroy false past its timeout; stores nothing; daemon thread | rec/recorder.h:33,51-56 | OK |
| A-16 | Item 16: OsEventIsSet exists; the set is skipped when the flag is already set | 03-runtime/runtime_internal.h:85; rec/recording_thread.h:146-149 | OK |
| A-T1 | T1, the fault line: LINE_FAULT and FAULT_KEY_AT, FAULT_KEY_WHAT, FAULT_KEY_COUNT | rec/record_file.h:36,96-101; rec/record_writer.h:157-158 | OK |
| A-T2 | T2 GONE: no retry queue in any header | scan | OK |

## B. Decision document vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | DEC item 5 says "The writer writes 230,000 lines a second", and the header repeats it. MD measures "a 25,000-line burst measured 185 ms", which is about 135,000 lines a second. The 230,000 figure is 2.9 us plus 1.4 us measured separately. | DEC:63; rec/record_writer.h:167; MD:213 | MINOR |
| B2 | Item 4: in C, a line that does not fit is written as far as it got, the reader skips it, and it is counted. MD gives only "the formatter stopping at its end" and the truncated_lines key in the sample line. No failure-matrix row covers it. | DEC:57; MD:214,228,264-279 | NOTE |
| B3 | Item 10's corner, a Die during a Destroy, gets no die line, and the reason is only in the hand-over log. MD does not state this. MD:261 says only that the second request waits for the drain. | DEC:127; MD:24,261 | NOTE |

The other decided items match MD's current state: 1 (MD:138,243), 2 (139), 3 (136,250), 5 (24,250), 6 (23,134,268,308), 7 (244), 8 (205,239), 9 and 10 (261), 11 (129,207,267,337), 12 (25,260), 13 (207,241,329), 14 (210), 15 (261,346), 16 (240), T1 (137,196).

## C. Headers vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | MD says "the C queue's head, tail and drop count each on their own cache line". SpscRecordQueue has no drop count. RCD59 removed it: "one home for a drop count (the queue's own counter removed)". | MD:214; util/spsc_record_queue.h:101-109 | MINOR |
| C2 | MD says "head, tail and the drop count on their own lines: 256 bytes a queue, 4 KiB for 16". sizeof(SpscRecordQueue) measures 192, and the struct has no drop count. | MD:307; util/spsc_record_queue.h:101-109 | MINOR |
| C3 | DropRecord, DropGap, DropKind, DropRecordNote and DropRecordTake are never named in MD. MD:25 and MD:260 describe the mechanism without these names. | rec/recording_thread.h:44-85 | NOTE |
| C4 | MD never names the makers FieldInt, FieldFloat, FieldBool and FieldText. It says only "the makers". | rec/record_field.h:91-94; MD:207,241,329 | NOTE |
| C5 | MD never names BufferPoolCreate, BufferPoolDestroy, BufferPoolsCreate, BufferPoolsDestroy, PoolBuffer or BufferPools.mb_present. | rec/buffer_pool.h:53-60,78-79,111-119 | NOTE |
| C6 | Not named in MD: the IndexQueue operations, the SpscRecordQueue operations, RecordFileCreate, RecordFileWriteHeader, RecordFileClose, ProducerPushEvent, LineText, DieReasonText, the RecorderState values, QUEUED_SPAN and QUEUED_EVENT. | util/index_queue.h:32-44; util/spsc_record_queue.h:37-65; rec/record_writer.h:54-55,73-79; rec/recording_thread.h:38-41,139; rec/recorder_internal.h:30-35 | NOTE |
| C7 | m_truncatedLines appears in MD only as a key in the sample health line. Its meaning is not described. | rec/recorder.h:91-92; MD:228 | NOTE |
| C8 | MD's TOCTOU table says "the writer walks at most the table's size". The header's step 2 says only "load the claimed entries once" and gives no limit. See E4. | MD:256; rec/record_writer.h:137 | NOTE |
| C-ok | Every recorder identifier that MD names exists in a header. MD's remaining names are perf and telemetry legacy names, other modules' helpers, or caller tuples in section 3. Every number MD gives for the current state matches the headers: 16, 16,384, 8 and 24, 8 KiB, 16 KiB, 31 fields, 192, 31, 8192, 64, 32, 5 s, 100 lines, 40 and 5 minutes, 15 stages, ten health values. | MD:7-279 | OK |

## D. Internal consistency of recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | The entry claim is stated two ways. MD:239: "in Python under the state Lock ..., in C by an atomic add". MD:310: "claims the next entry by an atomic add", with no build named. | MD:239 vs MD:310 | MINOR |
| D2 | Drawing 1 says "one record in, no lock". Gate item 1 says a drop takes the drop record's mutex and a half-full crossing takes the condition variable's lock. | MD:20 vs MD:205 | NOTE |

## E. Internal consistency of the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | At the deadline, leftover frames are "popped, returned and counted by kind into the entries' drop records". PoolBuffer carries no thread or entry index, so the writer has no entry to count a leftover frame into. | rec/record_writer.h:168-170; rec/recorder.h:85; rec/buffer_pool.h:53-60 | MINOR |
| E2 | One comment says "DROPPED and INVALID_ARG are counted in the health". The same comment block, at the maker paragraph, says that when a maker returns false the helper returns INVALID_ARG and "nothing is counted". | rec/record_field.h:69-71 vs rec/record_field.h:81-83; rec/recorder.h:79-80 | MINOR |
| E3 | The one hole: a record pushed between the final empty check and the STOPPED store is described as "dropped and counted after the last health line". A producer that loaded RUNNING before the stop and pushes after the final check succeeds in its push. Nobody pops that record, and nobody counts it, so the count is lost. The window is described as "microseconds". In Python the producer can be switched out between its state load and its push for up to the 5 ms switch interval. | rec/record_writer.h:174-176; DEC:17,67 | MINOR |
| E4 | The 17th claim is an atomic add and "dies". After it, m_claimedCount is 17. The Die that follows runs FlushInDie, and the last pass repeats step 2's snapshot. Step 2 gives no limit, so a C build that follows the header reads m_threads[16], which is out of bounds. | rec/recorder_internal.h:56-58,65-66; rec/record_writer.h:137,164 | MINOR |
| E5 | Destroy gives the writer the deadline now plus its timeout. It also waits on m_stopped for the same timeout. The writer writes the die, fault, time and health lines and the flush after the deadline. So a drain that runs to the deadline makes Destroy return false, and the pools are then not freed. | rec/record_writer.h:86,171-174,178-181; rec/buffer_pool.h:12-13 | NOTE |
| E6 | runtime_internal.h declares no create or destroy for OsEvent or OsLock, and no start or join for OsThread. Create allocates them and Destroy "joins". OsLock is also typedef'd twice; that is legal in C11. | 03-runtime/runtime_internal.h:76-92; rec/recorder.h:51-56 | NOTE |
| E7 | The comment block lists @m_droppedSpansReported and @m_droppedEventsReported. m_droppedFramesReported has no comment. | rec/recording_thread.h:96-97 vs :107 | NOTE |
| E8 | DropKind's comment says a frame drop is "a frame the pool refused". m_droppedFrames also counts frames dropped under the reserve, while STOPPING, for INVALID_ARG, and at the deadline. | rec/recording_thread.h:43 vs rec/recorder.h:83-87 | NOTE |
| E9 | The writer's health line has the key "stalled". Only RecorderReadHealth on the main thread computes stalled. No header says how the writer fills that key. | rec/record_file.h:120; rec/recorder.h:95-97; rec/record_writer.h:130-133 | NOTE |
| E10 | One comment says "the other counts are stored by the actor that sees the fault". Every other count is stored by the writer, which MD:25 states. | rec/recorder_internal.h:37-38 | NOTE |
| E11 | In step 4 a failed append "ends the pass". The last pass repeats steps 2 to 6 "again and again until ... empty, or ... deadline". With a dead disk it is not stated whether the last pass retries in a tight loop until the deadline or stops. | rec/record_writer.h:140-142,164-166 | NOTE |
| E12 | kRecorderSessionDirBytes is sized so that the record file path fits PathText (256). A PNG path can reach 192+1+63+1+31+4 = 292 bytes, and no type holds that path. | rec/recorder.h:28; rec/record_file.h:16; util/common_names.h:10 | NOTE |
