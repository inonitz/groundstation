# The recorder: adversarial design review (2026-10-18, round 1 of 1)

Reviewed: `modules/01-recorder/recorder.md`, `recorder.h`, `recorder_internal.h`, `recorder.html`
(the image alt and the paragraph; the drawing is an embedded PNG). Inherited mechanisms read for
their numbers and rulings: `01-perf/perf.md`, `02-telemetry/telemetry.md`. Gate: `modules/README.md`.
Checks run: `gcc -fsyntax-only -Wall -Wextra -pedantic -std=c11` on both headers; `sizeof` of every
internal struct (gcc, x86-64); `df -T` and `mount` for the session folder's file system.

Measured facts used below:

| fact | value | how |
|---|---|---|
| sizeof(TimingRecord) | 136 bytes, not 128 | gcc, x86-64 |
| sizeof(EventRecord) | 4096 bytes | gcc |
| sizeof(PoolSlot) | 128 bytes | gcc |
| -pedantic warnings | 2: "extra semicolon in struct or union", recorder_internal.h:56 and :59 | gcc |
| the repo's file system | ext4 (bind mount of /dev/nvme0n1p2); `/` is overlayfs | df -T, mount |
| pid_max | 4194304 | /proc/sys/kernel/pid_max |
| perf's approved thread cap | kPerfMaxThreads = 32 ("twice the design", perf.md:136) | perf.h:49 |
| the recorder's thread cap | kRecorderMaxThreads = 16 | recorder.h:148 |
| today's session folder | named by `%Y-%m-%dT%H:%M:%S`, made with `exist_ok=True` | log/session.py:34, :66 |

## The owner's four points

### 1. "How do you actually guarantee that files are being written into properly if there are multiple instances?"
**Verdict: partly holds.**
- **What holds.** One instance per process, one file per process, the pid in the name
  (recorder.md:33-38). Two live processes on one host never share a pid in one PID namespace.
  So two record files never share a writer. A relaunched child gets a new pid and a new file. Only
  the app has a frame channel, so a channel folder has one writer process.
- **What holds for the odd cases.** A child that outlives the app keeps appending to its own file in
  the old session folder. It collides with nothing. Stopping it is the supervisor's job, not the
  recorder's. A slow or network disk blocks only the writer thread. The recording path never
  waits; the rings hold about 100 s at the main thread's rate (perf.md:106-109).
- **Gap 1: the guarantee is by naming, not checked by the kernel.** The record file's open flags
  are not named. Today's session folder is made with `exist_ok=True` at one-second resolution. Two
  apps started in the same second share one folder. Their PNG names then collide
  (`perception/0001-highlight/000000.png`). The kernel can check both facts for free: `mkdir`
  fails with EEXIST, and `open(O_CREAT|O_EXCL)` fails with EEXIST. That is a start-up check
  (Create returns false), not a new mechanism. Cause FORCED (R1-15).
- **Gap 2: "one writer per file" also needs "one writer thread per file".** recorder.h:51 says
  Destroy does "drain, write, fsync, join". Read in that order, Destroy and FlushInDie drain the
  rings and write the file on the caller's thread while the writer thread may still run. Perf's
  drain lock is gone (perf.md:244-245). That makes two consumers of an SPSC ring and two writers of
  one file (R1-5).
- **Gap 3: "append-only" breaks on the full disk that was SEEN.** A write on a full disk may write
  part of a line (write(2)). The writer then pauses and resumes appending. The torn line now sits
  in the middle of the file. The reader rule only skips a torn last line (R1-6).
- **fsync on this machine.** The session folder is on ext4 through a bind mount, not on the
  container's overlayfs. fsync of the file does not persist the new directory entry (fsync(2)).
  After a writeback error, Linux marks the pages clean, and a later fsync can succeed with the data
  lost (LWN, "PostgreSQL's fsync() surprise"). Both need a power cut or a failing disk: FORCED. No
  mechanism; the matrix should name them (R1-16, R1-17).

### 2. "Is the GPU sampling different to the way we should sample CPU side code? ... keep the sampling contract/API as minimal as possible."
**Verdict: partly holds.**
- **The distinction is right.** A span is a duration around our own code. A sample reads a value
  that exists without us. CPU-side code is timed by spans, never sampled; statistical profiling
  is a different tool. GPU memory is an instantaneous gauge.
- **One correction to the wording.** NVML's GPU "load" is not a value at an instant. It is the
  percent of time a kernel ran over the device's last sample period, between 1/6 s and 1 s
  (NVML, nvmlUtilization_t). It is still a sample, not a span: our code does not bound it.
- **A GPU-side span is valid only when the call synchronizes.** GPU work is asynchronous to the
  CPU by default (PyTorch, CUDA semantics). SAM3's `detect` returns boxes on the CPU, so the span
  around it includes the kernels. A span around a call that only launches work would not.
- **The API is minimal.** One function, `RecordSample(kind, at, payload)`, in the same ring at the
  same cost. Samples are not events: a sample fits 100 bytes; an event needs up to 4 KB. Splitting
  the header per contract is not needed: recorder.h is 169 lines.
- **What is not minimal, and is harmful: SAMPLE_FREE_DISK.** It makes the writer a recording
  thread. With the cap at 16 that is the 17th thread, and Die mid-flight (R1-1). It also duplicates
  `m_freeGiB` and the health line's `free_gib`. Remove it; `SampleKind` keeps `SAMPLE_GPU`.
- **The internal cost of the fourth contract** is a tag, a union and one enum. A tagged union is
  the plain C shape for this, so it stays. Its layout is wrong (R1-3).
- **Carried, not the recorder's.** The desktop's GPU is an AMD RX 7900 GRE; pynvml reads NVIDIA
  only. The recorder is agnostic of the source, which is right. The screen module must pick the
  reader per vendor (unverified on the AMD desktop).

### 3. "WHY DO YOU USE SO MANY NAKED TYPES? YOUR RECORDER_INTERNAL IS HORRIBLE!"
**Verdict: partly holds.** The rewrite named most fields. These primitives remain:

| file:line | the primitive | justified? |
|---|---|---|
| recorder.h:51 | `uint64_t timeoutNs` | no. A duration with no type; `RecorderDuration` is missing |
| recorder.h:134-137 | four `uint32_t` counters | no. `RecordCount` exists but only in the internal header |
| recorder.h:140 | `float m_freeGiB` | yes. The unit is in the name; one display value |
| recorder.h:20-21 | `uint16_t m_width, m_height` | yes. Pixels inside the named `FrameSize` |
| recorder.h:34 | `uint32_t m_strideBytes` | weak. `ByteCount` is internal-only |
| recorder.h:35, internal:112 | `const uint8_t* m_pixels`, `uint8_t* m_bytes` | yes. Raw pixel memory |
| recorder.h:47-48, 97, 118, 124-125 | `const char*` texts | yes at a C boundary; but `topic` is a free string while the span stage is an enum (PRF1) |
| recorder.h:54 | `void* ctx` | yes. The DieActionFn signature (runtime.h:17) |
| internal:12 | `FileDescriptorType` = `int32_t` | the name: drop "Type"; POSIX uses `int` |
| internal:20, 24, 28, 32 | `char m_text[256]`, `[32]`, `[64]`, `[32]` | no. Four magic sizes; name them as k constants |
| internal:61 | `uint8_t m_pad[3]` | yes, padding; but the layout it pads is wrong (R1-3) |
| internal:70-71 | `uint16_t m_topicLength, m_keysLength` | no. Two naked lengths beside a named text |
| internal:150-151 | `_Atomic RecordCount m_queuedWrites, m_doneWrites` | the type says records; the field counts writes |

The aliases (`ThreadIndex`, `RingPosition`, `RecordCount`, `ByteCount`) carry meaning but give no
type safety: C typedefs mix silently. A one-member struct would cost the ring arithmetic its
readability. They are justified. Details in R1-10.

### 4. "Your code should be self explanatory."
**Verdict: partly holds.** With every comment covered, these do not read:
- `SPAN_COUNT` (recorder.h:83) reads as the enum's count, next to `SPAN_STAGE_COUNT`. It is the
  "count the objects" step.
- `const RecorderFrameConfig* frames` (recorder.h:49): nothing says NULL is allowed or what it means.
- `RecordSpan` returns void; `RecordEvent` and `RecordFrame` return `RecordResult`. The types do not
  say why.
- `RECORD_NOT_CREATED` serves two cases: never created, and no frame channel.
- `timeoutNs` (a duration, `uint64_t`) beside `deadlineNs` (a deadline, `RecorderTimestamp`).
- `kRecorderFreeCheckEvery = 100`: every 100 of what.
- `kRecorderExpectedPassesPerMinute`, `kRecorderFlightMinutes`, `kRecorderReserveMinutes`,
  `RECORDER_FRAME_RATIO`: nothing in the header shows they combine into the free-space rule.
- `WriterState` (internal:127-131) has no "not created" or "stopped" value. Its zero value is
  `WRITER_RUNNING`, so a zero-initialized instance reads as running before Create.
- `ThreadRings` (internal:101-105) has no thread name, yet the thread line writes one.
- The writer's own state is absent (R1-12): the drop counts already written, the threads already
  announced, the last drain and fsync times, the records since the last free check.
Details in R1-11 and R1-12.

## Findings

Counts: high 2, medium 5, low 11.

### R1-1. The 17th recording thread is designed in, and it dies mid-flight
- **Severity:** high. **Cause:** DESIGNED.
- **Where:** recorder.h:148 (`kRecorderMaxThreads = 16`); recorder.h:103-104 (`SAMPLE_FREE_DISK`,
  "by the writer"); recorder.md:118 ("the thread cap ... unchanged").
- **What is wrong.** Perf approved 32, twice the design's 16 (perf.h:49, perf.md:136, PRF5). The
  recorder set the cap to exactly 16 and calls it unchanged. The design's 16 recording threads are
  the main thread, the frame source, the recognizer, the platform worker, the emergency thread, two
  voices, eight job threads and the supervisor (perf.md:201-203). The writer records
  `SAMPLE_FREE_DISK`, so it is a 17th. Trace: start; the writer's first free check registers it;
  the eighth job thread's first span during a busy session registers the 17th; Die (RVW4) = the
  hand-over to the RC. Any thread a later module adds (the phone line listener, PHN5; Die's step
  thread if FlushInDie records its die event) dies the same way.
- **Smallest fix.** `kRecorderMaxThreads = 32`, the approved value. Delete `SAMPLE_FREE_DISK`. The
  writer never calls a Record function; it writes `free_gib` in its own health line.

### R1-2. A pool slot's single bool lets the writer encode a half-copied frame
- **Severity:** high. **Cause:** DESIGNED.
- **Where:** recorder_internal.h:116-125 (`_Atomic bool mb_inUse`); recorder.md:153-154.
- **What is wrong.** The job thread sets `mb_inUse` by test-and-set, then copies. The writer looks
  for slots in use and encodes them. One bool cannot tell "claimed, copy running" from "ready". The
  copy takes 0.05 to 0.18 ms at 720p (telemetry.md:163) and longer at 1080p. The writer polls every
  10 ms. Trace: every vision pass; the writer wakes during the copy; it encodes a mixed frame; the
  PNG is wrong with no error. The Python build has the same window: NumPy releases the GIL in
  low-level copies (NumPy, thread safety).
- **Smallest fix.** `typedef enum { POOL_FREE, POOL_FILLING, POOL_READY } PoolSlotState;` and
  `_Atomic PoolSlotState m_state`. The caller compares-and-swaps FREE to FILLING, copies, and stores
  READY with release order. The writer loads READY with acquire order, encodes, and stores FREE. One
  test: a writer stub that encodes during a slow copy never sees a FILLING slot.

### R1-3. TimingRecord is 136 bytes, not 128, and does not compile clean under -pedantic
- **Severity:** medium. **Cause:** DESIGNED (every span record; shown by a sizeof test).
- **Where:** recorder_internal.h:54-65; recorder.h:149 (`kRecordSpanBytes = 128`); recorder.md:21.
- **What is wrong.** `m_kind` 4 + `m_as` 4 + `m_thread` 1 + `m_pad` 3 = 12. The first timestamp
  needs 8-byte alignment, so it lands at 16. 16 + 8 + 8 + 100 = 132, rounded to 136. The approved
  128-byte record and every memory number built on it are off; a Python ring packed at a 128-byte
  stride no longer matches the C layout. Lines 56 and 59 carry stray semicolons (`union {;`,
  `m_as;;`), two -Wpedantic warnings.
- **Smallest fix.** Order the fields `m_start`, `m_end`, `m_kind`, `m_as`, `m_thread`, `m_pad[3]`,
  `m_payload`: offsets 0, 8, 16, 20, 24, 25, 28; total 128. Remove the two semicolons. Add
  `_Static_assert(sizeof(TimingRecord) == kRecordSpanBytes, "...")` and the same for EventRecord.

### R1-4. A new thread's rings are published without a ready flag, and the thread line has no home
- **Severity:** medium. **Cause:** DESIGNED.
- **Where:** recorder_internal.h:99-105, :142-143, :162; recorder.md:20.
- **What is wrong.** A thread claims an index by incrementing `m_threadCount`, then makes its rings
  ("made at the thread's first record"). The writer reads `m_threads[0 .. count)`. It can see the
  new count before `m_records` is set and read a NULL or half-set ring. Trace: a job thread's first
  span in a session while the writer drains; a NULL dereference in the writer is a crash of the app.
  Also, `ThreadRings` holds no name, and `RecorderWriteThreadLine` is listed under Create, not under
  the writer. If the recording thread writes that line, it writes the file and waits on the disk.
