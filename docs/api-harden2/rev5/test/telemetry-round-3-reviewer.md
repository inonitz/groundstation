# telemetry (rev5), round 3: the check of the revision after round 2 (2026-10-12)

Scope: telemetry.md, telemetry.h, telemetry.html after telemetry-round-2-agent.md.
New measurement: m4.py in the session scratchpad, a literal simulation of the header's stall rule.
No new web sources.

## The landing check, rounds 1 and 2
- Landed in full: every round 1 finding; R2-3, R2-6, R2-7, R2-8, R2-11.
- R2-1, partly: the enqueue time of the first pending record was dropped from the rule. See R3-1.
- R2-5, partly: the one-line turn kinds contradict the "ended" key list. See R3-2.
- R2-2, R2-4, R2-9, R2-10: landed in the document and the header, not in the drawing. See R3-4.

## Findings

**R3-1. The stall rule as written kills the app on the first record after any 5 s quiet stretch.** (critical)
- Claim: the header says "stalled = work pending and no finished write for kTelemetryStallSeconds". After a quiet stretch, the last finished write is old.
- Claim: the main thread records a turn while it drains the queue (step 1). It asks Stalled beside the status rows (step 2), microseconds later. One record is pending; the last finished write is over 5 s old. Stalled is true; the app dies, hand-over first.
- Why it matters: quiet stretches are the normal case: a turn every 2 s at most, often minutes apart. This is a mid-flight death on the first command after a pause.
- Evidence: measured: m4.py runs the header's rule literally. The writer idle for 6 s, one turn put, Stalled asked at once: the header's rule returns True.
- Evidence: the same script with the round 2 proposal returns False. The rule measures from the later of the last finished write and the moment work became pending.
- Change: the producers set `pending_since = now` under the queue's lock when queued equals written at the put. Stalled = queued > written and now - max(last_finished, pending_since) > the limit.
- Change: in the C contract the subtraction is unsigned. A time stored after the caller read `now` wraps around. Compare `now > ref + limit`, never `now - ref > limit`.
- Change: the test: idle 6 s, one record, Stalled at once is false.

**R3-2. A turn that ends at its decision writes one "ended" line, and that line has no decision keys.** (high)
- Claim: the header says a kind that ends at the decision "writes one line, phase ended". The "ended" key list is k, seq, phase, ended, status, refused, spoken.
- Claim: an emergency, a reject or a clear therefore records no heard text, no kind, no reject reason, no input, no clip. The stop, the most important turn, loses its transcript.
- Claim: which kinds end at the decision is listed in a code comment only ("emergency, reject, clear"). Manual, auto, empty and planner_failed are not placed.
- Change, recommended: every turn writes both lines, always. The "ended" line follows at once for a kind that ends at its decision. One reader rule, no per-kind table, one extra line per stop or reject.
- Change: m_rejectReason still says "why a reject or a drop". A drop is an event only now; delete "or a drop".

**R3-3. The "stop_reply" event has no path to the main thread in the design document.** (medium)
- Claim: RecordEvent is main thread only. The stop's reply arrives on the emergency thread.
- Claim: design section 3: the emergency thread "sends one POST and sleeps again". Section 4 lists five message kinds; none carries the stop's reply.
- Why it matters: the emergency budget, command to action under 1 s (section 8), can be checked in a replay only with this event. Perf's PERF_EMERGENCY times it; telemetry cannot say whether it succeeded.
- Change: the emergency thread posts a PlatformReply for the stop, or a sixth message kind. That is a design-document change; it belongs on the owner's list (see the open items).

**R3-4. The drawing disagrees with the document and the header in five places.** (medium)
- "an hour of stall holds 7 MB": the document now says at most 5 s of records ever wait.
- "Destroy: the end event, drain, join": no timeout, no die past it (R2-2).
- "die(): the die event, the sentinel, a join": no direct append when the writer itself failed (R2-4).
- The low-water mark and the "disk_low" event are absent; the bottom line names only the 6 GB floor (R2-9).
- The RecordEvent box lists no "disk_low"; the header's table has it.
- In the document and the header, also: the state line still says "revised after round 1"; the `@kTelemetryMinFreeGiB` comment sits above the vocabulary block, away from its enum; kTelemetryLowFreeGiB, kTelemetryStallSeconds and kTelemetryFreeCheckEvery have no comment.

