# Round 4: every point, with its full picture (2026-10-04)

Input: REVIEW-4-owner.md (your words, HDR6). Your instruction at the end of the session:
"You do not perform a design-review/architecture-design of a system without a full complete
picture of it. Re-review my notes, Get out of planning mode, and address every single one of my
points. After that, we will get into plan mode, and properly Design everything as we should, one
system at a time."

How this file is built. Section 0 is the whole picture: the processes, the threads, the data flow
of today's app. Then one section per header you reviewed. Each section opens with the system and
how it works TODAY, with the files. Then each of your points, in one place: your words, the answer,
the proposal as code, the open choice if one exists. Nothing points forward to another section;
code repeats where a point needs it. Nothing in the headers or the code is changed by this file.

Conventions in every snippet (your snippets and docs/guidelines.md): `m_` member, `mh_` handle
member, `mb_` bool member, `k` constant, `_Atomic T` for a value two threads touch, a handle is a
plain struct returned by value, `XxxBegin / XxxEnd` for a process or a thread owner, `XxxOpen /
XxxClose` for an opaque logger, `XxxCreate / XxxClose` for a plain object (your dispatcher). A
comment states a launch, a protocol or a unit; never an order of operations.

---

## 0. The whole picture, today (projects/integration_harden2)

### 0.1 The processes
| process | started by | talks over | role |
|---|---|---|---|
| the app (python3 -m app.main) | run.sh | | the ground station: the screen, the turn handler, every module |
| llama-server (Gemma 4 E4B) | the supervisor | HTTP 127.0.0.1:18090 | the planner of the recognizer; the describe answers |
| llm_to_action_asr_server (whisper, C++) | the supervisor | ROS2 /asr_server/transcribe | the laptop mic: F5 to record; publishes the text |
| llm_to_action_keyboard_hook (C++) | the supervisor | ROS2 /keyboard/in/raw | every key press and release, in any window |
| mock_apiserver.py (CONTROL=mock) | the supervisor | HTTP 127.0.0.1:8079 | stands in for the phone app |
| the phone app (CONTROL=real) | the human | HTTP <phone ip>:8080 | the drone commands, /tts; HUMAN-ONLY |
| llm_to_action_gstreamer_rx (VIDEO=dji, C++) | the supervisor | ROS2 camera/stream | decodes the phone's H.264; publishes frames |
| SAM3 | TODAY inside the app process (a loader thread) | | boxes and masks. rev4: its own process (your ruling, R2) |

### 0.2 The threads of the app, today
| thread | module | does |
|---|---|---|
| main | app/ui.py | the screen loop: read a frame, draw the boxes, compose the panes, show, one key |
| ROS spin: keys | runtime/ros.py, keys/keys.py | F1 quit, F2 clear, F4 manual toggle, F5 release |
| ROS spin: transcripts | audio/asr_ros.py | the mic's text -> the turn handler (the WHOLE turn runs on this thread) |
| ROS spin: images | video/ros_stream.py | the drone frames (VIDEO=dji) |
| phone listener + deliverer | audio/asr_phone.py | the phone's text -> the turn handler (the whole turn runs on the deliverer) |
| speech-out worker | audio/speech_out.py | speaks the pending sentence on each output in series |
| supervise-<name>, one per process (6) | runtime/supervisor.py | waits for its process to exit; restarts it |
| dji-app-probe | dji_app/client.py | while the phone app does not answer: GET /status/ every 2 s |
| vision-backend-load | sam3/loader.py | loads SAM3; one warm-up pass; then idle |
| vision-dispatcher + one thread per job (at most 8) | perception2/dispatcher.py, vision.py | count, highlight, describe |
| perf-writer, perf-gpu, perf-startup | log/perf.py | the timings to disk every 5 s; the GPU sample; the start-up rows |

### 0.3 One turn, today
```
mic  -> ASR node -> ROS topic ---+
                                 +--> Turns.__call__(text, source)           [the transcript's thread]
phone -> TCP/POST -> PhoneAsr ---+        session.begin(text)                 log/session.py
                                          recognizer.route(text) -> Decision   recognizer/recognizer.py
                                          recognizer.act(decision)
                                            emergency/manual/auto -> control -> dji client -> phone or mock
                                            mission                -> control.fly -> dji client
                                            clear                  -> vision.clear()
                                            highlight/count/describe -> vision.<kind>() -> dispatcher -> a job thread
                                          say(routed.say) -> chat line + speech-out worker
                                          session.commit() -> trace.jsonl
a job thread: SAM3 (one forward at a time, a priority lock) -> Sinks callbacks (app/turns.py)
              -> S.hl_dets / S.hl_masks (app/state.py, one lock) -> the screen draws them
```

### 0.4 The rev4 drafts you reviewed
docs/api-harden2/rev4/*.h, written 2026-10-02 from this code, laid out 2026-10-03. Your rounds:
REVIEW-1 (rev3), REVIEW-2, REVIEW-3, REVIEW-4 (this one). Nothing is implemented.

---

## 1. audio.h -- the system: speech in and speech out

**The job of the system.** Speech in: turn what the operator says into text and hand it to the
turn handler. Speech out: speak the app's answers.

**Today.**
- Two inputs. `audio/asr_ros.py`: subscribes to the ASR node's topic; `process()` describes
  the ASR node for the supervisor. `audio/asr_phone.py`: an asyncio socket server on
  0.0.0.0:8080 that accepts the phone's POST and its TCP line, drops the duplicate, and hands
  the text to a delivery thread. `audio/speech_in.py`: a name-to-class table
  `{"ros": RosAsr, "phone": PhoneAsr}` picked by config.ASR_SOURCES.
- Two outputs. `audio/tts_phone.py`: POST /tts through the phone-app client.
  `audio/tts_laptop.py`: phonikud -> piper -> sounddevice, offline. `audio/speech_out.py`: one
  worker thread; one pending sentence, the newest wins; speaks it on each output in series.

### 1.1 "What is the point of AsrServerProcess? what is it launching? What does the process actually do?" + "WHICH CASE DO YOU THINK APPLIES TO OUR SYSTEM? BE HONEST WITH YOURSELF PLEASE"
- **The case:** B. The code is bad at this edge. The system is 8,476 lines, not ginormous.
  Why bad: the inputs hide behind a name-to-class table keyed by config strings; the ASR node's
  launch sits in asr_ros.py under a generic `process()`; nothing names two inputs and two
  outputs where a reader starts.
- **What it launches:** `llm_to_action_asr_server`, our C++ ASR node
  (projects/llm_to_action/source/asr/asr_node.hpp), with, from config:
  `--backend=whisper-whisper --model=<ivrit whisper-large-v3-turbo q5_k> --fa --language=he
  --threads=1 --gid=0 [--captureid=N] [--record --recordDir=<session>/asr_clips]`, env
  `PULSE_SERVER=unix:/tmp/pulse-socket`.
- **What the process does:** opens the laptop mic through PulseAudio at 16 kHz; subscribes to
  /keyboard/in/raw; F5 starts a recording, F5 again stops it and wakes a consumer thread; the
  consumer runs whisper; with --record it writes the clip first; it publishes the text on
  /asr_server/transcribe.
- **The proposal, audio_in.h.** The two inputs are named where a reader starts. Each has Begin
  and End. Both call the same handler. The ROS republish of the phone text (rev4's PhoneBridge)
  is dropped: nothing needs it.
```c
/* audio_in.h -- speech in. TWO inputs. Each one calls the app's transcript handler. */
typedef enum SpeechInputKind {
	SPEECH_INPUT_MIC_ASR,        /* the laptop mic -> our whisper ASR node (a process) -> ROS2 */
	SPEECH_INPUT_PHONE_SPEECH    /* the phone's own recognizer -> WiFi -> our TCP listener      */
} SpeechInputKind;

