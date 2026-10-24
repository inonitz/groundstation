# Pre-mortem (Klein): the system fails in its first month in the field
Reviewed: docs/api-harden2/rev5/01-system-architecture.md and its .html drawing. Date: 2026-10-08.

## The story
Day 1. The app starts clean. Six processes come up. The rows go OK. The first mission flies.

Day 2. The operator says "stop". The platform worker is inside a /c/fly call. The phone's WiFi
hiccups. The call waits its 3 s timeout. The emergency sits first in the priority queue. Nobody
takes it; the one worker is busy. The drone keeps its heading for 3 s. At 2 m/s that is 6 m.

Day 4. The operator says "forward two meters" twice, then "stop". SAM3 runs, so the first plan
takes 1.4 s. The stop arrives while the second transcript waits in the route FIFO. STOP goes out
first. The recognizer finishes the second plan. The main thread turns it into a mission. The
platform worker sends /c/fly. The drone moves after the stop. Nobody spoke after "stop".

Day 6. The phone's WiFi drops for 40 s. The row says WAITING. The operator speaks four missions
to test the voice. Each mission queues. Each blocks 3 s. The phone returns. The backlog flies,
one by one, 40 s after it was spoken.

Day 8. SAM3 runs out of GPU memory on a three-concept pass. Its process dies and restarts. It
held slot 17 at death. Slot 17's count stays at 1 forever. By day 20, after thirty restarts, the
writer finds no free slot. The document does not say what the writer does then. Either the
screen freezes or a job reads a torn frame.

Day 9. A job loads "latest" = 5. Before it increments slot 5's count, it waits on the GIL behind
a 2.7 MB copy. The writer wraps the ring; 32 slots at 30 fps is 1.07 s. The writer refills slot
5. The job increments and reads a frame from the wrong second. The boxes land on the wrong
frame. The operator blames the model.

Day 11. The laptop voice speaks a sentence in 3 s. Replies, rejects and state lines come every
2 s. By the tenth minute the laptop voice is 40 s behind. The operator hears "stopped" while the
drone flies the next mission. F1 waits for both FIFOs or cuts them; the document does not say.

Day 13. The keyboard hook crashes three times in a row after a ROS daemon restart. Three failed
restarts of a laptop part kill the app. The drone hovers at 10 m. The document does not say what
the phone app does when our control line drops. The operator reaches for the RC and hopes.

Day 15. A vision job raises on a malformed describe reply. The pool stores the exception in a
future nobody reads. No VisionResult arrives. The view stays on screen. After eight such views
every new job is refused. The operator restarts the app to clear them.

Day 18. The phone roams between two access points. The TCP line goes half-open. No transcript
arrives from the phone. The HTTP probe every 2 s says OK. Nobody notices for ten minutes.

Day 21. The operator says "stop" through F5. Whisper takes about a second on a 3 s utterance
(unmeasured; the table has no ASR row). The budget was 1 s. The clock had no start point. Nobody
can say whether the budget held.

Day 24. Eight highlights run. Each asks SAM3 once a second. SAM3 serves 1.6 to 2.4 passes per
second. Its queue grows by about five requests per second. Each highlight refreshes every 3 to
5 s. The document promised 8 results per second.

Day 27. The app dies on our own error. /dev/shm keeps the segment. The next start attaches the
stale one. The SAM3 server reads frames of the old session for a minute.

Day 30. Perf shows an E2E of 4 s on one turn. Every row says OK. No queue depth is recorded. The
team guesses.

## Findings (the causes, ranked)
Each finding: what is wrong; why it matters; the force or rule it breaks, with the section; a
fix; the question for the owner. "(uncertain)" marks a finding I could not verify.

### CRITICAL
PM-1 The emergency waits behind a blocked HTTP call.
- Wrong: the one platform worker sends the emergency; a /c/fly in flight blocks it up to 3 s.
- Matters: a priority queue orders waiting items; it cannot preempt a call already running.
- Breaks: the emergency budget "command to action under 1 s" (section 8) against "HTTP blocks up
  to 3 s" (section 3); the rule "an emergency never meets the model" does not cover the phone.
- Fix: a second sender for the emergency only, its own thread and its own connection; the stop
  goes out within one frame regardless of the mission sender's state.
- Ask: does the phone app handle /c/stop while a /c/fly is in flight, or serially?

PM-2 An emergency does not cancel the work already in flight.
- Wrong: after STOP or HALT, the route FIFO, a plan inside Gemma, and the command queue keep
  their items; the next Decision becomes a mission and flies (section 4).
- Matters: the drone moves after the operator said stop; this is the Day 4 crash.
- Breaks: the emergency rule of section 4; the budget of section 8 says nothing about what
  follows the stop.
- Fix: a turn epoch owned by the main thread; an emergency increments it; a Decision, a command
  or a PlatformReply of an older epoch is dropped and logged; the command queue is cleared.
- Ask: after a stop, do pending spoken missions die silently, or get spoken back for a re-say?

