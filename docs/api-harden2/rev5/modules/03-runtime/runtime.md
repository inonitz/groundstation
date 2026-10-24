# runtime: the floor of the app (rev5 module review, started 2026-10-16)

The headers are `runtime.h` (the public contract) and `runtime_internal.h` (what crosses a boundary
inside runtime and what gets a pure test: Die's sequence and step 4, the supervisor's state and
policy); the drawing is `runtime.html`. The design document is
`../../01-system-architecture.md` (sections 2, 3, 9). Below it: the recorder (perf and telemetry folded into it, RCD1)
(approved). The state: revised after three rounds of the reviewer agent (`../../test/runtime-round-*.md`,
44 findings, all taken; `runtime-conclusions.md`); APPROVED 2026-10-17 (RUN11 to RUN14).

## 1. The job, in one sentence
Runtime starts and stops the app's processes, turns a fatal error into a safe crash, and hosts the ROS2 context.

## 2. The picture
Four parts, as in `runtime.html`:
```
 [1] Die: the crash path                [2] the supervisor: one thread, event-driven
     Die(reason), the first wins            a pidfd per child, readable at its exit;
     1 hand-over  2 notify  3 records       one poll on the pidfds + the command pipe;
     4 children (on the Die thread)         unregister, reap, close; the policy; the
     5 _exit; each function on its own      row: one atomic store; every fork on this
     thread, capped, left behind if stuck   thread, under the launch lock

 [3] ROS2: one context,                 [4] the start-up check, before any import
     a listener per topic on                the packages, programs, models; the ggml
     its own thread                         versions; the cores the process may use
```
1. **Die.** Our code never throws. A fatal condition calls Die(reason) from any thread; the
   first wins. Every registered function runs on its own short-lived thread, joined against
   its step's deadline, so a function stuck in a C call is left behind. The hand-over is the
   phone client's function (PHN6, 2026-10-18): the halt when a motion request left this run,
   then /c/stop, then /c/stop again 400 ms before the 1 s deadline, on its own connection; it
   never goes through the emergency thread, which may be the thread inside Die. The notify is one direct POST /tts.
   Step 4 is Die's own: the launch lock, the stopping flag, SIGINT through the pidfd to every
   child without a stop already sent, the second SIGINT to llama-server after 2 s, one
   deadline on every pidfd, then the kill of the late ones, logged.
2. **The supervisor.** One thread. Each child has a pidfd, readable when it exits. The thread
   sleeps in one poll on the pidfds and the command pipe. On a readable pidfd it unregisters
   it, reaps that child through its Popen, closes the pidfd, and applies the policy: a stop
   sent or the stopping flag means DOWN and no policy; a planned restart relaunches; a crash
   counts, waits its delay, relaunches, or ends the budget. The row is one atomic reference. Every fork runs on this
   thread under the launch lock. A terminal Ctrl+C never reaches a child: each runs in its
   own session. If the app is killed outright, the parent-death signal ends the children.
3. **ROS2.** One context. Each topic gets its own node and executor thread. That thread
   stamps the message and hands it on: a key or a transcript to the app's queue, a frame to
   the frame buffer. It never touches app state.
4. **The start-up check.** Every package, native program and model file; the ggml versions
   in the native bin folder; the CPUs the process may use and the cgroup quota against the
   machine's count. A miss dies at once with the command that fixes it.

