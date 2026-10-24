# The owner's review, round 4 (2026-10-04), word for word (of REVIEW-3-answers.md)

Review (3?) -
locally: Good
Globally: Good

1. audio.h -
1.1 - Understood, you're correct. It is not clear that this is the ROS2 ASR Process. In that case, what of the phoneBridge itself? If someone actually has to take a glance and understand, "alright, there are 2 ASR Inputs to this system, and 2 TTS outputs to this system, one is ..., the other is ...." and so on - This is not clear from reading the code, at all. CLAUDE! I SAID THIS, AND I WILL KEEP SAYING THIS - IF THE CODE IS NOT SELF DOCUMENTING, THEN EITHER:
A. THE SYSTEM IS FUCKING GINORMOUS (And even then, the subsystems should remain self explanatory on their own)
B. THE CODE IS BAD!
WHICH CASE DO YOU THINK APPLIES TO OUR SYSTEM? BE HONEST WITH YOURSELF PLEASE
1.2 - Which transmission is faster? why are we listening on both when we can listen on the faster one?
1.3 - Good
1.4 - Good, we should be pursuing that approach. Is it worth it to look into userspace threads, like fibers/coroutines/something-else-im-not-aware-of ?


2. dji_app.h
2.1 - Well we want to measure the e2e timings. you advise on extracting perf out, but I don't know if this means that the resulting performance benchmarks on specific DJI-App functions will still be as accurate, since we're operating on their outer scope.
2.2 - No, the supervisor is required here. WHO THE FUCK LAUNCHES ALL SERVICES BESIDES THE SUPERVISOR??? How do you actually know to route the commands properly to the mock server and not the phone if both are alive?
2.4 - Great!

* I took a second look at this, but this suffers from the same naming issues that many other APIs had.

3. flight.h
3.1 - I'm not reviewing your renames for flight.h. Here are the name lists:
```cpp

typedef struct PlatformCommandDispatcher {
  DjiApp*     dji;
  SessionLog* log;
  bool        manual;
} PlatformCommandDispatcher;

typedef PlatformCommandDispatcher PlatformCmdDispatcher;


PlatformCommandDispatcher* PlatformCommandDispatcherCreate(DjiApp* dji, SessionLog* log);
void                       PlatformCommandDispatcherClose(PlatformCommandDispatcher* f);

/*
  The comment here should be obvious by just looking at the code.
  If this is internal to the impl, then it shouldn't be stated here.
*/
/* manual = true: FIRST the flag (so no mission can leave after this line), THEN POST
 *     /c/stop: the aircraft stops and the RC has the sticks.
 * manual = false: the flag only; missions are allowed again. The F4 key and the spoken
 *     "manual" / "auto" all end here. */
HttpStatus PlatformCommandDispatcherSetManualControlMode(PlatformCommandDispatcher* f, bool manual);
bool       PlatformCommandDispatcherIsManualControlMode(const PlatformCommandDispatcher* f);

/* The emergency stop. It ALWAYS stops the aircraft, in both modes: auto: a zero-length
 * mission replaces the running one (we keep the sticks); manual: /c/stop (the RC keeps
 * the sticks). */
HttpStatus PlatformCommandDispatcherSendEmergencyStop(PlatformCommandDispatcher* f);

/* Send one mission. Manual mode: nothing is sent and the answer is 409 CONFLICT. */
HttpStatus PlatformCommandDispatcherSendCmdList(PlatformCommandDispatcher* f, const char* missionJson);

```

3.2-3.5 - See My previous bulleted response
3.6 - Good! Option A


4. frame.h
4.1 - The Source: Is this A or B? I don't understand what you exactly meant here. The rest is clear.
4.2 -
* How is the app the writer when Video is the Source of the frames? Are you suggesting that Video Copies the data into the app first, then transmitted over to the shared framebuffer?
* Why would gemma not read it? Don't we send Describe() commands to gemma? HOW WOULD GEMMA KNOW TO RESPOND TO THE QUESTIONS?????!?? IT NEEDS THE LATEST FRAME!
* Where in the app is this actually handled?? care to elaborate?? Is this just the FrameRing API? Where would it be called?
* Besides that your answers seem reasonable here.

