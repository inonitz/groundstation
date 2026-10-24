# runtime (rev5), round 2: the push-back on the revised runtime.md, runtime.h and runtime.html (2026-10-16)

Scope: the revision after round 1 (runtime-round-1-agent.md), checked against round 1's twenty findings.
The header compiles (gcc -fsyntax-only -Wall -Wextra). The drawing passes the checker.
Measured: Python 3.12.3, this machine. The scripts are r2_m1.py and r2_m5.py in the session scratchpad.
The mock ran on 127.0.0.1:18079. It received only GET /status and a WebSocket open on /c/ws/echo.

## Sources
No new web sources. Round 1's sources 1 to 13 apply. The new evidence is measured (R2-M1 to R2-M5).

## What landed, and what did not
- Landed: R1-1, R1-2, R1-3, R1-4, R1-8, R1-9, R1-11, R1-14, R1-15, R1-17, R1-18, R1-19, R1-20.
- Landed with a fault found in this round: R1-4 (R2-1), R1-5 (R2-6, R2-14), R1-6 (R2-6), R1-9 (R2-3).
- Not landed, R1-5: perf.h line 128 still says "in die(): ... 1 s". The agent's answer said it would become the records cap.
- Not landed, R1-7: "the supervisor signals the group" appears nowhere in the header or the drawing. R2-5 replaces it anyway.
- Not landed, R1-10: section 6's STA1 row still reads "an atomic state, a detail replaced whole".
- Not landed, R1-12: the header says the cgroup quota must "equal" the machine's CPUs. A quota above the count is fine, so the word is "at least".
- Not landed, R1-16: section 6's forces still say "the SAM3 server also takes a stop message".

## Agreed, one line each
- The pidfd per child, selectors and the three-deadline loop: agreed. R2-M4 measured the pidfd readable 0.54 ms after the child's last instruction (median of 20; max 0.83 ms).
- The handle by value, an index plus a row pointer: agreed. The index is never reused, and the rows outlive every reader.
- One atomic reference per row: agreed. Under a free-threaded build the question cannot arise: PerfCreate already dies without the GIL.
- setpriv --pdeathsig with start_new_session: agreed.
- The relaunch delays as an open point: agreed.
- No stop-message method: agreed, on one condition. Our SAM3 server must install its own SIGINT handler that sets its stop event. The default KeyboardInterrupt arrives only after the current C call (round 1, source 1), and it is an exception in our own code.
- Each step on its own thread, joined with its cap, with a parked second Die: agreed, apart from R2-1 and R2-14.
- The notify as one direct POST /tts: agreed.
- llama-server's second SIGINT: agreed, apart from R2-6.

## Findings

**R2-1. The hand-over's thread check can never be true. Die on the emergency thread still sends nothing.** (critical)
- Claim: the revision runs each step on its own short-lived thread. The hand-over function therefore never runs on the emergency thread. Its check "am I the emergency thread" is always false.
- Claim: Die called on the emergency thread. The step thread wakes the emergency thread. That thread is busy inside Die, joining the step thread. The 1 s cap expires, and no POST leaves.
- Why it matters: this is round 1's R1-4 fault, moved one level down. RVW4's first step fails in the one case it was revised for.
- Evidence: the header, step 1: "on the emergency thread it sends the two POSTs itself, elsewhere it wakes the emergency thread". The same header: "each run on its own short-lived thread".
- Change: the hand-over always sends the stop and the manual POSTs itself, from its step thread, on its own connection. Each POST gets a timeout that fits the 1 s cap. It never goes through the emergency thread.
- Change: the phone's server already serves a second connection beside an open call (design section 3, RVW1). A duplicate stop is harmless.

**R2-2. The reaped child's pidfd stays registered. The supervisor thread then spins without end.** (critical)
- Claim: instance 2's on_exit reaps the pid. It never unregisters the pidfd from the selector, and it never closes it. launch() opens a new pidfd for every relaunch.
- Evidence (R2-M1): one reaped child, its pidfd still registered. select(timeout=1.0) returned 708,987 times in one second.
- Why it matters: after the first crash, the supervisor thread runs a busy loop forever. It takes the GIL in each turn and slows the main thread's 33 ms frame. Every relaunch also leaks one file descriptor.
- Change: on a readable pidfd, the thread first unregisters it, then reaps the child, then closes the pidfd, then applies the policy.
- Change: add test_reaped_child_leaves_no_registered_fd. It counts the loop's wakes over 1 s after a crash: at most a few.

**R2-3. The L1 warm-up cannot be a ReadyFn under a 200 ms call cap.** (high)
- Claim: today's ReadyFn for Gemma is warm_ready (gemma/server.py line 58). It calls warm_up(), which is one whole plan through the recognizer.
- Claim: a warm plan takes 489 ms alone and 1362 ms while SAM3 runs (design section 8). A cold first plan takes longer; that number is unmeasured.
- Claim: a cap on a Python callable is cooperative only. Case one: the cap holds. Then every probe fails, the child is never ready, it is stopped, three crashes follow, and the start dies. Case two: the cap does not hold. Then the supervisor thread blocks 0.5 s to over 1.4 s per probe. During that time no exit and no command is served.
- Claim: the warm-up runs the recognizer. A bug there calls Die on the supervisor thread, in the middle of a probe. That is safe only while the probe holds no lock. The header does not say so.
- Change: readiness is the server's /health answering 200, under 200 ms. The warm-up runs once after UP, on the app's start thread after SupervisorWaitUntilReady.
- Change: L1 says the row turns UP after the warm-up. Moving the warm-up changes that meaning, so it is an owner decision (question 1).
- Change: the header states that no ReadyFn runs under the launch lock.