PM-3 The frame buffer protocol has a window between "load latest" and "increment the count".
- Wrong: section 6 gives no step that checks the slot is still the frame the reader wanted; the
  writer may refill the slot inside that window.
- Matters: a torn or wrong frame reaches a job, SAM3, the draw or telemetry; at 30 fps the
  window closes in 1.07 s; a GIL stall of that length happens under load.
- Breaks: section 6 ("the frame source is the only writer"; the counts protect a held slot);
  the readers' correctness is the whole point of the counts.
- Fix: a generation number per slot; the writer increments it before and after a write; the
  reader does load latest, inc count, compare the generation, else dec and retry; the writer
  skips a slot with count > 0.
- Ask: who closes the window, the reader by re-checking, or the writer by never reusing a slot
  that was "latest" within the last N frames?

PM-4 A reader that dies holding a slot leaks its count forever.
- Wrong: section 9 restarts SAM3 after an OOM death; section 6 has no reset of the dead
  reader's counts; the slot stays held.
- Matters: one slot per death; the ring shrinks; after enough deaths the writer has no free
  slot; the document does not say what the writer does then.
- Breaks: section 6 ("any process may hold a slot") combined with section 9 (SAM3 dies and
  restarts).
- Fix: either readers copy the slot and release within a millisecond, so a leak costs one slot
  per death and the writer skips it; or a per-slot holder id so the supervisor clears a dead
  process's holds at restart.
- Ask: when the next slot's count is above zero, does the writer skip, wait, or overwrite?

### HIGH
PM-5 Stale missions fly when the phone returns.
- Wrong: the command queue keeps missions through the WAITING state (section 9); each blocks 3 s;
  the backlog fires in order when the phone answers again.
- Matters: the drone executes commands spoken tens of seconds ago, in a changed situation.
- Breaks: the budget of section 8 and the safety intent of section 9.
- Fix: a time-to-live on every command; the platform worker drops an expired command and
  returns PlatformReply(expired); say it.
- Ask: the time-to-live number: 2 s, 5 s?

PM-6 The aircraft's state after an app death is not designed.
- Wrong: "a laptop part kills the app" and "die with the reason, stop every process" (section 9)
  send nothing to the drone and state nothing about the phone app's behavior.
- Matters: the drone may be airborne under our virtual-stick authority when the app dies.
- Breaks: section 9's failure handling; the safety rule that the kill chain is known before
  arming (CLAUDE.md).
- Fix: die() sends /c/stop on the emergency sender before stopping the processes, with a 1 s
  cap; the document states the phone app's behavior on a dropped control line.
- Ask: what does the phone app do when our control line drops: hover, return home, or nothing?

PM-7 The TCP line has no liveness rule.
- Wrong: section 2 makes the TCP line the only transcript channel from the phone; sections 9 and
  11 give no heartbeat, no reconnect, no row for the line.
- Matters: a half-open socket after a WiFi roam loses every phone transcript silently; the HTTP
  probe passes.
- Breaks: section 9 (the phone dead is detected by a probe; the line is not probed).
- Fix: a heartbeat line both ways every N s; reconnect after M s of silence; a row for the line.
- Ask: N and M; does the HTTP POST return as the fallback when the line is down?

PM-8 A job that raises never reaches an end state.
- Wrong: section 4 ends a job only through VisionResult; section 9 names no job error; a pool
  future keeps an exception unread.
- Matters: the view hangs; the pool slot stays taken; after eight, every job is refused.
- Breaks: section 3 ("the 9th job is refused") and section 9 ("a ninth vision job: refused")
  assume the eight end.
- Fix: the job wrapper turns any exception into VisionResult(error, end state); only an
  invariant failure calls die().
- Ask: is a job's exception "our own error" (die) or a job failure (an end state and a say)?

PM-9 The ASR time is missing from the emergency budget.
- Wrong: section 8 has no whisper row; the budget "command to action under 1 s" has no start
  point.
- Matters: whisper on a 2 to 3 s utterance may eat the whole budget (uncertain, unmeasured).
- Breaks: section 8 (every force "measured").
- Fix: measure whisper on a one-word and a five-word utterance; state where the clock starts
  (F5 release, end of speech, or transcript arrival).
- Ask: which path is the field emergency path, F5 plus whisper, or the phone's own ASR?

PM-10 The voice FIFOs have no bound and no lag rule.
- Wrong: section 3 says "no cutting"; section 8 says a laptop sentence takes seconds; nothing
  bounds the FIFO or the lag.
- Matters: the laptop voice falls tens of seconds behind; a spoken state is false by the time
  it is heard; F1 behavior with a full FIFO is unstated.
- Breaks: section 3 and the owner's SK6 ruling, which decided the order, not the bound.
- Fix: a bound per FIFO; the policy at the bound (refuse the newest status line, keep replies);
  F1 cuts both FIFOs.
- Ask: the bound; may status lines be dropped under lag while replies never are?

### MEDIUM
PM-11 Eight jobs at one refresh per second exceed SAM3's measured rate.
- Wrong: section 8 states "at most 8 vision results per s"; SAM3 serves 1.6 passes per s with
  Gemma busy (bench/gemma-plan-timing) and 2.4 alone.
