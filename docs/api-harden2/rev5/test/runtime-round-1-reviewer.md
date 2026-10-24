# runtime (rev5), round 1: the adversarial review of runtime.md, runtime.h and runtime.html (2026-10-16)

Scope: docs/api-harden2/rev5/modules/03-runtime/runtime.md, runtime.h, runtime.html.
Read with three lenses in turn: storage and hardware; concurrency and real time; YAGNI and decoupling.
Measured: Python 3.12.3, aiohttp 3.14.3, ROS 2 Jazzy rclpy, this machine (32 threads, RTX 5070 Laptop).
The scripts are m1_wake.py to m11_die.py in the session scratchpad
(/tmp/claude-0/-root-groundstation/14da1ec2-c83e-48a1-a0d3-b0c3f2b21ea9/scratchpad).
llama-server ran CPU only (--device none, -ngl 0, port 18999). The mock ran on 127.0.0.1:18079.
No command reached any aircraft. The mock received only GET /status and a WebSocket open on /c/ws/echo.
The drawing passes svg_text_check.py (0 faults). Its content is judged in R1-20.

## Sources
1. https://docs.python.org/3.12/library/signal.html : "A long-running calculation implemented purely in C ... may run uninterrupted for an arbitrary amount of time, regardless of any signals received. The Python signal handlers will be called when the calculation finishes." Also: set_wakeup_fd's "fd must be non-blocking". Also: installing a handler "will reset the restart behaviour to interruptible".
2. https://docs.python.org/3.12/library/subprocess.html : "The preexec_fn parameter is NOT SAFE to use in the presence of threads in your application. The child process could deadlock before exec is called." start_new_session runs setsid() in the child. process_group runs setpgid(0, value).
3. https://man7.org/linux/man-pages/man2/PR_SET_PDEATHSIG.2const.html : "The 'parent' in this case is considered to be the thread that created this process. In other words, the signal will be sent when that thread terminates".
4. https://man7.org/linux/man-pages/man7/signal.7.html : "Standard signals do not queue." poll, select, epoll_wait and nanosleep always fail with EINTR after a handler, regardless of SA_RESTART.
5. https://man7.org/linux/man-pages/man2/pidfd_open.2.html : the pidfd turns readable when the process "terminates and becomes a zombie". "Even if the child has already terminated by the time of the pidfd_open() call, its PID will not have been recycled". Linux 5.3 and later.
6. https://man7.org/linux/man-pages/man2/select.2.html : "select() can monitor only file descriptors numbers that are less than FD_SETSIZE (1024)". Modern code should use poll(2) or epoll(7).
7. https://raw.githubusercontent.com/python/cpython/3.12/Lib/subprocess.py : in _try_wait, ChildProcessError means "This child is dead, we can't get the status." The code then sets `sts = 0`, a false success.
8. https://man7.org/linux/man-pages/man3/termios.3.html : the INTR character (Ctrl+C) sends SIGINT to the terminal's foreground process group.
9. https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/server.cpp : the SIGINT and SIGTERM handler is installed only after the model loads. A second signal prints "Received second interrupt, terminating immediately." and calls exit(1).
10. https://raw.githubusercontent.com/aio-libs/aiohttp/master/aiohttp/web.py : run_app defaults to handle_signals True and shutdown_timeout 60.0 seconds.
11. https://api.nav2.org/jazzy/html/classrclcpp_1_1SignalHandler.html : rclcpp's init installs the handler for SIGINT and SIGTERM. The default is SignalHandlerOptions::All.
12. https://docs.python.org/3.13/library/os.html : os.cpu_count() gives the logical CPUs in the system. os.process_cpu_count() (3.13) gives the CPUs the process may use.
13. https://docs.python.org/3.12/library/select.html : "Users are encouraged to use the selectors module instead".

## Findings