typedef struct Transcript {
	SpeechInputKind m_input;
	const char*     m_text;
} Transcript;

typedef void (*TranscriptFn)(void* app, const Transcript* t);

/* input 1. The node: llm_to_action_asr_server
 *   --backend=whisper-whisper --model=<ASR_MODEL_PATH> --fa --language=he --threads=1 --gid=0
 *   [--captureid=<ASR_CAPTUREID>] [--record --recordDir=<session>/asr_clips]
 *   env PULSE_SERVER=<PULSE_SERVER>
 *   ready: it publishes; stop: SIGINT (a ROS2 node); after 3 failed restarts: die
 * F5 starts a recording; F5 again stops it; whisper runs; the clip is written; the text is
 * published on /asr_server/transcribe. */
typedef struct MicAsrInputHandle {
	Process*         mh_asrNode;
	RosSubscription* mh_transcripts;
} MicAsrInputHandle;

MicAsrInputHandle MicAsrInputBegin(Supervisor* s, const char* logDir, TranscriptFn fn, void* app);
bool              MicAsrInputEnd(MicAsrInputHandle* h);

/* input 2. Binds 0.0.0.0:port. The phone app holds the laptop's IP. */
typedef struct PhoneSpeechInputHandle {
	uint16_t  m_port;
	OsThread* mh_listener;     /* reads the phone's lines                         */
	OsThread* mh_deliverer;    /* calls fn, so a slow turn never blocks the socket */
	Status*   mh_status;       /* the "phone speech" row                          */
} PhoneSpeechInputHandle;

PhoneSpeechInputHandle PhoneSpeechInputBegin(uint16_t port, TranscriptFn fn, void* app);
bool                   PhoneSpeechInputEnd(PhoneSpeechInputHandle* h);
```

### 1.2 "Which transmission is faster? why are we listening on both when we can listen on the faster one?"
- **Today:** the phone app sends every command twice: a POST to /input and one JSON line on a
  persistent TCP socket, both to port 8080 (its GroundStationSpeechResolver.kt and
  TCPClient.kt). Our listener sniffs the first line, serves both, and drops the second copy
  within 1.5 s.
- **Faster:** the TCP line. One persistent socket: no connection setup, no HTTP headers per
  command. Measured: no (unverified). The builder logs which copy arrives first over 20 commands.
- **Why both today:** the phone sends both; nobody chose. Both arrive on one port, so the
  listener must still accept the HTTP connection.
- **The proposal:** take the text from the TCP line only; answer the POST 200 and ignore its
  body; the dedup goes. The better end state is a phone app that sends TCP only; that change is
  outside this repo.
- **Open: Q2.** a. TCP only, as above (recommended). b. keep both with the dedup.

### 1.3 "split to audio_in.h and audio_out.h"
- Ruling AUD2. The split is the two snippets of 1.1 and 1.4. Done in the header pass.

### 1.4 "What happens if we need to streamline a sentence both from the phone AND the laptop? ... won't they stall each other?" + "Good, we should be pursuing that approach. Is it worth it to look into userspace threads, like fibers/coroutines/something-else-im-not-aware-of?"
- **Today:** one worker; the sentence goes to the phone (a POST that returns at once), then to
  the laptop (blocks until spoken). A phone that does not answer holds the POST up to 3 s; the
  laptop voice waits that long. A second sentence replaces the pending one and cuts what plays.
- **Fibers or coroutines:** not worth it. The laptop voice blocks inside C calls (piper's
  synthesis, the sound device's wait). A coroutine cannot yield inside those; it would need a
  thread anyway. Two OS threads cost nothing here. Python's coroutines stay where they are: the
  phone listener.
- **The proposal, audio_out.h.** One worker per voice; each voice holds its own pending
  sentence; the app says a sentence to every voice it opened. No SpeechOut object.
```c
/* audio_out.h -- speech out. TWO voices. The app says a sentence to each voice it opened. */
typedef enum VoiceKind {
	VOICE_PHONE_TTS,       /* POST /tts to the phone app; Android speaks                */
	VOICE_LAPTOP_PIPER     /* phonikud -> piper -> the laptop speaker, offline          */
} VoiceKind;

typedef struct VoiceHandle {
	VoiceKind     m_kind;
	DjiAppHandle* mh_phone;          /* VOICE_PHONE_TTS: borrowed from the app            */
	void*         mh_phonemizer;     /* VOICE_LAPTOP_PIPER: phonikud (third party)        */
	void*         mh_synthesizer;    /* piper (third party)                               */
	OsThread*     mh_speaker;        /* this voice's own worker                           */
	OsCondition*  mh_wake;
	const char*   m_pending;         /* one sentence; a newer one replaces it             */
	_Atomic bool  mb_running;
} VoiceHandle;

VoiceHandle VoiceBegin(VoiceKind kind, DjiAppHandle* phone);
bool        VoiceEnd(VoiceHandle* v);
void        VoiceSay(VoiceHandle* v, const char* text);   /* never blocks; cuts what plays */
```

---

## 2. dji_app.h -- the service: the ONE client of the phone app, or of its mock

**The job of the service.** Send the drone commands and /tts to the phone app over HTTP; keep the
"dji app" status row; stand in for the phone with a mock when CONTROL=mock.

**Today.** `dji_app/client.py`: DjiApp(host, port, allow_real, timeout, perf); refuses a
non-loopback host without allow_real (CLAUDE.md); POST /c/takeoff, /c/land, /c/fly, /c/stop,
/tts; GET /status/ as the probe every 2 s while the app does not answer; a transmit switch that
makes motion requests return 409; `_command()` ends the perf mark "e2e" on any reply.
`mock_process()` describes tools/dji_mock/mock_apiserver.py on 127.0.0.1:8079 for the supervisor.
`config/defaults.py dji_target()`: CONTROL=mock -> 127.0.0.1:8079, not real; CONTROL=real ->
PHONE_IP:8080, real.

### 2.1 "Well we want to measure the e2e timings. you advise on extracting perf out, but I don't know if this means that the resulting performance benchmarks on specific DJI-App functions will still be as accurate, since we're operating on their outer scope."
- **Two different measurements.** The duration of a DJI-app request (POST /c/fly: how long
  until the phone answered) is the client's own event; it stays inside the client, measured
  around the HTTP call, exact. The e2e timing (the operator's command to the action) is the
  turn's event; the turn belongs to the app, so the app records it: its end is one function
  return after the client's reply, microseconds later.
- **So the client keeps a perf logger**, for its own requests. The e2e end leaves the client.
- **The proposal:** below, in 2.4, as one header.

### 2.2 "No, the supervisor is required here. WHO THE FUCK LAUNCHES ALL SERVICES BESIDES THE SUPERVISOR??? How do you actually know to route the commands properly to the mock server and not the phone if both are alive?"
- **The supervisor launches every process**, the mock included. My words "not required" were
  the name of a restart-policy flag in the code: `ProcessSpec.required`. True: after 3 failed
  restarts the app dies (a laptop part). False: the row goes WAITING and the user fixes it (a
  phone-side part: the mock, the gstreamer receiver). The name is bad. It becomes:
```c
typedef enum BudgetSpentPolicy { BUDGET_SPENT_DIE, BUDGET_SPENT_WAIT_FOR_USER } BudgetSpentPolicy;
/* in ProcessSpec: */
BudgetSpentPolicy m_onBudgetSpent;
```
- **The routing:** CONTROL decides once, at AppStart, and both sides derive from it.
  CONTROL=mock: the supervisor launches the mock, and the client is built for 127.0.0.1:8079.
  CONTROL=real: no mock is launched, and the client is built for PHONE_IP:8080 with allowReal.
  A live phone is never addressed while CONTROL=mock, because the client never knows its
  address. In code, at AppStart:
```c
if (CONTROL == mock) a->m_mock = DjiMockProcessBegin(a->mh_supervisor, logDir);   /* 127.0.0.1:8079 */
a->m_dji = DjiAppBegin(DJI_HOST, DJI_PORT, DJI_REAL, 3.0f, a->mh_perf);            /* from the SAME CONTROL */
```

### 2.4 "Great!" + "I took a second look at this, but this suffers from the same naming issues that many other APIs had."
- **The whole header, renamed:**
```c
/* dji_app.h -- the ONE client of the DJI phone app, or of the mock that stands in for it. */
typedef struct DjiAppHandle {
	const char*   m_host;
	uint16_t      m_port;
	float         m_timeoutS;
	PerfLogger*   mh_perf;          /* borrowed: one record per request                     */
	OsThread*     mh_probe;         /* GET /status/ every 2 s while the app does not answer */
	_Atomic bool  mb_ending;
	Status*       mh_status;        /* the "dji app" row                                    */
} DjiAppHandle;