## 3. How a caller uses it: two instances, in the Python of the build
**Instance 1: the app's start, and a module that launches its process.**
```python
# app/main.py, the first lines
preflight_or_die()                                 # the five checks; dies at once on a miss
die_install_uncaught_error_hooks()
recorder_create(session.dir, "app", RecorderFrameConfig(size, models_json))   # the one record service
die_add_flush(recorder_flush_in_die, None)       # fits DieActionFn; ctx NULL
die_add_flush(lambda ctx, reason, deadline:
# each module describes its process with a pure function of config and the log folder
specs = [llama_process_spec(log_dir, port), keys_process_spec(log_dir),
         asr_process_spec(log_dir), sam3_process_spec(log_dir)]
if not config.DJI_REAL:  specs.append(mock_process_spec(log_dir))
if video == "dji":        specs.append(gstreamer_process_spec(log_dir, phone_ip))
supervisor = supervisor_create(specs)              # the OWNER: launches, watches, stops them all
ros_context_init()

# llama/server.py, the pure function; nothing here launches anything
def llama_process_spec(log_dir, port):
    return ProcessSpec(name="llama", argv=llama_argv(port), env=native_env(),
                       ready_probe=partial(health_ok, port), ready_timeout_ns=s(240),
                       stop=ProcessStopPolicy(SIGINT, retry=SIGINT, retry_delay_ns=s(2), grace_ns=s(10)),
                       on_budget_spent=BUDGET_SPENT_DIE, log_path=f"{log_dir}/proc-llama.log")

# the app, at start: wait for what it must have, then the L1 warm-up (open point 5)
llama = supervisor_process(supervisor, "llama")
if not supervisor_wait_until_ready(supervisor, llama):
    die("llama-server never answered")
plan_warm_up(gemma)

# the app, once the phone client exists; each adapter fits DieFn(ctx, reason, deadline)
die_set_handover(phone_client_die_handover, client)  # halt if motion left, stop, stop; 1 s
die_set_notify(post_tts_app_is_gone, phone_url)      # one POST /tts, 0.5 s timeout
```
**Instance 2: the supervisor's loop in the source file, and the stall guard's request.**
```python
# runtime/supervisor.py, the one thread; the state is runtime_internal.h's
def _run(self):
    while not (self._quit_ran and self._every_child_reaped()):
        events = self._selector.select(timeout=self._earliest_deadline())
        for key, _ in events:
            if key.fileobj is self._cmd_pipe: self._run_commands()     # restart on purpose, quit
            else: self._on_child_exit(key.data)                        # that pidfd's child
        self._fire_passed_deadlines(monotonic_now())                        # a probe, a grace, a relaunch

def _on_child_exit(self, p):
    with self._launch_lock:
        if self._stopping: return                                      # left to Die's step 4
        self._selector.unregister(p.pidfd); p.popen.wait(); os.close(p.pidfd)
    self._apply(p, decide_after_exit(p, monotonic_now()))                   # the pure policy

# video/frame_source.py, the stall guard, from the frame source thread
if now - last_frame_at > STALL_NS:
    supervisor_restart_on_purpose(supervisor, gstreamer, "no frame for 6 s")
```

## 4. The open points for the owner
Added 2026-10-18 (FB2, RUN15): ProcessSpec carries the descriptors a child inherits
(m_passFds, m_nPassFds), Popen's pass_fds; the SAM3 server inherits the framebuffer's
nameless memfd this way. Every other descriptor stays closed in the child, as before.
Decided: Ctrl+C is the F1 quit (RUN11). The relaunch delays are 1.5 s, 3 s, 4.5 s (RUN12,
"Take intervals of 1.5s instead"). llama-server's second SIGINT: "Good! Approved!" The pidfd:
approved on the understanding below. The launch lock: "Yes, I agree with this design decision,
generally." Point 5, the probe: approved (RUN14). The module is APPROVED; TOCTOU is pinned by four tests.

2. **A delay before a relaunch.** A relaunch is the supervisor starting one of the six child
   processes again, with the same command line, after that process crashed. The problem: some
   crash causes clear by themselves within a second or two. The GPU driver frees the memory
   of a dead llama-server a moment after its exit. A TCP port stays reserved for a short time
   after its owner died. An audio device is released a moment after the ASR node died. If the
   supervisor restarts at once, the new process hits the same cause and crashes again. Three
   instant restarts take under a second. The budget of three is then spent, and a laptop part
   kills the app. Decided: the supervisor waits 1.5 s before the first relaunch, 3 s before
   the second, 4.5 s before the third (the delay times the restart count).

