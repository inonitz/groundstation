# ATAM (SEI): every force of the document as a scenario, walked through the design
Reviewed: docs/api-harden2/rev5/01-system-architecture.md and its .html drawing. Date: 2026-10-08.

## The scenarios
One row per force. Source: sections 8 and 9, the safety lines of sections 4 and 9, and section 6.
The verdicts: R = risk (a finding below), NR = non-risk, S = sensitivity point, T = tradeoff point.

| id | force (section) | stimulus | the design's path | verdict |
|---|---|---|---|---|
| S1 | a screen frame 33 ms (8) | one frame | drain, read rows, draw 720p plus views, waitKey(1) | S, R-A4 |
| S2 | a warm plan 489 / 1362 ms p50 (8) | two transcripts 1.5 s apart | the route FIFO, one worker | S, R-A6 |
| S3 | a SAM3 pass 410 ms to 1.9 s (8) | eight jobs, one refresh per s | the SAM3 priority queue | R-A5 |
| S4 | phone HTTP up to 3 s (8) | an emergency during a /c/fly | the priority queue, one worker | R-A1 |
| S5 | a laptop sentence takes seconds (8) | a say every 2 s | a FIFO per voice, no cutting | T, R-A8 |
| S6 | emergency under 1 s (8) | "stop" by F5 | whisper, ROS, trigger, queue, HTTP, aircraft | R-A1, R-A3 |
| S7 | the rates: one message per frame (8) | a held key, a burst | the bounded queue | NR, S |
| S8 | the phone dead (9) | WiFi drops 40 s | WAITING, a probe every 2 s | R-A2, R-A7 |
| S9 | a child dies (9) | the hook dies three times | restart, then die or wait | R-A9, R-A10 |
| S10 | SAM3 out of GPU memory (9) | a three-concept pass | its process dies and restarts | R-A11, R-A12 |
| S11 | the video stalls (9) | no frame for 6 s | a planned restart | R-A13 |
| S12 | a ninth job (9); F2 (4) | F2 with eight jobs running | a stop flag per job | R-A14 |
| S13 | our own error (9) | a worker raises | die, stop all, flush perf | R-A10 |
| S14 | a real drone (9) | a wrong host | refuse a non-loopback host | R-A15 |
| S15 | STOP in manual, HALT in auto (4) | an emergency in each mode | the trigger table | R-A16 |
| S16 | 409 if manual (4) | a Decision while manual | the main thread rejects | NR |
| S17 | the reader protocol (6) | load latest, then inc | no re-check | R-A17 |
| S18 | a reader dies holding a slot (6, 9) | SAM3 OOM | no reset | R-A18 |
| S19 | the hand-off to SAM3 (6) | a detect request | who holds the slot in flight: unstated | R-A19 |
| S20 | the writer meets a held slot (6) | a long hold | skip, wait or overwrite: unstated | R-A20 |
| S21 | 32 slots (6) | eight jobs plus SAM3, draw, telemetry | no derivation | S |
| S22 | memory order of latest (6) | an ARM target | the atomics package's default order | S (uncertain) |
| S23 | 4 us per atomic op (SK5) | 50 ops per frame | 0.2 ms per frame | NR |
| S24 | bgr8 frames on ROS at 30 fps (2) | 2.7 MB per message in rclpy | the frame source thread copies | S (uncertain) |
| S25 | telemetry reads frames (6) | every frame to disk | thread and rate unstated | S (uncertain) |

## The risks (findings, ranked)
Each finding: what is wrong; why it matters; the force or rule it breaks, with the section; a
fix; the question for the owner. "(uncertain)" marks a finding I could not verify.

### CRITICAL
A1 The emergency path shares one blocking worker with the missions (S4, S6).
- Wrong: the priority queue orders waiting commands; the running /c/fly holds the one worker up
  to 3 s; the emergency waits.
- Matters: the under-1 s budget fails whenever the phone is slow, which is when a stop matters.
- Breaks: section 8 (the budget) against section 3 (HTTP blocks up to 3 s).
- Fix: an emergency sender on its own thread and connection; the main thread hands it the stop
  directly; the mission sender keeps its order.
- Ask: does the phone app run /c/stop while a /c/fly is in flight?