**R1-1. The wake byte is written late: a long C call on the main thread holds back every child exit.** (critical)
- Claim: the design writes the byte from a Python-level SIGCHLD handler. That handler runs only when the main thread returns to the interpreter.
- Claim: the main thread makes long C calls. Examples: the start-up loads, cv2 calls, and a blocking socket read whose signal went to another thread.
- Why it matters: the supervisor thread stays asleep for the whole C call. A crash of a laptop part triggers the RVW4 hand-over. That hand-over now waits for an unrelated C call to end.
- Why it matters: design section 6 claims the handler "may only do what cannot block". A blocking pipe blocks after 65,536 unread bytes (M4a). The header does not set O_NONBLOCK.
- Evidence (M1, measured twice): the main thread was in an 865 ms GIL-releasing C call. The child exited at 200 ms. With the design's handler, the thread woke at 865 ms and 872 ms. With signal.set_wakeup_fd, it woke at 202 ms both times.
- Evidence: source 1 states the delay. Source 1 also states that set_wakeup_fd needs a non-blocking fd.
- Change: drop the signal handler. Open one pidfd per child with os.pidfd_open(pid) right after the launch (M5: readable 103 ms after the spawn of a 100 ms child; no handler installed). The thread sleeps in one poll on the pidfds and the command pipe. This is still event-driven (SUP1). It needs no main thread, no process-wide handler and no wakeup fd. It also removes the EINTR exposure of the main thread (source 1, last sentence; source 4).
- Change, if the owner keeps the signal: use signal.set_wakeup_fd(w, warn_on_full_buffer=False) on a non-blocking pipe, plus a no-op Python handler. SupervisorCreate must then run on the main thread (source 1).

**R1-2. waitpid(-1) reaps children that are not the supervisor's; the design then dies on the unknown pid.** (critical)
- Claim: `os.waitpid(-1, os.WNOHANG)` reaps every child of the process, not only the six.
- Claim: the app runs other children. app/main.py:189 runs `subprocess.run(["tmux", "kill-session", ...])`. Any library may do the same.
- Claim: the design's loop runs `on_exit(table[pid], status)`. An unknown pid raises KeyError. DieOnUncaughtErrors turns that into Die, mid-flight.
- Why it matters: a status line to tmux could end a flight. The other caller gets a false exit code 0.
- Evidence (M2): 50 calls of `subprocess.run(["sh","-c","sleep 0.01; exit 3"], timeout=5)` beside the reap loop. All 50 returned 0, not 3. The loop saw 50 pids it did not own.
- Evidence: source 7 shows the false success (`sts = 0`) on ChildProcessError.
- Change: reap only the supervisor's own pids. On a wake, call Popen.poll() for each of at most eight handles, or poll the readable pidfds (R1-1). Never call waitpid(-1). An unknown pid is never looked up.

**R1-3. Die's step 4 depends on the supervisor thread. The design's own Die paths block that thread.** (critical)
- Claim: Die path A. The supervisor thread calls Die when a laptop part spends its budget. Step 4 then asks that same thread to stop the children. A command on its queue is never read. A join of itself raises RuntimeError in Python.
- Claim: Die path B. A Die from another thread is running. The supervisor thread then reaps a crash past the budget and calls Die. The second Die "waits for the first" and blocks the supervisor thread. Step 4 again finds no thread to stop the children.
- Claim: between the start of Die and step 4 lie up to 11.5 s (1 + 0.5 + 5 + 5). The policy still runs in that time. It relaunches crashed children; llama-server loads for 15 to 60 s. Nothing in the design checks the dying flag before a relaunch.
- Claim: today's code holds one lock over "check stopping, then fork, then record the pid" (supervisor.py, review R16). The design drops that lock. Die can read the pids, and the supervisor can fork one more child after that read. The child is orphaned.
- Why it matters: PROC2 requires each child's own stop. If step 4 fails, os._exit leaves six children. The only remaining stop is the parent-death signal (R1-8).
- Change: step 4 runs on the Die thread itself. It sets the stopping flag. It sends each child its own stop. It waits on all pidfds with one deadline. Then it kills the late ones and logs them. It never sends a command to the supervisor thread.
- Change: the supervisor checks the stopping flag before every launch. The check, the fork and the pid store happen under one launch lock. Die takes the same lock, with a timeout, before it reads the pids. This lock guards a check-then-act over a fork, not one integer, so SK4 does not apply. Today's R16 fix is exactly this lock.

