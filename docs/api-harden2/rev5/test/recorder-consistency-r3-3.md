# Recorder consistency check, round 3, checker 3

**Verdict: NOT CONSISTENT. 2 BLOCKING, 17 MINOR, 24 NOTE (43 findings).**

Sources: the 16 headers (00-util 6, 01-recorder 10), runtime_internal.h:76-88 (OsEvent),
recorder.md (461 lines), docs/spec-harden2-cleanup.md rows 908-1063.
Paths: `H/` = docs/api-harden2/rev5/modules/01-recorder/, `U/` = .../00-util/, `MD` = H/recorder.md,
`L` = docs/spec-harden2-cleanup.md.

Mechanical checks, all clean:
- gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11 on the 10 recorder headers: 0 errors, 0 warnings.
- recorder_aggregate_for_review.md: all 16 header blocks byte-identical to the files (script diff).
- Measured sizes: struct Recorder 1408 (MD:152 says 1408), RecorderCounters 28 (RCD31: 28),
  SpscRecordQueue 256 with head/tail/drop at 64/128/192 (MD:302: 256, 4 KiB for 16).
- LINE_KIND_NAMES 9 = LineKind 9; SPAN_STAGE_NAMES 15 = SpanStage 15, same order.
- Every key in the MD:217-225 samples exists in record_file.h with that spelling.

## A. Document vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| A1 | Frame line sample has `"ok":1`; header says ok is true or false (a JSON bool). The health sample uses `false` | MD:222; H/record_file.h:84-85 | MINOR |
| A2 | TOCTOU row says "one writer per state transition". The header names two writers of STOPPED: the writer, or Destroy past its deadline | MD:257; H/recorder_internal.h:23-25 | MINOR |
| A3 | Python type check has no home on the hot path. The makers check type and range, but the tuple path uses no maker and the tuple declares no type. The doc relies on that check: test 5 ("a float where an int is declared"), gate 3, the makers row | MD:204, MD:237, MD:324; H/record_field.h:80-88 | MINOR |
| A4 | The writer makes the frame folder. No doc section says so: drawing 2 step 6 and section 2 omit it | H/record_file.h:16, H/record_writer.h:144-145; MD:21, MD:27 | NOTE |
| A5 | Drawing 5's Create list omits the asr_clips/ mkdir. Only section 11 names it | H/recorder.h:26-28; MD:24 vs MD:455 | NOTE |
| A6 | A thread that got no queue is described only in HISTORY rows (D2, D4). That path covers the failed allocation, mb_queueTried and the two queueless counts | H/recording_thread.h:67-68, H/record_writer.h:89-90,114-115, H/record_field.h:67; MD:158-159 | NOTE |
| A7 | No doc section gives the folder and name limits, the die reason or the common names: kRecordFolderBytes 64, kRecordNameBytes 32, DieReasonText 256, PathText 256, ProcessName 32, ThreadName 32 | H/record_frame.h:10-13, H/record_writer.h:53, U/common_names.h:10-12 | NOTE |
| A8 | Drawing 3's code names omit OsEventIsSet, which the producer's skip depends on | MD:22; H/recording_thread.h:101-102; runtime_internal.h:85 | NOTE |
| A9 | Drawing 5's last pass omits step 7 (retry) and step 9 (time reference + health before the late frames) | MD:24; H/record_writer.h:157-160 | NOTE |

## B. Decisions vs headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| B1 | PY1 says the only Python atomicity is one container operation or a lock: "no check-then-act on shared state unless one side alone can run". The header says "in the Python build the GIL serializes every access", but several threads write the same counters: m_droppedFrames (the job threads), m_droppedSpansWithoutQueue and m_droppedEventsWithoutQueue (any queueless thread). A `+=` there is a read-modify-write and loses counts | L:1041; H/recorder_internal.h:35-38, H/record_writer.h:114-115 | BLOCKING |
| B2 | PY1: two compare-and-swaps have no Python form. Destroy's deadline and the publish's oldest-ready stamp both use one, and PY1 forbids an unlocked check-then-act | L:1041; H/record_writer.h:78-84, H/record_frame.h:25-26 | MINOR |
| B3 | RCD34 B2 says "we must drop them and count accordingly". Frames still READY when the last pass passes m_stopDeadline are counted nowhere: only queued records are added to the dropped counts | L:1058; H/record_writer.h:159-162 | MINOR |
| B4 | RCD25: the retry queue is "appended again at the end of each pass". Header: step 7 of 9, then steps 8 and 9 follow | L:1049; H/record_writer.h:148 | NOTE |
| B5 | RCD19 T1 moved the clock to monotonic_clock.h. recorder.h still opens "its clock, its lifetime, its health" (the RCD5 wording) | L:1039, L:1025; H/recorder.h:1-2 | NOTE |
| B6 | PRF4 is cited for the cut rule and for drop-new, but the PRF4 row has neither. Only RCD12 says "PRF4's cut rule" | L:956, L:1032; H/record_field.h:86; MD:136, MD:321, MD:358 | NOTE |
| B7 | PRF5 is cited for every writer constant being config in Python. PRF5 rules only the thread table size | L:957; H/record_writer.h:36-37 | NOTE |

