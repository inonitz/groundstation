# The frame source (rev5 module 12): the review record

Scope: docs/api-harden2/rev5/modules/12-frame_source/frame_source.md, frame_source.h,
frame_source_internal.h. Three rounds, one reviewer each (general-purpose agent, model opus).
Each round: the reviewer's section, then the author's answer. The conclusions close the file.

## Round 1: reviewer

Scope: modules/12-frame_source/frame_source.md, frame_source.h and frame_source_internal.h.
I read the contracts below them: the frame buffer (its two headers and framebuffer.md), runtime
(its two headers and runtime.md), recorder.h, the architecture document sections 3, 6, 8 and 9,
today's video/*.py, the receiver node rx_node.cpp, runtime/ros.py, the brief sections 3 and 4,
and the gate. I read the three lenses in turn: storage and hardware; concurrency and real time;
YAGNI and decoupling. The machine: 32 threads, Python 3.12.3, opencv-python 4.11.0, ROS 2 Jazzy
rclpy with rmw_fastrtps_cpp. ROS ran on domain 88, localhost only. The drone stream came only
from tools/dji_mock/video_tcp_mock.py on 127.0.0.1:5600 and the owner's receiver. The webcam
ran under tools/lock.sh. My scripts are in the session scratchpad, folder review1/: t1.py and
run_t1.sh, run_t2.sh (the take and its page faults), b1.py with h1.py and run_h1.sh (the
receiver and the bridge, CPU and memory), ff1.py with run_ff1.sh (OpenCV on the TCP stream),
w2.py (the webcam's opens). No command reached any aircraft. Nothing was sent but video reads.
Port 5600 was free before and after; the mock and the receiver were stopped.

### Sources
1. https://raw.githubusercontent.com/ros2/rclpy/jazzy/rclpy/src/rclpy/subscription.cpp :
   take_message calls `rcl_take(...)`, then `convert_to_py(taken_msg.get(), pymsg_type)`; the raw
   path calls `rcl_take_serialized_message(...)`, then `py::bytes(...)`. No
   `py::gil_scoped_release` wraps any of them.
2. https://raw.githubusercontent.com/opencv/opencv/4.11.0/modules/python/src2/cv2_util.hpp :
   `#define ERRWRAP2(expr) try { PyAllowThreads allowThreads; expr; } ...` and
   `PyAllowThreads() : _state(PyEval_SaveThread()) {}`.
3. OpenCV 4.11.0 modules/videoio/src/cap_v4l.cpp (the copy in the author's scratch folder),
   line 1037: `getConfigurationParameterSizeT("OPENCV_VIDEOIO_V4L_SELECT_TIMEOUT", 10)`; line
   2082: `frame.copyTo(ret);`.
4. https://man7.org/linux/man-pages/man3/mallopt.3.html : "When blocks larger than the current
   threshold and less than or equal to DEFAULT_MMAP_THRESHOLD_MAX are freed, the threshold is
   adjusted upward to the size of the freed block." Also: "Dynamic adjustment of the mmap
   threshold is disabled if any of the M_TRIM_THRESHOLD, M_TOP_PAD, M_MMAP_THRESHOLD, or
   M_MMAP_MAX parameters is set."
5. https://sourceware.org/glibc/manual/latest/html_node/Memory-Allocation-Tunables.html :
   glibc.malloc.mmap_threshold: "When this tunable is set, all chunks larger than this value in
   bytes are allocated outside the normal heap, using the mmap system call." Once set, "the
   dynamic adjustment is disabled and the value is set as static." The same for
   glibc.malloc.trim_threshold.
6. rx_node.cpp line 15: `create_publisher<CameraPipelineMsgType>(kOutCameraPipelineRawFrameTopic, 10)`.
   runtime/ros.py: `self._node.create_subscription(msg_type, topic, callback, 10)`.
7. framebuffer.md section 7, "Mutable state": "The writer's thread, its write-open flag and its
   last count of held slots: the writer thread's ... The health read loads them." Section 8:
   "The health's latest sequence is the writer's own count."

### Findings

**R1-1. Most of the 9 ms take is page faults, and one environment addition cuts it by 4.7 times.** (medium; cause: SEEN)
- Claim: section 8 says "The take's cost is in the middleware". It is mostly the kernel's
  page faults. Each take allocates fresh 6 MB buffers and touches every page.
- Evidence (t1.py, a synthetic 1080p publisher at 30 a second): the typed take costs 8728 us
  median, 10851 us p99, with 4525 minor faults per take. The raw take: 8389 us, 4524 faults.
  4525 faults are three 6.2 MB buffers of 4 KiB pages.
- Evidence (the same, with `GLIBC_TUNABLES=glibc.malloc.mmap_threshold=67108864:glibc.malloc.trim_threshold=268435456`):
  the typed take costs 1868 us median, 3403 us p99, 0 faults, in two runs. The raw take:
  1967 us median.
- Evidence (h1.py: the mock, the real receiver and a 12-slot bridge, 10 s): the bridge used
  41.9 % of a core and took 135776 faults a second. Tuned: 14.4 % of a core and 0 faults.
  Both delivered 30 frames a second. The tuning raised the bridge's private memory from 39 to
  63 MiB. The receiver used 63.7 % of a core either way; it takes almost no faults.
- Evidence: sources 4 and 5 describe the mechanism: a static threshold keeps the 6 MB blocks
  in the heap and stops the trim that returns them. Why the dynamic threshold does not
  settle on its own here is unverified.
- Why it matters: the drone path costs about 106 % of a core today (receiver plus bridge).
  The tuning makes it about 78 %. Power per flight is a force for the field target.
- Why it matters: it does not save option (c). Tuned, the in-app subscription still stalls
  the main thread: p99 4027 us, max 6586 us (d1.py beside the 1 ms sleep probe). The budget is
  330 us. So the bridge's need stands.
- Change: the bridge spec's env gets one more addition, the GLIBC_TUNABLES string, from config
  (RUN16). Correct the note in section 8 and the bridge's cost in OPEN 1 and item 9.

**R1-2. OpenCV can read the phone's TCP stream directly into a slot, with no receiver and no bridge.** (medium; cause: SEEN)
- Claim: OPEN 1 lists the bridge, the receiver writing the block, and the in-app
  subscription. It omits the file kind's own path on the drone's stream.
- Evidence (ff1.py against the mock on 127.0.0.1:5600): `cv2.VideoCapture("tcp://127.0.0.1:5600", cv2.CAP_FFMPEG)`
  opened the stream. A thread read 30.1 frames a second at 1920x1080, all 301 into the slot.
  The read thread's CPU was 8611 us median a frame. The whole process used 41.3 % of a core.
  The main thread's gap: p99 1063 us, max 1141 us, at the baseline.
- Evidence: the drone path with the bridge measured 106 % of a core, or 78 % tuned (R1-1).
- Cost found: the open took 5.3 s, which looks like FFmpeg's default stream analysis; options
  to shorten it are unverified. The decode latency against the receiver's
  `max-threads=1` is unverified. A stream end needs a reopen in the capture thread, which is
  OPEN 4's mechanism applied to the drone.
- Why it matters: this path needs no OPEN 2, no bridge spec, no receiver spec, and no graph
  probe from OPEN 3. It removes R1-3, R1-4 and R1-5 below.
- Why it matters: it goes against RVW5 (2026-10-12): "The reason we used gstreamer in a
  standalone ROS2 node was for us to easily have an input source for image data that is
  uniform across all platforms". The choice is the owner's.
- Change: add it to OPEN 1 as option (d), with these numbers and RVW5 named. No
  recommendation from me against the ruling.

**R1-3. In a drone run, the app's frame buffer health stops at its first values.** (medium; cause: DESIGNED)
- Claim: the health's held-slot count is the writer's own value in its process memory
  (source 7). In a drone run the writer is the bridge, with its own handle (OPEN 2). The
  app's handle never writes, so its count stays 0.
- Claim: source 7 also says the health's latest sequence is "the writer's own count". If so,
  it stays at its first value too.
- Why it matters: the screen reads the health each frame and posts a chat line on a change
  (framebuffer.md section 3). In every drone run, the flight case, it shows no held slots. The
  FR1 early warning is blind exactly where it matters.
- Why it matters: OPEN 2's text does not name this. The owner would approve OPEN 2 without it.
- Change: name the fact in OPEN 2 and carry it to the frame buffer. The smallest option there:
  the app's ReadHealth counts the held slots from the 12 counts in the block. That is 12
  atomic loads, a few us each in Python (unverified), so once a second from Poll, not each
  frame.

**R1-4. A drone frame of another size is invisible to the app, so the matrix row claims what the design cannot do.** (medium; cause: DESIGNED)
- Claim: the matrix row "a frame of another size" names "the phone's stream setting" as its
  DESIGNED trigger. It says "the row's detail names it".
- Claim: for the drone, the rejected count lives in the bridge process (FrameBridge
  m_rejected). DroneSource has no counter. RecordVideoRow gets 0 rejected.
- Trace: the phone sends 1280x720. The bridge drops every frame and logs one line. Poll sees
  no new sequence. After 6 s the row says "no frame for 7 s". The receiver restarts every
  15 s for the rest of the run. Each restart cannot help.
- Why it matters: the operator sees a stall, not the cause. The log line is in a file nobody
  watches mid-flight.
- Change, the smallest: correct the row for the drone: the row reads RECOVERING with "no
  frame", the cause is in proc-frame_bridge.log. If the owner wants the cause on screen, that
  is a new mechanism and an open point. If the trigger cannot happen with the DJI app, drop
  it, and this finding becomes low.

**R1-5. With the bridge, the frame buffer's Die runs in the bridge, so the hand-over waits for the restart budget.** (low; cause: none)
- Claim: the matrix row "every slot held" says "Die inside BeginWrite" and "the hand-over
  first". In a drone run, BeginWrite runs in the bridge. The bridge has no hand-over
  registered. Its Die is the banner and an exit.
- Trace: the supervisor sees a crash. It relaunches after 1.5 s, 3 s and 4.5 s. Each new
  bridge dies on its first frame. Only then does BUDGET_SPENT_DIE end the app with the
  hand-over: about 9 s plus three starts (unverified).
- Why it matters: RVW4 asks for the hand-over at our own bug mid-flight. The cause of the
  trigger is a bug, with no SEEN or DESIGNED cause, so this is low.
- Change: correct the row for the drone. No mechanism.

**R1-6. "No queue" is not true for the drone: two DDS histories of depth 10 sit between the decode and the slot.** (low; cause: none)
- Claim: the receiver publishes reliable with depth 10 (source 6). Today's subscription helper
  uses depth 10. RosSubscriptionCreate takes no depth, so the bridge inherits it.
- Why it matters: if the bridge falls behind, it writes frames up to 10 periods old, 333 ms.
  FR1 asks for the latest frame. No cause is seen: the bridge needs 10.7 ms of each 33 ms.
- Change: name the two queues, their depth and their policy in the picture and in item 1. No
  mechanism.

**R1-7. The bridge's 72 MiB figure was measured with a one-slot block.** (low; cause: SEEN)
- Evidence: fs/bridge_parent.py maps 4096 bytes plus one slot. With 12 slots mapped and
  populated (b1.py): VmRSS 144 MiB, of which 72 MiB is the shared block and 39 MiB private.
  Tuned (R1-1): 63 MiB private.
- Why it matters: the block is the app's memory, counted once. The bridge's own cost is the
  private part. A reader of "72 MiB resident" will compare the wrong numbers.
- Change: state the private memory, 39 MiB, or 63 MiB with R1-1.

**R1-8. The drone stall row's "SEEN: the sessions" has no session line behind it.** (low; cause: none)
- Evidence: I searched the 57 session folders in logs/sessions for "stall", "RECOVERING" and
  "restarting gstreamer". No line matched.
- Why it matters: item 12 accepts a log line, a measurement in normal use, or the owner's word.
  "The guard exists" is none of these.
- Change: cite the requirement instead: architecture section 9, "The video stalls: a planned
  restart after 6 s." A ruling stands outside the item 12 test. The second row, "no video server
  when the receiver launches", fits DESIGNED: the operator starts the app before the phone's
  server.

**R1-9. The webcam opens three times at start, about 1 s each.** (low; cause: SEEN)
- Evidence (w2.py, webcam 0 at 1280x720 MJPG, three cycles): open and set 141 to 245 ms, the
  first read 778 to 781 ms, the release 5 to 6 ms. Webcam 2: 0.65 to 0.95 s a cycle, its
  release up to 249 ms. An immediate reopen succeeded in all 6 cycles.
- Claim: the preflight calls FrameSourceProbeSize, the app calls it again, and Create opens
  once more. The app's own probe already dies at start with the reason.
- Why it matters: about 1 s of start time for no new check. The preflight call is also a
  carried change to runtime, an approved module.
- Change: drop the preflight's call; keep the app's probe. Handing the probe's open device to
  Create would save one more second and close TOCTOU 3; that is an API change, the author's
  choice.

**R1-10. Two header structs carry fields that one kind never uses.** (low; cause: none)
- Claim: FrameSourceHandle holds m_kind and two pointers, one always NULL; CaptureSource
  repeats m_kind.
- Claim: FrameSourceSpecText serves both specs. The receiver never uses m_passFds or
  m_number. The bridge's PYTHONPATH string has no field named for it; m_libraryPath is
  the only candidate.
- Why it matters: the header must read without its comments (RUN3). A reader cannot tell which
  field each spec fills.
- Change: name the env field for what it holds (for example m_envAddition). Keep the handle as
  it is if the layout tool rules out a union; say so in one line.

### Checks that passed
- OpenCV's read releases the GIL. ERRWRAP2 holds a PyAllowThreads around the call (source 2).
  So the webcam and file reads into the slot run without the GIL, as item 8 says.
- rclpy's take holds the GIL for the whole take and the conversion (source 1). The bridge's
  premise holds.
- The bridge removes the main-thread stall. My in-app runs, default and tuned, stalled the
  main thread 6.6 to 13.3 ms at max; with the bridge the app's process takes no frame work.
- The 10 s V4L2 select timeout in FrameSourceDestroy's comment matches OpenCV's source
  (source 3, line 1037).
- The receiver relaunch path: the bridge kept 30.0 frames a second into the slot in both h1
  runs; the receiver stopped on SIGINT each time.
- TOCTOU 3: a release, then an immediate reopen, gave the same 1280x720 size in 6 of 6 cycles
  on two webcams.
- The stop order (the source, the supervisor, the buffer) leaves no writer behind for the
  webcam, the file and the drone. The bridge's executor join covers a callback in flight, so
  a graceful stop never leaves a slot WRITING.
- The sequence (uint32 at 30 a second, 4.5 years) and every `now - earlier` compare on
  RecorderTimestamp hold under wrap-around for any run length.
- The claim held across the blocking read fits the slot count: the frame buffer already counts
  one slot under write (FB5). No reader can see it: the sequence is 0 while it is WRITING.
- Every number I could not measure is marked unverified above.

## Round 1: answer
Every change below is applied to frame_source.md, frame_source.h and frame_source_internal.h.
Both headers compile with -Wall -Wextra -std=c11 -Wpedantic; the layout tool changes nothing.

- **R1-1. Accepted.** Cause: SEEN (a measurement in normal use). Evidence: the reviewer's
  t1.py and h1.py; re-measured by the author: the typed take 8866 us median without the
  tunables, 1864 us with them; the main thread in the app still 3130 us p99, 4480 us max.
  Change: the bridge's env gets config's GLIBC_TUNABLES string, an addition (RUN16); a named
  field FrameBridgeSpecText.m_mallocTunablesEnv; OPEN 1, item 9 and section 8 corrected (the
  take is mostly page faults; the bridge 14.4 % of a core; the in-app path still fails).
- **R1-2. Accepted as information, narrowed.** Cause: SEEN (measured on the mock). Change:
  OPEN 1 gets option (d) with its numbers, its costs (the 5.3 s open, a reopen path, the
  latency unverified) and RVW5 named. The recommendation stays the bridge: the ruling keeps
  the receiver as the uniform source, and only the owner revisits a ruling.
- **R1-3. Accepted.** Cause: DESIGNED (the screen reads the health each frame in every drone
  run; the trace through framebuffer.md section 7). Change: OPEN 2 names the fact and carries
  the fix to the frame buffer: a non-writer handle reads the held slots and the latest
  sequence from the block.
- **R1-4. Accepted, narrowed.** Cause: for the drone, none: 1920x1080 is a given (the brief);
  the author's "the phone's stream setting" had no evidence. For the webcam and the file:
  DESIGNED (the probe, then the reopen). Change: the matrix splits the row; the drone row
  says what happens (the app sees no frame, the receiver restarts to no effect, the cause in
  proc-frame_bridge.log). No mechanism.
- **R1-5. Accepted (text).** Cause: none (FR1 is our bug). Change: the matrix row says the
  bridge's Die is a banner and an exit, and the app's hand-over comes at the budget's end.
- **R1-6. Accepted (text).** Cause: none for a late bridge. Change: the picture, item 1 and a
  matrix row name the two DDS histories, keep-last 10, reliable; a note on why depth 10
  (best effort depth 1 delivered 18.6 frames a second, measured).
- **R1-7. Accepted.** Cause: SEEN (measured). Change: 39 MiB private, 63 MiB with the
  tunables; the block is the app's, shared.
- **R1-8. Accepted.** Cause: the row had none. Change: the stall row stands on the requirement
  (architecture section 9); the no-server row is DESIGNED with the measured trace.
- **R1-9. Accepted in part.** Cause: SEEN (measured, about 1 s an open). Change: the preflight
  makes no camera check; the app's probe is the one check. Rejected: handing the probe's open
  device to Create; it adds a second state across the recorder's and the buffer's creation,
  and the per-frame check covers TOCTOU 3 (6 of 6 reopens the same size).
- **R1-10. Accepted.** Cause: none needed (RUN3, the header reads without comments). Change:
  GstreamerRxSpecText and FrameBridgeSpecText, each with its own named fields; CaptureSource's
  m_kind replaced by mb_isFile; the handle's two pointers kept, with the reason in its comment.

## Round 2: reviewer

Scope: frame_source.md, frame_source.h and frame_source_internal.h as they stand after the
round-1 answer. I read the round-1 record, the brief sections 3 and 4, and the gate items 1 to
12. I read the contracts below: the frame buffer's two headers and framebuffer.md, runtime.h,
runtime_internal.h and runtime.md, and recorder.h. I read the architecture document sections
3, 6, 8 and 9, today's video/*.py and the receiver rx_node.cpp. I re-checked the three
mechanisms round 1 added, then read the design through the three lenses. The machine: AMD
Ryzen 9 8940HX, 32 threads, glibc 2.39, Python 3.12.3, opencv-python 4.11.0, numpy 1.26.4, ROS
2 Jazzy with rmw_fastrtps_cpp, domain 89, localhost only. The drone stream came only from the
unmodified tools/dji_mock/video_tcp_mock.py on 127.0.0.1:5600 and the owner's receiver. I did
not use the webcam. My scripts are in the session scratchpad, folder review2/: run_m1.sh (the
take under each tunable), m2.py with run_m2.sh (40 minutes of the drone path, two bridges),
m5.py with clipref.py and run_m5.sh, run_m6.sh (the latency of each path), run_o1.sh (the
FFmpeg open time), a1.py (the health fix's atomic loads, with atomics 1.0.3 installed into
review2/pylib only). No command reached any aircraft. Nothing was sent but video reads. Port
5600 was free before and after each run; the mock and the receiver were stopped each time.

### Re-check of the round-1 mechanisms
**1. The GLIBC_TUNABLES addition in the bridge's spec.**
- Cause: SEEN. A measurement in normal use: the bridge's CPU, 41.9 % of a core against
  14.4 % (R1-1, re-measured by the author).
- Verdict: the cause holds. The mechanism is right. Both settings are needed.
- Evidence (run_m1.sh, a 1080p publisher at 30 a second, the typed take):

  | GLIBC_TUNABLES | take median / p99 us | faults a take |
  |---|---|---|
  | none | 8958 / 12447 | 4525 |
  | mmap_threshold 64 MiB only | 9084 / 14841 | 4526 |
  | trim_threshold 256 MiB only | 9668 / 12778 | 4557 |
  | both (the spec) | 1990 / 3317 | 0 |
  | mmap_threshold 32 MiB, trim_threshold 256 MiB | 2173 / 3761 | 0 |
- Evidence: the source explains why the default does not settle (R1-1 left it unverified).
  The first free of a mapped chunk raises the threshold to that chunk and sets the trim
  threshold to twice it (source 3). A thread's arena tries a trim on every large free (source
  4). So 12.4 MB of free space at the top goes back to the kernel, and the next take faults it
  in again. Each setting alone switches the dynamic rule off and leaves the other at 128 KiB.
- Evidence (m2.py, 40 minutes, 72000 frames into each block): the tuned bridge's anonymous
  memory was 105 MiB from 270 s to 2400 s, flat. No growth and no fragmentation showed. The
  untuned bridge moved between 81 and 98 MiB. CPU in steady state: 10 to 12 % against 32 to
  34 % of a core.
- Breaks nothing found in this module. Two costs are wrong or unnamed: the memory figure
  (R2-3) and a value above glibc's documented limit (R2-4).

**2. The frame buffer health fix carried in OPEN 2.**
- Cause, for the held slots: DESIGNED. The app's m_slotsHeld is stored only by BeginWrite. In
  a drone run the app's handle never calls it. The screen reads the health each frame. The
  trace holds.
- Cause, for the latest sequence: none. The frame buffer keeps no writer copy of it since FB7
  (R2-5).
- Verdict: the held-slot half stands. Its cost and its caller are wrong in OPEN 2 (R2-2).
- Evidence (a1.py): 14 loads cost 60 us median, 79 to 111 us at p99, 210 to 395 us at max.
  One load costs 4.1 to 4.3 us. OPEN 2 says "a few us each (unverified), once a second". The
  screen calls the health every frame (framebuffer.md section 3).

**3. Option (d) in OPEN 1: OpenCV's FFMPEG backend reading tcp:// in the capture thread.**
- Cause: SEEN. Measured on the mock (R1-2).
- Verdict: the option is real. Its numbers were taken with OpenCV's default of 16 decoder
  threads. That default delays every picture by about half a second (R2-1).
- Evidence (m5.py): with one decoder thread, the latency is 13 ms median and the process uses
  48.6 % of a core. With 16 threads it is 500 ms median.
- Evidence (run_o1.sh): four sets of FFmpeg probe options left the 5.3 s open unchanged. Its
  cause is unverified.
- It breaks RVW5, as OPEN 1 already says.

### Sources
1. https://raw.githubusercontent.com/bminor/glibc/release/2.39/master/malloc/malloc.c, line
   5445: `do_set_mmap_threshold (size_t value)` sets `mp_.mmap_threshold = value;` and
   `mp_.no_dyn_threshold = 1;` with no upper check.
2. https://raw.githubusercontent.com/bminor/glibc/release/2.34/master/malloc/malloc.c, line
   5218: `/* Forbid setting the threshold too high.  */` then `if (value <= HEAP_MAX_SIZE / 2)`.
   The same check is in 2.31, 2.32 and 2.33; it is gone in 2.35 to 2.39 (fetched each).
3. The same file as source 1, lines 3379 to 3384, in `__libc_free`: `if (!mp_.no_dyn_threshold
   && chunksize_nomask (p) > mp_.mmap_threshold ...` then `mp_.mmap_threshold = chunksize (p);`
   and `mp_.trim_threshold = 2 * mp_.mmap_threshold;`.
4. The same file, line 4790: `/* Always try heap_trim, even if the top chunk is not large,`.
   https://raw.githubusercontent.com/bminor/glibc/release/2.39/master/malloc/arena.c, line 586,
   in heap_trim: `if ((unsigned long)(top_size) < (unsigned long)(mp_.trim_threshold))`.
5. https://man7.org/linux/man-pages/man3/mallopt.3.html, M_MMAP_THRESHOLD: "The upper limit is
   DEFAULT_MMAP_THRESHOLD_MAX: 512*1024 on 32-bit systems or 4*1024*1024*sizeof(long) on 64-bit
   systems."
6. https://sourceware.org/glibc/manual/latest/html_node/Memory-Allocation-Tunables.html,
   glibc.malloc.mmap_threshold: "When this tunable is set, all chunks larger than this value in
   bytes are allocated outside the normal heap, using the mmap system call."
7. https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-2000.rst, Jazzy Jalisco:
   Ubuntu Noble (24.04) "amd64 | Tier 1" and "arm64 | Tier 1".
8. https://raw.githubusercontent.com/opencv/opencv/4.11.0/modules/videoio/src/cap_ffmpeg_impl.hpp,
   fill_codec_context: `int requestedThreads = std::min(nCpus, 16);`. Line 262:
   `#define LIBAVFORMAT_INTERRUPT_READ_DEFAULT_TIMEOUT_MS 30000`.
9. https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/doc/multithreading.txt, frame
   threading: "There is one frame of delay added for every thread beyond the first one."
10. ../04-framebuffer/framebuffer.md, section 3: `health = framebuffer_read_health(frames)  #
    four plain loads; a change -> a chat line`, in the screen's per-frame code. Section 8: "The
    main thread reads four plain values, no atomic call (round 1, R1-7). Rejected: 14 atomic
    loads per frame on the main thread."
11. ../04-framebuffer/framebuffer_internal.h, struct Framebuffer: the fields m_slotsHeld,
    m_retries and m_misses, and no sequence; "The next sequence is the latest slot's sequence
    plus 1 (FB7: no copies)".

### Findings

**R2-1. Option (d) was measured with 16 decoder threads, which delay every frame by about half a second; with one thread it has the lowest latency of the three paths.** (medium; cause: SEEN)
- Claim: OpenCV gives FFmpeg min(CPUs, 16) decoder threads by default (source 8). Frame
  threading adds one frame of delay per thread beyond the first (source 9). At 30 frames a
  second, 15 frames are 500 ms.
- Claim: OPEN 1 lists (d) at 30.1 frames a second and 41 % of a core, with the latency
  unverified. Those numbers are the 16-thread configuration (R1-2's ff1.py passes no thread
  count).
- Evidence (m5.py, two runs each): each frame read is matched to its clip index by a
  thumbnail. Its send time is the mock's accept time plus the byte offset where its access
  unit ends, over the mock's byte rate. Frames after the first 12 s only.

  | path | latency median / p99 / max ms | CPU, % of a core |
  |---|---|---|
  | OpenCV FFMPEG, 16 threads (the default) | 497 to 500 / 782 to 787 / 785 to 802 | 44.7 (process) |
  | OpenCV FFMPEG, CAP_PROP_N_THREADS 1 | 13 to 14 / 46 to 67 / 89 to 114 | 48.6 (process) |
  | the receiver, camera/stream, a tuned rclpy subscription | 29 to 34 / 45 to 50 / 47 to 57 | 63.7 + 14.4 (R1-1) |
- Evidence: the receiver row in the last run counts 352 frames that matched one clip frame
  clearly. 150 of 772 matched two clip frames within 0.5 grey levels, so I left them out.
- Evidence: the one-thread read costs 13.1 ms of the thread's CPU a frame, 17.0 ms at max. It
  keeps up with 33 ms frames.
- Evidence: the default read timeout is 30 s (source 8). A read on a stalled stream holds the
  thread, and Destroy's join, up to 30 s. The header's join comment names 10 s, the V4L2 value.
- Why it matters: the owner weighs OPEN 1 on these numbers. As written, (d) looks like a CPU
  win with an unknown lag. Taken as measured, it ships a 0.5 s lag on every drone frame.
- Why it matters: with one thread, (d) is lower in latency and in CPU than the bridge path.
  That does not change RVW5; only the owner revisits it.
- Change: OPEN 1 (d) names CAP_PROP_N_THREADS 1 and CAP_PROP_READ_TIMEOUT_MSEC, and gives the
  three latency rows above. Item 9 gets the receiver path's latency, which no row has today.

**R2-2. The carried health fix costs 60 us a read, and the screen reads the health every frame, which the frame buffer already rejected.** (medium; cause: DESIGNED)
- Claim: OPEN 2 says the 14 loads run "once a second". Nothing in this design moves the
  screen's per-frame health read (source 10).
- Evidence (a1.py, atomics 1.0.3 views entered once, 20000 reads, two runs): 60.3 and 60.7 us
  median; 110.9 and 78.8 us at p99; 394.9 and 210.2 us at max.
- Why it matters: at 30 reads a second the main thread spends 1.8 ms a second. The worst read
  passes the 330 us budget of a call.
- Why it matters: the frame buffer rejected exactly this, "14 atomic loads per frame on the
  main thread" (source 10). OPEN 2 would bring it back without saying so.
- Claim: "when its handle is not the writer" has no test named. The app's m_writerThread is 0
  in a drone run, and also in a webcam run before the first BeginWrite. It is the writer
  thread's own plain field, so the main thread reading it is a read of another thread's
  non-atomic value.
- Change: OPEN 2 states the measured cost and the rate. The scan runs on the main thread once
  a second, beside Poll, and the screen's per-frame read stays four plain values. The role of
  the handle is fixed at Create, not read from m_writerThread. The frame buffer chooses the
  call; this module carries the numbers.

**R2-3. The bridge's private memory is 105 MiB in steady state, not 63 MiB, and it stays flat for 40 minutes.** (low; cause: SEEN)
- Evidence (m2.py, one receiver, a tuned and an untuned bridge, each with its own 12-slot
  block, every 30 s): at 30 s, 63 and 51 MiB anonymous; from 270 s to 2400 s, 105 MiB tuned,
  flat; 81 to 98 MiB untuned. Each bridge wrote 72000 frames, 30.0 a second.
- Evidence: the receiver's anonymous memory was 167 MiB from 270 s to 1950 s, then 180 and
  182 MiB. It served two subscribers in this run. The cause is unverified and outside this
  module.
- Why it matters: the 39 and 63 MiB figures are 15 s snapshots, before the memory settles.
  The tunables cost about 18 MiB in steady state, not 24.
- Why it matters: the 40-minute question is closed: no growth with the tunables.
- Change: OPEN 1, item 9 and section 8 state 105 MiB in steady state with the tunables, 81 to
  98 MiB without, measured over 40 minutes.

**R2-4. The spec's 64 MiB mmap threshold is above glibc's documented limit of 32 MiB; glibc 2.31 to 2.34 drop it, and the trim setting then makes the take worse.** (low; cause: none)
- Evidence: the mallopt page gives 32 MiB as the upper limit on 64-bit (source 5). glibc 2.31
  to 2.34 refuse a larger value (source 2). glibc 2.35 and later accept it (source 1).
- Evidence (run_m1.sh): the trim setting alone, which is what an older glibc keeps, gives 9668
  us and 4557 faults a take. 32 MiB with the same trim setting gives 2173 us and 0 faults.
- Why it matters: the fallback is silent. The bridge goes back to about 42 % of a core, and
  nothing reports it.
- Why it is low: ROS 2 Jazzy's Tier 1 is Ubuntu 24.04 (source 7). This machine runs Ubuntu
  24.04.4 with glibc 2.39. A binary Jazzy install has no older glibc.
- Change: config's string uses mmap_threshold=33554432. It is equal in effect here and valid
  on every glibc. No check is added.

**R2-5. The latest-sequence half of the health fix has no target.** (low; cause: none)
- Claim: after FB7 the frame buffer keeps no copy of the sequence (source 11). Its health can
  only read the latest sequence from the block, for any handle.
- Evidence: framebuffer.md section 8 still says "The health's latest sequence is the writer's
  own count". That line predates FB7. The struct has no field for it.
- Why it matters: OPEN 2 asks the frame buffer for a change it may already have. The manager
  carries two items where one is real.
- Change: OPEN 2 carries the held-slot count only, and names the stale framebuffer.md line
  for the frame buffer to correct.

**R2-6. Section 8 still gives the untuned take as the delay before the bridge's capture stamp.** (low; cause: none)
- Claim: the note "Why the capture time is RecorderNow() after the read" says the stamp "comes
  after the 9 to 10 ms take". With the tunables in the spec, the take is 1.9 ms (item 9).
- Change: 1.9 ms, with the tunables.

### Checks that passed
- Both tunables are needed, and the pair removes every fault of the take (re-check 1).
- No memory growth with the tunables over 40 minutes and 72000 frames (R2-3).
- The tunables reach only the bridge, through its spec's env addition (RUN16). /usr/bin/setpriv
  is not set-user-ID (mode 0755 here), so glibc passes GLIBC_TUNABLES on to python3.
- SupervisorRestartOnPurpose is a request through the supervisor's command pipe
  (runtime.md). Poll never waits for the receiver's 10 s grace.
- The argv fits kFrameSourceArgvMax: the supervisor adds the setpriv prefix itself
  (runtime_internal.h, kSupervisorArgvPrefix). The env arrays of 2 and 3 hold their additions
  and the NULL. The tunables string is 89 characters plus the NUL, under 128.
- Two bridges never write at once: the supervisor relaunches only after the pidfd reports the
  exit, so the per-handle writer check is enough.
- The rclpy executor of RosSubscriptionCreate is single-threaded on one thread (runtime.h).
  Every callback runs on the same thread, so the bridge's writer-thread check holds.
- The receiver path delivers a frame 29 to 34 ms after its access unit leaves the mock, p99
  under 51 ms. The bridge adds no queue age in normal use (R1-6 holds).
- TOCTOU 1 to 7 are named with what closes each. I found no unnamed check-then-act in the
  three files.
- Every number above that I did not measure is marked unverified.

## Round 2: answer
The re-check of the three round-1 mechanisms: the tunables keep their SEEN cause (both
settings needed; flat memory over 40 minutes); the health fix keeps a DESIGNED cause for the
held slots only; option (d) keeps its SEEN cause, with corrected numbers. Every change below
is applied; the header compiles with -Wall -Wextra -std=c11 -Wpedantic; the layout tool
changes nothing.

- **R2-1. Accepted.** Cause: SEEN (measured on the mock, two runs). Change: OPEN 1 (d) names
  CAP_PROP_N_THREADS 1 and the 30 s read timeout; item 9 gets the latency table of the three
  paths, the design's included. The recommendation stays the bridge, and the document now
  says plainly that on the numbers alone (d) wins. The reason it stays: RVW5 stands, and its
  reason is live: the owner's C++ fmu_node subscribes to camera/stream (fmu_node.hpp line
  256), the system harden2 folds into later. If the owner revisits RVW5 for harden2, (d) is
  the author's pick.
