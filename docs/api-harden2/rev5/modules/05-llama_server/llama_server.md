# llama_server: the llama-server process and its client (rev5 module 5, 2026-10-17)

The header is `llama_server.h`. The design document is `../../01-system-architecture.md`
(sections 2, 3, 8, 9). Below it: the recorder (perf and telemetry folded into it, RCD1) and runtime, approved. The review
record is `../../test/llama_server-review.md`. State: three reviewer rounds taken (12, 10
and 6 findings); the owner reviewed it on 2026-10-18 and ruled D1 to D4 and D8 (section
4). Open: the whole module's approval, and P1 (section 4).

## 1. The job, in one sentence
The module is the app's one path to llama-server: from its launch spec to each request.

## 2. The picture
```
 THE APP PROCESS                                              llama-server (a child)
 +---------------------------------------------------+       +--------------------------+
 | supervisor thread (runtime)                       |       | HTTP on a Unix socket:   |
 |   remove llama.sock; launch; pidfd                |------>|   <session>/llama.sock   |
 |   probe: GET /health, 200 ms cap, every 500 ms    |------>|   503 while the model    |
 |   stop: SIGINT, SIGINT after 2 s, kill after 10 s |------>|   loads, then 200        |
 |   writes the "llama" row                          |       |                          |
 |                                                   |       | POST /v1/chat/completions|
 | start thread (app): WaitUntilReady, then          |       |   9 slots (-np 9): one   |
 |   LlamaClientWarmUp ---- one connection --------->|------>|   per caller, none waits;|
 |   writes the "warm" row                           |       |   one shared KV pool,    |
 | recognizer worker: a plan                         |       |   --kv-unified -c 8192   |
 |   LlamaClientRequest --- one connection --------->|------>|                          |
 | pool thread (a vision job): an image request,     |       | closes an idle keep-alive|
 |   up to 8, one per pool thread                    |       |   connection after 5 s   |
 |   LlamaClientRequest --- one connection --------->|------>|                          |
 |                                                   |       | a prompt cache in host   |
 |                                                   |       |   RAM, --cache-ram 512   |
 |                                                   |       +--------------------------+
 | main thread: reads the "llama" and "warm" rows    |
 |   each frame (one atomic load each); sends nothing|
 | each caller times its own request: MonotonicNow()      |
 |   around the call -> RecordLlamaRequest (its tracer)|
 +---------------------------------------------------+
```
1. **The process.** The supervisor owns it (RUN9). This module gives one pure function
   that returns the ProcessSpec. The spec holds the command line from config and the
   native library path. It also holds the ready probe, the 240 s ready timeout, the stop
   policy and BUDGET_SPENT_DIE. The server listens on a Unix domain socket in the session
   folder, so no other process shares its address (D4).
2. **The client.** A plain struct the app owns. It opens one connection to the socket per
   request and closes it before it returns. No socket lives between requests. It never
   reads a status row. The reply, or its absence, is the truth.
3. **A slot per caller.** The server has 9 slots: the one planner and the pool of 8
   vision jobs (D2). No request waits for another. They share the GPU, so each slows as
   the load grows. The client has no lock and no queue.
4. **The warm-up.** The app's start thread sends the planner's warm sentence after the
   "llama" row is UP. The recognizer builds that request (REC1). After every relaunch the
   recognizer worker sends it again (D1). The client's "warm" row shows the result.
5. **The record.** The client holds no tracer and records nothing (PHN1). Each caller
   reads MonotonicNow() around its call and writes one PERF_LLAMA_REQUEST record with the
   helper RecordLlamaRequest, timed in the app from the request to the reply (RVW5).

## 3. How a caller uses it: two instances, in the Python of the build
**Instance 1: the app's start.**
```python
# app/main.py, the services, in order
settings = llama_server_settings_from_config(session.dir)   # the socket path inside
specs = [llama_server_process_spec(settings, log_dir), ...]   # pure: a spec out
supervisor = supervisor_create(specs)                   # launches it; the probe runs
server = supervisor_process(supervisor, LLAMA_SERVER_NAME)

llama = llama_client_create(settings.socket_path)    # no tracer (PHN1)

# false only for FAILED or WAITING; a laptop part's spent budget is the supervisor's Die
if not supervisor_wait_until_ready(supervisor, server):
    die("llama-server failed at start")

warm = llama_client_warm_up(llama, plan_warm_up_request())   # the recognizer builds it
if warm.result is not LLAMA_OK:
    die(f"the warm-up failed: {warm.result.name}")      # a start-up check

# the main thread, each frame: the "llama" row back to UP after a relaunch (D1)
if llama_row_changed and llama_row.state is UP and llama_row.was is RECOVERING:
    route_queue.put(WarmUp(plan_warm_up_request()))     # the recognizer worker sends it

# app shutdown: the modules first, so every caller thread is joined; then the services
llama_client_destroy(llama)
supervisor_destroy(supervisor)                          # SIGINT, SIGINT after 2 s, 10 s
```
**Instance 2: the two callers, each on its own thread.**
```python
# the recognizer worker: one sentence that needs the model
request = LlamaRequest(
    messages_json=plan_messages_json(sentence),
    grammar=UNIFIED_GRAMMAR,
    max_tokens=PLAN_MAX_TOKENS,
    timeout_ns=config.PLAN_TIMEOUT_NS,                  # the recognizer's value, 10 s
)
start = perf_now()
reply = llama_client_request(llama, request)
ok = reply.result is LLAMA_OK
record_llama_request(start, monotonic_now(), turn.id, LABEL_PLAN, ok, reply.timings)   # typed fields, no tracer
if reply.result is not LLAMA_OK:
    post(Decision("gemma_failed", reply.result.name))  # a chat line; no mission
    return
post(decide_from_plan(reply.text))

# a vision job on a pool thread: the frame as a JPEG, copied from its held slot
jpeg = encode_jpeg(slot)                                # the job's step; then release
request = LlamaRequest(
    messages_json=describe_messages_json(question, jpeg),
    grammar=VLM_GRAMMAR,
    max_tokens=256,
    timeout_ns=config.VISION_LLAMA_TIMEOUT_NS,          # the vision module's value, 20 s
)
start = perf_now()
reply = llama_client_request(llama, request)            # its own slot: no wait
ok = reply.result is LLAMA_OK
record_llama_request(start, monotonic_now(), job.id, LABEL_VISION, ok, reply.timings)
if reply.result is not LLAMA_OK:
    return VisionResult(job, FAILED, reply.result.name)   # architecture section 9
```

