# harden2 system architecture, rev5 (2026-10-08)

The design of the harden2 ground station as decided in the rev5 sketch sessions (ledger SYS1 to
SK6). The drawing of this document is `01-system-architecture.html`. Section 10 lists every box
and every line of that drawing; the drawing is regenerated from this document and compared
(`tools/style/sketch_compare.py`). The session log that led here is `01-system-sketch.md`.

## 1. Purpose
A Hebrew voice-commanded drone ground station. The operator speaks, by F5 or into the phone. The
app turns the sentence into a flight command, a stop, a mode switch, a vision job, or a refusal.
It shows the camera with the highlights, talks back on the phone and the laptop, and records
every turn for replay and for timing.

## 2. The processes
The app is one Python process. Six other processes run beside it, every one created, watched and
destroyed by the app's supervisor, each with a graceful stop; a kill is only a logged last resort.
- The keyboard hook (C++): every key press and release, on the ROS2 topic /keyboard/in/raw.
- The ASR node, whisper (C++): F5 records, F5 again stops; the transcript on /asr_server/transcribe.
- The phone app, or its mock when CONTROL=mock: the drone commands and /tts over HTTP (:8080 |
  :8079); one persistent TCP line in, carrying the phone's transcripts.
- The gstreamer receiver (C++): the phone's H.264 decoded; bgr8 frames on ROS camera/stream.
- llama-server with Gemma 4 E4B: HTTP :18090; ONE slot, one request at a time.
- The SAM3 server, our process: a priority queue inside; it holds a frame slot by its count.
The operating system raises the child-exit signal (SIGCHLD) when a child exits.

## 3. The threads of the app
One owner thread and a set of producers and workers (SYS1).
- The main thread owns all app state: manual mode, the turns, the views, the chat, the
  last-drawn rows, quit. Every frame, 33 ms: it drains the message queue, acts, reads the status
  rows, draws, and calls waitKey(1).
- Three producer threads: the keys listener (ROS spin → Key), the mic listener (ROS spin →
  Transcript), the phone listener (TCP line only → Transcript).
- The supervisor thread: SIGCHLD → its own queue → the restart policy → the status rows.
- The recognizer worker, one: the route is pure functions; a plan blocks 0.5-1.5 s.
- The platform worker, one: sends the commands in order; HTTP blocks up to 3 s.
- The emergency thread, one: sleeps on an event; the main thread wakes it with a stop; it sends
  one POST and sleeps again. The phone's server (ktor, CIO) serves it beside an open mission call.
  Rejected: the stop through the platform worker's priority queue; a running POST blocks it (RVW1).
- The voice workers, two, one per voice: each speaks its FIFO in order; all sentences go to
  both voices; no cutting.
- The thread pool of 8 for the vision jobs: the 9th job is refused; a stop flag per job.
- The frame source thread: webcam, drone stream or file; it writes a slot and publishes latest.

## 4. The message queue and the hand-offs
One bounded multi-producer, single-consumer queue in arrival order; the main thread is its only
consumer. Five message kinds: Key, Transcript, Decision, PlatformReply, VisionResult. Under one
message per frame arrives at the measured rates.
The main thread's handling, in order:
- Transcript → the trigger table (pure): emergency, manual, auto, clear → act now. An emergency
  is STOP in manual mode and HALT in auto mode. Anything else → the route queue, in order.
  What a stop means (RVW6, RVW7): the running mission is cancelled; the one sentence still in
  planning is dropped, with a chat line and a log line; nothing pauses or resumes. Manual mode
  cancels the same way and hands the sticks to the RC; "auto" re-allows missions. The mechanism:
  an epoch counter in the main thread; a stop increments it; an older Decision is dropped.
  Rejected: pause and resume (the phone API has no pause; RVW5); cancelling only the current
  mission (RVW6).
- While the phone's row is WAITING, a mission is refused at once and said so. A stop and the
  manual switch are always attempted. Rejected: a time-to-live per queued command (RVW3).
- Decision → a mission → the command queue (409 if manual); a vision kind → start a job; a
  reject → say.
- PlatformReply → the turn's status → say → telemetry(turn) → perf(E2E).
- VisionResult → the job's view → say; telemetry(job) at an end state.
- Key → F1 quit; F2 stop every job; F4 manual, plus a stop; F5 release = the ASR mark.
- The status rows are read each frame; a changed state → a chat line.
- say = append to EVERY voice's FIFO.
The queues the main thread fills: a FIFO per voice (no cutting); the route FIFO; the priority
queue to the platform worker, the emergency first; submit(job) to the pool.
The workers reach outside: the voices POST /tts; the recognizer sends the chat for the plan; the
platform worker sends /c/fly and /c/stop; the jobs send detect requests, and describe chats.
The results come back as messages: Decision, PlatformReply, VisionResult.

