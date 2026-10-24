# Recorder consistency, round 7, checker 2 (2026-10-22)

**Verdict: NOT CONSISTENT. 0 BLOCKING, 15 MINOR, 18 NOTE.**

The sources: `D` = test/recorder-decisions-2026-10-21.md; `md` = modules/01-recorder/recorder.md; header paths are relative to modules/. Every path below is under docs/api-harden2/rev5/.

Facts I checked first:
- gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on all ten 01-recorder headers: zero diagnostics, no FAIL.
- The aggregate (recorder_aggregate_for_review.md) holds all sixteen headers verbatim. A script compared every code block.
- sizeof, measured with gcc on this machine: SpscRecordQueue 192, RecordSlot 8, RecordingThread 384, struct Recorder 7360, PoolBuffer 128, Writer 432.

## A. The decision document against the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A-1 | Item 1 "deque under its own Lock", two queues: matches `IndexQueue.m_lock` and the two IndexQueues of BufferPool | D:41; 00-util/index_queue.h:1-5,23-29; 01-recorder/buffer_pool.h:62-75 | OK |
| A-2 | Item 2 "wakes ... resets it, and does one pass", one return arrow: matches "wait on m_wake ...; clear it" and "Then back to step 1, always" | D:45; record_writer.h:136,159 | OK |
| A-3 | Item 3 "returns RECORD_NOT_CREATED and nothing else": matches | D:49; record_field.h:69-71; recorder_internal.h:22-23 | OK |
| A-4 | Item 4 "16 KiB, twice the record bound ... the writer counts it": matches kWriterLineBytes 16384, the static assert and m_truncatedLines | D:57; record_writer.h:34-43,57; recorder.h:91-92 | OK |
| A-5 | Item 5: the last pass drains steps 2 to 6 to empty or to the deadline; Destroy's deadline is now plus its timeout; a Die during a Destroy waits: matches. The claim "The only hole ... counted, but after the last health line" does not hold: see E-3 | D:65-67; record_writer.h:163-181; recorder.h:58-64 | see E-3 |
| A-6 | Item 6: the names BufferPool, m_freeList, m_workQueue, m_buffers, the six operations, m_framePool, m_maskPool, 8 and 24 buffers, mb_pngWritten, OldestFilledAt under the work queue's lock, m_lastProgressAt one atomic with one writer: all present | D:73-81; buffer_pool.h:29-33,53-116; record_writer.h:92-95,112,130-133 | OK |
| A-7 | Item 7: every thread counts its own dropped frames, and the writer sums them: matches | D:94; recorder.h:83-87; recording_thread.h:43-48 | OK |
| A-8 | Item 8 "Create returns false, and the app dies at start, with the reason". Create returns a bare bool over eight causes, so the reason is not available to the caller. md's die text names only two causes | D:100; recorder.h:33-49; md:43 | MINOR |
| A-9 | Item 8, the rest: the table of 16 entries at Create, a claim by index, the 17th claim dies, the 16,384 bound: matches | D:100-102; recording_thread.h:1-8,29-33; recorder_internal.h:54-58 | OK |
| A-10 | Item 9 "Both go through one internal function under the state lock". No such function is declared; the procedure is prose only | D:106; record_writer.h:83-91; recorder_internal.h (no declaration) | NOTE |
| A-11 | Item 9's Python `_request_stop` stores only STOPPING. Item 10 stores the reason and the deadline first. The headers follow item 10. This is a drift inside D | D:110-117 vs D:125; record_writer.h:83-91 | NOTE |
| A-12 | Item 10, the stop request under the state lock, in both builds; the reason, then the deadline, then STOPPING with release; the writer loads with acquire; a second request stores nothing: matches | D:125; record_writer.h:83-91; recorder_internal.h:24-29; recorder.h:58-63 | OK |
| A-13 | Item 11: a failed append ends the pass for every queue, the record stays at the front, the drop sums still run, no RetryLine, failed_writes counts attempts: matches | D:133-151; record_writer.h:140-142,159-162; recorder.h:88-90 | OK |
| A-14 | Item 12 "Two operations exist on it, and only they touch it ... No other code reads or writes those five values". The writer also writes the cut-off counts into the drop records, "the writer holds each record's lock for that". No operation is named for this, and DropRecordNote is documented as "the producer, on a drop" | D:155-160; recording_thread.h:54-56,81-83; record_writer.h:169-170 | MINOR |
| A-15 | Item 12 names `note_drop` and `take_drop_gap`; the header names DropRecordNote and DropRecordTake; md names neither | D:157-158; recording_thread.h:83,85 | NOTE |
| A-16 | Item 13, `bool FieldInt(RecordField* out, FieldName name, int64_t value)`, false leaves out unchanged, no FIELD_INVALID: matches word for word | D:166-170; record_field.h:80-94 | OK |
| A-17 | Item 14 "Not checking a length is a failure ... the same in both builds". Two caller strings are copied into fixed buffers with no stated bound or check: the thread name (ThreadName, 32) and the die reason (DieReasonText, 256; "one string" in Python) | D:174-176; recorder.h:66-69, 58-64; common_names.h:12; record_writer.h:55,90-91 | MINOR |
| A-18 | Item 14, the session path (192), the process name (31), the info JSON (8192), the folder (64) and the name (32): present and checked | D:176; recorder.h:25-31,39-43; record_frame.h:10-19 | OK |
| A-19 | Item 15: one Create, a second returns false; Destroy past its timeout returns false and stores nothing; the writer is a daemon thread: matches | D:184-186; recorder.h:33,51-56; record_writer.h:178-181; recorder_internal.h:28-29 | OK |
| A-20 | Item 16, is-set before set: matches OsEventIsSet and ProducerWakeWriterIfHalfFull | D:190; 03-runtime/runtime_internal.h:85; recording_thread.h:146-149 | OK |
| A-21 | T1, the fault line with at, what and count at the end of each pass: matches | D:194; record_file.h:96-101; record_writer.h:156-158 | OK |
| A-22 | T2, the retry queue gone: no RetryLine and no retry queue in any header | D:198; grep over 00-util/*.h and 01-recorder/*.h | OK |
| A-23 | D defines a pass as "walk every queue and the pool once" (singular). Item 6 and the headers have two pools | D:33,145 vs D:75; record_writer.h:2-3 | NOTE |

## B. The decision document against recorder.md (current-state statements)

| # | what | where (file:line) | severity |
|---|---|---|---|
| B-1 | The section 4 heading says "every item of the decision document closed on 2026-10-22". D's status line marks 4, 6, 8, 10, 12, 13, 14 and 15 as DECIDED, not CLOSED | md:94 vs D:9,11,209 | MINOR |
| B-2 | md credits Create with checking "a frame's folder 64 and name 32, a record 8 KiB". D says RecordFrame checks the folder and the name, and the cut enforces the record bound | md:210 vs D:176 | MINOR |
| B-3 | Drawing 5 lists Destroy as "STOPPING, a deadline". Item 10 stores the deadline before STOPPING | md:24 vs D:125 | MINOR |
| B-4 | The failure matrix says "the next pass, 5 s later, retries". D says "at most 5 s later", and a frame or a watermark wakes the writer sooner | md:267 vs D:33,145 | MINOR |
| B-5 | md says "the queues and the pools are empty at STOPPED". D item 5 and the header name a hole: a record pushed between the final empty check and the STOPPED store. md never mentions that hole | md:121 vs D:67; record_writer.h:174-176 | MINOR |
| B-6 | Items 1, 2, 3, 6, 7, 9, 10, 11, 12, 13, 15, 16 and T1 match md | md:21-25,129,134,136-139,205,207,240,243-244,250,260-261,268,337,346 | OK |

## C. The headers against recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| C-1 | md puts "head, tail and the drop count" each on its own cache line, at "256 bytes a queue, 4 KiB for 16". The header has no drop count (RCD59 removed it). The measured sizeof(SpscRecordQueue) is 192, so 16 queues take 3 KiB | md:214,307 vs spsc_record_queue.h:101-109 | MINOR |
| C-2 | Every function, type, constant and number named in md exists with that name and value. The checked names and values: 16, 16,384, 8 KiB, 31, 8 and 24, 5 s, 100 lines, 16 KiB, 192, 31, 8192, 64, 32, 40 and 5 minutes, 15 stages, 10 line kinds, 10 health keys, the sample keys, DieActionFn, RecordLlamaRequest, RecordVideoRow | md:20-27,62,210,214,220-229,418-433; 05-llama_server/llama_server.h:184; 12-frame_source/frame_source_internal.h:123; 03-runtime/runtime.h:18 | OK |
| C-3 | DropRecord, DropRecordNote, DropRecordTake, DropGap and DropKind are not named in md; md says only "drop record" | recording_thread.h:43-85; md:205,244,260 | NOTE |
| C-4 | The locking contract of IndexQueueLock, IndexQueueUnlock and IndexQueueFront (the caller holds the lock) is not described | index_queue.h:37-44; md:7,268 | NOTE |
| C-5 | ProducerPushEvent, QUEUED_SPAN and QUEUED_EVENT are not named or described in md (drawing 1 names ProducerPushSpan only) | recording_thread.h:38-41,139-145; md:20 | NOTE |
| C-6 | RecordFileCreate, RecordFileWriteHeader and RecordFileClose are not named in md | record_writer.h:73-79; md:21,33 | NOTE |
| C-7 | BufferPools, BufferPoolsCreate/Destroy and mb_present are not described. Neither is the rule that only a Destroy that joined the writer frees the pools | buffer_pool.h:11-14,103-119; md:24,313-314 | NOTE |
| C-8 | The C byte area's size (kRingBytesPerRecordExpected, 64 bytes a record, about 1 MiB a queue) is not described | spsc_record_queue.h:72-75,90-96; md:7,307 | NOTE |
| C-9 | md's "actors by prefix: Producer, BufferPool, Writer, RecordFile" omits DropRecord, IndexQueue and Spsc | md:27; recording_thread.h:83-85 | NOTE |

## D. recorder.md, internal consistency

| # | what | where (file:line) | severity |
|---|---|---|---|
| D-1 | Section 8 says the first record claims its entry "by an atomic add". The Python mapping says "in Python under the state Lock ... in C by an atomic add" | md:310 vs md:239 (header: recorder_internal.h:56-58) | MINOR |

## E. The headers, internal consistency

| # | what | where (file:line) | severity |
|---|---|---|---|
| E-1 | The last pass meets a failed append. The header says a failed append ends the pass and "the pass skips every further append", but the last pass repeats steps 2 to 6 "until ... empty, or the clock passes that deadline", then writes "step 8 unconditionally". With a dead disk this is a loop with no wait until the deadline, and it is undefined whether the die line, the fault lines and the health line are attempted | record_writer.h:140-142,159-162,163-174 | MINOR |
| E-2 | Cut-off frames are "counted by kind into the entries' drop records", but a PoolBuffer carries no producing entry, so the writer cannot pick the entry | record_writer.h:169-170; buffer_pool.h:53-60; recorder.h:85 | MINOR |
| E-3 | "The one hole ... is dropped and counted after the last health line; the window is microseconds" is understated, for two reasons. (a) A producer that loaded RUNNING and then pushed after the final empty check leaves a record nobody writes or counts. A Python thread can be switched out for 5 ms between the load and the append (D:17). (b) A call made in STOPPED, or after the final sums, is counted only into a drop record that no one ever sums. One example is a recording thread during Die's children step | record_writer.h:174-176; recorder_internal.h:22-24; recorder.h:76-82; D:67 | MINOR |
| E-4 | "So a producer and the consumer never wait for each other" is false. TakeFree (producer) and ReturnFree (consumer) share the free list's lock. EnqueueFilled (producer) and Peek, Dequeue and OldestFilledAt share the work queue's lock | buffer_pool.h:62-65 vs buffer_pool.h:82-101 | MINOR |
| E-5 | "Full means the new record is dropped and counted" and "false: full; the record is dropped and counted": the queue holds no counter. The count lives in the caller's DropRecord | spsc_record_queue.h:2-3,46,101-109; recording_thread.h:130 | MINOR |
| E-6 | The runtime declares no OsThread create or join, and no OsEvent or OsLock create. Destroy joins the writer, and Create allocates the locks and the events | record_writer.h:179; recorder_internal.h:61; 03-runtime/runtime_internal.h:76-92 | NOTE |
| E-7 | `typedef struct OsLock OsLock;` appears twice in one header (valid in C11) | 03-runtime/runtime_internal.h:87,92 | NOTE |
| E-8 | Destroy's return value is not stated for the STOPPED and NOT_CREATED states | record_writer.h:89-90; recorder.h:51-56 | NOTE |
| E-9 | It is not stated whether Destroy frees the entries, the queues and the drop-record locks. A call in STOPPED still runs DropRecordNote on its entry. Only the pools' free rule is stated | recorder_internal.h:23-24; buffer_pool.h:12-14 | NOTE |
| E-10 | m_droppedFramesReported is missing from the field-doc block that documents its two siblings | recording_thread.h:96-97 vs :107 | NOTE |
| E-11 | Step 7's reserve in a process without pools: RecorderReserveBytes needs a FrameSize, and none exists there | record_writer.h:151-153; recorder_internal.h:74; recorder.h:42-43 | NOTE |
| E-12 | 00-util/fixed_text.h compiled alone gives "-Wpedantic: ISO C forbids an empty translation unit" (a macro-only header). The ten 01-recorder headers are clean | 00-util/fixed_text.h:12 | NOTE |
| E-13 | Leftover names of removed mechanisms: none. No FramePool, ready queue, retry queue, RetryLine, FIELD_INVALID, compare-and-swap on the state, lazy allocation, second Create, abandoned writer or shared stall field. "slot" and "publish" (the live C ring), "claim" (the entry claim) and "slot" (the frame buffer's, RVW3) name live mechanisms | spsc_record_queue.h:69-96; recording_thread.h:5-6,91; record_frame.h:24 | OK |
| E-14 | The includes all exist, and every used type is defined (gcc clean) | all 01-recorder/*.h | OK |