## 4. The open points for the owner
D1 to D4 are ruled (2026-10-18); the owner's words are quoted under each. P1 waits for
the owner's ruling in the manager's session.

**D1 (was OPEN 1). A warm-up again after a relaunch: RULED, yes.**
- The owner (2026-10-18, first answer): "Warmup after relaunch - Yes, since we are
  literally re-launching the app due to a problem, we can excuse the warmup as part of
  the restart process."
- The correction given: only the llama-server child relaunches; the app keeps running.
- The owner (2026-10-18, the decision list): "D1 - Yes".
- The design: the main thread sees the "llama" row return to UP. It puts one warm-up on
  the recognizer's queue. The recognizer worker sends it before the next sentence. The
  "warm" row shows "warming", then "warm". The header's LlamaClientWarmUp says so.

**D2 (was OPEN 2). The slot count: RULED, -np 9 --kv-unified -c 8192.** (the header:
kLlamaServerSlots, LlamaClientRequest)
- The owner (2026-10-18): "What about multiple vision jobs? aren't multiple vision jobs
  technically "third+ callers"?"
- Answer: yes. The pool runs up to 8 vision jobs. Each describe sends an image request.
  With SCENE_GATE=vlm or either, each highlight's gate sends one too.
- First measured: a few slots, and N image requests at once (1280x720, 128 tokens each),
  then a plan 50 ms later. These led to the question below.
  | flags | VRAM | 2 images: each | 2 images: the plan | 4 images: the last | 4 images: the plan |
  |---|---|---|---|---|---|
  | -np 1 -c 4096 (before D2) | 3932 MiB | 2477, 4849 ms | 5419 ms | 9801 ms | 10188 ms |
  | -np 2 --kv-unified -c 8192 | 4021 MiB | 3216 ms | 4129 ms | 7197 ms | 7795 ms |
  | -np 4 --kv-unified -c 8192 | 4062 MiB | 3434 ms | 1646 ms | 5542 ms | 6663 ms |
- What they showed: a plan waits only when every slot is busy.
- The owner (2026-10-18, second answer): "Then you know my answer already - How many
  concurrent requests are we actually planning for in our design? extrapolate that to the
  arguments that we need to give. Tell me what answer you came to."
- The answer: the design plans for 9 requests at once. One plan comes from the one
  recognizer worker; the warm-up goes through that worker too. Up to 8 image requests
  come from the pool of 8 vision jobs; the 9th job is refused (architecture section 3).
- The arguments: -np 9 --kv-unified -c 8192. A slot per caller, so nothing queues in the
  server, and the vision module needs no bound. The context: one plan (about 2300 tokens)
  and 8 image requests (about 440 each) use about 5800 of the 8192.
- Measured 2026-10-18 with -np 9 --kv-unified -c 8192:
  | load | the plan | each image request | VRAM |
  |---|---|---|---|
  | the plan alone | 590 ms | | 4165 MiB (233 MiB over -np 1) |
  | 1 image request and the plan | 1375 ms | 2740 ms | |
  | 4 image requests and the plan | 2443 ms | 5426 ms | |
  | 8 image requests and the plan | 5823 ms | 10,705 ms | |
- Every request got a slot and a 200. The plan no longer waits for a slot. It shares the
  GPU, so it slows with the load. Eight image requests side by side end at 10.7 s; one at
  a time they would end at about 19 s.
- The slot count follows the pool: config gives LLAMA_SERVER_SLOTS = VISION_POOL_SIZE +
  1.
- A timeout to check: 8 image requests take 10.7 s without SAM3. Under SAM3 load they may
  pass the 20 s vision timeout (unverified).
- The owner (2026-10-18): "D2 - Option A". The header has it: kLlamaServerSlots = 9.

**D3 (was OPEN 3). A hung server: RULED, no rule.**
- The owner (2026-10-18): "This is way too fucking complicated, seemingly for no reason"
  and "D3 - Drop. We need to pass a message to the "manager', s.t. this would not happen
  in the future."
- The design: a request that hangs ends at its timeout and returns LLAMA_TIMEOUT. The
  recognizer says Gemma failed; a vision job ends FAILED; the perf record shows ok 0. No
  llama-server hang was ever recorded. If one shows up in the records, it gets a design
  from that case.
- How it went wrong: test/llama_server-review.md, the section after the conclusions.

**D4 (was OPEN 4). How the client reaches its server: RULED, a Unix domain socket.**
- The owner (2026-10-18): "Too me it sounds like the payoff is worth it. Does
  llama-server actually support .sock?" and "D4 - See my point".
- Answer to the question: yes. Its help text (common/arg.cpp:3190): "ip address to
  listen, or bind to an UNIX socket if the address ends with .sock". Its log on our run:
  "listening on unix:///.../llama.sock". It opened no TCP port. /health gave 503 while
  loading, then 200. A plan took 478 ms (measured 2026-10-18).
- The owner (2026-10-18, on the answer): "I agree. Approved." D4 is ruled.
- The design: --host <session dir>/llama.sock; no --port, no --alias. The probe is GET
  /health on the socket. The client connects to the path.
