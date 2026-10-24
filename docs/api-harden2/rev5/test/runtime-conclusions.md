# The review of runtime: conclusions (2026-10-16)

Three rounds, one reviewer (general-purpose agent, model Opus 5.5), 44 findings: 20, 16, 8.
Every finding was accepted. The reviewer measured on this machine: a Python signal handler
saw a child's exit 665 ms late behind a C call; a pidfd saw it in 0.54 ms; waitpid(-1) stole
50 exits from subprocess.run; preexec_fn cost 103 ms a fork and stalled the main thread 48 ms;
llama-server ignored one SIGINT with a request in flight and exited on a second; the mock with
an open WebSocket ignored SIGINT for 60 s; a reaped pidfd left registered spun 700,000 times a
second; a 1080p ROS frame listener stalled the main thread up to 17 ms.

## What changed because of the review
- No signal handler: a pidfd per child, one poll on the pidfds and a command pipe, three
  deadlines; only the supervisor's own children are reaped, through Popen, under the launch
  lock; the pidfd unregistered and closed.
- Every fork on the supervisor thread, in its own session, with the parent-death signal set
  by a setpriv prefix; the thread outlives every child.
- Each stop through the pidfd; SIGINT for all six; llama-server's second SIGINT after 2 s;
  the mock's shutdown timeout 1 s; a stop sent means DOWN, never a relaunch.
- Die: every registered function on its own thread, joined against the step's deadline; the
  caps as constants; the hand-over sends the POSTs itself; the notify one direct POST /tts;
  step 4 on the Die thread, skipping children with a stop sent, never reaping; the quit sets
  the same stopping flag; the worst case 16.5 s.
- One atomic reference per row; the probe after every launch under a 200 ms call cap;
  readiness is /health; the warm-up after UP (an owner point); relaunch delays (an owner
  point); the core check against the affinity mask and the cgroup quota, never nproc; the
  ggml version check; rclpy imported inside RosCreate; no asyncio handler.
- The first draft would have: missed child exits behind C calls; stolen exits from other
  callers; relaunched children during Die; failed the hand-over when Die ran on the
  emergency thread; killed llama-server on every Die mid-flight; counted a terminal Ctrl+C
  as six crashes; spun after the first crash.

## What stays open for the owner (runtime.md section 4, six points)
1 Ctrl+C: the quit or Die; 2 the relaunch delays; 3 llama-server's second SIGINT; 4 a pidfd
per child instead of SIGCHLD; 5 the L1 warm-up after UP; 6 the launch lock against SK4.

## Cost
About 710k subagent tokens for the three rounds.