Rulings checked with no finding (latest ruling, then the header line that implements it):

| ruling | latest consequence (short) | header | verdict |
|---|---|---|---|
| PRF1 | stage an enum, name as text in file | H/record_span.h:16-33, H/record_file.h:42-45 | OK |
| PRF2, PRF3 | app holds start stamps; Create(sessionDir, process) | H/record_span.h:40-46, H/recorder.h:36-41 | OK (128-byte record superseded by RCD11/PY3) |
| PRF4, PRF5, RCD19 item 2 | 17th thread dies; cap = design count 16, config, never nproc | H/recording_thread.h:20-27 | OK |
| PRF7, RCD1, TEL1 | no handle, ambient instance | H/recorder.h:3, H/recorder_internal.h:50-51 | OK |
| TEL2 | no die after start; "one event" per fault | H/record_writer.h (no record call) | OK; "one event" is OPEN P2 |
| TEL3, TEL4 | generic sink, helpers in owners | no helper in any recorder header | OK |
| TEL5, TEL13, TEL14, TEL16 | lossless PNG level 1, source size, refuse start under reserve | H/record_frame.h:1-2, H/recorder.h:31-32 | OK |
| TEL7 | full rings/pools drop and count | U/spsc_record_queue.h:46, H/frame_pool.h:68 | OK (pause/resume superseded by RCD25) |
| TEL9, TEL17, TEL18 | W x H x 3 x 0.45 x 30/min x min; 40 and 5 min; uint64 | H/record_writer.h:38-50, H/recorder_internal.h:61-63 | OK |
| TEL10, TEL11, TEL12 | stall computed at read; 64-bit/float values as macros | H/record_writer.h:47-50,134-136 | OK (10 ms poll superseded by RCD6/RCD27) |
| RVW3 | job holds the slot during the copy | H/record_frame.h:20-22 | OK |
| RVW4, RVW6, RVW7 | per process, per thread, merged | H/record_file.h:14, H/recording_thread.h:1-5 | OK |
| GIL2 | recording threads are the app's; none to record | H/recording_thread.h:1-3,21 | OK |
| PY1 (index queue) | deque under one Lock | U/index_queue.h:4-5 | OK |
| PY2, PY3, RCD18 | tuple deque in Python; C ring is the C form | U/spsc_record_queue.h:4-7, H/record_field.h:80-83 | OK |
| RCD2, RCD5 | FrameSize, FrameView, one FrameView* | U/frame_types.h:8-25, H/record_frame.h:27-32 | OK |
| RCD3 | pid in name, app only frames, session folder before child | H/record_file.h:14, H/recorder.h:24,27-28 | OK |
| RCD4, RCD34 B1 | no sample, no GPU record | grep "gpu" over headers: 0 hits | OK |
| RCD6, RCD7, RCD27 | event-driven OsEvent, 5 s wait timeout, mask limit from config | H/record_writer.h:23-28,47, H/frame_pool.h:20-25 | OK |
| RCD9, RCD22 | SPSC endpoints, own cache lines, Front/Pop, FramePool names | U/spsc_record_queue.h:26-66,110-112, H/frame_pool.h:63-75 | OK |
| RCD11 (R4), RCD12 | watermark wake, time ref per fsync, drop gap, cut rule, no cached index, one snapshot | H/recording_thread.h:25-29,43-47,101-103, H/record_writer.h:139-152 | OK |
| RCD16 | names table macros, open flags, EVENT_KEY_FIELDS, unusedCtx | H/record_file.h:14-17,38-45,82, H/recorder.h:52 | OK |
| RCD17, RCD20, RCD37 | literal names; 31 + "cut" | H/record_field.h:11,23-31, H/record_event.h:9 | OK |
| RCD21, RCD23 | header per actor; slot ring + byte area; writer owns queue list | H/recorder_internal.h:1-8, U/spsc_record_queue.h:78-113, H/record_writer.h:111-113 | OK |
| RCD25 (W1) | 64-line retry queue, two index queues, full drops counted | H/record_writer.h:41,86-89,117-119 | OK (order: B4) |
| RCD27 | "under one lock" | H/frame_pool.h:49-51 (two locks) | OPEN P1, not a finding |
| RCD31, FB8 | counters unpadded | H/recorder_internal.h:35-48 | OK (28 B measured) |
| RCD34 A1 | Create makes asr_clips/ | H/recorder.h:26-28 | OK |
| RCD34 B2, RCD35 | non-RUNNING dropped and counted; 16384; RecordResult on all three | H/recorder_internal.h:20-22, H/recording_thread.h:28, H/record_field.h:65-78 | OK (frames: B3) |
| RCD36, RCD37 | 8192, "cut" only, no "length" | H/record_field.h:23-31 | OK |
| RCD38, RCD39 | the fix lists | H/record_writer.h:122,153-166, H/recorder.h:32-35, H/record_frame.h:16-26 | OK |
| RUN3 | DieActionFn(ctx, reason, deadlineNs) | runtime.h:18; H/recorder.h:50-52 | OK |
| REV7, REV8 | a cause per mechanism | headers carry no failure matrix | see C1, C2 |

