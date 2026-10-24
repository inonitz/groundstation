# First principles: remove each component in thought; which assumption is not a proven fact
Reviewed: docs/api-harden2/rev5/01-system-architecture.md and its .html drawing. Date: 2026-10-08.

## The removal test, every component
"Forces" are sections 8 and 9. "Holds" means the forces are still met without the component.

| component (section) | removed, replaced by | holds? | verdict |
|---|---|---|---|
| the message queue (4) | workers write app state under a lock | no: SYS1 | keep |
| the keys listener (3) | one ROS spin thread with two subscriptions | yes | F3 |
| the mic listener (3) | the same thread | yes | F3 |
| the phone listener (3) | the HTTP POST handler as the channel | yes, slower by one handshake (SK6) | keep, see F10 |
| the supervisor thread (3) | a blocking wait per child, as today | yes | F4 |
| the recognizer worker (3) | the route on the main thread, the plan on the pool | no: the plan blocks; order lost on a pool | keep |
| the platform worker (3) | the pool sends commands | no: order lost | keep, and add F6 |
| the voice workers x2 (3) | one worker: POST /tts, then speak on the laptop | likely (uncertain) | F5 |
| the thread pool of 8 (3) | a pool of 3 | yes: SAM3 serves 2.4 per s | F9 |
| the frame source thread (3) | the main thread reads the camera | no: a blocking read | keep |
| the shared-memory buffer (6) | a pipe to SAM3, 3.1 ms per pass | yes, 3 ms slower per pass | F2 |
| the 32 slots (6) | 3 slots with copy-and-release readers | yes, if readers copy | F1 |
| the reference counts (6) | a sequence per slot, readers copy and retry | yes | F1 |
| the status rows (5) | messages | no: STA1 | keep |
| telemetry (7) | nothing | no: section 1 ("records every turn") | keep |
| perf (7) | telemetry timestamps | likely yes (uncertain) | F11 |
| the keyboard hook process (2) | cv2.waitKey in the main loop | yes if keys need no global hook | F8 |
| the ASR node (2) | whisper in the app | no: the owner's C++ node; GPU isolation | keep |
| the gstreamer receiver (2) | cv2 decoding H.264 in the frame source thread | likely yes (uncertain) | F7 |
| llama-server (2) | an in-process model | no: ONE slot and a GPU process boundary | keep |
| the SAM3 server process (2) | SAM3 on a thread | no: 8 to 10 frames over 100 ms on a thread | keep |
| the mock (2) | nothing | no: the scripted run refuses a real control | keep |
| the SAM3 priority queue (2) | one pending request per job | yes, and smaller | F9 |
| the platform priority queue (4) | a FIFO plus an emergency sender | yes | F6 |
| the route FIFO (4) | the recognizer worker reads the message queue | no: the main thread is the only consumer | keep |

## Findings (ranked)
Each finding: what is wrong; why it matters; the force or rule it breaks, with the section; a
fix; the question for the owner. "(uncertain)" marks a finding I could not verify.

### CRITICAL
F6 The component the emergency budget needs is missing.
- Wrong: no component on the drawing can deliver a stop while a /c/fly blocks the one platform
  worker; the priority queue orders, it does not preempt.
- Matters: the budget of section 8 is met only when the phone is fast; a stop matters when it
  is slow.
- Breaks: section 8 (under 1 s) against section 3 (HTTP blocks up to 3 s).
- Fix: an emergency sender: its own thread, its own connection, fed by the main thread
  directly; the platform priority queue becomes a FIFO.
- Ask: does the phone app run /c/stop while a /c/fly is in flight?

### HIGH
F1 The reference counts exist only because readers hold a slot for the whole pass.
- Wrong: section 6 holds a slot for the duration of a detect (0.4 to 1.9 s plus the queue
  wait); a reader that copies the slot and releases holds it for about a millisecond
  (2.7 MB memcpy, unverified); then a sequence per slot replaces the counts: read the sequence,
  copy, re-read, retry if changed; the writer's return period to a slot is 32 / 30 = 1.07 s.