/* a non-loopback host without allowReal dies: a real phone is HUMAN-ONLY (CLAUDE.md) */
DjiAppHandle DjiAppBegin(const char* host, uint16_t port, bool allowReal, float timeoutS,
	PerfLogger* perf);
bool         DjiAppEnd(DjiAppHandle* d);

HttpStatus DjiAppSendTakeoff(DjiAppHandle* d);                              /* POST /c/takeoff */
HttpStatus DjiAppSendLand(DjiAppHandle* d);                                 /* POST /c/land    */
HttpStatus DjiAppSendCmdList(DjiAppHandle* d, const char* missionJson);     /* POST /c/fly     */
HttpStatus DjiAppSendStop(DjiAppHandle* d);                                 /* POST /c/stop    */
HttpStatus DjiAppSendTts(DjiAppHandle* d, const char* text);                /* POST /tts       */
extern const char* const kHaltMissionJson;   /* [{"type":"delay","seconds":0}]: pre-empts motion */

/* the mock: python3 tools/dji_mock/mock_apiserver.py 127.0.0.1 8079
 *   serves GET /status/*, POST /c/takeoff /c/land /c/fly /c/stop /tts, WS /c/ws/sticks;
 *   integrates a fake velocity at 20 Hz; writes every command to <logDir>/mock_commands.log
 *   ready: the port accepts; stop: SIGINT; after the budget: wait for the user */
typedef struct DjiMockHandle {
	Process* mh_mock;
	uint16_t m_port;
} DjiMockHandle;

DjiMockHandle DjiMockProcessBegin(Supervisor* s, const char* logDir);
bool          DjiMockProcessEnd(DjiMockHandle* m);
```
- **Manual mode** lives in the dispatcher (section 3): while it is on, the dispatcher does not
  call SendCmdList; the caller gets 409 at once. Nothing is queued. SendStop and SendTts are
  never blocked.

---

## 3. flight.h -- the system: the platform command dispatcher

**The job.** The only code that sends a flight command, and the only owner of manual mode.

**Today.** `control/flight.py` Control(dji, log): manual() turns the transmit switch off and
sends /c/stop; auto() turns it on; emergency_halt() sends a zero-delay mission in auto mode and
/c/stop in manual mode; fly(actions) records the mission into the current turn's log record, then
sends it; a lock around manual(); outcome_text() words every result.

### 3.1 "Bad naming ... Couldn't you atleast talk to me before using this stupid name?" + the names you gave
- Used as given. `m_` prefixes and `_Atomic` applied. The two implementation comments you
  struck are gone.

### 3.2 to 3.5 "See My previous bulleted response"
- The names below.

### 3.6 "Why do we own SessionLog? ... How do we actually use SessionLog In practice here?" -> "Good! Option A"
- **Today:** fly() writes the mission into the turn's record before sending (`log.set(mission=)`).
- **Option A, applied:** no log in the dispatcher. The recognizer's decision already holds the
  mission JSON inside the turn; the app records the turn after the dispatcher answered.
```c
/* platform_command_dispatcher.h */
typedef struct PlatformCommandDispatcher {
	DjiAppHandle* mh_dji;
	_Atomic bool  mb_manual;
} PlatformCommandDispatcher;

typedef PlatformCommandDispatcher PlatformCmdDispatcher;

PlatformCommandDispatcher* PlatformCommandDispatcherCreate(DjiAppHandle* dji);
void                       PlatformCommandDispatcherClose(PlatformCommandDispatcher* d);

HttpStatus PlatformCommandDispatcherSetManualControlMode(PlatformCommandDispatcher* d, bool manual);
bool       PlatformCommandDispatcherIsManualControlMode(const PlatformCommandDispatcher* d);
HttpStatus PlatformCommandDispatcherSendEmergencyStop(PlatformCommandDispatcher* d);
HttpStatus PlatformCommandDispatcherSendCmdList(PlatformCommandDispatcher* d, const char* missionJson);
```
- The wording of a result (today outcome_text) is the app's, where every answer is worded.

---

## 4. frames.h -- the frame buffer (new in rev4; SAM3 in its own process needs it)

**The job.** One place where every video frame lives, so the screen, the vision jobs, the
telemetry writer and the SAM3 process read the same frame by its number, with no copy per request.

**Today.** No such thing. `video/video.py` keeps `_latest` under a lock; `snapshot()` returns a
copy per caller; a vision job copies the frame it works on; SAM3 is in the app process.
Measured (bench/sam3-assessment, 2026-09-28): a frame through shared memory 0.1 ms round trip; a
pipe 3.1 ms; a detect 410 ms alone, 630 ms with Gemma busy, up to 1.9 s for three concepts.

### 4.1 "The Source: Is this A or B? I don't understand what you exactly meant here."
- **Both exist, one per source kind.** Webcam (A, direct): OpenCV's read takes a destination
  array; the decoder writes into the slot's bytes. Whether the V4L2 backend avoids its own copy
  is unverified; the builder measures it. Drone (B, one copy): the ROS image message arrives as
  bytes; they are copied once into the slot. The source of every frame is the frame source
  object (section 16), the only writer.

### 4.2 "How is the app the writer when Video is the Source of the frames?" + "Why would gemma not read it? ... IT NEEDS THE LATEST FRAME!" + "Where in the app is this actually handled??"
- **The writer** is the frame source object, which lives in the app PROCESS. The App STRUCT
  only creates and destroys the shared block. No double copy.
- **Gemma** is llama-server, a third-party process. It takes an image only inside its HTTP
  request, as a JPEG. It cannot map our shared block. So the describe job acquires the latest
  frame, encodes a JPEG from the slot, releases the slot, and sends the JPEG in the request. Gemma
  gets the latest frame that way, as today.
- **Where in the app:** FrameBufferCreate is the fifth step of AppStart, after the supervisor
  and before the frame source and the SAM3 server (both get the block's name).
  FrameBufferDestroy is the last step of AppStop, after every process ended. The readers: the
  screen loop (the latest frame), a vision job (the frame of its pass), the telemetry writer (the
  frame of a saved pass), the SAM3 process (the frame named in a request).

### 4.3 "WHICH FRAME? THE OLD ONE OR THE NEW ONE?" + "This is absolutely not clear enough" (the SAM3 side) + "THEN CALL IT AN ATOMIC FUCKING COUNTER"
- **No frame is dropped.** The writer overwrites the oldest slot that no reader holds. A held
  slot is in use (a detect in flight), not laying around. Held at once: at most 10 (8 jobs, the
  screen, the telemetry) against 32 slots. If no free slot exists, that is a bug: the writer dies
  with the reason.
- **The counter** is `_Atomic uint32_t m_readerCount`.
```c
/* frame_buffer.h -- ONE shared-memory block of frames (/dev/shm/<name>). The writer fills
 * slots in ring order and skips a slot a reader holds. Readers start from m_latest. */