**R2-4. on_exit has no branch for a deliberate stop. A stopped child is relaunched as a crash.** (high)
- Claim: instance 2's on_exit knows two cases: a planned restart, and a crash. SupervisorStop's child and the quit's children reach the crash branch. The policy counts a restart and schedules a relaunch after 1 s.
- Claim: the stopping flag is checked at the fork only. The rows still go RECOVERING, and the counter still grows. A laptop part stopped four times reaches the budget branch and calls Die.
- Change: each table entry gets a "stop sent" time, set when the supervisor sends the stop. on_exit checks three cases in this order. Stop sent or stopping: the row goes DOWN (FAILED when it was killed), and no policy runs. Planned: the relaunch. Otherwise: a crash.
- Change: add test_stopped_child_is_not_relaunched and test_quit_counts_no_crash.

**R2-5. The quit and Die's step 4 race on the same children.** (high)
- Claim: SupervisorDestroy's quit is running. Then Die starts, for example on an uncaught error during shutdown. Step 4 sends a second SIGINT to every child.
- Evidence (R2-M5): the mock with an open WebSocket got SIGINT, then SIGINT 0.5 s later. It exited in 0.56 s with rc 1, a forced exit. llama-server's second SIGINT is its forced exit(1) (round 1, source 9).
- Claim: two threads can reap one pid. Both see the readable pidfd.
- Evidence (R2-M2): the second waitpid raised ChildProcessError [Errno 10]. On the supervisor thread that is an uncaught error, so a second Die follows.
- Claim: the supervisor thread closes a pidfd after a reap, while step 4 polls it. Step 4 then gets EBADF, or it polls an unrelated file that reused the number.
- Change: step 4 sends SIGINT only to children whose "stop sent" time is empty (R2-4). It never reaps; it only waits until each pidfd is readable.
- Change: once the stopping flag is set, the supervisor thread neither reaps nor closes a pidfd. A pidfd is closed only under the launch lock.
- Change: every signal goes through signal.pidfd_send_signal(pidfd, sig). It targets that exact process, safe against a reused pid. No child has children, so the process group buys nothing.

**R2-6. Step 4 does not send llama-server's second SIGINT. Die is exactly when a plan is in flight.** (high)
- Claim: the header's step 4 says "each child's own stop". The drawing says "SIGINT each". Neither applies mb_secondSigint.
- Claim: in a normal shutdown, the Gemma client closes its connections first. Die has no such step. A Die mid-flight usually comes while the recognizer worker waits for a plan.
- Evidence: round 1's M9: with a request in flight, there was no exit in 30 s. The second SIGINT ended it in 2.46 s.
- Why it matters: without it, step 4 spends its whole 10 s cap, then kills llama-server. That breaks PROC2 on the most common Die path.
- Change: step 4 sends SIGINT, then 2 s later a second SIGINT to every child with mb_secondSigint that is still alive, then waits to the 10 s deadline, then kills. The header, the drawing and the matrix all state this.

**R2-7. Die inside the launch lock, and the lock's timeout, are not written.** (medium)
- Claim: "a launch past MaxProcesses is our bug: Die". The launch failure "counts as one crash". Both run in the launch command, on the supervisor thread, around the fork.
- Claim: a Die under the lock runs step 4 on the same thread. Step 4 takes the same non-reentrant lock "with a timeout". It waits the whole timeout. What step 4 does after that timeout is not written.
- Claim: a failed launch raises FileNotFoundError from Popen. Catching it needs a try. Gate item 8 says "the one try is Die's step loop". The rule (util/guarded.py, one per failure domain) needs a process-launch domain.
- Change: SupervisorLaunch checks MaxProcesses on the caller's thread, before it puts the command.
- Change: the launch failure goes through a guarded helper in util/guarded.py. The handler releases the lock before any Die.
- Change: on a lock timeout, step 4 reads the table anyway and logs one line. The parent-death signal covers a child forked in that moment.

**R2-8. SupervisorLaunch's wait has no stated bound, and one caller can deadlock it.** (medium)
- Claim: the thread serves commands between probes. The probes run one after another. Three children probing at start, at 200 ms per call, delay a launch by about 600 ms plus a 0.19 ms fork. With the L1 ReadyFn of R2-3, each probe adds 0.5 to 1.4 s.
- Claim: two launchers on two threads cannot deadlock. Each waits on its own event, and neither holds a lock.
- Claim: a launcher on the supervisor thread waits for itself forever. A ReadyFn or a policy callback could do this.
- Claim: a launcher during Die waits until the exit. The supervisor thread is inside Die, or it ignores launches once stopping is set.
- Change: the header states the bound: the probing children times 200 ms, plus the fork.
- Change: SupervisorLaunch on the supervisor thread is our bug and dies. Once stopping is set, it returns at once with a DOWN handle.