- **R2-2. Accepted.** Cause: DESIGNED (the screen's per-frame health read in every drone run).
  Change: OPEN 2 carries the measured cost (60 us median, 395 us max a scan), the rate (once
  a second, beside Poll), the screen's per-frame read unchanged, and the role fixed at Create.
- **R2-3. Accepted.** Cause: SEEN (measured, 40 minutes). Change: 105 MiB private with the
  tunables, flat; 81 to 98 MiB without; 10 to 14 % of one core.
- **R2-4. Accepted.** Cause: none for an old glibc here; the change is a value, not a
  mechanism. Change: mmap_threshold=33554432, equal in effect here and inside glibc's
  documented limit. No check added.
- **R2-5. Accepted.** Cause: none. Change: OPEN 2 carries the held slots only and names the
  stale framebuffer.md section 8 line.
- **R2-6. Accepted.** Change: the bridge's stamp comes 1.9 ms after the take begins, with the
  tunables.

## Round 3: reviewer

Scope: frame_source.md, frame_source.h and frame_source_internal.h as they stand after the
round-2 answer. I read the round-1 and round-2 records, the brief sections 3, 4, 5 and 8, and
the template and gate items 1 to 12 in modules/README.md. I read the contracts below: the frame
buffer's two headers and framebuffer.md, runtime.h, runtime_internal.h and runtime.md, and
recorder.h with frame_types.h and record_event.h. I read the ledger rows the document cites,
today's video/cam_list.py, fmu_node.hpp and rx_node.cpp. The machine: AMD Ryzen 9 8940HX, 32
threads, glibc 2.39, Python 3.12.3, opencv-python 4.11.0, ROS 2 Jazzy, domain 90, localhost
only. The drone stream came only from the unmodified tools/dji_mock/video_tcp_mock.py on
127.0.0.1:5600 and the owner's receiver with `--dji 127.0.0.1`. I did not use the webcam. My
scripts are in the session scratchpad, folder review3/: run_r3.sh runs t1.py (the take), h1.py
with b1.py (the receiver and a 12-slot bridge) and ff1.py (OpenCV on tcp://, one decoder
thread). No command reached any aircraft. Nothing was sent but video reads. Port 5600 was free
before and after; the mock and the receiver were stopped.

### Re-check of the mechanisms added since round 1
**1. The GLIBC_TUNABLES addition in the bridge's spec (mmap 32 MiB, trim 256 MiB).**
- Cause: SEEN. The bridge's CPU, 41.9 % of a core untuned against 14.4 % tuned (R1-1, R2
  re-check 1). The take is page faults on fresh 6 MB buffers (R2 sources 1 to 4).