enum { kFrameSlots = 32 };
typedef uint64_t FrameSeq;

typedef struct FrameSlot {
	FrameSeq         m_seq;
	PerfTimestamp    m_capturedAt;
	uint32_t         m_width;
	uint32_t         m_height;
	_Atomic uint32_t m_readerCount;
	uint8_t*         m_bgr;            /* width x height x 3, inside the shared block */
} FrameSlot;

typedef struct FrameBufferHandle {
	const char*      m_shmName;
	void*            mh_shm;           /* the block: slot headers + 32 x 1280 x 720 x 3 = 84.4 MiB */
	FrameSlot        m_slots[kFrameSlots];
	_Atomic FrameSeq m_latest;
	uint32_t         m_writeIndex;
} FrameBufferHandle;

/* the app process */
FrameBufferHandle FrameBufferCreate(const char* shmName, uint32_t width, uint32_t height);
void              FrameBufferDestroy(FrameBufferHandle* fb);     /* unlinks; after every other process ended */
/* the SAM3 process: opens the block the app created */
FrameBufferHandle FrameBufferOpenExisting(const char* shmName);
void              FrameBufferCloseExisting(FrameBufferHandle* fb);

/* the writer: the frame source */
FrameSlot* FrameBufferBeginWrite(FrameBufferHandle* fb);               /* the oldest slot with m_readerCount == 0 */
void       FrameBufferEndWrite(FrameBufferHandle* fb, FrameSlot* s);   /* s->m_seq becomes m_latest */
/* a reader */
const FrameSlot* FrameBufferAcquireLatest(FrameBufferHandle* fb);
const FrameSlot* FrameBufferAcquire(FrameBufferHandle* fb, FrameSeq seq);   /* NULL: overwritten */
void             FrameBufferRelease(FrameBufferHandle* fb, const FrameSlot* s);
```
- **The SAM3 side, per request:**
```c
for (;;) {
	Sam3Request req = Sam3ServerReceive(sock);                       /* {frame, phrase, floor, priority, wantMasks} */
	const FrameSlot* slot = FrameBufferAcquire(&fb, req.m_frame);
	if (slot == NULL) { Sam3ServerReply(sock, DETECT_FRAME_GONE); continue; }
	Detection det = Sam3DetectOnPixels(&model, slot->m_bgr, slot->m_width, slot->m_height, &req);
	FrameBufferRelease(&fb, slot);
	Sam3ServerReply(sock, &det);
}
```

### 4.4 "This is not meant to be a ring framebuffer, its meant to be literally just a buffer for frames? correct? ... How do you guarantee that the frames served to all of our systems are indeed the latest available frames?"
- **Both, split by role.** For the writer it is a ring: it walks the slots in order. For every
  reader it is "the latest frame": a reader never walks the ring; it reads `m_latest` and
  acquires that slot. The ring exists only so the writer can go on while a frame is held.
- **The guarantee:** `m_latest` is atomic and is written only after the slot is complete, so a
  reader never sees a half frame and always gets the newest complete one. A reader that holds
  frame N keeps N while it works; its next acquire gets the latest again.
- **32 slots** hold about 1.07 s at 30 fps. That is enough because held frames are skipped, not
  because 1 s covers a detect.

---

## 5. gemma.h -- the service: the ONE llama-server

**The job.** Run Gemma once, under the supervisor; answer chat requests for the recognizer's
planner and the vision describe.

**Today.** `gemma/server.py`: process() builds the ProcessSpec: the argv below, native_env(),
ready = GET /health == 200 and then one warm-up plan request, 240 s, proc-gemma.log, required.
`gemma/client.py`: Gemma(port, perf).request(messages, grammar, max_tokens, timeout) -> (ok,
text); records a "gemma" perf event with llama-server's own times. The supervisor stops it at
shutdown with SIGTERM, then SIGKILL after 10 s.

### 5.1 "Do you actually know how to start the gemma llama-server? ... That information that you find, is the exact information needed here." + "I genuinely don't understand what you want to change. KEEP IT IN ONE FUCKING PLACE!"
### 5.2 "I just don't understand how you plan to terminate the gemma process." -> "This is a really fucking stupid Suggestion." + the API you expect + the two REPO WIDE rules
- **In one place.** Your API, with the launch and the stop filled in:
```c
/* llama_server.h -- the ONE llama-server of the app. The app owns the handle. */
typedef struct llamaServerHandle {
	Process* mh_server;
	uint16_t m_port;
} llamaServerHandle;

/* The launch, exactly:
 *   llama-server -m <GEMMA_MODEL_PATH> --mmproj <GEMMA_MMPROJ_PATH> -dev Vulkan0 -ngl 99
 *     -c 4096 -np 1 --temp 0.0 --host 127.0.0.1 --port <port> --threads 1
 *     --jinja --chat-template-kwargs {"enable_thinking":false} --reasoning-budget 0
 *   env: LD_LIBRARY_PATH = <NATIVE_BIN_DIR> first
 *   ready: GET /health == 200 (503 while loading); up to 240 s
 *   log: <logDir>/proc-gemma.log
 *   after 3 failed restarts: die (a laptop part)
 *   stop: SIGINT, llama-server's own stop (it closes the server and frees the model); grace 10 s
 * Known: --image-min-tokens breaks the CLIP load; q4_0 KV + flash attention gives empty output;
 *        thinking off needs BOTH flags. */
llamaServerHandle llamaServerProcessBegin(Supervisor* s, const char* logDir, uint16_t port);
bool              llamaServerProcessEnd(llamaServerHandle* h);   /* false: it did not exit within the grace */

typedef struct llamaServerTimings {
	uint32_t m_cachedTokens;
	uint32_t m_promptTokens;
	uint32_t m_answerTokens;
	float    m_promptMs;
	float    m_answerMs;
} llamaServerTimings;

