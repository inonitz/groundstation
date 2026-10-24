# rev5, step 1: the system sketch. The context, the forces, the reasoning, the draft (2026-10-04)

The record of the design session for the whole-app sketch (BRN1, BRN2). It grows with the
conversation. When the owner says the sketch is complete, its last section becomes the spec.

## 1. What the app is
A Hebrew voice-commanded drone ground station. The operator holds F5 and speaks, or speaks into
the phone. The app turns the sentence into one of: a flight command, a stop, a mode switch, a
vision job (highlight, count, describe), or a refusal. It shows the camera with the highlights,
talks back, and records everything for replay and for timing.

## 2. The actors around the app
| actor | how it reaches the app | how the app reaches it |
|---|---|---|
| the operator | F1 F2 F4 F5 through the keyboard hook; speech through the mic or the phone; q c t [ ] x in the window | the window; the voice (phone or laptop) |
| the phone app (the drone) | POST transcripts to our port 8080; streams H.264 video | HTTP: /c/fly, /c/takeoff, /c/land, /c/stop, /tts; the mock stands in when CONTROL=mock |
| whisper (the ASR node) | publishes a transcript on a ROS2 topic | the supervisor starts it; F5 is read by the node itself |
| Gemma (llama-server) | | HTTP on 127.0.0.1:18090; ONE slot (-np 1): one request at a time |
| SAM3 | | its own process (R2): a request names a frame; shared-memory frames |
| the OS | process exits (SIGCHLD); the GPU | the supervisor; the frame buffer |

## 3. The data that moves
| data | size | born on | consumed by |
|---|---|---|---|
| a transcript | a sentence | a listener thread | the recognizer |
| a decision | kind, mission JSON, target | the recognizer | the dispatch: platform, vision, or nothing |
| a platform command | a JSON list | the dispatch | the phone app (HTTP, up to 3 s timeout) |
| a frame | 2.6 MiB at 720p, 30 per second | the frame source | the screen, the vision jobs, the SAM3 process, the telemetry |
| a detection | up to 128 boxes; masks for the kept boxes, 112.5 KiB each packed | the SAM3 process | the job; then the screen; the telemetry |
| a vision result | the state of a job and its payload | a job thread | the screen (draw), the chat, the voice, the telemetry |
| a spoken sentence | a string | the dispatch | each voice |
| a status row | (name, state, detail) | its owner's thread | the status pane |
| a telemetry record | a turn, a pass with its frame, a job | the main thread and the job threads | disk |
| a perf event | 128 bytes | any thread | disk |

## 4. The timing forces (measured unless marked)
| step | time | source |
|---|---|---|
| a screen frame | 33 ms at 30 fps | the webcam, MJPG 720p (2026-09-08) |
| a Gemma plan, warm | 489 ms p50 alone; 1362 ms p50 while SAM3 runs | bench/gemma-plan-timing (2026-10-01) |
| a SAM3 pass, 1 concept | 410 ms alone; 630 ms with Gemma busy | bench/sam3-assessment (2026-09-28) |
| a SAM3 pass, 3 concepts | 1.2 s alone; 1.9 s with Gemma busy | the same |
| a highlight refresh | every 1.0 s per job (SAM3_PERIOD) | config |
| a phone HTTP request | until the reply; 3 s timeout when the phone is dead | dji_app/client.py |
| a laptop TTS sentence | blocks until spoken: seconds | audio/tts_laptop.py |
| the emergency stop | the budget: command to action under 1 s | ROADMAP; log/perf.py |
| the frame through shared memory | 0.1 ms | bench/sam3-assessment |
| vision jobs alive | at most 8 | config (VISION_MAX_ACTIVE_TASKS) |

What the numbers force: every model call and every network call is a blocking step of 0.4 s to
3 s. The screen must keep its 33 ms. So no blocking step may run on the main thread (SYS1 made
this the rule). An emergency stop must never wait behind a plan or a mission.