4.3 -
* OK
* What do you mean "The frame is dropped and counted" ? WHICH FRAME? THE OLD ONE OR THE NEW ONE? I hope you mean the former here, we don't need old frames laying around in the Ring buffer
* OK
* OK
* This is absolutely not clear enough, jesus christ claude.
* OK
* THEN CALL IT AN ATOMIC FUCKING COUNTER, AS IT SHOULD BE CALLED! STOP USING EUPHEMISMS FOR CONCEPTS THAT ALREADY HAVE ESTABLISHED GROUNDING!

4.4 - I see. This is not meant to be a ring framebuffer, its meant to be literally just a buffer for frames? correct? Otherwise, I don't understand what you said here claude. How do you guarantee that the frames served to all of our systems are indeed the latest available frames?


5. gemma.h
5.1 - I genuinely don't understand what you want to change. KEEP IT IN ONE FUCKING PLACE! WHY DO YOU REDIRECT ME ALL OVER THE FUCKING PLACE CLAUDE! EVERY TIME YOU MAKE A GOD DAMN CHANGE-NOTE I HAVE TO RUN AROUND IN YOUR MULTI PAGE DOCUMENT LIKE A RETARD! YOU WANT TO SUMMARIZE ALL THE DETAILS AT THE END!? SURE! DO IT! BUT DONT MAKE ME GO THROUGH LOOPS AND HOOPS JUST TO COME TO A GOD DAMN CONCLUSION! FUCK!

5.2 -
* This is a really fucking stupid Suggestion.
* ![REPO WIDE(!)]!  Look into the API that I made below. This API should follow for any process that should run/stop that our supervisor would ever run, period.
* Do you think Killing processes is a normal and acceptable way to return resources to the system? ARe you fucking retarded? Sending a pkill and calling it a day?
* I expect you to generalize properly from this specific example to the rest of our processes.
* ![REPO WIDE(!)]! There are very few Modules in this repo that should have internal state. And even then, those should be still be Created() and Destroyed() accordingly. Most of the ownership is on the app's side.


* The API that I expect:
```c
typedef struct llamaServerHandle {
  Process* mh_server;
  uint16_t m_port;
} llamaServerHandle;


/* Called ONCE by the app at start: launches the server under the supervisor. */
llamaServerHandle llamaServerProcessBegin(Supervisor* s, const char* logDir, uint16_t port);
bool              llamaServerProcessEnd(llamaServerHandle* procToEnd);
/*
  This type of function is weird - if begin() returns a handle,
  Why should the internal state of this header contain the data of that same server?
  This header is supposed to be called purely by the app, only the app will have actual ownership of this process.
  How do you suppose the API here should Know about the internals of the App, given that the app Owns the handle?
  You might say hold an internal state for this "llama-server" abstraction. But why? This is literally a pure interface.
  Nothing is owned here. Nothing owns anything here. If you are really strict about ownership, you can argue that the llamaServerHandle is owning something here, when in reality - The one that holds said handle is the owner, in actuality.

  This should not exist.
*/
llamaServerHandle llamaServerProcessAttach(uint16_t port);


/* llama-server's own times for one request */
typedef struct {
  uint32_t cachedTokens;
  uint32_t promptTokens;
  uint32_t answerTokens;
  float    promptMs;
  float    answerMs;
} llamaServerTimings;


/* One chat request. false = no answer, a timeout, or a reply that is not valid: the
 * CALLER reports "llamaServerHandle failed"; it is never "the user said something invalid".
 * Thread-safe. */
bool llamaServerProcessSendRequest(
  llamaServerHandle* hdl,
  const char* messagesJson,
  const char* grammar,
  uint32_t maxTokens,
  float timeoutS,
  char* reply,
  size_t cap,
  llamaServerHandleTimings* timings
);
#endif

```

7. log.h
7.1 - Fine
7.2 - That name is even fucking worse. Isn't this literally just the universally recorded time to sync with the rest of the perf benchmarks?
7.4 & 7.5 -
* None of your bullshit. Horrible suggestions all around. You literally don't apply software architecture design to ANY of our API proposals. This is fucking insane. I don't know how I never realized this. You're Operating in retard mode and unfortunately I didn't catch it. How do we make sure that you actually do software architecture design and not this asinine bullshit?
This is the API that you should use -