A2 Queued work survives an emergency and a phone outage (S4, S8).
- Wrong: no epoch, no time-to-live; the route FIFO, the in-flight plan and the command queue
  keep their items through STOP, HALT and WAITING.
- Matters: the drone moves after a stop; a backlog flies after an outage.
- Breaks: section 4 (the emergency handling) and section 9 (the phone dead).
- Fix: a turn epoch bumped by every emergency; items of an old epoch dropped and logged; a
  time-to-live per command.
- Ask: the time-to-live; what the operator hears when a queued mission is dropped.

A17 The frame reader's load-then-increment window is unguarded (S17).
- Wrong: section 6 gives inc, read, dec; a writer wrap between load and inc refills the slot.
- Matters: a wrong or torn frame to a job, SAM3, the draw or telemetry.
- Breaks: section 6 (the counts protect a held slot).
- Fix: a generation per slot; the reader re-checks after inc and retries; the writer skips a
  held slot and bumps the generation around each write.
- Ask: reader re-check, or writer never reusing the last N "latest" slots?

A19 The hand-off of a frame to SAM3 has no stated holder (S19).
- Wrong: section 6 says SAM3 increments, reads, decrements; it does not say the job holds the
  slot from the request to the reply.
- Matters: if the job only passes an index, the slot may be refilled before SAM3 increments;
  the pass runs on the wrong frame.
- Breaks: section 6, the brief's "who holds a slot and when".
- Fix: the job holds the slot (inc before the request, dec after the reply); SAM3 adds its own
  hold; the document states the two holds and their order.
- Ask: confirm the job holds the slot across the whole request.

### HIGH
A3 The emergency path has two unmeasured legs (S6).
- Wrong: whisper's time and the aircraft's response to /c/stop are not in section 8.
- Matters: the 1 s budget cannot be checked; a path with a 3 s leg and two unknown legs is not
  a budget.
- Breaks: section 8 ("measured").
- Fix: measure whisper on short utterances; measure /c/stop to a mock and to the phone; state
  the clock's start.
- Ask: where the clock starts; which path is the field emergency path.

A5 The SAM3 queue is oversubscribed by a factor of three to five (S3).
- Wrong: eight jobs at one refresh per s against 1.6 to 2.4 passes per s.
- Matters: the queue grows; the newest frame waits behind stale requests.
- Breaks: section 8 ("at most 8 vision results per s") and section 2 (the SAM3 queue).
- Fix: one pending request per job; the newest replaces the waiting one; the refresh period
  becomes 8 / 2.4 = 3.3 s at full load, stated.
- Ask: accept 3.3 s per highlight at eight jobs, or lower the job count?