The message rates are tiny: transcripts about one per 2 s; vision results at most 8 per second
(8 jobs, one refresh each per second); keys a few per second; process events rare; decisions one
per transcript. At 30 frames per second the main loop sees under one message per frame.

## 5. The failure modes the sketch must carry
| failure | today's rule | source |
|---|---|---|
| the phone does not answer | the row goes WAITING; a probe every 2 s; the app lives | 2026-09-23, U6 |
| a process dies | restart; after 3 failed restarts a laptop part kills the app, a phone part waits | 2026-09-22 |
| SAM3 out of GPU memory | today the app dies; with SAM3 in its own process, the process dies and restarts | R2 |
| the video stalls | after 6 s a planned restart of the gstreamer receiver | config |
| too many vision jobs | the ninth is refused, never queued | 2026-09-22 |
| our own error anywhere | die with the reason; stop every process; flush perf first | 2026-09-19, C.1 |
| a real drone | HUMAN-ONLY; the client refuses a non-loopback host without allowReal | CLAUDE.md |

## 6. The rulings that bind the sketch
SYS1 one owner thread for all app state. OWN1 the app owns every handle. PROC2 Begin and End for
every process, a graceful stop. TEL1, PRF2 opaque loggers that take const data. REC1 the
recognizer is pure functions. ATM1 `_Atomic` types. TN2, T3C, T3C (2): several highlights, clear
all, a jobs pane. STOP1 (3), T1 (2), AUTO1: the trigger table. 2026-09-24: each part owns its
status row. 2026-09-22: a diagram shows every queue, thread and hand-off.

## 7. The reasoning, from the forces to a shape

### 7.1 The consequence of one owner thread
Only the main thread changes app state. So every input must arrive as a message: a transcript, a
key, a decision, a vision result, a process event. Every output that blocks must leave as work for
a worker: a plan, a SAM3 pass, an HTTP command, a spoken sentence. The main loop is: drain the
inbox, act, draw, at 30 Hz.

### 7.2 One inbox or several
The rates in section 4 say the inbox is nearly empty at every frame. One bounded queue of tagged
messages keeps the arrival order and needs one drain. A second "urgent" lane would protect the
keys from a burst of vision updates; at 8 updates per second no burst exists. So: one inbox.

### 7.3 The emergency stop and the serial planner
Gemma has one slot. Two plans in flight queue at the server anyway. So the recognizer's model
step is serial by nature: ONE recognizer worker with a queue of transcripts, not a job per
transcript. The hazard: an emergency transcript ("stop") arriving while that worker is inside a
1.4 s plan would wait behind it. The cure is in the recognizer's own order: steps 1 to 3 (the
trigger table, the fixed commands, the negation guard) are pure and take microseconds; only step
5 (the plan) blocks. So the main thread runs steps 1 to 3 on arrival; a sentence that one of them
answers is decided at once; only the rest goes to the worker. An emergency never meets the model.

### 7.4 The platform commands
A command is an HTTP request that can block up to 3 s. It cannot run on the main thread. It must
keep order (a mission, then a stop) and an emergency must overtake a queued mission. So: one
platform worker with a queue of commands and a priority for the emergency stop. Manual mode is
plain state of the main thread: while it is on, the main thread never enqueues a mission; it
answers 409 itself. No atomic flag is needed for manual mode.

### 7.5 The vision jobs
Parallel by nature: several highlights at once, each its own loop of SAM3 passes; the SAM3
process orders the passes (a command before a refresh). So the vision jobs run on the generic
scheduler (your answer). Each job publishes VisionResult messages to the inbox. The screen
draws the latest result per job, which the main thread keeps as its own view.

### 7.6 The voices
A sentence to the phone returns at once; a sentence to the laptop blocks for seconds. One worker
per voice, each with one pending sentence (round 4, 1.4).

### 7.7 What is shared outside the messages, by design
Two things, both atomics, both read-mostly:
- the frame buffer: `m_latest` and the per-slot `m_readerCount`; the writer is the frame source,
  the readers are the screen, the jobs, the SAM3 process, the telemetry;
