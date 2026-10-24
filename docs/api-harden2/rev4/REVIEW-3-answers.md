# Round 3: the answers, the plan, the decisions

Written 2026-10-02 for the owner's round-3 review (REVIEW-3-owner.md, HDR5). Rewritten
2026-10-03 as structured items (W3). Every point is answered under its own heading. The
heading quotes the owner's words. The headers are NOT changed yet: the owner reviews this
file first.

| mark | meaning |
|---|---|
| R3 n.m | the owner's round-3 point |
| R2, R1 | the round-2 and round-1 reviews |
| a ledger ID | docs/spec-harden2-cleanup.md, "Decision ledger" |
| code: file.py | today's code, projects/integration_harden2 |
| D n | a decision for the owner, section 4 |
| PROPOSED | the agent's proposal, not a ruling |

## 0. Where we are

### 0.1 Files touched since the compaction
- None. Only reads.

### 0.2 Written by this session before the compaction
| file | content |
|---|---|
| docs/api-harden2/rev4/*.h (17) | the rev4 drafts, laid out per guidelines.md (HDR4) |
| rev4/README.md, DESIGN.md, REVIEW-2-owner.md | the state, the round-1 answers, the round-2 words |
| tools/style/header_layout.py | the layout tool |
| docs/spec-harden2-cleanup.md | the ledger rows CP3 to HDR4 |
| docs/task-active-harden2-handoff-2026-10-02.md | the handoff to the building agent |
| docs/HISTORY.md, docs/harden2-status.md | the day's entries |

### 0.3 The global steps (the road to the freeze, RM1)
| step | state |
|---|---|
| 1. the joint review of the labels | done (JR4-JR17, MIL1) |
| 2. B2 and the benchmark rerun | done (473 of 545 PASS; whisper WER 9.6 %) |
| 3. the cleanup | done |
| 4. the code review | done; nothing fixed (10 verified findings; the thermo-nuclear review) |
| 4a. the blocker | the headers and the code are not 1:1 (API1) |
| 4b. the ground truth | GT1: rev2 (v2.3), rev3 (v2.3 + the rulings), GAPS.md |
| 4c. the redesign | rev4 with the owner: rounds 1, 2, 3. WE ARE HERE. Planning only (GT1 (2)) |
| 5. the owner's webcam test | waits for the build |
| 6. the field test | waits |
| 7. the walk-through | waits |
| 8. the doc sweep, the commits, the freeze | waits |

### 0.4 The local steps (this round)
1. This file: the answers, the plan, the general points, the decisions.
2. The owner rules on D1 to D11.
3. The agent applies the rulings to the rev4 headers.
4. A GAPS document for rev4; the handoff update.
5. The building agent implements, overnight.

## 1. The answers

### 1. audio.h

#### 1.1 "What is the point of AsrServerProcess? what is it launching? What does the process actually do?"
- **Launches:** `llm_to_action_asr_server`, our native C++ ASR node
  (projects/llm_to_action/source/asr/asr_node.hpp).
- **Command line** (code: audio/asr_ros.py, argv()):

| flag | value | meaning |
|---|---|---|
| --backend | whisper-whisper | the whisper.cpp backend |
| --model | ivrit-ai whisper-large-v3-turbo, ggml q5_k | the Hebrew model |
| --fa | | flash attention |
| --language | he | Hebrew |
| --threads | 1 | one CPU thread |
| --gid | 0 | the GPU |
| --captureid | ASR_CAPTUREID, optional | the microphone |
| --record --recordDir | <session>/asr_clips, when RECORD=1 | save each clip |
| env PULSE_SERVER | unix:/tmp/pulse-socket | the host's sound server |

- **What the process does, in order:**
  1. Opens the laptop microphone through PulseAudio, 16 kHz.
  2. Subscribes to the keyboard hook's topic, /keyboard/in/raw.
  3. F5 pressed: recording starts. F5 pressed again: recording stops. A consumer thread wakes.
  4. The consumer runs whisper on the recorded audio.
  5. With --record it first writes the clip: audio_<n>_<time>.wav.
  6. It publishes the text on /asr_server/transcribe (std_msgs/String).
- **Supervision:** required. A crash restarts it. After 3 failed restarts the app dies.
- **Fault:** none of this was in the header.
- **Change:** 2.1.

#### 1.2 "How does the phoneBridge know on what IP to listen? How does it interface with AsrServerProcess?"
- **The IP:** it binds 0.0.0.0, every interface, port 8080 (code: audio/asr_phone.py). The laptop picks no IP.
- **The phone:** holds the laptop's hotspot IP in its own settings (VoiceControlFragment, with a fixme).
- **Two channels:** the phone POSTs {"text": ...} and sends the same line over TCP. The bridge drops the duplicate.
- **The ASR server:** no interface at all. Two independent inputs.
- **Where they meet:** rev4: the one transcript topic (PROPOSED, R2 1.). Today: the same callback; the phone path never touches ROS.

#### 1.3 "split to audio_in.h and audio_out.h"
- **Ruling AUD2.** Done in the header pass (2.1).

#### 1.4 "What happens if we need to streamline a sentence both from the phone AND the laptop? ... won't they stall each other?"
- **Today** (code: audio/speech_out.py): one worker thread; one pending sentence; the newest wins.
- **One sentence, both outputs:** spoken in series. The phone first: a POST that returns at once. The laptop second: blocks until the sentence ends.
- **The stall:** a phone that does not answer holds the POST up to 3 s. The laptop voice waits that long. This is real.
- **Two sentences close together:** the second replaces the first. What plays is cut. Nothing queues. No stall. Ruled 2026-09-23 (latest answer wins).
- **Change:** D5, one worker per voice.

### 2. dji_app.h

#### 2.1 "Why does it still take a handle to perf if it isn't using perf in the struct?"
- **Today:** the client holds a Perf. `_command()` ends the "e2e" timing when any command gets a reply (code: dji_app/client.py).
- **Fault:** the header listed Perf as an argument and left the member out.
- **Change:** the client stops timing turns. The caller, which holds the turn, ends the timing (D6).

#### 2.2 "What is the point of DjiMockProcess actually?"
- **What it runs:** tools/dji_mock/mock_apiserver.py (aiohttp) on 127.0.0.1:8079, when CONTROL=mock.
- **What it serves:** the frozen protocol: GET /status/*, POST /c/takeoff, /c/land, /c/fly, /c/stop, /tts, WS /c/ws/sticks.
- **What it does:** integrates a fake velocity into a position at 20 Hz. Writes every command to mock_commands.log.
- **Why:** every run that is not the human's real-drone run sends its commands to it. The command path runs for real, with no aircraft (CLAUDE.md).
- **Why here:** it stands in for the phone app this module talks to.
- **Supervision:** not required. Past 3 failed restarts the row goes WAITING.

#### 2.3 "API Looks good besides that."
- Noted.

#### 2.4 "Is the handling of commands ... handled by the flight controller now? ... When manual=true are commands being dropped into a sink?"
- **Yes.** The controller is the only caller of the motion requests.
- **Manual on:** the controller does not call them. The request never leaves the controller. The caller gets 409 at once.
- **No sink.** Nothing is queued or dropped. The app words the refusal.
- **Today:** the transmit switch inside the client does the same (code: client.py, _motion).
- **Never blocked:** /c/stop and /tts, in both designs.

### 3. flight.h

#### 3.1 "Bad naming, Why is it called Flight? ... Couldn't you atleast talk to me before using this stupid name?"
- **Where it came from:** the file control/flight.py, and your words "the flight controller on the software side" (R2 2.).
- **Fault:** a bare "Flight" says nothing. I should have proposed the name first.
- **Change:** D1.

#### 3.2 "What is it called FlightFly? ... SENDING A JSON BUFFER OF COMMANDS! IT SHOULD EXPLAIN THAT AT THE MINIMUM!"
- **Agreed.** The new name: `...SendMissionJson`.

#### 3.3 "FlightHalt is also fucking bad naming"
- **Agreed.** The new name: `...EmergencyStop`. The two modes become a note.

#### 3.4 "FlightSetManual - WHAT DOES MANUAL MEAN????"
- **Meaning:** the pilot's RC has the sticks; our missions are refused.
- **Two functions:** `...HandSticksToPilot` (flag on, then POST /c/stop) and `...AllowMissions` (flag off).
- **The read:** `...PilotHasSticks`.

#### 3.5 "[API Wide Command] - Do A style check for intent-based naming for the whole API."
- **Ruling NAM1.** The rename table is section 3.1.

#### 3.6 "Why do we own SessionLog? Do we own a handle to it? How do we actually use SessionLog In practice here?"
- **Today:** the controller writes the mission into the current turn's record before it sends it (code: control/flight.py, _record). The handle may be None in the benches.
- **rev4:** the recognizer fills decision.missionJson into the Turn before Act calls the controller (log.h, the usage lines).
- **So:** the turn already holds the mission. The controller needs no log. It returns the HTTP status; the app writes it into the turn.
- **Change:** D2.

### 4. frames.h

#### 4.1 "the memory for the frames is allocated elsewhere. Where? ... What is the source of the frame?"
- **Where:** ONE shared-memory block under /dev/shm (Python: multiprocessing.shared_memory).
- **Size:** a small header per slot, plus 32 x 1280 x 720 x 3 bytes = 84.4 MiB.
- **bgr:** points into that block at slot i times the frame size. Nothing is scattered.
- **The source:** the video source. A webcam read lands in the slot's bytes. A ROS image is copied once into the slot.
- **Measured** (bench/sam3-assessment, 2026-09-28): shared memory 0.1 ms round trip; a pipe 3.1 ms.

#### 4.2 "Who is actually responsible for initialization ... destruction? Between who is the memory shared?"
| who | does |
|---|---|
| the App | creates it at start, before the video source and SAM3 start (shm_open, size, mmap, zeroed) |
| the App | unlinks it at AppStop, after every process has stopped |
| the SAM3 process | opens it by name after its model loads |
| the app process | the writer: the video source; the readers: the screen, the log |
| the SAM3 process | a reader |
| Gemma | does not read it; a describe sends a JPEG over HTTP, as today |

#### 4.3 "How do the processes/services in question interface with the ringbuffer? ... Pin/unpin is not clear enough."
| party | steps |
|---|---|
| the video source (the only writer) | BeginWrite gives the oldest slot with zero pins. Fill the pixels, the number, the time. EndWrite makes it the newest. |
| the writer, every slot pinned | the frame is dropped and counted. The writer never blocks. |
| the screen | read the newest number. Pin that slot for one draw. Draw. Unpin. |
| a vision job | read the newest number N. Send (N, phrase, priority) to the SAM3 process over its socket. |
| the SAM3 process | Pin(N). The slot no longer holds N: answer "frame gone". Else detect on a view of the slot's bytes, no copy. Unpin. Answer (N, boxes, masks). |
| the log | Pin(N) while it writes the JPEG and the boxes. Unpin. |
- **A pin:** an atomic counter per slot. The writer skips a slot with pins above zero.

#### 4.4 "Who is to say that 32 frames is enough? ... That captures only a second of data at most!"
- **The rate:** the webcam gives 30 fps at 720p (code: video/video.py; measured 2026-09-08). 32 slots = 1.07 s.
- **A detect:** 410 ms alone; 630 ms with Gemma busy; up to 1.9 s for three concepts (bench/sam3-assessment).
- **The point:** the ring does not hold every frame of those 2 s. It holds the frames IN USE, plus free slots.
- **In use = pinned.** The writer skips pinned slots. A pinned frame lives as long as its reader needs it.
- **Pinned at once:** at most 8 jobs, plus the screen, plus the log: about 10. That leaves 22 free slots.
- **Saving to disk:** the job keeps its frame pinned through the detect AND the save. One JPEG write: milliseconds (unverified; the builder measures it).
- **Not a recorder:** only frames with a pass are saved, as today. Recording every frame is a separate feature.

#### 4.5 "Besides these, I have no problem with the implementation"
- Noted. The ring stays. The four answers go into the header (2.4).

### 5. gemma.h

#### 5.1 "Do you actually know how to start the gemma llama-server? ... That information that you find, is the exact information needed here."
- **Command line** (code: gemma/server.py, argv()):

| flag | value | meaning |
|---|---|---|
| -m | /root/models/vlm/Gemma-4-E4B/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf | the model |
| --mmproj | /root/models/vlm/Gemma-4-E4B/mmproj-BF16.gguf | the vision projector |
| -dev | Vulkan0 | the GPU through Vulkan |
| -ngl | 99 | every layer on the GPU |
| -c | 4096 | the context |
| -np | 1 | one slot: one request at a time |
| --temp | 0.0 | deterministic |
| --host, --port | 127.0.0.1, 18090 | local only |
| --threads | 1 | one CPU thread |
| --jinja --chat-template-kwargs | {"enable_thinking":false} | thinking off, part 1 |
| --reasoning-budget | 0 | thinking off, part 2 |
| env | LD_LIBRARY_PATH: build/release/shared/dji/bin first | our libraries |

- **Ready:** GET /health answers 200 (503 while loading). THEN one warm-up plan request. Only then the row turns UP (L1).
- **Timeout:** 240 s. **Log:** <session>/proc-gemma.log. **Required:** past 3 failed restarts the app dies.
- **Gotchas** (2026-09-08): no --image-min-tokens (breaks the CLIP load). No q4_0 KV cache with flash attention (empty output). Thinking off needs both flags.
- **Fault:** the header hid all of it behind GemmaStartServer().
- **Change:** 2.5.

#### 5.2 "I just don't understand how you plan to terminate the gemma process."
- **The supervisor's stop** (shutdown, or SysDie): SIGTERM to every child. SIGKILL after 10 s to any still alive (code: runtime/supervisor.py, stop_all).
- **The row:** DOWN.
- **So:** the Gemma handle has no close. The header will say it.

### 6. keys.h
- "Good." Noted.

### 7. log.h

#### 7.1 "what is the point of TurnInput@seq?"
- **It is:** the turn's number in this session: 0, 1, 2, ...
- **It names:** the clip (utt_0007.wav) and the perception folder (0007-highlight-chair).
- **It links:** a job points at its turn by it (7.5).

#### 7.2 "What is TurnInput@epoch?"
- **It is:** the wall-clock time the turn began. Seconds since 1970, 3 decimals (code: log/session.py).
- **For:** aligning a turn with perf.jsonl and with the clip's file time.
- **Change:** rename to `startedAtUnixS`.

#### 7.3 "Turn Struct looks good"
- Noted.

#### 7.4 "How do you plan to replay a whole session when you don't store data about images, including bboxes and the full noun/word-list used with SAM3?"
- **You are right.**
- **Saved today, per pass:** the raw frame (jpg); the boxes with conf and label; the forward ms (code: log/session.py, save_pass).
- **Saved today, per request:** kind, target, query, verdict, the pass count.
- **Missing today:** the masks. The concept string, except as each box's label. Which step a pass was (gate, head, related, refresh).
- **Missing in rev4's VisionJob:** the phrase sent to SAM3; each pass's frame number and time; its boxes and masks; its step; the split target; the gate verdict and reason.
- **Change:** 2.7, D7.

#### 7.5 "How do you plan to connect between a job and a turn?"
- **Both directions:** VisionJob.turnSeq = the asking turn's number. TurnResponse.visionJob = the job's id.
- **The call:** LogBeginJob takes the Turn that asks.
- **Change:** one line beside the two fields says exactly this.

### 8. perception.h

#### 8.1 "How about you split the FUCKING PAYLOAD DEPENDING ON WHICH TASK WAS REQUESTED???"
- **Ruling PER2.** Job becomes a tagged union.

| kind | payload |
|---|---|
| highlight | the latest detection; the give-up clock; why absent |
| count | the per-frame counts; the median |
| describe | the question; the answer |

#### 8.2 "What is the point of the functor of JobChanged?"
- **It is:** the ONE callback the app gives the vision system.
- **Called on:** every state change of a job, and every count or describe answer.
- **The app then:** one chat line, one spoken sentence, the log's end-of-job record.
- **Today:** five callbacks do this (code: app/turns.py, VisionSinks). One replaces five.
- **Why a callback:** a module may not call the app (2026-09-23).
- **Change:** named by intent, `OnJobResultFn`.

#### 8.3 "Vision is a bad name."
- **What it is:** the thing that runs vision JOBS on frames, with SAM3 and Gemma.
- **Your term:** "the perception system" (2026-09-27). The folder: perception2/.
- **Change:** D3.

#### 8.4 "What is the point of sam3Turn?"
- **Today:** the SAM3 priority lock (code: perception2/sam3_lock.py). One forward at a time. A user's request before a highlight's refresh.
- **rev4:** SAM3 in its own process. The ordering moves INTO that process: a priority queue.
- **Change:** the request carries a priority. sam3Turn leaves the struct.

#### 8.5 "There is no differentiation between Highlighting with bounding boxes and highlighting with both bboxes & image seg-masks."
- **Why:** today there is no cheaper "boxes only" pass. One forward produces boxes AND masks (code: sam3/model.py).
- **The t key:** toggles only the DRAWING (code: app/state.py, use_sam).
- **What a "no masks" request can save:** the mask resize in post-processing, and the transfer. How much: unverified.
- **Change:** a `wantMasks` flag on the request; the builder measures first (D8).

#### 8.6 "What is VerifyRelation? How does it work?"
- **It is:** today's perception2/verify.py. Runs ONCE per highlight, at the gate. Not per refresh.
- **Steps:**
  1. SplitTarget. "bag held by child with green shirt": head "bag"; relation TOUCH; related "child with green shirt"; colour "green". The relation words come from a table. A side word alone ("on the left") means no relation.
  2. Detect the head at floor 0.1. Keep score 0.5 and above, above the speck floor. None: absent, "no bag".
  3. Detect the related noun. Keep score 0.3 and above.
  4. A colour was said: keep only related boxes whose middle region has that hue (HSV table; white, black, grey by brightness and saturation). None: absent.
  5. Test every (head, related) pair with the geometry below.
  6. One pair holds: draw that head. None: "misplaced". A failed SAM3 call fails open.

| relation | test |
|---|---|
| TOUCH | overlap, or a gap under 0.25 of the smaller side |
| NEAR | overlap, or a gap under 1.0 of the smaller side |
| ON | horizontal overlap of 0.3; the head's bottom within 0.25 of the related's height from its top |
| UNDER, ABOVE | the same, with the roles swapped |
| IN | 80 % of the head inside the related |

- **Change:** the six steps are declared in the header, each a function (2.8).

#### 8.7 "API Seems like its getting there, still half baked"
- **Agreed on two counts:** the payload (8.1) and the SAM3 ordering (8.4).
- **After 8.1 to 8.6 the header declares:** the union; each job's steps; the six verify steps; the request's priority and mask flag; no lock.
- You judge the result.

### 9. perf.h

#### 9.1 "PerfEvent@stage shouldnot be a string, unless you plan on chaining subEvents"
- **No chaining is planned.** Today the stage is a text label in perf.jsonl; the report groups by it.
- **The set is known** (code: log/perf.py, the docstring).
- **Ruling PRF1:** an enum. The file keeps the name as text.

#### 9.2 "What is the diff between record and MarkNow? ... is End its counterpart?"
| call | meaning | used when |
|---|---|---|
| Record | one finished event; the caller measured the ms itself | start and end in one scope |
| Mark | remember a start time under a name | the end is on another thread or module |
| End | record the event as ms since the mark; forget the mark | the counterpart of Mark |
| take_since (hidden) | read the ms since the mark; forget it; no record | the ASR time feeds the e2e mark |
| move_mark (hidden) | rename a mark | "e2e" becomes "e2e_box" when a turn starts a highlight |

- **Example:** the push-to-talk release is marked on the key thread. The end is in the phone-app client (a command) or on the screen (the first box).
- **Fault:** the header left take_since and move_mark out.
- **Change:** five calls, named by intent (2.9).

#### 9.3 "Where does the writer thread plan to write to?"
- **To:** <session>/perf.jsonl. One JSON line per event. Appended every 5 s (R7).
- **On SysDie:** the buffer is written first.
- **Change:** the function says it, not only the struct note.

#### 9.4 "How do you plan to actually instrument the code that you're writing?"
- **With markers in our own code.** Exactly as today:

| stage | recorded in | the ms is |
|---|---|---|
| startup | app/main.py; log/perf.py | launch to the imports done; launch to each row UP |
| asr | app/turns.py | the push-to-talk release to the transcript |
| turn | app/turns.py | the recognizer's handle |
| gemma | gemma/client.py | one request; plus llama-server's own times |
| sam3 | perception2/vision.py | one forward; plus the lock wait |
| highlight_gate, count, describe | perception2/vision.py | one job's step |
| say | audio/speech_out.py | one sentence on one output |
| e2e | dji_app/client.py (the command); app/ui.py (the first box) | command to action |
| frame | app/ui.py | every frame: the gap; read, draw, show |
| gpu | log/perf.py | every 1 s: memory, load |

- **The processes:** measured from our side, plus what they report. llama-server reports its prompt and generation times. The SAM3 process will report its forward ms in the answer.
- **Change:** this table goes into perf.h.

### 10. recognizer.h

#### 10.1 "What does the recognizer look like in action? ... externally ... internally?"
- **From outside** (the app, once per transcript, on the transcript's thread):

```
Turn* t = LogBeginTurn(log, heard->text, heard->source);
RecognizerRoute(rec, t->input.heard, &t->decision);    /* decides; sends nothing */
RecognizerAct(rec, &t->decision, &t->response);        /* flies, or starts a vision job */
/* the app words the result: the chat, the voice */
LogCommitTurn(log, t);
```

- **The benchmark:** calls only Route, over 545 sentences, and scores the decision.
- **Inside Route**, in this order. The first step that answers ends the routing:

```
1. MatchTrigger(text)       the table: the sentence without filler EQUALS one command
                            -> EMERGENCY | MANUAL | AUTO | CLEAR