- Matters: the counts bring the leak on a reader's death, the hand-off ownership and the
  load-then-increment window; a copy brings none of them; SAM3 copies too and the cross-process
  count disappears.
- Breaks: SK5 decided the count mechanism; nothing ruled that readers hold rather than copy;
  R2 and R3 keep the ring and "readers start from latest", which the copy keeps.
- Fix: a sequence per slot; readers copy and release; the writer never waits; the count fields
  go.
- Ask: zero-copy holds with counts, or a copy with a sequence? SK5 is named, not overruled.

F2 The shared-memory buffer saves 3 ms per pass.
- Wrong: the measured gain is 0.1 ms against 3.1 ms through a pipe (bench/sam3-assessment);
  a pass is 410 to 1900 ms; the gain is 0.2 to 0.7 percent; the cost is the whole protocol of
  section 6 across a process boundary.
- Matters: the hardest concurrency in the design buys the least.
- Breaks: ruling T6 ("without sending 2.7 MiB per request") and R2, R3 stand; the review asks
  whether the number was known when T6 was ruled.
- Fix: none proposed against the ruling; the question only.
- Ask: given 3 ms per pass, does T6 stand, or does SAM3 take its frame over the socket?

F12 Three statements in the document are not facts.
- Wrong: "at most 8 vision results per s" (section 8) against 1.6 to 2.4 SAM3 passes per s;
  "every one created, watched and destroyed by the app's supervisor" (section 2) for the phone
  app, which is not a child; "its process dies and restarts" (section 9) for an OOM that torch
  raises as an exception (uncertain).
- Matters: a header written from a false fact is wrong on day one.
- Breaks: SK1 (sections 1 to 5 of the sketch "mostly" correct) does not cover these three.
- Fix: 2.4 results per s at most, 3.3 s per highlight at eight jobs; five children plus the
  mock; "the SAM3 server exits on an OOM by design".
- Ask: confirm the server exits on OOM.

F13 Four forces are asserted, not measured.
- Wrong: the 33 ms frame with the draw and sixteen threads; the whisper leg; the aircraft's
  response to /c/stop; the describe chat's time.
- Matters: the emergency budget and the frame budget rest on them.
- Breaks: section 8 ("measured").
- Fix: four measurements before the headers; the ones needing the phone marked as such.
- Ask: which may be measured on the mock?

### MEDIUM
F3 The keys and mic listeners are one thread.
- Wrong: two ROS spin threads for two subscriptions; one executor spins both.
- Matters: one thread fewer on the GIL; one fewer to close.
- Breaks: KISS (guidelines, design priorities); section 3 ("three producer threads").
- Fix: one ROS listener thread; two callbacks; two message kinds.
- Ask: none.

F4 The supervisor thread adds a thread and a queue for rare events.
- Wrong: CPython delivers signals on the main thread, so the drawn thread cannot receive
  SIGCHLD; today's runtime/supervisor.py waits per child on its own thread with no poll (line
  207).
- Matters: the design as drawn cannot be built; the simpler shape already exists.
- Breaks: section 3; section 10 (no blocking step on the main thread); SK3 point 4 rejected
  polling, not a blocking wait.
- Fix: a blocking wait per child; the waiter writes the row and runs the restart policy.
- Ask: is a blocking wait per child "event-driven" under SK3 point 4?

F7 The gstreamer receiver process and its ROS topic carry 2.7 MB per frame through rclpy.
- Wrong: the frame source thread could decode H.264 with cv2's gstreamer backend in process;
  the ROS hop costs an unmeasured deserialization per frame under the GIL (uncertain).
- Matters: a process, a topic and a copy for every frame at 30 fps.
- Breaks: KISS; section 8 lists no cost for the hop.
- Fix: measure the rclpy cost per bgr8 frame; if above 3 ms, decode in process.
- Ask: why a separate process? The document gives no reason.

F9 Eight jobs and a priority queue serve a SAM3 that does 2.4 passes per second.
- Wrong: three jobs at one refresh per second already saturate SAM3; eight is a config value
  (VISION_MAX_ACTIVE_TASKS), not a derivation; the SAM3 queue needs no priority if each job
  has one pending request.
