# Recorder consistency check, round 5, reader 3 (2026-10-22)

**Verdict: NOT CONSISTENT. 51 distinct findings: 8 BLOCKING, 20 MINOR, 23 NOTE.** A row marked "= Xn" repeats the cause of row Xn and is not counted again. Rows marked OK are checks that passed and are not counted.

Sources: `test/recorder-decisions-2026-10-21.md` (dec), the 16 headers (`00-util/*.h`, `01-recorder/*.h`), `01-recorder/recorder.md` (md), and the ledger rows RCD52 to RCD56. The aggregate holds all 16 headers byte-identical to the files (checked by script). gcc `-fsyntax-only -Wall -Wextra -pedantic -std=c11`: 10 of 10 recorder headers pass, with no warnings.

## A. Decision document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | item 1, the lock on the index queue: OK | index_queue.h:4-5,24 | OK |
| A2 | item 2, one return arrow ("Then back to step 1, always"): OK | record_writer.h:153-154 | OK |
| A3 | item 3, RECORD_NOT_CREATED with no count: OK | record_field.h:71-72,78; recorder_internal.h:22-23 | OK |
| A4 | item 4, the C buffer of 16 KiB, cut and counted: OK | record_writer.h:34-42,56,113-116; recorder.h:88-89 | OK |
| A5 | item 5, drain everything, then the die line: record_writer.h does this. record_file.h still gives the old order: "the die line ... then the time reference and the health line; then the remaining frame lines until the deadline" | dec:65; record_writer.h:155-161 vs record_file.h:20-23 | BLOCKING |
| A6 | item 5, the drop window. Dec: "After the recorder's drain, a thread may still record. Those records are dropped". Headers: every record is dropped from STOPPING on, before the drain starts | dec:67 vs record_field.h:66-67; record_span.h:38-39; recorder_internal.h:23-24 | MINOR |
| A7 | item 6, the names (BufferPool, m_freeList, m_workQueue, m_buffers, the five operations, m_framePool, m_maskPool, the scheme as the first comment): OK | buffer_pool.h:1-10,63-68,75-88,98-103 | OK |
| A8 | item 6, "slot ... gone": the pool's IndexQueue still says "slot indexes", SlotIndex, SlotCount, SLOT_NONE | dec:75 vs index_queue.h:1,12-15,25-38 | MINOR |
| A9 | item 6, "calls that function on each pool and nothing else. No field is shared". The headers also share the writer's atomic m_lastProgressAt with the main thread, through WriterIsStalled | dec:81 vs record_writer.h:88-91,108,126-129; recorder.h:92-94 | BLOCKING |
| A10 | item 6, the stall reference. Dec: "5 s past the writer's last finished buffer". Header: m_lastProgressAt is also stored "at the end of each pass" | dec:77 vs record_writer.h:88-89,144,150 | MINOR |
| A11 | item 7 says "a plain `+= 1`"; item 12 says the same counts sit under a mutex. The headers follow item 12. The decision document contradicts itself | dec:94 vs dec:155-157; recording_thread.h:47-49,74-76 | MINOR |
| A12 | item 8, everything allocated at Create, a claim is an index, the 17th claim dies: OK | recorder.h:32-33,41; recorder_internal.h:53-57; recording_thread.h:3-6 | OK |
| A13 | item 9, one guarded transition to STOPPING, the writer reads the state each pass: OK | recorder_internal.h:24-28; record_writer.h:132 | OK |
| A14 | item 10, the reason first, then the stop: OK. The release/acquire pair, though, is on m_stopDeadline. Dec puts it on "the stop request" | dec:125 vs record_writer.h:84-87; recorder_internal.h:25 (a CAS on the state) | MINOR |
| A15 | item 11, a failed append ends the pass and the record stays at the front, with no retry queue: OK | record_writer.h:60-65,136-138; record_file.h:23-24; recorder.h:85-87,95-96 | OK |
| A16 | item 11, the writer's own lines (thread line written only after its append; buffer returned only after the frame line): OK | record_writer.h:134-135,142-143 | OK |
| A17 | item 12, the shape of the drop record. Dec: "the count of drops ... copies the three values". Header: three counts and two times, "copy the five values" | dec:155,158 vs recording_thread.h:58-62,77 | MINOR |
| A18 | item 13, a maker returns bool with an out parameter; FIELD_INVALID absent (grep): OK | record_field.h:81-95 | OK |
| A19 | item 14, the explicit bounds (path, info JSON, 64/32, 8 KiB): OK | recorder.h:25-30,39-40; record_frame.h:10-13; record_field.h:26 | OK |
| A20 | item 15, one Create; Destroy returns false and stores nothing; a daemon thread: OK | recorder.h:32,50-52; record_writer.h:163-165; recorder_internal.h:27-28 | OK |
| A21 | item 16, the is-set check before the set: OK | recording_thread.h:137-139; record_writer.h:25-26; runtime_internal.h:85 | OK |
| A22 | T1, the fault line: OK | record_file.h:34,41,94-99; record_writer.h:150-152 | OK |
| A23 | T2, gone: no RetryLine and no retry queue in any header (grep): OK | all 16 headers | OK |
| A24 | the decision document contradicts itself: item 10's heading says "PROPOSED"; the status block says "DECIDED ... 10" | dec:121 vs dec:9 | MINOR |
| A25 | the decision document still uses the old names in item 1 ("two index queues, free and ready"), which item 6 retires | dec:41 vs dec:75 | NOTE |

