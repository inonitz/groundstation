# The design review of 01-system-architecture.md: one problem per item (rewritten 2026-10-11)

The four reviews are 04-review-premortem.md, 04-review-atam.md, 04-review-design-doc-checks.md
and 04-review-first-principles.md. One agent, the four methods in order. This file merges them.
Each item below is ONE problem: what happens, why it matters, the fix the reviews propose, and
the question for the owner. The IDs in brackets point into the four files.

## CRITICAL

### 1. The stop waits behind a running mission call [PM-1, A1, F6]
What happens. The operator says "fly forward five meters". The platform worker sends the POST.
The phone takes two seconds to answer. The operator says "stop". The stop enters the command
queue, at the front. The worker is still inside the first POST. The stop leaves two seconds late.
Why it matters. The budget is one second from command to action. It fails exactly when the
phone is slow.
The fix, with your note. A second thread for emergencies only. It sleeps on an event. The main
thread wakes it with the stop. It sends its own POST. No persistent connection is kept: every
POST is its own short request, so there is nothing extra to maintain.
Question. Does the phone app serve two requests at once? If it serves one at a time, the stop
still waits inside the phone, and the fix must move to the phone side.

### 2. Sentences already in work still fly after a stop [PM-2, A2]
What happens. The operator says three things quickly: "fly forward five", "turn right", "stop".
The first sentence is inside Gemma, being planned. The second waits in the route queue. The
stop goes out at once. Then Gemma answers. The main thread receives the Decision for "fly
forward five" and sends it. The drone moves after the stop.
Why it matters. A stop must end everything that was said before it.
The fix. The main thread keeps a counter, the epoch. Every stop increments it. Every queued
sentence, every Decision and every command carries the epoch it was born in. The main thread
drops any item with an older epoch and logs it.
Question. Are the dropped sentences spoken back to the operator, or dropped silently?

### 3. Missions queued while the phone was away fly when it returns [PM-5, A2]
What happens. The phone stops answering. The operator keeps talking. Each mission waits three
seconds for a timeout. The commands pile up in the queue. The phone comes back. The whole pile
is sent in order, tens of seconds late.
Why it matters. The drone executes commands from a situation that no longer exists.
The fix. A time-to-live on every command. The worker drops an expired command and reports it.
Question. The time-to-live: two seconds, five seconds?

### 4. The frame buffer: how it works, then the first hole [PM-3, A17]
How it works today in the document. The buffer has 32 slots. The writer fills the next free
slot and then sets "latest" to that slot's number. A reader reads "latest", gets N. It
increments the count of slot N. It reads the pixels. It decrements the count. The writer skips
any slot whose count is above zero.
The hole. Between "read latest" and "increment the count" the reader can stall. The writer
refills a slot every 32 frames, about one second. If the reader stalls that long, slot N holds
a different frame when the reader increments. The reader then works on the wrong frame.
Why it matters. Rare, but silent: a wrong frame reaches a job, SAM3 or the record.
The fix. Each slot carries a sequence number. The writer bumps it on every write. The reader
re-reads it after the increment. On a mismatch it decrements and retries.

### 5. The frame buffer: the second hole, who holds the slot during a SAM3 request [A19]
What happens. The job reads "latest", gets N, and sends N to the SAM3 server. The server
increments the count of slot N when the request arrives. Between the two steps nobody holds the
slot. The writer may refill it.
The fix. The job increments the count before it sends the request and decrements after the
reply. The server then needs no count of its own.

### 6. The frame buffer: the third hole, a dead reader leaks its count [PM-4]
What happens. The SAM3 server dies while it holds slot N. The count of N stays at one. The
writer skips N forever. One slot is lost per death. The design restarts SAM3 after a death by
design, so this happens.
The fix. Either each slot records who holds it and the supervisor clears a dead process's
holds. Or readers copy the pixels and release within a millisecond, so a leak costs nothing.
Question. Which one?

### 7. The alternative to counts: copy and release [F1]
What the review found. The counts exist because readers hold a slot for a whole pass, up to
two seconds. If every reader copies the slot first, about 2.6 MB and about a millisecond
(unverified), the hold is a millisecond long. Then a sequence number per slot replaces the
counts: read the sequence, copy, re-read, retry if changed. Holes 4, 5 and 6 all disappear. The
SAM3 server copies too, and the shared atomics are not needed.
What stands. SK5 proved the atomics work. Nothing ruled "hold" over "copy".
Question. Hold with counts, or copy with a sequence?

### 8. The aircraft after the app dies [PM-6, A9]
What happens. die() prints the reason, stops every child process and exits. It sends nothing
to the drone. The drone may be airborne under our control at that moment.
The fix. die() sends /c/stop through the emergency thread first, capped at one second.
Your note, to dissect. Each die() in the design must justify itself: is the fault truly beyond
recovery? The review lists the die() reasons; the dissection is a session of its own.
Question. What does the phone app do by itself when our control line drops: hover, return
home, or nothing?