- the status rows: an atomic pointer per row; written by the row's owner thread, read by the
  status pane.
Everything else crosses a thread as a message or as const data into a logger.

### 7.8 The loggers
Telemetry takes const data from the main thread (turns, job ends) AND from the job threads (a
pass with its frame, while the frame is held); it serializes inside. Perf takes events from any
thread without a lock (PRF2).

## 8. The draft of the sketch (the one page; the conversation refines it)

### 8.1 The layers and who owns what
| layer | units | owned by |
|---|---|---|
| outside processes | llama-server, the SAM3 server, the ASR node, the keyboard hook, the gstreamer receiver, the mock | the supervisor (launch, watch, stop) |
| services | the supervisor, perf, telemetry, the frame buffer, the llama handle, the SAM3 handle, the phone-app client | the App |
| permanent workers | the mic listener, the phone listener, the recognizer worker, the platform worker, each voice, the frame source, the supervisor thread | the App, through Begin / End |
| on-demand workers | the vision jobs, on the generic JobScheduler | the App starts and stops them |
| pure functions | the recognizer's steps, the vision ops | nobody; called where needed |
| the owner thread | the inbox, the dispatch, the app state, the views, the chat, the screen | the App, on the main thread |

### 8.2 The data flow, every thread and hand-off
```
 [ASR node] --ROS topic--> (mic listener thread) ----MSG_TRANSCRIPT----+
 [phone app] --TCP line--> (phone listener thread) --MSG_TRANSCRIPT----+
 [keyboard hook] --ROS topic--> (keys listener thread) ---MSG_KEY------+
 [SIGCHLD] --> (supervisor thread) ----------------MSG_PROCESS_EVENT----+
 (recognizer worker) <--transcript queue-- main; ----MSG_DECISION------+
 (vision job threads, <= 8) ---------------------MSG_VISION_RESULT-----+
                                                                       v
                                                        +--------- the INBOX ---------+
                                                        |  one bounded queue, tagged  |
                                                        +-------------+---------------+
                                                                      v
   MAIN THREAD, every frame (33 ms):                                   |
     1. drain the inbox; for each message:                             |
        TRANSCRIPT -> steps 1-3 of the recognizer (pure) -> decided?   |
                      yes: act; no: push to the recognizer worker      |
        DECISION   -> act: a command to the platform queue             |
                           | a vision job on the scheduler             |
                           | a refusal: chat + voice                   |
        VISION_RESULT -> the job's view; chat; voice; telemetry        |
        KEY        -> F1 quit | F2 stop every highlight | F4 manual    |
        PROCESS_EVENT -> the status row text, a chat line              |
     2. draw: the latest frame (frame buffer) + every job's latest     |
        boxes and masks (the views) + the panes                        |
     3. waitKey(1): the window keys                                    |
                                                                       |
 main --command queue (emergency first)--> (platform worker) --HTTP--> [phone app | mock]
 main --sentence--> (voice worker, per voice) --POST /tts | sounddevice--> the operator
 main --JobSchedulerStart--> (job thread) --Sam3Request (frame number)--> [SAM3 server]
                                            <--Detection (boxes, packed masks)--
 (frame source thread) --writes slots--> [FRAME BUFFER, shared memory] <--reads-- main, jobs, SAM3, telemetry
 any thread --const data--> [telemetry] --> disk      any thread --PerfRecord--> [perf] --> disk
```

### 8.3 What a module may and may not do (the rules every module review inherits)
1. A module never touches app state. It returns a value, pushes a message, or writes const data
   into a logger.
2. A module never calls the app. There are no callbacks into the app.
3. A blocking step runs on a worker the App began, or on the scheduler.
4. A handle is a plain struct the App holds; Begin and End; no module keeps a hidden singleton.
5. A pipeline step is a pure function over data.
6. A process has a graceful stop; a kill is a logged last resort.
7. Shared memory is limited to the frame buffer and the status rows, both atomic.

## 9. Open after round 1 (answered in section 10)
- Whether the recognizer's steps 1 to 3 on the main thread and step 5 on the worker is the
  split you want (7.3), or the whole route stays on the worker with the emergency table checked
  on the listener thread instead.
