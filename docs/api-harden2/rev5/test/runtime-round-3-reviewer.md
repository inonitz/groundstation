# runtime (rev5), round 3: the landing check of runtime.md, runtime.h and runtime.html (2026-10-16)

Scope: the revision after round 2 (runtime-round-2-agent.md), and perf.h line 128.
Checked against round 1's twenty and round 2's sixteen findings, the rulings, and design sections 2, 3, 4 and 9.
The header compiles. The drawing passes the checker. No new measurement was needed.

## What landed, and what did not
- Landed in all three files: R1-1 to R1-20, apart from the stale lines below. R2-1, R2-2, R2-3, R2-4, R2-6 to R2-12, R2-14 to R2-16.
- Landed in the header only. R2-5: the header says the supervisor "stops reaping and closing once the flag is set". Instance 2 does the opposite (R3-1).
- Not landed, R2-13 and R2-3: stale lines remain (R3-4).
- Not landed, R2-13: "noted in the ledger" for the perf.h comment. No ledger line names it (R3-6).

## Findings

**R3-1. Instance 2 reaps and closes the pidfd before it checks the stopping flag, outside the lock.** (high)
- Claim: on_exit runs `selector.unregister; p.popen.wait(); os.close(p.pidfd)` first. Only then does it check `stopping`.
- Claim: the header promises the reverse: once the flag is set, the supervisor neither reaps nor closes.
- Why it matters: Die's step 4 reads the pidfds under the launch lock and polls them. The supervisor can close one in the meantime. Step 4 then polls a closed fd (EBADF), or an unrelated file that reused the number. That is R2-5's race, still open in the code the builder will copy.
- Change: on_exit takes the launch lock first. If stopping is set, it returns and leaves the pidfd to Die. Otherwise it unregisters, reaps, closes, releases the lock, and applies the policy.
- Change: the lock list in section 7 adds "the pidfd close".

**R3-2. The quit does not set the stopping flag. SupervisorDestroy can then wait forever.** (high)
- Claim: only Die sets the stopping flag (section 7: "set by Die under that lock"). The quit sends stops but leaves the flag clear.
- Claim: a relaunch may be pending at that moment: a crash in its 1, 2 or 4 s delay, or a WAITING retry. relaunch_due then forks a new child after the quit.
- Claim: the thread "returns only after every child is reaped". The new child never gets a stop. SupervisorDestroy's join never returns, and the app never exits.
- Claim: a Die during the quit skips every child with a stop sent. A llama-server stopped by the quit then gets no second SIGINT if the supervisor thread is the one inside Die. It is killed at 10 s.
- Change: the quit takes the launch lock and sets the stopping flag before it sends any stop. Pending relaunches are dropped.
- Change: step 4 sends the second SIGINT to every mb_secondSigint child still alive 2 s after its stop-sent time, whoever sent the first. A third SIGINT to llama-server is harmless.
- Change: add test_quit_drops_a_pending_relaunch.

**R3-3. The launch lock is ruled by the agent against SK4. It belongs to the owner.** (medium)
- Claim: SK4 is the owner's words: "WE ARE NOT USING MUTEXES FOR SIMPLE SHIT LIKE THIS". The round 1 answer ruled itself that SK4 "does not apply".
- Claim: the house rule says a recommendation is not a decision. The lock is a new mutex in a design the owner has not seen.
- Why it matters: the lock guards a check-then-act over a fork, the pidfd close and Die's table read. Today's R16 fix is the same lock. Without it, a fork can follow Die's read, and the orphan has only the parent-death signal.
- Change: add open point 6 in the MOD2 form. The problem: a fork after Die read the table. Now: one lock over the check, the fork, the pid store and the pidfd close; never on the row path. On "no": no lock; such an orphan gets SIGTERM from the parent-death signal at the exit. Recommended: the lock.