2. MatchFixedCommand(text)  a fixed pattern fully matches -> MISSION, no model
3. IsOnlyNegation(text)     "do not ..." with no order in it -> REJECT (negated)
4. RewriteHebrew(text)      number words to digits; known slips fixed -> he2
5. AskPlan(he2)             the ONE Gemma request, under the grammar
                            -> {"kind", "target_en", "mission"}; no answer -> GEMMA_FAILED
6. judge the plan           mission: NumbersMatch and not IsCopiedExample -> MISSION,
                                     else REJECT (numbers | copied example)
                            empty mission -> EMPTY
                            highlight | count: fix the target with the lexicon -> that kind
                            describe -> DESCRIBE
                            anything else -> REJECT (not a command)
```

- **Inside Act**, a switch on the kind:

```
EMERGENCY                    -> the controller's emergency stop
MANUAL / AUTO                -> the sticks switch
MISSION                      -> send the mission JSON
CLEAR                        -> stop every highlight
HIGHLIGHT / COUNT / DESCRIBE -> start that vision job (0 = refused: 8 alive)
REJECT / GEMMA_FAILED / EMPTY -> nothing is sent; the response says why
```

- **Code today:** recognizer/recognizer.py route() and act(). The steps: fast_path.py, bypass.py, guards.py, rewrites.py, lexicon.py.

#### 10.2 "I won't know for sure until I see what I requested of you."
- The three blocks go into the header, word for word (2.10).

### 11. runtime.h

#### 11.1 "There shouldn't be a watcher for each process. ... Why not use a single thread ... a condition variable ... a queue"
- **Today:** one thread per process, blocked in that process's wait (code: runtime/supervisor.py).
- **Not OS-internal.** The OS reports a child's exit by the SIGCHLD signal.
- **Ruling SUP1:** your design.
  1. The SIGCHLD handler puts an event on a queue and wakes the one supervisor thread.
  2. The thread polls EVERY process (no block). Two exits at once are both handled.
  3. For each exit it applies the policy: planned restart; budget left; budget spent.
  4. Readiness checks run on the same thread, round-robin every 0.5 s. One slow start delays no other.
- **Change:** 2.11.

#### 11.2 "the naming of your functional API is not good."
- **Agreed.** The rename table: section 3.1.

#### 11.3 "I don't understand how you would actually use this API"
- **The app at start** (code: app/main.py, start_processes):

```
sup   = SupervisorCreate();
gemma = SupervisorLaunchAndWatch(sup, GemmaServerProcess(logDir, port, thinking, warmUp));
keys  = SupervisorLaunchAndWatch(sup, KeyboardHookProcess(logDir));
asr   = SupervisorLaunchAndWatch(sup, MicAsrServerProcess(logDir));          /* the mic is a source */
mock  = SupervisorLaunchAndWatch(sup, DjiMockProcess(logDir));               /* CONTROL=mock */
gst   = SupervisorLaunchAndWatch(sup, DroneVideoReceiverProcess(logDir, ip)); /* VIDEO=dji */
sam3  = SupervisorLaunchAndWatch(sup, Sam3ServerProcess(logDir, SAM3_NF4));
/* the app does not wait: every row starts STARTING and turns UP by itself */
SupervisorRestartOnPurpose(gst, "video stalled 6 s");   /* the video stall guard */
SupervisorWaitUntilReady(gemma, 240);                   /* the scripted run, the benches */
SupervisorStopEveryProcess(sup);                        /* at the end, and on die */
```

#### 11.4 "Why is RosSubscribe/close here? ROS2 literally offers a this->create_subscription ... is this not the same in Python?"
- **The same.** rclpy has node.create_subscription(type, topic, callback, qos).
- **The difference:** who spins. Your C++ nodes spin on the main thread. Our main thread is the display loop (OpenCV).
- **Today:** each topic gets its own node, executor and thread (code: runtime/ros.py). Three topics: the keys, the transcripts, the drone images.
- **Why not one executor:** a transcript callback runs the whole turn. A Gemma plan takes 0.5 to 1.5 s. F4 and the video frames would wait behind it.
- **The wrapper:** those four lines (node, subscription, executor, thread) in ONE place, used by three modules.
- **Change:** keep it; name it `RosListenOnOwnThread`.

### 12. sam3.h

#### 12.1 "Mask@Bits - what?"
- **Today:** a numpy bool array, height x width, one BYTE per pixel (code: sam3/model.py).
- **Fault:** "bits" was the wrong word for bytes.
- **Across the process boundary:** packed, one BIT per pixel. 112.5 KiB per 720p mask instead of 900 KiB.
- **Change:** `packedBits` plus the row stride; the reader unpacks (the screen, for the tint).

#### 12.2 "Why is there a Sam3Process function, but on the other hand a Connect function?"
- **Two things,** as for Gemma and the mock.
- **The process description:** what the supervisor launches. argv: the server module, the weights, the ring name, the port. Ready: it answers "ready" after the load and the warm-up. Required. Log proc-sam3.log.
- **The connect call:** the app's client to that running process. It opens the request socket and holds the ring.
- **Why two:** the supervisor owns processes; the module owns its client.
- **Change:** `Sam3ServerProcess`, `Sam3ConnectToServer`.

#### 12.3 "Does it actually reflect our usage of the SAM3 api? or is the SAM3 API offered by transformers more explicit ...? What do you think?"
- **Today's detect, five steps** (code: sam3/model.py):

| step | transformers call | result |
|---|---|---|
| 1 | processor(images); model.get_vision_features | the image encoded ONCE per frame (S1) |
| 2, per concept | processor(text); model(vision_embeds, input_ids, attention_mask) | the text encoder, the detector, the mask decoder |
| 3 | processor.post_process_instance_segmentation(threshold, mask 0.5, frame size) | boxes, masks at frame size, scores |
| 4 | ours | the union over the concepts, sorted by score |
| 5 | ours | drop nested boxes of the same label (IoU over 0.5, or 70 % inside); cut to topk |

- **My opinion:** explicit. The header exists for you to see where a request's time goes (HDR3). The fan-out and the one encoding are exactly that.
- **Change:** the five steps are the server's functions; Sam3Detect runs them (2.12).

#### 12.4 "Other than that, looks solid."
- Noted.

### 13. scripted_run.h

#### 13.1 "Explain the usage in pseudo-code."
```
main(scriptPath):
    if CONTROL is not mock: die                        /* SAFETY: the sentences fly */
    steps = parse(scriptPath or DEFAULT_SCRIPT)        /* "say <sentence>" | "wait <s>" | "# ..." */
    until GET 127.0.0.1:18090/health is 200: sleep 1 s /* Gemma is up */
    sleep 20 s                                         /* SAM3 and the rest finish loading */
    RosInit; node = create_node("integration_feed")
    pub = node.create_publisher(String, ASR_TOPIC)     /* the ASR server's own topic */
    sleep 2 s                                          /* ROS2 discovery */
    for each step:
        wait -> sleep(s)
        say  -> pub.publish(String(sentence))
    destroy the node; RosShutdown
