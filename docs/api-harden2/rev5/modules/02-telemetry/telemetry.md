# telemetry: the record of a run (rev5 module review; design closed 2026-10-16)

> **FOLDED into the recorder (RCD1, 2026-10-18; the fold approved as O4, RCD2).** The telemetry module's
> mechanisms live on in `../01-recorder/recorder.md`; the contracts there replace the ones below.
> This document stays until the recorder is approved, for its measurements, its rejected
> alternatives and its tests, which the fold carries over.

The header is `telemetry.h` (the generic sink). The records live with their owners:
`telemetry_record_dispatch.h` (a turn, an event) and `telemetry_record_vision.h` (a pass, a
job, a box). No drawing (the owner removed them, DOC1). The design document is
`../../01-system-architecture.md`. The module below it, perf, is approved. The review record:
`../../test/telemetry-*.md` (three subagent rounds), the ledger rows TEL2
to TEL17 in docs/spec-harden2-cleanup.md.

## 1. The job, in one sentence
Telemetry writes the events, frames and masks of a run to disk for replay, and never kills the app.

## 2. The picture
Six boxes:
```
 [1] the callers            [2] the sink: copy          [3] the writer thread
     main thread  ─────────►    an event: its ring  ────►    one consumer
     job threads  ─────────►    a frame: the pools  ────►    encodes, writes
                                                                  │
 [6] the health, read       [5] the readers         [4] the files on disk
     by the main thread ◄──     the replayer     ◄──     trace.jsonl, the PNGs
     each frame                 log/show.py
```
1. **The callers.** The main thread writes a turn, a job and an event. The emergency thread
   writes the stop and its reply. A job thread writes a pass while it holds its frame slot.
   Each call goes through a helper in the owning module.
2. **The sink copies, during the call.** An event's keys go into the calling thread's ring. A
   frame goes into the frame pool, a mask into the mask pool. The caller keeps nothing and
   never waits. A full ring or pool drops the record and counts it.
3. **The writer thread.** The only consumer. It encodes each frame and mask as a lossless PNG
   and writes the files directly. It keeps trace.jsonl open and fsyncs it every 5 s. It
   counts failed writes and pauses on them. It never calls die().
4. **The files.** meta.json at Create. trace.jsonl holds every event line with its topic. A
   frame is `<channel>/<seq>.png`; a mask is `<channel>/<seq>_mask_<k>.png`.
5. **The readers.** The session replayer and log/show.py read the files by the helpers' keys.
   The app never reads them.
6. **The health.** Six counters, one per cause. The main thread reads them each frame, like a
   status row. A change becomes a chat line.

## 3. How a caller uses it: two instances, in the Python of the build
**Instance 1: the main thread, through the dispatch module's helpers; it never waits.**
```python
# app/main.py, once per process, right after perf; None = the folder is unwritable: die
size = frame_source_size(config)                   # the webcam probed; the drone 1920x1080
telemetry = telemetry_create(session.dir, size.w, size.h, info_json=models_json)

# app/dispatch.py, the main thread
telemetry_turn_decided(telemetry, turn)            # on the Decision message: a "turn" line
telemetry_turn_ended(telemetry, turn)              # on the PlatformReply: at = ended_at
telemetry_event(telemetry, Event(at=m.at, kind="key", detail="F4"))

# every frame, beside the status rows
health = telemetry_read_health(telemetry)
if health != last_health:
    chat.line(f"record: dropped {health.dropped_frames} frames, paused={health.degraded}")
    last_health = health

def telemetry_turn_decided(t, turn):               # the helper, in app/dispatch.py
    # js() is json.dumps: every text is escaped; the mission is embedded as an object
    telemetry_record_event(t, "turn", turn.started_at,
        f'"seq":{turn.seq},"phase":"decided","input":"{turn.input}","heard":{js(turn.heard)},'
        f'"audio_clip":{js(turn.audio_clip)},"he2":{js(turn.he2)},"kind":"{turn.kind}",'
        f'"mission":{js(turn.mission_json)},"target":{js(turn.target)},'
        f'"reject":{js(turn.reject_reason)},"job":{turn.vision_job}')
```
**Instance 2: a job thread records a pass through its helper, then posts its result.**
```python
# perception/jobs.py, a highlight job on a pool thread
slot = frames.acquire_latest()
t0 = perf_now()
reply = sam3.detect(req, slot.seq, concepts, priority)
t1 = perf_now()
telemetry_vision_pass(telemetry, VisionPass(job=job.id, job_kind="highlight", index=job.passes,
    req=req, step="refresh", started_at=t0, ended_at=t1, frame=slot.seq,
    captured_at=slot.captured_at, bgr=slot.pixels, width=slot.width, height=slot.height,
    stride=slot.stride,
    phrase_sent=concepts, boxes=boxes_of(reply), masks=reply.masks))
frames.release(slot)                               # the sink copied, or dropped and counted
job.passes += 1
results.put(VisionResult(job=job.id, state=TRACKING, boxes=reply.boxes))

def telemetry_vision_pass(t, p):                   # the helper, in perception/jobs.py
    channel = f"perception/{p.job:04d}-{p.job_kind}"
    name = f"{p.index:06d}"
    r = telemetry_record_frame(t, channel, name, p.captured_at, BGR24,
                               p.width, p.height, p.stride, p.bgr)
    png = f"{name}.png" if r == OK else ""
    masks = []
    for k, m in enumerate(p.masks):
        r = telemetry_record_frame(t, channel, f"{name}_mask_{k}", p.captured_at, GRAY8,
                                   p.width, p.height, p.width, m)
        masks.append(f"{name}_mask_{k}.png" if r == OK else "")
    telemetry_record_event(t, "pass", p.started_at,
        f'"job":{p.job},"index":{p.index},"req":{p.req},"step":"{p.step}",'
        f'"ended":{p.ended_at},"frame":{p.frame},"captured":{p.captured_at},'
        f'"phrase":{js(p.phrase_sent)},"boxes":{boxes_json(p.boxes)},'
        f'"answer":{js(p.answer)},"png":"{png}","masks":{json.dumps(masks)}')
```

