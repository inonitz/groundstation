# telemetry (rev5), round 2: the review of the revised telemetry.md, telemetry.h and telemetry.html (2026-10-12)

Scope: the revision after round 1 (telemetry-round-1-agent.md). Same machine and versions as round 1.
New measurements: m3.py in the session scratchpad. No new web sources; round 1's list applies.

## Round 1 changes: the landing check
- Landed in full: R1-1, R1-3, R1-6, R1-7, R1-8, R1-9, R1-11, R1-12, R1-13, R1-16, R1-17, R1-18, R1-19, R1-20.
- R1-5, partly: "a larger frame is our own bug: die" is in the agent's answer only. Neither the header nor section 7 says it.
- R1-15, partly: section 8 has the new numbers. Section 6 still states the old ones (see R2-10).
- R1-10, partly: ClaimMicClip is gone from the header. Section 6 still names "the clip claim" twice (see R2-10).
- R1-2, partly: the key table exists but is incomplete (R2-5). The change impact is one sentence, not the table guidelines.md asks for.
- R1-15: the replayer README note is promised, not written. It is outside this folder; track it.

## Agreed with the revision
- The unbounded main-thread FIFO: agreed. With a working stall rule the app dies within 5 s, so the queue never holds more than 5 s of records. Drop-and-count would make the holes the record must not have. The "an hour of stall holds 7 MB" line is a non-scenario; replace it with "at most 5 s of records".
- passes.jsonl per job: agreed. It needs two rules, in R2-5: the JPEG and the masks are written before the line; a reader skips a torn last line.
- The job thread waits on the pool with its slot held: agreed. It is the same slot the job already holds through the SAM3 request (RVW3). No slot is added: the worst case stays 8 of 32.
- Telemetry's own TelemetryBox and TelemetryMask: agreed. A shared types header becomes a hub every module includes. The conversion is one list comprehension per pass.

## Findings

**R2-1. The heartbeat misses a dead writer, misses a slow disk, and the documented check fires on an idle writer.** (high)
- Claim: the heartbeat is 0 when idle. A writer thread that died between two records (an exception in cv2 or json, no die() reached) also shows 0. The queue then grows without limit, and nothing ever fires.
- Claim: the heartbeat ages per record only. A degraded disk that takes 1 s per record never trips 5 s. The backlog grows by 3 records a second, unseen.
- Claim: instance 1 reads the heartbeat twice: `now - telemetry_write_started_at(t) > STALL_NS and ...started_at != 0`. First read 0: `now - 0` exceeds the limit. Second read: the writer just began a write, nonzero. The app dies on an idle disk.
- Claim: in the C contract PerfTimestamp is unsigned. `now` is read at the frame's start; a write that starts after it gives `now - startedAt` a huge wrap-around value. A false stall again.
- Why it matters: the stall rule is the only guard left after R1-1 made the queue unbounded. A miss means an unbounded queue; a false positive means a mid-flight death and hand-over (RVW4).
- Change: detect lack of progress, not a busy writer. The logger keeps two atomic counters, records queued and records written, and the time of the last write that finished.
- Change: a stall is "queued > written, and the oldest of (the last finished write, the first unwritten enqueue) is over 5 s old". It covers the dead writer, the stuck fsync and the slow disk.
- Change: one call, `bool TelemetryStalled(const TelemetryLogger* t, PerfTimestamp now)`, reads each value once. The app does not implement the arithmetic. A test drives each of the four cases above.

**R2-2. TelemetryDestroy joins with no timeout; on a stalled disk the app hangs at quit and nothing detects it.** (high)
- Claim: Destroy "writes the end event, puts the stop sentinel, joins, closes". The join has no timeout.
- Claim: the main thread calls Destroy, and the main thread is the only stall detector. Blocked in join, it never reads the heartbeat. A writer stuck in fsync hangs the process forever.
- Why it matters: F1 quit can come while the drone is still in the air. A hung app holds the virtual-stick authority; the documented kill is then the phone's toggle or the aircraft's power button.
- Change: Destroy joins with the stall limit as its timeout. Past it, Destroy calls die() with "the session disk stalled at shutdown", which hands over first (RVW4).