- Verdict: the cause holds. The 32 MiB value is right. It is equal in effect to the 64 MiB
  value every bridge figure was measured with.
- Evidence (run_r3.sh, part A, a 1080p publisher at 30 a second, two runs each, one session):

  | GLIBC_TUNABLES | take median / p99 / max us | faults a take, median |
  |---|---|---|
  | mmap 32 MiB + trim 256 MiB (the spec) | 1092 / 1643 / 1704; 1080 / 1580 / 2135 | 0 |
  | mmap 64 MiB + trim 256 MiB | 1113 / 1532 / 2041; 1021 / 1490 / 2447 | 0 |

- Evidence (part B, the mock, the real receiver and a 12-slot bridge, 10 s, two runs each):
  the bridge used 9.9 and 8.2 % of a core with 32 MiB, 9.2 and 9.3 % with 64 MiB. Each took 0
  faults a second and wrote 30.0 frames a second. RssAnon was 63 MiB at 15 s in all four.
- Note: the absolute numbers today are lower than in rounds 1 and 2 (the take 1.1 ms against
  1.9 ms; the receiver 48 % against 63.7 % of a core). The CPU clock differs between
  sessions. The comparison inside one session is the evidence; the document's figures stand
  as the earlier sessions' values.
- Evidence (the limit): glibc 2.34 malloc.c line 5219 accepts `value <= HEAP_MAX_SIZE / 2`.
  glibc 2.34 arena.c defines `HEAP_MAX_SIZE (2 * DEFAULT_MMAP_THRESHOLD_MAX)`, and
  DEFAULT_MMAP_THRESHOLD_MAX is `4 * 1024 * 1024 * sizeof(long)` on 64-bit, so the limit is
  33554432 and the spec's value passes it
  (https://raw.githubusercontent.com/bminor/glibc/release/2.34/master/malloc/arena.c).

**2. The held-slot scan carried to the frame buffer in OPEN 2 (once a second, beside Poll; the
role fixed at Create).**
- Cause: DESIGNED. In a drone run the app's handle never calls BeginWrite, so its stored
  m_slotsHeld stays 0. The screen reads the health each frame (framebuffer.md section 3). The
  trace holds against framebuffer_internal.h: BeginWrite is the only store of m_slotsHeld.
- Verdict: the cause holds for the held slots. The rate and the cost are right (60 us median,
  395 us max, R2-2). Two points of form and simplicity remain (R3-1, R3-3).
- The latest-sequence half is gone, as R2-5 asked. The stale framebuffer.md line is still
  there (line 574: "The health's latest sequence is the writer's own count"), so the carried
  correction is still needed.

**3. Option (d) in OPEN 1: OpenCV's FFMPEG backend reading tcp:// in the capture thread.**
- Cause: SEEN. Measured on the mock (R1-2, R2-1).
- Verdict: the option is right as written. One of its numbers had no measurement in its own
  configuration: "the main thread at its baseline" came from R1-2's run, and R2-1 says that
  run used OpenCV's default threads. I measured it with CAP_PROP_N_THREADS 1.
- Evidence (part C, two runs): 30.9 frames a second, 309 of 309 into the slot; the open 5267
  ms; the read thread 12.3 to 14.3 ms of CPU a frame median; the process 37.5 to 40.3 % of a
  core; the main thread's gap p99 1063 to 1067 us, max 1100 to 1105 us. That is the baseline.

### Landing check
Each accepted answer of rounds 1 and 2, and where it landed.

| answer | applied? | where |
|---|---|---|
| R1-1 the tunables in the bridge's env | yes | frame_source.h FrameBridgeSpecText.m_mallocTunablesEnv, kFrameBridgeEnvMax 3; md OPEN 1, item 7, item 9, section 8 |
| R1-2 option (d) | yes | md OPEN 1 (d), section 8, item 9 rows |
| R1-3 the held-slot fact | yes, then narrowed by R2-2 and R2-5 | md OPEN 2 "A second fact"; section 8 carried list |
| R1-4 the size row split | yes | md matrix: the webcam or file row, the drone row |
| R1-5 the bridge's Die | yes | md matrix "every slot held" |
| R1-6 the two DDS histories | yes | md picture, section 2 prose, item 1, the matrix "falls behind", section 8 depth note |
| R1-7 private memory | yes, superseded by R2-3 | no 39, 63 or 72 MiB figure is left |
| R1-8 the stall row's cause | yes | md matrix rows 1 and 2 |
| R1-9 no preflight probe | yes | md item 6, section 8 carried list; the header names no preflight |
| R1-10 the spec text structs | yes | frame_source.h GstreamerRxSpecText, FrameBridgeSpecText; internal CaptureSource.mb_isFile; the handle's comment |
| R2-1 (d) with one thread | yes | md OPEN 1 (d), item 9 latency table |
| R2-2 the scan's cost and rate | yes | md OPEN 2 |
| R2-3 105 MiB, flat | yes | md OPEN 1, item 9, section 8 |
| R2-4 33554432 | yes | md item 7 and item 9 strings; frame_source.h "32 MiB"; section 8 |
| R2-5 held slots only | yes | md OPEN 2 |
| R2-6 the stamp after the take | yes | md section 8 "1.9 ms with the tunables" |

The names and the constants agree between the document and both headers: the seven
UINT64_C durations (6 s, 15 s, 1 s, 1 s, 0.1 s, 10 s, 10 s), the three names, the topic,
1920x1080, the env array sizes, the five event keys, and every Python call of section 3 against
its C name. The four OPEN marks land: OPEN 1 on FrameBridgeProcessSpec and DroneSourceCreate,
OPEN 3 on both probes, OPEN 4 on WebcamSourceCreate, OPEN 2 in the internal header only
(R3-2). The gaps I found are the findings below.

### Findings

**R3-1. The held-slot scan is a second change to the frame buffer, packed into OPEN 2 as "a second fact".** (low; cause: DESIGNED for the scan, none for the form)
- Claim: OPEN 2 has five bullets. The fourth, "A second fact", carries its own change: a new
  scan, a role fixed at Create, a rate, and a caller.
- Claim: the scan has its own "on no": the app shows no held slot in every drone run. OPEN 2's
  "on no" is a different outcome: the bridge cannot write.
- Claim: no caller is named for the scan. Section 8 carries "Poll once a second" to module 15,
  but not the scan "beside Poll".
- Why it matters: MOD2 is four lines per point, and the guidelines want one topic per item. The
  owner may approve the writer handle and miss that the scan is a second decision.
- Change: OPEN 5 in the four-line form, with its OPEN 5 mark in the header (FrameSourcePoll's
  comment, where it runs). Name module 15 as the scan's caller in section 8.

**R3-2. OPEN 2 has no mark in the public header.** (low; cause: none)
- Claim: OPEN 2 appears only in frame_source_internal.h, on FrameBridge.m_frames.
  frame_source.h's FrameBridgeProcessSpec passes "the block's descriptor passed read-write",
  which is OPEN 2's change, under an OPEN 1 mark only.
- Why it matters: the brief (section 8) asks for every open point marked in the header. The
  public header is the one the owner reads first.
- Change: "OPEN 1, OPEN 2." on FrameBridgeProcessSpec's comment.

**R3-3. The role fixed at Create adds a parameter that a scan for every handle does not need.** (low; cause: none)
- Claim: R2-2 fixed the role at Create so the main thread never reads m_writerThread. A scan
  for every handle, once a second, gives the right count in every kind. The webcam run gets
  the same count from the scan as from m_slotsHeld.
- Evidence: the scan costs 60 us median and 395 us max (R2-2). Once a second, that is 0.006 %
  of the main thread's time, and every call stays under the 330 us budget at the median.
- Why it matters: KISS. A role is a new argument of FramebufferCreate and a branch in the
  health read. The 395 us max passes the budget in both shapes, so the role buys nothing there.
- Change: carry "a scan for every handle, once a second" as the smaller option to the frame
  buffer. The frame buffer chooses. This is a finding against a round-2 mechanism, so its
  cause goes back to R2-2: DESIGNED, unchanged.

**R3-4. Poll takes a hold to read a value the health already gives.** (low; cause: none)
- Claim: Poll step 1 is AcquireLatest, then Release, to learn the latest sequence.
  FramebufferHealthStatus has m_latestSequence, read from the block since FB7 (R2-5).
- Claim: the hold makes Poll a Die path. A second Acquire on a holding thread dies
  (framebuffer.h), so Poll must run only after the draw's release. The header says "holding no
  slot"; module 15 must keep that order.
- Why it matters: a plain read needs no ordering rule and no holder. One once-a-second health
  read could then give both the sequence and the held slots (R3-1).
- Change: Poll reads the health's latest sequence. If the frame buffer keeps the health
  per-frame plain, keep AcquireLatest and say why in section 8.

**R3-5. The internal header's TOCTOU list has six windows; the document has seven.** (low; cause: none)
- Claim: frame_source_internal.h names windows 1 to 6 and "Poll and Destroy". The document's
  row 7, the bridge killed between BeginWrite and EndWrite, is missing. The rulings table says
  "gate item 11, seven windows".
- Change: add window 7 to the header's list, "named, not closed (FORCED)".

**R3-6. Five numbers lack a source, or come from another configuration than the one named.** (low; cause: none)
- "today's load needs about 4" holders (OPEN 2): no measurement or source is named.
- "15 to 30 from a webcam (the room's light)" (section 2): the measurement is 15 to 19.8
  (item 9, section 6 "15 to 20"). 30 is the request, not a measurement.
- "BeginWrite plus EndWrite 54 us median" (sections 6 and 9): it is the frame buffer's 1080p
  figure with 8 slots. The frame buffer says "The 12-slot 1080p numbers are unverified". Its
  720p 12-slot figure is 107 us.
- AcquireLatest plus Release is 25 us in item 1 and 26 us in the picture and item 9. Both are
  the buffer's figures (1080p 8 slots; 720p 12 slots). One number, named once, reads better.
- The latency row "the receiver, camera/stream, the tuned bridge (the design)" was measured by
  m5.py with a tuned rclpy subscription and a numpy copy in one process, not with the bridge
  process and the memfd. The difference is unverified and likely small.
- Change: a source, or "unverified", for each; the row label "a tuned subscription, the
  bridge's shape".

**R3-7. PERF_FRAME names a stage of the retired perf module.** (low; cause: none)
- Claim: the matrix (two rows) and section 8 say "PERF_FRAME's frame age". The recorder
  replaced perf (RCD1); record_span.h names the stage SPAN_FRAME. The brief's update says to
  read SPAN_<x> for PERF_<x>.
- Change: SPAN_FRAME, in all three places.

**R3-8. The row "a webcam or file frame of another size" is labelled DESIGNED, while its own evidence says the trigger was not seen.** (low; cause: none)
- Claim: the cause column says "DESIGNED: the probe, then Create's reopen (6 of 6 reopens gave
  the same size)". The reopen is designed. A size change at the reopen was never seen, and
  6 of 6 is evidence against it.