- The catch (measured): the socket file stays after an exit, and a relaunch then fails
  ("couldn't bind"). So the supervisor removes the path before each launch. Carried to
  runtime: one new ProcessSpec field, m_removeBeforeLaunch.
- A limit: a socket path holds at most 107 characters (sun_path). A longer session path
  is our bug, and the app dies at start.
- What goes away: the alias, the reply's "model" check, T9 and the free-port check. T5
  becomes the stale-file window (gate item 11).

**P1. How a caller reaches the one perf tracer.** CLOSED by RCD1 and R4 (2026-10-19): no handle anywhere; RecordLlamaRequest packs typed fields with keys interned at the module's start; the header follows. The text below is the history of the point.
- The problem: PHN1 ruled that a client holds no tracer. Perf's approved texts disagree
  on how a caller reaches the one tracer of the process. The manager settles the texts
  and asks the owner (2026-10-18).
- Now: each caller passes its own tracer pointer to RecordLlamaRequest.
- On the manager's form A (a process-wide entry, no tracer argument): RecordLlamaRequest
  loses its first parameter. Nothing else in this module changes.
- Recommended: the manager recommends A. This module follows the owner's ruling.

## 5. Today
The code: `projects/integration_harden2/gemma/server.py` (89 lines), `gemma/client.py`
(128), `perception2/vlm_client.py` (134); the values in `config/constants.py`.
- server.py builds the command line and a ProcessSpec named "gemma". Its probe is GET
  /health with a 1 s timeout. With a warm-up given, the probe also sends one plan.
- client.py: `Gemma.request(messages, grammar, max_tokens, timeout_s, label)` returns
  `(ok, text)`. It opens one connection per request. It records the "gemma" perf stage
  with the long keys (cache_n, prompt_n, prompt_ms, predicted_n, predicted_ms).
- vlm_client.py encodes the frame as a JPEG at quality 80 and sends it as a data URL. The
  highlight gate and the describe both use it.
- The recognizer's timeout is 180 s (PLAN_TIMEOUT_S). The vision timeout is 30 s.

What is wrong with it against rev5:
1. The warm-up inside the probe blocks the probe 0.4 s to 4.2 s. The one supervisor
   thread then sees no crash for that time (runtime, open point 5).
2. The probe timeout is 1 s. The supervisor's cap is 200 ms.
3. `(ok, text)` hides why a request failed. The caller cannot tell "loading" from
   "invalid".
4. A hung server holds the recognizer worker for 180 s.
5. The `thinking` parameter exists only for the benches (YAGNI). Thinking is decided off.
6. The HTTP helper in util/guarded.py returns the error as a repr string. The kind is
   lost.
