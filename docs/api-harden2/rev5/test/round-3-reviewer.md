# perf (rev5), round 3: the check of the revised perf.md and perf.h (2026-10-12)

Checked: round-2-agent.md, perf.md (sections 1 to 6), perf.h, against rounds 1 and 2.
Measured on this machine: Python 3.12.3, pid_max 4194304.
No new web sources; the rounds 1 and 2 sources still apply.

## Landing check (task 1)
Every accepted change of rounds 1 and 2 landed, except these, each a finding below:
- R1-6: no test makes the writer's disk write fail and checks the lock is released before die() (R3-6).
- R1-20 and R1-15: no test for the GIL-off guard in PerfCreate (R3-6).
- R2-2: no test that the report lists a request with no matching pass (R3-6).
- R2-1: perf.md section 3 still says "the first cleanup of die() is the perf flush" (R3-2).
- R1-8, R2-8: the join keys landed on most stages, not on ASR, EMERGENCY and a Key message (R3-5).

## Findings

**R3-1. The E2E payload keys "start" and "end" overwrite the record's own start and end.** (high)
- Claim: PerfRecordLine has the JSON keys "start" and "end" (the timestamps). The PERF_E2E payload also has "start" (ptt, phone, transcript) and "end" (command, box). perf.h does not say whether the payload is nested or spliced into the record object.
- Why it matters: if spliced, every E2E line holds two "start" keys. JSON parsers keep the last one. The timestamp is lost, and E2E is the emergency budget's metric (section 8, under 1 s).
- Evidence: measured: `json.loads('{"stage":"PERF_E2E","start":123,"end":456,"turn":7,"start":"ptt","end":"command"}')` returns `start: 'ptt', end: 'command'`. The timestamps are gone without an error.
- Change: nest the payload under one key, for example `"p":{...}`, and say so in PerfRecordLine. Or rename the E2E keys to "from" and "to". Nesting is safer: it removes the whole class of collision. Add a test that parses an E2E line and checks both timestamps are integers.

**R3-2. The die() order is stated two ways, and the new order delays the notify.** (medium)
- Claim: perf.md section 3, last force: "the first cleanup of die() is the perf flush (section 9)". Section 4 now says the hand-over runs first. The document contradicts itself.
- Claim: the new order is stop, manual, flush, notify, exit. Design document section 9 says: the stop, then manual mode, "notify the operator, then die". The flush can take its full 1 s timeout before the operator hears anything.
- Why it matters: the operator holds the RC after the hand-over. He must know at once that the app is gone. The records are worth less than that second.
- Change: fix section 3's force. Order die() as stop, manual, notify, flush, exit. The flush is part of dying, so it follows the notify. Put this order into open point 5.

**R3-3. The Python mapping uses threading.Event, which PRF2 listed as a fault.** (medium)
- Claim: perf.md section 2 lists PRF2's bullet: "The stop goes through threading.Event, which takes a lock." Section 5 maps the writer's sleep to an Event.
- Why it matters: the owner reads his own listed fault reintroduced. The reason it is harmless is in round-1-agent.md, not in perf.md.
- Evidence: round-1-agent.md, R1-7: "The writer is not a recording thread, so PRF2's complaint does not apply to it."
- Change: one sentence in section 5 at the Event: the lock is taken only by the writer and by Destroy, never by a recording thread. Python has no atomic bool. Add it to the open points, since it departs from a listed bullet of a ruling.

**R3-4. The 33rd thread kills the app, and a kill mid-flight is a hand-over to the RC.** (medium)
- Claim: perf.md section 5: "The 33rd thread dies with the reason." die() mid-flight sends the stop and hands control to the RC (section 9).
- Why it matters: a timing tool's table limit then lands the mission. perf.md's own rule says "a timing tool must never slow the step it times".
- Evidence: the owner's rule supports dying: "Do not build recovery for a failure that does not happen." The 16-thread budget is fixed by design (section 3).
- Change: put both options to the owner. Option A: die, as written. Option B: the 33rd thread's records are dropped and counted in the drop line. The cost of B is one branch and one count. Recommendation: A at start-up, B after it, since the limit is a bug report, not a flight hazard. The owner decides.