- Why it matters: item 12 asks each row for its cause. A row that names DESIGNED without a
  trigger that happens weakens the audit the manager runs on the list.
- Why the handling stays: the pointer check is the correct use of `read(dst)`. OpenCV returns
  its own array on a size mismatch and leaves the slot untouched (measured). Without the check,
  EndWrite would publish a slot that holds an old frame. The check is part of the read, not a
  mechanism for this row.
- Change: the cause "no cause seen; the check is the read's own contract (item 8)".

**R3-9. Two cited rulings lack the owner's words in the rulings table.** (low; cause: none)
- Claim: the matrix row "the camera busy at start" and a test name cite "O3 a". The ledger row
  is `O3 | the preflight after down | "option A" | retry the frame read once after about 1 s`.
  O3 is not in the rulings table.
- Claim: the row "MOD1, MOD2, GATE1, DOC1, PAR2" quotes no words. The brief asks the rulings
  section to quote the owner.
- Claim: the matrix calls O3 "SEEN: the owner". The ledger records a choice of an option, which
  item 12 treats as a requirement, not as evidence.
- Change: add O3 with "option A" and its ledger topic; call the row "a requirement: O3 a". Quote
  the words of the five template rulings, or point to the README lines that hold them.

**R3-10. The probe keeps a second home in cam_list.py.** (low; cause: none)
- Claim: section 5 lists "a probe in two places" as wrong today. Item 6 keeps cam_list.py "a
  manual tool". cam_list.py has its own `_probe(index)`: VideoCapture, then read.
