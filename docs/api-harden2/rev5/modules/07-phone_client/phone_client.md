# phone client: the phone-app client and its mock (rev5 module 7, revised 2026-10-18)

The design calls this module "the phone-app client and its mock" (rev5/README.md, step 2).
The client's contract is `phone_client.h`; its insides are `phone_client_internal.h`. The
mock's side is `phone_mock.h`. The design document is `../../01-system-architecture.md`. The
review record is `../../test/phone_client-review.md`. The state: revised after six owner
reviews on 2026-10-18 (section 6). No point is open (section 4).

## 1. The job, in one sentence
The phone client sends the app's HTTP requests to the phone app or to its mock.

## 2. The picture
```
 senders (other modules' threads)          this module                    the phone | our mock
 ------------------------------------      -------------------------      --------------------
 platform worker  --PhoneSend(FLY, ...)-->  \                             HTTP, concurrent
   (module 11)      TAKEOFF, LAND            |  a NEW TCP connection per   (ktor CIO; aiohttp)
 emergency thread --PhoneSend(STOP | halt)-> |  request, on the caller's   :8080 the phone
   (module 11)                               |  thread; ONE deadline       :8079 the mock
 voice worker     --PhoneSend(TTS, ...)----> |
   (module 9)                                |
 Die step threads --Handover, Notify------>  /
   (runtime)
                                             probe thread (ours, one)
 main thread  <--one atomic load---------  the "phone" row  <----------  GET /status/ every 2 s
   each frame                              (the probe is its only writer)

 supervisor (runtime), when CONTROL is "mock" <--PhoneMockProcessSpec(logDir)--  starts and
   stops the mock; the client never knows whether it talks to the mock or the phone
```
1. **One constructor, blind to its server.** `PhoneClientCreate(ipv4, port)` builds the
   client. It does not know whether the host is the phone or the mock. It only sends.
2. **The launcher picks the server.** Config derives the host and port from CONTROL, the
   human's one decision. "mock" gives 127.0.0.1:8079; "real" gives the phone's address and
   port 8080. Only the human runs `run.sh up ... real`, after typing ARMED.
3. **One send function.** `PhoneSend` takes a route, a body and a deadline. It opens a new TCP
   connection on the calling thread and closes it before it returns. No socket is shared, so
   the stop never waits behind a mission.
4. **The probe and the row.** One probe thread sends GET /status/ every 2 s. It is the only
   writer of the "phone" row. The main thread reads the row each frame with one atomic load.
5. **Die's two actions.** The hand-over and the notify are this module's functions. Their
   context is the client. They use its fixed target, its latch and its motion count.
6. **Not here.** No perf record and no timing: the caller reads the clock around the call. No
   listener: speech in owns the socket that receives the phone microphone's text. No decision:
   the manual flag, the choice of halt or stop and every repeat are module 11's (NAM2).

**Inside the client (`phone_client_internal.h`).**
```c
struct PhoneClient {
	char             m_host[16];            /* copied from the target in Create */
	uint16_t         m_port;
	StatusRow        m_row;                 /* the "phone" row: the probe thread writes it */
	atomic_flag      m_motionClosed;        /* Die's latch: set once, never cleared */
	_Atomic uint64_t m_motionRequestsLeft;  /* the hand-over's one fact */
	char             m_dieSentence[512];    /* the notify's /tts body, from config */
	int32_t          m_stopFd;              /* Destroy wakes the probe through it */
	OsThread*        m_probeThread;
};
```
How each call works, in the Python of the build:
```python
# Create: it checks only that the host is an address it can connect to
def phone_client_create(ipv4, port):
    ok, _addr = parse_ipv4(ipv4)                       # util/guarded.py; returns a pair
    if not ok:
        die(f"phone client: {ipv4!r} is not a dotted IPv4 literal")
    c = PhoneClient(ipv4, port, row=ROW_STARTING,
                    die_sentence=speech_body(config.DIE_SENTENCE))
    c.probe_thread = start_thread(phone_probe_thread, c)
    return c

# PhoneSend: three steps on one new connection, on the caller's thread
def phone_send(c, route, body, deadline_ns):
    if (body is None) != (route not in (PHONE_ROUTE_FLY, PHONE_ROUTE_TTS)):
        return PhoneResult(PHONE_NOT_SENT, 0)              # a wrong route and body pair
    fd = phone_connect(c, deadline_ns)                     # 1. connect
    if fd is None:
        return PhoneResult(PHONE_NOT_SENT, 0)
    if is_motion(route):                                   # 2. the latch, the count
        if c.motion_closed.is_set():
            close(fd)
            return PhoneResult(PHONE_NOT_SENT, 0)
        c.motion_requests_left.inc()
    return phone_request(fd, route, body, deadline_ns,     # 3. request and reply
                         c.motion_closed if is_motion(route) else None)

# the probe thread: every 2 s, one GET /status/
def phone_probe_thread(c):
    while not wait_fd(c.stop_fd, timeout=PHONE_PROBE_PERIOD_NS):   # Destroy wakes it
        row = row_from_status(probe_status(c, perf_now() + PHONE_PROBE_TIMEOUT_NS))
        if row != c.row:
            c.row = row                                    # one reference store

# Destroy: after every sender is joined and Die's two actions are cleared
def phone_client_destroy(c):
    write_fd(c.stop_fd)
    c.probe_thread.join()                                  # one probe call, 1 s at most
```

