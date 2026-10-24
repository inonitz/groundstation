# Design-document checks (Google): trade-offs, alternatives, cross-cutting concerns, design versus manual
Reviewed: docs/api-harden2/rev5/01-system-architecture.md and its .html drawing. Date: 2026-10-08.

## The four checks, in one table
| check | verdict | where |
|---|---|---|
| trade-offs stated | partly: rulings are cited (SK4, SK5, SK6, STA1), their costs are not | sections 3, 6, 10 |
| alternatives named | no: not one rejected option appears in the document | every section |
| errors present | thin: processes yes (section 9), workers and queues no | sections 4, 9 |
| timing present | p50 only; two legs of the emergency path missing | section 8 |
| safety present | one line (section 9); the aircraft after an app death is absent | sections 4, 9 |
| observability present | rows and a chat line; no depths, no frame age | sections 5, 7 |
| design, not a manual | section 12 is a drawing inventory with path coordinates, half the file | section 12 |

## Findings (ranked)
Each finding: what is wrong; why it matters; the force or rule it breaks, with the section; a
fix; the question for the owner. "(uncertain)" marks a finding I could not verify.

### CRITICAL
D1 Safety is a cross-cutting concern the document does not carry.
- Wrong: section 9 has one safety line (the loopback refusal); nothing on the aircraft after an
  app death, on an emergency's effect on queued work, on STOP versus HALT, on the emergency
  path's own thread and budget legs.
- Matters: the headers will be written from this document; what it omits is built by guess.
- Breaks: the review brief's cross-cutting list (errors, timing, safety, observability); the
  kill-chain rule of CLAUDE.md.
- Fix: a "Safety" section: the kill chain, the epoch rule, the emergency sender, the legs of
  the budget with their numbers, the aircraft's state on every death.
- Ask: may the review's safety findings (pre-mortem PM-1, PM-2, PM-6) become that section?

D2 The phone app is listed as a child of the supervisor.
- Wrong: section 2 says six processes "every one created, watched and destroyed by the app's
  supervisor" and lists "the phone app, or its mock"; the real phone app runs on the phone and
  is not a child; SIGCHLD never arrives for it.
- Matters: the restart policy of section 9 ("a phone part waits for the user") cannot be driven
  by SIGCHLD; the drawing's OS line is wrong for one box.
- Breaks: section 2 against section 9; the drawing's "All six are created ... by the
  supervisor".
- Fix: five children plus the mock when CONTROL=mock; the phone app's liveness is the probe of
  section 9, stated as such.
- Ask: none; a correction.

### HIGH
D3 No alternative is named anywhere.
- Wrong: the sketch and the ledger hold the rejected options (hazard pointers, a shared counter
  with a mutex, a process-event message, REST for transcripts, a pipe for frames, a scheduler);
  the document names none.
- Matters: a reader cannot judge a choice without its rejected rival; the document must stand
  alone (guidelines, result documents).
- Breaks: the check "alternatives named" in sections 3, 6 and 9, where each choice stands
  without its rival; guidelines "Result documents".
- Fix: one "rejected" line per decision with the number or ruling that rejected it.
- Ask: may the ledger rows be quoted inline, or only cited?

D4 Trade-offs are stated as rulings without their costs.
- Wrong: "Atomics over mutexes (SK4)", "no cutting", "the TCP line only", "one slot" carry no
  cost line.
- Matters: the owner ruled on the benefit; the cost is what the field pays.
- Breaks: the check "trade-offs stated" in sections 3, 6 and 10.
- Fix: a cost per ruling: no cutting means the laptop voice lags N sentences times seconds;
  the TCP line only means no transcript on a half-open socket; one slot means a plan waits
  behind describes.
- Ask: none; a rewrite.

D5 Timing shows p50 only and misses two legs.
- Wrong: section 8 gives 489 and 1362 ms for a plan; the source gives p90 2034 ms and max
  3183 ms; whisper and the describe chat have no row; the draw has no row.
- Matters: queues and budgets are sized by tails, not medians.
- Breaks: section 8 ("measured").
- Fix: p50, p90 and max per step; rows for whisper, describe, draw and the aircraft's stop.
- Ask: which of the missing numbers may be measured on the mock, and which need the phone?

D6 Errors are designed for processes only.
- Wrong: section 9 covers a dead child, the phone, SAM3's memory, the stream, a ninth job and
  "our own error"; a worker's exception, a Gemma timeout, a voice POST failure, a full queue
  and a failed shared-memory attach have no outcome.
- Matters: an unhandled worker error is silent; the owner's rule is die or a status, never a
  swallow.
- Breaks: the check "errors present"; guidelines "Errors".
- Fix: a table, one row per worker and per queue: the failure, the message or row it becomes.
- Ask: which failures are "our own error"?

D7 The drawing omits the readers of the frame buffer and every line of telemetry and perf.
- Wrong: three shared-memory paths exist: the legend, the source to the buffer, SAM3 to the
  buffer; the draw, the jobs and telemetry read the buffer with no line; telemetry and perf
  have no line at all.