- Claim: section 8 drops run.sh's `cam_list.py --selected`. test/test_video.py lines 135 to 149
  test `show_selected`. The change-impact table does not name them.
- Change: cam_list.py calls the module's probe, or section 5 drops the "two places" point. The
  change-impact table names the show_selected tests as deleted or kept.

**R3-11. The bridge spec's two env additions have no named test.** (low; cause: none)
- Claim: the receiver has `test_the_receiver_spec_lists_only_additions`. The bridge has
  `test_the_bridge_spec_passes_the_descriptor_and_its_number`, which names no env.
- Why it matters: a lost or mistyped GLIBC_TUNABLES string fails silently. The bridge goes back
  to about 42 % of a core, and nothing reports it (R2-4).
- Change: the bridge's spec test also checks that m_env holds exactly PYTHONPATH and config's
  GLIBC_TUNABLES string, then the NULL.

**R3-12. The public header carries a measurement and a tooling note.** (low; cause: none)
- Claim: FrameBridgeProcessSpec's comment says "a static 32 MiB malloc threshold: rclpy's take
  of a 1080p frame drops from 8.9 to 1.9 ms, measured". That is a measurement, and it names
  one of two settings. Each setting alone does nothing (R2 re-check 1).
- Claim: FrameSourceHandle's comment says "(two fields, not a union: the layout tool)". That
  is a note about how the header is made.