## B. Decision document vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | item 3 is CLOSED, but md still reads "P1 to P4 open" and "OPEN P4" in current-state cells | dec:11,47 vs md:94,136,250 | MINOR |
| B2 | T1 is CLOSED with a fault line. md still says "no event: the writer never records; the health line ... carry the fault", "OPEN P2" | dec:194 vs md:137,197 | BLOCKING |
| B3 | item 8 (everything at Create) vs md: "the thread's entry and queue are made at its first record" | dec:100 vs md:206 | BLOCKING |
| B4 | item 8 (the Python entries exist from Create) vs md's Python mapping: "the thread table: a list, appended last" | dec:102 vs md:239 | BLOCKING |
| B5 | item 8 vs md's TOCTOU row: "the table entry is an atomic pointer, stored last with release, NULL until then" | dec:100 vs md:255 | BLOCKING |
| B6 | item 12 (a mutex) vs md's TOCTOU row: "the producer stores first, last, then the count with release; the writer loads the count with acquire" | dec:155-160 vs md:260 | BLOCKING |
| B7 | item 15 (Destroy stores nothing; one Create) vs md: "STOPPED has two [writers], the writer ... or Destroy past its deadline, and Create then needs a joined writer" | dec:184-186 vs md:261 | BLOCKING |
| B8 | item 15: a second Create returns false before any open. md still credits O_EXCL with guarding "a re-Create by the same process", and test 21 expects that path | dec:186 vs md:276,345 | MINOR |
| B9 | item 5 (all frames drained before the die line) vs drawing 5's row: "the die line if a reason is set, frames until the deadline" | dec:65 vs md:24 | MINOR |
| B10 | item 5 (after the drain, a record is dropped and counted, and the count is not in the file) vs md: such a record "is added to the dropped counts by the writer after its last pass". The writer does nothing after its last pass | dec:67 vs md:250 | MINOR |
| B11 | = A9: md also uses the writer's last progress in the stall rule | md:134,268 | = A9 |
| B12 | item 6, "slot" gone, vs md: "two slot pools", "a pool slot", "a pool has 8 slots", "slot indexes" | dec:75 vs md:7,189,291,309 | MINOR |
| B13 | item 6, "publish" gone, vs md: "a published frame" | dec:75 vs md:130 | MINOR |
| B14 | item 12 (a drop takes the mutex) vs md: "No lock on the span and event path" | dec:157 vs md:206 | NOTE |
| B15 | item 10 (the reason first, the stop second, release/acquire) is not stated anywhere in md | dec:125; md (grep: absent) | NOTE |
| B16 | item 14 (the path and info JSON bounds, checked in both builds) is not stated anywhere in md | dec:176; md (grep: absent) | NOTE |
| B17 | item 15 (Destroy past its timeout returns false; the daemon thread) is not stated in md; drawing 5 shows only "wait ... join" | dec:184 vs md:24 | NOTE |
| B18 | items 1, 2, 4, 9, 11 and 16 match md: OK | md:138,139,21,215,24,120,129,208,267,337,240 | OK |

