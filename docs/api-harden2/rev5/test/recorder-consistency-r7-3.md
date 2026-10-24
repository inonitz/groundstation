# Recorder consistency check, round 7, reader 3 (2026-10-22)

**Verdict: NOT CONSISTENT. 25 findings: 2 BLOCKING, 11 MINOR, 12 NOTE.**

Sources: recorder-decisions-2026-10-21.md (D), the 16 headers (verbatim in the aggregate, checked by diff: all 16 identical), runtime_internal.h, recorder.md (MD), the ledger (RCD40..RCD59 read). gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on the 10 recorder headers: 0 failures, 0 warnings.

Paths: H = docs/api-harden2/rev5/modules/01-recorder/, U = .../00-util/, D = docs/api-harden2/rev5/test/recorder-decisions-2026-10-21.md, MD = H/recorder.md.

## A. Decision document vs headers

Items applied as decided (no finding): 1 (U/index_queue.h:1-5), 2 (H/record_writer.h:159-160), 3 (H/record_field.h:69-71, H/recorder_internal.h:22-23), 4 (H/record_writer.h:34-43,57), 6 (H/buffer_pool.h:1-14,70-75,82-101; H/recorder.h:95-97), 7 (H/recorder.h:80-81), 8 (H/recording_thread.h:3-6,29-33; H/recorder_internal.h:54-58), 10 (H/record_writer.h:83-91; H/recorder.h:58-63), 11 (H/record_writer.h:140-142,161-162), 13 (H/record_field.h:80-94), 14 (H/recorder.h:25-31,40-41; H/record_frame.h:10-13), 15 (H/recorder.h:33,51-53), 16 (runtime_internal.h:85; H/recording_thread.h:146-148), T1 (H/record_file.h:96-101; H/record_writer.h:156-158), T2 gone (no retry queue, no RetryLine in any header).

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | D item 12: "Two operations exist on it, and only they touch it ... No other code reads or writes those five values". Header: the writer adds the deadline cut-off "into the entries' drop records (the writer holds each record's lock for that)": a third writer path, not Note (producer) or Take | D:155,160; H/record_writer.h:168-170; H/recording_thread.h:55-56 | MINOR |
| A2 | D item 12: the writer calls take "once per pass per entry". Header: step 5 calls DropRecordTake, step 9 sums every drop record again, and step 9 runs when step 5 is skipped after a failed append, so it must read the record itself: two reads per pass | D:158; H/recording_thread.h:84; H/record_writer.h:143,156-157,161-162 | MINOR |
| A3 | D item 9: "Both go through one internal function under the state lock" (`_request_stop`). No such function is declared in any header; only the behaviour is described | D:106,110-117; H/recorder_internal.h:24-29; H/record_writer.h:83-91 | NOTE |
| A4 | D item 5 and the header: "The only hole is a record pushed between the writer's final empty check and its STOPPED store ... microseconds". Not the only hole: a record call while STOPPING/STOPPED after the final step-9 sum is dropped and counted in its drop record, never written to the file; Die keeps recording threads alive through the 10 s children step | D:67; H/record_writer.h:171-176; runtime Die steps D:67 | MINOR |
| A5 | D item 12: note_drop "stores the two times" on every drop. Header: first time only when newGap | D:157; H/recording_thread.h:81-83 | NOTE |

## B. Decision document vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | MD section 4 heading: "every item of the decision document closed on 2026-10-22". D status: 4, 6, 8, 10, 12, 13, 14, 15 are DECIDED "to be applied"; T3 "your yes stands", not closed | MD:94; D:9,11,206-210 | MINOR |
| B2 | MD: "Create checks its bounds explicitly ...: ... a frame's folder 64 and name 32, a record 8 KiB". D item 14 and the headers: the folder and name are checked by RecordFrame, the record bound by the cut; Create checks only the path, the process name and the info JSON | MD:210; D:176; H/record_frame.h:15-18; H/recorder.h:40-41 | MINOR |
| B3 | D item 15: Destroy returns false past its timeout, state stays STOPPING, the daemon writer ends with the process. MD never states the false return or the daemon thread (only "stores nothing") | D:184; MD:24,120,261 | NOTE |
| B4 | D item 5 names the one hole (a push between the final empty check and STOPPED, counted after the last health line). MD's TOCTOU row says the cut-off is counted before the final health line and omits the hole | D:67; MD:250 | NOTE |
| B5 | MD: "one write per line, about 250 a drain". D item 8: "about 200 records between two passes" | MD:131; D:102 | NOTE |

## C. Headers vs recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | MD: the C queue's "head, tail and the drop count each on their own cache line"; "head, tail and the drop count on their own lines: 256 bytes a queue, 4 KiB for 16". Header: SpscRecordQueue has no drop count; two aligned fields (head, tail) after the read-only fields. RCD59 removed the queue's own drop counter | MD:214,307; U/spsc_record_queue.h:101-109 | MINOR |
| C2 | MD: "the writer walks at most the table's size" (17th thread). No header states the clamp of m_claimedCount (which an atomic add can push past 16) to kRecordingThreadsMax in the writer's snapshot | MD:256; H/recorder_internal.h:56-58,66; H/record_writer.h:137 | NOTE |
| C3 | Header elements with no description in MD sections 2, 3, 7 or 11: RecorderNameThisThread (only section 4 history, MD:175); SpscProducerRecordsQueued (only section 8, MD:298); RecordFileClose; the queued kind byte QUEUED_SPAN/QUEUED_EVENT; DropKind; the RecordCount type | H/recorder.h:66-69; U/spsc_record_queue.h:53-54; H/record_writer.h:79; H/recording_thread.h:37-48; U/common_names.h:14 | NOTE |