**R1-4. The hand-over and the notify fail in the cases that need them.** (critical)
- Claim: the hand-over wakes the emergency thread and waits up to 1 s. Suppose the emergency thread itself raised the uncaught error. Die then runs on that thread. The hand-over waits 1 s for a thread that is busy running Die. No stop is sent.
- Claim: the notify puts one sentence on the voice FIFOs. The design rules "no cutting" and "a laptop TTS sentence: seconds" (design sections 3 and 8). A running sentence holds the queue far beyond the 0.5 s cap. os._exit then drops the Die sentence unspoken.
- Claim: the notify writes a chat line. The chat is main-thread state (SYS1). From another thread this is a data race. If Die runs on the main thread, nobody draws the line before the exit.
- Why it matters: RVW4 is a safety ruling: hand the aircraft to the RC, then tell the operator. Both steps fail without a trace when Die starts on the wrong thread.
- Change: the hand-over function checks the current thread. On the emergency thread, it sends the stop and the manual POSTs directly. On any other thread, it wakes the emergency thread. In both cases the HTTP timeout fits within the 1 s cap.
- Change: the notify makes one direct POST /tts with a 0.5 s timeout. It does not use the voice FIFO. The chat line leaves Die. The stderr banner and the telemetry "die" event already record the reason.

**R1-5. The caps cannot be enforced as written, and the numbers disagree.** (high)
- Claim: Python cannot interrupt a thread that is blocked in a C call. DieFn(ctx, reason) carries no deadline. So Die has no means to cap a step.
- Claim: the caps disagree. runtime.h gives the record flushes "5 s cap each". perf.h line 128 gives PerfFlush in die() "1 s". TelemetryFlushInDie takes a timeoutNs that the DieFn signature cannot pass.
- Claim: a step that calls Die "is skipped and logged" (runtime.h). No mechanism is given. Today's plain Lock deadlocks (M11: a cleanup that calls die() still hung at the 5 s timeout).
- Claim: the worst case is unstated. It is 1 + 0.5 + 5 + 5 + 10 = 21.5 s if the children stop in parallel. It is about 70 s if they stop one after another. The header does not say which.
- Why it matters: a crash that hangs for a minute keeps the GPU and the camera busy, and the operator has no app.
- Change: Die runs each registered function on a new daemon thread and joins it with the step's cap. Die records the ids of these step threads. A Die from a step thread logs one line and parks; the join's timeout skips it. os._exit ends every parked thread.
- Change: `typedef void (*DieFn)(void* ctx, const char* reason, uint64_t deadlineNs);`. The caps become named config constants with units: kDieHandoverCapMs, kDieNotifyCapMs, kDieRecordsCapMs, kDieChildrenCapMs. Gate item 5 requires this. The perf cap and the runtime cap become one number.
- Change: step 4 stops the children in parallel, with one deadline. The header states the total.

**R1-6. Two of the six children do not stop on SIGINT when they still have work in flight.** (high)
- Claim: llama-server does not exit on SIGINT while a generation runs. The design's grace then ends in a kill. That breaks PROC2 on the normal path: a Die mid-flight usually comes while the recognizer has a plan in flight.
- Evidence (M9, CPU only): with no request, SIGINT gave exit 0 in 0.61 s. During the model load it gave rc -2 in 0.03 s, because the handler is not yet installed (source 9). During a generation, there was no exit in 30 s; the log stopped at "cleaning up before exit...". The process was killed.
- Evidence (M9b): SIGINT, then 2 s, then a second SIGINT gave exit(1) after 2.46 s. That is llama-server's own forced exit (source 9).
- Evidence (M9c): the client closed its socket first. The slot was released. One SIGINT then gave exit 0 in 0.51 s.
- Claim: the mock does not exit on SIGINT while a long-lived connection is open. rev5's mock carries the persistent TCP line (design section 2).
- Evidence (M8): idle, exit in 0.06 s. With one idle keep-alive HTTP connection, exit in 0.06 s. With one open WebSocket, no exit in 70 s; it was killed. aiohttp's shutdown_timeout defaults to 60 s (source 10).
- Claim: open point 3's alternative is not a real alternative. rclcpp handles SIGINT and SIGTERM the same way (source 11). llama-server does too (source 9), and so does aiohttp run_app (source 10). The fault is work in flight, not the signal number.
- Change: llama-server's stop is SIGINT, then 2 s, then a second SIGINT, then the grace, then the kill. In a normal shutdown the Gemma client closes its connections before the supervisor stops the server (M9c).
- Change: the mock calls run_app(shutdown_timeout=1.0) and closes the TCP line in on_shutdown.
- Change: add a stop test per process kind on the real binary with a request in flight. The six stop methods stay unproven until then.