- Matters: the owner's rule for diagrams is every queue, thread and hand-off, not the boxes.
- Breaks: section 12 (the inventory "every line"); guidelines "Docs", the owner 2026-09-22.
- Fix: a line from the buffer to the main thread, the pool and telemetry; a line into telemetry
  and perf from the main thread and the workers, or a stated convention that in-process reads
  are implied.
- Ask: implied lines or drawn lines?

### MEDIUM
D8 The frame buffer section is five lines for the one cross-process protocol.
- Wrong: section 6 has no slot size, no slot choice rule, no generation or timestamp, no
  hand-off owner, no cleanup, no memory order, no invariant.
- Matters: the headers for the buffer and the SAM3 server will be written from five lines.
- Breaks: the check "design, not a manual" in reverse: it is neither.
- Fix: a protocol section: the state per slot; the writer's steps; the reader's steps; the
  invariant "a slot with count above zero is never written"; the sizes.
- Ask: the frame size and format the buffer must hold (720p bgr8, 2.7 MB, or 1080p).

D9 Observability stops at the rows.
- Wrong: sections 5 and 7 give rows, a chat line, telemetry and perf; no queue depth, no held
  slot count, no frame age is recorded.
- Matters: a lagging system cannot be diagnosed; perf shows the symptom, nothing shows the
  queue.
- Breaks: the check "observability present".
- Fix: a depths row written by the main thread each frame: the message queue, the route FIFO,
  the command queue, each voice FIFO, the SAM3 queue, the held slots, the latest frame's age.
- Ask: in the rows, in perf, or both?

D10 Section 12 is an implementation artifact, not design.
- Wrong: lines 110 to 244 of 244 are the drawing's texts and SVG path coordinates.
- Matters: the design is half the file; the inventory belongs to the compare tool.
- Breaks: the check "design versus manual".
- Fix: the inventory in its own file next to the drawing; the document keeps the design.
- Ask: keep the inventory in the document for the compare tool, or move it?

D11 No acceptance tests and no non-goals.
- Wrong: nothing says how the design is proven: no stress test for the buffer, no measured
  emergency path, no soak for the queues; nothing says what the system will not do.
- Matters: the owner's rules: real tests over mocks; tests written with the module.
- Breaks: guidelines "Tests"; sections 8 and 9 list forces with no acceptance for any.
- Fix: one acceptance line per force: two processes, eight readers, 30 fps, ten minutes, zero
  torn frames; the emergency path under 1 s on the mock, measured; a non-goals list.
- Ask: which forces get a measured acceptance before the headers are approved?

D12 The document contradicts itself in four places.
- Wrong: section 10 says "Shared memory is the frame buffer and the status rows only" while
  section 5 and STA1 drop "shared" for the rows; section 10 says "Atomics over mutexes" while
  the message queue and every FIFO are mutex queues; section 3 says "three producer threads"
  while the drawing says "five threads, plus the job threads"; the drawing's dotted line means
  "a variable read each frame" and also the OS signal.
- Matters: a reader cannot tell which wording binds the headers.
- Breaks: the guideline "define a project term once, then use only that term".
- Fix: one wording each: the rows are per-part variables; atomics for a single integer, queues
  for messages; producers are the three listeners and the two workers plus the jobs; a seventh
  line kind for the signal.
- Ask: none; a rewrite.

### LOW
D13 Numbers that are config appear as literals.
- Wrong: ":8080 | :8079", ":18090", "32 slots", "8", "6 s", "2 s", "3 restarts", "0.5-1.5 s"
  appear without their config key.
- Matters: config is the one source of every value; a literal in the design drifts from it.
- Breaks: guidelines "Architecture: config/ is the one source of every value"; the literals
  sit in sections 2, 3, 6 and 9.
- Fix: the config key beside each number, or a table of keys at the end.
- Ask: none.

D14 Key bindings in the dispatch list are implementation detail.
- Wrong: section 4 binds F1, F2, F4, F5 inside the design of the dispatch.
- Matters: a rebinding changes the design document.
- Breaks: the check "design versus manual".
- Fix: name the actions (quit, stop all jobs, manual, ASR mark) and leave the keys to config.
- Ask: none.

D15 "409" names an HTTP status for an internal rejection.
- Wrong: section 4 says "the command queue (409 if manual)".
- Matters: a reader looks for an HTTP reply that does not exist on that path.
- Breaks: the guideline on plain names.
- Fix: "refused: manual mode".
- Ask: none.

## Questions for the owner
1. May the safety findings of the pre-mortem become a "Safety" section? (D1)
2. May the ledger rows be quoted inline for the alternatives? (D3)
3. Which missing timing numbers may be measured on the mock? (D5)
4. Which failures are "our own error"? (D6)
5. Drawn reader lines, or an implied-lines convention? (D7)
6. The frame size and format the buffer holds? (D8)
7. A depths row in the rows, in perf, or both? (D9)
8. Keep section 12 in the document, or move it beside the drawing? (D10)
9. Which forces get a measured acceptance before the headers? (D11)