- Matters: the pool and the queue are sized for a throughput SAM3 cannot give.
- Breaks: section 3 and section 8 against bench/sam3-assessment.
- Fix: the job count derived from SAM3's rate and the accepted refresh period; one pending
  request per job, newest wins; no priority.
- Ask: the accepted refresh period per highlight; the derivation of 8.

F10 The TCP line's reason is a speed advantage that is unverified.
- Wrong: section 11 says so; the line is kept as the only channel while the reliability rule is
  absent.
- Matters: a channel chosen for milliseconds loses seconds on a half-open socket.
- Breaks: SK6 decided the line; the benchmark it cites was not found in the document.
- Fix: find or redo the measurement; state the reliability rule beside it.
- Ask: if the measurement is not found, does SK6 stand?

F5 Two voice workers may be one. (uncertain)
- Wrong: a /tts POST likely returns before the phone finishes speaking; one worker could POST
  and then speak on the laptop, both in order.
- Matters: one thread and one FIFO fewer; the phone voice runs ahead of the laptop voice.
- Breaks: KISS; section 3 ("the voice workers, two"); SK6 decided both voices speak every
  sentence, not two threads.
- Fix: measure the /tts POST's return time; one worker if it returns in under 100 ms.
- Ask: may the phone voice run ahead of the laptop voice?

### LOW
F8 The keyboard hook's reason is unstated.
- Wrong: section 2 lists the hook; cv2.waitKey already returns keys when the window has focus.
- Matters: a process and a ROS topic for a need the document does not state.
- Breaks: the check "alternatives named".
- Fix: one line: keys must work without window focus, hence a global hook.
- Ask: must keys work without window focus?

F11 Perf may be telemetry's timestamps. (uncertain)
- Wrong: section 7 keeps two recorders; perf records (start, end) and telemetry records every
  turn and job; a turn's E2E is derivable from telemetry's timestamps.
- Matters: one recorder fewer; one less thing that must be flushed on die().
- Breaks: KISS; PRF2 and TEL1 keep both and are not overruled here.
- Fix: none proposed; the question only.
- Ask: does perf carry anything telemetry cannot?

## Assumptions in the document that are not proven facts
| assumption (section) | status |
|---|---|
| 8 vision results per s (8) | false: 1.6 to 2.4 passes per s measured |
| the phone app is a supervisor child (2) | false: it runs on the phone |
| SAM3 dies on OOM (9) | unverified; torch raises, the server loop decides |
| the TCP line is faster (2, 11) | unverified, stated as open |
| the 33 ms frame holds with the draw and sixteen threads (3, 8) | unverified; worst frames 40 to 74 ms with no overlays |
| under one message per frame (4) | derived from rates; a held key's repeat rate unmeasured |
| a phone request ends in 3 s (8) | the read timeout; the connect phase on a half-open WiFi is unverified |
| the counts make any process safe to hold a slot (6) | the measurement proved inc and dec, not the protocol |
| each child has a graceful stop (2) | plausible for SIGTERM; unverified for the gstreamer receiver and llama-server |
| a pipeline step is a pure function (10) | the plan calls Gemma; the route is pure except the plan |

## Questions for the owner
1. Does the phone app run /c/stop while a /c/fly is in flight? (F6)
2. Zero-copy holds with counts, or a copy with a sequence per slot? (F1)
3. Given 3 ms per pass, does T6 stand? (F2)
4. Confirm the SAM3 server exits on OOM. (F12)
5. Which of the four unmeasured forces may be measured on the mock? (F13)
6. Is a blocking wait per child "event-driven" under SK3 point 4? (F4)
7. Why is the gstreamer receiver a separate process? (F7)
8. The accepted refresh period per highlight; the derivation of 8? (F9)
9. If the TCP measurement is not found, does SK6 stand? (F10)
10. May the phone voice run ahead of the laptop voice? (F5)
11. Must keys work without window focus? (F8)
12. Does perf carry anything telemetry cannot? (F11)