**R3-4. Stale lines contradict the revision.** (medium)
- Section 6, forces: "A pidfd is readable 3 ms after the exit". The header and open point 4 say 0.54 ms (measured).
- Section 8, the pidfd note: "a pidfd 3 ms after it". Same fault.
- Section 8, the probe note: "The L1 warm-up stays the llama module's ReadyFn". The header, instance 1 and open point 5 say the warm-up runs after UP.
- Section 7b, item 8: "os.waitpid(pid, 0) on the readable pidfd only". The reap is p.popen.wait() (R2-11).
- Section 6, the U6 row: "WaitingRetrySeconds". The header's name is WaitingRetryNs.
- The drawing, box D: "the cgroup quota = the machine's". The header says "at least" (R1-12).
- Change: fix the six lines. Then grep the three files for "3 ms", "waitpid(pid", "ReadyFn" and "Seconds".

**R3-5. The telemetry adapter turns an absolute deadline into a relative timeout. Written naively, it wraps.** (low)
- Claim: DieFn passes `deadlineNs`, an absolute PerfTimestamp. TelemetryFlushInDie takes `timeoutNs`, a relative duration. The one-line adapter subtracts PerfNow().
- Claim: in C with uint64_t, a step thread that starts after its deadline gets a timeout near 2^64. Gate item 5 asks that every timestamp compare be written for unsigned values.
- Claim: the perf adapter fits as is. It ignores the deadline; perf's own 1 s lock timeout lies inside the 5 s cap.
- Change: name both adapters in instance 1: `PerfFlush(ctx)`, and `TelemetryFlushInDie(ctx, reason, deadline > now ? deadline - now : 0)`.

**R3-6. Two approved modules changed in meaning, without a ledger line.** (low)
- Claim: perf.h line 128 now reads "step 3, under the records cap". perf.md still says "a 1 s timeout" (lines 22, 250, 267). The two agree, because 1 s lies inside 5 s. The round 2 answer says the change was "noted in the ledger". No ledger line names it.
- Claim: modules/README.md carries the order "the perf flush, the telemetry drain". Step 3 now runs both at once, each on its own thread.
- Change: one ledger line for the perf.h comment. The carried item in modules/README.md becomes "the perf flush and the telemetry drain, in parallel".

**R3-7. Two items for the app step, not yet carried.** (low)
- Claim: design section 3 names the emergency thread as the sender of the stop outside the platform worker. Die's hand-over is now a third sender, from a step thread.
- Claim: design section 3 says "The supervisor thread: SIGCHLD → its own queue". Open point 4 covers the word "SIGCHLD"; the "its own queue" part also changes to "a pidfd per child".
- Change: add both to the app step's list in modules/README.md.

**R3-8. Open point 1 holds two decisions.** (low)
- Claim: decision one is whether Ctrl+C means the quit or Die. Decision two is whether the quit hands control to the RC when airborne.
- Claim: the second belongs to the app step. The point says so, but it still recommends it here.
- Change: open point 1 asks only the first. Its "now" names the gap: the quit's airborne behaviour is undecided until the app step.

## The owner's items, in my words
1. Ctrl+C: the quit or Die. The quit's airborne hand-over is decided at the app step.
2. A delay of 1, 2 and 4 s before each relaunch, or relaunch at once.
3. llama-server's second SIGINT after 2 s counts as its own stop, or a kill after 10 s.
4. A pidfd per child replaces the child-exit signal that design section 2 names.
5. The L1 warm-up runs after UP, so readiness is /health alone.
6. The launch lock, a mutex outside SK4's single-integer case (R3-3). It is missing from section 4 today.
- Points 2 to 5 each read alone, with the header and a little context. Each states the problem, now, on "no", and recommended.
- Point 1 needs the split of R3-8. Point 6 needs writing.

## Round 4
Not needed: R3-1 to R3-4 are local text fixes with no new mechanism, which the manager checks by reading.

## Questions for the manager agent
1. Will the launch lock go to the owner as open point 6, given SK4's wording (R3-3)?
2. Who writes the perf.h ledger line: this module's ledger entry, or the perf module's (R3-6)?