**R1-7. The children share the app's process group. A Ctrl+C reaches all of them, and the supervisor counts six crashes.** (high)
- Claim: no spec sets a new session or group. Today's Popen does not either.
- Claim: a Ctrl+C in the terminal sends SIGINT to the whole foreground group (source 8). All six children exit together. The supervisor reads six crashes and relaunches them. llama-server starts a 15 to 60 s GPU load. Meanwhile the app's main thread gets KeyboardInterrupt and runs Die. The relaunched children then race step 4.
- Why it matters: the stop then comes from the terminal, not from the supervisor. The restart budget is spent by an operator key, not by a crash.
- Change: launch every child with process_group=0 (Python 3.11+) or start_new_session=True (source 2). The supervisor alone stops them. It signals with os.killpg so that a grandchild, if one ever exists, also stops.
- Change: the parent-death signal (R1-8) becomes the only backstop for a SIGKILL of the app. That is the design's stated intent.

**R1-8. The parent-death signal: preexec_fn is unsafe and costly, and the signal follows the launching thread.** (high)
- Claim: the design sets PR_SET_PDEATHSIG "through the launcher". In Python that means preexec_fn. The documentation says it is not safe with threads (source 2). The app has about 20 threads.
- Evidence (M3b, M3c): in a process with 2 GiB resident and 8 threads, a launch took 0.19 ms on the default vfork path. With preexec_fn it took 103 ms, because preexec_fn forces fork(). The main thread, which only slept 1 ms per loop, stalled 47.9 ms per launch. Without preexec_fn the stall was 1.1 ms.
- Claim: the signal fires when the launching THREAD ends (source 3).
- Evidence (M3a): a child launched with prctl from a short-lived thread died with -15 as soon as that thread ended, while the process lived.
- Claim: SupervisorLaunch "launches at once" on the caller's thread. A launch from a temporary thread kills the child later. A launch outside the supervisor thread also races the reap: the child can exit before its pid is in the table.
- Change: every fork runs on the supervisor thread. SupervisorLaunch puts a command and waits for the pid. That thread lives until step 4 is done.
- Change: set the signal without preexec_fn. Prefix argv with `setpriv --pdeathsig TERM --`; it keeps the vfork path (M3a: 0.17 ms). SIGTERM is graceful for rclcpp, llama-server and aiohttp (sources 9 to 11). SIGKILL is not needed.
- Change: name the remaining window. If the launching thread dies before setpriv calls prctl, the child survives (M3a: a thread that ended at once left the child alive; one that lived 0.3 s did not). The C++ nodes we own can close it: call prctl first, then exit when getppid() is 1.