Checked and matching: every number MD states against its header (16 threads, 16,384 records, half-full watermark, 8 frame and 24 mask buffers, 8 KiB record, 31 caller fields, 16 KiB line buffer, 192/31/8192 bounds, 64/32 folder and name, 5 s wake, flush and stall, 100 lines, 40 and 5 minutes, 0.45 PNG ratio, 15 span stages, ten health values, every line kind and key in the MD sample lines vs H/record_file.h).

## D. Internal consistency of recorder.md

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | Drawing 1: the push takes "no lock". Gate item 1: a drop takes the drop record's mutex and a half-full crossing takes the condition variable's lock | MD:20 vs MD:205 | MINOR |
| D2 | "A thread's first record claims the next entry by an atomic add" (no build named). The Python mapping: in Python under the state Lock, in C by an atomic add | MD:310 vs MD:239 | MINOR |
| D3 | Drawing 5 lists Destroy's stop as "STOPPING, a deadline, the flag" and FlushInDie's without STOPPING; the TOCTOU row gives the order reason, deadline, then STOPPING | MD:24 vs MD:261 | NOTE |
| D4 | Drawing 6 lists the writer's stores as failed writes, PNG clashes, free space, under-reserve, progress time; truncated_lines and last_write_failed are missing (both in the health line sample) | MD:25 vs MD:228 | NOTE |

## E. Internal consistency of the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | The last pass with a failed append cannot work as written: "a failed append ends the pass" vs the last pass repeats "steps 2 to 6 again and again until every queue ... empty, or the clock passes that deadline". On a dead disk this is either an unthrottled retry loop for up to 5 s (failed_writes counts every attempt) or a stop; neither is stated. The die line, fault lines and health line appends after it are also unspecified on failure | H/record_writer.h:140-142,148-149,163-168; H/recorder.h:88-90 | BLOCKING |
| E2 | A frame line retried after a failed append cannot know its "ok" value: the PNG result (written, failed, name clash) is not kept; PoolBuffer carries only the stamps and mb_pngWritten, and mb_pngWritten is set after a failed write and after a clash too | H/record_writer.h:144-149; H/buffer_pool.h:6-8,48-49,53-60; H/record_file.h:88-94 | BLOCKING |
| E3 | Lost count: a producer that loaded RUNNING and pushes after the writer's final empty check succeeds; the record stays in the queue, is never written and is never counted. The header says such a record "is dropped and counted" | H/record_writer.h:174-176; H/record_span.h:38-39; MD:250 | MINOR |
| E4 | record_span.h: the span path takes "no lock". recording_thread.h: a drop takes the drop record's mutex and a half-full crossing the condition variable's | H/record_span.h:36-37 vs H/recording_thread.h:125-127 | MINOR |
| E5 | Two meanings of a "...Bytes" bound: kRecorderProcessNameBytes = 31 is a length ("fits ProcessName, 32"); kRecordFolderBytes = 64 and kRecordNameBytes = 32 are buffer sizes (FolderName/FrameName m_text[64]/[32]), so the longest folder is 63 | H/recorder.h:29; H/record_frame.h:11-12; H/buffer_pool.h:37-38 | MINOR |
| E6 | m_droppedFramesReported has no @ entry; the block documents only the spans and events counterparts | H/recording_thread.h:96-98,107 | NOTE |
| E7 | runtime_internal.h declares no create, destroy, start or join for OsEvent, OsLock or OsThread, yet Create allocates m_wake, m_stopped, m_stateLock, the drop locks and the index-queue locks, and Destroy joins m_thread | runtime_internal.h:76-92; H/record_writer.h:107-109; H/recorder_internal.h:61; H/recording_thread.h:64; U/index_queue.h:24 | NOTE |
| E8 | kRecorderSessionDirBytes = 192 "plus the file name fits PathText, 256", but the PNG path <sessionDir>/<folder>/<name>.png reaches 192+1+63+1+31+4 = 292 bytes; no type holds it | H/recorder.h:28; H/record_file.h:16 | NOTE |

Checked, no finding: every include resolves (gcc clean); no type used undefined; no constant with two values; leftover-name grep (slot, ready, retry, FramePool, FIELD_INVALID, lazy, compare-and-swap, a second Create, an abandoned writer, a shared stall field) finds only the SPSC ring's own record slots (U/spsc_record_queue.h:69-104), the frame buffer's slot of module 04 (H/record_frame.h:23-24), and "no lazy initialization" statements; no stall field outside the pool (H/record_writer.h:94-95); the state changes under a lock, not a compare-and-swap (H/recorder_internal.h:24-29).