## C. Headers vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | md says the health has "nine values"; RecorderHealth has ten fields (truncated lines added) | md:62 vs recorder.h:100-111 | MINOR |
| C2 | md's health line example has no "truncated_lines" key | md:228 vs record_file.h:115 | MINOR |
| C3 | md's contract lines have no fault line example | md:220-229 vs record_file.h:34,94-99 | NOTE |
| C4 | every code name in md's drawing table exists in a header, and every number checked matches: 16, 8/24, 100 lines, 5 s, 16 KiB, 8 KiB, 31 fields, 15 stages, 16,384, 40/5 minutes, 256 B per queue: OK | md:20-25,133,215,307,425,431 | OK |
| C5 | not described in md: DropRecord, DropGap, DropRecordNote, DropRecordTake | recording_thread.h:56-78 | NOTE |
| C6 | not described in md: kRecorderSessionDirBytes (192), kRecorderInfoJsonBytes (8192) | recorder.h:27-30 | NOTE |
| C7 | not named in md: kWriterLineBytes, LineText, m_truncatedLines (only "16 KiB" appears) | record_writer.h:42,53; recorder.h:88-89 | NOTE |
| C8 | not described in md: the Writer members m_stopDeadline, m_dieReason, m_lastProgressAt, m_queueEnds, m_line | record_writer.h:102-111 | NOTE |
| C9 | not named in md: FieldInt/Float/Bool/Text, FIELD_NAME_CUT, kRecordMaxCallerFields | record_field.h:24,31,92-95 | NOTE |
| C10 | not named in md: the IndexQueue operations, SLOT_NONE, the Spsc* operations, RecordSlot, kRingBytesPerRecordExpected | index_queue.h:15,32-38; spsc_record_queue.h:37-66,75,84-89 | NOTE |
| C11 | not named in md: BufferPoolCreate, BufferPoolsCreate, BufferPools, PoolBuffer, FolderName, FrameName, kBufferPool* | buffer_pool.h:25-34,47-53,71,98-106 | NOTE |
| C12 | not named in md: RecordFileCreate, RecordFileWriteHeader, RecordFileClose | record_writer.h:72-78 | NOTE |
| C13 | not named in md: RecorderState, m_claimedCount, mb_claimed, mb_announced, ProducerPushEvent, kRecordQueueWatermark, QUEUED_SPAN/EVENT, OsEventIsSet | recorder_internal.h:29-34,64; recording_thread.h:32,38-41,96,99,130 | NOTE |
| C14 | RecorderNameThisThread is described only in a section-4 history row, not in sections 2, 3, 7 or 11 | md:176 vs recorder.h:64-67 | NOTE |
| C15 | drawing 6's structure: "atomic counters and flags, one per cause, no lock". The drop counts in each entry sit under a mutex | md:25 vs recording_thread.h:47-63 | NOTE |
| C16 | = B3, B5: md's lazy entry and atomic-pointer table vs the preallocated table, m_claimedCount and mb_claimed | md:206,255 vs recording_thread.h:3-6,84-85; recorder_internal.h:55-57 | = B3/B5 |
| C17 | = B6: md's atomic drop gap vs DropRecord under m_lock | md:260 vs recording_thread.h:56-78 | = B6 |
| C18 | = B9: drawing 5's last-pass order vs WriterRun | md:24 vs record_writer.h:155-161 | = B9 |

