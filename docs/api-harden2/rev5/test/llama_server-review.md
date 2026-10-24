# The review of the llama server module (rev5, module 5), started 2026-10-17

## Round 1: reviewer

Scope: docs/api-harden2/rev5/modules/05-llama_server/llama_server.md and llama_server.h.
Context read: brief.md sections 3 and 4, modules/README.md, 01-system-architecture.md,
runtime.h, runtime_internal.h, runtime.md, perf.h, perf_record_llama.h, and today's code
(gemma/server.py, gemma/client.py, perception2/vlm_client.py, perception2/vision.py,
perception2/engine.py, recognizer/recognizer.py, util/guarded.py).
Three lenses, in turn: storage and hardware; concurrency and real time; YAGNI and decoupling.

Setup of the measurements (2026-10-17, this machine: RTX 5070 Laptop 8151 MiB, 14 GiB RAM,
Python 3.12.3). The GPU lock was taken (`tools/lock.sh wait llama_review gpu`) and released.
llama-server ran from build/release/shared/dji/bin with today's argv(port, False), on ports
18995, 18996 and 18997. Every server was stopped with SIGINT (then SIGINT after 2 s); none
is left. The scripts are m1.py to m5.py, parent.py and m3.py in
/tmp/claude-0/-root-groundstation/8b8d4bb2-a5d5-4ffb-b72a-5f2d3c448a5c/scratchpad/llrev.
The planner requests used the real UNIFIED_PROMPT, UNIFIED_SHOTS, UNIFIED_GRAMMAR and
PLAN_WARM_UP_SENTENCE. The image requests used synthetic 1280x720 JPEGs at quality 80.
No command reached a drone or a phone.

The header compiles clean: `gcc -fsyntax-only -Wall -Wextra -x c -I ../perf -I ../runtime`,
and also with `-Wpedantic -std=c11`.

### Sources
1. The llama.cpp source of this build, `build/release/shared/dji/bin/llama_shared/src/
   llama_cpp_internal_shared/`. tools/server/server-http.cpp:164: the listen socket gets
   `SO_REUSEADDR`; `SO_REUSEPORT` only "if (reuse_port)". common/arg.cpp:3204: reuse-port
   "default: disabled".
2. Same source, server-http.cpp:256 to 268: "no endpoints are allowed to be accessed when the
   server is not ready"; the answer is 503 "Loading model". This covers /v1/models too.
3. Same source, common/common.h:623: `int32_t cache_ram_mib = 8192; // -1 = no limit, 0 -
   disable`. common.h:620: `cache_idle_slots = true; // save and clear idle slots upon
   starting a new task`.
4. Same source, server-context.cpp:40: `constexpr int HTTP_POLLING_SECONDS = 1;`. The response
   reader waits on the results with this period and checks `is_connection_closed` between.
5. Same source, server-task.cpp:410 and 443: `finish_reason = "length"` unless the model
   stopped by itself.
6. Same source, common/arg.cpp:3394: "Setting 'enable_thinking' via --chat-template-kwargs is
   deprecated. Use --reasoning on / --reasoning off instead." arg.cpp:3541: `--reasoning off`
   sets `enable_thinking` to "false".
7. Same source, server-queue.cpp:22 to 34: `post(task, front)` pushes to the back of the task
   queue; only a cancel goes to the front. No request priority exists.
8. Same source, vendor/cpp-httplib/httplib.h:26: `CPPHTTPLIB_KEEPALIVE_TIMEOUT_SECOND 5`
   (version 0.51.0). This confirms the 5 s idle close of the document.
9. https://docs.python.org/3.12/library/socket.html, settimeout: "The value argument can be a
   nonnegative floating-point number expressing seconds, or None. ... If zero is given, the
   socket is put in non-blocking mode." sendall: "The socket timeout is now the maximum total
   duration to send all data."
10. runtime.md point 5: the probe runs "200 ms a call, every 500 ms, after every launch".
    runtime.md, today: "The readiness probe polls every 0.5 s at start." No probe runs after UP.

### The claims confirmed (no finding)
| claim of the document | measured here |
|---|---|
| the first plan after a relaunch 1551 ms; the next 396 ms | 1546 ms (cache_n 0); 538 ms and 516 ms (cache_n 1999) |
| a POST during the load: 503 in 0.34 ms | 503 in 0.18 to 0.26 ms, with the 225 KB image body |
| GET /health while loading answers 503 fast | 82 calls, 1.0 ms max |
| the model load to the first 200, relaunch: 4.0 s | 4.3 s |
| the server closes an idle connection after 5 s | source 8 |
| "the parent-death signal ends an orphan" | parent SIGKILLed with a 3000-token request in flight: the orphan exited 1.42 s later ("cleaning up before exit", then "cancel task") |
| a timed-out request frees the slot | the queued plan was removed: "stop: cancel task, id_task = 705"; the slot never ran it |
| a foreign process cannot share port 18090 | a second bind fails with EADDRINUSE, with SO_REUSEADDR and with SO_REUSEPORT (source 1) |
| OPEN 1 arithmetic | 1551 + 396 = 1947 ms; 1551 - 396 = 1155 ms: correct |
| the argv fits kLlamaServerArgvMax | 26 entries plus the NULL: 27 of 32 |

### Findings

**R1-1. A hung llama-server is never detected. Its row stays UP and every request times out.** (high)
- Claim: the probe runs only from a launch to the first 200 (source 10). After UP, nothing
  asks the server again.
- Claim: a hung process keeps its pidfd unreadable. The supervisor sees no exit.
- Claim: the failure matrix row "a timeout (a hung server)" ends at LLAMA_TIMEOUT. It names no
  end state. The server stays hung for the rest of the flight.
- Why it matters: each plan then costs the operator 10 s and fails. Each image request costs
  20 s. The "llama" row shows UP. Nothing relaunches the server.
- Evidence (m1.py, SIGSTOP on the server as a stand-in for a hang): a TCP connect still
  succeeded in 0.191 ms (the kernel accepts into the backlog). GET /health timed out at 200 ms.
  A plan timed out at its 2 s timeout. The pidfd was not readable. After SIGCONT, /health
  answered 200 in 0.78 ms.
- Evidence (m1.py): /health answered 120 of 120 calls during an image request, 0.67 ms max.
  So a /health liveness probe after UP finds a stopped process. It does not find a hang inside
  the decode loop. The HTTP threads answer /health beside it.
- Change: name the window in gate item 11 and in the failure matrix.
- Change: add an OPEN point in the four-line form. The problem: a hung server is never
  relaunched. Now: every request times out; the row says UP. On "no" (that is, act): the app
  counts LLAMA_TIMEOUT results with no LLAMA_OK between them. At two, it calls
  SupervisorRestartOnPurpose with "llama hung". Recommended: that rule, after R1-2 bounds the
  queue wait, so a queued timeout is never read as a hang.
- Change: runtime's contract names SupervisorRestartOnPurpose "the video stall guard" and
  does not count it against the budget. A GPU that hangs again after every relaunch would then
  restart forever. Carry to runtime: count this restart, or cap it.

**R1-2. The server's queue is unbounded. A plan behind a few image requests times out.** (high)
- Claim: the pool has 8 threads (architecture section 3). Each vision job may send one image
  request. The server queues them all in arrival order (source 7).
- Claim: OPEN 2 says "The plan's 10 s timeout holds the wait." That holds behind about three
  image requests. It fails behind more.
