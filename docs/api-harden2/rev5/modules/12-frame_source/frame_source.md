# The frame source: the one writer of the frame buffer (rev5 module 12, started 2026-10-18)

The headers are `frame_source.h` (the contract) and `frame_source_internal.h` (the state, the
stall rule as a pure function, the steps of each thread, the TOCTOU list). Below it: the
recorder (draft), runtime (approved), the frame buffer (finished). Above it: the app step
(module 15). The review record: `../../test/frame_source-review.md`.

## 1. The job, in one sentence
The frame source puts the newest frame of the run's one camera into the frame buffer.

## 2. The picture
```
 WEBCAM or FILE (one thread in the app)            DRONE (two processes, no thread in the app)
 --------------------------------------            ---------------------------------------------
 frame source thread, the buffer's one writer       phone app: H.264 over TCP :5600
   1 claim = BeginWrite (the oldest free slot)        |
   2 cv2 read(claim.pixels)  <- decode + one copy     v
     in C, the GIL released (19.8 frames/s here)    gstreamer receiver (the owner's C++ ROS 2 node)
     a failed read or another size: the claim         decode -> bgr8 -> publish camera/stream
     stays open, back to 2                            | DDS: 6.2 MB a frame, 30 a second;
   3 EndWrite(claim, MonotonicNow())                   | keep-last 10, reliable, at both ends
     |                                                v
     |                                              frame bridge (OUR process, OPEN 1)
     |                                                executor thread: rclpy take 1.9 ms with
     |                                                ITS OWN GIL (the malloc tunables); checks;
     |                                                BeginWrite; copy_pixels 0.7 ms; EndWrite
     v                                                v   (the memfd, inherited read-write)
 +----------------------------------------------------------------------------------------+
 |  THE FRAME BUFFER: 12 slots, latest, a count and a sequence per slot (module 4)        |
 +----------------------------------------------------------------------------------------+
     ^ FramebufferReadHealth's latest sequence, once a second (no hold)
     |
 MAIN THREAD: FrameSourcePoll(now) once a second; FrameSourceRow each frame (one load)
   a new sequence: the "video" row UP
   none for 6 s: the row RECOVERING; the drone: SupervisorRestartOnPurpose(receiver),
   again every 15 s while it lasts --> the supervisor's command pipe --> SIGINT, relaunch
   a changed row: one "video" event to the recorder
```
The threads: the frame source thread (webcam or file) in the app; the bridge's executor thread
and main thread in the bridge process; the app's main thread for the poll. The processes: the
receiver and the bridge, both the supervisor's, for the drone only. The rates: 30 frames a
second from the drone; from a webcam 15 to 20 measured in this room, 30 in daylight (the
frame buffer's 4b item 5); a file at its own rate. The
sizes: 6.2 MB a slot at 1080p, 2.8 MB at 720p. The webcam and the file have no queue: each
frame goes straight into a slot. The drone has two: the DDS histories of the receiver's
publisher and of the bridge's subscription, keep-last 10, reliable.

## 3. How a caller uses it: two instances, in the Python of the build
**Instance 1: the app's start and stop order, and the webcam's thread.**
```python
# app/main.py: the size first, then the recorder and the buffer, then the supervisor
settings = frame_source_settings_from_config()
size = frame_source_probe_size(settings)              # the webcam: open, one frame, release
if size is None:
    die(f"video: no frame from {settings.kind}")      # a start-up check
if not recorder_create(session.dir, "app", RecorderFrameConfig(size, info_json)):
    die("recorder: the session folder")
frames = framebuffer_create(size)
specs = [llama_spec, sam3_server_process_spec(log_dir, framebuffer_descriptor(frames)), ...]
if settings.kind == FRAME_SOURCE_DRONE:
    specs.append(gstreamer_rx_process_spec(log_dir, settings.phone_ipv4, rx_text))
    specs.append(frame_bridge_process_spec(log_dir, framebuffer_descriptor(frames), bridge_text))
supervisor = supervisor_create(specs)
if settings.kind == FRAME_SOURCE_WEBCAM:
    video = webcam_source_create(settings, size, frames)
elif settings.kind == FRAME_SOURCE_FILE:
    video = file_source_create(settings, size, frames)
else:
    video = drone_source_create(supervisor, supervisor_process(supervisor, GSTREAMER_RX_NAME), frames)
# ... the run ...
frame_source_destroy(video)                           # the thread joined: no writer is left
supervisor_destroy(supervisor)                        # the drone: the bridge and the receiver stop
framebuffer_destroy(frames)

# video/capture.py: the frame source thread, the buffer's one writer (webcam or file)
def _run(self):
    claim = None
    while not self._stop.is_set():
        if claim is None:
            claim = framebuffer_begin_write(self._frames)     # Die when no slot is free (FR1)
        ok, image = self._device.read(claim.pixels)          # the GIL released for the decode
        if not ok:
            self._failed_reads += 1
            self._after_failed_read()                         # the file: rewind; else 100 ms
            continue                                          # the claim stays open
        if image.ctypes.data != claim.pixels.ctypes.data:
            self._rejected += 1                               # another size: the slot untouched
            continue
        framebuffer_end_write(self._frames, claim, monotonic_now())
        claim = None
        self._pace()                                          # the file only
```
**Instance 2: the drone: the bridge's callback, and the main thread's poll.**
```python
# video/frame_bridge.py: our process; the supervisor launches it with --frames-fd N
def on_image(self, msg):                              # the bridge's executor thread
    if (msg.height, msg.width, msg.encoding, msg.step) != (H, W, "bgr8", W * 3) \
            or len(msg.data) != H * W * 3:
        self._rejected += 1                           # counted; logged once, at the exit
        return                                        # before any claim
    at = monotonic_now()
    claim = framebuffer_begin_write(self._frames)     # the writer handle of OPEN 2
    copy_pixels(claim.pixels, np.frombuffer(msg.data, np.uint8).reshape(H, W, 3))
    framebuffer_end_write(self._frames, claim, at)

# app/screen.py: the main thread
row = frame_source_row(video)                         # every frame: one atomic load
if now - last_poll >= FRAME_SOURCE_POLL_EVERY_NS:     # once a second
    frame_source_poll(video, now)                     # the health's latest sequence; no hold
    last_poll = now
```

## 4. The open points for the owner
Each one: the problem, what the header shows now, what changes on "no", the recommendation.
The header marks each with `OPEN n`.

**OPEN 1. The drone's frames go through a bridge process of ours.**
- The problem. rclpy's take of one 1080p message holds the app's GIL for 9 to 10 ms
  (measured, section 7b item 9). It is the same for the typed and the raw subscription and
  for every Fast DDS transport. So the main thread stalls: p99 11 ms, max 16 ms, 30 times a
  second. The budget is 330 us a call. Most of the take is page faults on fresh 6 MB
  buffers; glibc's malloc tunables cut it to 1.9 ms, but the main thread still stalls 3.1 ms
  at p99 and 4.5 ms at max (measured, R1-1). No Python code in the app can bound a C call
  that holds the GIL.
- Now. `FrameBridgeProcessSpec` and `DroneSourceCreate` (no thread in the app). The bridge
  is a small Python process. It subscribes to camera/stream and writes the slot through the
  inherited memfd. Measured: the app's main thread max gap 1549 us against a 1120 us
  baseline; 29.8 frames a second land. A frame reaches the slot 29 to 34 ms (median) after
  it leaves the phone's mock (R2-1). The cost: 105 MiB of private memory, flat over 40
  minutes (the block is the app's, shared); 10 to 14 % of one core with the malloc
  tunables; one more supervised process (BUDGET_SPENT_DIE, a laptop part). The whole drone
  path, the receiver included, is about 78 % of one core (R1-1).
- On "no". (b) The owner's receiver writes the block itself: it maps the memfd it inherits,
  claims, copies and publishes in C++. No 6 MB message crosses DDS. One copy a frame, about
  0.5 ms (unverified). The cost: a change to the owner's C++ node, and a second
  implementation of the writer's claim, in C++. (c) The subscription stays in the app, and
  the main thread loses 3 to 16 ms a frame. (d) No receiver and no bridge: the capture
  thread opens the phone's stream itself, `cv2.VideoCapture("tcp://<phone>:5600",
  CAP_FFMPEG)` with CAP_PROP_N_THREADS 1, and reads into the slot as the webcam does.
  Measured on the mock (R1-2, R2-1): 30 frames a second, all into the slot; a frame in the
  slot 13 to 14 ms (median) after it leaves the mock; 48.6 % of one core for the whole path;
  the main thread at its baseline. OpenCV's default of 16 decoder threads adds 500 ms of
  latency, so the one thread is required. The costs: it removes the owner's ROS 2 node from
  the path, against RVW5; the owner's C++ fmu_node reads camera/stream (fmu_node.hpp line
  256), the system harden2 folds into later; the open took 5.3 s, and four sets of FFmpeg
  probe options did not shorten it; a stream end needs a reopen in the thread (a restart
  path in place of the receiver's); FFmpeg's read timeout is 30 s by default, so a stalled
  read holds Destroy's join that long unless CAP_PROP_READ_TIMEOUT_MSEC sets it.
- Recommended: the bridge, for this build. My view on the numbers alone differs: (d) has
  less than half the latency, about 30 points less CPU, and no bridge, no receiver spec and
  no OPEN 2. I still recommend the bridge because RVW5 stands, and its reason is live: the
  owner's C++ system reads the same topic. The receiver stays unchanged, and the writer's
  code keeps one home (framebuffer.py). If the owner revisits RVW5 for harden2, (d) is my
  pick. (b) needs a change to his node.

**OPEN 2. The frame buffer gets a writer handle for another process (a change to a finished
module, carried to the manager, PAR2).**
- The problem. The frame buffer has one writer handle, the app's own. The bridge needs one
  on the descriptor it inherits.
- Now. The internal header names `FramebufferOpenWriter(fd)` and `FramebufferCloseWriter`: a
  read-write mapping of the block, the same BeginWrite and EndWrite, the writer-thread check
  per handle. The app's own handle never writes in a drone run.
- On "no". The bridge cannot write. OPEN 1 falls back to (b) or (c).
- Recommended: the two calls. One fact for the owner: a writer killed between BeginWrite
  and EndWrite leaves its slot WRITING for the rest of the run. The cause is FORCED (a
  kill), so item 12 gives it the generic handling only: the supervisor's relaunch. One slot
  is lost per such kill. A load of 9 holders needs 11 of the 12 slots. A normal load needs
  about 4: the draw, one or two jobs, the slot under write and the latest (unverified).

**OPEN 3. runtime's graph query has no call in runtime.h (a change to an approved module,
carried).**
- The problem. runtime.md point 5 gives the three ROS 2 nodes the probe
  `ros.count_publishers(topic) > 0` "on the app's own node". runtime.h declares no call for
  it. The receiver's probe and the bridge's probe need it; so do the keys and the ASR node.
- Now. `GstreamerRxReadyProbe` (a publisher on camera/stream) and `FrameBridgeReadyProbe` (a
  subscriber on camera/stream) are declared here and call it.
- On "no". Both probes are NULL: the rows go UP at launch. The "video" row still shows the
  frames.
- Recommended: two calls in runtime.h on its one graph node, `RosCountPublishers(topic)` and
  `RosCountSubscribers(topic)`. Measured: the receiver's publisher is seen within 2 s of its
  launch. A fact: the probe reports the node, not the frames; with no video server the node
  is UP and no frame flows (measured).

**OPEN 4. A webcam lost mid-run is not reopened.**
- The problem. The brief calls an unplugged webcam SEEN. I found no session line and no
  owner statement of it. Item 12 lists "a cut cable" as FORCED.
- Now. No reopen. The reads fail; the thread pauses 100 ms after each failed read; the row
  goes RECOVERING after 6 s with the count of failed reads; the app lives; the draw keeps
  the last frame.
- On "seen". The thread reopens after a run of failed reads: release, open with the probe's
  settings, the size checked on every frame as now. About 10 lines and one restart path.
- Recommended: no reopen until the owner names it as seen.

**OPEN 5. The frame buffer's held-slot count in a drone run (a second change to the frame
buffer, carried to the manager).**
- The problem (R1-3, R2-2). The health's held-slot count is the writer's own value, in the
  writer's process. In a drone run the app's handle never writes. So the screen's health
  shows no held slot for the whole run, and FR1's early warning is blind where it matters.
- Now. Carried; the frame buffer chooses the call: a scan of the 12 counts in the block, for
  every handle, once a second (R3-3: no role at Create is then needed). The caller: the
  screen (module 15), once a second, beside FrameSourcePoll. Measured: a 14-load scan costs
  60 us median, 111 us p99, 395 us max. The screen's per-frame health read stays four plain
  values (the frame buffer rejected 14 loads a frame, its R1-7). The header marks it at
  FrameSourcePoll.
- On "no". The health shows 0 held slots in every drone run. Nothing else changes.
- Recommended: the scan. A side fact for the frame buffer (R2-5): framebuffer.md section 8
  still says the latest sequence is "the writer's own count"; since FB7 it is read from the
  block. Poll relies on that read.

## 5. Today
- `video/video.py` (161 lines). `Video.read()` runs on the main thread each frame. For the
  webcam it is `cv2.VideoCapture.read()`: the main thread blocks on the camera, up to a frame
  period (52 ms measured at 19.8 frames a second). `snapshot()` copies the whole frame for
  each vision request. Five kinds: two (a gstreamer pipeline string, a stream URL) have no
  user. The open loop retries for 180 s and blocks the start. The stall guard runs only
  inside `read()`, so only while the main thread reads.
- `video/ros_stream.py` (80). The callback reshapes under a lock. `read()` copies 6 MB on the
  main thread each frame. rclpy's take holds the GIL 9 to 10 ms a frame on the executor
  thread (section 7b item 9). The spec uses the old `required=False`.
- `video/cam_list.py` (125). The preflight's camera check: open, read one frame. It is a
  second home of the same probe.
What is wrong: a blocking read and a 6 MB copy on the main thread; a 9 to 10 ms GIL hold per
drone frame; a copy per request; two unused kinds; a probe in two places; a stall guard tied
to the draw.

## 6. The rulings that bind it, and the forces
| ruling | the owner's words | here |
|---|---|---|
| FR1 (2026-10-04) | "WHICH FRAME? THE OLD ONE OR THE NEW ONE? ... we don't need old frames laying around in the Ring buffer" + "How do you guarantee that the frames served to all of our systems are indeed the latest available frames?" | the source publishes every good frame at once; no queue; no slot free is the buffer's Die |
| FB2 (2026-10-18) | "Good! keep it nameless and pass it on launch." | the bridge inherits the memfd at launch, read-write (OPEN 2) |
| FB3 (2026-10-18) | "Timeline a - Good. timeline b - Good! ... Anyways, I agree with your proposal. Approved." | every writer claims by the buffer's compare-and-swap; no claim of our own |
| FB5 (2026-10-18) | "OPEN 1 - Approved." | 12 slots; the source holds one claim at a time |
| FB7 (2026-10-18) | the owner's edit: ReadWriteFrameReference, FrameSize of uint16_t | the names used here |
| RVW5 (2026-10-12) | "The reason we used gstreamer in a standalone ROS2 node was for us to easily have an input source for image data that is uniform across all platforms" | the receiver stays a ROS 2 node, unchanged (OPEN 1) |
| Q3 (rev4, REVIEW-4-answers.md section 18) | the options "a. drop them. b. keep them."; the handoff records "a" (the verbatim answer is not in the ledger) | three kinds: webcam, drone, file |
| RUN9 (2026-10-17) | "The supervisor is the owner ... Who is the owner here!?" | two pure spec functions; the only request is RestartOnPurpose |
| RUN14 (2026-10-17) | "Make sure TOCTOU Doesn't fall inbetween the cracks." | gate item 11, seven windows, the same seven in the internal header |
| RUN16 (2026-10-18) | "the env vars should be empty in the initial process, unless we set the env char array to an addition between the current vars + whatever we want to additionally include." | each spec lists only its additions |
| REV8 (2026-10-18) | "R2 - I fully agree with everything here! APPROVED!" | every matrix row names its cause; OPEN 4 |
| GIL1 (2026-10-18) | "Is it sensible that I upgrade the python version of this container to a GIL-free version? ..." | OPEN in the ledger; section 8 says what it would change here |
| PRF7, RCD1 (2026-10-18) | "Why do you hold a handle to m_perf?"; "Call it RecorderCreate() and destroy(), recordSpan(), recordEvent(), recordFrame(), and so on" | no recorder argument anywhere; one RecordEvent call site |
| TEL17 (2026-10-16) | "Where is the issue here?" (the webcam probed, the drone 1080p) | FrameSourceProbeSize before the recorder and the buffer |
| SK4 (2026-10-06) | "WE ARE NOT USING MUTEXES FOR SIMPLE SHIT LIKE THIS!" | no lock; two relaxed counters |
| O3 (the preflight after a stopped run) | "option A": the frame read is retried once after about 1 s | the probe's retry, FRAME_SOURCE_PROBE_RETRY_NS |
| MOD1 (2026-10-12) | "perf.md is not written in a way that a human could realistically review under 15 minutes." | the section order |
| MOD2 (2026-10-12) | "I should be able to understand these points by reading the header and a little bit regarding each points' context." | the four-line open points, the OPEN marks |
| GATE1 (2026-10-14) | "What do you still need me to review? we're constantly losing the plot" | the proof-based gate, the failure matrix |
| DOC1 (2026-10-17) | "You keep generating and generating and generating documents" | two files plus the internal header |
| PAR2 (2026-10-18) | "I want the other subagents that I'd like to run to do their own thing, along with their respective review agents." | this agent and its three reviewers; the FSRC prefix only |
The owner on this module's inputs (2026-10-18, this session): "The recorder is bound to change
and its contract is still volatile ... perf & telemetry are effectively redundant due to their
replacement, recorder. That doesn't mean that the insights are invalid, though." So the module
uses three recorder names only: FrameSize, MonotonicNs with MonotonicNow, and one
RecordEvent call inside RecordVideoRow.

The forces, measured on this machine (section 7b item 9): a screen frame 33 ms; the 330 us
budget a call; rclpy's take 9 to 10 ms a 1080p frame with the GIL held (1.9 ms with the
malloc tunables); the webcam's decode 1.4 to 3.0 ms with the GIL released; the frame
buffer's BeginWrite plus EndWrite 54 us median (its document, 1080p with 8 slots; 12 slots
unverified); a webcam delivers 15 to 20 frames a second in this room.

## 7. The design gate
**Ownership.** The app creates the source after the supervisor (the drone kind needs the
receiver's handle) and destroys it first, before the supervisor and the buffer. The size
probe runs before the recorder and the buffer. The supervisor owns the receiver and the
bridge. The bridge maps the block at its start and unmaps it at its exit.
**Data in.** The settings from config; the frame size; the buffer; for the drone, the
supervisor and the receiver's handle. **Data out.** Frames into slots; the "video" row; one
"video" event per row change; two process specs.
**Mutable state, and its owner.** The capture thread's open claim: a local of that thread.
The failed-read and rejected counters: the capture thread adds, Poll loads; relaxed atomics,
a plain int in Python under the GIL. The stall guard and the row: the main thread's alone.
The bridge's state: its own process, its executor thread.
**Threads.** One in the app for the webcam or the file; it stops on a flag and is joined by
Destroy. None in the app for the drone. The bridge: its main thread waits for the stop; its
executor thread runs the callback; SIGINT ends both.
**Processes.** The receiver: SIGINT, no retry, 10 s grace; it exits in 124 ms (measured).
The bridge: SIGINT sets its stop event; it stops in 6.6 ms (measured) and exits 0.

## 7b. The gate, answered (modules/README.md, items 1 to 12)
1. **The real-time path.** The webcam and the file have no queue: a frame goes into a
   slot. The drone path has two DDS histories, keep-last 10 and reliable: the receiver's
   publisher and the bridge's subscription (runtime's helper sets 10). A late bridge would
   write a frame up to 10 periods old, 333 ms; the bridge needs 2.6 ms of each 33 ms, so no
   cause is seen. The main thread makes two calls. FrameSourceRow each frame: one atomic
   load (192 ns, runtime's figure). Poll once a second: the health read, whose latest
   sequence is two atomic loads at 4.1 to 4.3 us each (R2-2's measurement), so about 9 us,
   plus a few compares (unverified as a whole). Tried: the drone's frames in the app; the
   main thread stalled 11 ms at p99 and 16 ms at max. The bridge stops it: max 1549 us
   against a 1120 us baseline. Tried: the webcam read plus our copy; the main thread's max
   went from 1072 to 2035 us at 1080p. The read into the slot keeps it at the baseline.
2. **Not a sink.** It is a producer. It holds no app state and calls no module of the app.
   Its outputs: the slots, its own row, one event kind.
3. **Fault containment.** No Die of its own. The Die paths are the frame buffer's (no free
   slot; a second writer; a write left open); each one is our own bug (RVW4). Start-up:
   the probe's false and a Create that fails end the app at start. Mid-run every fault
   degrades: a failed read, a frame of another size, a stall, each to the row and a count.
   A crash of the bridge or the receiver is the supervisor's (section 7b matrix).
4. **Buffer lifetimes.** The writer holds one claim at a time. Webcam: claimed before the read
   and held across it, 50 to 70 ms (a frame period), longer while reads fail; published at
   the first good read. Bridge: claimed after the checks, held for the 0.7 ms copy. Poll:
   no hold. Never held for the recorder.
5. **Types and units.** Every time a MonotonicNs in ns of CLOCK_MONOTONIC, shared by
   the app and the bridge. Durations as UINT64_C macros (6 s, 15 s, 1 s, 0.1 s, 10 s).
   Counters FrameSourceCount, 32 bits. The sequence a dword (the buffer's). Every time
   compare is `now - earlier` on stamps of one clock.
6. **One home.** The probe here: the app's start calls FrameSourceProbeSize once; the
   preflight does not (R1-9). cam_list.py stays a manual tool that lists every camera; it
   opens each one through the module's open step (MJPG at the request) and keeps only its
   own brightness report (R3-10). The writer's claim: framebuffer.py, for the thread and
   the bridge.
   copy_pixels: util/copy.py (the buffer's). The stall constants: config, renamed from
   WATCHDOG_STALL_SECONDS and WATCHDOG_RETRY_SECONDS. FrameSize: recorder.h.
7. **The contract.** The specs, as code:
   ```
   gstreamer:    setpriv ... -- <NATIVE_BIN_DIR>/llm_to_action_gstreamer_rx --dji <PHONE_IP>
                 env + LD_LIBRARY_PATH=<NATIVE_BIN_DIR>:<the current value>   (config computes it)
                 probe: a publisher on camera/stream; 10 s; SIGINT, 0, 10 s; WAIT_FOR_USER
                 log: <logDir>/proc-gstreamer.log
   frame_bridge: setpriv ... -- python3 <HARDEN2>/video/frame_bridge.py --frames-fd <n>
                 env + PYTHONPATH=<HARDEN2>
                     + GLIBC_TUNABLES=glibc.malloc.mmap_threshold=33554432:glibc.malloc.trim_threshold=268435456
                 pass_fds [n]
                 probe: a subscriber on camera/stream; 10 s; SIGINT, 0, 10 s; DIE
                 log: <logDir>/proc-frame_bridge.log
   the event:    {"k":"event","t":0,"topic":"video","at":...,"state":"RECOVERING",
                  "detail":"no frame for 7 s","failed_reads":0,"rejected":0,"restarts":1}
   ```
   The readers: the supervisor (the specs), the replayer and log/show.py (the event), the
   status pane (the row).
8. **The Python mapping, as code.**
   ```python
   # the read releases the GIL: cv2's binding wraps VideoCapture.read in PyAllowThreads
   ok, image = device.read(claim.pixels)       # OpenCV decodes, then copyTo(the slot)
   same = image is not None and image.ctypes.data == claim.pixels.ctypes.data
   # thread-local: nothing; the claim is a local of _run; the counters plain ints (GIL)
   # a put that can block: none; no queue
   # an exception that can leave: cv2.error from a bad argument is our bug ->
   #   threading.excepthook -> Die (runtime's hook); a failed read returns (False, None)
   # the bridge: np.frombuffer(msg.data) is a view of rclpy's array; copy_pixels keeps the GIL
   #   for 0.7 ms in the bridge's own process; the app's GIL is not involved
   # allocation per frame: the read's tuple and one ndarray header; nothing grows
   ```
9. **The cost budget, measured 2026-10-18.** The machine: Ryzen 9 8940HX, 32 threads,
   Python 3.12.3, opencv-python 4.11.0.86 (FFMPEG yes, GStreamer no), numpy 1.26.4, ROS 2
   Jazzy rclpy 7.1.11, rmw_fastrtps_cpp 8.4.4, Fast DDS 2.14.6. The probe of the main thread:
   a 1 ms sleep loop; its gap above 1.05 ms is a stall. The drone runs: the real receiver
   against tools/dji_mock/video_tcp_mock.py on 127.0.0.1:5600, a 1080p H.264 test clip, ROS
   domain 87, localhost only. No phone and no aircraft.

   | webcam 0 (WEBCAM_DEV=0), 120 frames | 720p | 1080p |
   |---|---|---|
   | frames a second (this room) | 19.8 | 19.8 |
   | read(slot): written into the slot | 120 / 120 | 120 / 120 |
   | read(slot): thread CPU, median / p99 us | 1681 / 2325 | 3624 / 4144 |
   | read() + our copy: thread CPU, median us | 1944 | 4295 |
   | our copy alone, median / p99 / max us | 199 / 683 / 921 | 716 / 1095 / 1103 |
   | the decode alone (imdecode), median us | 1522 | 2505 |
   | main thread max gap beside read(slot) / read() + copy, us | 1078 / 1479 | 1072 / 2035 |
   | a destination of another size | untouched; OpenCV returns its own array | the same |
   Webcam 2 (the C920) gave 15 frames a second and wrote 120 of 120 into the slot. Its thread
   CPU was higher for read(slot) than for read() plus copy (6621 against 3873 us at 720p).
   That is unexplained; the CPU ran at 46 % of its clock. The main thread's figure, which the
   design rests on, is from webcam 0. OpenCV's source confirms one copy: the V4L2 backend
   decodes into its own buffer, then `frame.copyTo(ret)` (cap_v4l.cpp, 4.11.0, line 2082).

   | the drone path, 10 s each | frames/s | rclpy take, median / p99 / max us | main gap p99 / max us |
   |---|---|---|---|
   | no subscription (the baseline) | - | - | 1064 / 1121 |
   | typed subscription, our copy (today's shape) | 29.5 | 10291 / 12683 / 16011 | 10843 / 13578 |
   | raw subscription (CDR bytes), our copy | 30.1 | 10092 / 12854 / 13817 | 11114 / 15808 |
   | raw, best effort, depth 1 | 18.6 | 9739 / 12284 / 12737 | 10815 / 13661 |
   | typed, in the app, with the malloc tunables (R1-1, re-measured) | 30.0 | 1864 / 3290 / 3485 | 3130 / 4480 |
   | the bridge process, the app's main thread | 29.8 | in the bridge | 1063 / 1549 |
   | OpenCV reads tcp:// into a slot, no receiver (R1-2, the reviewer's) | 30.1 | none | 1063 / 1141 |

   | the latency, a frame leaving the mock to the slot (R2-1, the reviewer's m5.py) | median / p99 / max ms | CPU, % of a core |
   |---|---|---|
   | the receiver, camera/stream, a tuned subscription in the bridge's shape (one process; the bridge process itself unverified) | 29 to 34 / 45 to 50 / 47 to 57 | 63.7 + 14.4 |
   | OpenCV FFMPEG in the app, CAP_PROP_N_THREADS 1 (option d) | 13 to 14 / 46 to 67 / 89 to 114 | 48.6 |
   | OpenCV FFMPEG in the app, its default of 16 threads | 497 to 500 / 782 to 787 / 785 to 802 | 44.7 |
   The take's thread CPU equals its wall time: it is CPU work with the GIL held, not a wait.
   A callback that does nothing costs the same 12 ms a message. The reviewer counted 4525
   minor page faults a take: three fresh 6.2 MB buffers of 4 KiB pages. With
   `GLIBC_TUNABLES=glibc.malloc.mmap_threshold=33554432:glibc.malloc.trim_threshold=268435456`
   the take faults 0 times and costs 1864 to 2173 us. Each setting alone does nothing; 32
   MiB is glibc's documented upper limit of the threshold (R2-4). By size (an rclpy publisher,
   raw take, median): 320x240 342 us; 1280x720 3835 us; 1920x1080 9128 us. By Fast DDS
   transport at 1080p (median): DEFAULT 8704, SHM 8723, UDPv4 8898, LARGE_DATA 8842 us. The
   bridge with the 12-slot block, over 40 minutes and 72000 frames (the reviewer): 105 MiB
   private with the tunables, flat from 270 s on; 81 to 98 MiB without; 10 to 14 % of one
   core with the tunables, 32 to 42 % without; the receiver 63.7 % either way. It stops in
   6.6 ms on SIGINT. The receiver: SIGINT to exit 124
   ms; its publisher seen within 2 s of the launch; frames at a live subscriber 1 to 3 s after
   a relaunch, with no action on the subscriber's side. With no server at its launch, or after
   an end of stream, it stays alive and never reconnects.

   | the file kind (FFMPEG, a 1080p H.264 mp4) | value |
   |---|---|
   | read(slot): written into the slot | 120 / 120 |
   | thread CPU a frame, median / p99 us | 8657 / 9807 |
   | rewind and one read | 30.4 ms |
   | main thread max gap beside it | 1106 us |
   Rate times cost. The app's hottest thread is the webcam thread: 19.8 x 3.6 ms = 72 ms of
   CPU a second at 1080p, the GIL released for the read. Its GIL time is BeginWrite plus
   EndWrite, 54 us median a frame (the buffer's 1080p 8-slot figure), about 1 ms a second.
   The main thread: 30 row loads (6 us) and one Poll (about 9 us) a second; every call far
   under 330 us. The bridge, in its own process: 10 to 14 % of one core with the tunables
   (32 to 42 % without), measured. The commands, in this session's scratch folder
   `fs/`: `python3 w1.py <device> <w> <h>` under `tools/lock.sh run frame_source webcam`;
   `python3 d1.py typed|raw sleep|busy 10`, `d2.py`, `d3.py raw camera/stream 8` with the mock
   and the receiver running; `pub.py fs/img <w> <h>` for the size and transport rows;
   `bridge_parent.py` for the bridge row; `f1.py` for the copy and the file rows.
10. **Deterministic checks.** `gcc -fsyntax-only -Wall -Wextra -std=c11 -Wpedantic` with the
    recorder, runtime and perf folders on the include path: both headers clean.
    `header_layout.py` on both: no change. Every line under 90 characters. No drawing. The
    names and numbers of this document match the headers.
11. **TOCTOU.** Every check-then-act, with what closes it:
   | n | check, then act | the window | closed by | test |
   |---|---|---|---|---|
   | 1 | a claim, then the read | the read fails | the claim stays open; the next good read fills the same slot; only a good read publishes | `test_a_failed_read_keeps_the_claim_and_publishes_the_next_good_frame` |
   | 2 | a claim, then the read | the camera delivers another size | OpenCV allocates its own array and leaves the slot untouched (measured); the pointer check rejects it; the claim stays open | `test_a_frame_of_another_size_never_reaches_a_slot` |
   | 3 | the probe's size, then Create's reopen | the device at the index delivers another size | the per-frame check of row 2; the row names the count | `test_a_reopen_of_another_size_is_rejected_frame_by_frame` |
   | 4 | the bridge's frame, then its claim | a padded step, rgb8, another size | every check runs before BeginWrite (the buffer's rule) | `test_the_bridge_drops_a_wrong_shape_before_any_claim` |
   | 5 | Poll: no frame for 6 s, then the restart | a frame lands between | named, not closed: one needless restart, 1 to 3 s of video (measured) | `test_stall_decision_table` |
   | 6 | Destroy while the thread holds a claim | a write after the buffer is gone | the join comes before FramebufferDestroy (the app's order); the open claim dies with the buffer | `test_destroy_joins_the_thread_before_it_returns` |
   | 7 | the bridge killed between BeginWrite and EndWrite | its slot stays WRITING | named, not closed (FORCED, item 12); OPEN 2's fact | the supervisor's relaunch test |
12. **Need.** Every row of the matrix below names its cause. No mechanism serves a FORCED row.

The failure matrix:
| failure | cause | the module's state | what it leaves | the aircraft |
|---|---|---|---|---|
| the drone's stream ends or stalls | a requirement: the architecture, section 9, "The video stalls: a planned restart after 6 s"; no session line found (R1-8); measured: the receiver never reconnects after an end of stream | the row RECOVERING after 6 s; the receiver restarted, again every 15 s | the "video" event; the supervisor's line | never touched |
| no video server when the receiver launches | DESIGNED: the operator starts the app before the phone's server; the trace measured: the receiver errors and never connects | the same restart every 15 s until frames come | the same | never |
| rclpy's take stalls the app | SEEN: measured, 11 ms p99, 16 ms max | removed by the bridge (OPEN 1) | - | never |
| the receiver crashes | no cause seen; the generic handling | the supervisor relaunches it; after 3, WAITING, retried every 5 s | the supervisor's row | never |
| the bridge crashes, or is killed mid-write | no cause seen; FORCED for the kill | the supervisor relaunches it; a slot left WRITING (OPEN 2); after 3: Die (a laptop part) | the supervisor's row; Die's hand-over | the hand-over first (RVW4) |
| the bridge falls behind | no cause seen: it needs 2.6 ms of each 33 ms | the DDS histories hold up to 10 frames; a frame up to 333 ms old | SPAN_FRAME's frame age | never |
| the webcam is unplugged | FORCED (item 12: a cut cable); the brief's SEEN not found (OPEN 4) | reads fail; a 100 ms pause after each; the row RECOVERING after 6 s; no reopen | the event with the failed reads | never |
| a webcam or file frame of another size | no cause seen (6 of 6 reopens gave the same size, the reviewer); the pointer check is the read's own contract (item 8) | rejected before any publish, counted; the row's detail names it | the event's count | never |
| a drone frame of another size | no cause: 1920x1080 is a given; the bridge's checks guard the copy (the buffer's rule) | dropped in the bridge and counted; the app sees "no frame" and restarts the receiver every 15 s to no effect (R1-4) | the count in proc-frame_bridge.log at the bridge's exit | never |
| the camera busy at start, just released by a stopped run | a requirement: O3 a | the probe reads again after 1 s; then false: Die at start | the banner | none: at start |
| every slot held | the frame buffer's FR1 bug | Die inside BeginWrite; in a drone run that is the bridge's Die: a banner and an exit; the app's hand-over comes at the budget's end, about 9 s and three starts later (unverified, R1-5) | the "die" event | the hand-over first; late in a drone run |
| a busy Python thread in the app | SEEN: the frame buffer's round 2 | the webcam thread waits up to 5 ms for the GIL after its read: a later frame, never a main-thread stall | SPAN_FRAME's frame age | never |
| the file ends | DESIGNED: a test file | rewind, 30 ms | nothing | never |
| SIGKILL of the app | FORCED | the children end by the parent-death signal; the kernel frees the block | nothing | the phone's own failsafe |

## 8. The notes that did not make the header
- **Why the bridge and not the subscription in the app.** The take's cost is not in our
  callback (section 7b item 9). A raw subscription, a best-effort depth of 1 and four
  transports all cost 9 to 10 ms a 1080p frame with the GIL held. Most of it is page faults:
  glibc frees each 6 MB buffer back to the kernel and maps a fresh one at the next take. A
  static malloc threshold keeps the buffers (sources 4 and 5 of the review): 1.9 ms. That
  still stalls the app's main thread 3.1 ms at p99. A child process has its own GIL.
  Rejected: the in-app subscription, typed or raw, tuned or not.
- **Why the tunables go into the bridge's env only.** They are a measured CPU cut for the
  bridge: 41.9 % to 14.4 % of a core. The app's own allocations are not this module's.
  The cost: about 18 MiB more private memory in the bridge, flat over 40 minutes. The
  threshold is 32 MiB, glibc's documented limit; a larger value is dropped by glibc 2.31 to
  2.34 (R2-4).
- **Why not the receiver writing the block (OPEN 1, b).** It is the cheapest at runtime. It
  changes the owner's C++ node and puts a second copy of the claim in C++. RVW5 keeps the
  node a uniform ROS 2 source. It stays the option for later.
- **OpenCV in the app, reading the phone's stream.** The installed OpenCV has no GStreamer
  ("GStreamer: NO"), but its FFMPEG backend reads `tcp://` (the reviewer, R1-2). It is OPEN
  1's option (d). RVW5 rules the separate node, so it is the owner's call.
- **Why not a smaller or a compressed image on the topic.** 720p still costs 3.8 ms a take.
  A JPEG topic needs a re-encode in the owner's node and loses detail SAM3 sees. Rejected.
- **Why the webcam reads into the claimed slot.** It removes our copy, the one that holds the
  GIL (0.7 ms at 1080p). OpenCV's own copy stays, in C, without the GIL. The claim is held
  across the read; the slot count already counts "the slot under write" (FB5).
- **Why the probe does not hand its open device to Create.** It would save about 1 s at start
  and close TOCTOU 3 (R1-9). It needs a second state: an open device that lives across the
  recorder's and the buffer's creation. The per-frame check covers TOCTOU 3; 6 of 6 reopens
  gave the same size. Rejected on simplicity.
- **Why depth 10 on the bridge's subscription.** runtime's helper takes no depth. Measured: a
  best-effort depth of 1 delivered 18.6 frames a second, depth 10 reliable 30. The older
  frames in the history need a late bridge, and none is seen.
- **Why the claim stays open across a failed read.** The frame buffer has no abort call, and
  it needs none: the next good read fills the same slot. A publish of a failed read would
  show a stale or a torn frame.
- **Why the stall guard runs on the main thread, once a second.** It must see the drone's
  frames, which no thread of the app writes. The latest sequence is in the block for every
  kind. Once a second is enough for a 6 s rule: the stall is seen between 6 and 7 s.
  Rejected: a guard thread (a thread for one compare a second); the guard inside the capture
  thread (blind to the drone).
- **Why Poll reads the health and takes no hold (R3-4).** The health's latest sequence is
  read from the block since FB7, so it holds in every kind. A hold would make Poll a Die path
  (a second hold on one thread dies) and tie it to the draw's release. If the frame buffer
  keeps another source for that value, Poll falls back to AcquireLatest and Release, 25 us.
- **Why the handle has two pointers and not a union.** The layout tool cannot parse an
  anonymous union; two fields with one NULL read as clearly.
- **Why the sequence and not the capture time.** The sequence changes with each publish in
  every kind. The capture time in the read reference is the frame buffer's open point.
- **Why only the receiver is restarted on a stall.** Measured: after a relaunch of the
  receiver the bridge's subscription receives frames again by itself. A stuck bridge has no
  cause seen. Rejected: restarting both.
- **Why the capture time is MonotonicNow() after the read.** It includes the decode (1.5 to
  2.5 ms) and the USB transfer. The V4L2 buffer's own timestamp exists (CAP_PROP_POS_MSEC), in
  ms. No reader needs the difference. Rejected: the V4L2 stamp (YAGNI). In the bridge, the
  stamp comes after the take, 1.9 ms with the tunables. The receiver's header stamp is
  wall clock, not monotonic. Rejected: the header stamp.
- **Why no span per frame.** The recorder has no source stage. The costs are measured once,
  here. A frame's age reaches the record through SPAN_FRAME's payload (the screen's). Item 12:
  no cause for a per-frame record.
- **Why the bridge does not record.** It would open its own record file per pid. Its one
  fact, the count of rejected frames, is one line in its process log at its exit. A
  per-frame or rate-limited log line would be a mechanism for a row with no cause (item 12). The app's "video" event carries
  the stall.
- **Why the file kind loops.** It exists for tests (Q3 a). A test needs a live source; a file
  that ends would look like a stall.
- **If the build runs on a free-threaded Python (GIL1).** The take, tuned or not, would no
  longer block the main thread. The bridge would then be a choice, not a need. The capture
  thread and the claim stay as they are. Blocked today by opencv, rclpy, atomics and numpy
  1.26 (the ledger).
- **The costs of the choices.** The bridge: 105 MiB private, 10 to 14 % of one core, one
  process. The webcam thread: 72 ms of CPU a second at 1080p. One claim held across each
  read.
- **Carried to other modules and to the manager.** The frame buffer: OPEN 2, OPEN 5 and its
  stale section 8 line (R2-5). runtime: OPEN 3; and SupervisorRestartOnPurpose on a process
  that is RECOVERING at that moment (the supervisor's own window). config: FRAME_SOURCE_*
  replaces WATCHDOG_*; LD_LIBRARY_PATH's merged value computed in config/defaults.py, the
  one reader of the environment; the bridge's GLIBC_TUNABLES string. The preflight: no
  camera check; the app's probe dies at start with the reason (R1-9); run.sh's
  `cam_list.py --selected` goes. Module 15: Poll and the held-slot scan once a second (OPEN
  5); the stop order (the source, then the supervisor, then the buffer). The design
  document's section 3: "the frame source thread" becomes the bridge's executor thread for
  the drone.

## 9. The tests the module ships with (`test/test_frame_source.py`)
Change impact:
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| the read into a slot on its own thread | the main thread no longer reads the camera | yes, on purpose | test_video.py's read and snapshot tests rewritten |
| the drone through the bridge | the frames reach the buffer from another process | yes, on purpose | test_ros_frames_arrive... rewritten |
| two kinds dropped (Q3 a) | a pipeline string or a URL no longer opens | yes, by ruling | test_source_kind_names_every_source rewritten |
| the stall guard on the main thread | the restart no longer depends on the draw | no visible change | test_a_stalled_stream_restarts_gstreamer rewritten |
| no camera check in the preflight (R1-9) | run.sh's `cam_list.py --selected` goes | yes, on purpose | test_the_preflight_reads_the_camera_again_before_it_fails deleted; the probe's retry test replaces it |
New tests:
- `test_probe_reads_one_frame_and_releases_the_device` (a stub device)
- `test_probe_reads_again_after_one_second_when_the_first_read_fails` (O3 a)
- `test_the_drone_size_is_1920_by_1080` and `test_the_file_probe_reads_its_first_frame`
- `test_a_failed_read_keeps_the_claim_and_publishes_the_next_good_frame` (TOCTOU 1)
- `test_a_frame_of_another_size_never_reaches_a_slot` (TOCTOU 2; the real cv2 on a file and a
  wrong-size destination)
- `test_a_reopen_of_another_size_is_rejected_frame_by_frame` (TOCTOU 3)
- `test_the_bridge_drops_a_wrong_shape_before_any_claim` (TOCTOU 4: a padded step, rgb8,
  another size)
- `test_stall_decision_table` (TOCTOU 5; pure): a new sequence; under 6 s; a webcam over 6 s;
  the drone over 6 s; within 15 s of a restart; past 15 s
- `test_poll_restarts_the_receiver_once_per_15_s` (a stub supervisor counts the requests)
- `test_a_new_frame_after_a_stall_sets_the_row_up_and_records_one_event`
- `test_destroy_joins_the_thread_before_it_returns` (TOCTOU 6)
- `test_the_receiver_spec_lists_only_additions` (argv, env, SIGINT, WAIT_FOR_USER, the log)
- `test_the_bridge_spec_passes_the_descriptor_and_its_number_and_exactly_two_env_additions`
  (PYTHONPATH and config's GLIBC_TUNABLES string, then the end)
- `test_the_bridge_writes_a_frame_the_app_reads` (the real path: a child bridge with
  pass_fds and a test publisher on a private ROS domain; the app's AcquireLatest sees the
  pixels and the next sequence)
- `test_the_file_source_rewinds_at_its_end_and_paces_at_its_rate`