## 3. How a caller uses it: two instances, in the Python of the build
**Instance 1: the app's start, Die's two actions, the row each frame.**
```python
# app/main.py; config derives DJI_HOST and DJI_PORT from CONTROL, the human's one decision
phone = phone_client_create(config.DJI_HOST, config.DJI_PORT)   # the client never asks which
die_set_handover(phone_handover_for_die, phone)
die_set_notify(phone_notify_for_die, phone)

# the main thread, every frame, beside the other rows
row = phone_client_row(phone)                                 # one atomic load
if row != last_phone_row:
    chat.line(f"phone: {row.state} {row.detail}")
    last_phone_row = row

# the quit, in reverse
die_set_handover(None, None)
die_set_notify(None, None)
phone_client_destroy(phone)
```
**Instance 2: the emergency while a mission POST is still open (module 11's threads).**
```python
# the platform worker (module 11)
sent = perf_now()
result = phone_send(phone, PHONE_ROUTE_FLY, actions_json, sent + PLATFORM_REQUEST_NS)
perf_dji_request(perf, sent, perf_now(), "/c/fly", result.http_status)
queue.put(PlatformReply(turn=cmd.turn, result=result))

# the emergency thread (module 11): its own socket, at once
deadline = perf_now() + EMERGENCY_STOP_NS
if manual_mode:
    result = phone_send(phone, PHONE_ROUTE_STOP, None, deadline)
else:
    result = phone_send(phone, PHONE_ROUTE_FLY, kPhoneHaltMission, deadline)
    if result.outcome != PHONE_OK:              # also NOT_SENT once Die closed the latch
        result = phone_send(phone, PHONE_ROUTE_STOP, None, perf_now() + EMERGENCY_STOP_NS)
perf_emergency(perf, stop.received_at, perf_now(), stop.turn, result.http_status)
queue.put(PlatformReply(turn=stop.turn, result=result))      # TEL7
```
The deadlines, the halt-or-stop choice and both perf records are module 11's.

## 4. The decisions (no point is open)
**Ruled on 2026-10-18 (section 6 holds the words).**
- Die's hand-over is option a: halt, stop, stop (below).
- The phone app's code is not changed.
- The client is blind to its server. The launcher picks the server from CONTROL.
- Speech in owns the socket that receives the phone microphone's text.
- No mock token. No realistic case puts a real phone at 127.0.0.1:8079.
- A spec lists only its environment additions (ledger RUN15).
- The groundstation never cuts the motors.
- `phone_mock.h` stays as a second header.
- The start order kills no old stack: every part closes itself.

**Decided by the design, with the reason in section 8.** The owner may still overrule each:
- a new connection per request;
- one total deadline per send: `http.client` on a socket that sets the time left per call;
- a new connect attempt every 250 ms, the earlier ones kept open;
- the probe for the client's whole life, and the only writer of the row;
- the phone's `"ok"` field read on every reply.

**Die's hand-over, as ruled (option a, 2026-10-18).**
- Die closes the motion latch, so no new motion request starts.
- If any motion request left during this run, Die sends the halt (300 ms). The halt ends the
  phone's running mission.
- Die sends /c/stop (300 ms). The pilot gets the sticks.
- Die sends /c/stop again 400 ms before its 1 s deadline. It catches a mission step that took
  the sticks late.
- Measured on the mock: 603 to 605 ms in all. A pilot who was flying loses the sticks for
  0.59 ms p50 and 1.55 ms max. Both are unverified on the phone.
- The phone facts behind it are in AircraftController.kt; the manager checked them (PHN4).
  - A stop does not end the mission (lines 516 to 521).
  - A new mission ends the old one (lines 462 to 468).
  - The halt takes the sticks (line 484).
  - The phone acts after it answers (line 317).

**Who starts the mock, as ruled (2026-10-18).** The app's supervisor starts it when CONTROL is
"mock". CONTROL is the one flag; config reads it at start.
- One decision drives both sides. "mock" adds the mock to the supervisor's list and gives the
  client 127.0.0.1:8079. "real" adds nothing and gives the client the phone's address.
- The mock lives and dies with the app. It starts after the preflight and gets SIGINT at the
  quit. The parent-death signal ends it if the app is killed.
- Its logs land in the session folder: `proc-mock.log` and `mock_commands.log`, the record of
  every command it received. The supervisor gives it a "mock" status row.
- It needs no perf of its own. It is measured from our side, request to reply (RVW5).
- Its crash policy is `BUDGET_SPENT_DIE`. Every failure found is a start-up fault (measured
  2026-10-18). A held port exits 1 in 195 ms. A missing aiohttp fails at import.
- The start order writes no file and kills nothing:
  ```
  run.sh up webcam mock
    1. preflight
    2. tmux window "app", with -e CONTROL=mock -e VIDEO=webcam -e MVD_SESSION_DIR=...:
         bash -c 'source <ROS setup>; exec python3 -m app.main'
         app.main -> supervisor -> llama-server, ASR node, keys hook, [gstreamer], mock
         app.main -> PhoneClientCreate(config.DJI_HOST, config.DJI_PORT) -> 127.0.0.1:8079
  run.sh up webcam real: the same with CONTROL=real; no mock; the client -> the phone
  the quit: the app closes its parts in reverse; the supervisor sends the mock SIGINT
  ```
- The start script is module 15's. The changes are carried there.

## 5. Today
The code: `projects/integration_harden2/dji_app/client.py` (284 lines) and
`tools/dji_mock/mock_apiserver.py` (373 lines).
- `DjiApp` holds host, port, allow_real, a 3 s timeout and perf. It dies on a non-loopback host
  without allow_real. Each request opens a new `http.client` connection.
- The "dji app" row has a lock and two writers: every request, and the probe thread.
- The transmit switch is a manual flag inside the client. Off, a motion request returns 409.
- The app's supervisor starts the mock (`mock_process`); `run.sh` writes `app.sh` for the app.

What is wrong with it against rev5:
- The access decisions are mutable booleans: allow_real and the transmit switch.
- The manual flag is a decision. It belongs to the dispatcher (NAM2).
- One timeout per socket call does not bound a send. Round 1 measured 11.7 s for 0.5 s.
- "Never sent" and "sent, no reply" are the same None. A timed-out mission may still run.
- A 200 counts as success. The phone answers its errors with 200 and `"ok": false`.
- "localhost" passes the loopback check, and so do leading zeros and non-ASCII digits.
- The mock with an open WebSocket ignores SIGINT: no exit in 8 s, twice (measured).
- Today's die() sends nothing to the aircraft. RVW4 rules the hand-over.

## 6. The rulings that bind it, and the forces
**The owner's four reviews of 2026-10-18.** The full words are at the end of `brief.md`.
1. "You shoved way too many contracts into a single header". The mock went to `phone_mock.h`;
   the perf helpers went to module 11.
2. "Why do you have ownership/a handle of the performance module?" The client takes no tracer.
   The caller reads the clock around the call.
3. "Using booleans to establish whether access is allowed or not is extremely terrible
   security practice?"
   - Changed: the flags left the public struct. The target is fixed at Create.
4. "internal API Seems overengineered, including the external contract." One send, four
   outcomes, no endpoint struct.
5. "PhoneClientCreateForMock & PhoneClientCreateForPhone should each call a singular
   PhoneClientCreate() with their specific arguments. They should be helper functions."
   - Done, then replaced by items 15 and 16. The helpers went once the client became blind.
6. "what the hell is its internal structure? How does it actually work?" Section 2 and
   `phone_client_internal.h`.
7. "D1 - We will not modify the code on the app side." The phone fix is gone.
8. "D2 - I don't like that we write to app.sh." The start order uses tmux `-e`, no file.
9. "D3 - Correct. Speech In owns this module". The listener is speech in's.
10. "D4 - In what universe does this situation happen". No token.
11. "D5 - Good!" A spec lists only its additions (RUN15).
12. "D6 - No. The groundstation doesn't have that kind of authority. Never." The groundstation
    never cuts the motors.
13. "D7 - I mean, you already did it lol." `phone_mock.h` stays.
14. "D1 - I approve A!" The hand-over is option a (section 4).
15. "Why does PhoneClientCreate have the phone guard here? Does the phone client care? It only
    does what its being told to!" The guard and the helpers left the client.
16. "the phone client should be agnostic to the server its sending the data to". Create takes
    an address and a port, and nothing else.
17. "Why do we try to kill the old stack if we properly close everything on our own?"
    - The start order kills nothing.
18. "Would it be easier for us to manage the telemetry/perf from the mock by launching it from
    the supervisor". Ruled in the sixth review: "I approve all of what you said!"
    - The supervisor starts the mock when CONTROL is "mock" (section 4).

| ID | the owner's words | what it fixes here |
|---|---|---|
| NAM2 (2026-10-04) | "Here are the name lists:" PlatformCommandDispatcher ... SendEmergencyStop, SendCmdList | the names are the dispatcher's; this client sends |
| PROC2 (2026-10-04) | "Do you think Killing processes is a normal and acceptable way to return resources to the system?" | the mock's own stop: SIGINT, its 1 s shutdown |
| OWN1 (2026-10-04) | "Most of the ownership is on the app's side." | the app creates, holds and destroys the client |
| NAM3 | "Call it create() and destroy(), not begin() and end()." | PhoneClientCreate, PhoneClientDestroy |
| STA1 (2026-10-04) | "the UI thread would just read an atomic state for each row and call it a day" | the "phone" row: one atomic reference, one writer |
| SK4 (2026-10-06) | "WE ARE NOT USING MUTEXES FOR SIMPLE SHIT LIKE THIS!" | no lock anywhere in the module |
| SYS1 (2026-10-04) | "One owner thread for all app state" | no app state here; results go back as PlatformReply |
| RVW4 (2026-10-12) | "Good" (mid-flight: hand control to the RC, notify the operator, then crash) | PhoneHandoverForDie, PhoneNotifyForDie |
| RVW6, RVW7 (2026-10-12) | the stop rule; "Good." | the halt in auto, the stop in manual: module 11 chooses |
| U6 | "Option A" (the phone check 2 s) | PHONE_PROBE_PERIOD_NS |
| 2026-09-23 | the app never dies because of the phone | a dead phone is a row, never Die |
| TEL7 (2026-10-14) | decided: the stop's reply as a PlatformReply | instance 2 |
| RUN14 (2026-10-17) | "Make sure TOCTOU Doesn't fall inbetween the cracks." | gate item 11: twelve windows |
| PHN4, RUN15 (2026-10-18) | the stick's precedence refuted as "always"; the env as additions | the hand-over's facts; the mock's env |

The forces:
- The emergency budget: command to action under 1 s.
- A phone request: up to 3 s when the phone is dead.
- The rates: one mission POST per 2 s at most; one probe GET per 2 s; one /tts per sentence.
- The phone: ktor CIO, concurrent per request; it acts after it answers (line 317).
- The phone answers 503 when the RC, the aircraft or the product link is down (ApiServer.kt
  lines 159 to 182). It answers an exception with 200 and `"ok": false` (lines 140 to 148).
- The GIL: a send waits for the GIL after every socket call. Measured: p50 0.2 ms under a
  stand-in of the app's load, 36 ms with one thread spinning pure Python.
- WiFi: one lost SYN costs 1 s with a single connect (RFC 6298). The hotspot's loss rate is
  unverified.

## 7. The design gate
**Ownership.** The app creates the client at start, after the supervisor. It registers Die's
two actions with the client as their context. At the quit it clears them, then destroys the
client, after it joins every sender.

**Data in.** A target: a host and a port. Then per call: a route, a JSON body for FLY and TTS,
and a deadline.

**Data out.** A `PhoneResult` per send: the outcome and the HTTP status. The "phone" row.

**The state.** The struct in section 2.
- Nothing in it grants access. The target is copied once, inside Create. The latch is an
  `atomic_flag` that our code never clears.
- The motion count is a fact for the hand-over, not a permission (window l).

**Threads.** One of ours: the probe thread. It sends one GET capped at 1 s and sets the row on
a change. Then it waits on `m_stopFd`, with the 2 s period as the timeout. Destroy writes the
fd and joins it; the worst join is one probe call, 1 s. Every send runs on its caller's
thread. Die's actions run on Die's step threads.

**Processes.** The mock, when CONTROL is "mock". The supervisor launches it from
`PhoneMockProcessSpec` and stops it with SIGINT. It kills it only after a 10 s grace, logged.

The mock's spec, in the Python of the build:
```python
# phone_client/mock_spec.py, a pure function of config and the log folder
def phone_mock_process_spec(log_dir):
    return ProcessSpec(
        name="mock",
        argv=[sys.executable, config.MOCK_APISERVER_PATH, "127.0.0.1",
              str(config.MOCK_DJI_PORT)],
        env={"MOCK_CMD_LOG": f"{log_dir}/mock_commands.log"},       # an addition (RUN15)
        ready_probe=partial(status_is_200, config.MOCK_DJI_PORT),   # 200 ms cap
        ready_probe_ctx=None,
        ready_timeout_ns=PHONE_MOCK_READY_TIMEOUT_NS,               # 25 s
        stop=ProcessStopPolicy(SIGINT, retry=0, retry_delay_ns=0,
                               grace_ns=SUPERVISOR_DEFAULT_GRACE_NS),
        on_budget_spent=BUDGET_SPENT_DIE,
        log_path=f"{log_dir}/proc-mock.log",
    )

# app/main.py: one decision adds the spec
if config.CONTROL == "mock":
    specs.append(phone_mock_process_spec(log_dir))
```

The mock's build change (tools/dji_mock/mock_apiserver.py):
```python
OPEN_WS = web.AppKey("open_ws", set)          # each WebSocket handler adds and discards

async def fly(req):                            # as the phone: a bad body runs nothing
    ...
    if not isinstance(body, (list, dict)):
        return err("the body is not an action list")

async def on_shutdown(app):                    # every open WebSocket closed first
    for ws in set(app[OPEN_WS]):
        await ws.close()

web.run_app(build_app(), host=host, port=port, shutdown_timeout=1.0)   # was 60 s
```

## 7b. The gate, answered (modules/README.md, items 1 to 11)
1. **The real-time path.** Tried: a send on the main thread. Mechanism: no send runs there.
   The main thread's one call is the row read: one attribute load, 10.2 ns measured.
2. **A logger or a sink.** Not one. It holds no app state and no tracer. No die() after start.
3. **Fault containment.** Every die() is in `PhoneClientCreate`, at start:
   - a host that is not a dotted IPv4 literal;
   - a probe thread that cannot start.
   After start, a dead or slow phone is an outcome and a row, never Die (2026-09-23). A bug
   inside a send raises, and the uncaught-error hook runs Die (RVW4).
4. **Buffer lifetimes.** No frame slot is touched.
5. **Types and units.** Every duration is a `uint64_t` of nanoseconds in config:
   - the probe period, 2 s; the probe call, 1 s;
   - a connect attempt, 250 ms; a motion request's latch check, every 20 ms;
   - the hand-over's halt and first stop, 300 ms each; its second stop, 400 ms;
   - the mock's ready timeout, 25 s.
   The status is a `uint32_t`, 0 for none. A deadline compare is written for unsigned values:
   `left = deadline > now ? deadline - now : 0`. A reply is read up to 64 KiB.
6. **One home.** Tried: a value with two homes. Each item has one:
   - here: the client, the target, the routes, the outcomes, the result, the halt body;
   - here: the row, Die's two actions, the mock's side of the contract;
   - module 11: the deadlines, the halt-or-stop choice, the repeats, `PerfDjiRequest` and
     `PerfEmergency`;
   - module 9: the /tts body; speech in: the phone microphone's listener;
   - config: the two ports; runtime: the row types and `DieActionFn`.
7. **The contract.** The routes: POST /c/fly (a JSON array), /c/takeoff, /c/land, /c/stop and
   /tts (`{"text", "lang", "rate"}`); GET /status/ for the probe. Each request carries
   `Connection: close`. Each reply is read for its status and `ok`.
8. **The Python mapping.** As code, in section 2 and below. Every send makes its own socket on
   the calling thread. The GIL is released in every socket call, and each call must take it
   back. The one try is in `util/guarded.py`, the HTTP domain. The address parse is there too
   and returns a pair. No exception leaves the module.
9. **The cost budget.** The platform worker sends one mission per 2 s at most. Each costs 0.2
   to 0.4 ms on the mock. The main thread pays 10.2 ns a frame against 330 us. One socket and
   one reply buffer per send; nothing grows.
10. **Deterministic checks.** `gcc -fsyntax-only -Wall -Wextra -x c` passes on the three
    headers. The layout tool ran; it cannot lay out the two inline bodies, which are by hand.
11. **TOCTOU.** Twelve check-then-act windows, (a) to (l). Each is closed or named:
    - (a) The row reads UP, then the phone goes away. Named: the row is advice; the send's
      own outcome is the truth. Test: `test_send_to_a_vanished_phone_reports_it`.
    - (b) The row reads WAITING, then the phone comes back. Named: module 11 refuses a mission
      for one probe period at most. Test: `test_row_turns_up_within_one_period`.
    - (c) Two writers of the row. Closed: only the probe thread writes it. Test:
      `test_no_send_writes_the_row`.
    - (d) The address check, then a different address at connect. Closed: only a literal that
      `inet_pton` accepts passes, and Create copies it. Test:
      `test_create_refuses_names_and_leading_zeros`.
    - (e) A request times out, then the phone runs it late. Named: NO_REPLY means "it may have
      run". A motion request closes with a reset, so its unsent bytes are dropped. Test:
      `test_no_reply_after_the_request_left_is_not_not_sent`.
    - (f) Destroy while a send runs. Closed by the order: the app joins every sender, clears
      Die's two actions, then destroys. A Die that started before the clear is the one kept
      window, in C only. Test: `test_destroy_after_the_senders_are_joined`.
    - (g) Die's stop and the emergency thread's stop at once. Named: the phone gets both. The
      mock answered 3,480 stops with 200. Test: `test_two_concurrent_stops_both_answer`.
    - (h) A mission takes the sticks after the stop (the hand-over's phone facts). Named here,
      closed in module 11 by a repeat; in Die by the second stop. Test:
      `test_a_late_mission_is_logged_after_the_stop`.
    - (i) A motion request passes the latch just before Die closes it. Named: it checks the
      latch every 20 ms while it waits, then resets. The residual is the one send call. The
      abort time is the GIL's: 19.4 ms idle, 371 ms with one spinning thread (round 3). Test:
      `test_motion_send_aborts_after_the_latch_closes`.
    - (j) The probe stores a row the main thread already read. Closed: one reference store,
      only on a change. Test: `test_probe_stores_the_row_only_on_a_change`.
    - (k) Destroy while the probe waits. Closed: the probe waits on `m_stopFd` itself, so the
      wait returns at once. Test: `test_destroy_joins_the_probe_within_one_call`.
    - (l) The hand-over reads the motion count. Named: the count only grows. Any motion request
      this run means a halt under option a. A stop never ends the mission (fact 1), so no stop
      may skip it. Test: `test_handover_halts_only_after_motion`.

**The send's two guarded calls, as code.**
```python
# util/guarded.py, the HTTP domain: http.client on a socket that holds one deadline
class DeadlineSocket(socket.socket):                   # about 20 lines in all
    def recv_into(self, buf, n=0, flags=0):
        while True:                                    # a motion request waits in 20 ms slices
            left = remaining_s(self.deadline_ns)
            if left == 0.0 or (self.closed_fn is not None and self.closed_fn()):
                raise TimeoutError()                   # caught below, in phone_request
            self.settimeout(min(left, 0.02) if self.closed_fn else left)
            try:
                return super().recv_into(buf, n, flags)
            except socket.timeout:
                continue
    # sendall and recv set the time left the same way

def phone_request(fd, route, body, deadline_ns, motion_closed):
    conn = http_connection_on(fd, deadline_ns, motion_closed)
    left = False
    try:
        conn.request("POST", ROUTE_PATH[route], body=body, headers=CLOSE_JSON_HEADERS)
        left = True
        response = conn.getresponse()
        data = response.read(65536)
    except (OSError, http.client.HTTPException):
        close_by_reset(conn, motion_closed is not None)   # the kernel drops unsent bytes
        if left:
            return PhoneResult(PHONE_NO_REPLY, 0)
        return PhoneResult(PHONE_NOT_SENT, 0)
    conn.close()
    if response.status // 100 == 2 and ok_field(data):
        return PhoneResult(PHONE_OK, response.status)
    return PhoneResult(PHONE_REFUSED, response.status)

# Die's step 1, option a as ruled
def phone_handover_for_die(c, reason, deadline_ns):
    c.motion_closed.set()                                   # one-way
    if c.motion_requests_left.load() > 0:                   # any motion request this run
        send_once(c, "/c/fly", kPhoneHaltMission,
                  min(deadline_ns, perf_now() + PHONE_HANDOVER_POST_NS))
    send_once(c, "/c/stop", None, min(deadline_ns, perf_now() + PHONE_HANDOVER_POST_NS))
    sleep_until(deadline_ns - PHONE_HANDOVER_LAST_STOP_NS)
    send_once(c, "/c/stop", None, deadline_ns)              # connect, then request
```

**The measurements.** This machine: Linux 7.0.0, 32 logical CPUs, Python 3.12.3, aiohttp
3.14.3. Every request went to the mock on 127.0.0.1:8079, or to a test server on 127.0.0.1.
The slow-link runs used a private network namespace with netem. Each row has 300 requests, or
200 under load, after 20 warm-up requests. Each ran twice.

| measurement | run 1 | run 2 |
|---|---|---|
| POST /c/stop, a new connection, a /c/fly held open (p50 / p90 / max, ms) | 0.208 / 0.251 / 0.862 | 0.365 / 0.435 / 1.074 |
| POST /c/stop, a kept connection, a /c/fly held open | 0.107 / 0.133 / 0.681 | 0.140 / 0.180 / 0.488 |
| the stop under the stand-in load (30 fps, 8 ms Python, 6 MB copy) | 0.231 / 0.289 / 8.746 | 0.179 / 0.243 / 8.675 |
| the stop, 1 thread spinning pure Python | 35.7 / 45.8 / 56.0 | 35.7 / 45.8 / 56.1 |
| the stop, 4 spinning threads (past 1 s: 30 and 23 of 200) | 461 / 1,501 / 2,925 | 340 / 1,369 / 2,540 |
| the same with a 1 ms switch interval (past 1 s: 0) | 66.2 / 203 / 565 | 70.5 / 185 / 402 |

| other measurement | result |
|---|---|
| a 0.5 s deadline against a reply trickled a byte every 0.3 s | the deadline socket: 500.2 to 500.9 ms; plain http.client: 11,707 ms |
| a 300 ms round trip, 1 s deadline, parallel attempts | 20 of 20 at 601 ms; attempts closed at 250 ms: 20 of 20 NOT_SENT |
| every packet lost, 3 s deadline | NOT_SENT at 3,001 ms, 12 sockets, none left |
| a mission in transfer when the latch closes | reset at 60 ms; the body never reached the mock's handler |
| the hand-over on the mock: halt, stop, second stop | 603 to 605 ms, in that order in the mock's log |
| the halt's hold on the sticks: halt sent to the first stop's reply, 20 runs | 0.59 ms p50, 0.73 ms p90, 1.55 ms max |
| the mock: a handler bug; a held port; no aiohttp | HTTP 500, the mock lives; exit 1 in 195 ms; an import error at once |
| today's mock, SIGINT with an open WebSocket | no exit in 8 s, twice; with the build change: exit 0 in 26 to 41 ms |
| the main thread's row read | 10.2 ns |

**The failure matrix.**
| failure | the module's state | the row or the record | the aircraft |
|---|---|---|---|
| the phone dead | NOT_SENT (0.03 ms when refused) or NO_REPLY at the deadline | the row WAITING within one probe | untouched by this module; module 11 refuses missions while WAITING |
| a lost SYN or a slow link | the next attempt after 250 ms; the earlier stays open | none, if one connects | the stop leaves 250 ms late at worst |
| a timeout or a trickling reply | NO_REPLY at the deadline: "may have run" | the caller's record | module 11 repeats the emergency |
| the phone's error, 200 "ok": false | PHONE_REFUSED with the status | the caller's record | nothing ran |
| the aircraft link down (every route 503) | PHONE_REFUSED 503 | the row WAITING with the phone's 503 text | the commands do not reach it |
| a thread spinning pure Python | the send waits on the GIL: 36 ms with one | the caller's record | the stop late (carried to module 15) |
| the mock crashes | the supervisor relaunches it after 1.5, 3, 4.5 s; then Die; sends NOT_SENT meanwhile | the "mock" and "phone" rows | none: the mock moves nothing |
| the mock's port held at start | the mock exits 1 in 195 ms, three times; Die with the reason | the "mock" row, the banner | none |
| Die mid-flight | the latch; the halt after motion; two stops; then /tts | Die's banner | option a: the mission ended, the sticks the pilot's |
| Die mid-flight, the phone dead | each POST NOT_SENT or NO_REPLY; 1 s in all | Die's banner | the DJI link-loss behaviour (unverified) |
| the mock ignores SIGINT | today: no exit; after the build change: 41 ms | the log | none |

## 8. The notes that did not make the header
- **Why the client has no guard.** It sends where it is told (the owner, 2026-10-18). The
  launcher decides: config derives the host from CONTROL, and only the human sets "real"
  after typing ARMED. Rejected: a CONTROL check inside Create, and the two helpers.
- **Why no token.** The owner asked in what universe a real phone answers at 127.0.0.1:8079.
  Only after a human types an adb port forward on purpose, and no script does (grep).
- **Why the caller records perf.** The caller reads the clock around the call. A client with a
  tracer, or with times in its result, would carry what its caller already has.
- **Why one send function.** Six functions differed only in the path and the body. A route
  enum makes the contract a table.
- **Why a new connection per request.** A kept connection fails after a phone app restart, and
  the client cannot tell whether the POST arrived. A new connection has no stale state.
- **Why `http.client` on a deadline socket.** Plain `http.client` gives each socket call the
  full timeout again: 11.7 s for 0.5 s. A socket that sets the time left before each call
  bounds it: 500.2 to 500.9 ms. Rejected: a hand-written HTTP parser.
- **Why parallel connect attempts.** One lost SYN costs 1 s with a single connect. Attempts
  closed at 250 ms break a link slower than 250 ms per round trip. RFC 8305 keeps them open.
- **Carried to other modules.**
  - Module 11: `PerfDjiRequest` and `PerfEmergency`, with the clock read around each call.
  - Module 11: the repeat after an emergency, and the halt's fallback to the stop.
  - Module 11: the hand-over's phone facts, for its own manual switch.
  - Module 9: the /tts body; a 503 when the aircraft link is down.
  - Module 15: no app thread may spin pure Python.
  - Module 15: `run.sh` writes no `app.sh` (tmux `-e`) and kills no old stack.
  - Module 15: the app adds the mock's spec when CONTROL is "mock".
  - Runtime: RUN15; runtime.h line 25, "stop, then manual", becomes the ruled option a.
  - The design document, section 9: "allowReal" goes; the launcher picks the server.

## 9. The tests the module ships with (`test/test_phone_client.py`)
| change | behavior touched | breaks it? | test impact |
|---|---|---|---|
| one constructor blind to its server replaces allow_real | how the target is chosen | yes, on purpose | `test_a_real_host_without_allow_real_dies` and `test_from_env_uses_the_config_target` rewritten |
| the transmit switch moves to module 11 | 409 in manual mode | no, it moves | `test_transmit_off_blocks_motion_but_never_the_stop` moves |
| one send, four outcomes, a deadline | every request's return | yes, on purpose | `test_every_request_posts_its_path_and_body`, `test_a_malformed_phone_reply...` rewritten |
| the "phone" row, one writer | the status pane | the name and the timing change | the two row tests rewritten |
| no perf in the client | the e2e mark | moves to module 15 | `test_a_command_that_reaches_the_phone_app_ends_the_e2e_timing` moves |
| the mock's build change; its spec with BUDGET_SPENT_DIE | the mock's stop and its crash policy | yes, on purpose | `test_the_mock_process_waits_instead_of_dying` and `test_the_real_mock_starts...` rewritten |
| Die's two actions | a crash mid-flight | new behavior (RVW4) | new |

Each test runs on 127.0.0.1 only, against the real mock, a test server or a refused port.
None writes into logs/.
- `test_create_refuses_names_and_leading_zeros` (d).
- `test_each_route_posts_its_path_and_body_to_the_mock`.
- `test_stop_answers_while_a_mission_post_is_open`.
- `test_deadline_bounds_the_whole_send` (a trickling reply).
- `test_slow_link_connects_with_parallel_attempts` (netem in a namespace).
- `test_phone_error_200_ok_false_is_refused`.
- `test_no_reply_after_the_request_left_is_not_not_sent` (e).
- `test_send_to_a_vanished_phone_reports_it` (a); `test_row_turns_up_within_one_period` (b).
- `test_no_send_writes_the_row` (c); `test_probe_stores_the_row_only_on_a_change` (j).
- `test_destroy_after_the_senders_are_joined` (f).
- `test_destroy_joins_the_probe_within_one_call` (k).
- `test_two_concurrent_stops_both_answer` (g).
- `test_a_late_mission_is_logged_after_the_stop` (h).
- `test_motion_send_aborts_after_the_latch_closes` (i).
- `test_handover_halts_only_after_motion` (l).
- `test_handover_fits_its_cap_with_the_phone_dead`.
- `test_mock_stops_on_sigint_with_an_open_websocket`.
- `test_mock_spec_is_pure_and_complete` (argv, the env addition, 25 s, SIGINT, the budget).
- `test_mock_spec_is_added_only_when_control_is_mock`.