- Matters: the SAM3 queue grows without bound; a highlight refreshes every 3 to 5 s.
- Breaks: section 8 (a stated number that the sources contradict); section 2 (the SAM3 queue).
- Fix: one pending request per job in the SAM3 queue, the newest replaces; state the real
  refresh at full load: 8 jobs / 2.4 per s = 3.3 s.
- Ask: is 3.3 s per highlight acceptable at eight jobs, or does the job count drop?

PM-12 A plan waits behind describe chats on Gemma's one slot.
- Wrong: sections 2 and 4 send plans and describes to one slot with no order rule.
- Matters: a plan behind eight describes waits unbounded; the turn's E2E grows past the budget.
- Breaks: section 8 ("a warm plan: 489 ms") measured without describes in the queue.
- Fix: one gate in the app for every Gemma call; a plan goes first; a describe is sent only
  when no plan waits.
- Ask: the describe time, measured; may a describe ever delay a plan?

PM-13 The supervisor thread cannot receive SIGCHLD in CPython. (uncertain only in its fix)
- Wrong: section 3 draws "SIGCHLD → its own queue" into a thread; CPython runs signal handlers
  on the main thread only.
- Matters: the design as drawn cannot be built; the builder improvises on the main thread.
- Breaks: section 3 (the supervisor thread) and section 10 (a blocking step never on the main
  thread).
- Fix: a blocking wait per child on its own thread, as today's runtime/supervisor.py does
  (line 207, "blocks until the process exits; no polling"); or the handler only puts into the
  supervisor's queue.
- Ask: SK3 point 4 rejected polling; is a blocking wait per child "event-driven" enough?

PM-14 A SAM3 restart blinds every highlight for about five seconds.
- Wrong: section 9 restarts SAM3 (load 3.96 s plus a first detect 0.84 s, bench/sam3-assessment)
  while section 4 keeps the views and their boxes.
- Matters: stale boxes on a live scene; the operator trusts them.
- Breaks: section 9 and section 4 together.
- Fix: on a SAM3 death the row says LOADING with seconds; every view clears its boxes and shows
  waiting.
- Ask: do running jobs survive a SAM3 restart, or end with an error?

PM-15 A frozen stream shows stale boxes for 6 s.
- Wrong: section 6 has no timestamp per slot; the draw and the jobs cannot tell a 6 s old frame.
- Matters: the operator and the jobs act on a frozen frame until the restart of section 9.
- Breaks: section 9 ("the video stalls: a planned restart after 6 s").
- Fix: a monotonic timestamp per slot; the draw shows STALE after 0.5 s; a job skips a stale
  frame.
- Ask: the stale threshold; and what restarts, the gstreamer process or the frame source thread?

PM-16 The message queue's bound and overflow policy are unstated.
- Wrong: section 4 says "bounded" with no number and no rule at the bound.
- Matters: a blocked producer stalls a ROS spin; a dropped message may be an emergency.
- Breaks: section 4.
- Fix: the number; a producer blocks at the bound; a Transcript is never dropped.
- Ask: the number.

### LOW
PM-17 A stale shared-memory segment survives a crash.
- Wrong: section 6 names no owner of the segment's lifetime.
- Matters: the next session attaches the old segment; the SAM3 server reads old frames.
- Breaks: section 9 ("die ... stop every process") leaves the segment.
- Fix: the app unlinks and recreates the segment at start; SAM3 attaches by name afterwards.
- Ask: none; a confirmation.

PM-18 A row's state and detail are two stores.
- Wrong: section 5 says "an atomic store" of (name, state, detail); the detail string and the
  state int are two writes.
- Matters: a frame may show a new state with an old detail; STA1 accepts the odds.
- Breaks: section 5 as written; not STA1.
- Fix: write the detail before the state; say so in the document.
- Ask: none.

## Questions for the owner
1. Does the phone app process /c/stop concurrently with a /c/fly in flight? (PM-1)
2. After a STOP, do pending spoken missions die silently or get re-confirmed? (PM-2)
3. Who closes the load-then-increment window, the reader or the writer? (PM-3)
4. What does the writer do at a held slot: skip, wait, or overwrite? (PM-4)
5. The command time-to-live: 2 s, 5 s? (PM-5)
6. What does the phone app do when our control line drops? (PM-6)
7. The TCP heartbeat period and the silence limit; does HTTP POST return as fallback? (PM-7)
8. Is a job's exception "our own error" or a job's end state? (PM-8)
9. The emergency clock's start point; the field emergency path? (PM-9)
10. The voice FIFO bound; may status lines drop under lag? (PM-10)
11. Is 3.3 s per highlight at eight jobs acceptable? (PM-11)
12. May a describe ever delay a plan; the describe time? (PM-12)
13. Is a blocking wait per child "event-driven" under SK3 point 4? (PM-13)
14. Do jobs survive a SAM3 restart? (PM-14)
15. The stale-frame threshold; what restarts on a stall? (PM-15)
16. The message queue bound. (PM-16)