/* false = no answer, a timeout, or an invalid reply: the CALLER reports "llama-server failed". */
bool llamaServerProcessSendRequest(
	llamaServerHandle* h,
	const char* messagesJson,
	const char* grammar,
	uint32_t maxTokens,
	float timeoutS,
	char* reply,
	size_t cap,
	llamaServerTimings* timings
);
```
- **No Attach.** A benchmark begins its own server with its own Supervisor.
- **The stop, honestly.** llama-server has no stop endpoint. Its stop protocol is SIGINT, which
  it handles: it stops serving and frees the model. For a third-party process the signal IS the
  protocol. A kill is not a stop. It is the last resort after the grace, logged as a failure, so
  that no process keeps the GPU after the app ended. `llamaServerProcessEnd` returns false then.
- **The warm-up** is the APP's step after Begin: one planner request built by the recognizer's
  pure function (section 10). Not Begin's business, not the recognizer's.
- **REPO WIDE, applied to every process:** `XxxProcessBegin(Supervisor*, logDir, ...)` returns a
  handle by value; `bool XxxProcessEnd(XxxHandle*)` uses that process's own stop. The list: the
  llama-server (SIGINT), the SAM3 server (a "stop" message on its socket), the ASR node (SIGINT, a
  ROS2 node), the keyboard hook (SIGINT), the gstreamer receiver (SIGINT), the mock (SIGINT).
- **REPO WIDE, ownership:** a handle is a plain struct; the holder owns it; the app holds every
  handle. Opaque only for a thing that holds OS resources and no app state.

---

## 6. keys.h -- the global keys
- "Good." The naming pass only: `KeyboardHookHandle KeyboardHookProcessBegin(Supervisor*, const
  char* logDir, KeyFn onPress, KeyFn onRelease, void* app)` / `KeyboardHookProcessEnd`.

---

## 7. log.h -- the service: the session record (telemetry)

**The job.** Write what happened in a session so it can be replayed: every turn, every vision job,
every pass with its frame.

**Today.** `log/session.py` SessionLog: begin(heard, source) opens a per-thread record and claims
the mic's newest clip; set(**fields) adds to it; commit() appends one JSON line to trace.jsonl;
begin_request / save_pass / end_request write perception/<seq>-<kind>-<slug>/ with one raw frame
and one json (boxes: conf, box, label; forward ms) per pass and a request.json (kind, target,
query, verdict, passes). Masks are not saved. The concept string sent to SAM3 appears only as
each box's label. Nothing says which pass was the gate, the related-noun check or a refresh.

### 7.1 "what is the point of TurnInput@seq?" -> "Fine"
- The turn's number in the session; it names the clip and the perception folder; the job
  points back to its turn by it.

### 7.2 "What is TurnInput@epoch?" -> "That name is even fucking worse. Isn't this literally just the universally recorded time to sync with the rest of the perf benchmarks?"
- **Yes.** It is the same clock as every perf event. So it is typed as that clock:
  `PerfTimestamp m_startedAt`, taken by `PerfNow()`. The wall-clock of the session start is
  written once in meta.json; no turn carries a wall-clock.

### 7.4 "How do you plan to replay a whole session when you don't store data about images, including bboxes and the full noun/word-list used with SAM3?" + 7.5 "How do you plan to connect between a job and a turn?" -> "None of your bullshit. Horrible suggestions all around. ... This is the API that you should use" + "How do we make sure that you actually do software architecture design and not this asinine bullshit?"
- **Your API, used.** One call added, with its reason: a highlight runs for minutes and holds a
  frame for every pass; its frames cannot wait for the job's end, so a pass is recorded when it
  happens.
```c
/* telemetry.h -- the session record. Opaque: file handles and a queue, NO app state.
 * The app passes CONST data; the logger deep-copies or writes at once. */
typedef struct TelemetryLogger TelemetryLogger;

TelemetryLogger* TelemetryOpen(const char* sessionDir);
void             TelemetryClose(TelemetryLogger* t);

void TelemetryRecordTurn(TelemetryLogger* t, const TurnData* turn);
void TelemetryRecordVisionPass(TelemetryLogger* t, const VisionPassData* pass);
void TelemetryRecordVisionJob(TelemetryLogger* t, const VisionJobData* job);
/* the ASR node saved the mic clip before it published; the newest unclaimed one is this turn's */
bool TelemetryClaimMicClip(TelemetryLogger* t, uint32_t turnSeq, char* clipPath, size_t cap);
```
- **The data the app owns and passes.** The turn:
```c
typedef struct TurnData {
	uint32_t           m_seq;
	PerfTimestamp      m_startedAt;
	SpeechInputKind    m_input;
	char               m_heard[512];
	char               m_audioClip[128];      /* "" when none (the phone)                      */
	RecognizerDecision m_decision;            /* kind, he2, missionJson, target, reject, ms    */
	HttpStatus         m_platformStatus;      /* the phone app's answer, or 0                  */
	JobId              m_visionJob;           /* 0 = none. The job's data holds m_turnSeq back */
	char               m_spoken[256];
} TurnData;
```
  A pass, with everything a replay needs: the frame, the phrase SAM3 got, the step, the boxes,
  the masks:
```c
typedef enum VisionPassStep {
	PASS_GATE, PASS_VERIFY_HEAD, PASS_VERIFY_RELATED, PASS_REFRESH, PASS_COUNT_FRAME, PASS_DESCRIBE
} VisionPassStep;

typedef struct VisionPassData {
	JobId          m_job;
	uint32_t       m_turnSeq;
	VisionPassStep m_step;
	FrameSeq       m_frame;
	PerfTimestamp  m_capturedAt;
	const uint8_t* m_bgr;                     /* valid during the call: the slot is held */
	uint32_t       m_width;
	uint32_t       m_height;
	const char*    m_phraseSent;              /* "car, van, truck"                       */
	const Box*     m_boxes;
	uint32_t       m_nBoxes;
	const Mask*    m_masks;                   /* 0 when the pass asked for none          */
	uint32_t       m_nMasks;
	uint32_t       m_ms;
} VisionPassData;
```
  The job's data (its spec, its end state and result) is the vision system's; its design is
  section 8 and the coming design session.
- **The job-turn link** is in the data, both ways: the turn holds `m_visionJob`; the job holds
  `m_turnSeq`.
- **How I make sure architecture design happens.** The honest cause of the round-3 designs: I
  transcribed today's Python objects into C structs and called it an API. The gate below runs
  before any header reaches you; its answers stand at the top of the header:
  1. One sentence: what this unit does. If it needs "and", split it.
  2. Ownership: who creates it, who holds it, who ends it. Default: the app.
  3. Data in, data out: const data in; data out; a sink takes const; nothing reads another
     unit's memory.
  4. State: every mutable field with its owner; opaque only for OS or third-party resources.
  5. Threads: every thread, its owner, its stop.
  6. Processes: Begin and End, the ready check, the stop protocol.
  7. Names: the intent; the test is the header read cold by you.
  8. The API as code first; prose only for the why.
  And the process you set: one system at a time, in plan mode, with its full picture first.

---

## 8. perception.h -- the system: vision

**The job.** Run the operator's vision requests: highlight a thing and keep following it; count
things; describe the view.

**Today, the whole picture.**
- `perception2/vision.py` Vision: ONE class that holds the SAM3 priority lock, the dispatcher,
  the engine, the sinks, the per-task thread-locals, the highlight stop events. Its methods:
  count / highlight / describe / clear; the three job bodies; the gate; the tracking loop.
- `perception2/dispatcher.py`: one dispatcher thread; starts one thread per task; at most 8.
- `perception2/sam3_lock.py`: one SAM3 forward at a time; a user's command before a refresh.
- `perception2/engine.py`: the score gate (keep boxes near the best), the mask hygiene, the
  Gemma presence gate (GATE=vlm, off by default).
- `perception2/verify.py`: split a phrase into head, relation, related noun, colour; detect the
  head and the related noun; a colour check by hue; a geometry test per relation.
- `perception2/counting.py`: drop nested boxes; the median over frames.
- `perception2/concept.py`: a phrase -> the concept string SAM3 gets ("the vehicles" -> "car,
  van, truck, ...").
- `perception2/vlm_client.py`: the describe request to Gemma with the JPEG; the reply split
  into a long and a short text.
- The results reach the app through five callbacks (`app/turns.py` VisionSinks) that write into
  one locked global (`app/state.py` S: hl_dets, hl_masks, chat, thinking); the screen reads S.
- One highlight at a time in the code; the design says several (TN2). Clear = clear all (T3C).
  A jobs pane is in the plan (T3C (2)).

### 8.1 "How about you split the FUCKING PAYLOAD DEPENDING ON WHICH TASK WAS REQUESTED???" -> "SHOW ME THE FUCKING CODE."
- The payload per kind, as the job's result:
```c
typedef enum VisionJobKind  { VISION_JOB_HIGHLIGHT, VISION_JOB_COUNT, VISION_JOB_DESCRIBE } VisionJobKind;
typedef enum VisionJobState { JOB_CHECKING, JOB_TRACKING, JOB_ABSENT, JOB_LOST, JOB_CLEARED, JOB_DONE, JOB_NOT_READY } VisionJobState;