- Whether the platform worker is its own thread (7.4) or a job on the scheduler with a
  priority; my reasoning prefers the thread because commands must keep their order.
- The names of the units; they come after the shapes.

## 10. Round 2 of the conversation (2026-10-04): your answers and the pseudocode

Your answers: sections 1 to 5 stand ("Correct", "Yeah, mostly" on the rates). The verbs are
Create and Destroy (NAM3). The status rows are not shared: each part owns an atomic state and a
short detail; the UI reads them (STA1). You asked for pseudocode on the decisions, the
recognizer's place, the platform worker, and the voices. Here it is, in one piece.

### 10.1 Why a decision is a message, and where the fast path runs
A decision must come back to the main thread because only the main thread may act: it holds
manual mode, the turn, the chat, the telemetry, the scheduler. The recognizer worker blocks on
Gemma, so it cannot be the main thread. The fast path never goes to the worker: the main thread
calls ONE pure function of the recognizer, the trigger table, on arrival. That is the only
recognizer code on the main thread. The whole route, steps 1 to 6, lives on the worker. So no
responsibility is split: the recognizer module owns both functions; the main thread only chooses
which one to call first.

Why every non-emergency sentence goes through the worker, even a fixed command that needs no
model: order. "Fly forward 5 m" (no model) said after "go to the car" (a plan) must not overtake
it. The worker's queue keeps the order of the sentences; it is the store of the routing jobs.
Gemma's one slot is why ONE worker is enough, not why the queue is unneeded.