```
- **In the app:** each sentence arrives exactly as from the ASR server. No F5 release. The e2e timing starts at the transcript (code: app/turns.py).

#### 13.2 "I don't understand the point with ScriptMain."
- **It is:** the program's main(), the function above.
- **Why in the header:** rev4 declares everything (HDR3).
- **Fault:** the name says nothing.
- **Change:** `ScriptedRunMain`, with the pseudo-code above it.

#### 13.3 "Is this an actual pyhon file or a shell script???"
- **A Python file:** test/scripted_e2e_run.py.
- **Started by:** run.sh, in its own tmux window, when SCRIPT=<file> or SCRIPT=default (run.sh lines 222 to 226). Also test/test_app.py imports its publish function.

### 14. status.h
- "Looks good." Noted.

### 15. util.h
- "no comments here." Noted.

### 16. video.h

#### 16.1 "What is the current connection between the camera source and the gstreamer C++ ROS2 Node?"
| VIDEO | path |
|---|---|
| dji | the phone app streams H.264 over TCP on its video port |
| dji | our native node `llm_to_action_gstreamer_rx --dji <phone ip>` (source/gstreamer_udp_cam_rx/rx_node.cpp) |
| dji | its pipeline: tcpclientsrc -> h264parse -> avdec_h264 -> appsink (one buffer, drop the rest) |
| dji | it polls the appsink at 100 Hz on its ROS timer; publishes a bgr8 Image on camera/stream |
| dji | in the app: RosStream subscribes (one node, one spin thread); keeps the latest frame |
| webcam | cv2.VideoCapture on the camera index; 1280x720 MJPG. No gstreamer, no ROS. |
| a file path | cv2.VideoCapture on the file |
- **So:** the gstreamer node exists ONLY for the drone.
- **Fault:** the header's drawing lacked the transport and the pipeline.

#### 16.2 "Is frameRing owned here? Who has ownership of this framebuffer?"
- **Not owned here.** The App creates and unlinks the ring (4.2).
- **Video:** the only WRITER. A borrowed pointer.
- **Change:** the field says "borrowed; the App owns it".

#### 16.3 "Video is a bad name."
- **What it is:** the one source of frames into the ring.
- **Change:** D4.

#### 16.4 "Who calls GstreamerProcess?"
- **The App,** at start, when VIDEO=dji (code: app/main.py, start_processes).
- **The video source gets:** only the restart callback.
- **Change:** `DroneVideoReceiverProcess`.

### 17. app.h

#### 17.1 "Why not pull the Chat out of the Screen Struct to a different struct?"
- **Ruling CHAT1.** A Chat struct: the lines, the count, the scroll, the lock. The App owns it. The Screen borrows it.
- **Today:** S.chat in app/state.py; chat() in app/turns.py; render_chat in app/chat_pane.py.

#### 17.2 "ScreenAddChat? What is the intent here? what does it actually do?"
- **It appends** one line (role, text, style) to the chat.
- **Callers:** the turn thread (the user's sentence, the decision, the answer); the vision callback (a job's result).
- **Change:** `ChatAppendLine`.

#### 17.3 "Also ScreenRun()? the hell?"
- **It is:** the display loop. Until quit:
  1. Read the newest frame number from the ring; pin; copy; unpin.
  2. Draw every live job's boxes and masks.
  3. Compose the status pane, the chat pane, the jobs pane.
  4. Show. Wait one key. Handle a window key.
  5. Record the frame event.
- **Change:** `ScreenDrawUntilQuit`, with the loop written in the header.

#### 17.4 "Where is the display Loop actually running?"
- **On the MAIN thread.** OpenCV's window must run there.
- **Every other part:** its own threads. The three ROS spin threads; the vision jobs; the speech worker; the supervisor thread; the phone bridge's two threads.
- **Change:** the header says it.

#### 17.5 "Where does all of the initialization happen?"
- **In AppStart** (today: app/main.py main() and Services.__init__). The order:

| # | built | note |
|---|---|---|
| 1 | the crash hooks | an uncaught error anywhere dies |
| 2 | the session log | dies if the folder is not writable |
| 3 | perf | |
| 4 | the supervisor | |
| 5 | the Gemma client | before the server: the server is warmed through it |
| 6 | the processes | the Gemma server; the keyboard hook; the ASR server (mic); the mock (CONTROL=mock); the video receiver (VIDEO=dji) |
| 7 | the phone-app client | with its probe |
| 8 | the SAM3 loader | its own thread; the warm-up |
| 9 | the modules | speech out; the video source; the controller; the vision system; the recognizer; the turn handler; speech in; the status board; the screen; the keys |
| 10 | the display loop | the main thread, until quit |
| 11 | the shutdown | the modules, then the services, in reverse |
- **Change:** this table above AppStart (2.17).

#### 17.6 "Alright Looks good all things considered."
- Noted.

## 2. The plan per file (each item with its source)

### 2.1 audio.h, split into audio_in.h and audio_out.h (AUD2)
- `MicAsrServerProcess`: the full launch of 1.1 in the header (R3 1.1; HDR3 "Don't hide anything").
- `PhoneTranscriptBridge`: binds 0.0.0.0:8080; the phone holds the laptop's IP; drops the TCP duplicate; publishes on the transcript topic (R3 1.2).
- One worker thread per voice, each with its own pending sentence (R3 1.4; D5). "Newest wins" stays, per voice (2026-09-23).
- No Perf in speech out; the worker records the SAY stage itself (R2 1.; PRF1).

### 2.2 dji_app.h
- Perf leaves the client; the controller ends the command timing (R3 2.1; D6).
- `DjiMockProcess`: the full description of 2.2 in the header (R3 2.2).
- The manual-mode note: not called; 409 at once; nothing queued (R3 2.4).

### 2.3 flight.h, the controller (its name: D1)
- The functions by intent: SendMissionJson, EmergencyStop, HandSticksToPilot, AllowMissions, PilotHasSticks (R3 3.2 to 3.4; NAM1).
- No SessionLog in the struct (R3 3.6; the log.h usage lines; D2).
- The command e2e end moves here (D6).
- Keep: the atomic flag; no lock; the flag first, then /c/stop (R2 2.: "Yes", "Yes").
- No generic drone layer now: "No new DroneLink" (2026-09-23; D11).

### 2.4 frames.h
- The answers 4.1 to 4.4 go into the header text (R3 4.1 to 4.4; the measured 0.1 ms).
- Add `droppedFrames` (atomic) and `FrameRingUnlink` (R3 4.2, 4.4).
- The interface stays (R3 4.5).

### 2.5 gemma.h
- `GemmaServerProcess(logDir, port, thinking, warmUpFn)`: the ProcessSpec with the table of 5.1 (R3 5.1; L1).
- `GemmaConnect(port)`: the one client handle. A benchmark connects to its own server (R2 4.; the same shape as SAM3 and the mock, R3 12.2).
- The termination note (R3 5.2).

### 2.6 keys.h
- The rename only: `KeyboardHookProcess` (NAM1).

### 2.7 log.h
- `epoch` becomes `startedAtUnixS`; the `seq` note says what it names (R3 7.1, 7.2).
- `VisionJobRecord` (no clash with the live Job): the phrase sent to SAM3; the split target; the gate verdict and reason; a list of passes (R3 7.4).
- A pass: the step (GATE, VERIFY_HEAD, VERIFY_RELATED, REFRESH, COUNT_FRAME, DESCRIBE); the frame number and time; the phrase sent; the boxes; the mask files; ms.
- Masks as one PNG per box: D7.
- One line for the job-turn link beside the two fields (R3 7.5).
- `LogSaveSam3Pass` takes the step and the masks (NAM1).

### 2.8 perception.h (its name: D3)
- `Job` as the tagged union of 8.1 (PER2).
- `OnJobResultFn`, with when it is called (R3 8.2).
- No `sam3Turn`, no `jobsLock`. The SAM3 request carries `priority` and `wantMasks` (R3 8.4, 8.5; D8).
- The six verify steps declared, each a function (R3 8.6).
- `...StopHighlight(task)` and `...StopEveryHighlight()` replace VisionClear (T3C, T3C (2)).
- The jobs pane reads `...CopyJobs` (T3C (2)).

### 2.9 perf.h
- `PerfStage` enum: STARTUP, ASR, TURN, GEMMA, SAM3, HIGHLIGHT_GATE, COUNT, DESCRIBE, SAY, E2E, FRAME, GPU (PRF1).
- Five calls: PerfRecordDuration, PerfMarkStart, PerfEndSinceMark, PerfReadSinceMark, PerfRenameMark (R3 9.2).
- The instrumentation table of 9.4 in the header (R3 9.4).
- `PerfOpen` names the file and the 5 s period (R3 9.3; R7; C.1).

### 2.10 recognizer.h
- The three blocks of 10.1 above Route and Act (R3 10.1).
- The step functions stay (T1 (2); AUTO1; STOP1 (3)).

### 2.11 runtime.h
- One supervisor thread; the SIGCHLD handler feeds a queue; the loop of 11.1 written out with today's policy (SUP1; U6).
- `Process` loses `watcher`. `Supervisor` gains `thread`, `events`, `wake`.
- The renames of 3.1 (NAM1). The usage block of 11.3 (R3 11.3).
- `RosListenOnOwnThread`, with the note of 11.4. `RosInit` and `RosShutdown` stay explicit (R2 9.).

### 2.12 sam3.h
- `Mask.packedBits` with the stride (R3 12.1).
- `Sam3ServerProcess`, `Sam3ConnectToServer` (R3 12.2).
- The five steps of 12.3 as the server's functions; `Sam3Detect` runs them (R3 12.3; S1).
- The request: frame number, phrase, floor, priority, wantMasks.
- The answer: boxes; packed masks for the kept boxes only, at most 16; in a shared answer region (D9).
- The priority queue inside the server (R3 8.4).

### 2.13 scripted_run.h
- The pseudo-code of 13.1 above `ScriptedRunMain` (R3 13.1, 13.2).
- The top note: a Python file; who starts it (R3 13.3).

### 2.14 status.h, 2.15 util.h
- No change (R3 14, 15).

### 2.16 video.h, the frame source (its name: D4)
- The drawing gets the transport, the pipeline and the topic (R3 16.1).
- `ring`: borrowed; the App owns it; this is the only writer (R3 16.2).
- `DroneVideoReceiverProcess`, launched by the App when VIDEO=dji (R3 16.4).
- The code has five source kinds; rev4 has three. The two unused ones: D10.

### 2.17 app.h
- A `Chat` struct; `ChatAppendLine` (CHAT1; R3 17.2).
- `ScreenDrawUntilQuit`; the loop written out; "runs on the main thread" (R3 17.3, 17.4).
- The start-up table of 17.5 above `AppStart`; `AppStop` in reverse (R3 17.5; D15; 2026-09-23).

## 3. General points, for every file

### 3.1 The rename table (NAM1)
| old | new |
|---|---|
| FlightController and Flight* | D1 |
| FlightFly / FlightHalt | SendMissionJson / EmergencyStop |
| FlightSetManual(true) / (false) | HandSticksToPilot / AllowMissions |
| FlightIsManual | PilotHasSticks |
| Vision and Vision* | D3 |
| VisionClear(0) / (task) | StopEveryHighlight / StopHighlight(task) |
| VisionJobs / JobChangedFn | CopyJobs / OnJobResultFn |
| Video and Video* | D4 |
| GstreamerProcess | DroneVideoReceiverProcess |
| AsrServerProcess / PhoneBridge | MicAsrServerProcess / PhoneTranscriptBridge |
| KeysProcess | KeyboardHookProcess |
| GemmaStartServer / GemmaAttach | GemmaServerProcess + GemmaConnect |
| Sam3Process / Sam3Connect | Sam3ServerProcess / Sam3ConnectToServer |
| Mask.bits | Mask.packedBits |
| VisionJob / TurnInput.epoch | VisionJobRecord / startedAtUnixS |
| LogSavePass | LogSaveSam3Pass |
| PerfRecord / PerfMarkNow / PerfEnd | PerfRecordDuration / PerfMarkStart / PerfEndSinceMark |
| take_since / move_mark (hidden) | PerfReadSinceMark / PerfRenameMark |
| SupCreate / SupStart / SupStopAll | SupervisorCreate / SupervisorLaunchAndWatch / SupervisorStopEveryProcess |
| ProcessWaitUp / ProcessRestart | SupervisorWaitUntilReady / SupervisorRestartOnPurpose |
| SysOnDie / SysDie / SysInstallCrashHooks | RunBeforeTheAppDies / DieWithReason / TurnUncaughtErrorsIntoDie |
| RosSubscribe / RosSubscriptionClose | RosListenOnOwnThread / RosStopListening |
| ScreenRun / ScreenAddChat | ScreenDrawUntilQuit / ChatAppendLine |
| ScriptMain | ScriptedRunMain |

### 3.2 The rules for every header
1. Every process description declares its whole launch: argv, env, the ready check and timeout, required or not, the log, who launches it, what it does (R3 1.1, 2.2, 5.1, 12.2, 16.4).
2. Every pointer member says who owns the thing: owned, or borrowed from X (R3 3.6, 4.2, 16.2).
3. Every function says on which thread it runs: main, the caller's, or its own (R3 1.4, 11.1, 17.4).
4. One payload per kind, as a tagged union (PER2; Voice, the source, Job, the stage).
5. Every module header has an in-action block: the real call sequence as pseudo-code (R3 10.1, 11.3, 13.1, 17.3, 17.5).
6. Names say the intent. A note explains the why, never the what (NAM1; guidelines.md).
7. No free text where the set is known: the stage, the source, the kind, the step (PRF1).
8. Every hidden path found in this round is declared: take_since and move_mark; the client's e2e end; the verify steps; the five SAM3 steps; the two unused video kinds.
9. The "[rev4]" bracket notes go. The revision and the date stay only in the top comment.
10. For the build (API1): a check tool reads every header and every module. It fails on a member without its attribute, a function without its def, or the reverse.

## 4. The decision table (reply "D1 a, D2 a, ...")

| ID | question | options, the recommendation first |
|---|---|---|
| D1 | the controller's type name | a. DroneCommandGate: every command passes this gate; manual mode closes it. b. PhoneAppCommander. c. keep FlightController; rename only the functions. |
| D2 | the controller and the log | a. no log in the controller; the turn holds the mission; the app writes the status. b. keep the log pointer; record from the controller, as today. |
| D3 | the vision system's name | a. Perception (your word; the folder perception2/): PerceptionStartHighlight, StartCount, AskDescribe, StopHighlight, StopEveryHighlight, CopyJobs. b. VisionJobRunner. |
| D4 | the video type name | a. FrameSource: Open, Close, NewestFrame, Ended; the kinds DroneStreamSource, WebcamSource, VideoFileSource. b. CameraFeed. |
| D5 | speech out, the 3 s stall | a. one worker per voice, each with its own pending sentence. b. one worker in series; accept the stall. |
| D6 | where the command e2e timing ends | a. in the controller; the client holds no Perf. b. in the client, as today; the member shown. |
| D7 | masks in the session record | a. one PNG per box per pass; the builder measures the cost. b. boxes only, as today. |
| D8 | the "boxes only" request flag | a. add wantMasks; the builder measures the saving; under 10 % of a pass, the flag goes. b. no flag. |
| D9 | masks across the process boundary | a. packed bits; kept boxes only; at most 16; a shared answer region of 4 slots (7.2 MiB). b. over the socket; 1.8 MiB per answer. |
| D10 | the two unused video kinds (a gstreamer pipeline string; a stream URL) | a. drop them: webcam, dji, a file for tests (YAGNI). b. keep them. |
| D11 | a generic drone layer (FL1) | a. not now: "No new DroneLink" (2026-09-23). b. design it now. |