**R2-9. SupervisorStop: blocking or not, and DOWN or FAILED.** (medium)
- Claim: the header does not say whether SupervisorStop returns at once. Suppose each module's Destroy calls it and each call waits out its grace. Six Destroys in a row then take up to 60 s. Today's stop_all stops all children in parallel.
- Claim: the header says SupervisorStop leaves the row DOWN. The matrix says a killed child leaves FAILED.
- Change: SupervisorStop is a command and returns at once. SupervisorDestroy waits once, with one deadline, for every child.
- Change: a clean exit leaves DOWN; a kill leaves FAILED. The header and the matrix say the same.

**R2-10. Open point 1 leaves out what the aircraft gets. Its "on no" calls the safe path a harm.** (medium)
- Claim: the point says Ctrl+C is "the F1 quit, the graceful shutdown". It does not say whether the quit hands control to the RC when airborne.
- Claim: "on no" calls Die's hand-over "a key the operator pressed by habit". RVW4 rules the hand-over to be the safe outcome mid-flight.
- Why it matters: if the quit does not hand over, a Ctrl+C mid-flight leaves the aircraft to a closing app. The owner decides without that fact.
- Change: for each option, state what the aircraft gets: the quit (with or without a hand-over) and Die (always the hand-over first).
- Change: the open points also lack R2-3's decision: the L1 warm-up against the probe cap. Each of the five then reads: the problem, now, on "no", recommended.

**R2-11. Reaping with os.waitpid behind Popen's back leaves Popen thinking the child runs.** (low)
- Claim: instance 2 reaps with os.waitpid(p.pid, 0). Popen.returncode stays None.
- Evidence (R2-M3): five relaunches gave five "ResourceWarning: subprocess N is still running" lines. Each dropped Popen's __del__ also calls waitpid on the reaped pid, from whatever thread runs the garbage collector.
- Change: reap with p.popen.wait() once the pidfd is readable. It makes one waitpid, sets the return code, and prints nothing.

**R2-12. SupervisorWaitUntilReady's answer on RECOVERING is undefined.** (low)
- Claim: the header says it returns when the row "leaves STARTING", true on UP and false on FAILED or WAITING. A crash during start goes to RECOVERING. RECOVERING is not in the list.
- Change: it waits until UP, FAILED or WAITING. RECOVERING keeps it waiting.

**R2-13. Stale or wrong text in the revision.** (low)
- Section 6, forces: "the SAM3 server also takes a stop message" contradicts the revision (R1-16).
- Section 6, the STA1 row: "an atomic state, a detail replaced whole" contradicts the one reference (R1-10).
- Open point 4 and section 8: "a pidfd readable 3 ms after the exit". Measured (R2-M4): 0.54 ms median, 0.83 ms max.
- Instance 1 registers perf_flush_in_die and telemetry_flush. Neither exists in any header. PerfFlush has no deadline, and TelemetryFlushInDie takes a timeoutNs. The adapter to DieFn needs a home: runtime or the app.
- perf.h line 128 still says "1 s" (R1-5; question 4).
- The preflight's cgroup quota: "at least", not "equal" (R1-12).
- The drawing's step 1 repeats R2-1's emergency-thread path.

**R2-14. Perf and telemetry share one step thread. A stuck perf write takes the telemetry flush with it.** (low)
- Claim: both registered functions of step 3 run in order on one step thread. A perf write stuck in a C call never returns. The telemetry flush then never starts, and the "die" event is lost.
- Change: each registered function gets its own thread. All of a step's threads are joined against the step's one deadline. The two files are independent.

**R2-15. The supervisor thread's life is the children's life. That invariant is unwritten.** (low)
- Claim: the parent-death signal follows the forking thread (round 1, source 3). If the supervisor thread returns early, every child gets SIGTERM.
- Claim: an uncaught error on that thread is safe. threading.excepthook runs on the thread, and Die never returns. A plain return from the loop is not safe.
- Change: the header states that the thread returns only after every child is reaped. Add test_supervisor_thread_outlives_every_child.

**R2-16. DieOnAsyncioError may have no caller in rev5.** (low)
- Claim: design section 3 makes the phone listener a "TCP line only" thread. No asyncio loop appears in the rev5 design. Today only audio/asr_phone.py runs one.
- Change: keep the function only if the phone listener's review keeps asyncio. Otherwise remove it (YAGNI).

## Questions for the manager agent
1. L1 says the Gemma row turns UP after one warm-up plan. May the warm-up move after SupervisorWaitUntilReady, so that readiness is /health alone (R2-3)?
2. Does the F1 quit hand control to the RC when the aircraft is airborne? Open point 1 needs that fact (R2-10).
3. Does any rev5 module keep an asyncio loop? If not, DieOnAsyncioError goes (R2-16).
4. perf.h is approved and still says "1 s" for the flush in die(). Does perf change its comment? Or does runtime keep perf's 1 s inside the 5 s records step (R2-13)?
