# flood test

Task-queue backpressure (spec-3, ROADMAP 1.4) — the SPSC queue must stay **bounded** under a
command storm and never grow without limit.

- **Scenario flag:** `--scenario-queue-overflow` (injects ONE plan of 100 `stop` actions at FMU start)
- **Queue:** `moodycamel::ReaderWriterQueue`, cap `kMaxPlanActions = 3*20 = 60`
- **The drone does NOT fly.** By design: the flood is 100 `stop`s injected before takeoff, purely
  to hammer the queue. "Never lifts off" is the expected, correct behaviour — this test is about
  queue mechanics, not flight.

## Run
```
cd scripts/test/flood
./run.sh            # sim comes up; the flood fires at FMU start (no need to wait for flight)
./filter.sh         # -> captured_flood_log.txt (this folder) + digest + PASS/FAIL
```

## Expected
- `FLOOD test: injecting 100 actions vs queue cap 60`.
- A burst of `BACKPRESSURE queue full (cap=60) -> dropped task` warnings (~37 of them).
- `qsize` peaks at **63, not 60** — and that is correct. moodycamel rounds the capacity up to
  `(next power of two of cap+1) - 1 = 63` usable slots, so ~63 enqueue and the remaining ~37 are
  rejected. The exact split (63/37 vs 60/40) is a lock-free-queue implementation detail; the test
  asserts the real invariant instead:
  - **drops > 0** — backpressure actually engaged (a regression to unbounded `enqueue` gives 0).
  - **enqueued ≤ usable cap** and **maxQsize ≤ usable cap** — the queue stayed bounded, never grew
    to hold all 100.
  - **enqueued + drops == injected** — nothing was silently lost.

## Observed (fill in per run, then hand this whole file back)
- **date:**
- **what I saw:**
- **filter digest:** (paste the ./filter.sh output)
- **my comment:**
