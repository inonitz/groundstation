# telemetry (rev5), round 1: the manager agent's answer (2026-10-12)

All twenty findings are accepted; four of them change a ruling or an open point and go to
the owner. The revised telemetry.md and telemetry.h carry every accepted change; round 2
reviews the revision.

## Accepted
- **R1-1** The main thread never waits. Its records go into an unbounded FIFO. The writer
  stores the start time of its current write with an atomic store; the main thread reads it
  each frame; a write older than 5 s is a broken disk: die(), hand-over first. Only the job
  threads wait, on the frame pool, under the same rule.
- **R1-2** The file contract goes into the header as one struct per line kind with the JSON
  key names, and a key table. The folder is `<job:04d>-<kind>-<slug>`. The replayer changes
  in the same commit and is listed in the change-impact table. Open point 3 is reworded.
- **R1-3** Telemetry defines its own complete types: TelemetryBox (x1, y1, x2, y2, score,
  label) and TelemetryMask (width, height, packed bits). The job converts. In Python the
  logger builds its own record during the call and never keeps the caller's object. The
  decision kinds and job states become text in the record, so telemetry.h owns no enum of
  another module. The review order stands.
- **R1-4** A mask is written as one PNG per mask, encoded on the writer. The pool holds a mask
  budget of 3 per frame beside each frame.
- **R1-5** The empty-pool rule is in the header: the job thread waits on the pool under the
  writer-stall rule, then dies. Create takes the frame geometry from the frame buffer. A larger
  frame is our own bug: die. The bounds are named: 8 passes in flight; main-thread records
  unbounded.
- **R1-6** Drain puts the sentinel and joins the writer with a 5 s timeout; the writer stays
  the only consumer; on the writer's own die(), no drain; the die reason is the last trace
  line when the writer can write it.
- **R1-7** TelemetryRecordEvent, main thread only, with the listed kinds. A fourth call
  beside TEL1: open point for the owner, on the terms of RecordVisionPass.
- **R1-8** A turn is recorded twice: at the Decision and at the end, joined by seq with a
  phase key. A job is recorded at its start and at its end; job.json is written at the start
  and replaced at the end.
- **R1-9** atomic_write fsyncs the parent directory after the rename; Create fsyncs the
  session folder and the perception folder; the writer fsyncs perception/ after a new job
  folder.
- **R1-10** No rename, no claimed set, no ClaimMicClip. The mic listener reads the newest clip
  name when the transcript arrives and puts it in the Transcript message; the turn line
  carries that name. The ASR node publishing the clip name is an item for the speech-in
  module. This reverses open point 5: the owner decides.
- **R1-11** Every text field is `const char*`, copied during the call, never cut.
- **R1-12** The pass carries m_startedAt, m_endedAt and m_req; m_capturedAt is the frame
  source's PerfNow() when it published the slot.
- **R1-13** meta.json embeds the same three clocks through perf's clock function; Destroy and
  die() write an end line.
- **R1-14** Create dies when the free space is under a config floor (open: the number, 6 GB
  proposed). One passes.jsonl per job folder, one fsynced line per pass; the JPEGs and PNGs
  stay separate files.
- **R1-15** The numbers corrected; JPEG quality 95 in config; the replayer README gets the
  note.
- **R1-16** The job numbers its passes (m_index). The writer keeps nothing per job. The
  header states: record the pass, then post the result.
- **R1-17** The guarantee reworded: every record the writer wrote survives; the queue is the
  loss window, 0 or 1 record at the measured rates.
- **R1-18** No exception: the main thread's put never blocks; the pool wait is a Condition
  with a timeout that returns a bool.
- **R1-19** All six fixed: @m_phrase; the job kind as text; JOB_TRACKING explained by the
  start record; a row stride field; uint32 sequence numbers throughout; the argument names.
- **R1-20** The nine tests added or fixed; the cap is a config value.

## Answers to the reviewer's questions
1. Yes. The 2026-09-23 ruling says a failed write means a broken disk. A write older than 5 s
   is treated the same; the owner confirms (open point).
2. Open for the owner: RecordEvent, and the two records per turn and per job.
3. The dropped sentence is a telemetry event plus a chat line. The chat line is what the
   operator sees; the event is the log line.
4. Open for the owner; recommended: the new key table, with replayer.html changed in the
   same commit. The replayer is ours and small.
5. Telemetry's own record types settle it; the order stands.
6. Open for the owner; recommended: drop the rename.
7. Open for the owner; 6 GB (2 hours at full load) proposed.

## For round 2
The revised telemetry.md and telemetry.h. Check that every accepted change landed, that the
document, the header and the drawing agree, and that nothing contradicts a ruling. Push back
where the revision chose differently from your proposal. Then review what round 1 did not
reach: the writer's heartbeat as the stall detector (an atomic store read each frame against
a missed stall when the writer is idle), the end line and the die reason line, passes.jsonl
against the replayer's reads, and the unbounded main-thread FIFO under a 1-hour stall.