## 5. The status rows
One row per part: (name, state, detail). Each part writes its own row with an atomic store. The
main thread reads the rows each frame. No process-event message exists (STA1).

## 6. The frame buffer
Shared memory: 32 slots, a "latest" index, a sequence number and a reference count per slot.
The counts are C11 atomics (SK5). The frame source is the only writer: it takes the next slot
whose count is zero, bumps its sequence, writes the pixels, sets "latest". A reader acquires
before it uses: it reads "latest", increments that slot's count, re-reads the sequence, and
retries on a mismatch (RVW4). A job acquires its slot before it sends the frame number to the
SAM3 server and releases after the reply; the server reads pixels only and touches no count
(RVW3). The other readers: the main thread for the draw, the telemetry. Rejected: a mutex per
slot, too heavy for one integer (SK4); hazard pointers, dropped once real atomics were proven
(SK5); the server claiming the slot on arrival (RVW3); copy-and-release (not needed, RVW3).

## 7. The records
ONE recorder per process (RCD1, 2026-10-18; perf and telemetry folded into it): spans (a duration
of our code), events (a fact with typed fields at an instant) and frames (pixels), from any
thread, with no handle. One byte ring per recording thread, written in place by reserve and
commit; the hot path packs numbers, never text. Frames go into pools while the job holds its slot.
One writer thread per process makes the JSON lines, the PNGs and the file record-<process>-<pid>.jsonl;
the first line is the clock line, re-emitted every 5 s; the names of keys and topics are written
once. Each process writes its own file; the report merges them by the clock lines and the request
id; the C++ processes are measured from our side, request to reply (RVW5 to RVW7). The design, the
survey of the field and the rulings: modules/01-recorder/recorder.md. Rejected: a shared-memory
ring for records (RVW6), a handle passed per module (PRF7), a sample contract (RCD4).

## 8. The timing forces (measured; the sources in 01-system-sketch.md section 4)
A screen frame: 33 ms. A warm plan: 489 ms alone, 1362 ms while SAM3 runs. A SAM3 pass: 410 ms
alone, 630 ms with Gemma busy, up to 1.9 s for three concepts. A phone HTTP request: up to 3 s
when the phone is dead. A laptop TTS sentence: seconds. The emergency budget: command to action
under 1 s. The rates: a transcript per 2 s; at most 8 vision results per s; a few keys per s.

## 9. The failure handling
The phone dead: the row WAITING, a probe every 2 s, the app lives. A child dies: a restart;
after 3 failed restarts a laptop part kills the app, a phone part waits for the user. SAM3 out of
GPU memory: its process dies and restarts. The video stalls: a planned restart after 6 s. A ninth
vision job: refused. Our own error, or a required child dead after three restarts, mid-flight: hand control to the
RC (the stop, then manual mode), notify the operator, then die (RVW4). At start-up, die at once.
A vision job: a SAM3 or Gemma failure ends the job with FAILED, its slot released; a disk error
or a bug in our code crashes (RVW4). A refused /tts or a Gemma timeout: a chat line and the row.
The phone's TCP line: an "ok" line per transcript back to the phone; the socket's keepalive
option detects a dead peer; the phone listener owns both (RVW5). The gstreamer receiver stays a
separate ROS2 node: one uniform image source for every platform (RVW5).
A real drone: human-only; the client refuses a non-loopback host without allowReal.

## 10. The rules every module inherits
A module never touches app state and never calls the app. A blocking step runs on a worker the
app created, or on the pool. A handle is a plain struct the app holds, Create and Destroy. A
pipeline step is a pure function. A process has a graceful stop. Shared memory is the frame
buffer and the status rows only. Atomics over mutexes (SK4).

## 11. Open items
The TCP line's speed advantage is unverified (SK6). Names come after the shapes (NAM3 applies).
A safety section is written once the design is final (RVW4). Full-load timing with p50, p90 and
max is remeasured before the headers (RVW3). Perf is reached through one entry point per
process, not a handle per Create (RVW4).