typedef struct HighlightUpdate { Detection m_detection; } HighlightUpdate;                              /* the boxes and masks of one pass */
typedef struct CountResult     { uint32_t m_median; uint32_t m_perFrame[8]; uint32_t m_nFrames; } CountResult;
typedef struct DescribeResult  { char m_answer[1024]; char m_spoken[256]; } DescribeResult;

typedef struct VisionResult {
	JobId          m_job;
	uint32_t       m_turnSeq;
	VisionJobKind  m_kind;
	VisionJobState m_state;
	PerfTimestamp  m_at;
	char           m_why[96];                 /* ABSENT: the failed check */
	union { HighlightUpdate highlight; CountResult count; DescribeResult describe; } m_as;
} VisionResult;
```

### 8.2 "What is the point of the functor of JobChanged?" -> "Bad design."
- Withdrawn. No callback from a module into the app. How a result reaches the app is the open
  design question of the vision session (below).

### 8.3 "Vision is a bad name." -> "I'll not review D3. Its in fucking narnia."
- Withdrawn with the rest. The names come out of the design session, after the units exist.

### 8.4 to 8.7 "I'll not review the rest of your comments, since your design is really bad, we can't really salvage anything here." + "This file supposedly encapsulates our vision system, which is a Job Scheduler That is literally glued together with a whole bunch of Stateless Vision Utilities. We need to split the responsibilities here. We need to run a proper /superpowers:brainstorming session on this"
- **Agreed.** The old perception.h is withdrawn whole.
- **What the session already settled (2026-10-04, your answers):**
  | question | your answer |
  |---|---|
  | the scheduler | a generic JobScheduler: JobFn plus data; no vision word in it |
  | the jobs pane: a click focuses a job | emphasize it: thick and bright; the others thin and dim |
  | the masks switch | per job, from the jobs pane; the t key goes |
  | how a result reaches the app | OPEN: my proposals were rejected twice, with no context given. It is asked again in the design session, with the full picture first. |
- **The split as it stands, for the session to start from** (not ruled):
```c
/* job_scheduler.h -- runs jobs on threads; knows nothing about vision. Opaque: threads only. */
typedef struct JobScheduler JobScheduler;
typedef uint32_t JobId;                                        /* 0 = none */
typedef void (*JobFn)(void* data, const _Atomic bool* stop);

JobScheduler* JobSchedulerOpen(uint32_t maxJobs);
void          JobSchedulerClose(JobScheduler* s);              /* stops every job; joins */
JobId         JobSchedulerStart(JobScheduler* s, JobFn fn, void* data, const char* name);   /* 0: maxJobs alive */
void          JobSchedulerRequestStop(JobScheduler* s, JobId id);
bool          JobSchedulerIsAlive(const JobScheduler* s, JobId id);
```
```c
/* vision_ops.h -- stateless vision utilities. Each takes the handles it needs; keeps nothing. */
typedef struct GateResult { bool mb_present; Detection m_found; char m_why[96]; } GateResult;
GateResult VisionGate(Sam3ServerHandle* sam3, FrameSeq frame, const char* phrase);          /* SAM3 >= 0.5; plus VerifyRelation when the phrase has one */
Detection  VisionHighlightPass(Sam3ServerHandle* sam3, FrameSeq frame, const char* phrase, bool wantMasks);
uint32_t   VisionCountPass(Sam3ServerHandle* sam3, FrameSeq frame, const char* phrase);
Target     VisionSplitTarget(const char* phrase);
bool       VisionVerifyRelation(Sam3ServerHandle* sam3, FrameSeq frame, const Target* t, const Detection* head, char* why, size_t cap);
bool       VisionDescribe(llamaServerHandle* llama, const FrameSlot* frame, const char* question, char* answer, size_t cap);
void       VisionPhraseToConcepts(const char* phrase, char* concepts, size_t cap);             /* "the vehicles" -> "car, van, truck, ..." */
```
  The three job bodies (HighlightJobRun, CountJobRun, DescribeJobRun) are loops over these
  calls. What they are given, what they own, and how their results travel: the design session.
- **What VerifyRelation is** (today's verify.py; it runs once per highlight, at the gate):
  1. Split the phrase: "bag held by child with green shirt" -> head "bag", relation TOUCH,
     related "child with green shirt", colour "green". A side word alone ("on the left") means
     no relation.
  2. Detect the head at floor 0.1; keep score 0.5 and above; none: absent.
  3. Detect the related noun; keep score 0.3 and above.
  4. A colour was said: keep the related boxes whose middle has that hue; none: absent.
  5. Test every (head, related) pair: TOUCH = overlap or a gap under 0.25 of the smaller side;
     NEAR = under 1.0; ON = horizontal overlap and the head's bottom meets the related's top;
     UNDER, ABOVE the same swapped; IN = 80 % of the head inside the related.
  6. One pair holds: draw that head. None: misplaced. A failed SAM3 call fails open.
- **The SAM3 ordering** (today the priority lock) moves into the SAM3 server as a priority queue
  (section 12); no lock in the vision system.

---

## 9. perf.h -- the service: the timings

**The job.** Record every timed event of a run to disk, cheaply, so metrics are computed later.

**Today.** `log/perf.py` Perf: record(stage, ms, **fields) appends a dict to a list under a lock;
mark(name) / end(name, stage) / take_since(name) / move_mark(a, b) keep named start times in a
dict; a writer thread appends the list to perf.jsonl every 5 s; die() flushes first; a GPU
sampler thread; a start-up watcher thread.

### 9 "This is a bad API" + the five bullets + the API you were imagining
- **Dynamic allocation:** today one dict per event; your design allocates the block once.
- **Blocking IO:** today the write is on a thread, but every record() takes a lock; your design
  takes none.
- **Same-name markers:** today two turns on two threads both mark "e2e"; the second overwrites
  the first. A real bug today. Your design has no marks: the app holds each start timestamp in
  its own data (the turn, the job, the push-to-talk release).
- **The running bool:** `_Atomic`, as every shared value.
- **"Nobody actually writes a marker system like this":** accepted.
```c
/* perf.h -- the timings of a run. Opaque: a thread, an atomic write index, a pre-allocated
 * array of fixed 128-byte blocks. NO app state. */
typedef struct PerfLogger PerfLogger;
typedef uint64_t PerfTimestamp;      /* monotonic nanoseconds; the one clock of the app */