3. **llama-server's second SIGINT.** Measured 2026-10-16. With no request running, one SIGINT
   ends llama-server cleanly in 0.6 s. With a request running, it ignores the first SIGINT;
   it did not exit in 30 s. Its own code treats a second SIGINT as "terminate now"; it exited
   2.5 s after the second one. A Die mid-flight usually comes while a plan is running. Now:
   llama-server's stop policy is SIGINT, then SIGINT again after 2 s if it still runs, then the
   grace, then the kill. The other five children get one SIGINT. On "no": one SIGINT for
   llama-server too; every Die mid-flight then waits the 10 s grace and kills it. Recommended:
   the second SIGINT.

4. **A pidfd per child, not SIGCHLD.** The question is not speed. It is whether the supervisor
   learns of a crash at all in time. The design document says the child-exit signal wakes the
   supervisor. In Python a signal handler runs on the main thread, and only between two
   bytecodes. CPython runs Python code as a sequence of bytecode instructions and looks for a
   pending signal only at the boundary between two of them. A call into C (a window read, a
   socket read, an image encode) is one instruction that runs to its end in C, so no boundary
   comes until it returns. While the main thread is inside such a call, the handler waits. Measured: a child's exit was seen 665 ms late behind one such call. A
   pidfd is a file descriptor that becomes readable when its child exits. The supervisor
   thread sleeps on the six pidfds directly. The main thread is not involved. Measured: 0.5 ms
   after the exit. A second gain: no signal handler means the main thread's own system calls
   are never interrupted by one. Now: a pidfd per child. On "no": the signal, with the
   standard wake-up pipe. Recommended: the pidfd. The design document's word changes at the
   app step. Approved (RUN12): the supervisor thread sleeps in the kernel's poll on the
   pidfds until one changes; the main thread plays no part.

5. **The readiness probe: why it exists, where it came from, and its 200 ms.** Why probe at all:
   a child process cannot tell its parent "I am ready" unless a channel exists for it.
   llama-server and the mock announce readiness only by answering HTTP; a ROS 2 node
   announces nothing, it publishes when it has data. So the supervisor asks: a GET /health, or
   a port check. The children we write (the SAM3 server) could report through a pipe, but
   the third-party ones cannot, so one mechanism serves all six. Where it came from: today's
   supervisor (2026-09-22) already has it: a `ready` callable in the spec, polled every 0.5 s
   during start-up. The 200 ms: new in this design, from the reviewer's round 1. One thread
   now probes every child, so one call must not block it; a GET to localhost answers in
   milliseconds, and 200 ms is the timeout for a server that hangs. Your reading is right: the
   supervisor owns the processes, so knowing their state and setting their rows is its job,
   and the probe is how it learns. Now: the probe per spec (/health or a port), 200 ms a call,
   every 500 ms, after every launch. On "no": a child reports readiness itself, which three of
   the six cannot. Recommended: the probe.
   The six probes, as the modules would write them (the owner asked, RUN13):
   ```python
   # llama-server: /health answers 200 (503 while the model loads)
   ready_probe = lambda: http_status("http://127.0.0.1:18090/health", timeout=0.2) == 200
   # the mock phone app: /status/ answers 200 (today's mock_ready)
   ready_probe = lambda: http_status("http://127.0.0.1:8079/status/", timeout=0.2) == 200
   # the SAM3 server, ours: one line on its socket, "status" -> "ready" after the warm pass
   ready_probe = lambda: socket_line("127.0.0.1", SAM3_PORT, "status", timeout=0.2) == "ready"
   # the three ROS 2 nodes have no HTTP: ready = their topic has a publisher (a graph
   # query on the app's own node; DDS discovery, under a millisecond, no message needed)
   ready_probe = lambda: ros.count_publishers("/keyboard/in/raw") > 0        # keys
   ready_probe = lambda: ros.count_publishers("/asr_server/transcribe") > 0  # the ASR node
   ready_probe = lambda: ros.count_publishers("camera/stream") > 0           # gstreamer rx
   ```
   Today the three ROS 2 nodes have no probe at all (ready once launched); the graph query
   is the one new piece.