### 10.2 The pseudocode of the whole turn path
```
# the listener threads (the mic topic, the phone socket, the keys topic): they only produce
on_transcript(text, input):      InboxPush(inbox, MSG_TRANSCRIPT{text, input, at = PerfNow()})
on_key(code, action):            InboxPush(inbox, MSG_KEY{code, action, at = PerfNow()})

# the main thread, every frame
while InboxPop(inbox, m):
    switch m.kind:

    case MSG_TRANSCRIPT:
        turn = TurnsBegin(turns, m.text, m.input, m.at)          # main-thread state: seq, the clip claim
        ChatAppend(chat, CHAT_USER, m.text)
        trigger = RecognizerMatchTrigger(m.text)                  # PURE; the trigger table; microseconds
        if trigger == TRIGGER_EMERGENCY:                          # the main thread knows manual; the worker does not
            PlatformQueuePush(platformQ, {turn.seq, manual ? CMD_STOP : CMD_HALT}, FIRST)
            TurnsDecided(turns, turn.seq, DECIDE_EMERGENCY)
        elif trigger == TRIGGER_MANUAL or trigger == TRIGGER_AUTO:
            manual = (trigger == TRIGGER_MANUAL)                  # plain main-thread state
            if manual: PlatformQueuePush(platformQ, {turn.seq, CMD_STOP}, FIRST)
            TurnsDecided(turns, turn.seq, DECIDE_MANUAL | DECIDE_AUTO)
            say(wording)                                          # chat + every voice
        elif trigger == TRIGGER_CLEAR:
            for job in views: JobSchedulerRequestStop(sched, job.id)
            TurnsDecided(turns, turn.seq, DECIDE_CLEAR); say(wording)
        else:
            RouteQueuePush(routeQ, {turn.seq, m.text})            # stored in order for the recognizer worker

    case MSG_DECISION:                                            # from the recognizer worker
        turn = TurnsFind(turns, m.seq); turn.decision = m.decision
        switch m.decision.kind:
            case DECIDE_MISSION:
                if manual: turn.platformStatus = 409; say("refused: manual mode")
                else:      PlatformQueuePush(platformQ, {turn.seq, CMD_LIST, m.decision.missionJson}, IN_ORDER)
            case DECIDE_HIGHLIGHT, DECIDE_COUNT, DECIDE_DESCRIBE:
                spec = VisionJobSpecFrom(turn, handles)           # by value; the job owns its copy
                turn.visionJob = JobSchedulerStart(sched, <JobRun of the kind>, spec)
                if turn.visionJob == 0: say("too many vision jobs")
            case DECIDE_REJECT, DECIDE_PLANNER_FAILED, DECIDE_EMPTY:
                say(wording)                                      # nothing is sent
        if nothing waits for a reply: TelemetryRecordTurn(telemetry, &turn); TurnsEnd(turns, turn.seq)

    case MSG_PLATFORM_REPLY:                                      # from the platform worker
        turn = TurnsFind(turns, m.seq); turn.platformStatus = m.status
        say(wording of m.status)
        PerfRecord(perf, PERF_E2E, turn.startedAt, m.at, "")
        TelemetryRecordTurn(telemetry, &turn); TurnsEnd(turns, turn.seq)

    case MSG_VISION_RESULT:                                       # from a job thread
        view = ViewsApply(views, &m.result)                       # the latest result per job, main-thread memory
        if m.result.state is an end state or an answer: say(wording); TelemetryRecordVisionJob(telemetry, ...)
        if first TRACKING of the job: PerfRecord(perf, PERF_E2E, view.requestedAt, m.at, "box")

    case MSG_KEY:
        F1: quit = true     F2: stop every highlight     F4: manual = !manual (+ CMD_STOP when on)
        F5 release: pttReleasedAt = m.at

    case MSG_PROCESS_EVENT:  ChatAppend(chat, CHAT_SYSTEM, m.text)     # the row itself is the part's atomic

frame = FrameBufferAcquireLatest(frames); ScreenDraw(screen, frame, views, chat, statusRows); FrameBufferRelease(frames, frame)
key = waitKey(1); handle the window keys (q c t [ ] x)

# the recognizer worker thread: ONE, serial (Gemma has one slot); its queue stores the routing jobs in order
loop:
    (seq, text) = RouteQueuePop(routeQ)                           # blocks while empty
    decision = RecognizerRoute(text, llama)                       # steps 1-6; step 5 blocks on Gemma 0.5-1.5 s
    InboxPush(inbox, MSG_DECISION{seq, decision, at = PerfNow()})

# the platform worker thread: ONE, ordered; the emergency stop jumps the queue
loop:
    cmd = PlatformQueuePop(platformQ)                             # FIRST entries before IN_ORDER entries
    status = switch cmd.kind:                                     # the worker never reads manual mode
        CMD_HALT:  DjiAppSendCmdList(dji, kHaltMissionJson)       # the emergency in auto mode: keeps our sticks
        CMD_STOP:  DjiAppSendStop(dji)                            # the emergency in manual mode, and manual-on
        CMD_LIST:  DjiAppSendCmdList(dji, cmd.json)               # blocks until the reply, up to 3 s
    InboxPush(inbox, MSG_PLATFORM_REPLY{cmd.seq, status, at = PerfNow()})

# a voice worker: ONE per voice (phone, laptop)
loop:
    wait on the voice's condition until pending != NULL
    text = take pending
    speak(text)                                                   # phone: POST /tts, returns at once; laptop: blocks until spoken
```
Why the platform worker is a thread and not a job on the scheduler: the scheduler runs jobs at
the same time; two missions in flight could reach the phone in either order; and a scheduler has
no notion of "this one first". A single ordered queue with one consumer has both.

