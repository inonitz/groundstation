# Recorder consistency, round 6, checker 3 (2026-10-22)

**Verdict: NOT CONSISTENT. 3 BLOCKING, 14 MINOR, 21 NOTE** (unique findings; a row marked "= Xn" repeats one and is not counted twice).

Sources: D = docs/api-harden2/rev5/test/recorder-decisions-2026-10-21.md; md = 01-recorder/recorder.md; headers by file name (00-util, 01-recorder, 03-runtime/runtime_internal.h); L = docs/spec-harden2-cleanup.md.
gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on all ten 01-recorder headers: clean, no FAIL. The aggregate holds all sixteen headers verbatim (checked by substring match).

## A. Decision document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | Item 10: "Die stores the reason first, and asks the recorder to stop second ... the stop request is an atomic store with release order". Headers: the stop request is a compare-and-swap FIRST; the winner stores the reason and the deadline AFTER it | D:125; recorder.h:59-60; record_writer.h:83-87 | BLOCKING |
| A2 | Item 5: "A Die during a Destroy waits for the Destroy's drain until its own deadline". record_writer.h says the opposite: "A Die during a Destroy loses the compare-and-swap and returns at once" (RCD57 wording; RCD58 superseded it). recorder.h:61-62 and record_writer.h:171-173 follow the decision | D:63; record_writer.h:87-88 | BLOCKING |
| A3 | Item 10's order (reason stored before the stop request) gives a Die during a Destroy a die line unless the writer is past that step ("the one corner"). Headers: the loser "stores nothing ... no die line" in every case | D:125-127; recorder.h:61-62; record_writer.h:87-89 | MINOR |
| A4 | Item 13 (+ L RCD58): a maker's false stops the helper, which returns the code; no record call. record_field.h lists "a maker returned false" under INVALID_ARG and says INVALID_ARG "is counted in the health"; recorder.h says "nothing is counted" | D:168; record_field.h:66-72; recorder.h:79-80 | MINOR |
| A5 | Item 6 names five pool operations. The header has a sixth, BufferPoolPeekFilled, needed by item 11's "returns to the free list only after its frame line" (L RCD57). Not named in item 6 | D:75, D:151; buffer_pool.h:89 | NOTE |
| A6 | The status block still says items 4, 6, 8, 10, 12-15 are "to be applied to the headers"; L RCD56-58 record them applied | D:9, D:209; L RCD56 | NOTE |
| A7 | Item 1 (index queue under a lock): OK | D:41; index_queue.h:1-5,24 | OK |
| A8 | Item 2 (one return arrow, wait/clear/load): OK | D:45; record_writer.h:134,157-158 | OK |
| A9 | Item 3 (NOT_CREATED, counts nowhere): OK | D:49; recorder_internal.h:22-23; record_field.h:70-72 | OK |
| A10 | Item 4 (C buffer 16 KiB, twice the bound, cut, counted; Python no buffer): OK | D:57; record_writer.h:34-43,57,118; recorder.h:91-92 | OK |
| A11 | Item 5 (drain until empty or deadline; die, health, flush; deadline = Destroy timeout / Die 5 s): OK apart from A2 | D:65; record_writer.h:159-176; runtime.h:32 | OK |
| A12 | Item 6 (BufferPool, m_freeList, m_workQueue, m_buffers, m_framePool, m_maskPool, OldestFilledAt under the queue lock, m_lastProgressAt one writer, no shared stall field; 8 and 24 buffers): OK | D:73-81; buffer_pool.h:1-12,27-31,68-73,94-99,109-114; record_writer.h:90-93,110,128-131 | OK |
| A13 | Item 7 (own drop record, writer sums each pass): OK | D:94; recording_thread.h:54-85; record_writer.h:154-155 | OK |
| A14 | Item 8 (16 entries, queues at Create, claim = index, 17th dies, Create false on allocation failure): OK; 16 x (128 KiB slots + 1 MiB bytes) matches "about 1 MiB" | D:100; recording_thread.h:3-6,29-33; recorder_internal.h:53-57; recorder.h:33-43 | OK |
| A15 | Item 9 (STOPPING by one function, CAS / Python lock; STOPPED returns at once): OK | D:106-119; recorder_internal.h:24-28; recorder.h:63 | OK |
| A16 | Item 11 (failed append ends the pass for every queue; record stays at front; failed_writes counts attempts; thread line and frame buffer only after append): OK | D:133-151; record_writer.h:61-66,136-148; recorder.h:88-90; buffer_pool.h:84-92 | OK |
| A17 | Item 12 (three counts, two times, one mutex, two operations): OK | D:155-160; recording_thread.h:54-85 | OK |
| A18 | Item 13 (status out, destination unchanged on false; FIELD_INVALID gone): OK apart from A4 | D:166; record_field.h:81-95 | OK |
| A19 | Item 14 (session path, info JSON limits; folder 64, name 32; 8 KiB cut; from config/ in Python): OK | D:176; recorder.h:25-31,40-41; record_frame.h:10-13 | OK |
| A20 | Item 15 (Create once, second false; Destroy false past timeout, stores nothing, daemon writer): OK | D:184-186; recorder.h:33,51-56; record_writer.h:27,173-176 | OK |
| A21 | Item 16 (is-set before set; the C function): OK | D:190; runtime_internal.h:85; recording_thread.h:146-149 | OK |
| A22 | T1 (fault line at the end of each pass, time, cause, value; never a record call): OK | D:194; record_file.h:35,95-100; record_writer.h:5-7,154-156 | OK |
| A23 | T2 / item 11 "What goes" (retry queue, RetryLine): no trace in any header | D:149,198; grep of all 16 headers | OK |