## 4. The decisions, all taken (the owner's words in the ledger, TEL2 to TEL17)
| decision | the ruling |
|---|---|
| telemetry never kills the app after start-up | TEL2: drop, count, one event, a chat line |
| the sink is generic; the records live with their owners | TEL3: telemetry.h; telemetry_record_dispatch.h, telemetry_record_vision.h |
| perf gets the same helper pattern | TEL4: perf_record_<owner>.h |
| the frames and the masks | TEL5, TEL13, TEL16: lossless PNG level 1, at the source's resolution |
| the start-up check stays | TEL6: "the app hasn't started yet"; Create returns NULL, the start-up dies |
| a full ring or pool | TEL7: drop and count; nothing waits |
| a failed write | TEL7: pause, count, resume when the disk recovers |
| the files | TEL7: one trace.jsonl for every line; frames and masks by channel folder |
| the stop's reply | TEL7: the emergency thread posts a PlatformReply message |
| the audio clip | TEL8: the mic listener takes the newest clip name at the transcript; no rename |
| the free-space rule | TEL9, TEL17: from the frame size, the expected vision rate and the flight length; no number for one machine |
| the fsync | TEL10: trace.jsonl every 5 s; the PNGs never |
| the blob call | TEL14: none; no caller |
| the N-th pass knob, a codec parameter | TEL14: YAGNI, none |

**The free-space rule (TEL17).** bytes = W x H x 3 x 0.45 x passes per minute x minutes. W and H
are the source's; 0.45 is PNG level 1's worst measured ratio; the passes per minute is the
expected vision rate, 30 (the busiest recorded session; the median is 15; full load is 180 and
no flight sustains it); the minutes are the flight length, 40, and the reserve, 5. Both rates
are config values. At 1080p: 2.8 MB a pass; the start check 3.4 GB, which is 40 minutes at the
expected rate (6.7 minutes at full load); the pause reserve 0.4 GB, 5 minutes (50 s at full
load). At 720p: 1.5 GB and 0.2 GB.

**The frame size at start.** The frame buffer and telemetry are created before the frame
source runs, and both need the size. The webcam is probed at start (open, read one frame,
read its size); the drone stream is 1920x1080, a given; a video file is probed. The probe
runs before the buffer and the logger are created. No issue; a start-order fact for the app.

## 4a. The records and their homes (TEL3)
| record | the owning module | the helper | the topic | the keys |
|---|---|---|---|---|
| a turn, decided | the app's dispatch | TelemetryTurnDecided | "turn" | seq, phase, started, input, heard, audio_clip, he2, kind, mission, target, reject, job |
| a turn, ended | the app's dispatch | TelemetryTurnEnded | "turn" | seq, phase, ended, status, refused, spoken |
| an event | the app | TelemetryEvent | "event" | kind, turn, job, detail |
| a vision pass | the vision jobs | TelemetryVisionPass | "pass" + the files | job, index, req, step, started, ended, frame, captured, phrase, boxes [x1, y1, x2, y2, score, label], answer, png, masks |
| a job, started and ended | the vision jobs | TelemetryJobStarted, JobEnded | "job" | id, turn, kind, phrase, requested, ended, state, why, passes, answer, spoken, channel |
| a box | the vision jobs | TelemetryBox | inside "pass" | x1, y1, x2, y2, score, label |
| the health line | telemetry itself | the writer, at Destroy | "health" | the six counters |
The two record headers hold these now; each moves into its module's header at that review.
The same for perf: `perf_record_<owner>.h`, one per owning module.

