# harden2 API rev4: the design being devised with the owner (started 2026-10-02)

Input: the owner's review of rev3 (docs/api-harden2/rev3/REVIEW-1-owner.md). For each point: the
fact in today's code, then the proposed API. PROPOSED = the agent's proposal, not yet ruled.
Nothing is implemented. The next agent builds from the ruled version of this file.

## 1. audio.h
Facts today:
- A source is a text: "ros" (the laptop mic) or "phone"; the session log calls the mic "mic".
- RosAsr subscribes to the ASR server's ROS2 transcript topic. PhoneAsr runs its own socket server
  (REST and TCP on one port, because the phone app sends each transcript both ways), drops the
  duplicate, and hands the text on through a queue and a second thread. That is its bulk.
- SpeechIn only builds the listed sources, closes them and collects their status rows. Each source
  calls the same callback on_heard(text, source) itself.
- LaptopTts: phonikud turns Hebrew text into phonemes; piper turns phonemes into audio; the audio is
  played on the laptop. PhoneTts posts the text to the phone app's /tts.
- SpeechOut: say(text) stores ONE waiting sentence (the newest wins) and wakes a worker thread; the
  worker stops what plays on every output, then speaks the sentence on each output in turn. `names`
  only labels the perf record of each output. `perf` records how long each sentence took to speak.
PROPOSED (the owner's ideal: every source -> text -> the ROS2 network):
```c
typedef enum { SPEECH_MIC, SPEECH_PHONE } SpeechSource;         /* no free text              */
/* ONE path into the app: the ROS2 transcript topic. The laptop mic's ASR server already
 * publishes there. The phone bridge is a small listener that republishes each phone transcript
 * on the SAME topic, tagged SPEECH_PHONE. The app then has ONE subscriber. */
typedef void (*HeardFn)(const char* text, SpeechSource source);
typedef struct SpeechIn { RosSubscription* transcripts; HeardFn onHeard; } SpeechIn;
SpeechIn* SpeechInCreate(HeardFn onHeard);
void      SpeechInClose(SpeechIn* in);
typedef struct PhoneBridge {            /* phone -> the transcript topic                     */
	uint16_t  port;                     /* the phone app posts {"text": ...} here            */
	OsThread* listener;                 /* receives, drops the duplicate, republishes        */
	Status*   status;                   /* the "phone speech" row                            */
} PhoneBridge;
typedef enum { VOICE_PHONE, VOICE_LAPTOP } VoiceOutput;
typedef struct Voice {                  /* one way to speak                                  */
	VoiceOutput kind;
	void (*speak)(struct Voice* v, const char* text);   /* blocks until spoken               */
	void (*stop)(struct Voice* v);                      /* cut what is playing               */
} Voice;
typedef struct SpeechOut {
	Voice**      voices;  uint32_t nVoices;   /* each spoken sentence goes to every voice     */
	OsThread*    worker;                /* speaks; say() never blocks                        */
	OsCondition* wake;
	bool         running;               /* atomic                                            */
	const char*  pending;               /* the ONE waiting sentence: the newest wins         */
} SpeechOut;
```
`names` goes (a Voice knows its kind). `perf` goes from the struct: the worker reports each
sentence's time through the app's perf callback, or the timing is dropped (owner to say).

## 2. control.h -> flight.h
Facts today: manual_on() only READS the mode. manual() turns the transmit switch off and sends
/c/stop; auto() turns it on; toggle_manual() is the F4 key; emergency_halt() and fly() send. The lock
makes "switch off + send stop" one step against the other thread.
PROPOSED (the owner: "the flight controller on the software side"; fewer functions; an atomic flag):
```c
typedef struct FlightController {
	DjiApp*     dji;
	SessionLog* log;                    /* every mission sent is recorded in its turn        */
	bool        manual;                 /* ATOMIC. true: missions are refused, the RC flies  */
} FlightController;
FlightController* FlightCreate(DjiApp* dji, SessionLog* log);
void       FlightClose(FlightController* f);
HttpStatus FlightSetManual(FlightController* f, bool manual);  /* true: flag on, then /c/stop;
                                                                  false: flag off            */
bool       FlightIsManual(const FlightController* f);
HttpStatus FlightHalt(FlightController* f);     /* the emergency: works in both modes        */
HttpStatus FlightFly(FlightController* f, const char* missionJson);   /* 409 while manual    */
```
No lock: the flag is set before the stop is sent, so a mission can never slip out after "manual".
The voice thread keeps running in manual mode: vision requests work, missions come back refused.
The F4 key is FlightSetManual(f, !FlightIsManual(f)). The wording of a result (outcome_text) moves
to the app, which words every result (rev3 GAPS.md G14).

## 3. dji_app.h
Facts: the phone is outside the laptop, so nothing tells us when it comes back. While it does not
answer, ONE background thread asks GET /status/ every 2 s and turns the row from WAITING to UP when it
answers. `probing` says that thread runs (so a second one is never started); `closed` ends it at
shutdown; `status` is the "dji app" row of the status pane.
PROPOSED: keep the behaviour; `probing` and `probeLock` become the thread handle itself
(`OsThread* probe`, NULL when none runs).

## 4. gemma.h
Facts: two different things carry the name. GemmaProcess() is only the DESCRIPTION of the
llama-server process, which the supervisor starts. GemmaCreate() makes a small client object (a port
and perf); GemmaClose() releases nothing.
PROPOSED (the owner: one handle):
```c
typedef struct Gemma {
	Process* process;                   /* the supervised llama-server; NULL when attached   */
	uint16_t port;
} Gemma;
Gemma* GemmaStart(Supervisor* s, const char* logDir, uint16_t port, bool thinking);
Gemma* GemmaAttach(uint16_t port);      /* a benchmark: a server someone else started        */
bool   GemmaRequest(Gemma* g, const char* messagesJson, const char* grammar, uint32_t maxTokens,
	float timeoutS, char* reply, size_t cap);
```
No GemmaCreate, no GemmaClose: the supervisor stops the process with every other process.

## 5. keys.h
Facts: the "keys process" is the native keyboard hook (C++): it reads the keyboard for every window
and publishes each press and release on its own ROS2 topic (not the transcript topic). Python's Keys
is only the subscriber. The hook is a process because it is a separate native program.
Can it fail: it is a process, so the supervisor watches it like the others (3 restarts, then the app
dies: without it there is no F4). No failure of it is recorded (unverified).
PROPOSED: no change.

## 6. log.h (and perf.h)
Facts:
- perceptionDir: the folder where this turn's vision work is saved (each SAM3 pass: the frame and its
  boxes; a describe: the frame and the answer). A turn with no vision request has none.