## C. Decisions vs document

| # | what | where (file:line) | severity |
|---|---|---|---|
| C1 | REV8 gate 12 requires a cause for every counter with a policy. png_name_clashes (count, skip the PNG, ok false) has no failure-matrix row and no SEEN, DESIGNED or FORCED cause | L:1014; MD:260-274; H/recorder.h:74-75 | MINOR |
| C2 | REV8: the queue allocation failure has no failure-matrix row. That path has its own two counters and the mb_queueTried rule | L:1014; MD:260-274; H/record_writer.h:114-115 | NOTE |
| C3 | Section 11 cites OPEN 1 for MonotonicNs/MonotonicNow. OPEN 1 approved RecorderTimestamp/RecorderNow (RCD2); RCD15 gave today's names | MD:416; L:1022, L:1035 | NOTE |
| C4 | The failure matrix says the retry runs "in step 7 of the same pass"; RCD25 says "at the end of each pass" (same drift as B4) | MD:263; L:1049 | NOTE |

## D. Internal consistency of the document

| # | what | where (file:line) | severity |
|---|---|---|---|
| D1 | "this document changes the boundary and the lifetime, not the mechanisms". Section 4's change table changes mechanisms: the queue, the wake, the retry queue, the pool state, the record shape | MD:7-9 vs MD:119-135 | MINOR |
| D2 | "the drop totals: summed by the writer, never a shared +=". Drawing 6: "the job threads add dropped frames" (a shared add) | MD:240 vs MD:25 | MINOR |
| D3 | "the file name carries the pid, so O_EXCL is the second guard" against a second app. A second app has another pid, so another file name, and O_EXCL cannot fire | MD:272 vs MD:27, MD:31 | MINOR |
| D4 | The HISTORY disclaimer and the instance row call the current headers "draft 14"; the aggregate is draft 15 | MD:143, MD:150 vs H/recorder_aggregate_for_review.md:1 | MINOR |
| D5 | "about 250 a drain" vs the doc's own 40 spans a second x 5 s = 200 (RCD35: 200) | MD:130 vs MD:210, MD:293 | NOTE |
| D6 | Test 6's "the count is true after a drain" does not state the re-arm of the once-per-crossing rule | MD:325 vs MD:293 | NOTE |
| D7 | "the hot path passes numbers and names, and builds no text". Instance 2 builds boxes_json(reply) text before record_event | MD:37-38 vs MD:79-80 | NOTE |