**R2-3. "The newest clip at receipt" attaches the wrong clip when no clip was written for this transcript.** (high)
- Claim: the ASR node writes a clip only with --record, and only when `wavman.open` succeeds (asr_node.cpp, after line 234). It publishes the transcript either way.
- Claim: with no claimed set, the newest clip is then the previous turn's. The listener attaches it to this turn. Two turns point at one audio file.
- Why it matters: a wrong clip is worse than no clip. The owner labels recordings by hand against the clips (memory: the owner's labels are the reference); a silently shifted clip corrupts the dataset.
- Change, minimum: the listener keeps the last name it handed out. It sends "" when the newest name is unchanged. The test: two transcripts, one clip; the second turn gets "".
- Change, exact: the ASR node publishes the clip name with the transcript. Make it a precondition of the speech-in module, not a later item. The heuristic stays only until then.

**R2-4. The die line is never written for the deaths telemetry itself causes.** (medium)
- Claim: when the writer's own write fails, Drain is a no-op, so no die line. When the disk stalls, Drain's die event queues behind the stuck write; the 5 s join expires; no die line.
- Claim: the die line therefore exists only for deaths unrelated to the disk. A replay of a disk death looks exactly like a SIGKILL: no end line, no die line.
- Why it matters: the reason is the first thing a post-mortem needs. The record's own failure is the case the record cannot tell.
- Change: on a failed write, the writer attempts one direct append of the die line to trace.jsonl before it calls die(). It ignores the result; it never recurses. A full disk often still accepts a 200-byte append into a file's last block.
- Change: die() always prints the reason to stderr, which the session's process log keeps. The key table defines the three endings: an end line (clean), a die line (our death), neither (killed, or the disk death above).

**R2-5. The key table is incomplete and the two turn lines are ambiguous.** (medium)
- Claim: the comment says the turn keys are "TurnData's names without m_". The list then differs: `started` for m_startedAt, `mission` for m_missionJson, `reject`, `status`, `job`. The table must be the one place; delete the rule.
- Claim: the replayer cannot compute a job's folder. The turn line has `job`; the folder is `<job:04d>-<kind>-<slug>`. The slug of a Hebrew phrase is empty (measured: today's `_slug("מה אתה רואה")` returns ""). The describe question may be Hebrew. Put the folder name in the turn line and in job.json, or name the folder `<job:04d>-<kind>` only.
- Claim: `audio_clip` is "the ASR clip's file name". The replayer resolves it relative to the session (replayer.html, `urlFor(u.audio_clip)`). State that it is the path under the session, `asr_clips/<name>`.
- Claim: `meta.json` has `"models":{...}`. The keys are unnamed; the replayer shows them.
- Claim: the write order is unstated. The JPEG and the mask PNGs must be written before the passes.jsonl line that names them. A reader skips a torn last line in trace.jsonl and passes.jsonl.
- Claim: the two turn lines repeat every field. Which line wins when they differ is undefined. Which kinds get two lines is undefined: an emergency, a reject, a clear end at once.
- Claim: a dropped sentence is written twice: TurnData kind "dropped" and the event "sentence_dropped". One fact, two records.
- Change: the "decided" line carries the decision fields; the "ended" line carries seq, phase, ended, status, refused, spoken only. Kinds that end at the decision write one line with phase "ended". A drop is the event only; the turn's ended line has kind "dropped" removed from the list.

**R2-6. meta.json "through perf's clock function": the approved perf.h has no such function.** (medium)
- Claim: perf.h exposes the PerfClockLine type only. PerfCreate reads the clocks internally. Telemetry cannot call it.
- Why it matters: the claim needs a change to an approved header, or it is false. Either is the owner's call.
- Change, recommended: telemetry fills a PerfClockLine itself, three clock reads back to back, with the same type. It depends on perf's type, not on its internals. The alternative, `PerfClockLine PerfReadClocks(void)` in perf.h, reopens an approved module.

**R2-7. Kinds and states as free text lose the one check enums gave, with nothing in its place.** (medium)
- Claim: m_kind, m_step, m_state, m_phase, m_input and the event kinds are `const char*`. A typo ("count-frame", "Cleared") reaches the disk silently. The replayer matches exact strings.
- Claim: the reason given, "telemetry.h holds no enum of another module", does not apply. These strings are the file's vocabulary. The file contract is telemetry's.
- Change: the header lists each closed vocabulary as constants, `extern const char* const kTelemetryKinds[]`, one table per field. RecordX dies when a value is not in its table (our own bug, RVW4). A test writes every value of every table.