**R1-9. The readiness probe is under-specified: which thread runs it, when, and how a never-ready child ends.** (high)
- Claim: the header says the probe runs "during start-up only". After a relaunch, nothing probes. A relaunched llama-server would show UP for 15 to 60 s before it can serve.
- Claim: today, the Gemma row turns UP only after one warm-up plan (owner L1, app/main.py start_processes). The design's instance uses health_ok and drops L1 without a ruling.
- Claim: a ReadyFn is an HTTP call. On the supervisor thread it blocks the reap and the commands for its timeout. Today each process has its own thread, so this never mattered.
- Claim: the select loop has one timeout, retry_due(). It also needs the probe ticks and the stop-grace deadlines. That is three timer kinds in one loop.
- Claim: "a child never gets ready: killed" skips the process's own stop (PROC2).
- Claim: SupervisorWaitUntilReady takes a timeout that repeats m_readyTimeoutS (240 s in both, in instance 1).
- Change: probe after every launch, on the supervisor thread, with a per-call HTTP timeout of 200 ms or less. The loop sleeps until the earliest of three deadlines: the next probe, the next grace end, the next WAITING retry.
- Change: a never-ready child gets its own stop, then the grace, then the kill. It counts as one crash against the budget, as today.
- Change: SupervisorWaitUntilReady(s, p) has no timeout. It returns true on UP and false on FAILED.
- Change: the L1 warm-up stays the llama module's ReadyFn, unless the owner rules otherwise.

**R1-10. Two atomic stores make a torn row. The chat line can then carry the wrong reason.** (medium)
- Claim: m_state and m_detail are two stores. The main thread can read the new state with the old detail. The design turns a changed state into a chat line once, so the stale detail stays in the chat.
- Why it matters: STA1 accepted a rare torn read for the pane, which redraws every frame. A one-shot chat line never redraws.
- Evidence (M7): six rows per frame. Two attribute loads per row cost 357 ns. One tuple load per row costs 192 ns. In Python, one reference store of an immutable tuple is atomic under the GIL.
- Change: the row is one atomic reference to an immutable (state, detail) pair: `typedef struct { ProcessState m_state; const char* m_detail; } RowValue;` and `const RowValue* _Atomic m_row;`. It is one store and one load, and it costs less.

**R1-11. The frame listener is described wrongly, and its cost to the main thread is not measured.** (medium)
- Claim: runtime.md says every listener "puts it on the app's queue". The drone frames go to the frame buffer, not the queue (design section 6). The text is wrong for one of the three listeners.
- Claim: gate items 1 and 9 cover only the row loads. The listener threads take the GIL for each 6 MB message.
- Evidence (M10): a 1920x1080 bgr8 Image published at 30 Hz to one rclpy listener (its own node and executor, as designed). 220 of 300 frames arrived in 10 s. The main thread ran a 1 ms sleep loop. Its p99 gap rose from 1.06 ms to 9.47 ms, and its worst gap rose from 1.11 ms to 17.09 ms. The callback's own copy was 0.66 ms; the rest is rclpy's conversion of the message under the GIL.
- Evidence (M10): executor shutdown, join, destroy_node and rclpy.shutdown took 4.2 to 4.5 ms. The destroy order works.
- Why it matters: 17 ms is half of a 33 ms frame. 27 % of the frames are lost before the app sees them.
- Change: the document states the frame listener's cost: 17 ms worst stall and 22 frames a second delivered, measured. Gate item 9 gets its own row for it.
- Change: the frame path itself is a question for the frame source's review (question 5).

**R1-12. The core-count check uses numbers that do not mean "the machine's".** (medium)
- Claim: PRF5 says "nproc". nproc follows OMP_NUM_THREADS. Many ML setups set that variable.
- Evidence (measured): `nproc` gave 32. `OMP_NUM_THREADS=4 nproc` gave 4, while the affinity mask still held 32 CPUs. Under `taskset -c 0-3`, os.cpu_count() gave 32 and len(os.sched_getaffinity(0)) gave 4. /sys/fs/cgroup/cpu.max reads "max 100000" here.
- Claim: `docker --cpus=4` sets a cpu.max quota. Neither os.cpu_count() nor the affinity mask shows a quota. The check passes on a crippled container. The dev environment is a container.
- Change: the machine's count is os.cpu_count() (source 12). The check fails when len(os.sched_getaffinity(0)) is smaller. It also fails when cpu.max holds a quota below os.cpu_count() times the period. It never calls nproc.