Stated the same everywhere (checked): the thread cap 16 (MD:20,136,203,326,426); the queue 16,384 (MD:121,268,293,321); the pools 8/24 (MD:23,132,265); the wake sources and the 5 s timeout (MD:21,22,129,236,253,304); the file name (MD:27,97,118,423); the nine pass steps (MD:21,263); the cut field (MD:20,121,204,269,322); the 8 KiB bound (MD:7,121,204,269).

## E. Internal consistency of the headers

| # | what | where (file:line) | severity |
|---|---|---|---|
| E1 | "its JSON escaping at most doubles it, so a line always fits" is false, and RCD38 removed the line cut. A control byte escapes to 6 bytes (\u0001). A name is an 8-byte pointer in the record but prints in full. An 8-byte int64 prints up to 20 characters. An 8192-byte record can exceed the 32768-byte LineText | H/record_writer.h:33-35,40,122,125 | BLOCKING |
| E2 | A second Create resets only mb_announced and the deadline. m_stopped stays set by the old writer, and m_dieReason stays. A later FlushInDie or Destroy then returns from its wait at once, before the new writer's last pass | H/recorder.h:32-35, H/recorder_internal.h:26-27, H/record_writer.h:94-97,162-164 | MINOR |
| E3 | Records left after the final drain are "added to the dropped counts", but nothing says they leave the queue. A second Create "reuses the queues" (MD test 22), so the new writer writes them: counted and written | H/record_writer.h:160-162; MD:341 | MINOR |
| E4 | "so a second process with the same name fails" vs the file name format, which carries the pid | H/record_writer.h:57-58 vs H/record_file.h:14 | MINOR |
| E5 | Destroy past the timeout "(no join; health shows stalled)". The stall rule covers frames only, so a process with no frame waiting never shows it | H/recorder.h:43-45 vs H/record_writer.h:134-135, H/recorder.h:76-77 | MINOR |
| E6 | m_droppedFrames causes omit a frame during STOPPING or STOPPED. Two other headers call that DROPPED and counted | H/recorder.h:69-71 vs H/record_field.h:66-71, H/record_frame.h:18-19 | MINOR |
| E7 | mb_lastWriteFailed says "its line waits in the retry queue". A full retry queue drops that line | H/recorder.h:78-79 vs H/record_writer.h:88-89 | MINOR |
| E8 | "a bad value drops the record and counts it, before any reserve". No reserve step exists since the byte ring went (RCD18, RCD23) | H/record_field.h:87-88 | MINOR |
| E9 | One failed line can count 2+ times in m_failedWrites: at the failed append, at a re-failure in step 7, at a drop from the full queue. The count's unit is unstated | H/record_writer.h:59,86-89,148; H/recorder.h:72-73 | NOTE |
| E10 | Two drop counters per queue: SpscRecordQueue.m_dropped (via SpscProducerRecordsDropped) and RecordingThread's m_droppedSpans/m_droppedEvents. Only the second is said to feed the drop line and health | U/spsc_record_queue.h:46,55,112; H/recording_thread.h:57-58 | NOTE |
| E11 | m_firstDropAt is restored at each new gap. A drop line covering two gaps in one pass reports "from" of the last gap only | H/recording_thread.h:43-47; H/record_file.h:92 | NOTE |
| E12 | OsLock has no operations anywhere. OsEvent and OsThread have no create, destroy or join. index_queue.h and Writer depend on them | runtime_internal.h:76,82-88; U/index_queue.h:17; H/record_writer.h:27-28 | NOTE |
| E13 | SpscRecordQueueCreate does not say maxRecords must be a power of two, though m_slotCount must be | U/spsc_record_queue.h:34-43 vs :99-100 | NOTE |
| E14 | The C byte area is 64 bytes per slot. Records over 64 bytes fill it before the slots, so "16,384 holds over six minutes" holds by slot count only | U/spsc_record_queue.h:75,94; H/recording_thread.h:23-24 | NOTE |
| E15 | "(INVALID_ARG, Python)" limits that drop cause to Python; record_field.h counts INVALID_ARG in every build | H/recorder.h:65-66 vs H/record_field.h:70-71 | NOTE |
| E16 | After the last pass, the leftover records go to "the dropped counts": the thread entries or the totals is unstated. They land after the last health line, and no later pass sums the thread entries | H/record_writer.h:160-162; H/recorder.h:67-68 | NOTE |