typedef enum PerfStage {
	PERF_STARTUP, PERF_ASR, PERF_TURN, PERF_LLAMA_REQUEST, PERF_SAM3_REQUEST, PERF_DJI_REQUEST,
	PERF_HIGHLIGHT_GATE, PERF_COUNT, PERF_DESCRIBE, PERF_SAY, PERF_E2E, PERF_FRAME, PERF_GPU
} PerfStage;

PerfLogger*   PerfOpen(const char* sessionDir, uint32_t maxEvents);   /* allocates once; starts the writer thread */
void          PerfClose(PerfLogger* p);
PerfTimestamp PerfNow(void);                                          /* a clock read; no lock */
void PerfRecord(
	PerfLogger* p,
	PerfStage stage,
	PerfTimestamp start,
	PerfTimestamp end,
	const char* payloadJson                                           /* copied; at most 127 bytes */
);
```
- **One difference from your snippet:** `PerfStage` is an enum (your PRF1 ruling); the call
  shape is yours. **Open: Q1** if you want the string back.
- **Python, honestly:** time.monotonic_ns(); a list of maxEvents preallocated slots;
  itertools.count for the index (one bytecode, atomic under the GIL); about 1 us per record,
  not 50 ns; the writer thread flushes every 5 s and on die.

---

## 10. recognizer.h -- the system: the recognizer

**The job.** One sentence in, one tagged decision out, for the next stage.

**Today.** `recognizer/recognizer.py` Recognizer(control, vision, gemma, log): route(text) ->
Decision through fast_path (the triggers), bypass (the fixed commands), the negation guard, the
Hebrew rewrites, ONE Gemma plan request, the number guard and the echo guard; act(decision)
calls control or vision; handle = act(route). warm_up(gemma) sends one plan request at start.

### 10 "Recognizer should not have an internal state. It is literally a bundle of functions ..." + "Warming up 'the recognizer' means sending initial requests to the ... models ... This is not the responsibility of the 'Recognizer'"
- **No state; pure functions; no Create, no Close, no Act.** The app's turn handler does the
  dispatch, because the app owns the handles. The warm-up is the app's: one request after the
  llama-server began, built by the recognizer's pure message builder.
```c
/* recognizer.h -- one sentence in, one tagged decision out. Pure functions; no state. */
typedef enum DecisionKind {
	DECIDE_EMERGENCY, DECIDE_MANUAL, DECIDE_AUTO, DECIDE_CLEAR, DECIDE_MISSION,
	DECIDE_HIGHLIGHT, DECIDE_COUNT, DECIDE_DESCRIBE, DECIDE_REJECT, DECIDE_PLANNER_FAILED,
	DECIDE_EMPTY
} DecisionKind;

typedef enum RejectReason {
	REJECT_NONE, REJECT_NEGATED, REJECT_NUMBERS_CHANGED, REJECT_COPIED_EXAMPLE, REJECT_NOT_A_COMMAND
} RejectReason;

typedef struct RecognizerDecision {
	DecisionKind m_kind;
	char         m_he2[512];           /* the Hebrew the planner read; "" when no model ran */
	char         m_missionJson[2048];
	char         m_target[128];        /* highlight / count: the English target            */
	RejectReason m_reject;
	uint32_t     m_recognizeMs;
	uint32_t     m_planMs;
} RecognizerDecision;

RecognizerDecision RecognizerRoute(const char* text, llamaServerHandle* planner);

/* the steps of Route, in run order; the first that answers ends it */
TriggerKind RecognizerMatchTrigger(const char* text);                                      /* 1: the trigger table */
bool        RecognizerMatchFixedCommand(const char* text, char* missionJson, size_t cap);  /* 2: no model */
bool        RecognizerIsOnlyNegation(const char* text);                                    /* 3 */
void        RecognizerRewriteHebrew(const char* text, char* he2, size_t cap);              /* 4 */
void        RecognizerPlannerMessages(const char* he2, char* messagesJson, size_t cap);    /* 5: the app's warm-up uses it too */
bool        RecognizerParsePlan(const char* reply, RecognizerDecision* out);               /* 5 */
bool        RecognizerNumbersMatch(const char* he2, const char* missionJson);              /* 6 */
bool        RecognizerIsCopiedExample(const char* he2, const char* missionJson);           /* 6 */
```
- **The app's turn handler, where the dispatch now lives:**
```c
void AppOnTranscript(void* ctx, const Transcript* t) {
	App* a = ctx;
	TurnData turn = { .m_seq = a->m_turnSeq++, .m_startedAt = PerfNow(), .m_input = t->m_input };
	strcpy(turn.m_heard, t->m_text);
	if (t->m_input == SPEECH_INPUT_MIC_ASR) TelemetryClaimMicClip(a->mh_telemetry, turn.m_seq, turn.m_audioClip, 128);
	ChatAppendLine(&a->m_chat, CHAT_USER, t->m_text);
	turn.m_decision = RecognizerRoute(t->m_text, &a->m_llama);
	switch (turn.m_decision.m_kind) {
	case DECIDE_EMERGENCY: turn.m_platformStatus = PlatformCommandDispatcherSendEmergencyStop(a->mh_dispatcher); break;
	case DECIDE_MANUAL:    turn.m_platformStatus = PlatformCommandDispatcherSetManualControlMode(a->mh_dispatcher, true); break;
	case DECIDE_AUTO:      turn.m_platformStatus = PlatformCommandDispatcherSetManualControlMode(a->mh_dispatcher, false); break;
	case DECIDE_MISSION:   turn.m_platformStatus = PlatformCommandDispatcherSendCmdList(a->mh_dispatcher, turn.m_decision.m_missionJson); break;
	case DECIDE_CLEAR:     AppStopEveryHighlight(a); break;
	case DECIDE_HIGHLIGHT: case DECIDE_COUNT: case DECIDE_DESCRIBE:
	                       turn.m_visionJob = AppStartVisionJob(a, &turn); break;   /* the vision design session */
	default:               break;                                                   /* reject, failed, empty: nothing is sent */
	}
	AppWordTheResult(a, &turn);          /* -> m_spoken: ChatAppendLine + VoiceSay on every voice */
	TelemetryRecordTurn(a->mh_telemetry, &turn);
	PerfRecord(a->mh_perf, PERF_TURN, turn.m_startedAt, PerfNow(), "");
}
```

---

## 11. runtime.h -- the service: dying, the supervisor, the ROS2 context

(You did not re-review runtime.h in round 4; its round-3 points were ruled SUP1 and are shown here
because sections 2, 5 and 12 depend on them.)

**Today.** `runtime/supervisor.py`: one watcher thread per process, blocked in that process's
wait; a restart budget of 3; required -> die, else WAITING; stop_all = SIGTERM to all, SIGKILL
after 10 s. `runtime/fatal.py`: die(), on_die(), the crash hooks. `runtime/ros.py`: one node, one
executor and one thread per topic.
```c
/* runtime.h -- dying, the one supervisor of every process, the ROS2 context. */
void DieWithReason(const char* reason);
void RunBeforeTheAppDies(void (*fn)(void), bool first);
void TurnUncaughtErrorsIntoDie(void);

typedef bool (*ReadyFn)(void* ctx);
typedef bool (*StopRequestFn)(void* ctx);       /* the process's OWN stop message */
typedef enum StopMethod        { STOP_BY_SIGINT, STOP_BY_REQUEST } StopMethod;
typedef enum BudgetSpentPolicy { BUDGET_SPENT_DIE, BUDGET_SPENT_WAIT_FOR_USER } BudgetSpentPolicy;