- `kind` holds what the sentence was decided as, as text.
- `tl`: the mic turn and a phone turn can be open at the same moment on two threads, so "the open
  turn" is kept per thread. `seq`: the turn counter. `claimed`: the ASR server saves each utterance
  as a clip; a mic turn takes the newest clip no turn has taken yet.
- The turns are not kept: each is written to trace.jsonl when committed.
PROPOSED:
```c
typedef enum { TURN_EMERGENCY, TURN_MANUAL, TURN_AUTO, TURN_CLEAR, TURN_MISSION, TURN_HIGHLIGHT,
	TURN_COUNT, TURN_DESCRIBE, TURN_REJECT, TURN_GEMMA_FAILED, TURN_EMPTY } TurnKind;
typedef struct {                        /* 1. the raw input                                  */
	uint32_t seq;  double epoch;  SpeechSource source;
	const char* heard;                  /* the transcript                                    */
	const char* audioClip;              /* the mic clip, or NULL                             */
} TurnInput;
typedef struct {                        /* 2. what the recognizer decided                    */
	TurnKind kind;
	const char* he2;  const char* missionJson;  const char* target;
	RejectReason reject;  uint32_t recognizeMs, planMs;
} TurnDecision;
typedef struct {                        /* 3. the vision request, when kind is a vision kind */
	TaskId task;  const char* passesDir;    /* the saved frames and boxes of its passes      */
	const char* resultJson;             /* count: n; highlight: present, best; describe: answer */
} TurnVision;
typedef struct {                        /* 4. what the user got back                         */
	HttpStatus control;  const char* spoken;  uint32_t e2eMs;
} TurnResponse;
typedef struct { TurnInput input; TurnDecision decision; TurnVision vision; TurnResponse response; } Turn;
typedef struct SessionLog {
	const char* dir;
	Turn*    turns;  uint32_t nTurns;   /* every turn of the session, in order               */
	OsLock*  lock;
} SessionLog;
Turn* LogBeginTurn(SessionLog* log, const char* heard, SpeechSource source);
void  LogCommitTurn(SessionLog* log, Turn* t);          /* also one line of trace.jsonl      */
```
The caller holds its Turn, so no per-thread slot is needed; the clip is taken inside LogBeginTurn.
Use, in C:
```c
Turn* t = LogBeginTurn(log, "עלה חמישה מטרים", SPEECH_MIC);
RecognizerRoute(rec, t->input.heard, &t->decision);      /* fills the decision               */
t->response.control = FlightFly(flight, t->decision.missionJson);
t->response.spoken  = "mission: sent";
LogCommitTurn(log, t);                                   /* the turn is in log->turns        */
```
Perf moves to its own header, perf.h (log/perf.py is already its own file).