- Why it matters: the brief asks for no implementation comments in the public header. The
  numbers have their home in item 9.
- Change: "config's GLIBC_TUNABLES (two static malloc thresholds)" in the header; the
  measurement stays in the document. The union note moves to section 8.

**R3-13. FrameBridge has no field for "one log line per new shape".** (low; cause: none)
- Claim: FrameBridgeOnImage logs one line per new shape. That needs the last logged shape.
  FrameBridge holds m_frames, m_size, m_rejected and m_subscription only.
- Why it matters: RUN3, the header reads without its comments.
- Change: `FrameSize m_lastRejectedSize` and the encoding, or "a log line per rejected
  frame, rate-limited by" a named rule.

**R3-14. StallAction's STALL_MARK is not clear without the function's comment.** (low; cause: none)
- Claim: the enum has no comment block above it. MARK means "the row RECOVERING, no restart";
  the name does not say so. The brief asks for comment blocks above enums.
- Change: an @-block above the enum for STALL_MARK and STALL_RESTART, or the name
  STALL_MARK_RECOVERING.

**R3-15. The document has prose lines that the edits left unwrapped.** (low; cause: none)
- Evidence: lines 173 (115 characters), 271 (133), 293 (129), 390 (127) and 496 (141) are
  prose, not table rows. Lines 243 to 245, 375 to 376 and 490 to 492 break mid-sentence into
  short lines of 21 to 55 characters.