typedef struct ProcessSpec {
	const char*       m_name;
	const char**      m_argv;
	const char**      m_env;
	ReadyFn           m_ready;
	float             m_readyTimeoutS;
	StopMethod        m_stop;
	StopRequestFn     m_stopRequest;
	float             m_stopGraceS;
	BudgetSpentPolicy m_onBudgetSpent;
	const char*       m_logPath;
} ProcessSpec;

typedef struct Process {
	ProcessSpec m_spec;
	int32_t     m_pid;
	uint32_t    m_restarts;
	bool        mb_plannedRestart;
	Status*     mh_status;
} Process;

typedef struct Supervisor {
	Process*     m_processes[16];
	uint32_t     m_nProcesses;
	OsThread*    mh_thread;        /* the ONE supervisor thread (SUP1)                 */
	OsQueue*     mh_events;        /* SIGCHLD -> an event; a stop request -> an event   */
	_Atomic bool mb_stopping;
} Supervisor;

Supervisor* SupervisorCreate(void);
Process*    SupervisorLaunch(Supervisor* s, const ProcessSpec* spec);
bool        SupervisorWaitUntilReady(Process* p, float timeoutS);
bool        SupervisorRestartOnPurpose(Process* p, const char* reason);
bool        SupervisorStop(Supervisor* s, Process* p);      /* the spec's stop, then the grace; false: it did not exit */
void        SupervisorStopEveryProcess(Supervisor* s);      /* at AppStop and on die */
void        SupervisorClose(Supervisor* s);

RosSubscription* RosListenOnOwnThread(const char* node, const char* topic, RosMessageFn fn, void* ctx);
void             RosStopListening(RosSubscription* s);
void             RosInit(void);
void             RosShutdown(void);
```
`SupervisorStop`: send the spec's stop (SIGINT, or the process's own request); wait the grace;
exited: the row DOWN, true; not exited: the row FAILED, a log line, SIGKILL as the last resort so
no process keeps the GPU, false.

---

## 12. sam3.h -- the service: the SAM3 server (its own process)

**Today.** `sam3/model.py` Sam3Backend in the app process: detect() encodes the frame once, runs
the text and detector step per concept, post-processes to boxes and masks, unions, drops nested
boxes; a lock makes one forward at a time. `sam3/loader.py`: loads it on a thread; a warm-up pass.
Masks: numpy bool arrays, one byte per pixel.

### 12.1 "Mask@Bits - what?" + 12.2 "Why is there a Sam3Process function, but on the other hand a Connect function?" + 12.3 "is the SAM3 API offered by transformers more explicit, and therefore should be rewritten more explicitly into the discrete steps ...? What do you think?"
- **Mask:** today one byte per pixel; "bits" was the wrong word. Across the process boundary a
  mask goes packed, one bit per pixel: 112.5 KiB per 720p mask instead of 900 KiB.
- **Two things, as for every process:** the Begin that launches the server under the supervisor
  and returns the handle; the request call on that handle. No separate Connect.
- **The five steps:** explicit, yes. You asked to see where a request's time goes (HDR3); the
  concept fan-out and the one encoding per frame are exactly that.
```c
/* sam3.h -- the SAM3 server: our Python process; loads the saved nf4 weights; serves detects. */
typedef struct Sam3ServerHandle {
	Process*           mh_server;
	uint16_t           m_port;
	FrameBufferHandle* mh_frames;     /* borrowed: the server opened the same block */
} Sam3ServerHandle;

/* launch: python3 -m sam3.server --weights nf4 --frames <shmName> --port <port>
 * ready: it answers "ready" after the load and one warm-up pass; up to 120 s
 * stop: the "stop" message on its socket; it frees the model and exits; grace 10 s
 * after 3 failed restarts: die */
Sam3ServerHandle Sam3ServerProcessBegin(Supervisor* s, const char* logDir, Sam3Weights w,
	const char* shmName, uint16_t port);
bool             Sam3ServerProcessEnd(Sam3ServerHandle* h);

typedef enum Sam3Priority { SAM3_PRIORITY_COMMAND, SAM3_PRIORITY_REFRESH } Sam3Priority;

typedef struct Sam3Request {
	FrameSeq     m_frame;
	const char*  m_phrase;          /* "car, van, truck": one concept per comma  */
	float        m_minScore;
	Sam3Priority m_priority;        /* the server's queue: COMMAND before REFRESH */
	bool         mb_wantMasks;
} Sam3Request;

typedef struct Mask {
	uint32_t m_width;
	uint32_t m_height;
	uint32_t m_strideBytes;
	uint8_t* m_packedBits;          /* 1 bit per pixel; the reader unpacks */
} Mask;

typedef struct Detection {
	DetectStatus m_status;          /* OK, NOT_READY, FRAME_GONE */
	FrameSeq     m_frame;
	uint32_t     m_n;
	Box          m_boxes[128];
	Mask         m_masks[16];       /* the kept boxes only, best first */
	uint32_t     m_ms;
} Detection;

bool Sam3ServerSendDetectRequest(Sam3ServerHandle* h, const Sam3Request* r, Detection* out, float timeoutS);

/* inside the server, one request = these five, in order */
void Sam3EncodeFrame(Sam3Model* m, const uint8_t* bgr, uint32_t w, uint32_t h, Sam3Embeds* out);   /* the image encoder, once per frame */
void Sam3DetectConcept(Sam3Model* m, const Sam3Embeds* e, const char* concept, Sam3Raw* out);     /* the text encoder, the detector, the mask decoder */
void Sam3PostProcess(Sam3Model* m, const Sam3Raw* raw, float minScore, Detection* out);          /* boxes, masks at frame size, scores */
void Sam3MergeConcepts(Detection* all, const Detection* one);                                     /* the union, best first */
void Sam3DropNestedBoxes(Detection* d);                                                           /* IoU > 0.5 or 70 % inside, same label */
```

---

## 13. scripted_run.h, 14. status.h, 15. util.h
- Round 3 answers stand (no round-4 points): `ScriptedRunMain` with the pseudo-code above it;
  the prefix pass on status.h and util.h.

## 16. video.h -- the frame source
- No round-4 points. The round-3 answer stands: a FrameSourceHandle with three kinds (the drone
  stream through the gstreamer node, the webcam, a file), the only writer into the frame buffer,
  which the app owns. The two unused kinds of today's code (a gstreamer pipeline string, a stream
  URL) are dropped. **Open: Q3** if you want them kept.

## 17. app.h -- the program
- No round-4 points. The App owns every handle, in build order; AppStart is the code, AppStop
  the reverse. The turn handler is in section 10. The vision parts of the App wait for the design
  session.

---

## 18. The open choices (besides the vision design session)
| ID | question | options, the recommendation first |
|---|---|---|
| Q1 | the perf stage | a. the PerfStage enum (PRF1), with your call shape. b. `const char* stage` as in your snippet. |
| Q2 | the phone's two channels | a. the TCP line only; the POST answered 200 and ignored; later the phone app sends TCP only. b. both, with the dedup. |
| Q3 | the two unused video kinds | a. drop them. b. keep them. |

## 19. What comes next (your instruction)
Plan mode, one system at a time, each with its full picture first: the vision system, then
audio, runtime, telemetry and perf, dji_app and the dispatcher, the app. Each ends in a spec you
approve; only then its header is rewritten.