- **Smallest fix.** Add `ThreadName m_name` and `_Atomic bool mb_ready` to `ThreadRings`. The thread
  fills its rings and name, then stores `mb_ready` with release order. The writer skips an entry not
  ready, and writes the thread line itself. Optional and simpler still: make the rings at Create;
  untouched pages cost no resident memory.

### R1-5. Destroy and FlushInDie become a second consumer and a second writer of the file
- **Severity:** medium. **Cause:** DESIGNED.
- **Where:** recorder.h:51 ("drain, write, fsync, join"), :54; recorder.md:25, :152-153 (item 11).
- **What is wrong.** The rings are SPSC with the writer as the only consumer. Perf's drain lock is
  gone. If Destroy or FlushInDie drains on its own thread while the writer runs, two threads advance
  `m_tail` and write the file. Trace: a slow write puts the writer in the stall rule; die() mid-flight
  runs FlushInDie from Die's step thread; the writer wakes during that drain. Item 11 says a late
  record "is counted as dropped". It is not: a record that lands after the last drain sits in a ring
  nobody reads, and its count is never written.
- **Smallest fix.** Destroy and FlushInDie never touch a ring or the file. They store
  `WRITER_STOPPING`, wake the writer and join with the timeout. The writer does the last drain and
  the last fsync. The rings and pools are never freed (process lifetime). Item 11 then says: a
  record after the last drain is lost, not counted. A stuck writer at Destroy leaves its records in
  memory; the timeout returns anyway, as telemetry approved.

### R1-6. A short write on a full disk leaves a torn line in the middle of the file
- **Severity:** medium. **Cause:** SEEN (a full disk in a session, recorder.md:161).
- **Where:** recorder.md:132, :161, :163; telemetry.md:197.
- **What is wrong.** write(2): a write may transfer fewer bytes when the disk is short of space. The
  writer counts, pauses and resumes appending. The half line is now fused with the next line, in the
  middle of the file. The reader rule skips only a torn last line. A torn PNG from the same event
  stays on disk under its real name.
- **Smallest fix.** The writer keeps the offset of the last whole line. After a failed or short
  write it calls `ftruncate` to that offset before it resumes. It unlinks a PNG whose write failed.
  The reader skips and counts every unparsable line, not only the last. One test: a stub that
  returns a short write once.

### R1-7. A pass event names a PNG that was pooled, not written; the frame line is not in the contract
- **Severity:** medium. **Cause:** SEEN (the full disk, again).
- **Where:** recorder.md:26, :78, :138-146; telemetry.md:87.
- **What is wrong.** The helper writes `"png":"<name>.png"` when RecordFrame returns OK. OK means
  copied into the pool. If the later PNG write fails, the event still names the file. Section 2
  says the writer "writes the file and then its line", but that line kind is missing from the
  file format of item 7. The replayer has nothing that proves a PNG landed.
- **Smallest fix.** Add the line to the contract:
  `{"k":"frame","channel":"perception/0001-highlight","name":"000012","at":104530001,"ok":1}`,
  written after the PNG is complete. The replayer trusts frame lines; the event's `png` key stays as
  the request.