**Where the Gemma warm-up runs, and who reports it (decided with point 5).** Your description is the design: the
   server launches, the warm-up runs, then the dashboard shows it ready. The warm-up was the
   readiness probe because today's code made it so, after L1 (2026-09-29): "the row turns UP
   after one warm-up plan". That worked while each process had its own watcher thread. In
   the new design one supervisor thread probes every child, and a probe must return in
   200 ms. A plan takes 0.5 to 1.4 s, so the warm-up cannot be the supervisor's probe. Now:
   the supervisor's probe is /health, which says the server answers; its row goes UP then.
   The app's start thread runs the warm-up right after. The Gemma module owns its own status
   row, as every part does, and sets it "warm" when the warm-up returns. The dashboard shows
   both rows. On "no": the warm-up stays the probe and the supervisor thread blocks up to
   1.4 s per probe, during which it sees no crash. Recommended: the probe is /health; the
   module's row says warm.

6. **The launch lock.** The supervisor thread forks the children. Die's step 4 reads the list
   of children to stop them. The problem: a fork can happen after Die read the list. That
   child is never stopped by Die. The lock makes three things one indivisible step: check the
   stopping flag, fork, record the pid. Die sets the stopping flag under the same lock before
   it reads the list. After that no fork happens. SK4 says no mutex for a single integer. This
   lock guards a fork, not an integer. Today's code has the same lock. Without it the missed
   child lives until the app exits, when the parent-death signal ends it; the harm is one
   child alive a few seconds longer. On "no": no lock. Recommended: the lock.
   The realistic case (the owner asked): a laptop part crashed and its relaunch delay just
   expired, so the supervisor thread is about to fork; at the same moment another thread
   dies on an uncaught error, which is correlated: the same fault that crashed the child
   often fails the request a worker was waiting on. The window is microseconds; the lock
   costs microseconds and sits off every hot path. TOCTOU: without the lock the sequence
   "check the stopping flag, then fork" is exactly a time-of-check to time-of-use race; the
   lock closes it by putting the check, the fork and the pid store in one critical section,
   and Die's flag store and list read in the same one. The other TOCTOU of a supervisor, a
   pid reused by a new process between a check and a kill, is closed by the pidfd: every
   signal goes to the file descriptor of that exact process, never to a pid. Approved,
   generally (RUN12).
   **With the lock, what TOCTOU remains (the owner, RUN13).** Three windows were checked.
   (a) Between Die's snapshot of the list and its signals, a child may exit on its own and
   the kernel may reuse its pid. Closed: the signal goes through the pidfd, which names that
   exact process; a pidfd of an exited child answers "no such process", never another
   process. (b) Between Die's snapshot and its signals, the supervisor thread could close a
   pidfd Die holds. Closed: once the stopping flag is set, under the lock, the supervisor
   thread neither reaps nor closes; the descriptors Die read stay valid until _exit. (c) A
   restart command queued before the flag and run after it. Closed: the command handler
   checks the flag under the lock before its fork. One window stays, by choice: Die takes
   the lock with a timeout; if the supervisor thread held it for longer than that (it holds
   it for a fork and a reap, microseconds), Die reads the table without the lock and logs
   one line. A child forked in that instant is missed by Die and ended by the parent-death
   signal at _exit. The alternative is a Die that can hang on the lock, which is worse.