A7 The TCP line has no liveness and no fallback (S8).
- Wrong: the only phone transcript channel has no heartbeat, no reconnect rule and no row.
- Matters: a half-open socket silences the phone while the HTTP probe passes.
- Breaks: section 9 (the phone's liveness is the probe); section 11 leaves only the speed open.
- Fix: a heartbeat both ways; reconnect on silence; a row for the line; the HTTP POST as
  fallback.
- Ask: the periods; whether the dropped HTTP POST returns.

A8 The voice FIFOs lag without a bound (S5).
- Wrong: no bound, no lag rule, no F1 rule for a full FIFO.
- Matters: a spoken state is false by the time it is heard; quit waits.
- Breaks: section 3 and section 8 together; SK6 decided the order, not the bound.
- Fix: a bound; refuse the newest status line at the bound; F1 cuts both FIFOs.
- Ask: the bound; which sentences may drop.

A9 The aircraft's state after an app death is undefined (S9, S13).
- Wrong: three failed restarts kill the app; die() stops processes; nothing reaches the drone.
- Matters: the drone may be airborne under our authority.
- Breaks: section 9; the kill-chain rule of CLAUDE.md.
- Fix: die() sends /c/stop on the emergency sender first, capped at 1 s; the document states
  the phone app's behavior on a dropped line.
- Ask: hover, return home, or nothing, when our line drops?

A10 A worker's exception has no designed outcome (S12, S13).
- Wrong: section 9 names only "our own error"; a job's exception stays in an unread future; a
  voice POST failure and a Gemma timeout have no outcome.
- Matters: hung views, a stuck voice, a silent recognizer.
- Breaks: section 9; the rule that each part reports through its row (section 5).
- Fix: every worker wraps its step; an error becomes a message with an end state and a row
  change; only an invariant calls die().
- Ask: which errors are "our own" and which are a part's end state?

A15 The loopback check does not prove a mock (S14). (uncertain)
- Wrong: section 9 refuses a non-loopback host; an adb port forward makes a real phone appear
  at 127.0.0.1.
- Matters: a control command reaches a real aircraft through a passing check.
- Breaks: section 9's safety line; the CLAUDE.md rule that control tools run only against the
  mock.
- Fix: the mock answers a status field "mock: true"; the client verifies it before any control
  call.
- Ask: is an adb forward ever used on this machine?

### MEDIUM
A4 The 33 ms frame is asserted, not measured for the draw (S1).
- Wrong: the 33 ms is the webcam's rate; the draw of a 720p frame with views and panes has no
  number; load_vs_frames.py saw worst frames of 40 to 74 ms with no overlays.
- Matters: a slow draw drops frames and delays every dispatch, including the emergency.
- Breaks: section 8 ("measured").
- Fix: measure the draw with eight views; state the frame budget's split.
- Ask: is a dropped frame acceptable, and how many per second?

A6 The route FIFO is sized on the plan's p50 (S2).
- Wrong: section 8 gives 489 and 1362 ms; the source gives p90 2034 ms and max 3183 ms.
- Matters: two transcripts 2 s apart stack at the tail; the second answers 3 s late.
- Breaks: section 8.
- Fix: state p50, p90 and max; state the FIFO bound and the rule at the bound.
- Ask: may a transcript be refused while a plan runs?

A11 SAM3's death on OOM is assumed (S10). (uncertain)
- Wrong: torch raises an exception on OOM; the server may live on with a fragmented GPU;
  today's sam3/*.py has no OOM handling, so the behavior is whatever the server loop does.
- Matters: a live but broken SAM3 is never restarted; every detect fails.
- Breaks: section 9 ("its process dies and restarts").
- Fix: the SAM3 server exits on an OOM by design; the row says why.
- Ask: confirm the server exits on OOM.

A12 A SAM3 restart leaves stale boxes for about 5 s (S10).
- Wrong: the load of 3.96 s plus a first detect of 0.84 s while the views keep their boxes.
- Matters: trusted boxes on a live scene.
- Breaks: section 9 with section 4.
- Fix: the row says LOADING with seconds; every view clears and shows waiting.
- Ask: do jobs survive the restart?

A13 A stalled stream shows a stale frame with no mark (S11).
- Wrong: no timestamp per slot; the draw and the jobs cannot tell a frozen frame for 6 s.
- Matters: boxes and decisions on a frozen frame.
- Breaks: section 9.
- Fix: a monotonic timestamp per slot; STALE after 0.5 s; jobs skip.
- Ask: what restarts on a stall, the gstreamer process or the source thread?

A14 F2 cannot free the pool for seconds (S12).
- Wrong: a stop flag is read only between blocking calls; a stopped job holds its thread until
  SAM3 (up to 1.9 s plus the queue wait) or a describe returns.
- Matters: after F2 a new job is refused for seconds.
- Breaks: section 3 (the 9th job is refused) against section 4 (F2 stops every job).
- Fix: a stop cancels the pending SAM3 request (the SAM3 queue drops it) and the pool counts
  only unstopped jobs against the eight.
- Ask: should a stopped job count against the eight until its call returns?

A16 STOP and HALT have no defined drone semantics (S15).
- Wrong: section 4 names them; nothing says which phone endpoint each calls and what each does
  to the queued missions.
- Matters: the builder guesses; the two modes may behave the same or wrongly.
- Breaks: section 4.
- Fix: one line each: the endpoint, the aircraft's motion, the queue's fate.
- Ask: is HALT a hover with the mission queue cleared, or paused?

A18 A dead reader's hold is never released (S18).
- Wrong: no per-slot holder and no reset at restart.
- Matters: the ring shrinks by one slot per SAM3 death; the writer's behavior at a full ring is
  unstated.
- Breaks: section 6 with section 9.
- Fix: copy-and-release readers so a leak costs little, or a holder id the supervisor clears.
- Ask: which of the two.

A20 The writer's rule at a held slot is unstated (S20).
- Wrong: section 6 says the writer "writes a slot"; not which, nor what it does at count > 0.
- Matters: skip keeps correctness; wait freezes the source; overwrite breaks the counts.
- Breaks: section 6.
- Fix: the writer takes the next slot with count 0 and generation bumped; it never waits.
- Ask: confirm skip.

## The non-risks
- NR1 The status rows (section 5): an int store per part and a read per frame; STA1's odds
  hold; the two-store detail race is cosmetic.
- NR2 The message rates (section 8) at steady state: under one message per frame; verified by
  arithmetic on the sources.
- NR3 The atomics cost (SK5): 4 us per op; fewer than 50 ops per frame; 0.2 ms.
- NR4 SAM3 in its own process (section 2): load_vs_frames.py measured 0 frames over 100 ms in
  child mode versus 8 to 10 on a thread; the choice is supported.
- NR5 Perf with no lock (section 7): a list append under the GIL is atomic.
- NR6 The 409 in manual mode (section 4): a pure check on the main thread.
- NR7 The one recognizer worker at p50 (section 3): one plan per 2 s fits 1.4 s.

## The sensitivity points
- SP1 The draw cost on the main thread (S1); every dispatch latency depends on it.
- SP2 The hold duration of a slot (S21); the number 32 is safe only if holds are short and the
  writer skips; eight jobs plus SAM3, the draw and telemetry hold at most about twelve.
- SP3 The plan's tail (S2): p90 2034 ms, max 3183 ms; the route FIFO's depth follows it.
- SP4 The GIL with sixteen threads (uncertain): the main thread's wake-up waits for the switch
  interval behind busy threads; a 2.7 MB numpy copy holds the GIL.
- SP5 rclpy deserialization of a 2.7 MB bgr8 message at 30 fps (S24, uncertain): unmeasured;
  it runs on the frame source thread under the GIL.
- SP6 Telemetry's frame rate to disk (S25, uncertain): 30 frames per s times 2.7 MB is 83 MB/s
  if every frame is written raw; the thread and the format are unstated.
- SP7 The memory order of the "latest" store (S22, uncertain): x86 is forgiving; an ARM target
  needs release and acquire; the atomics package's default order is not stated.

## The tradeoff points
- T1 One owner thread (SYS1): simplicity against the 33 ms budget carried by one thread.
- T2 Shared memory for frames (R2, R3, T6): 0.1 ms against 3.1 ms per pass through a pipe,
  bench/sam3-assessment; 3 ms saved per 410 ms pass, against the protocol of section 6.
- T3 No cutting in the voices (SK6): completeness against lag.
- T4 One platform worker with a priority queue: order against the emergency's latency.
- T5 Atomics over mutexes (SK4): speed and no deadlock against a harder-to-prove protocol.
- T6 The SAM3 process: OOM isolation and a clean frame loop against a 4.8 s blind restart and
  the cross-process protocol.
- T7 The TCP line only (SK6): a speed advantage that is unverified against a reliability rule
  that is absent.

## Questions for the owner
1. Does the phone app run /c/stop concurrently with a /c/fly in flight? (A1)
2. The command time-to-live; what the operator hears on a dropped mission? (A2)
3. The emergency clock's start; the field emergency path? (A3)
4. The frame drop tolerance per second? (A4)
5. Accept 3.3 s per highlight at eight jobs, or lower the count? (A5)
6. May a transcript be refused while a plan runs? (A6)
7. The TCP heartbeat and silence periods; does HTTP POST return? (A7)
8. The voice FIFO bound; which sentences may drop? (A8)
9. The phone app's behavior when our line drops? (A9)
10. Which errors are "our own" and which are a part's end state? (A10)
11. Does the SAM3 server exit on OOM? (A11)
12. Do jobs survive a SAM3 restart? (A12)
13. What restarts on a stall? (A13)
14. Does a stopped job count against the eight until its call returns? (A14)
15. Is an adb forward ever used on this machine? (A15)
16. HALT: hover with the queue cleared, or paused? (A16)
17. Reader re-check or writer no-reuse for the window? (A17)
18. Copy-and-release readers, or a holder id the supervisor clears? (A18)
19. Confirm the job holds the slot across the whole SAM3 request. (A19)
20. Confirm the writer skips a held slot and never waits. (A20)