- Claim: OPEN 2 says "An image request comes only when the operator asks for one." Today's
  config GATE=vlm and GATE=either send an image request at every highlight gate
  (perception2/vision.py:281, engine.py:136). The document does not say whether rev5 keeps it.
- Why it matters: the plan carries a voice command. A timeout drops that command with a
  "gemma_failed" line. The cause is a describe the operator asked a moment before.
- Evidence (m1.py): 6 image requests (128 tokens each) sent 20 ms apart, then a plan with a
  10 s timeout. The image requests ended at 2645, 4946, 7277, 9540, 11792 and 14051 ms. The
  plan raised TimeoutError at 10011 ms.
- Change: bound the image requests in flight to one. The vision module owns the image
  requests, so the bound is the vision module's: one lock for the image requests, taken with
  the request's own deadline. A plan then waits behind at most one image request: 3722 ms max
  alone (the document's measurement).
- Change: this document states the bound as a contract of its callers, in OPEN 2 and in gate
  items 1 and 11. It lists it as carried to the vision jobs.
- Change: OPEN 2's "Now" line states the measured case behind six image requests.

**R1-3. A reply cut at max_tokens is LLAMA_OK.** (medium)
- Claim: the server ends a reply at max_tokens with HTTP 200 and finish_reason "length"
  (source 5). The grammar does not stop that.
- Claim: the design reads only choices[0].message.content. A cut reply is LLAMA_OK with a
  broken text. The header's comment says a reply is "never cut". The server cuts it first.
- Why it matters: the recognizer reads a cut plan as "not a plan" and tells the operator "I
  did not understand". The true cause is the token limit. A cut describe loses its SHORT
  RESPONSE line.
- Evidence (m1.py): a plan with max_tokens 8 under UNIFIED_GRAMMAR returned HTTP 200,
  finish_reason "length", text `{"kind": "mission", "target`. An image request at 128 tokens
  also ended with "length".
- Change: read choices[0].finish_reason. "length" gives LLAMA_INVALID_REPLY, or a new
  LLAMA_CUT if the callers must tell it apart.
- Change: add finish_reason to gate item 7's reply keys. Add the case to
  test_invalid_reply_kinds.

**R1-4. The prompt cache in host RAM is not named. It grows to 8 GiB by default.** (medium)
- Claim: llama-server keeps a prompt cache in host RAM, 8192 MiB by default (source 3). The
  argv does not set it.
- Claim: the document's "a plan right after an image request: 429 ms (cache_n 1986)" depends
  on that cache. With -np 1, the image request replaces the slot's KV cache. The planner state
  comes back from host RAM.
- Why it matters: this machine has 14 GiB of RAM. The app, the SAM3 server and the other
  children share it. Every distinct image request adds one saved state.
- Evidence (m5.py, -lv 4): "prompt cache is enabled, size limit: 8192 MiB". The planner state:
  2029 tokens, 131.8 MiB. Each image prompt state: 310 tokens, 27.8 MiB.
- Evidence (m1.py): the server's RSS rose from 2550 to 3112 MiB over 11 distinct image
  requests, about 51 MiB each. It ended at 3499 MiB.
- Evidence (m2.py, `--cache-ram 0`): a plan after an image request took 1417 ms (cache_n 1).
  RSS rose 19 MiB per image request.
- Change: put `--cache-ram` in LlamaServerSettings, from config. A first value: 512 MiB. It
  holds the planner state and about 13 image states (unverified under the full app).
- Change: name the mechanism in section 6 and section 8. Add a failure-matrix row for host
  RAM. Add `test_argv_sets_the_prompt_cache_limit`.

**R1-5. T5 is described wrongly. The preflight check carried to runtime is itself a check-then-act.** (medium)
- Claim: T5 says a foreign server on 18090 "answers 200. The row then turns UP for the wrong
  process."
- Evidence (m2.py): with a foreign HTTP server on the port, our llama-server exited with code
  1 after 0.153 s. Its log: "couldn't bind HTTP server socket" at 0.090 s, before the model
  load. The supervisor's first probe comes at 500 ms. So the reap usually comes first.
- Why it matters: the usual result is a crash loop: three relaunches, then BUDGET_SPENT_DIE.
  Mid-flight, a bench that takes 18090 during the 1.5 s relaunch delay ends the flight by Die.
  The die reason says "llama", not "port taken".
- Claim: the free-port check in the preflight runs once at start. A bench can take the port
  later. It closes nothing in flight.
- Change: make the probe check identity. Add `--alias llama-<the app's pid>` to the argv. The
  probe reads GET /v1/models: 503 while loading (source 2), 200 with data[0].id equal to the
  alias when ready. A foreign server never matches.
- Evidence for the change (m5.py): GET /v1/models answered in 0.4 ms with
  `['llama-app-4242']`. During the load it answered 503 (m1.py).
- Change: rewrite T5 with the measured order. Keep the preflight check only as a clear early
  message. It is not the closure.

**R1-6. The remaining-time step can raise an exception or give the wrong kind.** (medium)
- Claim: section 8 says "the socket timeout is the remaining time before each step". The
  remaining time can be zero or negative after a slow step.
- Evidence (m4.py): `settimeout(-0.001)` raises ValueError. It is not an OSError and not an
  HTTPException, so util/guarded.py's except does not catch it. It reaches the crash hook,
  then Die, also mid-flight.
- Evidence (m4.py): `settimeout(0.0)` makes the socket non-blocking (source 9). A recv then
  raises BlockingIOError, not TimeoutError. The helper would report the wrong kind.
- Claim: in the C build, `timeout - (now - start)` on uint64_t wraps to about 2^64 ns.
- Claim: getresponse() reads the status line, the headers and the body in separate recv calls.
  Each gets the full value set before it. The total can pass the timeout if the reply comes in
  parts. llama-server sends a non-streamed reply at once, so this is a small window.
- Change: before each step, compute the elapsed time. If it is at or past the timeout, return
  LLAMA_TIMEOUT without the step. Otherwise set the remaining time.
- Change: add `test_a_spent_deadline_is_a_timeout_and_never_raises`.

**R1-7. A quit waits for every request in flight, up to its timeout.** (medium)
- Claim: Instance 1 joins every caller thread before LlamaClientDestroy, then stops the
  services. A caller blocked in a request cannot be woken. The client has no cancel.
- Why it matters: F1 during an image request holds the quit up to 20 s. During the warm-up it
  holds up to 30 s. The gate's "every thread and its stop" item names no bound.
- Evidence (the document's own measurement): SIGINT with a request in flight ends the client's
  request with RemoteDisconnected at 2.26 s. So the service's stop ends the wait sooner. The
  shutdown order runs it last.
- Change: state the bound in section 7 (the threads): a caller stops within its request's
  timeout.
- Change: add an OPEN point in the four-line form. The problem: a quit waits up to 20 s. Now:
  the join waits. On "no": the client keeps the socket of each request in flight. Destroy's
  first step calls shutdown(SHUT_RDWR) on each, and the callers return LLAMA_CLOSED.
  Recommended: accept the bound. The quit is rare, and the extra state costs a lock.

**R1-8. The server's cancel takes up to 1 s, not "about 0.6 s".** (low)
- Claim: T3, OPEN 2 and section 6 give 0.6 s from one run.
- Evidence: the server checks the connection once per HTTP_POLLING_SECONDS, 1 s (source 4). The
  cancel lands between 0 and 1 s after the close.
- Change: write "up to 1 s (the server checks the connection once a second)" in all three places.

**R1-9. The 98-byte payload rests on bounds the header does not state.** (low)
- Claim: the header types the counts as uint32_t and the times as float. The format of the
  floats is not stated.
- Evidence (m4.py, compact JSON): with counts at 4096 (the context) and times with one decimal,
  the worst payload is 97 bytes. With uint32 maxima it is 116 bytes. With raw float digits it is
  119 bytes. Both pass kPerfPayloadBytes (104). perf.h then writes {"cut":N}.
- Change: state in the header comment: the counts are at most m_contextTokens; the times carry
  one decimal (today's client rounds the same way). test_longest_payload_fits uses those maxima.
- Note for the owner: the key "ok" keeps a single bit. Section 5 calls the same loss a fault of
  today's code (item 3). The kind would fit in the 6 bytes left (`,"r":6`). The keys are fixed by
  TEL4, so this is the owner's call.

**R1-10. The document and the header disagree on four names.** (low)
- Evidence: Instance 1 and section 8 call `llama_server_process_spec(log_dir)`. The header has
  `LlamaServerProcessSpec(settings, logDir, text)`.
- Evidence: section 8 uses `LLAMA_SERVER_STOP_POLICY`. The header has `kLlamaServerStopPolicy`.
- Evidence: Instance 2 reads `config.LLAMA_PLAN_TIMEOUT_NS`. The header defines
  `LLAMA_PLAN_TIMEOUT_NS` itself.
- Evidence: the header says the probe's ctx is the LlamaServerSpecText. Section 8 binds the
  port with `partial(...)`.
- Why it matters: gate item 10 says the names were "checked by grep". They were not.
- Change: one name per item, in both files.

**R1-11. The header holds values that belong to its callers, and three unused items.** (low)
- Claim: LLAMA_PLAN_TIMEOUT_NS is the recognizer's value. LLAMA_VISION_TIMEOUT_NS is the
  vision jobs' value. The module uses only m_timeoutNs. The labels "plan" and "vision" are
  the callers' names too.
- Claim: the house rule says config/ is the one source of every value. A timeout defined in a
  module header is a second home.
- Claim: kLlamaServerSlots has no reader. The argv's "-np 1" is fixed text, not a setting.
- Claim: `#include <stddef.h>` has no use in the header.
- Claim: LlamaReply.m_req has no reader named in the document. The perf record already has req.
- Change: move the plan and vision timeouts to config under the callers' names. Keep only the
  warm-up timeout, or move it to the app. Drop kLlamaServerSlots and stddef.h, or name their
  reader. Name m_req's reader, or drop it.

**R1-12. This binary marks the thinking-off flag as deprecated.** (low)
- Evidence (every launch here): the first log line is "Setting 'enable_thinking' via
  --chat-template-kwargs is deprecated. Use --reasoning on / --reasoning off instead."
  (source 6).
- Claim: the owner's gotcha stands: thinking off needs both flags (2026-09-08, 12/12). This
  finding does not recommend against it.
- Why it matters: a later llama.cpp may drop the old form. Thinking would then come back with
  no error. test_argv_has_both_thinking_off_flags pins the old form only.
- Change: note in section 8 that the binary's own form is `--reasoning off`. Re-measure the
  12/12 check before any switch. Optional: a start-up check that the log has no
  "deprecated" line for this flag.

### The brief's section 4, checked
1. The spec function: present. The probe identity gap is R1-5.
2. The connection handling: one per request; closed; the rule "the reply is the truth" is
   stated. Sound.
3. The warm-up: present. The relaunch case is OPEN 1.
4. The request call: present. The cut reply is R1-3.
5. The timeouts: present. The hang is R1-1. The queue is R1-2. The deadline step is R1-6.
6. The perf record: present. The bounds are R1-9.
7. The failure matrix: present. Missing rows: a hung server's end state (R1-1), host RAM
   (R1-4), a cut reply (R1-3), the port taken during a relaunch (R1-5).

### Count
12 findings: 2 high (R1-1, R1-2), 5 medium (R1-3 to R1-7), 5 low (R1-8 to R1-12).

## Round 1: answer
Every finding is accepted. The changes are in llama_server.md and llama_server.h. The header
compiles with -Wall -Wextra -Wpedantic -std=c11, and the layout tool ran.
- **R1-1, accepted.** New OPEN 3, in the four-line form. The header shows the recommended
  rule: m_timeoutsInARow, kLlamaHungTimeoutsInARow = 2, and an onHung callback given at
  LlamaClientCreate. The app's callback calls SupervisorRestartOnPurpose. The window is T7 in
  gate item 11. The failure matrix has a "hung server" row. Carried to runtime: count this
  restart, or cap it.
- **R1-2, accepted.** The vision module keeps one image request in flight. This is a
  contract on the caller, carried to the vision review. OPEN 2 now states the six-request
  measurement and the bound. Gate item 1 names the queue's depth.
- **R1-3, accepted.** A new value, LLAMA_CUT, for finish_reason "length". It stays apart
  from LLAMA_INVALID_REPLY so the chat line can name the token limit. finish_reason is in
  gate item 7. New test: test_finish_reason_length_is_cut.
- **R1-4, accepted.** m_cacheRamMib in the settings; --cache-ram 512 from config
  (LLAMA_CACHE_RAM_MIB). A note in section 8, a matrix row, and a test. Which state the
  server drops first when the cache is full stays unverified.
- **R1-5, accepted.** The probe is now LlamaServerReadyProbe: GET /v1/models, true only for
  the alias llama-<the app's pid>. T5 is rewritten with the measured order. The preflight
  check stays carried, for a clear message only. This changes runtime's approved /health
  probe for this one process; section 8 names that.
- **R1-6, accepted.** The deadline test comes before each socket step. A spent deadline is
  LLAMA_TIMEOUT and never raises. The C form computes the elapsed time first, so nothing
  wraps. The code is in section 8. New test: test_a_spent_deadline_is_a_timeout_and_never_raises.
- **R1-7, accepted in part.** The bound is stated in section 7 (threads): a plan about
  0.5 s, an image request up to 3.7 s, the full timeout only for a hung server. No new open
  point. The reviewer's own recommendation was to accept the bound, and the realistic wait
  is seconds, not 20 s. The cancel in Destroy is listed as rejected.
- **R1-8, accepted.** "Within 1 s" in T3, OPEN 2 and the header.
- **R1-9, accepted in part.** The bounds are in the header comment: the counts at most
  m_contextTokens, the times with one decimal. The "r" key is not added. The keys do not
  change in the move (TEL4). Section 8 offers it to the owner.
- **R1-10, accepted in part.** A C-to-Python name table is in section 8. The Python names are
  the snake_case of the C names. The stop policy keeps the Python constant form,
  LLAMA_SERVER_STOP_POLICY. A grep now checks every header name in the document.
- **R1-11, accepted in part.** The three timeouts left the header. They are config values,
  each owned by its caller, with their numbers in section 7. m_req left the reply: it had no
  reader. stddef.h left. kLlamaServerSlots stays: the spec function writes it into "-np".
  Section 7 names that reader. The labels stay text: perf's approved table names them.
- **R1-12, accepted in part.** A note in section 8. The argv keeps both flags, because of the
  owner's gotcha. A switch needs the 12/12 check again first. The start-up check of the log
  is not added (YAGNI); the argv test pins the flags.

## Round 2: reviewer

Scope: the revision of llama_server.md and llama_server.h after round 1, checked against the
twelve round 1 answers. The same three lenses: storage and hardware; concurrency and real
time; YAGNI and decoupling.

Setup of the measurements (2026-10-17, this machine: RTX 5070 Laptop 8151 MiB, 14 GiB RAM,
Python 3.12.3). The GPU lock was taken (`tools/lock.sh wait llama_review2 gpu`) and released
after each run. llama-server ran from build/release/shared/dji/bin with today's argv(port,
False), plus `--cache-ram 512 --alias llama-4242`, on port 18997. Every server stopped on the
first SIGINT. None is left. The scripts are r2m1.py to r2m5.py in
/tmp/claude-0/-root-groundstation/8b8d4bb2-a5d5-4ffb-b72a-5f2d3c448a5c/scratchpad/llrev2.
The planner requests used the real UNIFIED_PROMPT, UNIFIED_SHOTS, UNIFIED_GRAMMAR and
PLAN_WARM_UP_SENTENCE. The image requests used synthetic 1280x720 JPEGs at quality 80,
32 tokens each. No command reached a drone or a phone.

The header compiles clean: `gcc -fsyntax-only -Wall -Wextra -x c -I ../perf -I ../runtime`,
and also with `-Wpedantic -std=c11`. Every header line is under 91 characters.

### Sources
1. The llama.cpp source of this build, tools/server/server-http.cpp:255 to 276. While
   `is_ready` is false, every path but the web frontend's gets 503 "Loading model". This
   covers /v1/models.
2. Same source, server-context.cpp:1407 to 1418: the model name is the first alias of a
   std::set. server-context.cpp:4152: every completion's "model" field is that name.
   server-context.cpp:5115: /v1/models gives it as "id". common/arg.cpp:2871 to 2880:
   --alias splits on commas.
3. Same source, server-task.cpp:1659 to 1736 (alloc): to make room, it removes the oldest
   entry (`states.pop_front()`). server-task.cpp:1741 to 1815 (load): the entry it restores
   leaves the cache (`states.erase(it_best)`). server-task.cpp:1818 (update): a size limit,
   then a token limit. server-context.cpp:1394: the token limit is n_ctx, raised to fit the
   size limit.
4. Same source, server.cpp:28 to 37: the second SIGINT calls `exit(1)` inside the signal
   handler. exit() runs the static destructors while the other threads still run.
5. Same source, server-context.cpp:1904 to 1912: a full context also sets STOP_TYPE_LIMIT.
   server-task.cpp:410: STOP_TYPE_LIMIT gives finish_reason "length".
6. runtime_internal.h, @m_stopSentNs: "0 until the stop signal was sent; an exit after it is
   DOWN". runtime.md line 38: "a stop sent or the stopping flag means DOWN and no policy; a
   planned restart relaunches". runtime.md failure matrix: "a child stopped on purpose or by
   the quit | DOWN, or FAILED when killed; no relaunch, no count".
7. 01-system-architecture.md line 41: "The thread pool of 8 for the vision jobs: the 9th job
   is refused; a stop flag per job."
8. https://man7.org/linux/man-pages/man3/mallopt.3.html, M_ARENA_MAX: the default arena
   limit is 8 times the number of cores on a 64-bit system. The variable MALLOC_ARENA_MAX
   sets the same limit.

### The measurements (no finding by itself)
| what | measured here |
|---|---|
| /v1/models while loading | 503 on 65 calls, 5.25 ms max; refused on 3 calls before the bind |
| /v1/models when ready, with --alias llama-4242 | data[0].id "llama-4242"; aliases ["llama-4242"] |
| the "model" field of every chat reply | "llama-4242", 5 of 5 plans |
| a plan cold; warm (cache-ram 512, alias) | 1547 ms (cache_n 0); 547 ms (cache_n 1999) |
| a plan after 10 image requests (cache-ram 512) | 520 ms, cache_n 1998: the planner state stayed |
| a plan after 16 more image requests | 1487 ms, cache_n 1: the planner state was evicted |
| the plan after that | 560 ms, cache_n 1999 |
| the server's log over those 26 image requests | 11 lines "removing oldest entry"; no token-limit line |
| RSS over 80 image requests, cache-ram 512 | 2289 MiB, then 3597 MiB from the 40th request on |
| RSS over 80 image requests, cache-ram 0 | 2289 MiB, then 2966 MiB from the 40th on |
| the same, MALLOC_ARENA_MAX=2, cache-ram 512 (50) | 2289 MiB, then 2948 MiB from the 30th on |
| the same, MALLOC_ARENA_MAX=2, cache-ram 0 (50) | 2288 MiB, then 2303 MiB |
| settimeout(1e-9), (1e-12), (1e-300), then recv | TimeoutError after 1.06 ms each; never BlockingIOError |
| the design's _count over six timeouts in a row | onHung fires at the 2nd only; the 3rd to 6th never fire |
| a stopped process (SIGSTOP), SIGINT, SIGINT after 2 s | alive at 10 s; only SIGKILL ended it (returncode -9) |

### The round 1 answers, judged
- **R1-1, accepted.** Landed in both files: m_timeoutsInARow, kLlamaHungTimeoutsInARow,
  LlamaHungFn, OPEN 3, T7, the matrix row. The rule has three new faults: R2-1, R2-2, R2-3.
- **R1-2, accepted.** The bound is in OPEN 2, gate item 1 and the picture. Instance 2 does
  not show the lock's deadline that R1-2 asked for. See R2-6.
- **R1-3, accepted.** LLAMA_CUT is in the header, gate item 7 and the tests. Agreed. One
  comment is too narrow: R2-9.
- **R1-4, accepted.** m_cacheRamMib, the argv, the note, the matrix row and the test landed.
  The RAM bound in the matrix is wrong by a factor of two: R2-5. The eviction is now
  measured: R2-8.
- **R1-5, accepted.** The alias probe landed in both files. T5 is rewritten with the
  measured order. The preflight's free-port check as a message only: agreed. It runs once.
  Its only job is a clear reason at start. The alias closes the probe's window. The probe
  still leaves the requests open: R2-4. The probe change itself overrides an approved
  ruling: R2-7.
- **R1-6, accepted.** Agreed. The test before each step is sound. A tiny positive remainder
  rounds up to 1 ns, then to a 1 ms poll (measured). It never gives BlockingIOError. R1-6's
  fourth claim got no answer: R2-10.
- **R1-7, accepted in part.** The reason holds for one request in flight. It fails for the
  vision jobs that wait on the image lock: each one sends its own request before it ends.
  See R2-6. The rejected cancel in Destroy: agreed.
- **R1-8, accepted.** "Within 1 s" is in T3, OPEN 2 and the header. Agreed.
- **R1-9, accepted in part.** Keeping the keys: agreed (TEL4; modules/README.md: "the keys
  do not change in the move"). An offer to the owner in section 8 is not an open point:
  R2-7.
- **R1-10, accepted in part.** LLAMA_SERVER_STOP_POLICY as the Python constant form: agreed.
  Two stale names remain: R2-9.
- **R1-11, accepted in part.** kLlamaServerSlots now has a reader. The labels as text:
  agreed, perf's table names them. The warm-up timeout has two owners: R2-9.
- **R1-12, accepted in part.** Agreed, with one note. The argv test pins our flags. It
  cannot see a new binary that changes what a flag does. The time to re-run the 12 of 12
  check is a llama.cpp update. No finding.

### Findings

**R2-1. After the first planned restart, a second hang is never detected.** (high)
- Claim: the rule fires only when the count reaches exactly 2. The C form: "only one sees
  2". The Python form: `next(self._streak) == K_LLAMA_HUNG_TIMEOUTS_IN_A_ROW`.
- Claim: nothing resets the count when onHung fires. Only a result other than LLAMA_TIMEOUT
  resets it.
- Claim: the LlamaClient lives across relaunches. So the count spans the relaunch.
- Claim: a reset needs a request that ends during the restart: LLAMA_CLOSED at the kill, or
  LLAMA_REFUSED or LLAMA_LOADING during the load. An operator who waits for the row to show
  UP sends none.
- Why it matters: the relaunched server hangs again, for example after a GPU fault. Its
  timeouts count 3, 4, 5. The rule never fires again. This is the R1-1 failure: every
  request times out for the rest of the flight, and the row says UP.
- Evidence (r2m4.py): the design's own _count over six timeouts in a row fires at the 2nd
  only.
- Change: the thread that reaches 2 resets the count before it calls onHung. In C: a
  compare-exchange from 1 to 0 in place of the fetch-add that gives 2. In Python: replace
  the streak, then call onHung.
- Change: the reset lets a second onHung fire during the restart's own grace. R2-3 makes the
  supervisor drop it.
- Change: add `test_a_second_hang_after_the_restart_calls_on_hung_again`.
- Change: this reset makes the runtime carry of OPEN 3 necessary, not optional. A server
  that hangs at every launch then restarts forever. The cap or the count must land in
  runtime.

**R2-2. A hung server's planned restart needs the kill. The approved runtime text then leaves the row DOWN or FAILED.** (high)
- Claim: a hung server rarely ends on SIGINT. A process under SIGSTOP runs no handler until
  SIGCONT. A decode loop that hangs in a GPU call never reads the stop flag. The second
  SIGINT calls exit(1) inside the handler (source 4). exit() runs static destructors beside
  the hung thread; whether it returns is unverified.
- Evidence (r2m5.py): a stopped process got SIGINT, then SIGINT after 2 s. It was alive at
  10 s. Only SIGKILL ended it.
- Claim: runtime's approved text says an exit after a stop sent is DOWN, and a killed one
  is FAILED, "no relaunch, no count" (source 6). A planned restart sends a stop. The header
  also has AFTER_EXIT_RELAUNCH_PLANNED. The order of the two checks is written nowhere.
- Why it matters: OPEN 3 depends on that order. Read literally, the hang restart leaves the
  "llama" row FAILED. Every later request is LLAMA_REFUSED for the rest of the flight. No
  Die comes, since no budget was spent.
- Change: OPEN 3 states its dependency: a planned restart relaunches also when the stop
  needed the kill. Carry it to runtime as a stated precedence: planned first, then stop sent.
- Change: carry two tests to runtime: `test_planned_restart_that_needs_the_kill_relaunches`
  and `test_planned_restart_after_a_sigstop_comes_up`.
- Change: the matrix row "a hung server" gives the recovery time: the two timeouts, then up
  to 10 s to the kill, then about 4 s of load (R1 measured 4.0 s to 4.3 s).

**R2-3. A planned restart can arrive while the supervisor already relaunches the server. Its meaning there is undefined.** (medium)
- Claim: onHung fires from any caller thread at any moment. Three states are possible when
  the command reaches the supervisor thread.
- Claim (a): its own stop is in progress. With R2-1's reset, a second onHung can fire in the
  10 s grace. A second stop would restart the timers or the reason.
- Claim (b): a crash relaunch is pending. A TIMEOUT computed just before a GPU fault crashes
  the server. The command then finds no child. The pidfd is closed. Its fd number may be
  reused by another child's new pidfd. A signal through it could reach the wrong child.
- Claim (c): the relaunched server still loads (STARTING). A restart then throws away a load
  that was nearly done.
- Why it matters: gate item 11 asks for every check-then-act. The decision "is the server
  still hung?" is made on a caller thread. The act runs later on the supervisor thread.
- Change: name it as T8 in gate item 11.
- Change: carry to runtime the rule that closes it. The supervisor thread applies a planned
  restart only when the entry is UP, with a live child and no stop sent. Otherwise it drops
  the command and logs it. The check and the act then run on the one thread that owns the
  table.
- Change: carry `test_planned_restart_while_recovering_or_stopping_is_dropped`.

**R2-4. After UP, the client trusts any server on the port. T5 is closed for the probe only.** (medium)
- Claim: the probe runs only from a launch to UP. After UP, the client sends each plan to
  whatever listens on 18090.
- Claim: a crash, then a foreign llama-server binds 18090 in the 1.5 s relaunch delay. Our
  relaunches fail to bind. For about 9 s (1.5, 3 and 4.5 s delays), plans go to the
  foreign server. Then the budget ends in Die.
- Claim: the plan carries our prompt and our grammar. A foreign llama-server with any model
  returns a grammar-valid plan. The recognizer can turn it into a mission.
- Why it matters: the failure matrix says "never touched" in the aircraft column. In this
  case a plan from another model can reach the aircraft.
- Evidence: every chat reply's "model" field equals the alias (5 of 5 plans; source 2).
- Change: LlamaClientCreate takes the alias. A reply whose "model" differs is
  LLAMA_INVALID_REPLY. The cost is one string compare on a field already parsed.
- Change: name it as a window in gate item 11, and add
  `test_a_reply_from_another_alias_is_invalid`.
- Change: if the author rejects the compare as YAGNI, the window must still be named, and
  the matrix row must stop saying "never touched".

**R2-5. --cache-ram 512 does not bound the server's RAM at 512 MiB. The server grows 1.3 GiB, then holds.** (medium)
- Claim: the matrix row says "host RAM: bounded by --cache-ram 512 MiB". The server's RSS
  rises 1308 MiB above its loaded size. It holds at 3597 MiB from the 40th image request.
- Evidence (r2m2.py, 80 image requests each): cache-ram 512 gives 2289 to 3597 MiB.
  cache-ram 0 gives 2289 to 2966 MiB. So the cache costs about 630 MiB at its limit.
  Another 677 MiB grows with no cache at all.
- Evidence (r2m3.py, MALLOC_ARENA_MAX=2, 50 image requests each): cache-ram 0 gives 2288 to
  2303 MiB. cache-ram 512 gives 2289 to 2948 MiB. So the 677 MiB is glibc's per-thread
  arenas (source 8): the HTTP threads each keep freed memory.
- Why it matters: this machine has 14 GiB. The app, the SAM3 server and the other children
  share it. The budget must use the measured 3.6 GiB, not 2.3 GiB plus 512 MiB.
- Change: the matrix row and the note "Why --cache-ram 512" state the measured plateau.
- Change: offer MALLOC_ARENA_MAX=2 in the spec's env. kLlamaServerEnvMax becomes 3. The
  server then holds at 2.95 GiB. Its effect on the plan time is unverified; measure it
  before the switch.

**R2-6. The image lock in Instance 2 has no deadline. Queued vision jobs then fill the pool and stretch the quit.** (medium)
- Claim: R1-2 asked for "one lock for the image requests, taken with the request's own
  deadline". Instance 2 shows `with image_request_lock:`, a wait with no bound.
- Claim: the pool has 8 threads, and the 9th job is refused (source 7). Jobs that wait on
  the lock hold pool threads. A hung server holds each one for its full 20 s in turn. Seven
  waiting jobs wait up to 140 s, and the pool refuses every new job meanwhile.
- Claim: the wait on the lock sits outside the request's 20 s timeout. VISION_LLAMA_TIMEOUT_NS
  then does not bound a vision job.
- Claim: R1-7's answer bounds the quit by one request. Each queued job sends its own request
  after the lock. A quit with three queued image jobs waits for three requests, not one.
- Change: Instance 2 takes the lock with the job's deadline: `acquire(timeout=...)`. On a
  miss the job ends FAILED without a send.
- Change: the job checks its stop flag after it takes the lock and before it sends.
- Change: both lines go into the carry to the vision review. Section 7's quit bound then
  holds: one request in flight, the rest end at the stop flag.

**R2-7. Three owner choices sit in notes and carries, not in the open points.** (medium)
- Claim: the probe on /v1/models replaces the /health probe. The owner approved /health
  (RUN14, runtime point 5). The brief's section 4 item 1 also says /health. Section 6 still
  quotes RUN14 as "/health is the probe".
- Claim: OPEN 3's "Carried to runtime: count this one, or cap it" changes runtime's approved
  "not counted against the budget". After R2-1 it is required, not optional.
- Claim: section 8 says of the "r" key "The owner may add it." That is a question for the
  owner, outside section 4.
- Why it matters: the rules say a recommendation is not a decision. A change to an approved
  ruling is the owner's to make. MOD2 puts every owner question in section 4, marked OPEN n
  in the header.
- Change: OPEN 4, the identity probe, in the four-line form. The problem: a foreign server
  can turn the row UP. Now: /v1/models with the alias. On "no": /health, and T5 stays open.
  Recommended: the alias.
- Change: OPEN 3 names the budget change to runtime as part of its "Recommended" line, with
  RUN14 named.
- Change: the "r" key becomes OPEN 5, or the sentence goes. Section 6's RUN14 row says what
  changes.

**R2-8. The eviction order is now measured. The planner state survives about 13 image requests between two plans.** (low)
- Claim: the author left "which state the server drops first" unverified.
- Evidence (source 3): the oldest entry goes first. A restored entry leaves the cache, and
  it comes back as the newest at the next save. So the order is by last use.
- Evidence (r2m1.py): the planner state survived 10 image requests (520 ms, cache_n 1998).
  It was evicted by 16 more (1487 ms, cache_n 1). (512 - 132) / 27.8 gives 13 image states.
- Why it matters: a kept Gemma highlight gate sends an image request at every gate. About
  14 gates between two plans make the next plan cold, once: about 1 s more.
- Change: replace "unverified" in section 8 with the order and the measured count. Keep
  512 MiB. A larger value costs RAM (R2-5) for a 1 s gain once per burst.

**R2-9. The document and the header disagree in five places.** (low)
- Evidence: section 7, Data out: "A LlamaReply: the result, the request number, ...". R1-11
  removed m_req from LlamaReply.
- Evidence: section 6's RUN14 row: "/health is the probe" (see R2-7).
- Evidence: the header's @LLAMA_CUT: "the reply stopped at m_maxTokens". A full context
  gives the same finish_reason "length" (source 5).
- Evidence: section 7 gives LLAMA_WARM_UP_TIMEOUT_NS to "the app". Instance 1 has the
  recognizer build the whole warm-up request, its timeout included.
- Evidence: the Python mapping keeps `self._timeouts`, read only once to seed
  `self._streak`. The name table lacks K_LLAMA_HUNG_TIMEOUTS_IN_A_ROW.
- Change: one name and one owner per item, in both files. @LLAMA_CUT: "at m_maxTokens or at
  the context's end".

**R2-10. The header says the call blocks "up to m_timeoutNs". The bound is per socket step, not per call.** (low)
- Claim: R1-6's fourth claim got no answer. getresponse() reads the status line, the headers
  and the body in separate recv calls. The helper sets the remaining time once, before
  getresponse(). Each recv inside it may then wait that whole remainder.
- Claim: section 8 says the one recv carries the whole wait. That holds while the server
  sends the reply at once. It fails when a reply stalls mid-body, for example a server that
  hangs while it writes.
- Change: the header says "up to m_timeoutNs before the reply starts". Section 8 names the
  case. A hard bound would need a recv loop under the helper's own deadline; that is a
  choice for the author, and its cost is small.

### Count
10 findings: 2 high (R2-1, R2-2), 5 medium (R2-3 to R2-7), 3 low (R2-8 to R2-10).

## Round 2: answer
Every finding is accepted; two in part. The header compiles with -Wall -Wextra -Wpedantic
-std=c11, and the layout tool ran.
- **R2-1, accepted.** The timeout that brings the count to 2 exchanges it to 0, then calls
  onHung. A second hang after the restart fires again. The header's @m_timeoutsInARow says
  so. The Python form resets the streak before the call. New test:
  test_a_second_hang_after_the_restart_calls_on_hung_again.
- **R2-2, accepted.** OPEN 3's recommendation now lists the precedence as change 1 to
  runtime: a planned restart relaunches also when its stop needed the kill. The two tests
  are carried. The matrix row gives the recovery time.
- **R2-3, accepted.** T8 in gate item 11. The closing rule is change 2 to runtime in OPEN 3:
  the supervisor thread applies a planned restart only when the entry is UP with a live
  child and no stop sent. The test is carried.
- **R2-4, accepted.** LlamaClientCreate takes the alias. A reply whose "model" differs is
  LLAMA_INVALID_REPLY. The alias moved from the spec text into LlamaServerSettings, so the
  spec and the client read the one value. T9 in gate item 11; the matrix row no longer
  claims more than the compare gives.
- **R2-5, accepted in part.** The matrix row and section 8 state the measured plateau,
  3.6 GiB. MALLOC_ARENA_MAX=2 is named and not taken: its effect on the plan time is not
  measured, and the app's whole RAM budget is not measured either.
- **R2-6, accepted.** Instance 2 takes the image lock with the job's time left, and checks
  the stop flag after it. Both are carried to the vision review. The quit bound of section 7
  then holds.
- **R2-7, accepted in part.** OPEN 4 is the identity probe, in the four-line form, with RUN14
  named. OPEN 3's recommendation names its three changes to runtime's approved contract.
  The "r" key offer is dropped, not made an open point: the move rule fixes the keys.
- **R2-8, accepted.** Section 8 states the least-recently-used order and the measured
  counts. 512 MiB stays.
- **R2-9, accepted.** The request number left Data out. The RUN14 row says what OPEN 4
  changes. @LLAMA_CUT names the context's end. LLAMA_WARM_UP_TIMEOUT_NS is the recognizer's,
  since it builds the warm request. The Python mapping lost self._timeouts; the name table
  has K_LLAMA_HUNG_TIMEOUTS_IN_A_ROW.
- **R2-10, accepted.** A hard bound: the body is read in a loop of read1() calls, with the
  deadline test before each. The header says each read waits only the time left. New test:
  test_a_reply_that_stalls_mid_body_ends_at_the_deadline.

## Round 3: reviewer

Scope: the landing check of llama_server.md and llama_server.h after the round 2 answer.
Checked against the ten round 2 findings, brief.md sections 3, 4, 5 and 8, modules/README.md,
runtime.h, runtime_internal.h, runtime.md and perf.h. No GPU measurement was needed. One
Python check ran in the scratch folder (llrev3). No command reached a drone or a phone.

### The deterministic checks
- `gcc -fsyntax-only -Wall -Wextra -x c -I ../perf -I ../runtime llama_server.h`: clean.
- The same with `-Wpedantic -std=c11`: clean.
- `tools/style/header_layout.py` on a copy of the header: no change.
- Every header line is under 91 characters.
- No em-dash and no banned word in either file.
- Every header name appears in the document, but LlamaServerSettings and the field names.
- Every name of the document that looks like a header name is in the header or in config.

### The round 2 answers, landed or not
- **R2-1.** Landed in the header and in the Python form. T7 states a third rule: R3-3.
- **R2-2.** Landed. OPEN 3 change 1, the two carried tests, and the recovery time in the matrix.
- **R2-3.** Landed. T8, OPEN 3 change 2, and the carried test.
- **R2-4.** Landed in both files. Gate item 7 does not list the "model" key: R3-5.
- **R2-5.** Landed. The 3.6 GiB plateau is in the matrix and in section 8.
- **R2-6.** Landed. The new lock line has a fault of its own: R3-2.
- **R2-7.** Landed. OPEN 4 is in the four-line form. OPEN 3 names its three runtime changes.
- **R2-8.** Landed. Section 8 states the least-recently-used order and the counts.
- **R2-9.** Landed in all five places.
- **R2-10.** Landed in the header, in section 8 and in the tests. getresponse() still reads
  the status line and the headers under one remainder. A server that stalls between two
  header lines is not a real case. No finding.

### Findings

**R3-1. OPEN 3 change 3 does not stop a loop. The 60 s stable reset clears the count first.** (medium)
- Claim: OPEN 3 counts a hang restart against the budget. It says a server that hangs at
  every launch then "ends in Die, not in a loop".
- Evidence: runtime.h says "up SUPERVISOR_STABLE_NS: the restart count goes back to 0".
- Evidence: runtime_internal.h says the policy "resets the count first" when the child was up
  for 60 s.
- Claim: the hang rule needs two timeouts in a row. The recognizer worker sends one plan at a
  time, so two plans take at least 20 s.
- Claim: after a relaunch, no warm-up runs (OPEN 1). The first request comes when the
  operator speaks.
- Claim: the stop then takes up to 10 s. So the up time at the exit is the operator's delay
  plus 22 s to 30 s.
- Why it matters: the count reaches the budget only when the operator speaks within about
  30 s of each UP. Otherwise the restart loop never ends. Each cycle costs two lost commands
  and about 34 s.
- Claim: SupervisorRestartOnPurpose takes only a reason string. It cannot mark a hang restart
  as counted and the video stall guard's restart as free.
- Change: OPEN 3 states the condition and the cost of one cycle.
- Change: OPEN 3 names the API change to runtime. Either every planned restart counts, or the
  call gains a "counted" argument.
- Change: if the owner wants Die for a server that keeps hanging, carry one more rule to
  runtime. A hang restart is exempt from the stable reset. The other choice is to accept the
  loop.

**R3-2. Instance 2 takes the image lock with a timeout that can be negative. That raises ValueError.** (medium)
- Claim: Instance 2 calls `image_request_lock.acquire(timeout=job.time_left_s())`. A job whose
  deadline passed during its earlier steps has a negative time left.
- Evidence (llrev3, Python 3.12.3): `acquire(timeout=-0.5)` and `acquire(timeout=-1e-9)` raise
  "ValueError: timeout value must be positive".
- Evidence (the same run): `acquire(timeout=-1)` waits with no bound. A time left of exactly
  -1.0 s then blocks the pool thread forever.
- Why it matters: this is R1-6's fault again, in the code that is carried to the vision
  review. The exception reaches the crash hook and Die, or it is lost in the pool's future.
- Claim: the request then gets the full VISION_LLAMA_TIMEOUT_NS. A job that waited on the lock
  then ends up to 20 s past its deadline.
- Change: Instance 2 tests the time left first. A spent deadline ends the job FAILED with no
  wait. Otherwise it waits only the time left.
- Change: the request's m_timeoutNs is the smaller of VISION_LLAMA_TIMEOUT_NS and the time left.
- Change: add both lines to the carry to the vision review.

**R3-3. Three places state three rules for the hang count. T7's rule can lose a hang.** (low)
- Evidence: the header's @m_timeoutsInARow says the timeout that brings the count to 2
  exchanges it to 0, "then calls m_onHung once". The call has no condition.
- Evidence: T7 says "only a thread that gets 2 back from the exchange calls onHung".
- Evidence: the Python `_count` calls on_hung after it resets the streak, with no condition.
- Claim: under T7's rule, two timeouts that race lose the fire. Thread A gets 2 from the
  fetch-add. Thread B gets 3. A's exchange returns 3, so A does not call. B saw 3, so B does
  not exchange. The count is 0, and both timeouts are gone.
- Why it matters: a hung server can time out a plan and an image request close together.
  The rule then fires two timeouts late.
- Change: one rule in all three places. The thread that gets 2 from the fetch-add exchanges
  the count to 0. It calls onHung when the exchange returns 2 or more. A 0 means a reply came
  between, so it does not call.
- Change: the state table of section 7 names the exchange beside the fetch-add and the store.

**R3-4. Gate item 3 gives the wrong death for a server that never gets ready.** (low)
- Claim: gate item 3 says the app dies at start "when the probe never sees 200 in 240 s".
- Evidence: runtime.md's matrix says a child that never gets ready gets "its own stop, the
  grace, the kill; one crash counted". The supervisor then relaunches it.
- Claim: with BUDGET_SPENT_DIE and three restarts, Die comes after the fourth launch. Each
  launch can take 240 s plus the 10 s stop. The total is about 17 minutes (unverified).
- Claim: Instance 1's `die("llama-server never named itself ...")` is then unreachable. The
  supervisor's Die comes first, and SupervisorWaitUntilReady never returns false for a
  BUDGET_SPENT_DIE process.
- Why it matters: the owner reads a 4-minute start-up death. The real wait is four times as long.
- Change: gate item 3 and the matrix state the counted crash, the relaunches and the total.
- Change: Instance 1 either drops the die line, or says that the line is the WAITING and
  FAILED case only.

**R3-5. Stale or missing lines.** (low)
- Gate item 7 lists the reply keys read. It lacks "model", which T9 and @LLAMA_INVALID_REPLY
  read.
- Section 7, Ownership: "the probe reads the port from it". The probe reads the alias too.
- OPEN 4, "On no": it says /health. It does not say whether the reply's "model" check goes
  too. T9 is closed by that check, not by the probe.
- The header gives the "warm" row's values from LlamaClientWarmUp only. The Python form starts
  it at STARTING "cold". In C, LlamaClientCreate must store a first pair. Otherwise the main
  thread's first load reads NULL.
- LLAMA_WARM_UP_TIMEOUT_NS belongs to the recognizer (section 7). Its prefix names the llama
  module. The recognizer's other value is PLAN_TIMEOUT_NS.
- Section 7, the constants: "the model loads in 4 s to 60 s". 4.0 s and 15.7 s are measured.
  60 s is not, so it needs "unverified".
- Change: fix the six lines. Then grep both files for "reply keys", "port from" and "60 s".

**R3-6. The deliverable rules, three misses.** (low)
- Section 1: the job sentence has "and". modules/README.md says such a module splits. The
  brief scopes both parts into one module, so only the sentence changes. An example: "The
  module is the app's one way to reach llama-server: its process spec and one request at a
  time."
- STE: some sentences pass 20 words. T8's second sentence has 45. The quit sentence in
  "Threads" has 30. The vision carry in section 9 has 31.
- Line width: two prose lines are not wrapped (line 9, 115 characters; gate item 5, 159). In
  the Python blocks, ten lines pass 89 characters (for example 65, 107, 549, 556, 561).
- Change: split the sentences, wrap the lines, and run the layout check on the Python blocks.

### The deliverable rules, checked
- The section order follows MOD1: 1 to 9, with the gate answers and the matrix in 7b.
- Each open point has the four lines. The header marks OPEN 1 to OPEN 4.
- The header uses an anonymous typedef enum with its comment block above. No enum comment
  holds a comma.
- Every 64-bit constant is a UINT64_C macro. The shared values are _Atomic. Every field has
  the m_ prefix.
- Gate items 1 to 11 are answered. Items 2 and 5 to 8 give the mechanism without a "Tried"
  line. The proof is still there, so no finding.
- The failure matrix is present, with the hang, host RAM and foreign-server rows.

### Count
6 findings: 0 high, 2 medium (R3-1, R3-2), 4 low (R3-3 to R3-6).

### Round 4
Not needed. R3-1 changes the text of an open point and adds one carry to runtime. R3-2 is
two lines of the caller's code. R3-3 to R3-6 are local text fixes. The manager can check
them by reading.

## Round 3: answer
Every finding is accepted. R3-1 takes another path than the reviewer proposed. The header
compiles with -Wall -Wextra -Wpedantic -std=c11; the layout tool leaves it unchanged.
- **R3-1, accepted, another path.** Runtime's budget cannot stop a hang loop: a planned
  restart is not counted, and 60 s up resets the count. So OPEN 3 no longer asks runtime
  to count it. The app's onHung callback counts the hang restarts of the run. The fourth
  hang calls Die, with the hand-over first mid-flight. Runtime's API does not change. OPEN 3
  states the cost of one cycle. New app test:
  test_fourth_hang_restart_dies_with_the_handover_first.
- **R3-2, accepted.** Instance 2 tests the deadline before the subtract. A spent deadline
  ends the job FAILED with no wait. The lock waits only the time left. The request's
  timeout is the smaller of VISION_LLAMA_TIMEOUT_NS and the time left. All three lines are
  in the carry to the vision review.
- **R3-3, accepted.** One rule in the header, T7 and the Python form: the thread that gets
  2 exchanges the count to 0, and calls onHung when the exchange returns 2 or more.
- **R3-4, accepted.** Gate item 3 states the counted crash, the three relaunches and the
  total (about 17 minutes, unverified). Instance 1's die line now covers FAILED and
  WAITING only, with a comment.
- **R3-5, accepted.** "model" is in gate item 7. The probe reads the port and the alias.
  OPEN 4's "On no" says the reply check goes too. The header gives the "warm" row its
  first value (STARTING "cold" at Create). The warm-up timeout is PLAN_WARM_UP_TIMEOUT_NS,
  the recognizer's. The load time says 4.0 s and 15.7 s measured, 60 s unverified.
- **R3-6, accepted.** The job sentence has no "and". The long sentences are split. Every
  prose and code line is 89 characters or less; only table rows are longer.

## Conclusions
Three rounds, three reviewers (general-purpose agents, model opus), 28 findings: 12, 10
and 6. Every finding was accepted; some in part, each with its reason above.

**Agreed (the design after the review).**
- One TCP connection per request. The server closes an idle keep-alive after 5 s, so a
  kept connection is stale most of the time. A new connect costs 0.021 ms.
- No client lock. The server's one slot and its queue serve in arrival order. The vision
  module keeps one image request in flight.
- The client reads no status row: the reply is the truth. A dead server answers refused
  in 0.72 ms; a loading one 503 in 0.34 ms.
- One request function with a result enum: OK, REFUSED, LOADING, CLOSED, TIMEOUT, CUT,
  HTTP_ERROR, INVALID_REPLY. A false return, never an exception.
- A deadline test before each socket read; the body read in a loop; a spent deadline is a
  timeout.
- --cache-ram 512 keeps the planner prompt warm after image requests (429 ms against
  1417 ms without the cache).
- The perf record PERF_LLAMA_REQUEST with the approved keys; the longest payload 98 bytes.

**Open for the owner (llama_server.md section 4).**
1. OPEN 1: a warm-up again after a relaunch. Recommended: at start only.
2. OPEN 2: a plan behind an image request. Recommended: arrival order with the bound.
3. OPEN 3: a hung server. Recommended: two timeouts in a row ask a planned restart; the
   fourth hang dies. It needs two changes to runtime's approved contract.
4. OPEN 4: the identity probe. Recommended: --alias llama-<pid> on /v1/models, and each
   reply's "model" checked. It changes RUN14's /health probe.

**Changed because of the review.**
- The first draft would have: kept a hung server UP for the whole flight; let six image
  requests time a plan out; read a cut reply as a success; let the prompt cache grow to
  8 GiB; trusted any server on the port; raised ValueError on a spent deadline; and never
  detected a second hang after the first restart.

**Carried to other modules.**
- runtime: a planned restart relaunches also after the kill; it applies only when UP; a
  free-port check in the preflight for a clear message; whether m_env merges with the app's
  environment; util/guarded.py's HTTP helper returns the failure kind and runs the
  deadline loop.
- the vision jobs: one image request in flight; the lock with the time left; the stop flag
  after the lock; the request's timeout capped by the time left; whether rev5 keeps the
  Gemma highlight gate.
- perf: perf_record_llama.h moves into llama_server.h and is deleted at the move.

## After the rounds: how OPEN 3 went wrong (2026-10-18)
The owner, on the hang rule: "This is way too fucking complicated, seemingly for no reason"
and "I need to understand why this happened again. I don't quite understand how this
derailed quite like this."

The chain:
1. The first draft's failure matrix had a row "a timeout (a hung server)". The author wrote
   it; the brief asked only for "a timeout".
2. R1-1 asked what happens after that row. The reviewer made a hang with SIGSTOP and rated
   it high. No real hang was ever recorded.
3. The author accepted R1-1 and built a mechanism: a count, a callback, a planned restart.
4. Round 2 reviewed the mechanism, not the need. It found three true faults in it (R2-1,
   R2-2, R2-3). Each was fixed by more mechanism, two of them in runtime.
5. Round 3 found that runtime's 60 s reset defeats the fix (R3-1). The author added a death
   at the fourth hang.

The causes and the advice: 05-llama_server/brief.md, "SEALED: the advice" (lifted after
the manager's own mitigation) and "REV7 RECORD" (the comparison and the merged text).
- The owner's rulings (2026-10-18): "D3 - Drop" (the hang rule removed) and "D8 - Drop" (the
  per-read deadline loop removed). What to change in the reviews is open: ledger REV7 holds the procedure.
- The owner's other rulings (2026-10-18), after these conclusions: D1, a warm-up after every
  relaunch; D2, -np 9 --kv-unified -c 8192; D4, a Unix domain socket in place of TCP and
  the alias. The "Agreed" and "Open" lists above predate them; 05-llama_server/llama_server.md
  section 4 is the current state.
- After that (2026-10-18): PHN1 applied. The client holds no perf tracer; each caller times
  its own request. LlamaRequest lost m_label, and LlamaClient lost m_perf and m_nextReq.
  The "Agreed" line about the perf record above still holds for the keys, not for who
  writes the record.