- Why it matters: item 10 says "Every line under 90 characters". That holds for the headers;
  the document wraps at about 95 like its siblings, but these lines are edit leftovers.
- Change: rewrap those paragraphs.

### Checks that passed
- Both headers compile with `gcc -fsyntax-only -Wall -Wextra -std=c11 -Wpedantic` and the
  recorder, runtime and perf folders on the include path: no warning.
- header_layout.py on copies of both headers in review3/: no diff against the originals.
- Every header line is under 90 characters (the longest is 89). No non-ASCII character in the
  three files. No em-dash. None of the banned words.
- The job is one sentence without "and". The document follows the MOD1 order: the job, the
  picture, two Python instances, the open points, today, the rulings, the gate with the
  matrix, the notes, the tests. OPEN 4 uses "On seen" for its "on no"; the question is
  "is it seen", so the form fits.
- Every quoted owner sentence in the rulings table is in the ledger word for word (19
  checked by script). The owner's note on the recorder is verbatim in the brief's log.
- `_Atomic` on every shared value: mb_stop, m_failedReads and m_rejectedFrames. The guard and
  the row are the main thread's alone. The bridge's state is one thread's. m_ and mb_ prefixes
  hold. The kinds and StallAction are anonymous `typedef enum`. Every duration is a UINT64_C
  macro.