**R1-13. The restart budget: the reset has no defined moment, and a crash loop spends three restarts in under a second.** (medium)
- Claim: "reset after StableSeconds up" can mean a timer or a check at the exit. Today it is the check at the exit (supervisor.py `_run_once`). A timer adds a fourth deadline to the loop.
- Claim: the design relaunches at once. Transient causes clear in seconds: GPU memory not yet freed, a busy audio device, a port. Three instant relaunches fail the same way. A laptop part then calls Die mid-flight.
- Why it matters: design section 9 says "SAM3 out of GPU memory: its process dies and restarts". If llama-server holds the memory, three restarts in a row fail the same way, and the app dies.
- Change: the reset is computed at the exit: up for 60 s or more means the count goes back to 0. No timer.
- Change, a question for the owner: a delay before each relaunch (1, 2, 4 s), as a config constant.

**R1-14. The start-up check drops a standing rule, checks the wrong library path, and imports too early.** (medium)
- Claim: docs/guidelines.md says "The preflight fails when the libggml*.so.0 names mix versions." The runtime design does not list it. Today only run.sh checks it (run.sh line 110). The bin folder holds both 0.15.3 and 0.18.0 builds today.
- Claim: "the native bin folder is first on the library path" tests the app's own LD_LIBRARY_PATH. The children get their path from native_env(), not from the app. The check tests a value no child uses.
- Claim: "before any module imports a package". Today runtime/ros.py imports rclpy at module level. If the runtime package loads its ROS part with the rest, the preflight runs after a package import.
- Change: the preflight checks the ggml versions, as run.sh does. The library-path check moves to the spec: every native spec's env starts with config.NATIVE_BIN_DIR. rclpy is imported inside RosCreate, or in a file the preflight never imports.