## 5. Today
The code: `projects/integration_harden2/runtime/`: `fatal.py` (83 lines), `supervisor.py` (268),
`status.py` (83), `ros.py` (54), `deps.py` (106); `util/process.py`.
- die(): prints the reason, runs the registered cleanups in order (the recorder's flush, then the
  supervisor's stop_all), `os._exit(1)`. A second die() waits for the first. The crash hooks
  turn an uncaught exception in any thread into die(). It sends nothing to the aircraft.
- The supervisor: a watcher thread per process; each blocks in `proc.wait()`; stop_all
  sends SIGTERM to every child and kills after 10 s; a required process past 3 restarts
  dies; a phone-side one waits and retries every 5 s; 60 s up resets the count; a planned
  restart is not counted. The readiness probe polls every 0.5 s at start.
- status.py: a Status row with a lock, set by its owner; the board asks every source.
- ros.py: one context; a Subscription per topic on its own node and executor thread.
- deps.py: the preflight of packages, programs and models.
What is wrong with it against rev5: a thread per process (SUP1 rules one, event-driven); a
SIGTERM for every child, then a kill (PROC2 rules each process's own stop); a lock on a status
row (STA1 rules an atomic store); die() sends nothing to the aircraft (RVW4 rules the
hand-over first); no core-count check (PRF5).

## 6. The rulings that bind it, and the forces
| ID | the owner's words | what it fixes here |
|---|---|---|
| 2026-09-19 | no exceptions in our own code: crash, loudly | Die(reason); DieOnUncaughtErrors |
| 2026-09-22 | every process through the supervisor; a crash stops every child; 3 restarts; a laptop part dies, a phone part waits | the policy and the budget |
| U6 (2026-09-25) | "Option A": the phone check 2 s; process restarts 5 s | SUPERVISOR_WAITING_RETRY_NS |
| SUP1 (2026-10-02) | "There shouldn't be a watcher for each process ... a single thread ... a condition variable ... saved into a queue" | one thread, woken by a pidfd per child and a command pipe; no signal handler |
| PROC2 (2026-10-04) | "Do you think Killing processes is a normal and acceptable way to return resources to the system?" | each process's own stop; the grace; a kill only logged |
| NAM3 | Create and Destroy | every handle |
| STA1 | a status row is an atomic state the UI reads | StatusRow: one atomic reference to an immutable (state, detail) pair |
| RVW4 (2026-10-12) | mid-flight: hand control to the RC, notify the operator, then crash | the four steps of Die |
| PRF5 (2026-10-12) | the nproc assertion | the preflight |
| the perf review, point 5; TEL2; RCD1 | the recorder's flush after the hand-over and the notify; the recorder never dies | DIE_STEP_RECORDS; the flushes have caps |
The forces:
- The processes: six (the keyboard hook, the ASR node, the mock or the phone app's stand-in,
  the gstreamer receiver, llama-server, the SAM3 server). Each is a ROS2 node, llama-server, an
  aiohttp server or our own Python; every one handles SIGINT; our SAM3 server installs its
  own SIGINT handler that sets its stop event (the default KeyboardInterrupt would be an
  exception in our code).
- A crash of a child is rare: a restart takes seconds (llama-server 15 to 60 s to load).
- Die mid-flight must reach the stop within the 1 s emergency budget: the hand-over runs
  first and is capped at 1 s; the flushes come after.
- The main thread reads the six rows each frame: an atomic load each, no lock.
- A Python signal handler runs on the main thread only when that thread returns to the
  interpreter: measured, a child's exit was seen 665 ms late behind an 865 ms C call. A pidfd
  is readable 0.54 ms after the exit (max 0.83 ms), with no handler. So no signal handler.
- waitpid(-1) reaps children the supervisor does not own: measured, 50 subprocess.run calls
  beside such a loop all returned 0 instead of 3. So only the supervisor's pids are reaped.
- A fork with preexec_fn costs 103 ms and stalls the main thread 48 ms (measured, 2 GiB
  resident); the default vfork path costs 0.19 ms. So the parent-death signal is set by a
  setpriv prefix, not preexec_fn.
- llama-server ignores one SIGINT while a request is in flight (no exit in 30 s); a second
  SIGINT after 2 s ends it in 2.5 s; with no request, one SIGINT ends it in 0.6 s. The mock
  with an open WebSocket ignores SIGINT for 60 s (aiohttp's default). Measured 2026-10-16.
- A Ctrl+C in the terminal reaches every process of the foreground group.

## 7. The design gate
**Ownership.** The supervisor owns the processes. A module describes its process with a pure
function that returns a ProcessSpec; the app collects every spec the settings need and
creates the supervisor with them; the supervisor launches, watches, relaunches and stops
them all. A module never launches or stops its own process; it may ask for a planned
restart through its handle. The app creates the supervisor and the ROS context at start and
destroys them last. The supervisor thread owns the table. Die's sequence is private to the
Die source file.

**Data in.** A ProcessSpec; a Die reason; a registered DieFn with a deadline; a listener's
topic and callback.

**Data out.** The rows (one atomic reference each); the process logs; Die's banner.

**Mutable state, and its owner.** The process table: the supervisor thread's; one timer
per entry (what is due next, and when), so one sweep fires every passed deadline. The rows:
one atomic store by the supervisor thread, read by the main thread. The command pipe and
queue: pushed by any thread, drained by the supervisor thread; two commands exist, a planned
restart and the quit. The launch lock: held for the stopping check, the fork, the pid store,
and the reap and pidfd close; taken by Die's step 4 before it reads the pids, and by the
quit before it sends any stop. The stopping flag, the supervisor's: set by Die or by the
quit under that lock; pending relaunches are dropped once it is set. The dying flag, Die's:
the first Die wins; later callers park.

**Threads.** The supervisor thread (one poll; three deadlines; never blocks on a child; the
probe calls are capped at 200 ms; it returns only after every child is reaped, since its
exit would send every child the parent-death signal). A ROS executor thread per listener.
Die's step threads, one per registered function, joined against the step's deadline.
Stops: no module stops its own process (SupervisorStop went, YAGNI); SupervisorDestroy puts the quit,
which sets the stopping flag under the launch lock and drops pending relaunches, then
waits once with one deadline for every child, joins; a listener's Destroy shuts its
executor, joins, destroys the node.

**Processes.** The six children; each in its own session; each with the parent-death signal;
each stopped by its stop policy: the stop signal, a retry signal after a delay where the spec
has one (llama-server), the grace, the kill.

## 7b. The gate, answered (modules/README.md, items 1 to 10)
1. The real-time path: the main thread reads six atomic references per frame (192 ns each,
   measured); nothing of this module runs on the main thread; a Die from it ends the run.
2. Not a sink; no app state.
3. Fault containment: every Die traced: a start-up miss; a laptop part past the budget
   (2026-09-22); an uncaught error (2026-09-19); a launch past MaxProcesses. Mid-flight each
   runs the hand-over first, on a thread that can send it (R1-4).
4. Buffer lifetimes: none held.
5. Types and units: every duration a uint64_t of nanoseconds as a macro, or a config
   constant; the caps named; no 64-bit value in an enum.
6. One home: Die, the supervisor, ROS, the preflight here; the specs in their modules.
7. The contract: the rows' states; the log path per process; the Die steps and caps; the
   total of 16.5 s.
8. The Python mapping: os.pidfd_open and selectors (poll, not select: select fails past fd
   1023); p.popen.wait() once the pidfd is readable, under the launch lock; subprocess.Popen with
   start_new_session and a setpriv prefix, no preexec_fn; the row an atomic reference to a
   tuple; the command queue a queue.Queue plus one byte on the command pipe; Die's steps on
   daemon threads joined with their caps; os._exit(1); the tries: Die's step loop, and the
   process-launch domain in util/guarded.py (Popen can raise when the binary is gone).
9. The cost budget: six reference loads per frame, 1.2 us; a fork 0.19 ms on the supervisor
   thread; the frame listener's 17 ms worst stall is the frame source's number.
10. gcc -Wall -Wextra on the header; the drawing passes the checker.

The failure matrix:
| failure | the module's state | what the record shows | the aircraft |
|---|---|---|---|
| a child crashes | RECOVERING, relaunched after 1, 2, 4 s; after 3: FAILED and Die (a laptop part) or WAITING (a phone part) | the rows; an event line | a laptop part's Die mid-flight: the hand-over first |
| a child never gets ready | its own stop, the grace, the kill; one crash counted | the row | none at start |
| a launch fails (the binary gone) | one crash counted; RECOVERING | the row; the log | none |
| a child ignores its stop | the grace, then the kill, logged; the row FAILED | the log line | none |
| a child holds a request at its stop | llama-server: the second SIGINT; the mock: its 1 s shutdown | the log line | none |
| Die from any thread | the steps on their own threads with caps; 16.5 s worst | the "die" event; the banner | the hand-over, 1 s cap |
| Die on the supervisor thread | the same: step 4 runs on the Die thread, not through the supervisor | the banner | the hand-over still runs |
| Die on the emergency thread | the hand-over never needs it: it sends the POSTs itself | the banner | the hand-over runs |
| a child stopped on purpose or by the quit | DOWN, or FAILED when killed; no relaunch, no count | the row | none |
| the quit and Die's step 4 at once | step 4 skips every child with a stop sent; nobody reaps twice | the banner | the hand-over first |
| a Die step calls Die | it parks; its join times out; the next step runs | the banner | the hand-over ran first |
| a Ctrl+C at the terminal | no child sees it; the app: open point 1 | | by the quit or by Die |
| SIGKILL of the app | the parent-death signal ends every child | nothing | the phone's own failsafe |
| the app's ROS context dies | the three listeners stop; the children's own contexts are untouched | the rows of the keys, the mic and the video stay as they are; the app's rows for them show no messages | none |

## 8. The notes that did not make the header
- **Why Die registers steps instead of calling modules.** Runtime is the floor; it cannot
  depend on the platform client above it. Rejected: Die calling the client directly.
- **Why each step runs on its own thread.** Python cannot interrupt a blocked C call; a join
  with a timeout is the only cap. If no thread can be started (the OS thread limit, a
  RuntimeError from Thread.start), the function runs on the Die thread, uncapped: a stop
  sent late beats a stop never sent (the second Gemini review). Rejected: an uncapped step;
  a cap by cooperation only.
- **Why step 4 is Die's own.** The supervisor thread may be the one that called Die, or may
  be parked behind the first Die. Rejected: a stop-all command to the supervisor thread.
- **Why a pidfd per child, no signal handler.** Measured: a handler on the main thread saw an
  exit 665 ms late behind a C call; a pidfd 0.54 ms after it; waitpid(-1) stole 50 exits
  from subprocess.run. Rejected: the SIGCHLD handler; waitpid(-1); polling every 0.5 s (SUP1).
- **Why every fork on the supervisor thread.** The parent-death signal follows the forking
  thread; a fork elsewhere races the reap. Rejected: a fork on the caller's thread.
- **Why setpriv, not preexec_fn.** preexec_fn is unsafe with threads and forces a 103 ms fork
  that stalls the main thread 48 ms; setpriv keeps the 0.19 ms vfork path. The window: a
  thread that ends before setpriv runs leaves the child alive; the supervisor thread lives
  until step 4 is done. Carried: our C++ nodes also exit when getppid() is 1.
- **Why each child in its own session.** A terminal Ctrl+C would stop all six and the
  supervisor would count six crashes and relaunch them while the app dies. Rejected: the
  shared group.
- **Why a kill is still in the design.** A process that ignores its stop for 10 s holds the
  GPU or the camera; the next run cannot start. The kill is the logged last resort (PROC2).
- **Why one atomic reference per row.** Two stores tear: a new state with the old detail in
  a one-shot chat line. One reference to an immutable pair costs less (192 against 357 ns).
- **Why no stop-message method.** Our SAM3 server handles SIGINT like the other five, with
  its own handler that sets its stop event; the "stop message" was never the owner's
  ruling. Rejected: StopMethod, StopRequestFn.
- **Why the hand-over sends the POSTs itself.** Each step runs on a short-lived thread, so
  "am I the emergency thread" is never true there; and the emergency thread may be the one
  inside Die. Its own connection and the phone's concurrent server make it safe. Rejected:
  waking the emergency thread.
- **Why the reap goes through Popen.** os.waitpid behind Popen's back leaves it thinking the
  child runs and prints a ResourceWarning at collection (measured, five relaunches).
- **Why no asyncio handler.** The rev5 phone listener is a plain TCP thread; no loop exists.
- **Why the probe after every launch.** A relaunched llama-server loads 15 to 60 s; a row UP
  before it can serve is a lie. The probe is /health under 200 ms; the L1 warm-up runs after
  UP on the app's start thread (open point 5).
- **The CPU check and a restricted machine.** PRF5 said "unless we are inside a VM/Container,
  this constant should be fine". The check is a config value, on by default. A CI runner or
  a container with a CPU quota turns it off in config; it is not a flight machine. The test
  suite never runs the preflight, so the tests are unaffected either way.
- **How a child gets its state.** A child is a separate program. Nothing of the app's
  memory crosses to it. It gets exactly four things: its command line (the spec's argv: the
  program and its arguments, built from config), its environment (the spec's env: the native
  library path, PULSE_SERVER for the ASR node), its standard output and error (the log file
  the supervisor opened), and whatever it reads by itself (the model file named on its
  command line; the shared-memory frame buffer by the name on its command line; a ROS 2
  topic). The supervisor forks and execs that command line, in its own session, behind the
  setpriv prefix. A relaunch runs the same command line again. The readiness probe is how
  the supervisor learns that the child reached its serving state.
- **The Python mapping, honest.** The supervisor about 200 lines (today 268); Die about 80
  (today 83); ros.py as today with rclpy imported inside RosCreate; deps.py with the ggml
  and the core checks added. The frame listener's 17 ms stall is carried to the frame source.

## 9. The tests the module ships with (`test/test_runtime.py`)
Change impact:
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| one supervisor thread, pidfds | how crashes are seen | no visible change | the supervisor tests rewritten |
| each child in its own session, SIGINT, the parent-death signal | how children end | yes, on purpose | new, on the real binaries |
| Die's four steps with caps | what a crash does mid-flight | yes, on purpose (RVW4) | new |
| one atomic reference per row | the status pane's source | no visible change | the status tests rewritten |
| the preflight's two new checks | the preflight | additive | new |
- `test_child_exit_wakes_the_thread_in_under_10_ms_while_main_is_in_a_c_call`.
- `test_foreign_child_keeps_its_exit_code`: subprocess.run beside the supervisor.
- `test_three_exits_at_once_are_all_reaped`; `test_launch_that_fails_counts_one_crash`.
- `test_budget_spent_dies_for_a_laptop_part_and_waits_for_a_phone_part`.
- `test_stable_run_resets_the_budget_at_the_exit` (TR9); `test_relaunch_delays_1_2_4`.
- `test_planned_restart_is_not_counted`; `test_relaunch_is_probed_before_up`.
- `test_never_ready_child_gets_its_stop_then_the_kill`.
- `test_llama_stops_with_a_request_in_flight` and `test_mock_stops_with_an_open_line`, on the
  real programs; `test_ros_node_stops_on_sigint`.
- `test_terminal_sigint_reaches_no_child`; `test_children_die_with_a_sigkilled_parent`
  (launched from the supervisor thread, the parent killed with SIGKILL).
- `test_row_is_one_immutable_pair` (the structure, not a time).
- `test_die_runs_the_steps_in_order_with_caps`; `test_step_stuck_in_a_c_call_is_left_behind`.
- `test_die_on_the_supervisor_thread_stops_the_children`; `test_no_fork_after_die_read_the_pids`.
- `test_die_on_the_emergency_thread_still_hands_over`; `test_second_die_parks`.
- `test_reaped_child_leaves_no_registered_fd` (the wakes after a crash: at most a few).
- `test_quit_counts_no_crash`; `test_planned_restart_stop_is_not_a_crash`.
- `test_step_4_skips_a_child_with_a_stop_sent`; `test_retry_signal_in_step_4`.
- `test_supervisor_thread_outlives_every_child`; `test_create_launches_every_spec`.
- `test_health_is_the_probe_and_the_warm_up_runs_after_up`.
- `test_quit_drops_a_pending_relaunch`; `test_reap_waits_for_the_lock_and_skips_once_stopping`.
- TOCTOU, pinned (the owner, RUN14): `test_signal_goes_to_the_pidfd_never_a_reused_pid`;
  `test_no_pidfd_is_closed_once_stopping`; `test_restart_command_after_stopping_is_refused`;
  `test_lock_timeout_path_logs_and_the_child_dies_with_the_parent`.
- `test_step_that_dies_is_cut_at_its_cap`; `test_die_at_start_up_runs_no_handover`.
- `test_step_runs_inline_when_no_thread_can_start`; `test_cpu_check_off_by_config`.
- `test_uncaught_error_in_a_thread_and_an_unraisable_die`.
- `test_preflight_dies_on_a_missing_package_mixed_ggml_fewer_cpus_and_a_quota`.
- `test_ros_listener_stamps_and_hands_on_from_its_own_thread`; `test_listener_destroy_order`.
