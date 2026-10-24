# telemetry (rev5), round 2: the manager agent's answer (2026-10-12)

All eleven findings are accepted. Three go to the owner. The revision carries every change;
round 3 checks it.
- **R2-1** The heartbeat is replaced by progress: two atomic counters (queued, written) and
  the time of the last finished write. `TelemetryStalled(t, now)` does the arithmetic: no
  progress for 5 s with work pending. It covers a dead writer, a stuck fsync and a slow
  disk. Open point 1 is reworded: a stall is "no progress for 5 s", a slow disk included.
- **R2-2** Destroy joins with the stall limit as timeout, then dies with the reason.
- **R2-3** The listener sends "" when the newest clip name is unchanged. The exact join,
  the ASR node publishing the name, becomes a precondition of the speech-in module.
- **R2-4** On its own failed write the writer tries one direct append of the die line,
  ignores the result, then dies. die() prints the reason to stderr. The three endings are in
  the key table.
- **R2-5** The key table is explicit, one place. The folder is `<job:04d>-<kind>`. audio_clip
  is the path under the session. meta.json names its model keys. The write order: files,
  then the line. A reader skips a torn last line. The "decided" line carries the decision;
  the "ended" line carries seq, phase, ended, status, refused, spoken. A kind that ends at
  the decision writes one line, phase "ended". A drop is the event only.
- **R2-6** Telemetry fills a PerfClockLine itself with three clock reads. perf.h stays as
  approved.
- **R2-7** Each closed vocabulary is a constant table in the header; a value outside it dies.
- **R2-8** A mask is 0 or nonzero; the writer scales. A mask not at the frame's size dies.
- **R2-9** The writer checks the free space every 100 records and writes a "disk_low" event
  under a low-water mark. What happens next is the owner's (open point 8).
- **R2-10** The stale text fixed; the job sentence lists the four record kinds; the larger
  frame rule is in the header; the change-impact table added.
- **R2-11** The tests added; a script regenerates the replayer's sample session from the
  module, as the hand check of the replayer.

## Answers
1. Both: no progress for 5 s with pending work, so a slow disk that falls behind trips it.
2. Telemetry reads the clocks itself into perf's type.
3. Open for the owner, recommended: under the low-water mark stop writing frames and masks,
   announce it with the event, keep every JSON line; die at ENOSPC only if it still comes.
   A hole in the frames beats a hand-over mid-flight.
4. Yes: an item on the speech-in review as a precondition; the deduplicating listener until then.
5. Yes.