### R1-8. The file format misses four line kinds and keeps a pointer it does not own
- **Severity:** low. **Cause:** N/A (contract, gate item 7).
- **Where:** recorder.md:138-146; recorder.h:40-43; recorder_internal.h:145.
- **What is wrong.** The contract lists clock, thread, span, event, drop and health. A sample line,
  the frame line (R1-7), the info line (`m_infoJson`, telemetry's meta.json) and the die line have no
  form. The health line shows five keys; `RecorderHealth` has seven fields. The clock keys carry no
  unit (`mono` and `boot` are ns, `real` is us). `struct Recorder` stores `RecorderFrameConfig` by
  value, so it keeps `m_infoJson`, a pointer into the caller's memory.
- **Smallest fix.** Write every line kind as code in item 7, with the unit in each time key's name or
  in the clock line. Create writes the info line before it returns and stores no pointer.

### R1-9. The health block is read and written without atomics
- **Severity:** low. **Cause:** DESIGNED; the effect is a wrong display value for one frame.
- **Where:** recorder_internal.h:154; telemetry.md:202-203 (approved: atomic stores, one writer each).
- **What is wrong.** `RecorderHealth m_health` is a plain struct that the writer updates and the main
  thread reads each frame. In C that is a data race.
- **Smallest fix.** Hold each counter as `_Atomic` in the internal state; `RecorderReadHealth` loads
  each one into the caller's plain `RecorderHealth`.

### R1-10. The remaining naked types
- **Severity:** low. **Cause:** N/A (style, the owner's point 3).
- **Where:** the table under point 3.
- **Smallest fix.** `typedef uint64_t RecorderDuration;` for `timeoutNs` and the three `*_NS` macros.
  Move `RecordCount` into recorder.h and use it for the four health counters. Name the four text
  sizes (`kPathTextBytes = 256` and the others). `typedef uint16_t TextLength;` for the two event
  lengths. Rename `FileDescriptorType` to `FileDescriptor`, and `m_queuedWrites`/`m_doneWrites` to a
  `WriteCount` type.

### R1-11. Names that do not read without their comments
- **Severity:** low. **Cause:** N/A (clarity, the owner's point 4).
- **Where:** the list under point 4.
- **Smallest fix.** `SPAN_COUNT` to `SPAN_OBJECT_COUNT`. `kRecorderFreeCheckEvery` to
  `kRecorderFreeCheckEveryRecords`. `RECORDER_FRAME_RATIO` to `RECORDER_PNG_BYTES_PER_RAW_BYTE`.
  `RECORD_NO_FRAME_CHANNEL` beside `RECORD_NOT_CREATED`. A `RecorderState` enum whose zero value is
  `RECORDER_NOT_CREATED`, then `RUNNING`, `PAUSED`, `STOPPING`, `STOPPED`. `RecordEvent` returns void
  like `RecordSpan`: no caller uses its result; only `RecordFrame`'s result has a reader.

### R1-12. The writer's own state is missing from the visible struct, and the loop contradicts the document
- **Severity:** low. **Cause:** N/A (the house split: the mechanism as a visible struct).
- **Where:** recorder_internal.h:138-155, :164-171; recorder.md:25.
- **What is wrong.** The drop line needs the last count written per ring. The thread line needs the
  threads already announced. The 5 s drain and fsync need their last times. The free check needs a
  record count. R1-6 needs the last whole-line offset. None of these is in the struct. Line 164 says
  the drains run "every poll"; the document says every 5 s.
- **Smallest fix.** A `WriterProgress` struct, owned by the writer thread only, with those fields;
  the loop comment says which steps run every poll and which every 5 s.

### R1-13. The fold changes approved contracts while saying it does not
- **Severity:** low. **Cause:** N/A. Gate item 12: a change to an approved contract is an open point
  for the owner.
- **Where:** recorder.md:7-9, :118; recorder.h:90-92; recorder_internal.h:36.
- **What is wrong.** The payload shrank from 104 bytes (perf.h:47) to 100. recorder.h says "the
  payload is cut at the record"; perf approved "never cut: replaced by "cut":N and counted"
  (perf.md:224). The thread cap went from 32 to 16 (R1-1). The drain lock went (R1-5). The file names
  changed (perf-*.jsonl, trace.jsonl, meta.json to record-*.jsonl). The public `kRecordEventBytes`
  says 4096, but the topic and the keys share 4084 bytes.
- **Smallest fix.** Keep "replaced by cut:N". List each change as an open point for the owner, or
  revert it.

### R1-14. The public header carries the writer's knobs; the caller's limits are hidden
- **Severity:** low. **Cause:** N/A (decoupling; ruling TEL9 and TEL17).
- **Where:** recorder.h:147-167; recorder_internal.h:35-38.
- **What is wrong.** The poll periods, the idle time, the pool and ring counts and the record size are
  mechanism. The caller needs only the payload limit and the event-keys limit, and those are in the
  internal header. TEL17 rules the rates "config values"; here they are compile-time enum values.
- **Smallest fix.** Publish `kRecordPayloadBytes` and `kRecordEventKeysBytes`; move the rest to the
  internal header. Say that the rates and minutes are config values read at Create.

### R1-15. The multi-process rule is not checked by the kernel
- **Severity:** low. **Cause:** FORCED (two apps started in the same second).
- **Where:** recorder.md:33-38, :167; log/session.py:34, :66.
- **What is wrong.** The rule rests on naming. Today's folder name has one-second resolution and
  `exist_ok=True`. PHN7 removed "kill the old stack" from run.sh, so a second app is possible.
- **Smallest fix (the generic start-up check, no new mechanism).** The app makes the session folder
  with a mkdir that fails on EEXIST. Create opens the record file with `O_CREAT|O_EXCL|O_APPEND`.
  Either failure makes Create return false, and the start dies. The matrix row "two processes write
  one file" then names these two checks.

### R1-16. The SIGKILL and power-cut row is merged and wrong for a power cut
- **Severity:** low. **Cause:** FORCED.
- **Where:** recorder.md:163; telemetry.md:248-249 (the approved rows).
- **What is wrong.** "PNGs on disk stay" holds for SIGKILL, which keeps the page cache. A power cut
  loses up to about 35 s of PNGs, never fsynced, and can lose a new file's directory entry
  (fsync(2)). SIGKILL also loses the pools: up to 8 frames and 24 masks whose events may already
  name them.
- **Smallest fix.** Split the row back into telemetry's two rows. No mechanism.

### R1-17. Three cause labels in the failure matrix are not supported
- **Severity:** low. **Cause:** N/A (gate item 12).
- **Where:** recorder.md:162, :164, :165.
- **What is wrong.** "A full pool: SEEN (3 passes a second)": no session shows it. Telemetry says no
  flight sustains 3 a second (telemetry.md:120-121); at that rate the writer is 27 % busy at 1080p.
  "A full span ring: DESIGNED (a burst over 4096 in 5 s)" names no flight trigger. "A 5 s stall:
  DESIGNED (a slow disk)" names no trace. The fsync-after-a-writeback-error case (LWN) is missing.
- **Smallest fix.** Label the drop-and-count and stall rows as rulings (TEL7, PRF, the telemetry
  stall rule); they stand on the owner's authority. Add the fsync error as FORCED with the generic
  handling: counted, degraded.

### R1-18. The drawing cannot pass gate item 10
- **Severity:** low. **Cause:** N/A.
- **Where:** recorder.html (an embedded PNG); recorder.md:151 ("no drawing").
- **What is wrong.** `svg_text_check.py` cannot read text in a PNG. So "the document, the headers and
  the drawing agree" is not checkable. Item 10 says there is no drawing; there is one.
- **Smallest fix.** Item 10 names the drawing and how it was checked. If the source is an SVG, keep
  it inline so the checker can run.

## What is right
- The ambient instance with no handle (PRF7) and one file per process (RVW6, RVW7).
- Two rings per thread: 512 KiB of spans plus 1 MiB of events, against 16 MiB for one shared slot
  size (recorder.md:176-178).
- Drop-new and count, no wait on the recording path; a full pool returns at once.
- One writer thread: one fsync, one file handle; a 40 to 90 ms PNG delays only the next PNG, and the
  rings cover a 5 s drain.
- Power-of-two ring capacities with a free-running unsigned position: `head - tail` stays correct
  across the 2^32 wrap.
- The frame copy during the call while the job holds its slot (RVW3).
- The fold itself: one service, one clock line, one reader; the nine helper headers merge into one
  `record_<owner>.h` per owner.
- `FrameSize` and `FrameView` as structs; RecordFrame takes one pointer (RCD2).

## Sources
- fsync(2), Linux man page: https://man7.org/linux/man-pages/man2/fsync.2.html
- write(2), Linux man page (partial writes): https://man7.org/linux/man-pages/man2/write.2.html
- open(2), Linux man page (O_EXCL): https://man7.org/linux/man-pages/man2/open.2.html
- LWN, "PostgreSQL's fsync() surprise": https://lwn.net/Articles/752063/
- NVML, nvmlUtilization_t: https://docs.nvidia.com/deploy/nvml-api/structnvmlUtilization__t.html
- PyTorch, CUDA semantics, asynchronous execution: https://docs.pytorch.org/docs/stable/notes/cuda.html
- NumPy, thread safety: https://numpy.org/doc/stable/reference/thread_safety.html

## Round 1: answer (the manager, 2026-10-18)
Every finding judged on its cause, then applied or narrowed. Counts: accepted 16, narrowed 2, rejected 0.
The owner's four points, as the review judged them, now hold: the file rule is checked by the kernel (O_EXCL, a mkdir that fails on EEXIST, carried to the app step); the sample contract is one function and the writer never records; the internal header has no unnamed primitive left except pixel bytes, padding and the C string boundary; the names read without comments (SPAN_OBJECT_COUNT, RECORD_NO_FRAME_CHANNEL, RecorderDuration, RecorderState with NOT_CREATED as zero).
| finding | cause | answer |
|---|---|---|
| R1-1 | DESIGNED | accepted: the cap is 32 (PRF5); SAMPLE_FREE_DISK deleted; the writer never records |
| R1-2 | DESIGNED | accepted: PoolSlotState FREE, FILLING, READY with a compare-and-swap and a release store |
| R1-3 | DESIGNED | accepted: the timestamps first, byte-sized kind, stage and thread, a 104-byte payload; two static_asserts; 128 and 4096 measured |
| R1-4 | DESIGNED | accepted: ThreadName and mb_ready on ThreadRings; the writer announces threads; the rings stay lazy (the approved rule), the flag closes the window |
| R1-5 | DESIGNED | accepted: Destroy and FlushInDie set STOPPING, wake, join; the writer alone drains; a late record is lost, not counted; listed as a change against perf |
| R1-6 | SEEN | accepted: ftruncate to the last whole line, unlink a half PNG; the reader skips every unparsable line |
| R1-7 | SEEN | accepted: the frame line after the PNG; the event's png key is the request |
| R1-8 | N/A | accepted: every line kind in the contract with units; the info line at Create; no pointer kept |
| R1-9 | DESIGNED | accepted: the health counters are atomics in the instance; ReadHealth loads them |
| R1-10 | N/A | accepted: RecorderDuration, RecordCount public, named text sizes, TextLength, FileDescriptor, WriteCount |
| R1-11 | N/A | narrowed: every rename taken, RecordEvent returns void, RecorderState added; RecordFrame keeps its result, as the review says |
| R1-12 | N/A | accepted: WriterProgress; the loop comment names what runs every poll and what every 5 s |
| R1-13 | N/A | accepted: the payload is 104 again with {"cut":N}; the cap 32; every remaining change listed in recorder.md section 4 for the owner |
| R1-14 | N/A | narrowed: the knobs moved to the internal header; the caller sees four limits; the rates stay as C defaults with the note that config holds the values (TEL17) |
| R1-15 | FORCED | accepted as a start-up check, no mechanism: O_CREAT, O_EXCL, O_APPEND; the mkdir rule carried to the app |
| R1-16 | FORCED | accepted: the two rows split; no mechanism |
| R1-17 | N/A | accepted: the drop and stall rows stand on rulings; the fsync-after-error row added as FORCED |
| R1-18 | N/A | narrowed: the PNG page stays (the owner chose it); gate item 10 names the drawing and the graphviz checks that ran |

## Conclusions
- Agreed: all of the above. Open: none for the reviewer; the owner reads the seven changes against the approved contracts in recorder.md section 4.
- Changed: recorder.h, recorder_internal.h (rewritten; -Wextra -pedantic clean; sizes pinned), recorder.md sections 2, 4, 7, 8, 9.
- Added by the review, each with its cause: PoolSlotState (DESIGNED), mb_ready and ThreadName (DESIGNED), WriterProgress (the house split), the frame line (SEEN), ftruncate after a short write (SEEN), the O_EXCL open (a start-up check), RecorderState (clarity). No thread, callback or restart path was added.
- Carried: the app makes the session folder with a mkdir that fails on EEXIST; the screen picks the GPU reader per vendor; the frame buffer drops its FrameSize copy at the fold.


## Round 2: reviewer (2026-10-18)

Reviewed: `modules/01-recorder/recorder.md` (DRAFT 4), `frame_types.h`, `recorder.h`, `record_span.h`,
`record_event.h`, `record_frame.h`, `recorder_internal.h`. Round 1 and its answer are above; this
round tests what changed. Inherited numbers: `01-perf/perf.md`, `02-telemetry/telemetry.md`.
The Die sequence: `03-runtime/runtime.h`, `runtime_internal.h`. Every mechanism added since round 1
was re-checked for its cause first (gate item 12): PoolSlotState (R1-2, DESIGNED), mb_ready (R1-4,
DESIGNED), the frame line and ftruncate (SEEN), O_EXCL (a start-up check), RecorderState (clarity),
the wake-up object (the owner, RCD6), one RingBuffer (the owner), m_pendingSince (the stall ruling).
Each cause holds. The findings below are against how the mechanisms are built, not against their need.

Measured facts used below (this machine: gcc 13.3.0, x86-64, 32 logical cores, CPython 3.12.3 with
the GIL on, `sys._is_gil_enabled()` True). Scripts in the session scratchpad, not in the repo.

| fact | value | how |
|---|---|---|
| the six headers | all clean under -Wall -Wextra -pedantic -std=c11 | gcc -fsyntax-only, one by one |
| sizeof(struct Recorder) | 648 bytes, as claimed | gcc sizeof |
| offsetof m_threads; the byte after it | 304; 560 is `m_frameSize` | gcc offsetof |
| sizeof ThreadRings, RingBuffer, PoolSlot | 112, 32, 120 bytes | gcc sizeof |
| SpanRecord, EventRecord | 128, 4096 bytes (the static_asserts hold) | gcc sizeof |
| RingBuffer: m_head, m_tail | offsets 0 and 4: one cache line | gcc offsetof |
| `_Atomic float`, pointers, 64-bit | lock-free on x86-64 | atomic_is_lock_free |
| C push of a 128-byte record (acquire tail, release head) | 7.4 ns | gcc -O2, 2 M pushes, best of 5 |
| C push of a 4096-byte record | 118 ns | same |
| first write to a fresh 4 KiB page of a malloc'd ring | 1244 ns per page | gcc -O2, 256 pages |
| Python span push: two monotonic_ns, encode, pack_into | 437 ns | timeit, a class over a bytearray |
| Python event push (4096-byte record) | 451 ns | same |
| Python span pop, event pop (unpack_from) | 212 ns, 259 ns | same |
| Python Event.set() with the flag already set | 414 ns | timeit |
| Python Event.set() with a waiter | median 1763 ns, p99 7684 ns | 2000 sets, a waiting thread |
| Python scan of 32 slot states | 301 ns | timeit |
| Python check-then-set claim, two threads at once | 0 double claims in 2 x 20,000, switch interval 5 ms and 1 us | barrier-synchronized test |
| a ring of capacity 1000, 1000 live positions across the 2^32 wrap | 705 distinct slots: 295 records overwritten | arithmetic |
| the span ring's wrap at 40 records a second | 3.4 years | arithmetic |
| OsEvent in rev5 | declared only in recorder_internal.h:19; runtime_internal.h declares OsThread (line 76), not OsEvent | grep over rev5 |

### The owner's demands

#### 1. The types are grouped, one header per logical group
**Verdict: holds.**
- **Evidence.** `frame_types.h` holds the frame types shared by three modules. `recorder.h` holds
  the clock, the lifetime and the health. Each contract has its own header. The mechanism is in
  `recorder_internal.h`. Each header compiles alone, clean under -pedantic.
- **One nit.** `record_frame.h` includes `frame_types.h` and `recorder.h`; the second already
  includes the first. Harmless.

#### 2. One RingBuffer type
**Verdict: holds, with two gaps.**
- **Evidence.** One struct (recorder_internal.h:116-123), two functions (:125-126), used twice in
  `ThreadRings` (:138-139). Nothing in Push or Pop allocates or locks. C cost: 7.4 ns for a span,
  118 ns for an event. Python cost: 437 ns for a span push with its two clock reads, inside the
  approved 1 us.
- **Gap 1.** The memory orders and the power-of-two capacity are not stated (R2-7).
- **Gap 2.** Pop advances the tail before the line is on disk (R2-8).

#### 3. No writer bookkeeping in the instance (648 bytes measured)
**Verdict: partly holds.**
- **What holds.** 648 bytes, measured. The thread table is 32 pointers (256 bytes). The timer and
  the step counters are locals of `RecorderWriterRun`.
- **What is still writer bookkeeping in shared state.** `RECORDER_PAUSED` in `m_state` (:185) is the
  writer's pause, written into the state that every record call reads (R2-3). `m_pendingSince`
  (:212) has several writers and no rule (R2-4). `mb_announced` (:141) is writer-owned inside a
  struct the recording thread allocates; that is acceptable, but only the comment says so.
- **What is missing, and is not bookkeeping.** The stop request from Die: its reason and its
  deadline have no field (R2-5).

#### 4. The many writer functions cut to four
**Verdict: holds by count; the order moved into a comment.**
- **Evidence.** `RecorderWriteWholeLine`, `RecorderFileName`, `RecorderWriteHeaderLines`,
  `RecorderWriterRun` (:224-240). Two of the four are Create's, not the writer's.
- **Cost.** The writer's six steps now exist only as one run-on comment (:231-239). The house split
  asks for "a visible struct and an ordered list of functions". This is a tension between two
  owner rulings, not a defect: see R2-16.

#### 5. Naked primitives left
| file:line | the primitive | justified? |
|---|---|---|
| frame_types.h:10-11 | `uint16_t m_width, m_height` | yes. Pixels inside the named FrameSize |
| frame_types.h:23 | `uint32_t m_strideBytes` | yes. The unit is in the name |
| frame_types.h:24, internal:122, :167 | `const uint8_t* m_pixels`, `uint8_t* m_records`, `uint8_t* m_pixels` | yes. Raw bytes |
| recorder.h:26, :34-35, :42 | `const char*` | yes. The C string boundary |
| recorder.h:42 | `void* ctx` | yes. The DieActionFn signature |
| recorder.h:54, internal:219 | `float m_freeGiB` | yes. The unit is in the name |
| internal:49 | `typedef int FileDescriptor` | yes. POSIX uses int |
| internal:87 | `kRecordEventBytes - 12` | no. A magic 12: the size of `m_at` plus two lengths (R2-14) |
| internal:97 | `uint8_t m_pad[6]` | yes. Padding, pinned by the static_assert |
| internal:96, :136 | `ThreadIndex m_thread`, `ThreadIndex m_index` | named, but not needed (R2-14) |

#### 6. Does recorder_internal.h read without its comments?
**Verdict: partly.** The structs read. These do not:
- The writer's order of work (:231-239) exists only in a comment.
- `m_pendingSince`: "the oldest READY slot's publish time, 0 if none" is only in the comment, and no
  slot stores a publish time.
- `mb_announced`: that it is the writer's is only in the comment.
- `RingBufferPush` returning false: that the record is dropped and counted is only in the comment.

### The six test points, answered

| point | answer | finding |
|---|---|---|
| 1. the generic ring | correct as an SPSC ring if Push loads the tail with acquire and stores the head with release, and Pop the reverse; full = `head - tail == capacity`, empty = `head == tail`, both right across the 2^32 wrap only for a power-of-two capacity; nothing allocates or locks | R2-7, R2-8 |
| 2. the wake-up | correct only for a sticky event (threading.Event semantics) and the order wait, clear, read the state, scan; OsEvent has no home and no stated semantics; the frame burst fits; the stall rule cannot be computed as written | R2-4, R2-5, R2-6 |
| 3. the pools | the C compare-and-swap closes two claims at once; Python has no compare-and-swap; a slot stuck in FILLING is FORCED in C; the scan is 32 loads (301 ns in Python) | R2-11, R2-12 |
| 4. the thread table | a plain pointer store before mb_ready is not safe: mb_ready lives inside the pointee, so the writer reads a NULL or racing pointer first; the 33rd thread makes the writer read past the table; an exited thread's rings are never freed, which is right (FORCED, and the writer still drains its last records) | R2-1, R2-2 |
| 5. the owner's demands | above | R2-3, R2-14, R2-16 |
| 6. the file | correct: see below | none |

**The file, point 6.** ftruncate on an O_APPEND descriptor is correct, and O_APPEND is what makes it
work without an lseek.
- ftruncate needs only a descriptor open for writing: "With ftruncate(), the file must be open for
  writing" (truncate(2)). O_APPEND does not change that.
- After a short write of n bytes, the offset is the old end plus n: "the file offset is incremented
  by the number of bytes actually written" (write(2)).
- ftruncate does not move it back: "The file offset is not changed" (truncate(2)).
- The next write still lands at the new end: "Before each write(2), the file offset is positioned at
  the end of the file" (open(2), O_APPEND). Without O_APPEND the next write would leave a hole of
  zero bytes between the truncated end and the old offset.
- The writer needs the byte count of the last whole line as a local: the header lines' size plus
  every whole write. Shrinking a file needs no free space, so the truncate works on a full disk.
- O_CREAT|O_EXCL fails with EEXIST when the name exists (open(2)): the second-instance check holds.

### Findings

Counts: high 0, medium 6, low 10.

#### R2-1. The 33rd thread makes the writer read past the thread table, and crash inside Die
- **Severity:** medium. **Cause:** DESIGNED (the matrix row "a 33rd recording thread", recorder.md:212).
- **Where:** recorder_internal.h:205-206.
- **What is wrong.** A thread takes its index by incrementing `m_threadCount`. The 33rd gets 32 and
  calls Die. The count now reads 33. Die's step 3 wakes the writer for its last pass. The writer
  walks `m_threads[0 .. 33)`. `m_threads[32]` is offset 560: the bytes of `m_frameSize` and the
  start of `m_frames`, read as a pointer (measured offsets). The dereference faults. The aircraft is
  safe, since the hand-over is step 1. The records that explain the bug are lost.
- **Smallest fix.** The writer walks `min(count, kRecorderMaxThreads)`. One test: a 33rd thread's
  record, then the writer's pass, reads 32 entries.

#### R2-2. The thread table publishes its pointer without an atomic, so mb_ready cannot be reached safely
- **Severity:** medium. **Cause:** DESIGNED (R1-4's trace: a job thread's first record while the writer drains).
- **Where:** recorder_internal.h:128-142, :206.
- **What is wrong.** `mb_ready` lives inside the `ThreadRings` that the pointer points to. The writer
  must read `m_threads[i]` before it can read `mb_ready`. That pointer is a plain array element.
  The new thread increments the count, allocates 1.5 MiB, fills it, then stores the pointer. In that
  window the writer reads count k+1 and a NULL `m_threads[k]`; its read of `mb_ready` is a NULL
  dereference. That is round 1's crash, back. A plain read racing a plain store is also a data
  race in C11, which is undefined behavior (cppreference, memory model).
- **Smallest fix.** `ThreadRings* _Atomic m_threads[kRecorderMaxThreads];`. The thread stores the
  pointer last, with release order. The writer loads it with acquire order and skips NULL. Delete
  `mb_ready`: NULL means not ready. In Python, `list.append` of the rings object is atomic under the
  GIL (Python FAQ), and the writer reads the list.

#### R2-3. RECORDER_PAUSED makes a disk pause discard every record, uncounted, and can overwrite a stop
- **Severity:** medium. **Cause:** SEEN (a full disk in a session, recorder.md:203).
- **Where:** recorder_internal.h:182-188, :222-223; recorder.md:191-192 (item 11), :203.
- **What is wrong.** A failed write pauses the writer. Item 11 says a record call records only when
  the state is RUNNING, "anything else returns at once". So during a disk pause every span, event
  and frame returns at once and is never counted. The matrix says "pause, count, resume". Telemetry
  approved that records still enter the rings during a pause (telemetry.h, `m_degraded`). Second
  defect: the state now has three writers. The writer stores RUNNING when it resumes. Destroy or
  Die may have stored STOPPING just before. The plain store overwrites it, the writer never takes
  its last pass, and Destroy and Die wait out their timeouts.
- **Smallest fix.** Delete `RECORDER_PAUSED`. The pause is a local of the writer, shown by
  `mb_degraded`. `m_state` then has one writer per transition: Create stores RUNNING, Destroy and
  FlushInDie store STOPPING, the writer stores STOPPED after it saw STOPPING. One test: a failed
  write, then 10 spans, then a recovered disk: the 10 spans are in the file.

#### R2-4. The stall rule cannot be computed as designed
- **Severity:** medium. **Cause:** the telemetry stall rule (the owner's ruling) is the requirement;
  the trace through our design is DESIGNED: a write or an encode that blocks for 5 s.
- **Where:** recorder_internal.h:197-198, :212, :217, :237-238; recorder.md:204.
- **What is wrong.**
  - The writer sets `mb_stalled` in its own step 6. A writer blocked in write, fsync or the encode
    never reaches step 6. So the flag is false for the whole stall and true only after it ends.
    Telemetry approved the stall as computed at read, by the main thread, from atomic values.
  - `m_pendingSince` has writers on both sides: each job thread on publish, the writer on free. No
    rule is stated. The writer cannot recompute "the oldest READY slot's publish time": no slot
    stores its publish time (`m_at` is the capture time). A job's store and the writer's store of
    0 race; the loser's value is lost.
  - Records in the rings never count as pending. If they did, `RECORDER_STALL_NS` equals
    `RECORDER_DRAIN_EVERY_NS`, so every timer drain would sit at the edge of a stall.
- **Smallest fix.** Add `RecorderTimestamp m_publishedAt` to `PoolSlot`, stored before the READY
  release store. Add `_Atomic RecorderTimestamp m_lastProgressAt`, stored by the writer after each
  finished PNG or line batch. Delete `m_pendingSince`. `RecorderReadHealth` computes stalled: a
  READY slot exists, and now is past the later of the oldest `m_publishedAt` and `m_lastProgressAt`
  plus `RECORDER_STALL_NS`. The scan is 32 loads; 301 ns in Python, once a frame. Delete
  `mb_stalled` from the instance. Say in the matrix that the stall rule covers frames only, since
  spans and events wait for the timer by design.

#### R2-5. Die's reason and deadline have no home, so the die line has no writer
- **Severity:** medium. **Cause:** DESIGNED (any die() mid-flight; the die line is in the contract, recorder.md:177).
- **Where:** recorder.h:42; recorder_internal.h:200-220, :231-239; recorder.md:30.
- **What is wrong.** `RecorderFlushInDie(ctx, reason, deadlineNs)` only stores STOPPING and wakes the
  writer. The instance has no field for the reason or the deadline. So the writer cannot write the
  die line. If FlushInDie writes it, the file has two writers again (R1-5). The writer also cannot
  stop encoding PNGs at the deadline. And step 5 fsyncs "every 5 s", so the last pass may skip the
  fsync. The process exits right after Die, so the page cache keeps the lines; only a power cut
  needs the fsync.
- **Smallest fix.** Add a named `DieReasonText m_dieReason` and `_Atomic RecorderTimestamp
  m_stopDeadline`. FlushInDie fills both, then stores STOPPING with release order. The last pass,
  in this order: the rings, the die line, the health line, the fsync, then the PNGs while the clock
  is before the deadline.

#### R2-6. OsEvent has no home and no semantics, and the lost wake-up depends on them
- **Severity:** medium. **Cause:** DESIGNED (die() while the writer encodes a PNG; the writer is 16 %
  busy at 720p and 31 % at 1080p at 3 passes a second, telemetry.md section 6).
- **Where:** recorder_internal.h:16-19, :211, :231; recorder.md:26-27, :184.
- **What is wrong.** The header says OsEvent is in runtime_internal.h. It is not: that file declares
  OsThread only. The race closes only if the event is sticky: a set with no waiter must stay set
  until the writer clears it. A condition variable does not do that: "pthread_cond_signal() ...
  shall have no effect if ... there are no threads blocked on cond" (POSIX). The trace: the writer
  checks the state, then encodes; Die stores STOPPING and wakes; the writer waits; the wake is gone.
  It sleeps up to 5 s, Die's 5 s flush cap ends, and the last records are lost. A lost frame wake
  is harmless: the next publish or the timer wakes the writer. Python's `threading.Event` is
  sticky: "Threads that call wait() once the flag is true will not block at all" (Python docs). It
  is safe only in this order: wait, clear, read the state, then scan. A clear after the scan loses
  a wake that came during the scan.
- **Smallest fix.** Give OsEvent its home in runtime_internal.h, with Event semantics: a sticky flag,
  set, clear, and a timed wait on CLOCK_MONOTONIC. In C, an eventfd or a futex word does this. State
  the writer's order in recorder_internal.h: wait, clear, read the state, drain, scan. One test: a
  stop stored between the writer's state check and its wait ends the writer at once, not after 5 s.

#### R2-7. The ring's memory orders are not stated, and the capacity is not pinned to a power of two
- **Severity:** low. **Cause:** N/A for the orders (clarity). FORCED for the wrap: 3.4 years at 40 a second.
- **Where:** recorder_internal.h:52, :113-126.
- **What is wrong.** The header names no order for `m_head` and `m_tail`. Plain `_Atomic` operations
  default to sequentially consistent. That is correct but hides the design. The rule "the slot is the
  position modulo the capacity" works across the 2^32 wrap only for a power-of-two capacity. With
  1000, 1000 live positions across the wrap fall into 705 slots (measured). Today's 4096 and 256 are
  powers of two, but the generic type takes any `m_capacity`.
- **Smallest fix.** One line in the ring's comment: Push loads the tail with acquire and stores the
  head with release; Pop loads the head with acquire and stores the tail with release; the drop count
  is a relaxed store by the producer alone. A check at Create that the capacity is a power of two,
  and the slot as `position & (capacity - 1)`. In Python, positions are ints that never wrap; the
  class must not emulate a 32-bit wrap.

#### R2-8. Pop advances the tail before the line is on disk
- **Severity:** low. **Cause:** SEEN (the full disk).
- **Where:** recorder_internal.h:126, :222-223.
- **What is wrong.** The writer pops a record, then writes its line. If the write fails, the record
  has left the ring. "The next wake retries" does not say what it retries.
- **Smallest fix.** The writer keeps its one formatted line, a local, until it is written, and pops
  nothing while paused. The rings then fill and drop-new and count, as ruled.

#### R2-9. A second Create in the same process finds the old instance's rings
- **Severity:** low. **Cause:** DESIGNED (test_recorder.py creates several instances in one process, recorder.md:236).
- **Where:** recorder.h:33-39; recorder_internal.h:128-130.
- **What is wrong.** The thread-local pointer to a thread's rings survives Destroy. A Destroy that
  timed out leaves the old writer running. Nothing says whether Create accepts STOPPED, or what
  happens to the table and the thread-local pointers.
- **Smallest fix.** Create returns false unless the state is NOT_CREATED or STOPPED. The thread table
  and the thread-local pointers survive; the new writer reads the same rings.

#### R2-10. Destroy and FlushInDie both join the writer, and Die on the writer joins itself
- **Severity:** low. **Cause:** FORCED (no designed path calls Die during Destroy or on the writer).
- **Where:** recorder.h:38-42; recorder.md:30.
- **What is wrong.** Die during Destroy makes two threads join the writer: "If multiple threads
  simultaneously try to join with the same thread, the results are undefined" (pthread_join(3)).
  Die on the writer joins itself: EDEADLK in C, a RuntimeError in Python, which leaves the module.
  Telemetry approved the writer case (`test_flush_in_die_on_the_writer_appends_once`).
- **Smallest fix (generic, no mechanism).** The writer sets a second OsEvent, "stopped", at its end.
  Destroy and FlushInDie wait on it with their timeout and never join. On the writer's own thread,
  FlushInDie returns at once.

#### R2-11. The Python mapping names a compare-and-swap that Python does not have
- **Severity:** low. **Cause:** N/A (the mapping; the build today is CPython 3.12 with the GIL).
- **Where:** recorder.md:184 ("an atomic state each"), :193; recorder_internal.h:149.
- **What is wrong.** Python has no compare-and-swap. A check-then-set of a list element gave 0 double
  claims in 40,000 simultaneous claims (measured). That rests on where CPython 3.12 checks for a
  thread switch, not on a guarantee. The Python FAQ lists `L[i] = L[j]` and `i = i+1` as not atomic
  and says "When in doubt, use a mutex". A free-threaded build (PEP 703) removes even that. The
  FILLING state is real in Python: NumPy releases the GIL during a large copy.
- **Smallest fix.** In Python, PoolClaim takes a free index with `collections.deque.popleft()`, the
  approved telemetry mapping. The slot state stays, for the writer's READY test. The counters that
  several threads increment get the same treatment, or the writer sums them (R2-16).

#### R2-12. A slot left in FILLING is never freed
- **Severity:** low. **Cause:** FORCED in C (no thread dies alone; a fault kills the process).
- **Where:** recorder_internal.h:148-150, :175-177.
- **What is wrong.** In Python, an exception between Claim and Publish leaves the slot FILLING
  forever. A stride the copy does not handle is one way. Eight such calls and the pool drops every frame.
- **Smallest fix (generic).** Check the size, the format and the stride before Claim
  (RECORD_INVALID_ARG). The guarded copy stores FREE on failure. One test: a bad stride returns
  INVALID_ARG and all 8 slots stay free.

#### R2-13. "No allocation" is false for a thread's first record
- **Severity:** low. **Cause:** N/A (clarity).
- **Where:** record_span.h:38-40; recorder_internal.h:128-129; recorder.md:225.
- **What is wrong.** The first record of a thread allocates 1.5 MiB. Each first write to a page of
  the rings then costs a page fault: 1244 ns per page, measured. Every one of a thread's first 256
  events touches a new page. The main thread pays about 1.2 us extra per event for its first two
  minutes. That fits the 330 us budget. A failed allocation has no stated result.
- **Smallest fix.** record_span.h says "the first record of a thread makes its rings". A failed
  allocation leaves the thread without rings; its records are dropped and counted as dropped spans.

#### R2-14. A magic number and two fields that nothing needs
- **Severity:** low. **Cause:** N/A (style, YAGNI).
- **Where:** recorder_internal.h:87, :96, :136.
- **What is wrong.** `kRecordEventBytes - 12`: the 12 is `m_at` plus two lengths. `SpanRecord.m_thread`
  repeats what the writer knows from the ring; `EventRecord` has no such field, which shows it is not
  needed. `ThreadRings.m_index` repeats the table position.
- **Smallest fix.** `kRecordEventBytes - sizeof(RecorderTimestamp) - 2 * sizeof(TextLength)`. Delete
  `m_thread` (the pad becomes 7 bytes) and `m_index`.

#### R2-15. Three changes against approved contracts are not in the list for the owner
- **Severity:** low. **Cause:** N/A (gate item 12: a change to an approved contract is an open point).
- **Where:** recorder.md:108-121; recorder_internal.h:32, :222-224.
- **What is wrong.**
  - Perf approved one write and one fsync per drain (perf.md section 7). The recorder writes one
    line per write. It is cheap at 250 lines per 5 s, and it makes the ftruncate simple, but it is a
    change.
  - Telemetry approved FlushInDie on the writer's own thread (R2-10). The recorder drops it.
  - Telemetry approved the mask pool as the frame pool times the perception's mask limit
    (telemetry.h:77). The recorder fixes it at 24.
- **Smallest fix.** Three rows in recorder.md section 4. The mask pool as `kRecordPoolFrames` times
  the mask limit from config.

#### R2-16. The writer's order and the counters' owners read only from comments
- **Severity:** low. **Cause:** N/A (clarity; the house split).
- **Where:** recorder_internal.h:119, :175-176, :213-216, :231-239.
- **What is wrong.** The six steps are one paragraph with inline numbers. Nothing says when the health
  line is written. Each ring has `m_dropped`, and the instance has its own drop totals; nothing says
  who adds to the totals. If every recording thread does, that is a shared read-modify-write; in
  Python, `+=` is not atomic (Python FAQ). `PoolClaim(Pool*)` counts a drop but cannot reach the
  instance; `PoolPublish` takes the instance.
- **Smallest fix.** One step per line in the comment. The writer sums the rings' `m_dropped` into the
  instance's totals on each wake. The health line goes once per fsync. `PoolClaim` takes
  `struct Recorder*` like `PoolPublish`. Whether the six steps become named functions again is for
  the owner, against his "cut to four".

### What is right
- One ring type for two record sizes, at 7.4 ns and 118 ns in C and about 440 ns in Python.
- Spans and events do not wake the writer. A wake costs 1.8 us in Python, about four spans' worth.
- A frame wakes the writer. At 3 passes a second with 3 masks, the writer needs 54 ms a pass at 720p
  and 103 ms at 1080p. Frames arrive slower than the writer clears them, so the pools hold one or
  two. 8 frames and 24 masks hold 2.7 s of a full stall, then drop and count, as ruled.
- The pool's three states and the compare-and-swap in C close two claims at once and the half-copied
  frame.
- The writer alone drains and writes. Destroy and Die only ask (R1-5 holds).
- An exited thread's rings stay. The writer still drains its last records, and the threads are
  made once at start, so nothing leaks over a session.
- ftruncate with O_APPEND, and the O_EXCL open (point 6).
- 648 bytes, the record sizes pinned by static_assert, all six headers clean under -pedantic.

### The three lenses
- **Storage and hardware.** One write per line is about 250 syscalls a drain; a write returns in
  under 1 ms (telemetry.md section 6). `m_head` and `m_tail` share a cache line. The producer and the
  consumer each invalidate it, but at 40 records a second that costs nothing; no padding (YAGNI).
  A power cut and fsync after a writeback error stay FORCED rows, as answered in round 1.
- **Concurrency and real time; the GIL.** None of the C11 atomics exist in Python. The GIL makes a
  single load or store of an attribute or a list element atomic, and orders them: the head store
  after `pack_into` is seen after the bytes, since `pack_into` holds the GIL. The GIL is released in
  the NumPy copy, `cv2.imencode`, `os.write`, `os.fsync` and `Event.wait`, so FILLING and READY are
  real in Python. A compare-and-swap and a shared `+=` are not (R2-11, R2-16). The main thread's cost
  is 40 spans a second at 437 ns: 18 us a second, well inside 330 us a frame.
- **YAGNI and decoupling.** Delete `RECORDER_PAUSED` (R2-3), `mb_ready` (R2-2), `m_pendingSince` and
  `mb_stalled` (R2-4), `SpanRecord.m_thread` and `ThreadRings.m_index` (R2-14). Add only what Die needs
  (R2-5) and one progress time (R2-4). The six headers stay six.

### Sources
- truncate(2) and ftruncate, Linux man page: https://man7.org/linux/man-pages/man2/ftruncate.2.html
- write(2), Linux man page: https://man7.org/linux/man-pages/man2/write.2.html
- open(2), Linux man page (O_APPEND, O_EXCL): https://man7.org/linux/man-pages/man2/open.2.html
- pthread_cond_signal, POSIX.1-2024: https://pubs.opengroup.org/onlinepubs/9799919799/functions/pthread_cond_signal.html
- pthread_join(3), Linux man page: https://man7.org/linux/man-pages/man3/pthread_join.3.html
- C memory model, data races: https://en.cppreference.com/w/c/language/memory_model
- Python FAQ, thread-safe mutation: https://docs.python.org/3/faq/library.html#what-kinds-of-global-value-mutation-are-thread-safe
- Python threading, Event objects: https://docs.python.org/3/library/threading.html#event-objects
- PEP 703, making the GIL optional: https://peps.python.org/pep-0703/
- NumPy, thread safety (the GIL released in copies; cited in round 1): https://numpy.org/doc/stable/reference/thread_safety.html

## Round 2: answer (the manager, 2026-10-18)
Every finding judged on its cause and applied. Counts: accepted 16, narrowed 0, rejected 0. Every mechanism the round added was checked for its cause first; each holds.
| finding | cause | answer |
|---|---|---|
| R2-1 | DESIGNED | accepted: the writer walks at most kRecorderMaxThreads entries |
| R2-2 | DESIGNED | accepted: the table holds atomic pointers, stored last with release, loaded with acquire; NULL is not ready; mb_ready deleted |
| R2-3 | SEEN | accepted: RECORDER_PAUSED deleted; the pause is the writer's local, shown by mb_degraded; records keep entering the rings; one writer per state transition |
| R2-4 | DESIGNED | accepted: m_publishedAt on the slot, m_lastProgressAt by the writer; RecorderIsStalled computed at read by the main thread; m_pendingSince and the instance's stalled flag deleted; frames only, stated |
| R2-5 | DESIGNED | accepted: DieReasonText and m_stopDeadline; FlushInDie fills them, then STOPPING with release; the last pass in the stated order, the PNGs while before the deadline |
| R2-6 | DESIGNED | accepted: OsEvent carried to runtime_internal.h as a sticky flag with set, clear and a timed monotonic wait; the writer's order is wait, clear, read the state |
| R2-7 | N/A, FORCED | accepted: the orders stated on the ring; a power-of-two check when the ring is made; the slot by mask; Python positions never wrap |
| R2-8 | SEEN | accepted: the writer holds its one formatted line until written, retries it first, pops nothing while paused |
| R2-9 | DESIGNED | accepted: Create accepts NOT_CREATED and STOPPED; the table and the thread-local pointers survive |
| R2-10 | FORCED | accepted as the generic rule: a second event, stopped; Destroy and FlushInDie wait on it; only Destroy joins, after it; on the writer's own thread FlushInDie returns at once |
| R2-11 | N/A | accepted: in Python the claim takes a free index from a deque; the state stays for READY |
| R2-12 | FORCED | accepted as a check: the size, format and stride are checked before the claim, so the copy cannot fail |
| R2-13 | N/A | accepted: stated in the ring comment; a failed allocation leaves the thread without rings, counted as dropped spans |
| R2-14 | N/A | accepted: the event text sized by sizeof; m_thread and m_index deleted; the pad is 7 |
| R2-15 | N/A | accepted: three rows added to the changes table; the mask pool is the frame pool times the mask limit |
| R2-16 | N/A | accepted: one step per line; the writer sums the rings' drop counts; the health line once per fsync; PoolClaim takes the instance |

## Conclusions (after round 2)
- Agreed: everything in both rounds. Open: none for the reviewers. For the owner: the changes against the approved contracts, recorder.md section 4, now twelve rows.
- Changed: recorder_internal.h rewritten again (-Wextra -pedantic clean; the instance 920 bytes; the record sizes pinned); recorder.md sections 2, 4, 7, 8, 9.
- Added by round 2, each with its cause: the atomic pointer table (DESIGNED), m_publishedAt and m_lastProgressAt (the stall ruling), DieReasonText and m_stopDeadline (DESIGNED), the stopped event (the generic rule for a join), the power-of-two check (clarity). Deleted: RECORDER_PAUSED, mb_ready, m_pendingSince, the instance's stalled flag, SpanRecord.m_thread, ThreadRings.m_index.
- Carried: OsEvent, a sticky flag with set, clear and a timed monotonic wait, into runtime_internal.h; the mask limit per pass as a config value; the app makes the session folder with a mkdir that fails on EEXIST; the screen picks the GPU reader per vendor; the frame buffer drops its FrameSize copy at the fold.



## Round 3: reviewer (2026-10-19)

Reviewed: DRAFT 7 after R4 (the field survey). Read in full: this file, `recorder.md`, the three
util headers, the seven recorder headers, `modules/README.md`, `docs/guidelines.md`. Rounds 1 and
2 are not repeated. This round tests what R4 changed.

**The causes of the mechanisms added since round 2 (gate item 12, checked first).**
| mechanism | cause | holds? |
|---|---|---|
| the byte ring, reserve, pack in place, commit | the owner's R4 approval (a ruling) | yes, on his authority |
| typed fields, interned keys, the writer makes text | R4 ruling | yes |
| the watermark wake at half a ring | R4 ruling; the trigger "a burst past 1 MiB in 5 s" is neither SEEN nor DESIGNED at the measured rates | stands on the ruling only (R3-4) |
| the clock line at every fsync | R4 ruling (a stepped wall clock) | yes |
| the drop line with the gap | R4 ruling | yes |
| the producer's cached tail, the consumer's cached head | none named; rigtorp's reason is millions of operations a second, ours is 40 | no cause; it also breaks the watermark (R3-4) |
| two index queues per pool | R1-2 (DESIGNED), rebuilt by the owner's RCD8 to RCD11 | yes |

Measured facts used below (gcc 13.3.0, x86-64; CPython 3.12.3, GIL on; ext4 on NVMe). Scripts
are in the session scratchpad, not in the repo.
| fact | value | how |
|---|---|---|
| ten headers alone under -Wall -Wextra -pedantic -std=c11 | nine clean; `fixed_text.h` alone: "ISO C forbids an empty translation unit" | gcc -fsyntax-only, one by one |
| sizeof SpanHead, EventHead | 24 and 16 bytes; the layout says 18 and 10 | gcc sizeof |
| SpscByteRing | 128 bytes: m_head at 0, m_tail at 64, m_capacity at 68, m_bytes at 72 | gcc offsetof |
| sizeof RecordField, ThreadRing, struct Recorder | 24, 256 (aligned to 64), 1104 bytes | gcc sizeof |
| run sizes | a span with 3 numbers 52 bytes; the GPU event with 2 numbers 34 bytes | arithmetic, 4 + head + 10 per field |
| tail space under 4 bytes at a wrap | 4 of 114 wraps (tail space 1 and 3 bytes) | simulation: 2 M runs of real sizes, no rounding |
| recorded detection lists over 2047 bytes | 12 of 845 pass files; the largest 5849 bytes (95 detections, "fingertips") | logs/sessions/*/perception/**/pass_*.json, compact JSON |
| Python: three field makers (tuples) | 125 to 176 ns | timeit, best of 5 |
| Python: span with makers and a pack per part | 805 to 844 ns | timeit, includes two clock reads (60 ns) |
| Python: one Struct per field shape, cached | 994 to 1064 ns | timeit |
| Python: a helper with its own precompiled Struct | 296 to 311 ns | timeit |
| Python: the pre-R4 f-string record, same harness | 723 to 804 ns | timeit |
| Python: Event.set() already set; is_set() check first | 332 ns; 23 ns | timeit |
| Python: the writer formats one span line (json.dumps) | 2946 ns | timeit |
| Python: os.write of one line; of 250 lines at once | 1443 ns a line; 44 ns a line | 25,000 lines on ext4 |
| main-thread wake lateness while the writer formats 25,000 lines | no writes: p99 5135 us; a write per line: p99 146 us; a write per 250 lines: p99 1094 us; idle: p99 56 us | a 1 ms sleeper thread, switch interval 5 ms |
| pack_into raises | '<q' with a float, None, numpy.float32, or a value past 2^63; a 4-byte header 2 bytes from the end | struct.error, measured |

### The six test points

#### 1. The byte ring
**Verdict: the orders hold; the end of the ring does not.**
- **Orders.** Reserve writes only the producer's locals. Commit stores the head with release. Peek
  loads the head with acquire; Release stores the tail with release; Reserve loads the tail with
  acquire. That is a correct SPSC protocol. The consumer sees whole runs only.
- **The cached tail.** It is refreshed only when the cached view says full, as rigtorp's
  `try_push` does. The tail only grows, so a stale cache under-reports free space. It never
  over-reports. `head - cachedTail` never exceeds the capacity. That holds for Reserve. It fails
  for `SpscProducerFill`, which the watermark reads (R3-4).
- **The padding run.** A run of 34 bytes makes later offsets 2 mod 4. Nothing rounds a run. So
  the tail space at a wrap can be 1, 2 or 3 bytes: 4 of 114 wraps in the simulation. A padding
  header needs 4. In C the header lands past the buffer. In Python pack_into raises (measured).
  The kernel's ring rounds every record to 8 bytes: `len = round_up(size + BPF_RINGBUF_HDR_SZ, 8)`.
  This is R3-1.
- **A run exactly at the end.** It needs no padding if the test is "run > tail space". The next
  run starts at 0. Correct; a test should pin `>` against `>=`.
- **The consumer's skip.** A padding run is released by its m_bytes like any run. Correct once
  the header always fits.
- **The quarter-ring bound.** Correctness needs only run plus worst padding to fit: half a ring.
  A quarter is safe. 4096 bytes is 1/256 of the ring. The generic Init does not check the 16-bit
  m_bytes limit (R3-10).
- **The 2^32 wrap.** The capacity is a power of two and divides 2^32. Offsets by mask and
  free space by subtraction stay right. At about 2 KB a second the wrap is weeks away.
- **A reserve with no commit.** Nothing shared changes until Commit, if the padding and the run
  are published by one release store. The consumer sees nothing. The next Reserve reuses the
  space. In C a dying thread kills the process: FORCED. In Python a wrong-typed value raises
  between Reserve and Commit (R3-12). The ring is safe; the exception is the problem.
- **The Python mapping.** pack_into holds the GIL for the whole write. The head store is a later
  bytecode. A thread switch passes the GIL, a mutex, so the writer that reads the new head sees
  the bytes. This rests on the GIL. A free-threaded build (PEP 703) gives no stated order between
  a bytearray write and an attribute store: unverified. Positions are ints and never wrap.

#### 2. The typed fields and the run layout
**Verdict: the arithmetic holds; the bound loses SEEN data.**
- **Sizes.** SpanHead 8+8+1+1 = 18. EventHead 8+1+1 = 10. FieldHead 2, value 8, TextHead 2.
  A three-number span is 4 + 18 + 30 = 52 bytes. Correct.
- **The C structs do not match.** sizeof is 24 and 16. The field offsets match the packed layout;
  the tail padding does not. Every 8-byte value sits at an offset that is not a multiple of 8
  (R3-8).
- **255 keys and topics.** Index 0 is NONE and the table has 256 entries. The design uses about 60.
  Correct.
- **The intern while the writer formats.** The writer loads the count in step 2 and drains in
  step 4. An intern and a run that uses it can both land between the two. The run's line then
  precedes its definition line. But the file writes names, not ids, so no reader needs the
  definition lines at all (R3-6).
- **The text's lifetime.** The caller's bytes are copied into the run during the call. Correct.
- **A run over 4096 bytes refused.** The recorded detection lists exceed 2047 bytes in 12 of 845
  passes. Those pass events are refused whole and counted as ring drops (R3-2).
- **A bool as 8 bytes.** 7 bytes wasted per bool, at about 2 KB a second: nothing. One value width
  keeps the reader's table to two cases. Keep it.
- **A float as a double.** A Python float is a double; 'd' converts nothing. Keep it.
- **The makers returning 24 bytes by value.** In C, above 16 bytes the SysV ABI returns through
  memory: a few stores, nothing at 40 a second. In Python each maker makes a tuple: 42 to 59 ns
  per field, measured. That cost matters more (R3-11).

#### 3. The watermark wake
**Verdict: correct as a sticky set; wrong in its fill; with no measured need.**
- **Once per crossing.** The fill comes from the cached tail. The cached fill only grows until the
  cache says full. It passes half after 512 KiB of writes since the last refresh, whatever the
  writer drained: a wake for nothing. From then until the refresh, it stays above half. A real
  burst in that window sees no crossing and gets no wake (R3-4).
- **The lost wake.** The producer commits, then sets. The writer waits, clears, then drains. A set
  after the clear stays set; a set before the clear is followed by a drain that sees the commit.
  Correct.
- **The timer.** wait(5.0) restarts after each wake. The fsync and the health line keep their own
  last time. Correct.
- **Half of 1 MiB against the rates.** The main thread writes 40 x 52 bytes = 2.1 KB a second.
  Half a ring is about 250 s of it. In the app, every published frame wakes the writer about 3
  times a second, and every pass drains every ring. So the app's rings never hold more than a
  third of a second. The SAM3 process writes about 3 spans a second. No measured rate reaches
  the watermark unless the writer has stalled for minutes, and then a wake does nothing.

#### 4. The clock line and the drop gap
**Verdict: the clock line holds; the gap has no reset rule.**
- **The clock line before every health line.** Once per fsync, every 5 s. Correct in the normal
  pass. The last pass omits it (R3-3).
- **Torn values.** Each 64-bit atomic is lock-free on x86-64 (round 2). One value is never torn.
- **A torn pair.** Count, first and last are three stores. The writer reads them at different
  moments. If it reads last before first, a new gap's first can be newer than the old gap's
  last: "from" after "to". Nothing says who resets m_firstDropAt after a drop line. The writer
  cannot: the field is "the producer's alone" (R3-5).

#### 5. The writer's pass order
**Verdict: the normal pass holds with one snapshot fix; the last pass skips steps.**
- **Steps 3 and 4.** If step 4 reloads the thread table, a ring that appeared after step 3 gets
  lines before its thread line (R3-7).
- **Step 5 after step 4.** A drop line follows runs committed after the gap. The section 9 test
  "in time order" then fails. The reader places the drop by its from and to (R3-5).
- **The last pass.** It lists the rings, the die line, the health line, the fsync, the PNGs. It
  omits the thread lines, the held line, the drop lines and the clock line (R3-3).
- **The cost of text in the writer.** 2.9 us a line in Python. 250 lines per 5 s is 0.74 ms per
  5 s. A burst of 25,000 lines takes 74 ms to format and 36 ms to write, 185 ms in all with a
  write per line.
- **The GIL.** Formatting alone holds the GIL for up to the 5 ms switch interval: the main thread
  woke up to 5.1 ms late (p99). A write per line releases the GIL each line: p99 146 us, inside
  the 330 us budget. A write per 250 lines: p99 1.1 ms. So in Python, R2-15's write per line is
  also the GIL's friend. The mapping should say so, so nobody batches it "for speed".

#### 6. Against the field
**Verdict: two claims are wrong; one practice we lack matters.**
- **Wrong: "OpenTelemetry ... wakes early at half full".** The spec exports early "when queue
  contains maxExportBatchSize or more spans": 512 of 2048, a quarter. The Python SDK 1.20 does
  the same: `if len(self.queue) >= self.max_export_batch_size`. It is a batch size, not a fill.
- **Wrong: Tracy "re-sampled during the run".** Tracy calibrates its timer at start. It does not
  re-sample. Perfetto does: "These clocks are periodically snapshotted by the traced service."
- **Imprecise: eBPF in the padding discussion.** eBPF needs no padding run. It maps the data
  pages twice: "no need to worry about special handling of wrapped-around data". The doc credits padding
  to LTTng only, which is right; the table's row for eBPF should not imply padding.
- **Holds.** The 8-byte eBPF header with busy and discard bits. Notification "only if consumer
  has already caught up". Reserve "avoids the extra copy of memory". rigtorp's aligned indexes
  and cached copies. OpenTelemetry's 2048 queue, its bounded ForceFlush and Shutdown, and
  "should not block or throw". perf's wakeup watermark.
- **What the field does that we do not, and it matters.** Record rounding: eBPF rounds every
  record to 8 bytes, so the end always fits a header (R3-1). Perfetto emits an interned entry
  "in the same TracePacket that first refers to them". That makes define-before-use true by
  construction (R3-6). rigtorp keeps the capacity and the slot pointer off the index lines
  (R3-9).
- **What the field does that we need not.** Double-mapped pages, per-CPU buffers, binary files,
  overwrite mode, interning-state resets after loss. At 2 KB a second none pays.

### Findings

Counts: high 1, medium 2, low 13.

#### R3-1. The tail space at a wrap can be smaller than a run header
- **Severity:** high. **Cause:** DESIGNED.
- **Where:** spsc_byte_ring.h:5-7, :25-34, :81-84; recorder_internal.h:75-80, :117-123.
- **What is wrong.** Runs have any byte length: 52 for a span, 34 for the GPU event, any length
  with text. Nothing rounds them. So at a wrap the tail space can be 1, 2 or 3 bytes. The design
  says the producer writes a padding run there. A padding header is 4 bytes. In C it writes up to
  3 bytes past the ring: heap corruption on the main thread. In Python pack_into raises (measured).
  Trace: any app session longer than about 8 minutes wraps the main ring; 4 of 114 wraps in the
  simulation hit it. A 40-minute flight wraps each busy ring about 5 times.
- **Smallest fix.** Round every run to 8 bytes, as eBPF does: the run's total is
  `(4 + payload + 7) & ~7`. The tail space is then 0 or at least 8. The header's m_bytes stays
  the payload length; the consumer advances by the rounded total. One test: runs of 34 bytes until
  a wrap; no write past the end, and the consumer reads every run.
- **Source:** https://github.com/torvalds/linux/blob/master/kernel/bpf/ringbuf.c

#### R3-2. The text bound drops whole pass events that sessions already produced
- **Severity:** medium. **Cause:** SEEN (12 of 845 recorded passes have a detection list over 2047 bytes; the largest 5849).
- **Where:** record_field.h:17-18; recorder.md:143, :156-157, :272; recorder_internal.h:125-126.
- **What is wrong.**
  - The pass event carries the boxes as one text field. Past 2047 bytes the run is refused. The
    whole event is lost: the job, the request, the phrase, the boxes.
  - The passes lost are the ones with the most detections, the ones a reader most wants.
  - The refusal is counted as a dropped event and stamps the gap. The drop line then reads as a
    writer that fell behind. It was our own bound.
  - recorder.md:156-157 still says "the 104-byte payload replaced by {"cut":N} and counted
    (PRF4)". Line 143 says "nothing is cut". The matrix calls the case DESIGNED; it is SEEN.
- **Smallest fix.** Keep the approved rule, PRF4: the packer cuts a text field to fit the run's
  bound, at a UTF-8 character start, and adds an int field "cut" with the original length. A
  record is never refused for its text. Delete the INVALID_ARG drop path for spans and events.
  One test: a 5849-byte boxes text makes one event line with "cut":5849 and valid UTF-8.

#### R3-3. The last pass skips four steps of the normal pass
- **Severity:** medium. **Cause:** DESIGNED (any die() mid-flight runs this pass).
- **Where:** recorder_internal.h:333-337; recorder.md:221, :306.
- **What is wrong.** The last pass lists: the rings, the die line, the health line, the fsync,
  the PNGs. It omits the thread lines, the held line, the drop lines and the clock line.
  - Trace: a job thread's first span 1 s before die(). Its lines carry "t":9 with no thread line.
  - A held line from a disk error is never retried, or lands after newer lines.
  - The drops since the last pass have no drop line in the one file that explains the die.
  - The health line has no clock line before it. The section 9 test "the clock line appears
    before every health line" fails on every die.
- **Smallest fix.** The last pass is the normal pass with the die line inserted: steps 3 to 5,
  the die line, step 8 (clock, health, fsync), then step 6 while the clock is before
  m_stopDeadline. One test: a ring made, a drop, then FlushInDie; the file holds the thread line,
  the drop line, the clock line, then the health line.

#### R3-4. The watermark reads a stale fill, and no measured rate needs it
- **Severity:** low. **Cause:** the failure needs a burst past half a ring in 5 s; that is neither
  SEEN nor DESIGNED. The watermark stands on the R4 ruling.
- **Where:** spsc_byte_ring.h:51-62, :85-86; recorder_internal.h:182-187, :289-293; recorder.md:24, :283.
- **What is wrong.**
  - `SpscProducerFill` uses the cached tail. The cache refreshes only at "full". The cached fill
    crosses half after 512 KiB of writes since the last refresh: a wake for nothing.
  - Until the next refresh the cached fill stays above half. A real burst then sees no crossing.
    The wake is lost, which is what the watermark exists to prevent.
  - The need. The app drains every ring about 3 times a second, on each frame wake. The SAM3
    process writes about 3 spans a second. Half a ring is minutes of data at either rate.
  - The cached tail and head have no cause at 40 records a second. One acquire load per reserve
    costs nothing measurable at that rate.
- **Smallest fix.** Delete `m_cachedTail` and `m_cachedHead`. Reserve, Fill and Peek load the
  other index with acquire every time. The watermark then reads the true fill. Whether the
  watermark stays at all is an open point for the owner: no SEEN or DESIGNED trigger reaches it.
- **Source:** https://github.com/rigtorp/SPSCQueue/blob/master/include/rigtorp/SPSCQueue.h

#### R3-5. The drop gap has no reset rule, and its three values are not one snapshot
- **Severity:** low. **Cause:** FORCED at the measured rates once R3-2 is fixed (a full ring needs
  minutes of writer stall).
- **Where:** recorder_internal.h:163-180, :327-328; recorder.md:217, :310.
- **What is wrong.**
  - "m_firstDropAt: of the gap since the last drop line". Only the writer knows a line was
    written. It cannot reset a field that is "the producer's alone".
  - The writer reads count, first and last at three moments. Read in the wrong order, "from" can
    follow "to".
  - Step 5 runs after step 4. A drop line follows the runs committed after the gap. The section
    9 test "in time order" contradicts the pass order.
- **Smallest fix (generic, no new mechanism).** The producer keeps a local "dropping" flag. The
  first drop after a successful commit stores m_firstDropAt; every drop stores m_lastDropAt, then
  the count, with release. The writer loads the count with acquire, then first, then last. It
  keeps its own last count and writes the difference. The test says the reader places a drop
  line by its "from".

#### R3-6. The key and topic definition lines have no reader
- **Severity:** low. **Cause:** N/A (YAGNI). The ordering defect inside it is DESIGNED.
- **Where:** recorder_internal.h:132-153, :323-324; recorder.md:205-206, :210-211, :256-258, :282.
- **What is wrong.**
  - The writer makes `"p":{"read":1.2}` and `"topic":"gpu"`. The file holds names, never ids. So
    `{"k":"key","id":1,"name":"read"}` serves no reader.
  - The claim "an id above it cannot be in a run yet" is false within one pass. The count is
    loaded in step 2. An intern and its first run can both land before step 4.
  - NameTable carries two `@m_names` comments (:138-147), one of them stale.
- **Smallest fix.** Delete the key and topic lines, `m_announced`, and step 2. The writer reads a
  name by id; the name was stored before the intern returned, and the run's release and acquire
  carry it. If ids are wanted in the file later, write a definition in the same pass, just before
  its first use, as Perfetto does.
- **Source:** https://docs.fuchsia.dev/rust/perfetto_trace_protos/perfetto/protos/struct.InternedData.html

#### R3-7. The thread lines and the rings need one snapshot of the table per pass
- **Severity:** low. **Cause:** DESIGNED (a job thread's first record during a pass); the effect is one line before its thread line.
- **Where:** recorder_internal.h:324-327.
- **What is wrong.** Step 3 writes thread lines for the non-NULL entries. Step 4 walks "every
  ring". If step 4 loads the table again, a ring stored between the two gets lines first.
- **Smallest fix.** Load the 32 pointers once per pass into a local array. Steps 3, 4 and 5 use it.

#### R3-8. The run heads as C structs disagree with the run layout
- **Severity:** low. **Cause:** N/A (clarity); a C reader that casts or uses sizeof reads the wrong stride.
- **Where:** recorder_internal.h:85-123.
- **What is wrong.** sizeof(SpanHead) is 24 and sizeof(EventHead) 16, against 18 and 10. The
  payload starts 4 bytes into a run, so every 8-byte value is misaligned. A cast to `SpanHead*`
  is undefined behavior in C, though x86 tolerates it.
- **Smallest fix.** One sentence: every part is read and written by memcpy at the stated offsets
  (pack_into and unpack_from in Python); the structs name the fields, the k-constants give the
  sizes. Pin the offsets: `static_assert(offsetof(SpanHead, m_fieldCount) + 1 == kSpanHeadBytes)`
  and the same for EventHead.

#### R3-9. The ring's read-only fields share the consumer's cache line
- **Severity:** low. **Cause:** N/A (the layout contradicts its own claim; no cost at 40 records a second).
- **Where:** spsc_byte_ring.h:40-49; recorder.md:292.
- **What is wrong.**
  - m_capacity (offset 68) and m_bytes (offset 72) sit on m_tail's line. The producer reads them
    on every reserve. So every consumer release invalidates a line the producer reads. The
    comment says a pop never touches the producer's line.
  - The doc says three lines per ring and 64 rings: 12 KiB. The ring is 128 bytes, two lines, and
    the cap is 32 threads.
  - ThreadRing is aligned to 64. A malloc gives 16. The thread's first record must use
    aligned_alloc.
- **Smallest fix.** Put m_capacity and m_bytes first, before the aligned head, as rigtorp does.
  Fix the text: 192 bytes, three lines, 32 rings. State aligned_alloc(64) for ThreadRing.
- **Source:** https://github.com/rigtorp/SPSCQueue/blob/master/include/rigtorp/SPSCQueue.h

#### R3-10. The generic ring does not check its 16-bit run length
- **Severity:** low. **Cause:** N/A (a util contract; the recorder's 4096 is far below the limit).
- **Where:** spsc_byte_ring.h:31, :69-78.
- **What is wrong.** m_bytes is 16 bits. Init accepts any maxRunBytes up to a quarter ring. A
  user with a 1 MiB ring and 256 KiB runs gets a silent truncated length.
- **Smallest fix.** Init returns false when maxRunBytes exceeds 65535 plus the header. One line in
  the false list.

#### R3-11. In Python the generic typed path costs what the f-string cost
- **Severity:** low. **Cause:** N/A (a cost claim; the budget still holds).
- **Where:** recorder.md:233-235, :282, :346-347; record_field.h:52-56.
- **What is wrong.**
  - "The pack of three numbers is well under 200 ns": measured 805 to 844 ns with the makers, a
    pack per part and two clock reads. The pre-R4 f-string record took 723 to 804 ns in the same
    harness. R4's main benefit does not appear in Python as specified.
  - A helper that owns a precompiled `struct.Struct` for its field shape: 296 to 311 ns.
  - `Event.set()` takes the Event's internal lock even when set: 332 ns. Section 2 says nothing
    on the path locks. `is_set()` first: 23 ns.
  - At 40 spans a second even 844 ns is 34 us a second, inside the 330 us budget.
- **Smallest fix.** The Python mapping: each `record_<owner>` helper builds one `struct.Struct`
  per record shape at import and packs in one call; the generic packer stays for odd shapes. The
  watermark set reads `if not wake.is_set(): wake.set()`. Replace "under 200 ns" with the
  measured numbers.
- **Source:** https://github.com/python/cpython/blob/3.12/Lib/threading.py

#### R3-12. A wrong-typed value raises between reserve and commit
- **Severity:** low. **Cause:** none SEEN; the trigger is our own bug (a float to field_int). The generic handling only.
- **Where:** record_field.h:52-56; recorder.md:233, :70-71.
- **What is wrong.** '<q' raises on a float, None, numpy.float32 or a value past 2^63 (measured).
  The ring is safe: nothing is published. But the exception leaves the module. util/guarded.py has
  no domain for struct, and the house allows no other try.
- **Smallest fix (generic).** The Python makers check the type and the range: an int field takes
  an integral value, a float field a real one. A bad field makes the record call drop and count
  before the reserve. No try. One test: field_int with 1.5 counts a drop and raises nothing.
- **Source:** https://docs.python.org/3/library/struct.html

#### R3-13. The writer's order is a run-on paragraph again, and naked bytes came back
- **Severity:** low. **Cause:** N/A (clarity; R2-16 was accepted as "one step per line").
- **Where:** recorder_internal.h:224-230, :322-337; spsc_byte_ring.h:4-7; record_field.h:36, :56;
  record_span.h:43; record_event.h:27; recorder_internal.h:88-89, :98-99, :109-110, :114, :151-152.
- **What is wrong.** The eight steps run inline with bare numbers ("1 wait ... 2 the definition
  lines"). Three comments break mid-sentence ("one writer per\n transition"). Naked primitives:
| file:line | the primitive | justified? |
|---|---|---|
| spsc_byte_ring.h:31 | `uint16_t m_bytes` | weak. A 16-bit run length beside the 32-bit `RingBytes` |
| spsc_byte_ring.h:32-33, :83 | `uint8_t m_kind`, `m_reserved`, `uint8_t kind` | m_reserved yes (padding); the kind byte weak |
| spsc_byte_ring.h:48; internal:207, :288 | `uint8_t*` | yes. Raw bytes |
| record_field.h:36, :56; internal:114 | `uint16_t` text lengths | no. R1-10's `TextLength` is gone |
| record_span.h:43; record_event.h:27; internal:89, :99 | `uint8_t count`, `m_fieldCount` | no. A `FieldCount` is missing |
| internal:98, :109 | `uint8_t m_topic`, `uint8_t m_key` | no. `RecordTopic` and `RecordKey` exist and are uint8_t |
| internal:88, :110 | `uint8_t m_stage`, `uint8_t m_type` | yes in a packed layout; the comment names the enum |
| internal:151-152 | `_Atomic uint32_t m_count`, `uint32_t m_announced` | no. A `NameCount`; m_announced goes (R3-6) |
| internal:55 | `typedef int FileDescriptor` | yes. POSIX |
| recorder.h:59 | `float m_freeGiB` | yes. The unit is in the name |
- **Smallest fix.** One step per line, numbered, in the writer comment. `typedef uint16_t
  TextLength;` and `typedef uint8_t FieldCount;` in record_field.h. `RecordKey m_key` and
  `RecordTopic m_topic` in the heads. Rewrap the three broken comments.

#### R3-14. The document contradicts the headers in six places
- **Severity:** low. **Cause:** N/A (gate item 10: the document and the headers agree).
- **Where and what.**
  - recorder.md:7 names `ring_buffer.h` and `slot_pool.h`; the files are `spsc_byte_ring.h` and
    `index_queue.h`.
  - recorder.md:156-157 and :172 keep "the 104-byte payload replaced by {"cut":N}" and "the
    128-byte record ... unchanged"; line 143 says otherwise (R3-2).
  - recorder.md:295 says 936 bytes; line 240 says 1104; measured 1104.
  - recorder.md:292 says three lines and 64 rings; measured two lines, the cap is 32 (R3-9).
  - recorder.md:239 says all ten headers are clean; `fixed_text.h` alone warns under -pedantic
    (an empty translation unit). Harmless for a macro header; say so.
  - spsc_byte_ring.h:54-55: the `@m_reservedAt` comment says "0 bytes when none", which describes
    `m_reservedBytes`.
- **Smallest fix.** Edit each line to the measured value or the current name.

#### R3-15. Two claims about the field are wrong
- **Severity:** low. **Cause:** N/A (gate item 10; the survey is the reason for R4).
- **Where:** recorder.md:145, :283, :325, :328.
- **What is wrong.** OpenTelemetry exports early at maxExportBatchSize, 512 of 2048: a quarter, by
  count, not "half full". Tracy calibrates its timer once at start; it does not re-sample clocks
  during the run.
- **Smallest fix.** "OpenTelemetry exports early at a batch size (512 of 2048)." Drop Tracy from the
  clock row; Perfetto's periodic snapshots stand alone.
- **Sources:** https://opentelemetry.io/docs/specs/otel/trace/sdk/ ;
  https://github.com/open-telemetry/opentelemetry-python/blob/v1.20.0/opentelemetry-sdk/src/opentelemetry/sdk/trace/export/__init__.py ;
  https://perfetto.dev/docs/concepts/clock-sync

#### R3-16. Three small fields repeat what their container knows
- **Severity:** low. **Cause:** N/A (YAGNI).
- **Where:** recorder_internal.h:202, :219; index_queue.h:37 with recorder_internal.h:316-320.
- **What is wrong.**
  - `FrameSlot.m_format`: the frame pool is BGR and the mask pool is gray, always.
  - `FramePool.m_count`: the free queue's capacity holds it.
  - `RecorderIsStalled` peeks `m_ready` through `IndexQueuePeek`, which takes the queue's lock, on
    the main thread, each frame. The hold is a few loads; it is still a lock on the path gate item
    1 audits. In Python `deque[0]` needs no lock.
- **Smallest fix.** Delete the two fields. Name the peek's lock in gate item 1 with its hold time.

### What is right
- The SPSC orders: release on commit and release, acquire on the other side. The consumer sees
  whole runs only.
- A reserve with no commit leaves nothing for the consumer and costs nothing.
- One ring per thread with variable runs: a three-number span is 52 bytes, not 128.
- The sticky wake with commit-then-set and wait-clear-drain. No wake is lost.
- The clock line every 5 s in the normal pass, for a stepped wall clock.
- Pools as two index queues: one model for C and Python.
- Text made by the writer, with a write per line. In Python that write releases the GIL every
  line, so a 25,000-line burst kept the main thread's p99 lateness at 146 us (measured).
- Names, not ids, in the file. The reader needs no decoder.
- The instance at 1104 bytes, measured as claimed in section 7.

### The three lenses
- **Storage and hardware.** About 2 KB a second per busy ring; a write per line costs 1.4 us on
  this ext4; fsync every 5 s. NVMe wear is nothing. Page faults on a ring's first lap spread over
  minutes. The ring's read-only fields share the consumer's line (R3-9). The end of the ring needs
  rounding (R3-1).
- **Concurrency and real time; the GIL.** The C orders are right. The cached indexes add a stale
  fill and no measured gain (R3-4). In Python the GIL orders pack_into before the head store; the
  writer's write per line bounds GIL holds to one line's formatting; Event.set takes a lock
  (R3-11). A free-threaded build is outside the design: say "CPython with the GIL" in the mapping.
  The main thread takes the ready queue's lock each frame (R3-16).
- **YAGNI and decoupling.** Should go: the key and topic definition lines with `m_announced` and
  step 2 (R3-6); `m_cachedTail` and `m_cachedHead` (R3-4); `FrameSlot.m_format` and
  `FramePool.m_count` (R3-16); the INVALID_ARG path for spans and events (R3-2). For the owner:
  the watermark, `kRecordRingWatermarkBytes`, `SpscProducerFill` and `RecorderAfterCommit` have no
  SEEN or DESIGNED trigger (R3-4). Justified: every other type, constant and function in the ten
  headers. Should come: `TextLength`, `FieldCount` (R3-13).
- **Does recorder_internal.h read without its comments?** The structs read. The writer's order,
  the run layout's packing rule and the drop gap's owners do not: each lives only in a comment
  (R3-8, R3-5, R3-13).

### Sources
- BPF ring buffer, kernel documentation: https://docs.kernel.org/bpf/ringbuf.html
- kernel/bpf/ringbuf.c (`round_up(size + BPF_RINGBUF_HDR_SZ, 8)`, double-mapped pages): https://github.com/torvalds/linux/blob/master/kernel/bpf/ringbuf.c
- rigtorp SPSCQueue (aligned indexes, cached copies, capacity first): https://github.com/rigtorp/SPSCQueue/blob/master/include/rigtorp/SPSCQueue.h
- OpenTelemetry trace SDK, batching processor: https://opentelemetry.io/docs/specs/otel/trace/sdk/
- OpenTelemetry Python SDK 1.20, BatchSpanProcessor.on_end: https://github.com/open-telemetry/opentelemetry-python/blob/v1.20.0/opentelemetry-sdk/src/opentelemetry/sdk/trace/export/__init__.py
- Perfetto, clock synchronization: https://perfetto.dev/docs/concepts/clock-sync
- Perfetto InternedData (an entry emitted in the packet that first refers to it): https://docs.fuchsia.dev/rust/perfetto_trace_protos/perfetto/protos/struct.InternedData.html
- CPython 3.12 threading.Event (set under the Condition's lock): https://github.com/python/cpython/blob/3.12/Lib/threading.py
- Python struct (pack_into, the range errors): https://docs.python.org/3/library/struct.html
- PEP 703, the free-threaded build: https://peps.python.org/pep-0703/

## Round 3: answer (the manager, 2026-10-19)
Every finding judged on its cause and applied. Counts: accepted 16, narrowed 0, rejected 0.
| finding | cause | answer |
|---|---|---|
| R3-1 | DESIGNED | accepted: every run rounded to 8 bytes, as the kernel's ring; the tail space is 0 or a header |
| R3-2 | SEEN | accepted: PRF4 restored on a text field: cut at a character, a "cut" int field with the original length; no refusal; the matrix row is SEEN with the numbers |
| R3-3 | DESIGNED | accepted: the last pass is the normal pass with the die line inserted |
| R3-4 | the R4 ruling | accepted: the cached indexes deleted, the fill is the true one; the watermark stays on the owner's R4 ruling, with the note that no measured rate reaches it |
| R3-5 | FORCED | accepted as the producer's protocol: first after a good commit, last and then the count with release; the writer reads count, first, last and writes the difference; a drop line is placed by its from |
| R3-6 | N/A | accepted: no key or topic lines; no announce; the writer reads names by id, carried by the run's release and acquire |
| R3-7 | DESIGNED | accepted: one snapshot of the thread table per pass |
| R3-8 | N/A | accepted: memcpy at the stated offsets, never a cast; static_asserts pin the two heads to 18 and 10 packed bytes |
| R3-9 | N/A | accepted: the read-only fields first; 192 bytes, three lines, 32 rings; aligned_alloc(64) for a thread's ring |
| R3-10 | N/A | accepted: Init refuses a run bound over 65535 |
| R3-11 | N/A | accepted: one precompiled Struct per helper shape (296 to 311 ns measured); is_set() before set(); the measured numbers in the document |
| R3-12 | our own bug | accepted: the makers check type and range; a bad value drops and counts before the reserve; no try |
| R3-13 | N/A | accepted: one step per line; FieldCount and TextLength; RecordKey and RecordTopic in the heads; NameCount; the comments rewrapped |
| R3-14 | N/A | accepted: the six contradictions fixed |
| R3-15 | N/A | accepted: OpenTelemetry's batch size, Tracy's one calibration |
| R3-16 | N/A | accepted: m_format and m_count deleted; the peek's lock named in gate item 1 |

## Conclusions (after round 3)
- Agreed: everything in the three rounds: 50 findings, 48 applied, 2 narrowed. Open: none for the reviewers. For the owner: the changes against the approved contracts, recorder.md section 4.
- The one high of round 3 was a real memory fault: a padding header past the ring at 4 of 114 wraps. The rounding closes it by construction.
- Carried: OsEvent and OsLock into runtime_internal.h (done 2026-10-19); the mask limit per pass as a config value; the session folder's mkdir rule; the GPU reader per vendor in the screen.

## The blind read (2026-10-19): can an outsider rebuild the design from the ten headers alone?
The owner's test: "Give a subagent read only access to all the files of the recorder, not including
the markdown and the html ... If the subagent can get >90% Accuracy, I'll review it one last time
... Otherwise, It means that the design is non-obvious enough, or frankly, just bad."
The reader (opus, maximum care) had the ten headers in an isolated folder and nothing else. Its
reconstruction (59 KB, ten sections, every claim cited to a header line) sits in the session
scratchpad as blind/reconstruction-2026-10-19-a.md; the manager's comparison against recorder.md:

| section of the reconstruction | right | wrong | not in the headers (a gap of the headers) | score |
|---|---|---|---|---|
| 1 the job and the domain | the job sentence; the domain from the stage names; SAM3 as a process; the flight budget | none | none | 95 |
| 2 the picture | every thread, buffer, queue, owner, the two processes, the path to disk, the thread table protocol | none | the slot claim by fetch_add (inferred right); which pool a frame enters, by format (inferred right) | 90 |
| 3 the lifetime | the state machine, Create's steps, the re-Create rule, FlushInDie's steps, the second process | none; but it read "Destroy: deadline 0, so no frames are encoded" correctly from a header that is WRONG (defect D3 below) | Destroy's frame rule; what Destroy frees; fork | 75 |
| 4 the contracts | all three signatures, costs, never-does, full-buffer rules, the typed fields and the module pattern | none | the pool choice; what INVALID_ARG covers; key 0 in a field | 90 |
| 5 the hot path | the run layout byte for byte (a worked example, the Python struct formats), the ring rules, the reserve and commit algorithm, the watermark, the drop protocol, the pass order | none | whether 4096 bounds the payload or the run; the drop's time stamp; m_reservedAt | 85 |
| 6 the failures | the full ring, the full pool, the failed write, the pause, the reserve, the stall, the die, the text cut, the full table, the bad value | the 33rd thread ("dropped"): the design dies (RVW4), and the header no longer says it | the reserve formula; recovery from degraded; a failed PNG; ringless drops | 65 |
| 7 the file | the name, the flags, the line kinds and their order, the reader's use of the clock and drop lines, the frame line as proof | every key name (guessed; the contract is in recorder.md section 7 only); the clock line's content | the whole line contract | 45 |
| 8 the concurrency | every ordering the headers state; the thread-local; the two queues; the name hand-off | none | m_state and m_threadCount orderings | 85 |
| 9 the gaps | 21 suspected defects and 23 open questions, every one with a line | none: 14 of the 21 are REAL defects the three reviews missed (D1 to D14 below); the rest are gaps the headers must close | | |
Weighted by the owner's question (the mechanism, the contracts, the machinations): about 72 %. Under 90.

**The verdict, honestly.** The mechanism, the contracts and the concurrency model came through at 85
to 90 %. Two things did not: the file's line contract lives only in the markdown (section 7 is not in
any header, so an outsider guesses every key), and the recovery rules are scattered comments. And the
reader found fourteen real defects that three review rounds did not. So both of the owner's readings
hold in part: the headers do not say enough, AND the design still has faults.

**The real defects the blind read found (the manager's own, to fix before any re-test).**
| id | the defect | the fix |
|---|---|---|
| D1 | a failed write keeps the line, but the run is released at the failure or not: the retried line's run is written twice or lost | the held line remembers its ring; the run is released only when its line is written |
| D2 | drops of a thread without a ring (a failed Init, a 33rd thread) have nowhere to be counted | one process-level atomic for ringless drops; the 33rd thread dies (RVW4), stated in the header again |
| D3 | Destroy stores deadline 0 and step 7 runs "while before the deadline", so Destroy never encodes a pending frame; "never a drain here" contradicts the last pass | Destroy's deadline is now plus its timeout; "never a drain on the caller's thread" |
| D4 | a thread whose ring Init failed allocates again on every record | a tried flag in the thread-local |
| D5 | the ring does not keep maxRunBytes, so Reserve cannot enforce it | the field stays in the ring |
| D6 | the cut field can make 17 fields, and two cut texts make two "cut" keys | the caller gets 15 fields; one reserved; one cut field with the total bytes cut |
| D7 | the stall rule reads m_publishedAt of a slot the writer may recycle at that moment: a data race | the writer stores an atomic "oldest ready published at" at the end of each pass; the main thread reads only atomics |
| D8 | Destroy and Die both store STOPPING and the deadline; the later store can erase Die's reason and deadline | only Die writes the deadline, by a compare-and-swap from 0; the state store is idempotent |
| D9 | on the last pass the fsync comes before the frames, so the last PNGs and frame lines are never fsynced | a final fsync after step 7 while time remains |
| D10 | a channel and a name are path components with no check; two equal names overwrite a PNG | the names are checked (no separator, no "..", the length bound); a PNG is opened O_EXCL and a clash is counted |
| D11 | the bool's 8 bytes are 7 undefined bytes if the packer copies the union | the packer zero-extends; the writer reads byte 0 |
| D12 | mb_announced survives a re-Create, so the new file lacks the old threads' lines | Create resets every mb_announced |
| D13 | mb_degraded means a write pause AND the reserve | two flags: mb_writePaused and mb_underReserve; the recovery rule for each stated |
| D14 | record_event.h still says "the writer writes the definition line" | the stale comment removed |
Also to state in the headers, from the open questions: which pool a frame enters (by format); INVALID_ARG covers the size, the stride, the format, a channel or name too long or malformed; a second intern of a name returns the same id; a name over 31 bytes is refused as NONE; a field with key NONE is left out of the record; an intern before Create returns NONE; a record in STOPPING or STOPPED is dropped and counted; 4096 bounds the whole run; the drop stamps are RecorderNow() at the drop; "every 100 records" counts runs written; the thread name comes from RecorderNameThisThread(name) at a thread's start, else "thread-N"; m_threadCount is a claim counter and a claim past 32 dies; fork without exec is not supported; m_reserved is zero; the line buffer is 16 KiB and a line past it is cut with a "cut" key; NaN and infinity are written as null; invalid UTF-8 is replaced; a failed PNG write is unlinked and counted; the set of the wake-up object takes the event's own lock, at most once per crossing; the reserve formula as a function in the header; the Python mapping's "no allocation" caveat.

**The structural fix the test points at.** The file is the recorder's real contract with its readers,
and it exists only in prose. A header `record_file.h` with the line kinds and every key as named
constants, plus the stage and type name tables, gives the writer and the readers (the report, the
replayer) one home, and gives an outsider the file from the code. The reader's section 7 would then
score with the rest.

## The second blind read (2026-10-19): the ten headers with EVERY comment removed
The owner: "Remove all comments from the code. Lets see how much the subagent can guess with pure code,
nothing else." A fresh reader (opus, maximum care), 523 lines of code, no comment, nothing else.
Result: overall 65 % (the commented read: about 72 %). Of 274 names: 206 CLEAR, 64 GUESS, 4 OPAQUE.
| section | commented read | comment-free read | what the comments bought |
|---|---|---|---|
| the job | 95 | 85 | the domain story |
| the picture | 90 | 75 | the PNG location; the thread line |
| the lifetime | 75 | 60 | the die path; the re-create rule |
| the contracts | 90 | 70 | the cut rule; the pool choice |
| the hot path | 85 | 60 | the text encoding; who owns head and tail (guessed right) |
| the failures | 65 | 50 | every recovery rule |
| the file | 45 | 35 | the file name pattern; nothing else was in the code either way |
| the concurrency | 85 | 75 | the orderings (guessed right from practice) |
The 64 guesses were nearly all right: the ring's head and tail roles, the rounding, the padding, the
watermark, the two pools split by pixel format, the thread-local, the flight budget. The 4 opaque:
IndexQueuePeek (no visible caller), SPAN_MESSAGE, FlushInDie's ctx, mb_degraded's trigger.
Not readable from the code: the clock behind RecorderTimestamp (monotonic or wall), the file's line
format and name, the PNG path, the recovery rules, the stall's meaning. The five names that hurt the
reader most: mb_degraded, RecorderRunBytes with TextHead, RecorderFormatRun with RecorderFileName,
mb_dropping, FlushInDie's ctx.
**The six names the owner could not read** (RecordKeyIntern, RecordTopicIntern, EventHead, FieldHead,
NameTable, ThreadRing) the reader rated CLEAR. The owner is the audience; the reader is not. They are
renamed in the next draft: Intern becomes Register; the packed layout structs carry "Packed" and
"Header"; NameTable becomes RegisteredNames; ThreadRing becomes RecordingThread; the twenty-field
instance becomes nine named parts (the state, the file, the threads, the keys, the topics, the two
pools, the writer handshake, the counters), each its own struct; RecorderTimestamp becomes
MonotonicNs so the clock is in the type.
**Conclusion of the two reads.** The mechanism is obvious enough: an outsider rebuilt the ring, the
runs, the pools, the writer and the threads from code alone and guessed the orderings right. The
policy and the file are not in the code, and the design still has the fourteen defects of the first
read. The next draft puts the file contract and the rules into headers, renames for the audience,
splits the instance, fixes the fourteen, and is tested blind again, comment-free, before the owner reads.

## The third blind read (2026-10-19): draft 9, comments removed
A fresh reader, eleven comment-free headers (record_file.h new), nothing else. Overall 68 %. Of 365
names: 272 CLEAR, 87 GUESS, 6 OPAQUE. The reconstruction: the session scratchpad,
blind3/reconstruction-2026-10-19-c-no-comments.md.
| section | draft 7, with comments | draft 8, no comments | draft 9, no comments |
|---|---|---|---|
| the job | 95 | 85 | 90 |
| the picture | 90 | 75 | 80 |
| the lifetime | 75 | 60 | 60 |
| the contracts | 90 | 70 | 70 |
| the hot path | 85 | 60 | 65 |
| the failures | 65 | 50 | 50 |
| the file | 45 | 35 | 60 |
| the concurrency | 85 | 75 | 75 |
| overall | 72 | 65 | 68 |
The file rose from 35 to 60: record_file.h worked. The six opaque names and the three code gaps it
named were fixed the same hour: the string tables and the open flags are macros in record_file.h;
EVENT_KEY_FIELDS exists; the health names say their trigger (m_registersRefused,
mb_lastWriteFailed); LineAwaitingRetry; m_oldestReadyFramePublishedAt; FlushInDie's unusedCtx; the
writer makes the channel folder. What stays under 70 without comments is policy: what a die handler
is, what Destroy does past its timeout, a thread that exits, the flight budget's check. Code cannot
carry those without a comment or a document. The mechanism reads at 80 to 90 from code alone.