### 9. The document has no safety section [D1]
What is missing. The kill chain. The epoch rule. The emergency thread. The budget's legs with
numbers. The aircraft's state on every kind of death.
The fix. One section, "Safety", written from items 1, 2, 3 and 8.

### 10. The document lists the phone app as a child of the supervisor [D2, F12]
What is wrong. The real phone app runs on the phone. The supervisor never starts it and never
receives a child-exit signal for it. The children are five, plus the mock when CONTROL=mock.
The fix. Correct section 2 and the drawing's note.

### 11. "At most 8 vision results per second" is false [A5, F12]
What is wrong. Eight highlights at one refresh per second need eight SAM3 passes per second.
SAM3 does 1.6 to 2.4. The requests pile up in the SAM3 queue; the newest frame waits behind
stale requests.
The fix. One pending request per job; a newer frame replaces the waiting one. At eight jobs each
highlight refreshes every 3.3 seconds. The document states that number.
Question. Accept 3.3 seconds per highlight at eight jobs, or lower the job count?

## HIGH

### 12. The TCP transcript line can be half open, and nobody notices [PM-7, A7]
What happens. The WiFi roams. The socket stays open on our side but carries nothing. Every
phone transcript is lost. The HTTP probe of the phone app still passes, so the row stays UP.
Your note. Today the phone cannot know whether a transcript arrived at all. The TCP line carries
no acknowledgement. The HTTP POST carried one: the 200 reply.
The fix. A heartbeat both ways; a reconnect after silence; a status row for the line; an
acknowledgement per sentence, which the POST already gives.
Question. The heartbeat period and the silence limit. Does the POST return as the channel that
acknowledges?

### 13. A vision job that raises an exception hangs [PM-8, A10]
What happens. The job's thread dies with the exception unread. Its view stays on screen. Its
pool slot stays taken. After eight such jobs, every new job is refused.
The fix. The job body catches at its top, sends VisionResult with an error end state, and the
row changes. Only an invariant failure calls die().

### 14. A voice POST failure and a Gemma timeout have no designed outcome [A10, D6]
What happens. The phone refuses /tts: the voice worker has no rule. Gemma times out: the
recognizer worker has no rule. Both are silent.
The fix. Every worker wraps its step. A failure becomes a message with an end state and a row.
Question. Which failures are "our own error" and die, and which are a part's end state?

### 15. Whisper's time is missing from the emergency budget [PM-9, A3]
What is missing. The budget "under one second" has no row for whisper. On a short utterance
whisper may take most of the budget (unmeasured).
The fix. Measure whisper on a one-word and a five-word utterance.
Question. Where does the emergency clock start: the F5 release, the end of speech, or the
transcript's arrival?

### 16. The aircraft's response to /c/stop is unmeasured [A3, F13]
The fix. Measure it on the mock and on the phone. The phone measurement waits for the field.

### 17. The timing section shows medians only [D5]
What is wrong. A plan is listed as 489 ms. The source also holds p90 2034 ms and max 3183 ms.
Queues and budgets are sized by the tail, not the median.
The fix. p50, p90 and max per step; rows for whisper, describe, the draw and the stop.

### 18. The voice queues have no bound [PM-10, A8]
What happens. The laptop voice takes seconds per sentence. Sentences arrive faster. The queue
grows. A spoken state is false by the time it is heard. F1 with a full queue is unstated.
The fix. A bound per voice. At the bound, refuse the newest status line, never a reply. F1
cuts both queues.
Question. The bound.

### 19. The loopback check does not prove a mock [A15, uncertain]
What happens. An adb port forward makes a real phone answer at 127.0.0.1. The safety check
passes. A command reaches a real aircraft.
The fix. The mock answers "mock: true" in its status; the client checks it before any command.
Question. Is an adb port forward ever used on this machine?

### 20. The document names no rejected alternative [D3]
The fix. One "rejected" line per decision, with the ruling or the number that rejected it.

### 21. The rulings carry no cost line [D4]
Examples. "No cutting" costs a lagging laptop voice. "The TCP line only" costs a silent phone
on a half-open socket. "One slot" costs a plan that waits behind a describe.
The fix. A cost line per ruling.

### 22. The drawing omits lines [D7]
What is missing. The lines from the frame buffer to its readers: the draw, the jobs, the
record. The lines into telemetry and perf from the main thread and the workers.
Question. Draw them, or state that in-process reads are implied?

### 23. The shared-memory ring buys under one percent [F2]
What the review found. A frame through shared memory costs 0.1 ms; through a pipe 3.1 ms. A
pass costs 410 to 1900 ms. The gain is 0.2 to 0.7 percent. The cost is the whole cross-process
protocol of items 4 to 7.
What stands. Ruling T6 stands. The review only asks.
Question. Given 3 ms per pass, does T6 stand, or does SAM3 take its frame over the socket?

## MEDIUM and LOW
They stay in the four files: the stall threshold, the message queue bound, a job's stop
semantics, a describe delaying a plan, live jobs across a SAM3 restart, the gstreamer process,
keys without window focus, perf against telemetry, the place of section 12.