## B. Decision document vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | Item 13: the helper stops, no record call. md says "a maker's bad value gives INVALID_ARG, counted", and test 5 says "the helper stops, and the record call returns INVALID_ARG, counted" | D:168; md:208; md:330 | MINOR |
| B2 | Item 8: Python is "bounded, not static", a deque grows by one tuple per record. md gate item 1: "no allocation at all" | D:102; md:206 | MINOR |
| B3 | Item 4: "In Python there is no buffer". md lists "the line buffer" among what Create allocates, with no "C only" | D:53; md:311 | MINOR |
| B4 | Item 14: the Create bounds (session path, process name, info JSON) and the explicit Python check are stated nowhere in md; the Create failures listed omit them | D:176; md:42-43, md:280 | NOTE |
| B5 | Items 5 and 10: a Die during a Destroy waits for the drain; no die line, the hand-over log has the reason. md says only "one winner" | D:63, D:127; md:262 | NOTE |
| B6 | No test row pins item 5 (drain to empty), item 6 (stall from BufferPoolOldestFilledAt), item 4 (the C cut line counted), item 14 (a too-long path or info JSON), T1 (the fault line) | md:324-349 | NOTE |
| B7 | Items 1, 2, 3, 6, 7, 9, 11, 12, 15, 16, T1 match md's current state | md:20-25, 129, 136-139, 241, 244-245, 251, 256-262, 268-269, 338, 347 | OK |

## C. Headers vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | md: "no per-buffer state: an index is on the free list, on the work queue, or held"; "no per-buffer state exists". The header has a per-buffer flag mb_pngWritten | md:127, md:309; buffer_pool.h:46-47,56 | MINOR |
| C2 | Every function, type, constant and number md names exists in a header with that name and value (16,384; 8 and 24; 100 lines; 5 s; 16 KiB; 8 KiB; 31 fields; 15 stages; ten health values; 40 and 5 minutes; 256 bytes a queue; 44 MB at 720p) | md:7-27, 206-262, 411-434 | OK |
| C3 | index_queue.h's operations (IndexQueueCreate/Push/Pop/Front/Lock/Unlock, INDEX_NONE) are not described; md has only "a bounded FIFO of indexes under one lock" | index_queue.h:31-43; md:7, md:244 | NOTE |
| C4 | kRecorderSessionDirBytes 192, kRecorderProcessNameBytes 31, kRecorderInfoJsonBytes 8192 not described (= B4) | recorder.h:27-31 | (= B4) |
| C5 | SpscProducerRecordsQueued, SpscProducerRecordsDropped and the queue's m_dropped not described | spsc_record_queue.h:53-55,112 | NOTE |
| C6 | kRingBytesPerRecordExpected 64 (the C byte area per slot) not described | spsc_record_queue.h:73-76,94 | NOTE |
| C7 | the kind byte QUEUED_SPAN / QUEUED_EVENT not described | recording_thread.h:37-41 | NOTE |
| C8 | DieReasonText, 256 bytes, the die reason's bound, not described | record_writer.h:55,109 | NOTE |
| C9 | kWriterExpectedVisionPassesPerMinute 30, the reserve's rate, not described; md gives the measured 4 to 32 passes a minute only | record_writer.h:44; recorder_internal.h:70-72; md:201 | NOTE |
| C10 | Drawing 6's list of what the writer stores omits truncated lines and last-write-failed | md:25; recorder_internal.h:46-48 | NOTE |
| C11 | "The actors by prefix: Producer, BufferPool, Writer, RecordFile" omits DropRecord and IndexQueue | md:27; recording_thread.h:83-85; index_queue.h:32-43 | NOTE |

## D. recorder.md internal consistency

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | "T1" defined as "RCD19's util headers", but used for the fault line ruling | md:411 vs md:137, md:197 | MINOR |
| D2 | Test 10 expects "the thread line, the drop line, the die line, the time reference line, the health line, in that order". The last pass writes the fault lines between the die line and the time reference, and the test's drop changes dropped_spans, so a fault line appears | md:335 vs md:24; record_writer.h:166-168 | MINOR |
| D3 | HISTORY rows state forms later removed without naming the superseding ruling: D4 "a failed ring Init is tried once", D7 "two atomics the writer stores at each pass end", D8 "Die unconditionally, so Die wins (D8 as built)", D12 "Create resets every thread's announced flag". Only the blanket preamble at md:146-149 covers them | md:163-167 | NOTE |