```c
/* Logger is completely opaque. Holds file handles/queues, NO app state. */
typedef struct TelemetryLogger TelemetryLogger;

TelemetryLogger* TelemetryOpen(const char* sessionDir);
void             TelemetryClose(TelemetryLogger* log);

/* App passes CONST data. Logger deep-copies or writes to disk immediately. */
void TelemetryRecordTurn(TelemetryLogger* log, const TurnData* turn);
void TelemetryRecordVisionJob(TelemetryLogger* log, const VisionJobData* job);

```
DO you understand what I'm talking about now, claude?

8. perception.h
8.1 - SHOW ME THE FUCKING CODE. I don't need your words. I need CODE, AN API TO STARE AT, TO UNDERSTAND YOUR ACTUAL INTENTIONS. OUR SHARED LANGUAGE IS CODE, NOT ENGLISH! NOT HEBREW! NOT FUCKING PORTUEGESE! CODE!
8.2 - Bad design.
8.3 - I'll not review D3. Its in fucking narnia. See my previous notes regarding this.
8.4 => 8.7 - I'll not review the rest of your comments, since your design is really bad, we can't really salvage anything here.
* This file supposedly encapsulates our vision system, which is a Job Scheduler That is literally glued together with a whole bunch of Stateless Vision Utilities. We need to split the responsibilities here.
* We need to run a proper /superpowers:brainstorming session on this, since this cannot continue.


9. perf.h -
* This is a bad API
* What about the overhead of dynamic allocation of buffers?
* What about blocking the IO, causing the App to stall while you write to disk?
* What about thread collisions on same-name markers?
* what about the fact that your running bool is not actually atomic?
* Nobody actually writes a marker system like this.
* this is more in line with what I was imagining -
```c
#include <stdint.h>
#include <stdbool.h>

/* Opaque struct containing thread, atomic write index, and pre-allocated array */
typedef struct PerfLogger PerfLogger;

/* A mark is just a raw nanosecond timestamp. API does not track this. App does. */
typedef uint64_t PerfTimestamp;

/* 1. Allocate huge fixed buffer once. Spawns background disk writer thread. */
PerfLogger* PerfOpen(const char* sessionDir, uint32_t maxEvents);
void        PerfClose(PerfLogger* p);

/* 2. Fast clock read. Zero locks. */
PerfTimestamp PerfNow(void);

/* 3. Record event.
 * Uses atomic_fetch_add on buffer index. Zero locks. Takes < 50ns.
 * Copies payload into fixed 128-byte block to prevent dangling pointers.
 */
void PerfRecord(
    PerfLogger* p,
    const char* stage,
    PerfTimestamp start,
    PerfTimestamp end,
    const char* payloadJson
);

```


10. recognizer.h
* Recognizer should not have an internal state. It is literally a bundle of functions to mutate and manage data, to tag it to the next part in the pipeline.
* Warming up "the recognizer" means sending initial requests to the command-producing/translation/vision/etc... models, not anything else. This is not the responsibility of the "Recognizer" to "warm up" models.



I am done reviewing your "changes"/"suggestions". You're fucking braindead. Address every single point. Your designs are horrible. Each system has responsibilities that it shouldn't have, and so much more going on than necessary. We will need to do a proper design review / architecture review for each system here, because this won't fly.

---
Later the same day, in plan mode (the agent's questions and the owner's answers):
- "Ignore everything before Review (3)" (the text above the review was personal notes).
- The vision split, the scheduler: "Generic JobScheduler".
- How a job's result reaches the app (three proposals: an event queue drained by the screen loop; a queue drained by a results thread; no queue, the loop compares states): "All horrible designs".
- The jobs pane, a click focuses a job: "Emphasize the focused job".
- The "draw masks" switch: "Per job, from the jobs pane".
- Which thread consumes the result messages (the main thread; a results thread with a double-buffered model; two queues): "all designs horrible".
- Which property of the results path is wrong: "What is the system we're discussing? Are we discussing multiple? If so, what is the connection we're discussing? You're throwing me in with no context at all regarding the problem and just asking me highly specific technical questions when I lack complete context regarding the old way we did it, the way I responded to you (mind you, your response is from yesterday) and now the highly specific information you gave me regarding a design decision. You do not perform a design-review/architecture-design of a system without a full complete picture of it. Re-review my notes, Get out of planning mode, and address every single one of my points. After that, we will get into plan mode, and properly Design everything as we should, one system at a time."