## D. recorder.md, internal

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | the entry made "at its first record" vs "Everything is allocated at Create ... claims the next entry by an atomic add" | md:206 vs md:310 | = B3 |
| D2 | "a list, appended last" and "an atomic pointer ... NULL until then" vs the allocation at Create | md:239,255 vs md:310 | = B4/B5 |
| D3 | no fault event, "OPEN P2", vs "a fault line is written when a counter changes (TEL2)" | md:137,197 vs md:466 | = B2 |
| D4 | NOT_CREATED marked "OPEN P4" vs stated as settled ("a record before Create is a no-op (NOT_CREATED)"); the heading says "P1 to P4 open", yet the P1 and P3 rows are closed | md:94,136,250 vs md:138,139,420 | = B1 |
| D5 | "slot pools", "pool slot", "8 slots" vs "buffer pool ... 8 frame buffers" | md:189,291,309 vs md:23,308 | = B12 |
| D6 | "a published frame" vs "a filled buffer" for the same wake | md:130 vs md:22 | = B13 |
| D7 | Destroy may store STOPPED vs the writer alone ends the last pass and Destroy joins | md:261 vs md:24,120 | = B7 |
| D8 | the same queue span stated as "about seven minutes" and as "over six minutes" (both fit 409 s) | md:267 vs md:272 | NOTE |

## E. Headers, internal

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | = A5: two different last-pass orders (frames before the die line vs frames after the health line) | record_file.h:20-23 vs record_writer.h:155-161 | = A5 |
| E2 | the deadline is loaded "once, at the die-line step", but the drain before that step stops "when the clock passes m_stopDeadline" | record_writer.h:85-87 vs record_writer.h:155-156 | MINOR |
| E3 | DropRecordNote takes a RecordKind, which has only QUEUED_SPAN and QUEUED_EVENT. Yet DropRecord counts frames, and a frame drop is counted in the job thread's drop record | recording_thread.h:38-41,60,76 vs recorder.h:83 | MINOR |
| E4 | a maker returning false: "the record call returns INVALID_ARG, counted in the thread's drop record". But the helper stops before any record call, and no function lets it count | record_field.h:83-84; recorder.h:75-76 | MINOR |
| E5 | "No lock on the span and event path; the one lock the producer ever meets there is the condition variable's", yet a drop on that path takes DropRecord's m_lock | recording_thread.h:116-118 vs recording_thread.h:47-49,74-76 | MINOR |
| E6 | = A8: "slot" names in the pool's index queue | index_queue.h:1,12-15 | = A8 |
| E7 | the last pass lists steps 2 to 6, the die line and step 8, but not step 9 (the sums of the drop records, the fault lines). The deadline-cut counts are added after the last health line | record_writer.h:150-152 vs 155-161 | MINOR |
| E8 | "a value past kRecordingThreadsMax dies": an atomic add from 0 gives the 17th claim the value 16 itself, not one past it | recorder_internal.h:55-57 | NOTE |
| E9 | the drop line has keys for spans and events only; DropRecord also counts frames, which no drop line carries | record_file.h:101-108 vs recording_thread.h:60 | NOTE |
| E10 | step 5 takes each drop record; step 9 sums "every entry's drop record". It is unstated whether step 9 locks again or reuses step 5's copy | record_writer.h:139,150-151 | NOTE |
| E11 | "Returns ... at once when the state is not RUNNING" next to "Die during a Destroy: its deadline replaces Destroy's". These agree only through the unconditional store of the deadline, which is stated in the other header | recorder.h:59-61 vs record_writer.h:83-84 | NOTE |
| E12 | gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11: 10 of 10 pass, no warnings; every include resolves; no type is used undefined; no constant has two values | 01-recorder/*.h | OK |
| E13 | Create fills both endpoints of each queue, but only the consumer ends are kept (m_queueEnds). ThreadProducer.m_producer must be rebuilt at the claim, and no header says so | spsc_record_queue.h:34-36 vs record_writer.h:109; recording_thread.h:110 | NOTE |
| E14 | = A9: a shared stall field, m_lastProgressAt | record_writer.h:108,126-129 | = A9 |
| E15 | the removed mechanisms are absent: no ready queue, retry queue, FramePool, FIELD_INVALID, second Create, lazy allocation or abandoned writer (grep). "slot" stays only in the index queue (A8); in the SPSC ring it is that ring's own term. "claim" means only an entry claim | all 16 headers | OK |