## E. Headers internal consistency

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | Race in the stop request. The compare-and-swap to STOPPING is visible before m_stopDeadline and m_dieReason are stored. A writer on a timer wake loads STOPPING at step 1, enters the last pass, and loads a deadline not yet stored (zero): the drain is cut at once, everything is counted dropped, and the reason is read with no release/acquire pair covering it. The same gap exists in Python (state set under the lock, the deadline after it) | recorder.h:59-60; record_writer.h:83-87,134,159-161; recorder_internal.h:24-27 | BLOCKING |
| E2 | One header, two rules for a Die during a Destroy: "returns at once" against "waits for the Destroy's drain" (= A2) | record_writer.h:87-88 vs :171-173 | (= A2) |
| E3 | record_file.h's last-pass order "the die line ...; then the time reference and the health line; then the flush" omits step 9's fault lines, which record_writer.h puts between them | record_file.h:21-23 vs record_writer.h:166-168 | MINOR |
| E4 | "A buffer in neither queue belongs to the one thread that holds it, so no state per buffer exists" against the per-buffer mb_pngWritten in the same header | buffer_pool.h:5-6 vs :46-47,56 | MINOR |
| E5 | Two homes for one drop count: the SPSC queue counts a drop itself (m_dropped, SpscProducerRecordsDropped); the drop record "nothing else touches" also counts it; recorder.h says every thread counts in its own drop record | spsc_record_queue.h:46,55,101-102,112; recording_thread.h:54-56,130; recorder.h:80 | MINOR |
| E6 | Maker false: counted (record_field.h) vs not counted (recorder.h) (= A4) | record_field.h:66-72 vs recorder.h:79-80 | (= A4) |
| E7 | "NaN where an int is expected" makes FieldInt false, but FieldInt takes an int64_t, which cannot hold NaN | record_field.h:83 vs :92 | MINOR |
| E8 | The writer is "woken ... by a filled buffer", but no header says who sets m_wake on an enqueue: BufferPoolEnqueueFilled only stamps and enqueues, RecordFrame's comment is silent, and a BufferPool has no path to the Writer | record_writer.h:4-5,96; buffer_pool.h:81-82; record_frame.h:20-28 | MINOR |
| E9 | A failed append "ends the pass". Whether steps 7 to 9 still run (the drop sums into the health, m_lastProgressAt, the fault lines) is not stated. If they are skipped, under a dead disk the producers' drops never reach the health, against D:7 "the health and the chat line show it" | record_writer.h:139-140,146-147,154-156 | MINOR |
| E10 | The last pass runs "step 8 unconditionally (the time reference and the health line); one more flush"; step 8 already ends with the flush to disk. One flush or two is unclear | record_writer.h:152-153 vs :167-168 | NOTE |
| E11 | The last pass repeats steps 2 to 6 "again and again" until empty or the deadline. Under a failing append it re-tries with no wait until the deadline; unstated | record_writer.h:159-161 | NOTE |
| E12 | The field block lists m_droppedSpansReported and m_droppedEventsReported; m_droppedFramesReported is undocumented | recording_thread.h:94-97 vs :107 | NOTE |
| E13 | OsEvent and OsLock have no create or destroy, and OsThread no start or join, in runtime_internal.h, yet IndexQueue, DropRecord and Writer hold pointers to them and Destroy joins. OsLock is typedef'd twice (legal C11) | runtime_internal.h:76-92; index_queue.h:24; recording_thread.h:64; record_writer.h:105-107 | NOTE |
| E14 | The PNG path (RECORD_FRAME_PATH_FORMAT) reaches 192+1+63+1+31+4+1 = 293 bytes; PathText is 256; no header names the buffer that holds it, so no stated bound covers it (item 14) | record_file.h:16; recorder.h:28; record_frame.h:11-12; common_names.h:10 | NOTE |
| E15 | DieReasonText is 256 bytes; what happens to a longer reason (cut or refused) is unstated | record_writer.h:55,109; recorder.h:64 | NOTE |
| E16 | "release its frame buffer slot" uses the two words item 6 removed from the pool; here they name the shared frame buffer of module 04, and "slot" in spsc_record_queue.h is the SPSC ring's. Not the removed mechanism | record_frame.h:23; spsc_record_queue.h:70-107; D:75 | NOTE |
| E17 | Leftover-name sweep: no retry queue, RetryLine, ready queue, FramePool, FIELD_INVALID, lazy allocation, second Create, abandoned writer or shared stall field in any header; "retry" once, meaning the next pass's re-append | buffer_pool.h:47 | OK |
| E18 | Compile: all ten 01-recorder headers clean under the given gcc line. fixed_text.h compiled alone warns "ISO C forbids an empty translation unit" (macro-only; outside the given command) | 00-util/fixed_text.h:12 | OK |