## 12. The drawing, box by box and line by line (the inventory the drawing is checked against)
Every text of the drawing, in drawing order:
- THE APP PROCESS
- python3 -m app.main
- The rule, and the lines
- Only the main thread changes app state. Every other thread
- produces a message, or takes work from a queue it filled.
- a message into the queue (multi-producer, one consumer)
- a FIFO queue to a worker thread
- HTTP, a TCP line, or the SAM3 socket
- a ROS2 topic
- shared memory with C11 atomics
- a variable written atomically, read each frame
- Δ
- STATUS ROWS
- one row per part: (name, state, detail)
- written by its owner with an atomic store
- read by the main thread each frame
- changed → a chat line
- keys listener
- ROS spin → Key
- mic listener
- ROS spin → Transcript
- Δ
- phone listener
- TCP line only → Transcript
- Δ
- supervisor thread
- SIGCHLD → its queue → rows
- MESSAGE QUEUE
- multi-producer, one consumer,
- bounded, arrival order
- Key
- Transcript
- Decision
- PlatformReply
- VisionResult
- under one message per frame
- producers: five threads, plus
- the job threads; one consumer
- drain
- MAIN THREAD, the one owner of app state. Every frame, 33 ms:
- 1  drain the queue; act on each message:
-    Transcript      → the trigger table (pure): emergency, manual, auto, clear → act now
-                      emergency = STOP in manual, HALT in auto; anything else → the route queue
-    Decision        → mission → the command queue (409 if manual) | vision → start a job | reject → say
-    PlatformReply   → the turn's status → say → telemetry(turn) → perf(E2E)
-    VisionResult    → the job's view → say | telemetry(job) at an end state
-    Key             → F1 quit · F2 stop every job · F4 manual (+ stop) · F5 release = the ASR mark
- 2  read the status rows; a changed state → a chat line        say = append to EVERY voice's FIFO
- 3  draw: the latest frame + views + the panes      4  waitKey(1)
- state owned here: manual, the turns, the views, the chat, the last-drawn rows, quit
- FIFO ×2, no cutting
- route FIFO
- priority queue, emergency 1st
- submit(job)
- Δ
- voice workers ×2
- speaks its FIFO in order
- all sentences, both voices
- recognizer worker
- the route is pure functions
- a plan blocks 0.5-1.5 s
- platform worker ×1
- sends in order
- HTTP blocks up to 3 s
- thread pool (8)
- the 9th job is refused
- a stop flag per job
- Decision
- PlatformReply
- VisionResult
- /tts
- chat: the plan
- /c/fly, /c/stop
- detect; describe
- frame source thread
- webcam | drone stream | file
- writes a slot; publishes latest
- Δ
- FRAME BUFFER, shared memory
- 32 slots · latest · a reference count per slot
- the counts are C11 atomics; any process may hold a slot
- readers of the latest frame
- telemetry
- opaque; const data in
- from any thread
- perf
- record(start, end)
- any thread, no lock
- OUTSIDE PROCESSES
- keyboard hook (C++)
- ROS /keyboard/in/raw
- ASR node, whisper (C++)
- ROS /asr_server/transcribe · F5 records
- Δ
- phone app | mock
- one persistent TCP line in · HTTP /c/*, /tts out
- the OS
- the child-exit signal (SIGCHLD)
- gstreamer receiver (C++)
- ROS camera/stream, bgr8
- llama-server, Gemma 4 E4B
- HTTP :18090 · ONE slot
- SAM3 server (our process)
- priority queue inside · holds a slot by its count
- All six are created, watched and destroyed
- by the supervisor. Each has a graceful stop.
- A kill is only a logged last resort.
- The SAM3 server increments the slot's count, reads, decrements.
- The same atomics as the app.

The lines of the drawing: 39 paths; by kind: l-http 8, l-msg 8, l-queue 9, l-ros 4, l-shm 6, l-sig 4.
Each path, kind and geometry:
- l-msg: M70,202 H130
- l-queue: M70,226 H130
- l-http: M70,250 H130
- l-ros: M70,274 H130
- l-shm: M70,298 H130
- l-sig: M70,322 H130
- l-sig: M735,330 V398
- l-sig: M920,330 H900 V285 H892
- l-msg: M920,90 H900 V375 H170 V398
- l-msg: M920,170 H900
- l-msg: M920,250 H900
- l-msg: M290,520 H328
- l-queue: M425,640 V678
- l-queue: M635,640 V678
- l-queue: M845,640 V678
- l-queue: M1045,640 V678
- l-queue: M425,708 V738
- l-queue: M635,708 V738
- l-queue: M845,708 V738
- l-queue: M1045,708 V738
- l-msg: M570,810 V860 H170 V822
- l-msg: M780,810 V860
- l-msg: M990,810 V860
- l-http: M490,810 V890 H1170 V250 H1218
- l-http: M700,810 V890
- l-http: M930,810 V890
- l-http: M1120,810 V890
- l-http: M1170,590 H1218
- l-http: M1170,690 H1218
- l-shm: M290,965 H328
- l-shm: M330,945 H320 V630 H328
- l-shm: M600,930 V915 H1140 V812
- l-shm: M730,990 H778
- l-ros: M1220,90 H1132
- l-ros: M1220,170 H1132
- l-http: M1220,250 H1132
- l-sig: M1220,330 H1132
- l-ros: M1660,410 H1690 V1045 H170 V1002
- l-shm: M1640,720 V1020 H530 V1002