**R3-5. The join keys stop short of the emergency path.** (medium)
- Claim: PERF_ASR carries "chars" only, no "turn". PERF_EMERGENCY carries "status" only and starts at the drain. A Key message (F5, F4) has neither a turn nor a req, yet PERF_MESSAGE requires "turn or req".
- Why it matters: the emergency budget is command to action under 1 s (section 8). Its parts are the ASR, the message wait, and the POST. Without one shared key the report cannot add them for one stop.
- Change: the turn key is assigned at the transcript's receipt and carried on PERF_ASR, PERF_MESSAGE, PERF_TURN and PERF_EMERGENCY. A Key message carries a key sequence number as "key". Or PERF_EMERGENCY starts at the transcript's receipt stamp, so it is one span by itself. The second is simpler and matches "command to action".

**R3-6. Three accepted tests are missing from section 6.** (low)
- Claim: test_die_flushes_with_a_timeout covers a blocked write. No test covers the writer's failed write: release the lock, then die() (R1-6).
- Claim: no test covers PerfCreate dying when the GIL is off (R1-15, R1-20).
- Claim: no test covers the report listing a req with no matching pass (R2-2).
- Change: add `test_writer_disk_error_releases_the_lock_then_dies`, `test_create_dies_without_the_gil`, `test_report_lists_a_request_with_no_pass`.

**R3-7. The file contract leaves three details open.** (low)
- Claim: the four line kinds carry no discriminator. The report must guess the kind from which keys exist.
- Claim: the stage name "as text" is not fixed: "PERF_FRAME" or "frame". The report's row names and V1's frame list depend on it.
- Claim: PerfClockLine's field comments are shifted. @m_monotonic describes all three clocks; @m_realtime describes the pair.
- Claim: payload units are unstated. "wait_ms" names its unit; "read", "draw", "show", "pm", "gm" do not.
- Change: each line gets a first key "k" with one of clock, thread, drop, rec. The stage text is the enum name without "PERF_", lower case. Fix the comments. State ms for every payload duration in the stage table.

**R3-8. "A ring is never reused" rests on the thread-local cache, not on the native id.** (low)
- Claim: the ring table is keyed by threading.get_native_id(). Linux recycles thread ids after pid_max. A dict lookup by native id could then return an old ring.
- Evidence: measured: 200 sequential threads got 200 distinct native ids. pid_max here is 4194304, so reuse inside one run is unlikely, not impossible.
- Change: a new thread always finds its threading.local empty. On that miss, create a new ring and append it to a list. The dict key is not needed. The test of 50 threads stays.

## Agreement check (task 2)
Apart from R3-1, R3-2 and R3-7, perf.md and perf.h agree: the 16 stages, the span and sample marks, the four line kinds, the file name, the constants (128, 104, 4096, 32).

## Ruling check (task 3)
- C.1, R7, V1, PRF1, RVW4 to RVW7, SYS1, OWN1, TEL1: no contradiction found.
- PRF2: three departures, all open points or R3-3: PerfOpen(maxEvents), allocation in Python, the Event.
- Design document section 9: R3-2 (the notify order). Sections 3, 7, 8: no contradiction.

## Open points for the owner (task 4)
perf.md's six are correct. The list is not complete. Missing:
- 7. The Event in the Python writer, against PRF2's listed bullet (R3-3).
- 8. The 33rd thread: die, or drop and count (R3-4).
- Open point 5 should carry the notify placement (R3-2).

## Round 4 (task 5)
No round 4: R3-1 is a one-line contract fix and the rest are edits; the owner's review is next.

## Questions for the manager agent
1. R3-1: nest the payload under one key, or rename the E2E keys?
2. R3-5: does PERF_EMERGENCY start at the transcript's receipt, or does a turn key join three records?
