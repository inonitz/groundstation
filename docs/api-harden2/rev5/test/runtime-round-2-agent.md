# runtime (rev5), round 2: the manager agent's answer (2026-10-16)

All sixteen findings are accepted. Two change an owner ruling's wording and go to the owner.
- **R2-1** The hand-over sends the stop and the manual POSTs itself, from its step thread, on
  its own connection, each POST with a timeout inside the 1 s cap. The emergency thread is
  not involved. The phone's server serves a second connection beside an open call (RVW1).
- **R2-2** On a readable pidfd: unregister, reap, close, then the policy. A test counts the
  wakes after a crash.
- **R2-3** Readiness is /health under 200 ms. The warm-up runs once after UP, on the app's
  start thread. L1 said the row turns UP after the warm-up: open point for the owner. No
  ReadyFn runs under the launch lock.
- **R2-4** A "stop sent" time per entry; on_exit: stop sent or stopping, then DOWN (FAILED
  when killed) and no policy; planned, then the relaunch; otherwise a crash.
- **R2-5** Step 4 signals only children without a stop sent; it never reaps; once stopping
  is set the supervisor thread neither reaps nor closes; every signal goes through
  pidfd_send_signal; no process group.
- **R2-6** Step 4 sends the second SIGINT after 2 s to every child with mb_secondSigint still
  alive, then waits to the deadline, then kills.
- **R2-7** The MaxProcesses check on the caller's thread before the command; the launch
  failure through a guarded helper (a process-launch domain in util/guarded.py), the lock
  released before any Die; on a lock timeout step 4 reads the table anyway and logs one line.
- **R2-8** The bound stated: the probing children times 200 ms plus the fork; a launch from
  the supervisor thread is our bug and dies; once stopping, Launch returns a DOWN handle.
- **R2-9** SupervisorStop is a command and returns at once; Destroy waits once with one
  deadline for every child; a clean exit leaves DOWN, a kill FAILED, everywhere.
- **R2-10** Open point 1 states what the aircraft gets under each choice; the design document
  does not say what the F1 quit does airborne, so that fact is carried to the app step and
  named in the point. The L1 point is added.
- **R2-11** The reap is popen.wait() once the pidfd is readable.
- **R2-12** WaitUntilReady waits through RECOVERING; it returns on UP, FAILED or WAITING.
- **R2-13** The stale text fixed; the measured 0.54 ms; the DieFn adapters live in the app
  (one line each); the cgroup quota "at least"; perf.h's comment changes from "1 s" to "the
  records cap" (a comment, the approved API unchanged; noted in the ledger).
- **R2-14** Each registered function of a step on its own thread; all joined against the
  step's one deadline.
- **R2-15** The supervisor thread returns only after every child is reaped; a test.
- **R2-16** DieOnAsyncioError removed: the rev5 phone listener is a plain TCP thread.

## Answers
1. Open for the owner, with the problem stated (the 200 ms cap against a 0.5 to 1.4 s plan).
2. Unknown in the design document; carried to the app step and named in open point 1.
3. None in rev5; the function is gone.
4. perf.h's comment changes to "the records cap"; the API is untouched.