## 7. perception.h: what the engine does
One highlight pass, on one frame, for one phrase ("red backpack"):
1. Ask SAM3 for every candidate, at a low score threshold, so weak ones are seen too.
2. Keep only the boxes whose score is near the best one (a 0.48 box dies next to a 0.90 box; two
   windows at 0.85 and 0.88 both stay).
3. Give each kept box its mask; drop a mask that covers almost the whole frame; tighten the box to
   its mask; drop a near-full-frame box that has no clean mask.
The "gate" (is it there at all?) runs before the first pass: SAM3 must find it with a score of 0.5 or
more; for a target with a relation ("the bag held by the child") the related object and the relation
are checked too (verify).
PROPOSED: no object, three plain functions:
```c
uint32_t HighlightPass(Sam3* sam3, const VideoFrame* f, const char* phrase, Box* boxes, Mask* masks,
	uint32_t cap);                              /* steps 1-3; masks[i] belongs to boxes[i]   */
bool     HighlightGate(Sam3* sam3, const VideoFrame* f, const char* phrase, const char** why);
uint32_t CountPass(Sam3* sam3, const VideoFrame* f, const char* phrase);
```
The thresholds (floor, drawConf, rel, maskK) are config values, not members.

## 8. recognizer.h
Facts: Route() decides and sends nothing (the benchmark calls it). Act() carries a decision out.
Recognize() is Route then Act (the app's one call). Plan() is the one Gemma request inside Route; it is
public only for the benchmarks and the warm-up.
PROPOSED: the public API is Create, Close, Recognize and Route. Act and Plan become internal.
`RecognizerCreate(flight, vision, gemma, log, bool warmUp)`: with warmUp it sends one plan request,
so the planner's prompt is in Gemma's cache before the first command.

## 9. runtime.h
Facts and PROPOSED, point by point:
- The Status lock: the owner of a row writes (state, detail); the screen reads both. PROPOSED: no
  lock: the pair is replaced in one atomic step.
- `procs`: name -> the OS process, so the supervisor can stop or restart it.
- The Supervisor is ONE object for ALL processes; a Process is the handle of one of them.
- StatusBoard: PROPOSED: its own header, status.h (Status, StatusRow, StatusBoard).
- SupProcess is the DESCRIPTION of how to start a process (argv, env, the ready check); Process is the
  running one. PROPOSED: rename SupProcess to ProcessSpec, the code's name.
- SysPackage: one line of the preflight's dependency list (an import name and its install command).
  PROPOSED: it leaves the runtime API and goes to the preflight tool's own header.
- RosStart / RosStop: rclpy needs init() once before the first node and shutdown() once at the end.
  PROPOSED: no public calls: the first RosSubscribe initialises, the last RosSubscriptionClose
  shuts down.

## 10. sam3.h
Facts: `precision` names the weights ("nf4" or "bf16"). `quantize` = True means "load bf16 and
quantize it to 4 bits now"; False loads weights saved already in 4 bits. Only sam3/save_nf4.py uses
True. The lock guards the mask cache between a detect and a later mask lookup on another thread.
PROPOSED: `typedef enum { SAM3_NF4, SAM3_BF16 } Sam3Precision;` `quantize` leaves the backend (the
save tool does it). The lock goes with the cache when masks are kept per frame (rev3 GAPS.md G4).
SAM3 as its own process (owner: "RIGHT NOW"): earlier rulings S2 and POST (2) put it after the
freeze; this is a new instruction. PROPOSED shape, to be measured before it is ruled:
```c
ProcessSpec Sam3Process(const char* logDir);   /* loads the model, warms up, then serves     */
typedef struct Sam3 { Process* process; void* frames;  /* a shared-memory ring of frames     */
	uint16_t port; } Sam3;                     /* requests: frame index + phrase -> boxes   */
```
The frame-transfer cost was measured in bench/sam3-assessment (read its README before designing).

## 11. util.h, 12. video.h
No change asked.