### 10.3 The voices: the rule to settle
Your sentence: "the worker pool for the Speech needs to wait until all of its elements are clear
until we can say anything again." Two readings; the pseudocode differs in one line.
- Cut and replace (today's rule, 2026-09-23 "latest answer wins"): `say(text)` sets every
  voice's pending slot and cuts what plays; the operator hears the newest sentence at once.
- Wait for the pool: `say(text)` is refused, or queued, while any voice still speaks; the
  operator hears every sentence in full, in order, later.
Which one do you mean? My reasoning: a stop confirmation must not wait behind a describe answer
of 10 s on the laptop voice, so the newest-wins rule stays; a queue of one is enough.

### 10.4 The status rows (STA1)
Each part owns `_Atomic SysState m_state` and a detail string of at most 64 bytes. The UI thread
reads the state atomically and copies the detail. A torn detail is a garbled line for one frame,
never a wrong state. No message, no lock. The "process event" message carries only the chat line.

### 10.5 Verified against the record (2026-10-06, the owner: "are you sure this is the design you intended on?")
I read the diagram against sections 7 and 10. Two corrections, both now in the pseudocode above:
1. The platform worker never reads manual mode. The main thread chooses the command: CMD_STOP
   while manual (the RC keeps the sticks), CMD_HALT otherwise (a zero-delay mission keeps our
   sticks). The worker only sends what the queue holds.
2. The describe job calls llama-server too, with a JPEG of the frame it holds. The first drawing
   showed only the SAM3 call from the jobs.
Three constraints the module reviews inherit, found in the same check:
- The llama handle is used by two threads at once: the recognizer worker and a describe job. The
  SAM3 handle by up to eight job threads. The phone-app handle by the platform worker and the
  phone voice. Each handle's send is thread-safe by contract: one connection per call, or a lock
  inside the handle. The module review of each decides which.
- The mic clip claim is a rename on the main thread, under a millisecond. It must happen at the
  transcript's arrival, before the next clip exists; the turn's record may come seconds later.
- A VisionResult carries up to 16 packed masks, 1.8 MiB. In Python the message holds references;
  in the C sketch the message owns a mask block the consumer frees with the next update of that
  job. No copy per hop.
Everything else in the drawing matches the record.

## 11. The ponytail pass (2026-10-06; the owner: "use the ponytail skill to examine our current design")

The ladder: does it need to exist; already in the codebase; stdlib; one line; only then code.

| piece of the sketch | rung | the lazy version | what it costs |
|---|---|---|---|
| the inbox | stdlib | `queue.Queue(maxsize=256)`; a message is a dataclass per kind; the drain is `get_nowait` until `queue.Empty`; dispatch by `match type(m)` | nothing; no Inbox type, no tag enum |
| the route queue | stdlib | `queue.Queue()` | nothing |
| the command queue, emergency first | stdlib | `queue.PriorityQueue()` of `(priority, seq, cmd)` | nothing |
| the recognizer worker, the platform worker | stdlib | one `threading.Thread` each, a `while` over its queue | nothing |
| a voice worker | already here | audio/speech_out.py's worker loop, one instance per voice; the pending slot is a variable plus an `Event` | nothing |
| the JobScheduler | stdlib | `ThreadPoolExecutor(max_workers=8)`, a live count checked before submit (the ninth is refused, as ruled), an `Event` per job as its stop flag | about 20 lines over the executor; the dispatcher thread and its condition go |
| MSG_PROCESS_EVENT | delete | the main thread reads every status row each frame anyway; a row whose state changed since the last draw gets its chat line there | one message kind and one producer fewer; a transient state can be missed, harmless for a row |
| the status rows | one line | `self.row = (name, state, detail)`: a tuple assignment is atomic under the GIL; the lock in runtime/status.py goes | nothing (STA1 says the same) |
| the supervisor's SIGCHLD plus a queue | lazier alternative | one thread, `for p in procs: p.poll()` every 0.5 s; no signal handler on the main thread | a crash is seen up to 0.5 s late; a restart takes seconds anyway. SUP1 rules one thread; the signal is the owner's preference, so he picks |
| the frame buffer's cross-process atomics | delete | the SAM3 process never holds a slot. The job holds the pin in the app process, sends the frame number, and releases after the reply. One process owns the counters; they are plain ints under the GIL. The server reads `np.ndarray(buffer=shm.buf)[slot]` | the server needs no Acquire, no Release, no "frame gone" check; `multiprocessing.shared_memory.SharedMemory` is stdlib |
| the shared-memory ring itself | name it, keep by ruling | a frame over the socket costs 3.1 ms per pass against 0.1 ms; a pass is 410 ms, so the ring saves under 1 % | the ring is the owner's requirement (R2, R3 "I have no problem with the implementation"); not re-argued |
| the perf logger | stdlib | `time.monotonic_ns`, a preallocated list, `itertools.count` for the index, one writer thread, `json.dumps` | about 60 lines; today's 208 go |
| the telemetry logger | stdlib + already here | `queue.Queue` and a writer thread around today's log/session.py writes (`cv2.imwrite`, the atomic json) | the deep copy is the queue's put of a frozen dataclass |
| the two phone channels | delete one | TCP lines only; the HTTP sniffing and the dedup go (Q2 a) | the POST is answered 200 and ignored until the phone app stops sending it |
| the ROS listeners | already here | runtime/ros.py's Subscription, unchanged | nothing |
| the SAM3 priority (command before refresh) | stdlib | `queue.PriorityQueue` inside the server; today's PriorityLock goes | nothing |
| the recognizer's step functions | already here | fast_path.py, bypass.py, guards.py, rewrites.py, lexicon.py as pure functions; the Recognizer class goes | nothing |

The three biggest cuts: the SAM3 process touches no counter (one owner of the ring's state); no
MSG_PROCESS_EVENT; the JobScheduler is a ThreadPoolExecutor with a stop flag per job.

What ponytail does not touch: the owner thread (SYS1), Create/Destroy for every process with a
graceful stop (PROC2), the handles owned by the app (OWN1), the const-data loggers (TEL1, PRF2),
the trigger table on arrival (the emergency path), input checks at the phone socket.

### 11.1 What the ponytail pass changed in the design itself (the owner, 2026-10-06: "besides the manual polling of the supervisor processes I don't understand what is different inherently in the design itself")
Four things; the rest of section 11 is the build of the same design.
1. The frame pins have one owner: the app process. The job holds the pin for the whole request; the
   SAM3 server only reads. The server's acquire, release and "frame gone" path go.
2. Process state is pulled, not pushed: the main thread reads the status rows each frame; no
   MSG_PROCESS_EVENT. This makes two input paths (messages and rows) where the design had one.
3. The phone speaks over one channel: TCP lines; no dedup.
4. The supervisor polls every 0.5 s instead of handling SIGCHLD.
The sketch otherwise passed the ladder: no component for a speculative need; the ring is the one
flagged piece and stays by ruling. The agent's view: take 1 and 3; 2 only if two input paths are
acceptable; 4 by preference. Open for the owner.

### 11.2 The owner's answers on the four changes (2026-10-06, SK3 and SK4)
1. Taken, without a counter. Each reader thread publishes the slot it reads in its own
   variable: a hazard pointer. The readers: the UI thread, each job thread, the telemetry writer;
   at most ten. A reader stores the slot index before it reads the slot and clears it after. One
   store is atomic (under the GIL; an atomic store in C). The writer scans the hazard pointers
   before it reuses a slot and skips any slot it finds. The one race: the reader reads "latest",
   then publishes; the writer could reuse that slot between the two steps. The fix: after
   publishing, the reader re-reads the slot's sequence number and retries on a mismatch. No mutex.
2. STA1 stands. Each component writes its own row with an atomic store. The UI thread reads the
   rows once per frame, for the pane; a row whose state changed since the last frame gets its chat
   line there. No process-event message; the supervisor thread is not a producer of the queue.
3. One channel. Which one: the persistent socket is faster by one TCP handshake per sentence (a
   few milliseconds on the hotspot, unverified; our server answers "Connection: close", so a POST
   opens a new connection each time). REST is more reliable: the phone gets a 200 per sentence and
   knows the laptop took it; after a WiFi drop the next POST works by itself; the persistent socket
   dies with the WiFi and the phone must reconnect. A WebSocket would give a persistent, framed,
   acknowledged channel (the phone app already serves one for the sticks) at the cost of a
   WebSocket server on the laptop; not needed for one sentence per 2 s. The agent's recommendation:
   REST only; this reverses the earlier TCP-only suggestion, which chose speed over reliability.
   Open for the owner.
4. The supervisor is event-driven. The operating system raises the child-exit signal; the handler
   (one line, on the main thread by Python's rule) puts a token on the supervisor's queue; the
   supervisor thread wakes, reads each child's exit status without blocking, applies the restart
   policy and writes the child's row. No polling. One thread (SUP1).

### 11.3 Atomic operations in Python (2026-10-06, SK5; replaces 11.2 point 1)
The `atomics` package (PyPI, 1.0.3) wraps C11 atomics. It gives fetch_inc, fetch_dec, load,
store, exchange and compare-exchange on a plain int (`atomics.atomic`) and on any buffer
(`atomics.atomicview(buffer=..., atype=INT)`), a shared-memory buffer included. Measured on this
machine: eight threads, 100,000 increments and 100,000 decrements each, final value 0; two
processes on one shared-memory int, 100,000 increments each, final value 200,000; about 4 us per
operation, Python call overhead included. The install is one scripted line.

So the slot reference count is one 4-byte atomic per slot, inside the shared block, next to the
slot's sequence number. A reader does fetch_inc before it reads the slot and fetch_dec after. The
writer loads the count and skips a slot above zero. The reader's race check stays: after the
increment, compare the slot's sequence number with the one it expected; on a mismatch, decrement
and retry. No mutex. No hazard pointers. The same code works for the app's threads and for the
SAM3 process, so the "app owns the counts" rule of 11.2 becomes a choice, not a need.

### 11.4 The owner's answers on the two open items (2026-10-06, SK6)
1. The phone channel: the persistent TCP line. The owner recalls a measurement where it was
   faster; the agent searches the tree and the git history for it (section 11.5).
2. The voices: every sentence is spoken on both voices, in order. A FIFO per voice; each voice
   worker speaks its queue; no cutting. The main thread's say() appends to every voice's FIFO.
The drawing with both answers, and every change since the first sketch marked:
03-system-sketch-rev2.html.

### 11.5 The TCP against REST measurement: searched 2026-10-06, not found
Searched: the working tree (bench, tools, docs), docs/HISTORY.md, the research documents, and the
commit messages of every branch. No measurement of the phone's transcript channel exists.
What exists:
- Commit dcf4a25 (2026-09-01): "phone_ears TCP channel fixed (phantom arg killed every TCP
  transcript; REST twin masked it) ... live desk loop verified: Hebrew over REST+TCP, dedup".
- HISTORY.md, 2026-09-01: the laptop side "matched to the app's real contract (POST /input +
  raw-TCP JSON)". The double send is the phone app's contract; the laptop only mirrored it.
- HISTORY.md, 2026-08-25/26: "transport latency WS p95 24 ms / telemetry p95 47 ms, zero loss".
  That is the DJI control link, laptop to phone, over a WebSocket. Not the transcript channel.
So the TCP line stays by the owner's ruling (SK6). Its speed advantage is unverified. The
measurement is cheap once the phone is on: the listener stamps both arrivals of the same sentence
and logs the gap, over 20 sentences. It needs the phone, so it waits for the webcam or field test.

### 11.6 Facts found 2026-10-11 for the review's questions
- The phone app's API server is ktor on the CIO engine (ApiServer.kt line 131). Each request is a
  coroutine; requests are served concurrently. A /c/stop is served while a /c/fly is still open.
  So a separate emergency sender in the app does reach the phone at once.
- On the phone, /c/stop calls stop(emergency = true) (DJIAircraft.kt line 84): it stops the
  intelligent missions, then issues KeyStopAutoLanding and KeyEmergencyStop, then KeyStopTakeoff.
- die() in the design today (runtime/fatal.py; document section 9): print the reason, run the
  registered cleanups in order (perf flush first, then the supervisor stops every child), then
  os._exit(1). It sends nothing to the aircraft.
- An exception inside a function submitted to a ThreadPoolExecutor is stored in its Future; it
  never reaches threading.excepthook, so the crash hook that kills the app today would not see
  it. Today's dispatcher runs a plain thread per job, where the hook does see it.