- frame_source.h declares Framebuffer and FileDescriptorType itself. Including framebuffer.h
  beside it fails today: the two FrameSize types conflict (gcc: "conflicting types for
  FrameSize"). The header's comment names the fix, carried as RCD7. EndWrite takes a
  PerfTimestamp and gets RecorderNow(); both are uint64_t until the fold.
- Every matrix row names a cause or "no cause seen"; the FORCED rows get the generic handling
  only. No mechanism serves a FORCED row.
- The cited code facts hold: fmu_node.hpp line 256 subscribes to the camera topic with depth 10;
  rx_node.cpp publishes it with depth 10; video.py 161 lines, ros_stream.py 80, cam_list.py 125;
  config/constants.py has WATCHDOG_STALL_SECONDS 6.0 and WATCHDOG_RETRY_SECONDS 15.0.
- The stall rule holds on a trace: Create's time as the first "last frame"; the first
  sequence 1 against the initial 0; MARK for the webcam; RESTART first, then every 15 s.
- The argv and env arrays fit their sizes; the tunables string is 89 characters plus the NUL,
  under kFrameSourceEnvBytes 128.
- Every number I did not measure is marked unverified above.

## Round 3: answer
The re-check holds: the tunables keep a SEEN cause (32 MiB measured equal to 64 MiB); the
held-slot scan keeps a DESIGNED cause; option (d) keeps a SEEN cause. Every change below is
applied. Both headers compile with -Wall -Wextra -std=c11 -Wpedantic; the layout tool
changes nothing; no header line passes 89 characters.

- **R3-1. Accepted.** Change: the scan is OPEN 5 in the four-line form, its caller the
  screen (module 15) once a second; the mark in the header at FrameSourcePoll.
- **R3-2. Accepted.** Change: "OPEN 1, OPEN 2." on FrameBridgeProcessSpec.
- **R3-3. Accepted.** Cause traced back to R2-2: DESIGNED, unchanged. Change: OPEN 5 carries
  the smaller option, a scan for every handle; no role at Create.
- **R3-4. Accepted.** Change: Poll reads the health's latest sequence; no hold, no Die path,
  no order rule against the draw. Section 8 names the fallback (AcquireLatest, 25 us) if the
  frame buffer keeps another source for the value.
- **R3-5. Accepted.** Change: window 7 added to the internal header's TOCTOU list.
- **R3-6. Accepted.** Change: the normal load of 4 marked unverified with its parts; the
  webcam rate 15 to 20 measured, 30 in daylight from the frame buffer's record; the 54 us
  named as the 1080p 8-slot figure; Poll's cost one figure (about 9 us); the latency row
  labelled "a tuned subscription in the bridge's shape".
- **R3-7. Accepted.** Change: SPAN_FRAME in all three places.
- **R3-8. Accepted.** Change: the row's cause reads "no cause seen; the pointer check is the
  read's own contract (item 8)".
- **R3-9. Accepted.** Change: O3 added with "option A", the row reads "a requirement: O3 a";
  MOD1, MOD2, GATE1, DOC1 and PAR2 quoted.
- **R3-10. Accepted.** Change: cam_list.py opens each camera through the module's open
  step and keeps only its brightness report; the change-impact table deletes
  test_the_preflight_reads_the_camera_again_before_it_fails with the reason.
- **R3-11. Accepted.** Change: the bridge's spec test checks exactly two env additions.
- **R3-12. Accepted.** Change: the header says "two static malloc thresholds"; the numbers stay
  in item 9; the union note moved to section 8.
- **R3-13. Accepted, narrowed.** Cause: none for a drone frame of another size (R1-4). A field
  for a log rate would be a mechanism for a row with no cause. Change: the per-shape log line
  goes; the bridge counts and logs the count once, at its exit.
- **R3-14. Accepted.** Change: an @-block above StallAction for STALL_MARK and STALL_RESTART.
- **R3-15. Accepted.** Change: the leftover paragraphs rewrapped.

## Conclusions
Three rounds, one reviewer each (general-purpose agent, model opus): 10, 6 and 15 findings,
31 in all. Accepted 27, narrowed 4 (R1-2, R1-4, R1-9, R3-13), rejected 0. No finding was high.
Every run stayed on 127.0.0.1: the video mock and the owner's receiver, ROS 2 on private
domains. No command reached any aircraft. The webcam was taken and released through
tools/lock.sh.

**Agreed.**
- The webcam and the file read straight into a claimed slot on one thread; OpenCV's own copy
  runs without the GIL; no main-thread stall (measured at the baseline).
- The claim stays open across a failed read and a frame of another size; only a good read
  publishes.
- rclpy's take of a 1080p frame holds the GIL 9 to 10 ms (1.9 ms tuned); the drone's frames
  cannot be taken in the app within the 330 us budget.
- The stall guard on the main thread once a second, by the health's latest sequence; only the
  receiver is restarted; the receiver never reconnects by itself (measured).
- The size probe once, at the app's start, before the recorder and the buffer.

**Open for the owner (frame_source.md section 4).**
- OPEN 1: the frame bridge process (recommended), against (b) the receiver writing the block,
  (c) the stall, (d) OpenCV reading the phone's stream (on the numbers the best; against RVW5).
- OPEN 2: a frame buffer writer handle for another process (carried, PAR2).
- OPEN 3: runtime's graph query call for the probes (carried).
- OPEN 4: no reopen of a lost webcam until the owner names it as seen.
- OPEN 5: the frame buffer's held-slot scan once a second in a drone run (carried).

**Changed because of the review.**
- The bridge's env gains GLIBC_TUNABLES (a 32 MiB static mmap threshold, a 256 MiB trim
  threshold): the take 8.9 to 1.9 ms, the bridge 32 to 42 % down to 10 to 14 % of a core,
  memory flat at 105 MiB over 40 minutes.
- Option (d) entered OPEN 1 with one decoder thread: 13 ms latency against the bridge path's
  29 to 34 ms, 48.6 % against 78 % of a core.
- The failure matrix: every row's cause corrected (the stall a requirement of section 9; the
  no-server row DESIGNED; the size rows without a cause; O3 a requirement).
- Poll takes no hold; the spec texts split per spec; the per-shape log line dropped.
- The preflight's camera check dropped; cam_list.py opens through the module.

**Every item the review added, with its cause.**
| item | cause | an open point? |
|---|---|---|
| GLIBC_TUNABLES in the bridge's env | SEEN: the bridge's CPU, measured in normal use | no: a config value of the bridge, inside OPEN 1 |
| the held-slot scan in the frame buffer | DESIGNED: the screen's health read in every drone run | yes: OPEN 5, a change to a finished module |
| option (d) in OPEN 1 | SEEN: measured on the mock | inside OPEN 1 |
| the DDS histories named, depth 10 kept | none needed: text | no |
| Poll reads the health, no hold | none needed: a simplification | no |
| the bridge's rejected count logged at exit | none needed: it replaces a per-shape log line | no |