**R2-8. The mask contract "0 or 255" costs 35 times the copy, and a mask at another size overflows the pool.** (medium)
- Claim: SAM3's masks today are numpy bool arrays: one byte per pixel, 0 or 1. The contract asks for 0 or 255. The job thread must scale every mask during the call.
- Evidence: measured: bool to uint8 times 255, 0.56 ms per 720p mask; a copy of the bool array's uint8 view, 0.016 ms. Three masks: 1.7 ms against 0.05 ms, on the job thread.
- Claim: TelemetryMask carries its own width and height. The pool's mask budget is sized by the frame. A mask larger than the frame is undefined.
- Change: `@m_bits`: 0 or nonzero. The writer scales when it encodes the PNG. A mask whose size is not the frame's is our own bug: die, stated in the header.

**R2-9. The free-space floor is checked once, at Create; a long run on a shared disk still dies mid-flight.** (medium)
- Claim: sessions accumulate; nothing deletes them. Other writers share the disk: the ASR clips (16 kHz float, about 64 KB per second of speech), the perf files, the child processes' logs.
- Claim: start with 6.1 GB free; two hours at full load later, ENOSPC; a crash and a hand-over mid-flight. The floor only moved the death later.
- Evidence: measured: `os.statvfs` costs 2 us. A check per record is free.
- Change: the writer checks the free space every 100 records. Under a low-water mark, it writes a "disk_low" event. What happens next is the owner's: keep going and die at ENOSPC, or stop writing frames and keep the JSON. The 2026-09-23 ruling allows no status row, so the operator never sees the event. See question 3.

**R2-10. Stale text contradicts the revision.** (low)
- Section 6, forces: "A memcpy of it: 0.18 ms. A JPEG encode: 2.6 ms, 288 KB ... A PNG encode: 23 ms, 1.3 MB." Section 8 and the remeasured bullet say otherwise. Keep one set.
- Section 6, forces: "The records come from the main thread (turns, job ends, the clip claim)". The claim is gone; the events are missing.
- Section 6, rulings: the TEL1 row says "RecordVisionPass and ClaimMicClip added". The R26, R27 row says "the clip claim by input kind".
- Section 1: the job sentence omits the events. It now needs "and", which the template says means a split; reword as "every turn, pass, job and event".
- Section 7 and the header: R1-5's "a larger frame is our own bug: die" is missing.
- Section 9: the change impact is a sentence. guidelines.md asks for a table: change, behavior touched, breaks it, test impact.

**R2-11. The test list misses the cases this revision introduced.** (medium)
- Missing: a dead writer and a slow writer are both detected; an idle writer never is (R2-1).
- Missing: Destroy with a stuck writer returns within the limit and dies (R2-2).
- Missing: two transcripts, one clip: the second turn gets no clip (R2-3).
- Missing: the writer's own failed write leaves a die line when the disk allows it (R2-4).
- Missing: a torn last line in trace.jsonl and passes.jsonl is skipped; a passes line never names a missing JPEG (R2-5).
- Missing: a value outside a vocabulary table dies (R2-7).
- Gap: `test_replayer_key_table_reads_a_written_session` tests a Python reader, not replayer.html. No JavaScript runtime is installed here (`which node` finds nothing). The JS can drift from the header unseen. A script that regenerates the replayer's sample session from the module would let the owner check the replayer by hand in one step.
- Gap: the SIGKILL case: kill the process mid-pass; every line already written parses, and no end or die line exists.

## Questions for the manager agent
1. R2-1 replaces the heartbeat with progress counters. Does the owner's open point 1 ("a stall is a broken disk") then cover a slow disk too, or only a stopped one?
2. R2-6: does telemetry read the three clocks itself, or does perf.h, approved, gain a clock function?
3. R2-9: below a low-water mark, should the record stop writing frames (a hole, announced by an event), or keep writing and die at ENOSPC? The 2026-09-23 ruling and "no holes" pull in opposite directions here.
4. R2-3: will the speech-in module make the clip name part of the transcript message? Until then, is the deduplicating listener acceptable?
5. Should a regenerated sample session be the replayer's contract check, given no JavaScript runtime in the container?