**R3-5. Nobody creates asr_clips/ any more.** (medium)
- Claim: today SessionLog makes `asr_clips/` at start (session.py, `os.makedirs(self.clips_dir)`). The revision removes the clip claim; TelemetryCreate names only the session and perception folders.
- Claim: the turn line still says `audio_clip` is "asr_clips/<name>". The ASR node's WavWriter does not create folders; with no folder, `wavman.open` fails silently and no clip is ever written.
- Change: TelemetryCreate makes and fsyncs `asr_clips/`, since the record names that path. The supervisor passes the same path to the ASR node. A test checks the folder exists after Create.

**R3-6. The header hardcodes values that config/ must own, and one must equal another module's value.** (medium)
- Claim: the project rule: "config/ is the one source of every value". The header's enum fixes the JPEG quality, the stall limit, both free-space marks and the check interval. Open point 6 says "in config".
- Claim: kTelemetryMasksPerFrame is 3 because perception masks at most mask_k = 3 detections (perception2/engine.py). A 4th mask dies as "our bug". Raising mask_k in config would then crash the app.
- Change: the Python mapping states that each constant is a config value, read once at Create. The masks per frame is the perception's mask limit, the same config entry, not a copy.

**R3-7. The frame size is fixed for the run; the frame source may change it.** (medium)
- Claim: a pass whose frame is not Create's size dies. The frame source is "webcam, drone stream or file" (design section 3). A planned video restart after a 6 s stall (section 9) may reconnect at another size.
- Why it matters: a source change mid-run becomes a crash in the recorder, not in the video path.
- Change: carry an item to the frame-buffer and frame-source reviews: the slot geometry is fixed for a run, or a geometry change is a planned restart of the app's video path. Add it to modules/README.md's carried items.

**R3-8. Three statements elsewhere now disagree with this module.** (low)
- The approved perf die() order is "stop, manual, notify, flush, exit". Telemetry inserts its drain after the flush. The runtime module must own that order; carry it there.
- Design section 6 lists "the telemetry" as a frame-buffer reader. Telemetry never acquires a slot now; the job copies. Section 12's drawing says the same.
- Design section 4 says "telemetry(job) at an end state" and "telemetry(turn)" once. Both are now twice. Section 7 says "from any thread"; three of the four calls are main thread only.
- Change: list these for the app step (step 3), which checks every interface against the sketch.

**R3-9. The open points need two splits and one addition to meet MOD2.** (low)
- Point 7 holds four decisions: the copy on the caller, JPEG at 95, masks as PNGs, a mask as 0 or nonzero. It has no "On no". Split it, one decision each, each with its "On no".
- Point 1 holds two decisions: the main thread never waits; a stall is "no progress for 5 s". The owner may accept one and not the other. Split it.
- Missing: the emergency thread's reply message (R3-3). It changes the design document, so the owner rules on it.
- The rest are understandable from the header plus the point's own text.

**R3-10. The tests miss the faults of this round.** (low)
- Missing: the first record after a 6 s idle is not a stall (R3-1).
- Missing: a stop, a reject and a clear each record heard, kind and input (R3-2).
- Missing: under the low-water mark the writer writes one "disk_low" event (R2-9 has no test).
- Missing: asr_clips/ exists after Create (R3-5).

## The items open for the owner, in my words
1. A stalled disk counts as a broken disk: the app dies after 5 s with no progress, a slow disk included.
2. The main thread never waits on the record; its records queue without a bound.
3. A fourth call, RecordEvent, beyond TEL1's three calls and the accepted RecordVisionPass.
4. Two records per turn and per job, so a crash keeps the turn in flight.
5. New file keys; the replayer and show.py are rewritten in the same commit.
6. No clip rename; the ASR node publishing the clip name is a precondition of the speech-in module.
7. A 6 GB floor at start and a 2 GB low-water event during the run.
8. Below the low-water mark: stop writing frames and masks, or keep writing and die at a full disk.
9. The four format decisions of point 7, each on its own.
10. Not yet listed: the emergency thread posts its reply as a message (R3-3).

## Round 4
No full round 4 is needed. R3-1 and R3-2 are one-paragraph fixes; a check of those two diffs and their tests suffices.

## Questions for the manager agent
1. R3-2: do you accept two lines for every turn, or keep one line for some kinds with the union of the keys?
2. R3-3: is the stop's reply a PlatformReply, or a sixth message kind? Either changes design section 4.
3. R3-7: will you add the fixed frame geometry to the carried items in modules/README.md?