7. The stop is SIGTERM, then a kill (PROC2 rules each process's own stop).
8. Each failure prints a line. The perf record and the result already carry it.
9. A reply cut at max_tokens reads as a success (finish_reason is not read).
10. The prompt cache in host RAM is never named: 8192 MiB by default (llama.cpp's
    common.h).

## 6. The rulings that bind it, and the forces
| ID | the owner's words | what it fixes here |
|---|---|---|
| PROC2 (2026-10-04) | "Do you think Killing processes is a normal and acceptable way to return resources to the system?" | the stop policy: SIGINT, SIGINT, the kill only logged |
| OWN1 (2026-10-04) | "There are very few Modules in this repo that should have internal state. And even then, those should be still be Created() and Destroyed() accordingly. Most of the ownership is on the app's side." | LlamaClient: a plain struct, Create and Destroy |
| REC1 (2026-10-04) | "Warming up "the recognizer" means sending initial requests to the command-producing/translation/vision/etc... models, not anything else. This is not the responsibility of the "Recognizer" to "warm up" models." | the recognizer builds the warm request; the app sends it |
| L1 | "Why isn't this done already?" (warm Gemma and SAM3 at start) | LlamaClientWarmUp at start, and after every relaunch (D1) |
| RUN9 (2026-10-17) | "The supervisor is the owner ... Who is the owner here!?" | a pure spec function; the module launches nothing |
| runtime point 5 (RUN14) | "The rest are approved." | the probe after every launch; the warm-up after UP; the module's own row says warm. D4 moves /health from TCP to a Unix domain socket |
| RUN14 (2026-10-17) | "Make sure TOCTOU Doesn't fall inbetween the cracks." | gate item 11 below |
| RUN3, RUN4 (2026-10-17) | "I'm not looking at your comments. Your code should be self explanatory." | the header's names carry the design |
| RVW4 (2026-10-12) | mid-flight: hand control to the RC, notify the operator, then crash | the budget spent runs Die, the hand-over first |
| RVW5 (2026-10-12) | "You can measure the C++ processes from our end, measuring the time it takes for them to process + the time it takes for the request to be met together as a single metric." | PERF_LLAMA_REQUEST, timed in the app |
| SYS1 (2026-10-04) | "One owner thread for all app state" | the client returns a reply; it touches no app state |
| TEL4 (2026-10-14) | "we should also have, say, helper functions for performance logs." | RecordLlamaRequest moves here |
| PHN1 (2026-10-18) | "Why do you have ownership/a handle of the performance module?" (the phone client); the same question here, 2026-10-18: "Why do you hold a handle to m_perf? What did we establish regarding the performance module?" | the client holds no tracer; each caller times its call and calls RecordLlamaRequest with its own tracer |
| MOD1, MOD2 (2026-10-12) | "I should be able to understand these points by reading the header and a little bit regarding each points' context." | the document's order; an OPEN n mark in the header while a point is open |
| GATE1 (2026-10-14) | the proof-based gate | section 7b |
| DOC1 (2026-10-17) | "You keep generating and generating and generating documents" | two files only; no drawing |

The forces come from 01-system-architecture.md section 8 and from this module's
measurements. They ran on 2026-10-17 on this machine (RTX 5070 Laptop, Vulkan), with
today's command line on port 18991. So they used TCP and -np 1 -c 4096, before D2 and D4.
The rows marked "(before D4)" describe the alias design that D4 replaced:
| what | measured |
|---|---|
| a warm plan alone (the plan-timing bench, 2026-10-01) | 489 ms p50 server; 1362 ms p50 while SAM3 runs; 3223 ms max with SAM3 |
| a warm plan alone, our time, 20 plans, a new connection each | 585 ms p50, 1718 ms p90, 1905 ms max |
| the time outside the server's prompt_ms and predicted_ms | 42 ms p50 on a new connection; 44 ms on a kept one |
| the first plan after the first launch (no warm-up) | 4195 ms (prompt 3337 ms, 2000 tokens) |
| the first plan after a relaunch; the next plan | 1551 ms (cache_n 0); 396 ms (cache_n 1987) |
| a plan right after an image request | 429 ms (cache_n 1986: the planner prompt stayed cached) |
| an image request, 1280x720 JPEG (168,777 bytes), 128 tokens | 1978 ms p50, 3722 ms max (5 requests) |
| a plan sent 50 ms into an image request | 3351 ms (the image request: 1994 ms) |
| a plan right after a client timeout on a long request | 1411 ms; the cancelled task held the slot about 0.6 s (1 run) |
| the long request in full, for that compare | 22,368 ms: the server cancelled it ("stop: cancel task" in its log) |
| GET /health while loading (503), 310 calls | 0.26 ms p50, 20.2 ms max |
| GET /health before the port is open (refused) | 0.72 ms |
| GET /health ready: a new connection; a kept one (200 calls) | 0.115 ms p50 (0.44 max); 0.050 ms p50 |
| one TCP connect to the port alone (200) | 0.021 ms p50, 0.164 ms max |
| the model load to the first 200 (files in the page cache) | 15.7 s first launch; 4.0 s relaunch |
| a POST during the load | 503 in 0.34 ms |
| a kept connection idle 1 s, 4 s; 6 s, 12 s | 200; RemoteDisconnected |
| a plan on a kept connection idle 6 s | BrokenPipeError after 14 ms |
| a kept connection whose request failed, used again | CannotSendRequest (http.client is left mid-request) |
| SIGINT, idle | exit in 0.77 s |
| SIGINT with a request in flight, then SIGINT after 2 s | exit in 2.26 s; the client saw RemoteDisconnected |
| TCP_QUICKACK on the client | no change to the outside time |
| the plan request body; an image request body | 10,221 bytes; 225,241 bytes |
| json.dumps of the plan body; json.loads of a plan reply | 29.6 us; 4.1 us |
| JPEG encode 720p; base64 of it; json.dumps of the image messages | 1.96 ms; 0.11 ms; 0.38 ms |
| the longest span payload as a JSON string, before R4 | 98 bytes; as typed fields under R4 it is smaller and never cut (unverified until built) |
| on the Unix domain socket (2026-10-18): GET /health ready; a plan | 0.077 ms p50 (0.29 max); 478 ms p50 |
| the reviewer (R1): a plan behind six image requests, 10 s timeout | TimeoutError at 10,011 ms |
| the reviewer (R1): the server under SIGSTOP | connect 0.191 ms; /health and plans time out; the pidfd not readable |
| the reviewer (R1): /health during an image request | 120 of 120 answered, 0.67 ms max |
| the reviewer (R1): a plan with max_tokens 8 | HTTP 200, finish_reason "length", a cut text |
| the reviewer (R1): the prompt cache's saved states | the planner 2029 tokens, 131.8 MiB; an image prompt 310 tokens, 27.8 MiB |
| the reviewer (R1): a plan after an image request with --cache-ram 0 | 1417 ms (cache_n 1) |
| the reviewer (R1): our server with a foreign server on the port (before D4) | "couldn't bind" at 0.090 s; exit 1 at 0.153 s |
| the reviewer (R1): GET /v1/models with --alias (before D4) | 0.4 ms; data[0].id is the alias; 503 while loading |
| the reviewer (R2): /v1/models while loading (before D4) | 503 on 65 calls, 5.25 ms max |
| the reviewer (R2): the "model" field of every chat reply (before D4) | the alias, 5 of 5 plans |
| the reviewer (R2): the planner state after 10, then 16 more image requests | kept (520 ms); then evicted (1487 ms, cache_n 1) |
| the reviewer (R2): server RSS over 80 image requests, cache-ram 512; cache-ram 0 | 2289 to 3597 MiB; 2289 to 2966 MiB |
| the reviewer (R2): the same with MALLOC_ARENA_MAX=2, cache-ram 512 | 2289 to 2948 MiB |
| the reviewer (R2): a stopped process, SIGINT, SIGINT after 2 s | alive at 10 s; ended only by SIGKILL |
| the reviewer (R2): settimeout(1e-9) then recv | TimeoutError after 1.06 ms; never BlockingIOError |

## 7. The design gate
**Ownership.** The supervisor owns the process (RUN9). The app owns the LlamaClient: it
creates it at start, after perf, and destroys it after every caller thread is joined. The
app also holds the LlamaServerSpecText until SupervisorDestroy, since the probe reads the
socket path from it. The recognizer owns the planner's messages and the warm sentence
(REC1). The vision module owns the image messages and the JPEG.

**Data in.** Config gives the binary, the model, the projector and the device. It also
gives the GPU layers, the context, the threads and the prompt-cache size. The app gives
the session folder (the socket path). A LlamaRequest gives the messages JSON, a grammar
or none, the maximum tokens and a timeout.

The timeouts are config values, each owned by its caller:
| config value | owner | value | why |
|---|---|---|---|
| PLAN_TIMEOUT_NS | the recognizer | 10 s | 3223 ms max under SAM3; 5823 ms beside 8 image requests |
| VISION_LLAMA_TIMEOUT_NS | the vision module | 20 s | 3722 ms max alone; slower under SAM3 (unverified how much) |
| PLAN_WARM_UP_TIMEOUT_NS | the recognizer (it builds the warm request) | 30 s | the first plan of the first launch: 4195 ms |
| LLAMA_CACHE_RAM_MIB | config | 512 MiB | the planner state 132 MiB plus about 13 image states |

**Data out.** A ProcessSpec. A LlamaReply: the result, the HTTP status, the server's
timings and the text. The caller puts the timings into its PERF_LLAMA_REQUEST record. The
"warm" row.

**Mutable state, and its owner.**
| state | written by | read by | how |
|---|---|---|---|
| m_warmRow | LlamaClientWarmUp only: the start thread at start, the recognizer worker after a relaunch, never both at once | the main thread, each frame | one atomic store of an immutable pair |
| the LlamaReply | the request's own thread | the same thread | the caller's own memory |
| the connection | the request's own thread | the same thread | opened and closed inside one call |
| the server's queue | llama-server | llama-server | inside the child; not app memory |

**Threads.** The module starts no thread. LlamaClientRequest runs on its caller's thread:
the recognizer worker, a pool thread, or the start thread. It blocks up to the request's
timeout. The probe runs on the supervisor thread under the 200 ms cap. A caller stops
when its request ends: by a reply, a closed connection or its timeout. A quit waits for
the request in flight. A plan takes about 0.5 s. An image request takes up to 3.7 s. Only
a hung request costs the full timeout. Rejected: a cancel in Destroy. It needs a list of
sockets under a lock, for a rare case.

**The process.** One llama-server, launched by the supervisor from the spec. The command
line, from `LlamaServerProcessSpec`:
```
setpriv --pdeathsig TERM --                        (the supervisor's prefix, runtime)
<NATIVE_BIN_DIR>/llama-server
  -m <GEMMA_MODEL_PATH> --mmproj <GEMMA_MMPROJ_PATH>
  -dev Vulkan0 -ngl 99 -c 8192 -np 9 --kv-unified --temp 0.0
  --host <session dir>/llama.sock --threads 1
  --cache-ram 512
  --jinja --chat-template-kwargs {"enable_thinking":false} --reasoning-budget 0
before each launch: the supervisor removes <session dir>/llama.sock (carried to runtime)
env: LD_LIBRARY_PATH=<NATIVE_BIN_DIR>:<the app's LD_LIBRARY_PATH>
log: <log_dir>/proc-llama.log
```
The header's constants:
| name | value | why |
|---|---|---|
| kLlamaServerSlots | 9 | -np: the pool of 8 vision jobs plus the planner (D2) |
| LLAMA_SERVER_READY_TIMEOUT_NS | 240 s | the model loads in 4.0 s (relaunch) to 15.7 s (first launch), measured; 60 s on a cold disk (unverified) |
| LLAMA_SERVER_RETRY_DELAY_NS | 2 s | the second SIGINT (runtime, measured) |
| LLAMA_SERVER_GRACE_NS | 10 s | then the kill, logged |
| kLlamaServerArgvMax | 32 | the argv has 27 entries plus the NULL |
| kLlamaServerEnvMax | 2 | LD_LIBRARY_PATH plus the NULL |
| kLlamaServerNumberBytes | 128 | the number texts of the argv |
| kLlamaServerSocketPathBytes | 108 | sun_path: 107 characters and the NUL |
| LLAMA_SERVER_SOCKET_FILE | "llama.sock" | the file name inside the session folder |
| kLlamaServerPathBytes | 4096 | PATH_MAX on Linux |
| kLlamaReplyTextBytes | 16384 | a reply of 300 tokens is a few KiB |
The stop: SIGINT; SIGINT again after 2 s; the kill after 10 s, logged. A request in
flight makes the server ignore the first SIGINT (runtime, measured 2026-10-16).

## 7b. The gate, answered (modules/README.md, items 1 to 11)
1. **The real-time path.** Tried: a request on the main thread. Stopped: no call of this
   module runs there. The main thread reads the "warm" row: one atomic load, 192 ns
   (runtime's measurement). The module has no queue the main thread touches. The server's
   queue is inside the child. It never holds a request: each caller has its own slot
   (D2).
2. **A logger or a sink.** This module is a client, not a logger. Its types hold a socket
   path and a row. It holds no tracer (PHN1). No app state, no domain type of another
   module. It makes no sink call: the callers write the perf record.
3. **Fault containment.** Tried: every failure of the server. Stopped: each becomes a
   LlamaResult and a false return. The module calls no die(). The traced deaths:
   - the supervisor, when the server never gets ready. Each 240 s miss is a counted crash
     and a relaunch. After three relaunches comes BUDGET_SPENT_DIE. The worst start then
     takes about 17 minutes (unverified: 4 x (240 s + 10 s) plus the delays);
   - the app at start, when the warm-up fails (a start-up check: the planner is broken);
   - the app at start, when the socket path is longer than 107 characters
     (LlamaServerSettingsFromConfig; our bug);
   - the supervisor, when the restart budget is spent (BUDGET_SPENT_DIE, a laptop part);
     mid-flight, Die runs the hand-over first (RVW4);
   - our own bug, for example a missing m_messagesJson: an exception, then the crash hook
     and Die (RVW4).
4. **Buffer lifetimes.** Tried: a frame slot held across a 20 s request. Stopped: the
   module touches no slot. The image arrives as the caller's JPEG copy inside the
   messages. The vision job may release its slot right after the encode.
5. **Types and units.** Every duration is a uint64_t of nanoseconds, a macro with
   UINT64_C. The socket path is at most 107 characters (sun_path). The token counts are
   uint32_t. The server's milliseconds are float. The timeout is one socket timeout per
   step, set once, never computed from a remainder (D8). The perf key req is the caller's
   turn or job number.
6. **One home.** LlamaTimings and RecordLlamaRequest move here from record_llama.h (the former perf_record_llama.h);
   the keys do not change. The planner's messages and the warm sentence: the recognizer.
   The image messages and the JPEG: the vision module. The one HTTP try: util/guarded.py.
   The native library path: util/process.py (native_env). Every value: config.
7. **The contract.** The command line and the env are in section 7. The endpoint is POST
   /v1/chat/completions with the keys messages, max_tokens, temperature 0.0, and grammar
   when given. The reply keys read: choices[0].message.content, choices[0].finish_reason,
   and timings.cache_n, prompt_n, predicted_n, prompt_ms, predicted_ms. The probe reads
   GET /health, its status only. The perf payload: req, label, ok, cn, pn, gn, pm, gm.
   The log: proc-llama.log. The readers that change are in section 9's change-impact
   table.
8. **The Python mapping, as code.** Section 8, "The Python mapping". Thread-local state:
   none. A put that can block: none. An exception that can leave the module: only our own
   bug. The GIL is released inside the socket calls.
9. **The cost budget.** The main thread: one atomic load per frame, 192 ns, 0.06 % of 330
   us. The caller threads hold the GIL for their own steps. A plan: json.dumps 29.6 us
   and json.loads 4.1 us, at most one plan per 2 s. An image request: base64 0.11 ms and
   json.dumps 0.38 ms, in the vision job's step, once per operator question. The worst
   stall of the main thread behind them is that one 0.38 ms call, about once per
   question. A TCP connect cost 0.021 ms; a /health on the socket takes 0.077 ms.
10. **Deterministic checks.** `gcc -fsyntax-only -Wall -Wextra -x c` with the perf and
    runtime folders on the include path: clean. `tools/style/header_layout.py`: ran. No
    drawing. The names: the C and Python table in section 8; a grep of every header name
    in this document after each round.
11. **TOCTOU.** Every check-then-act, named:
    - **T1. The row says UP; the request reaches a dead server.** Closed: the client
      never reads a row. The reply decides: refused in 0.72 ms (TCP; on the socket
      unmeasured), 503 in 0.34 ms, or a closed connection at once. Test:
      `test_request_reads_no_row_and_a_dead_server_is_refused`.
    - **T2. A kept connection is stale.** The server closes an idle one after 5 s
      (measured between 4 s and 6 s). A relaunch also ends it. Closed: no connection
      lives past its request. Test:
      `test_request_after_6_s_idle_and_after_a_relaunch_succeeds`.
    - **T3. The timeout fires while the reply arrives.** Closed: the client closes the
      socket and returns LLAMA_TIMEOUT. It never retries, so no plan is sent twice. The
      server checks the connection once a second, so it cancels the task within 1 s.
      Test: `test_timeout_returns_false_and_the_cancelled_task_frees_the_slot`.
    - **T4. The "warm" row says warm after a relaunch.** A window, kept by choice. From
      the crash to the re-warm, the row still says warm. The "llama" row shows
      RECOVERING; it is the truth. When it returns to UP, the re-warm sets "warming",
      then "warm" (D1). Test: `test_warm_row_has_one_writer`.
    - **T5. Another process on the server's address.** Closed by D4: the address is a
      Unix domain socket in this run's session folder. Only this app creates files there.
      The supervisor removes a stale file before each launch, then the child binds. Kept
      window: between the remove and the bind, a process of the same user could create
      the path. Covered: the session folder is this run's own. Test:
      `test_relaunch_after_a_stale_socket_file_comes_up`.
    - **T6. Two callers at once.** Closed: the client has no shared mutable state but the
      warm row, written by one thread. Each caller has its own slot (D2). Test:
      `test_two_callers_at_once_both_get_replies`.
    - T7 and T8 (the hang rule) went with D3. T9 (another server on the port after UP)
      went with D4.

**The failure matrix.**
| failure | the module's state | the record | the aircraft |
|---|---|---|---|
| the server is down or relaunching | LLAMA_REFUSED in under 1 ms; false | the perf record, ok 0 | never touched; no mission |
| the server loads its model (RECOVERING, STARTING) | LLAMA_LOADING, 503 in 0.34 ms; false | the perf record, ok 0 | never touched |
| the server crashes or stops mid-request | LLAMA_CLOSED at once; false | ok 0; the supervisor's row | never touched |
| a timeout (one slow request) | LLAMA_TIMEOUT after 10, 20 or 30 s; the socket closed | ok 0 | never touched |
| a reply cut at max_tokens | LLAMA_CUT; false | ok 0 | never touched |
| host RAM: the prompt cache and the C library's pools | the server grows from 2.3 GiB to 3.6 GiB, then holds (measured, 80 image requests) | | never touched |
| a stale socket file at a relaunch | removed by the supervisor before the launch | | never touched |
| an invalid reply (not JSON, no content, too long) | LLAMA_INVALID_REPLY; false; no retry | ok 0 | never touched |
| an HTTP error (a 500, a 400) | LLAMA_HTTP_ERROR, the status kept; false | ok 0 | never touched |
| the GPU out of memory at the load | the process exits; the supervisor counts a crash | the row; proc-llama.log | never touched |
| the GPU out of memory in a request | a 500 or a crash (unverified which) | ok 0, or the row | never touched |
| the restart budget spent | the supervisor's Die (BUDGET_SPENT_DIE) | the die event; the banner | mid-flight: the hand-over first (RVW4) |
| the warm-up fails at start | the "warm" row FAILED; the app dies (start-up) | the banner | none yet at start |
| every caller at once (8 image requests and a plan) | each has its slot; the plan 5823 ms, the images 10.7 s (measured, no SAM3) | all records | never touched |
| a stale kept connection | cannot happen: none is kept | | |

## 8. The notes that did not make the header
- **Why one connection per request.** A kept connection saves 0.065 ms per request (0.115
  against 0.050 ms on /health). A plan takes about 500 ms. The server closes an idle
  connection after 5 s. Turns are often more than 5 s apart. So a kept connection is
  often stale. These numbers are on TCP. cpp-httplib applies the same keep-alive timeout
  to a Unix domain socket (its source; unverified on our run). A stale one fails with
  BrokenPipeError or RemoteDisconnected. A failed one is left unusable
  (CannotSendRequest). Recovery would need a retry of a POST, which can send a plan
  twice. Rejected: a persistent connection with a keep-alive.
- **Why no lock in the client.** Each caller has its own slot (D2). A client lock would
  make them wait for each other again. Its wait would sit outside the request's timeout.
  Rejected: a client-side mutex.
- **Why the client reads no row.** A row check before a request is a check-then-act (T1).
  A refused connection answers in 0.72 ms, so the check saves nothing. Rejected: the row
  check.
- **Why one request function, not two.** The chat API has one endpoint. An image is one
  content part of a message. A second function would repeat the send, the timeout and the
  parse. Rejected: LlamaRequestText and LlamaRequestImage.
- **Why the warm-up is not the probe.** A plan takes 0.4 s to 4.2 s. The one supervisor
  thread must not block that long (runtime point 5, approved).
- **Why no retry.** The caller decides what a failure means. The recognizer says
  "gemma_failed"; a vision job ends FAILED (architecture section 9).
- **Why these timeouts.** The timeout matters only for a hung request. A crash ends the
  request at once (LLAMA_CLOSED). So a long timeout is cheap. A plan: 3223 ms max under
  SAM3, and 5823 ms beside 8 image requests; 10 s. An image request: 3722 ms max alone,
  slower under SAM3; 20 s. The warm-up: the first plan of a launch took 4195 ms; 30 s.
  The numbers under full load (SAM3, an image request and a plan together) are
  unverified.
- **The 42 ms outside the server.** It is not the connection: a kept connection and
  TCP_QUICKACK give the same. It is the server's own work outside prompt_ms and
  predicted_ms. The cause (the tokenizer, the chat template, the grammar) is unverified.
- **Why thinking has no parameter.** Thinking is decided off. The parameter served only
  the benches (YAGNI). A bench that needs it passes its own command line.
- **Why --cache-ram 512.** The server saves each prompt's state in host RAM, up to 8192
  MiB by default. This machine has 14 GiB. The cache keeps a plan warm after an image
  request. The plan took 429 ms with it and 1417 ms without it (R1-4). 512 MiB holds the
  planner state (132 MiB) and about 13 image states (28 MiB each). The server drops the
  least recently used state first (its source; R2-8). Measured: the planner state lived
  through 10 image requests. 16 more dropped it. The next plan then took 1487 ms, once.
- **The server's RAM.** --cache-ram bounds the cache, not the process. The server grows
  from 2.3 GiB to 3.6 GiB and holds there. About 0.65 GiB of that is the C library's
  per-thread memory pools; MALLOC_ARENA_MAX=2 removes it (R2-5). Not taken: its effect on
  the plan time is not measured.
- **Why a Unix domain socket (D4).** A TCP port is a name any process on the machine can
  take. A path in this run's session folder is not. The server supports it (its help text
  and our run). The Python client needs one HTTPConnection subclass whose connect() opens
  an AF_UNIX socket to the path. curl reaches it with --unix-socket.
- **The thinking-off flags.** This binary logs that --chat-template-kwargs for thinking
  is deprecated; its own form is --reasoning off (R1-12). The owner's gotcha stands: off
  needs both flags (12 of 12, 2026-09-08). A switch needs that check again first.
- **The result kind in the perf record.** The key "ok" keeps one bit. The keys do not
  change in the move (TEL4), so no key is added.
- **The slot count.** D2 holds it, with the measurements. The first draft said two slots
  split the context; with --kv-unified they share it (measured 2026-10-18).
- **Why the label is text.** The perf table names the labels "plan" and "vision". The
  warm-up adds "warmup". The caller passes it to RecordLlamaRequest. A size test covers the
  longest payload.
- **Why the reply has a fixed text buffer.** It keeps the C header honest about the size.
  A grammar-bound reply of 300 tokens is a few KiB. A longer reply is invalid, never cut.
- **The names, C and Python.**
  | C (the header) | Python (the build) |
  |---|---|
  | LlamaServerSettingsFromConfig(sessionDir) | llama_server_settings_from_config(session_dir) |
  | LlamaServerProcessSpec(settings, logDir, text) | llama_server_process_spec(settings, log_dir); no text: Python strings live while referenced |
  | LlamaServerHealthProbe(ctx) | llama_server_health_probe(socket_path), bound by partial |
  | kLlamaServerStopPolicy | LLAMA_SERVER_STOP_POLICY |
  | LlamaClientCreate, LlamaClientRequest, LlamaClientWarmUp, LlamaClientDestroy | llama_client_create, llama_client_request, llama_client_warm_up, llama_client_destroy |
  | LlamaResult, LLAMA_OK ... | an enum.Enum LlamaResult |
  | RecordLlamaRequest(p, start, end, req, label, ok, timings) | perf_llama_request(...), called by the callers |
- **The env.** ProcessSpec's m_env holds the entries this child adds to the app's
  environment. Whether the supervisor merges them is runtime's contract. Carried.
- **Who encodes the image.** The vision job, from its held slot (Q4 a). The JPEG encode
  costs 1.96 ms and releases the GIL. base64 and json.dumps hold it for 0.49 ms.

**The Python mapping.** `llama_server/server.py` about 50 lines, `client.py` about 90.
```python
# llama_server/server.py: pure; launches nothing
def llama_server_process_spec(settings, log_dir):
    return ProcessSpec(
        name=LLAMA_SERVER_NAME,
        argv=llama_server_argv(settings),            # --host settings.socket_path
        env=native_env(),
        ready_probe=partial(llama_server_health_probe, settings.socket_path),
        remove_before_launch=settings.socket_path,   # carried to runtime (D4)
        ready_timeout_ns=LLAMA_SERVER_READY_TIMEOUT_NS,
        stop=LLAMA_SERVER_STOP_POLICY,               # SIGINT, SIGINT after 2 s, 10 s
        on_budget_spent=BUDGET_SPENT_DIE,
        log_path=os.path.join(log_dir, "proc-llama.log"),
    )

# llama_server/client.py
class LlamaClient:
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.warm_row = StatusRow(STARTING, "cold")
        return

    def request(self, rq):
        body = _payload(rq)                         # bytes: the messages JSON joined in
        # util/guarded.py, the HTTP domain's one try: a new connection to the Unix domain
        # socket (an HTTPConnection subclass), closed in every path; one socket timeout;
        # it returns the status, the body and the failure kind, never a repr
        status, raw, failure = http_post(
            self.socket_path,
            PATH,
            body,
            rq.timeout_ns,
        )
        reply = _reply(status, raw, failure)        # pure
        return reply                                # a frozen dataclass

    def warm_up(self, rq):
        self.warm_row.set(STARTING, "warming")      # one reference store of a new pair
        reply = self.request(rq)
        if reply.result is LLAMA_OK:
            self.warm_row.set(UP, "warm")
        else:
            self.warm_row.set(FAILED, reply.result.name)
        return reply
```
- The GIL: http.client releases it in connect, send and recv. The worker holds it only
  for the payload join and the reply's json.loads.
- A frozen LlamaReply freezes all it holds: its fields are a str, ints, floats and a
  tuple.
- http.client's timeout applies to each socket step, not to the whole request. The reply
  of a non-streamed completion arrives at its end, so the one recv carries the whole
  wait. A reply that stalls halfway may wait longer; no such stall was ever seen (D8).

## 9. The tests the module ships with (`test/test_llama_server.py`)
Change impact:
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| the server on a Unix domain socket, /health its probe (D4); the warm-up after UP and after every relaunch (D1) | when the row turns UP | yes, on purpose (runtime point 5; D4) | test_gemma's start tests rewritten |
| --cache-ram 512 | host RAM; a plan after an image request | no visible change below 512 MiB | new |
| finish_reason "length" is LLAMA_CUT | a cut reply | yes: a failure, not a garbled success | new |
| a warm-up after every relaunch (D1) | the first plan after a crash | no visible change: today's code also warms each launch | new: test_warm_up_runs_again_when_the_llama_row_returns_to_up |
| TCP 127.0.0.1:18090 becomes <session dir>/llama.sock (D4) | every tool that reaches the server by port | yes: curl needs --unix-socket; benches pass their own path | the client and probe tests rewritten |
| a result kind in place of (ok, text) | the callers' failure path | no visible change; the chat line can name the kind | recognizer and vision call sites rewritten |
| the timeouts 10 s, 20 s, 30 s | a hung request | yes: 180 s and 30 s before | new |
| the client stops recording; each caller records PERF_LLAMA_REQUEST (PHN1) | who writes the record | no visible change in the file | the recognizer and vision tests check the record |
| the stage "gemma" becomes "llama_request" with short keys | log/perf_report.py, bench/gemma-plan-timing | yes, on purpose (perf, approved) | the report tests rewritten |
| the stop: SIGINT, SIGINT, the kill | how the server ends | yes, on purpose (PROC2) | runtime's test on the real binary |
| the process name "gemma" becomes "llama" | the status pane, the log file name | yes: proc-llama.log | test_app's row names rewritten |

The tests:
- `test_argv_has_both_thinking_off_flags`; `test_argv_never_has_image_min_tokens`;
  `test_argv_keeps_the_default_kv_cache_type`;
  `test_argv_has_nine_slots_kv_unified_and_the_socket_host` (D2, D4).
- `test_spec_is_pure_and_names_the_stop_policy_and_budget`: two calls, equal specs, no
  child.
- `test_env_puts_the_native_bin_dir_first`.
- `test_probe_is_false_on_503_refused_no_socket_and_timeout` (a local fake server).
- `test_probe_returns_within_200_ms_against_a_server_that_never_answers`.
- `test_reply_parse_reads_text_and_timings`; `test_reply_without_timings_has_zeros`.
- `test_invalid_reply_kinds`: not JSON, no choices, a null content, too long.
- `test_finish_reason_length_is_cut` (R1-3).
- `test_argv_sets_the_prompt_cache_limit_and_the_socket_host` (R1-4, D4).
- `test_relaunch_after_a_stale_socket_file_comes_up` (T5, the real binary).
- `test_settings_die_on_a_socket_path_past_107_characters`.
- `test_warm_up_runs_again_when_the_llama_row_returns_to_up` (D1, in the app's tests).
- `test_each_failure_maps_to_its_result`: refused, 503, closed mid-reply, timeout, 500.
- `test_request_reads_no_row_and_a_dead_server_is_refused` (T1).
- `test_request_after_6_s_idle_and_after_a_relaunch_succeeds` (T2, the real binary).
- `test_timeout_returns_false_and_the_cancelled_task_frees_the_slot` (T3, the real
  binary).
- `test_warm_row_has_one_writer` (T4); `test_warm_up_sets_warming_then_warm_or_failed`.
- `test_two_callers_at_once_both_get_replies` (T6, the real binary).
- `test_client_records_nothing`: a request with no tracer anywhere in the client.
- `test_perf_llama_request_writes_the_short_keys`; `test_longest_payload_fits`.
- `test_no_socket_is_open_after_a_request`: the process's open sockets, before and after.

Carried to the vision jobs (D2): none. Each job has its own slot; no lock is needed.