## 5. Today
The code: `projects/integration_harden2/log/session.py` (265 lines), `log/disk.py`,
`log/session_files.py`, `log/show.py`. One `SessionLog(folder)` is built by the app and handed to
the turns and the vision tasks. A turn: `begin()` opens a mutable dict in thread-local storage
and claims the mic clip; the recognizer calls `set()` on it; `commit()` appends one fsynced
line. A pass: `begin_request()` makes a folder; `save_pass()` encodes a JPEG and writes it plus
a json on the job thread, with an atomic write and fsync each; `end_request()` rewrites the
request json. No mask is saved. Errors (2026-09-23): no status row; a failed write dies.
What is wrong with it against rev5: app state inside the logger (the turn counter, the open
requests, the claimed clips, the current record per thread); a mutable record written by the
recognizer; every write on the caller's thread, fsync included; a lossy frame; a die() on a
disk fault, which mid-flight is a hand-over to the RC.

## 6. The rulings that bind it, and the forces
Rulings: the table of section 4, plus NAM3 (Create and Destroy), RVW3 (the job holds its slot
across the request and releases after), RVW4 (die mid-flight = the hand-over; not for this
module), SYS1 (the main thread never blocks), V1 (audio never enters git; sessions/ is
gitignored), the 2026-09-23 start-up rule.
The forces, measured on this machine:
- A frame at 720p is 2.76 MB raw; a memcpy of it 0.05 to 0.18 ms; a PNG level 1 encode 37 to
  41 ms, 1.0 to 1.26 MB (0.36 to 0.45 of raw). At 1080p: 6.2 MB raw, about 90 ms, 2.8 MB.
- A mask is one byte per pixel; a PNG of it 3.5 to 4.3 ms, 8 to 16 KB (a synthetic mask).
- JPEG q95 moved one SAM3 box in 16 and the scores by up to 0.086 (40 images); so lossless.
- The rates: a turn per 2 s; vision at most 3 passes a second (SAM3 is serial), 30 a minute
  expected, 15 the median of the recorded sessions; a job end a few times a minute.
- The writer's work at full load: 3 x 41 ms = 123 ms a second at 720p (busy 12 %); 270 ms at
  1080p (busy 27 %); cv2 releases the GIL while it encodes.
- A write() returns in under 1 ms; an fsync of the trace costs 0.6 ms; this kernel's flusher
  runs every 5 s and writes back pages older than 30 s.
- Thread identifiers are recycled; a frozen Python object freezes nothing inside it; a
  put(timeout) blocks the caller; an unsigned timestamp compare must be `now > ref + limit`.