**R1-15. DieOnUncaughtErrors claims "any thread"; it covers two hooks. Ctrl+C becomes an "uncaught error".** (medium)
- Claim: today it sets threading.excepthook and sys.excepthook (fatal.py). It does not cover sys.unraisablehook, a C callback (sounddevice's PortAudio callback), or an asyncio loop. audio/asr_phone.py sets its own loop handler today; the header does not mention it.
- Claim: with rclpy's handler off, Ctrl+C raises KeyboardInterrupt in the main thread, and sys.excepthook turns it into Die. The design does not say whether Ctrl+C is a crash or the quit.
- Change: the header lists the hooks it sets, sys.unraisablehook included. It names the asyncio handler as runtime's function, which the phone listener installs.
- Change: Ctrl+C gets a defined meaning (question 3).

**R1-16. YAGNI and decoupling in the header.** (medium)
- Claim: Process::m_restarts is _Atomic. Only the supervisor thread reads it, and the detail text already shows "restart n/3". It does not need to be atomic, or in the handle at all.
- Claim: StopMethod, StopRequestFn and m_stopCtx exist for one process: our own SAM3 server. We write that server, so it can handle SIGINT like the other five. One enum, one function type and one pointer go. PROC2's decision column names "a stop message" (question 1).
- Claim: the timeout of SupervisorWaitUntilReady repeats m_readyTimeoutS (R1-9).
- Claim: SupervisorStop returns "false when the kill was needed". No caller is named. The supervisor already logs the kill.
- Claim: SupervisorLaunch returns a Process* that the supervisor owns. OWN1 says the app owns plain handles. PROC2 says the Create call "returns a handle by value".
- Claim: the units mix float seconds (m_readyTimeoutS, m_stopGraceS) with uint64_t nanoseconds (TelemetryFlushInDie's timeoutNs). A float holds 240.0 exactly, but the house type for a duration is the ns integer.
- Change: remove m_restarts from the handle. Remove the stop-request trio if question 1 allows. Remove the second timeout and Stop's bool. Return the handle by value, holding an index into the supervisor's table. Write durations as uint64_t ns.

**R1-17. select.select fails on a file descriptor of 1024 or more.** (low)
- Evidence (M4b): select.select on fd 1105 raised "ValueError: filedescriptor out of range in select()". Source 6 says the limit "will not change".
- Why it matters: a ValueError is an uncaught error, so it becomes a Die. A pidfd opened at a late relaunch gets a high number in a process with DDS sockets and record files.
- Change: use select.poll or selectors.DefaultSelector (source 13).

**R1-18. The failure matrix has a wrong row and lacks four rows.** (low)
- Claim: "the ROS context dies → the rows of the ROS children go RECOVERING" is wrong. The children are other processes with their own contexts. The app's context does not touch their rows.
- Missing: Die on the supervisor thread (R1-3).
- Missing: a launch that raises. Popen raises FileNotFoundError when the binary is gone, for example rebuilt during a run. That error leaves the module, which breaks gate item 8. It should count as one crash.
- Missing: a child that holds a long request at its stop (R1-6).
- Missing: Ctrl+C at the terminal (R1-7).
- Change: fix the row and add the four.

**R1-19. Some tests can pass without checking anything, and the faults above have no tests.** (low)
- Claim: `test_rows_are_read_without_a_lock` relies on "a lock added fails the budget test". An uncontended Lock costs 122 ns (measured). Six rows cost 0.7 us per frame, against a 330 us budget. The mutation passes, so the test checks nothing.
- Claim: `test_children_die_with_a_killed_parent` must launch from the supervisor thread and kill the parent with SIGKILL. Otherwise it passes for the wrong reason (M3a).
- Change: the row test asserts the structure, one immutable pair per row (R1-10), not a time.
- Change: add tests for the faults: test_foreign_child_keeps_its_exit_code (R1-2); test_exit_seen_while_main_thread_in_c_call (R1-1); test_die_on_supervisor_thread_stops_children; test_no_relaunch_during_die (R1-3); test_die_on_emergency_thread_still_hands_over (R1-4); test_step_that_dies_is_cut_at_its_cap (R1-5); test_llama_stops_with_a_request_in_flight and test_mock_stops_with_an_open_line, on the real programs (R1-6); test_terminal_sigint_counts_no_crash (R1-7); test_relaunch_is_probed_before_up (R1-9); test_core_check_sees_quota_and_affinity (R1-12).

**R1-20. The drawing hides the hand-offs that this review found faulty.** (low)
- Claim: the drawing names the emergency thread and the voices only as text inside the Die box. It draws no arrow from Die to the emergency thread or to the voice FIFOs. It does not show that the handler runs on the main thread. It does not show the second pipe for commands.
- Why it matters: the owner's rule (2026-09-22) is that a diagram shows every queue, thread and hand-off. R1-1, R1-3 and R1-4 sit exactly on these missing lines.
- Change: draw each hand-off as its own line, with the thread that runs it.

## Questions for the manager agent
1. PROC2: "a stop message for our SAM3 server" stands in the decision column, not in the owner's quoted words. Did the owner rule it? If not, SIGINT for all six removes StopMethod, StopRequestFn and m_stopCtx (R1-16).
2. SUP1 asks for one thread woken by an event. Does a pidfd per child satisfy the owner's intent (R1-1), or does design section 2 ("SIGCHLD") bind the mechanism?
3. What does Ctrl+C mean in the app: Die with the hand-over, or the F1 quit (R1-7, R1-15)?
4. A delay before each relaunch adds a constant to config. Does it need an owner ruling, given section 9's SAM3 out-of-memory case (R1-13)?
5. The frame listener stalls the main thread up to 17 ms and loses 27 % of the frames (M10). Does this belong to runtime's review, or to the frame source's review? There, RVW5 keeps the gstreamer receiver as a separate ROS2 node.
6. Is llama-server's second SIGINT "the process's own stop" under PROC2? Or must the Gemma client close its connections first, also inside Die (R1-6)?
7. Is a launch lock in the supervisor acceptable under SK4 ("no mutex for a single integer")? It guards a check-then-act over a fork (R1-3).
8. Should the chat line leave Die's notify step? The chat is main-thread state, and the main thread may be the one that died (R1-4).
