# runtime (rev5), round 1: the manager agent's answer (2026-10-16)

All twenty findings are accepted; four points go to the owner. The revision carries every
change; round 2 checks it.

- **R1-1** No signal handler. One pidfd per child, opened right after the launch; the thread
  sleeps in one poll on the pidfds and the command pipe. Event-driven, one thread (SUP1's
  intent); no dependence on the main thread; no EINTR exposure. The design document says
  "SIGCHLD": carried to the app step as a wording change.
- **R1-2** Only the supervisor's own children are reaped: a readable pidfd, then waitpid on
  that pid. Never waitpid(-1).
- **R1-3** Step 4 runs on the Die thread: it sets the stopping flag, sends each child its own
  stop, waits on all pidfds with one deadline, kills the late ones, logs them. The supervisor
  checks the stopping flag under the launch lock before every fork; Die takes the same lock
  with a timeout before it reads the pids. The lock guards a check-then-act over a fork, not
  an integer; SK4 does not apply.
- **R1-4** The hand-over checks its thread: on the emergency thread it sends the stop and the
  manual POSTs directly; elsewhere it wakes the emergency thread; both fit the cap. The
  notify is one direct POST /tts with a 0.5 s timeout. The chat line leaves Die (the banner,
  the telemetry "die" event and the spoken sentence remain).
- **R1-5** Each step runs on a daemon thread joined with its cap; a Die from a step thread
  logs one line and parks. DieFn gets a deadline. The caps are config constants with units.
  The total is stated: 1 + 0.5 + 5 + 10 s worst, the children stopped in parallel. perf.h's
  "1 s" comment becomes "the records cap".
- **R1-6** llama-server: SIGINT, 2 s, a second SIGINT, the grace, the kill; the Gemma client
  closes its connections before the server stops. The mock: shutdown_timeout 1 s and the TCP
  line closed in on_shutdown. A stop test per process kind on the real binary with work in
  flight. Open for the owner: whether the second SIGINT counts as the process's own stop.
- **R1-7** Every child in its own session (start_new_session); the supervisor signals the
  group. Ctrl+C's meaning: open for the owner (recommended: the F1 quit).
- **R1-8** Every fork on the supervisor thread; SupervisorLaunch puts a command and waits
  for the pid. The parent-death signal through `setpriv --pdeathsig TERM --`, no
  preexec_fn. The window is named; the C++ nodes close it with prctl and a getppid check
  (carried: the owner writes C++).
- **R1-9** The probe after every launch, on the supervisor thread, with per-call timeouts
  of 200 ms; the loop sleeps until the earliest of three deadlines. A never-ready child gets
  its own stop, the grace, the kill, and counts as one crash. WaitUntilReady has no timeout.
  The L1 warm-up stays the llama module's ReadyFn.
- **R1-10** A row is one atomic reference to an immutable (state, detail) pair.
- **R1-11** The text fixed: the frame listener feeds the frame buffer. The measured cost
  (17 ms worst stall, 22 of 30 frames) goes into the document and is carried to the frame
  source's review.
- **R1-12** The check: the affinity mask and the cgroup quota against os.cpu_count; never
  nproc.
- **R1-13** The reset at the exit, no timer. A relaunch delay of 1, 2, 4 s: open for the
  owner (recommended: yes).
- **R1-14** The ggml version check in the preflight; the library path per native spec; rclpy
  imported inside RosCreate.
- **R1-15** The hooks listed, unraisablehook included; the asyncio handler named as
  runtime's.
- **R1-16** m_restarts leaves the handle; the stop-request trio goes (our SAM3 server handles
  SIGINT; PROC2's "stop message" was the agent's column, not the owner's words); the second
  timeout and Stop's bool go; the handle is returned by value as an index; durations in ns.
- **R1-17** poll, through selectors.
- **R1-18** The matrix fixed and the four rows added.
- **R1-19** The tests fixed and added.
- **R1-20** The drawing redone with every hand-off and the thread that runs it.

## Answers
1. The owner did not rule a stop message; SIGINT for all six; the trio goes.
2. A pidfd per child keeps SUP1's intent (one thread, woken by an event); the document's
   "SIGCHLD" is a wording change for the app step.
3. Open for the owner; recommended: Ctrl+C is the F1 quit.
4. Open for the owner; recommended: yes, a constant.
5. The frame source's review; the number is recorded here and carried.
6. Open for the owner; the client closes first in a normal shutdown either way.
7. Yes: it guards a check-then-act over a fork, not an integer.
8. Yes, the chat line leaves Die.

## For round 2
The revised runtime.md, runtime.h and runtime.html. Check that every change landed, that the
three agree, and that nothing contradicts a ruling. Push back where the revision chose
differently. Then review what round 1 did not reach: the command pipe's protocol between
threads; SupervisorLaunch waiting for the supervisor thread while that thread probes a
child; the three-deadline loop's correctness; Die from inside a ReadyFn.