## 7. The design gate
**Ownership.** The app's main thread calls `TelemetryCreate(sessionDir, width, height,
infoJson)` once, right after perf and after the source's size is known, and
`TelemetryDestroy(timeout)` right before `PerfDestroy`. It holds the pointer and passes it to
the dispatch and the vision jobs. `TELEMETRY_NONE` records nothing. Every constant is a config
value read at Create; the masks per frame is the perception's own mask limit.

**Data in.** Two generic calls: an event (a topic, a timestamp, JSON keys) and a frame (a
channel, a sequence number, the pixels, BGR24 into the frame pool or GRAY8 into the mask
pool). Every text and every pixel is copied during the call. The sink knows no turn, pass or
job; the owning modules' helpers build the records.

**The deep copy.** An event's keys into the calling thread's ring (256 records of 4 KiB,
preallocated; a put is an index step, no lock, no allocation; a full ring drops and counts; a
longer event is our bug: INVALID_ARG, counted). A frame into one of 8 preallocated frames; a
mask into one of 24; a full pool drops and counts; the caller releases its slot at once. A
size or format not Create's is INVALID_ARG, counted as a dropped frame, never degraded.

**Data out.** meta.json at Create (the session, the host, the three clocks as a PerfClockLine
read by telemetry itself, the frame size, the info JSON). trace.jsonl: one line per event with
its topic, in write order; the handle stays open; flushed and fsynced every 5 s and at
Destroy; a reader skips a torn last line. The PNGs: written directly, never fsynced; a torn
one is skipped. The "health" line at Destroy; the "die" event in die().

**Mutable state, and its owner.** The rings: one per recording thread (up to 16; the design
has 10: the main thread, the emergency thread, 8 job threads); the recording thread stores
the write index, the writer the read index. The two pools' free lists. The six counters and
the four stall values: atomic stores, one writer each, read by the main thread. The trace
handle and the free-space count: the writer's.

**Threads.** One writer thread, the only consumer. It drains the rings and the pools, encodes,
writes the files and then the line, bumps the written count and the last-finished time,
returns the pool slot; every 5 s it fsyncs the trace; every 100 records it reads the free
space; on a failed write it counts, pauses, retries later; idle, it sleeps 10 ms, then 50 ms
after 500 ms of nothing. `TelemetryDestroy` writes the health line, puts the sentinel, joins
up to the timeout, returns anyway. `TelemetryFlushInDie` writes the die event, then as
Destroy; on the writer's own thread it appends the die line once and returns.

**Processes.** None.

## 7b. The gate, answered (modules/README.md, items 1 to 10)
1. The real-time path: the main thread calls RecordEvent only; the call copies at most 4 KiB
   into its own ring and stores one index; worst case about 2 us; no lock, no wait; a full
   ring drops. The main thread also reads six atomic values each frame.
2. A sink: telemetry.h holds no domain type; the records live in telemetry_record_*.h; no
   app state; no die() after Create.
3. Fault containment: the only exit is Create returning NULL at start-up; the app's start-up
   dies on it (2026-09-23). Every later fault degrades to a counter.
4. Buffer lifetimes: a job thread calls VisionPass while it holds its frame slot; the sink
   copies during the call; the slot is released right after, never held for the record.
5. Types and units: every constant is a config value with its unit in its name; the two
   nanosecond values and the ratio are macros; the stall compare is `now > ref + limit`.
6. One home: the sink in telemetry.h; a turn and an event in telemetry_record_dispatch.h; a
   pass, a job and a box in telemetry_record_vision.h; nothing twice.
7. The contract: the files and their keys in the headers; the readers in the change-impact
   table of section 9.
8. The Python mapping: the rings are lists found through thread-local storage; the pools are
   preallocated numpy arrays with free-index deques; a put never blocks; cv2.imencode
   releases the GIL; no exception leaves the module (the disk's try is in util/guarded.py).
9. The cost budget: the main thread records about 2 events a second at 2 us each, 0.01 % of a
   frame; a job thread copies a frame in 0.18 ms per pass; the writer encodes 3 PNGs a second
   at 38 ms (720p) or 90 ms (1080p).
10. gcc -Wall -Wextra on the three headers; the two drawings pass the checker.

The failure matrix:
| failure | the module's state | what the record shows | the aircraft |
|---|---|---|---|
| the disk refuses a write (EIO, ENOSPC) | the writer pauses; failed writes counted; degraded | a "health" change; a chat line | never touched |
| the writer stalls 5 s with work pending | stalled true; the rings fill, then drop | dropped events counted | never touched |
| the free space under the reserve | paused until it rises | a chat line; a hole in the frames | never touched |
| a ring or a pool full | the record dropped and counted | the pass line says png "" | never touched |
| a wrong frame size or format | INVALID_ARG, counted as a dropped frame | the counter; a test catches it | never touched |
| SIGKILL, OOM, a segfault | the rings and pools lost: 0 or 1 record | no "end" line | not by this module |
| a power cut | under 5 s of lines and up to 35 s of PNGs lost | a torn last line or PNG, skipped | not by this module |
| die() elsewhere | FlushInDie after the hand-over and the notify, 5 s cap | a "die" event with the reason | by RVW4, not by this module |

## 8. The notes that did not make the header
- **Why a generic sink with helpers.** The sink stays the same when the planner's schema or
  the detector changes; only a helper changes. Rejected: TEL1's domain-typed sink
  (superseded); a helpers header beside the sink (the structure lives with its owner).
- **Why no die().** A logger has no authority over a vehicle; PX4's logger and rosbag2 drop
  and count for the same reason. Rejected: the 2026-09-23 "a failed write dies", for this
  module after start-up.
- **Why a ring per thread, one writer.** No shared index, no lock on the recording path; one
  consumer keeps every ring single-reader; a disk write can block for seconds. Rejected: one
  shared queue; a bounded queue the main thread waits on; a stall detected by the blocked
  caller (two false-positive rules were found by simulation before the progress rule).
- **Why pools and a copy.** The frame buffer's 32 slots belong to the whole app; a stalled
  disk must not hold any. Rejected: holding the slot until written; waiting for a pool slot.
- **Why direct writes, the trace fsynced, the PNGs not.** An app crash keeps the page cache;
  only a power cut loses it; an fsync per file was up to 10 per pass, 30 a second; reopening
  60 PNGs every 5 s is the same storm in batches. Rejected: a temp file and rename per PNG;
  the folder fsync; the fsync pass over the PNGs.
- **Why lossless PNG level 1.** JPEG q95 moved one box in 16; level 2 buys 1 % for 10 % more
  time; raw is 2.2 times the bytes; lossless WebP is 300 ms. Masks the same, since every tool
  reads PNG. Rejected: JPEG; raw; WebP; packed bits for masks; hardware video encoders.
- **Why one trace file.** One stream of lines with a topic each, as MCAP and rosbag record;
  one torn-line rule. Rejected: a json per job and per pass.
- **Why the clip claim leaves.** The node writes the clip, then publishes; the newest clip at
  the transcript is its clip; the listener carries the name; "" when none is new.
- **Why the free-space rule uses the expected rate.** No flight sustains full vision; the
  recorded sessions run 4 to 32 passes a minute; a reserve sized for 180 a minute for an hour
  would refuse to start on a half-empty disk for nothing (the owner, 2026-10-16).
- **The Python mapping.** The rings: a preallocated list per thread, found through
  thread-local storage; the pools: `np.empty((8, h, w, 3))` and `np.empty((24, h, w))` with
  free-index deques; the writer: one thread, `cv2.imencode(".png", ..., level 1)`, direct
  `open/write/close`, the trace file kept open and fsynced every 5 s, `os.statvfs` every 100
  records; the stop: a sentinel; the GIL check and every constant from config. About 170
  lines; today's 265 go.

## 9. The tests the module ships with (`test/test_telemetry.py`)
Change impact (the build tasks come after every design, with the replayer's own update):
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| the generic sink; the helpers' keys in the owning modules | what the replayer and show.py read | yes | their tests rewritten; a sample-session generator added |
| no die() in telemetry | a failed write no longer ends the app | yes, on purpose (TEL2) | the die tests become health tests |
| lossless PNG at the source's size | the frame files | yes | rewritten |
| masks saved | new files | additive | new |
| no clip rename | asr_clips keeps the ASR names | yes | test_claim_* deleted |
| one trace.jsonl | job.json and passes.jsonl gone | yes | rewritten |
- `test_event_from_the_main_thread_returns_under_one_ms_with_the_writer_blocked`.
- `test_full_ring_drops_and_counts`; `test_full_pool_drops_counts_and_returns_at_once`.
- `test_mask_pool_is_separate_from_the_frame_pool`: 8 passes with 3 masks each all land.
- `test_caller_may_release_and_mutate_the_slot_after_the_call`: the PNG is the original.
- `test_png_is_lossless`; `test_mask_png_is_lossless`.
- `test_pool_is_sized_from_the_source`: 720p and 1080p.
- `test_wrong_frame_size_is_invalid_arg_counted_and_never_degrades`.
- `test_failed_write_sets_degraded_and_never_dies`; `test_degraded_resumes_above_the_reserve`.
- `test_stalled_on_a_dead_writer_a_stuck_write_and_a_slow_writer_not_when_idle`.
- `test_first_record_after_a_long_idle_is_not_a_stall`.
- `test_destroy_with_a_stuck_writer_returns_within_the_timeout`.
- `test_flush_in_die_writes_the_die_event`; `test_flush_in_die_on_the_writer_appends_once`.
- `test_trace_is_fsynced_every_period_and_pngs_never` (a counted stub).
- `test_free_space_rule_from_size_rate_and_minutes`; `test_create_returns_none_under_it`.
- `test_turn_helper_writes_both_lines_and_they_parse`; `test_pass_helper_files_then_line`.
- `test_pass_line_marks_a_dropped_frame_with_an_empty_name`.
- `test_second_transcript_without_a_new_clip_gets_no_clip`.
- `test_every_vocabulary_value_round_trips`; `test_value_outside_a_table_is_written_as_given`.
- `test_every_record_fits_the_event_size`: the largest turn line under 4 KiB.
- `test_meta_json_holds_the_three_clocks_the_frame_size_and_the_info`.
- `test_torn_last_line_is_skipped`; `test_sigkill_mid_pass_leaves_only_parsable_lines`.
- `test_sample_session_generator_matches_the_helper_keys`; `test_show_reads_a_session`.
- `test_pass_cost_on_the_caller_under_one_ms_with_eight_threads`.
