# The review of the phone client (rev5 module 7), three rounds (2026-10-17)

Scope: docs/api-harden2/rev5/modules/07-phone_client/phone_client.md, phone_client.h,
phone_client_internal.h. One reviewer per round (general-purpose agent, model Opus). Round 1
reads with three lenses: storage and hardware; concurrency and real time; YAGNI and
decoupling. Round 2 is the push-back. Round 3 is the landing check. Every request of every
round went to the mock on 127.0.0.1 only.

## Round 1: reviewer

Scope: phone_client.md, phone_client.h, phone_client_internal.h, read against the brief
(sections 0, 3, 4), runtime.h, runtime_internal.h, runtime.md, perf.h, the system design
(sections 2, 3, 4, 8, 9) and the gate in modules/README.md. Three lenses in turn: storage and
hardware; concurrency and real time; YAGNI and decoupling. I also read the phone app's source
on this machine (/root/DJI-android-sdk-v5-recon-swarm, the kcg/dr package). Every request went
to the mock on 127.0.0.1:8079, or to a socket server of my own on an ephemeral 127.0.0.1 port.
No request touched /c/ws/sticks. Every POST /c/fly carried the HALT mission only.

### What I measured, and how
Machine: Linux 7.0.0, 32 logical CPUs, Python 3.12.3, aiohttp 3.14.3. The scripts live in my
scratch folder (.../scratchpad/r1), not in the repo. Each one asserts the host 127.0.0.1. The
send under test is the document's `http_by_deadline`, copied line for line.
- The mock: `MOCK_CMD_LOG=<scratch>/mock_commands.log python3
  /root/groundstation/tools/dji_mock/mock_apiserver.py 127.0.0.1 8079`. Stopped with SIGINT.
  Port 8079 was free at the end (`ss -tln`).
- M1, the order (m1_order.py): a raw socket sends the headers of POST /c/fly and 10 of its 35
  body bytes. After 0.2 s, a POST /c/stop goes on a new connection. After 0.2 s more, the rest
  of the mission's body goes. Then the mock's command log is read.
- M2, the GIL (m2_gil.py): POST /c/stop on a new connection per request, 200 timed after 20
  warm-up requests. The same process runs 0, 1, 4 or 8 pure-Python CPU threads. Two runs.
  m2b_kept.py repeats it with 4 threads, a kept connection against a new one, 100 each.
- M3, the deadline (m3_trickle.py): my own server answers a 40-byte reply, one byte every
  0.3 s. The send has a 0.5 s deadline.
- M4, Destroy (m4_probe.py): the document's probe loop, with a 0.3 s GET. Destroy (set
  stopping, then set the wake event) runs between the loop's stopping check and its clear().
- M5, one lost SYN (m5_syn.py): my own listener with a full accept queue drops the SYN. It
  accepts again from 0.3 s on. Three runs.
- M6, TIME_WAIT: `ss -tan state time-wait` after M2.
- M7, the mock's stop: two scratch copies of the mock, each with one open WebSocket on
  /c/ws/echo, then SIGINT. Copy A: only `shutdown_timeout=1.0`. Copy B: A plus the document's
  `on_shutdown` exactly as written, appended to `app.on_shutdown`.

| measurement | result |
|---|---|
| M1: the mock's log after the stop and the late mission | `POST /c/stop` first, then `POST /c/fly [{"type": "delay", "seconds": 0.0}]`; the mission answered 200 |
| M2: the stop, 0 busy threads, p50 / p90 / max (ms) | run 1: 0.373 / 0.431 / 0.564; run 2: 0.204 / 0.247 / 0.368 |
| M2: 1 busy thread | 30.8 / 35.9 / 41.1; 30.9 / 41.1 / 51.6 |
| M2: 4 busy threads | 101.8 / 137.5 / 178.0; 102.1 / 137.5 / 198.3 |
| M2: 8 busy threads | 228.9 / 294.7 / 376.0; 223.3 / 304.9 / 431.9 |
| m2b: 4 busy threads, kept against new (p50 / p90 / max, ms) | kept 20.4 / 40.7 / 56.0; new 91.6 / 142.4 / 203.3 |
| M3: a 0.5 s deadline against a trickling reply | REPLIED 200 after 11,707 ms |
| M4: the join after Destroy | 2,300 ms (the document's worst: one probe call, 1 s) |
| M5: a connect whose first SYN was dropped | 1,061, 1,055 and 1,053 ms |
| M6: TIME_WAIT sockets after about 880 requests in 60 s | 358 on the client side, 0 on the mock's side |
| M7 copy A: SIGINT with an open WebSocket | exit after 2,066 ms |
| M7 copy B: the same | exit after 50 ms with `KeyError: 'open_ws'`; exit code 1, also with no WebSocket open |
| the ephemeral port range, the SYN retries | 32768 to 60999; tcp_syn_retries 6 |

### Sources
- Python, socket.sendall: "The socket timeout is no longer reset each time data is sent
  successfully. The socket timeout is now the maximum total duration to send all data."
  https://docs.python.org/3/library/socket.html. No such total exists for recv: a timeout
  applies to each operation ("operations fail if they cannot be completed within the timeout").
- RFC 6298, section 2.1: "the sender SHOULD set RTO <- 1 second" until an RTT sample exists.
  https://www.rfc-editor.org/rfc/rfc6298. A SYN has no RTT sample. M5 shows Linux's 1 s.
- aiohttp, web_advanced, graceful shutdown: "A developer should keep a list of opened
  connections (Application is a good candidate)", with `request.app[websockets].add(ws)` in
  the handler. https://docs.aiohttp.org/en/stable/web_advanced.html
- Python, sys.setswitchinterval: the default is 0.005 s (printed by M2). A thread that blocks
  in a socket call releases the GIL and waits to take it back.
- The phone app's source: ApiServer.kt lines 159-182 (an interceptor on every route returns
  503 when the RC, the aircraft or the product is not connected); AircraftController.kt lines
  458-501 (`fly` cancels the previous flight job, then calls `vSticks.takeControl()` at line
  484) and lines 516-521 (`stop` launches `ac.stop` and `relinquishControl`; it does not cancel
  the flight job); DJIAircraft.kt lines 84-95 (`stop(emergency)` calls
  `FlightControllerKey.KeyEmergencyStop` when emergency is true).
- DJI's public FlightControllerKey list
  (https://developer.dji.com/cn/api-reference-v5/android-api/Components/IKeyManager/Key_FlightController_FlightControllerKey.html):
  I found no entry for KeyEmergencyStop. DJI's Payload SDK names an "emergency stop motor"
  and warns that in the air it "will make the aircraft crash"
  (https://developer.dji.com/doc/payload-sdk-api-reference/en/module/flight-controller.html).
  Whether the MSDK key does the same is unverified.

### Findings, most severe first

**R1-1 (critical). A stop can be overtaken by a mission that is still in transfer.**
- Claim: the failure matrix says "a stop while a mission POST is open ... stopped". That is
  false. Two connections give no order between them. A mission that reaches the phone after the
  stop runs after the stop.
- Evidence: M1. The mock logged `/c/stop`, then `/c/fly`, and answered the mission with 200.
  On the phone, `fly` cancels the running flight and calls `vSticks.takeControl()`
  (AircraftController.kt line 484). So a late mission takes the sticks back from the RC. The
  design's own slow-body measurement shows the same: 2,480 stops, then the mission answered 200.
- Why it matters: the emergency budget is "command to action under 1 s". Here the action is
  undone after the stop. On WiFi, one lost segment of the mission is retransmitted after at
  least 200 ms (Linux's minimum RTO). The stop needs only one handshake. So the overtake is
  plausible on the real link (rate unverified). Gate item 11 does not list this window.
- Change: name window (j) in gate item 11. This module cannot fix it alone, but it must
  expose it. Add an atomic count of motion sends in flight (`m_motionInFlight`, one increment
  before the connect, one decrement after the close). `PhoneResult` of a stop gets
  `mb_motionWasInFlight`. Module 11 then sends a second stop when that in-flight send ends. The
  same applies to Die's hand-over: state that its stop does not cover a mission in transfer.
  Add a test: the slow-body mission of M1, then the second stop, read back from the log.

**R1-2 (high). The deadline does not bound a send.**
- Claim: section 7b says a trickling server "can pass it by one step". The overrun has no
  bound.
- Evidence: M3. A 0.5 s deadline returned after 11,707 ms. `getresponse()` and `read()` call
  `recv` many times. Each `recv` gets the full timeout again. Only `sendall` has a total
  (Python docs, above).
- Why it matters: the emergency thread is one thread. While it is held, the next stop waits.
  The platform worker is held the same way. The probe's "1 s cap" and Destroy's "one probe
  call" join are unbounded too. Die is safe only because its step thread is left behind. ktor
  will not trickle on purpose. A congested WiFi link that delivers a reply in pieces stretches
  each step instead (unverified).
- Change: one short raw HTTP/1.1 exchange in util/guarded.py instead of `http.client`. Send
  the request with `Connection: close`. Then loop `recv` with `settimeout(remaining)` before
  every call, until the headers and Content-Length are in, or the deadline passes. About 30
  lines (unverified). Add a test with the trickling server of M3: the send returns NO_REPLY
  within the deadline plus 10 ms.

**R1-3 (high). The cost numbers come from an idle process. The GIL multiplies them by 100 to
1,000.**
- Claim: gate item 9 says a stop costs 0.2 to 0.4 ms and a new connection 0.1 to 0.2 ms more.
  Those are true only with no other Python thread busy.
- Evidence: M2. One busy thread: p50 31 ms. Four: p50 102 ms. Eight, the size of the vision
  pool: p50 223 to 229 ms, max 432 ms. m2b: with four busy threads a kept connection costs
  20 ms and a new one 92 ms. A new connection makes more blocking calls, and each one gives
  the GIL away for up to the 5 ms switch interval.
- Why it matters: the hand-over's first POST has 400 ms. M2's max with eight threads passes
  that with a healthy mock. The stop then reads NO_REPLY and a second stop follows. The app's
  real pure-Python load is unknown (unverified). The vision jobs and the recognizer are Python
  threads.
- Change: measure gate item 9 again under a stand-in for the app's thread load, and state the
  numbers. Then decide the connection rule per route. /c/stop is idempotent, so urllib3's
  rule holds for it: a kept connection for the emergency thread, and one retry on a new
  connection when the kept one fails before any reply byte. Keep a new connection per request
  for /c/fly, as the document argues.

**R1-4 (high). One lost SYN costs 1 s, the whole emergency budget.**
- Claim: section 8 says a new connection costs "one round trip" on WiFi. It also risks a
  handshake retransmission, and that costs 1 s.
- Evidence: M5, 1,053 to 1,061 ms for a connect whose first SYN was dropped. RFC 6298 sets
  the first RTO to 1 s. A lost SYN-ACK costs the same.
- Why it matters: the stop's deadline is under 1 s, so one lost SYN makes it NOT_SENT, and no
  send retries. The hand-over's 400 ms POST cannot see the retransmission at all. The probe's
  1 s cap equals the RTO. So one lost SYN turns the row WAITING, refuses missions for a period,
  and clears the mock confirmation (OPEN 4). The WiFi loss rate is unverified.
- Change: in the connect step, cap each attempt at about 250 ms and open a new socket on a
  timeout, until the deadline. A NOT_SENT attempt sent nothing, so a new SYN is always safe.
  For the probe: the row turns WAITING after two failed probes in a row, or the cap rises to
  1.5 s. Add both to the failure matrix as "a lossy WiFi link".

**R1-5 (high). The emergency HALT goes through a send that OPEN 4 refuses.**
- Claim: the design's section 4 says "An emergency is STOP in manual mode and HALT in auto
  mode". Today `emergency_halt()` sends the HALT mission on /c/fly (control/flight.py lines
  91-98). The header offers HALT only through `PhoneSendMission`, which returns
  `PHONE_REFUSED_HERE` until a probe saw `"mock": true`. Instance 2 shows only the stop.
- Evidence: on the phone, only `fly` cancels the running flight job (AircraftController.kt
  lines 462-468). `stop` leaves the flight job running (lines 516-521). So HALT is not a
  synonym for the stop. A probe that failed once (R1-4) clears the confirmation. The next HALT
  is then refused.
- Why it matters: "A stop and the manual switch are always attempted". In auto mode the
  emergency is the HALT, and here it can be refused. Gate item 11 and the measurements cover
  only /c/stop.
- Change: one of two, for the owner as an open point. (a) A `PhoneSendHalt` that is never
  refused here. It would send the HALT body, which belongs to module 11, so module 11 passes
  it in. (b) Module 11 always sends /c/stop as the emergency, and the design's section 4 is
  corrected. Either way, the TOCTOU list gets the HALT path.

**R1-6 (medium). Destroy can wait a full period plus a probe call.**
- Claim: "the worst join is one probe call, 1 s".
- Evidence: M4, 2,300 ms with a 0.3 s GET. Destroy sets stopping and the wake after the
  loop's check. The loop's `clear()` then erases the wake, the GET runs, and the wait sleeps
  the whole 2 s. The eventfd of the internal header has the same order.
- Why it matters: the app's shutdown waits up to 3 s on this module, and longer under R1-2.
  The test `test_destroy_joins_the_probe_within_one_call` passes or fails by timing luck.
- Change: check stopping right after the clear: `wake.clear(); if stopping: return`. Destroy
  sets stopping before the wake. So either the check sees it, or the wake survives the clear.
  The test forces the order of M4 with two events.

**R1-7 (medium). The mock's build change, as written, crashes at every stop.**
- Claim: the snippet closes `app["open_ws"]`. Nothing creates or fills that key. The four
  WebSocket handlers (echo, sticks, gimbal, telemetry) do not register themselves.
- Evidence: M7 copy B. SIGINT ends it with `KeyError: 'open_ws'` and exit code 1, even with
  no WebSocket open. The document's "exits 0 in 41 ms" was measured on another patch. Copy A,
  with only `shutdown_timeout=1.0`, exits in 2,066 ms, so not "1 s at most".
- Why it matters: every mock stop leaves a traceback in proc-mock.log. A desk run that reads
  the log for errors flags each one.
- Change: write the whole change. Create the set at build time under a `web.AppKey`, add and
  discard it in each of the four handlers, and append `on_shutdown`. aiohttp's docs show this
  shape (above). Or keep only `shutdown_timeout=1.0` and state "about 2 s". That is under the
  10 s grace and adds no handler code.

**R1-8 (medium). The phone answers 503 on every route when the aircraft link is down.**
- Claim: the failure matrix has no row for "the RC or the aircraft is not connected".
- Evidence: ApiServer.kt lines 159-182. The interceptor covers /status, /tts and /c alike.
  `PhoneProbeDecide` maps a non-2xx reply to WAITING_FOR_USER. Today's detail text says "the
  user must fix the phone app".
- Why it matters: in flight, a lost aircraft link shows as a dead phone app. The operator is
  sent to the wrong fix. Die's notify (/tts) also gets 503 then, so the operator hears nothing.
  A desk run with the phone and no aircraft gets 503 on every /tts (speech out's concern too).
- Change: `PhoneProbeReply` keeps the 503 body text (the phone sends "No connection to
  Aircraft" and two others). The verdict puts it in the row's detail. Add the failure matrix
  row: the aircraft link lost; every route 503; the stop's 503 triggers the second stop.

**R1-9 (medium). The stop's effect on the aircraft is stated as a source fact. It is not one.**
- Claim: OPEN 1 says "/c/stop stops the aircraft and hands the sticks to the RC (DJIAircraft.kt
  line 84)".
- Evidence: line 84 starts `stop(emergency)`. With emergency true, the controller's default,
  it calls `FlightControllerKey.KeyEmergencyStop` (line 92). DJI's public key list has no entry
  for it. DJI's Payload SDK says its emergency motor stop "will make the aircraft crash" in the
  air. Today's docstring rests on "the app dev" saying it does not crash.
- Why it matters: Die's hand-over sends this stop, perhaps twice (OPEN 1). If the key cuts the
  motors in the air, the hand-over crashes the aircraft. That is unverified either way.
- Change: write the source fact as it is, with "unverified". Make the human-run field test a
  precondition of relying on the hand-over: the aircraft secured as CLAUDE.md requires, the
  human sends /c/stop, the motors observed. Ask the app developer for the key's documentation.

**R1-10 (medium). The probe stores a new row every 2 s. The usage code then speaks every 2 s.**
- Claim: `_probe_loop` stores `verdict.row` on every pass. Instance 1 compares with `is not`.
- Evidence: a new tuple each pass is a new identity, so the chat gets "phone: UP" every 2 s.
  In the C build, each store is a new immutable pair. Runtime's grace-period reclamation then
  runs every 2 s for no change.
- Why it matters: chat spam on the screen. Runtime stores a new pair only on a change.
- Change: `PhoneProbeDecide` returns one of five constant `RowValue`s, built once at Create.
  The probe stores only when the pointer differs. Add the case to `test_probe_decide_table`.

**R1-11 (low). The mock's env changes runtime's approved contract by inference.**
- Claim: section 8 reads ProcessSpec's env as "additions over the app's environment" and says
  "runtime's build must merge them". Runtime.md section 8 says the child gets "its environment
  (the spec's env ...)". Today's spec passes `dict(os.environ, MOCK_CMD_LOG=...)`.
- Why it matters: if runtime execs the spec's env as the whole environment, the mock starts
  with no PATH or HOME. One module cannot settle another approved module's contract in a note.
- Change: raise it to the owner as a runtime question, or pass the full environment as today.

**R1-12 (low). A deadline that passes during the connect still sends the request.**
- Evidence: after `connect()`, `settimeout(max(remaining, 0.001))` sends with 1 ms. The send
  fits in the socket buffer, so the mission leaves late and reads NO_REPLY.
- Change: after the connect, a remaining time of 0 closes the socket and returns NOT_SENT. The
  phone saw no request bytes, so that outcome is true.

**R1-13 (low). TIME_WAIT is not stated. It is harmless here.**
- Evidence: M6, 358 sockets in TIME_WAIT on the client side, none on the mock's side. The
  client closes first, so TIME_WAIT stays on the laptop, never on the phone. Linux keeps it
  60 s. At the app's rate, about 2 requests per s, that is about 120 sockets, against 28,232
  ephemeral ports. The rate is the document's; the 120 is computed, not measured.
- Change: one line in gate item 9 (the storage lens): the count and the port range.

**R1-14 (low). The loopback check's Python form must reject non-ASCII digits.**
- Evidence: `str.isdigit()` is true for "١" and "²". Today's `_is_loopback` accepts
  "127.0.0.١" and raises ValueError on "127.0.0.²" (`int("²")`). A raise is our own code
  throwing at start.
- Change: write the Python of `PhoneHostIsLoopback`: `p.isascii() and p.isdigit()`, then
  `int(p) <= 255`. Add both strings to `test_localhost_and_names_are_refused`.

**R1-15 (low). Three constants and one field have no reader.**
- `PHONE_MOCK_SHUTDOWN_NS`: the mock reads its own literal 1.0. No function here uses it.
- `PHONE_MOCK_PORT` and `PHONE_REAL_PORT`: config already holds MOCK_DJI_PORT and DJI_PORT
  ("config/ is the one source of every value").
- `PhoneResult.m_sentNs`: perf is recorded inside the send. No caller in the document reads
  it. The emergency record uses `m_doneNs` only.
- Change: drop them, or name the reader of each.

**R1-16 (low). The document disagrees with itself and with today's code.**
- The header says "one PERF_DJI_REQUEST record per call". `_send` returns REFUSED_HERE before
  the record.
- The stop's p50 reads "0.14 to 0.37 ms" in section 2, "0.11 to 0.37" in section 6, and
  0.105 to 0.365 in the table. Gate item 10 claims agreement.
- Today's client.py is 284 lines, not 264.
- Window (e) is "one period" in gate item 11. It is one period plus one probe call. A send
  that gets a reply from the adb-forwarded phone never wakes the probe, so nothing shortens it.
- Change: fix each in place.

### Checked and found sound
- The single writer of the row and the confirmation flag: only the probe stores them.
- The wake during a GET (window g): the clear before the GET keeps that wake.
- File descriptors: every path closes its connection; nothing outlives a send.
- The loopback literal (window d): a dotted literal goes to getaddrinfo with no DNS lookup.
- The mock's stop latency on an idle process: M2's 0 thread rows agree with the table.
- OPEN 3: the phone dials the laptop, so the listener belongs to speech in.

## Round 1: answer
Fifteen findings accepted with the change made. One accepted in part (R1-3). Every change is in
phone_client.md, phone_client.h and phone_client_internal.h; both headers compile and passed
the layout tool again. The phone app's source was read again for R1-1, R1-5, R1-8 and R1-9;
each cited line matches.
- **R1-1, accepted.** Window (j) is named in gate item 11 and in the failure matrix; the
  matrix no longer says "stopped". Every result keeps `m_sentNs` for module 11's repeat rule
  (instance 2 shows it; carried to module 11). For Die the endpoint gained
  `mb_motionBlocked` and `m_motionInFlight`: the hand-over blocks new motion, drains the one in
  flight (200 ms at most), then sends. A motion send with no reply closes with a reset, so no
  unsent byte leaves later. New window (k) for the block against a starting send, closed by
  the order of the two atomics. Tests added.
- **R1-2, accepted.** `http.client` is replaced by one raw HTTP/1.1 exchange with
  `Connection: close` and the time left set before every socket call. Measured: a 0.5 s
  deadline against a server that trickles a byte every 0.3 s returns NO_REPLY after 500.6 ms.
  Test added.
- **R1-3, accepted in part.** Accepted: the cost was measured again under load and the table is
  in section 7b. Under a stand-in of the app's load (30 frames a second, 8 ms of Python and a
  6 MB copy per frame) the raw stop keeps p50 0.18 to 0.23 ms, max 8.7 ms. With four spinning
  threads it passes 1 s in 23 to 30 of 200 sends; a 1 ms switch interval brings that to 0.
  The lever and the rule "no thread spins pure Python" are carried to module 15. Rejected: a
  kept connection for the emergency thread. A half-open kept socket swallows a stop until its
  deadline with no error; a new connection fails fast or retries its SYN. Under the stand-in
  load both forms cost under 0.4 ms p50.
- **R1-4, accepted.** A connect attempt lasts 250 ms (RFC 8305's attempt delay), then a new
  socket, until the deadline. A failed attempt sent no request byte, so a new one is safe. The
  probe's 1 s cap then holds four attempts. The failure matrix has the lossy-link row. Test
  added (a full accept queue, as M5).
- **R1-5, accepted.** `PhoneSendHalt` is a route here, with `kPhoneHaltMission`. It is a motion
  send, so OPEN 4 refuses it: a /c/fly takes the sticks of an aircraft we never commanded.
  Module 11 falls back to the stop on any halt outcome but a 2xx (instance 2; carried). On
  loopback a SYN is never lost, so R1-4's chain that clears the confirmation cannot occur
  there.
- **R1-6, accepted.** The probe checks `mb_stopping` right after the clear; Destroy sets the
  flag before the wake. Window (m) added; the test forces the order of M4.
- **R1-7, accepted.** The build change is written whole: an `AppKey` set created at build time,
  added and discarded in all four WebSocket handlers, `on_shutdown`, `shutdown_timeout=1.0`.
  The document states copy A's 2,066 ms. The 41 ms was measured on a scratch copy that
  registered the set; the document now shows that whole shape.
- **R1-8, accepted.** `PhoneLinkFault` maps the phone's three 503 texts (ApiServer.kt 167 to
  179). The row says which link is down. The failure matrix has the row. /tts 503 is carried
  to module 9.
- **R1-9, accepted.** New OPEN 6: what /c/stop does to a flying aircraft. The source fact is
  written as it is, with "unverified". The field test is the human's precondition: the
  aircraft secured as CLAUDE.md requires, the human sends /c/stop. The assistant runs neither.
- **R1-10, accepted.** Eight fixed pairs (`kPhoneRows`); the probe stores only on a change.
  Window (l) and a test added.
- **R1-11, accepted.** New OPEN 5: the env of a spec is runtime's contract, raised to the owner.
- **R1-12, accepted.** After the connect, no time left closes the socket and returns NOT_SENT.
  Test added.
- **R1-13, accepted.** Gate item 9 states TIME_WAIT: on the laptop, about 120 sockets
  (computed) against 28,232 ports.
- **R1-14, accepted.** The check needs ASCII digits; the test refuses "127.0.0.١" and "127.0.0.²".
- **R1-15, accepted.** `PHONE_MOCK_SHUTDOWN_NS`, `PHONE_MOCK_PORT` and `PHONE_REAL_PORT` are
  gone. `m_sentNs` now has a reader: module 11's repeat rule.
- **R1-16, accepted.** The header says "one record per send that left the laptop". The p50
  figures agree. Today's client is 284 lines. Window (e) is one period plus one probe call.

## Round 2: reviewer

Scope: the revision after round 1 (phone_client.md, phone_client.h, phone_client_internal.h).
I read it against round 1's findings and the author's answer. I also read the brief (sections
0, 3, 4), runtime.h, runtime_internal.h, runtime.md, perf.h, the system design, the gate, and
the phone app's source again. The push-back targets the new mechanisms. Both headers compile
(`gcc -fsyntax-only -Wall -Wextra -x c -Iperf -Iruntime -Itelemetry`).

### Safety record
- Every request went to the mock on 127.0.0.1:8079 or to my own socket servers on 127.0.0.1.
- The netem tests ran in a private network namespace (`unshare -n`), on its own loopback.
  No other agent's traffic passed through it.
- No request touched /c/ws/sticks. Every POST /c/fly carried the halt body only.
- The mock's command log at the end: 52 POST /c/stop, 52 POST /c/fly with the halt body,
  nothing else. The mock exited on SIGINT. Port 8079 was free afterwards (`ss -tln`).

### Measurements
Machine: Linux 7.0.0, 32 logical CPUs, Python 3.12.3, aiohttp 3.14.3. The scripts live in
my scratch folder (`.../scratchpad/r2`), not in the repo. `rawx.py` is the document's
`http_exchange`, filled in line for line: 250 ms attempts, `Connection: close`, the read
until Content-Length or EOF, the reset by `SO_LINGER {1, 0}` on an error.
- The mock: `MOCK_CMD_LOG=<scratch>/mock_commands.log python3
  /root/groundstation/tools/dji_mock/mock_apiserver.py 127.0.0.1 8079`.
- M1, framing (t_mock.py part 1): GET /status/ and POST /c/stop with `Connection: close`.
- M2, the hand-over against a mission in transfer (t_mock.py part 2). A worker thread holds
  the in-flight count at 1. It sends a POST /c/fly whose 37-byte halt body trickles one byte
  every 20 ms. 50 ms later the document's `phone_handover_for_die` runs.
- M3, the hand-over on a healthy mock, no mission, 50 runs (t_mock.py part 3).
- M4, reply shapes (t_reply.py), each against my own server. The server reads the request
  headers byte by byte, so the body stays unread in its kernel buffer. Its close then sends a
  reset.
- M5, slow and dead links (t_connect.py, `unshare -n python3 t_connect.py`). netem on the
  namespace's loopback. Each send is a POST /c/stop to my own server.
- M6, one dropped SYN (t_syn.py): a full accept queue that frees at 0.3 s.
- M7, window (k) as a store-buffering litmus test in C (sb.c, `gcc -O2 -pthread`). One
  million trials per run. Then the same in Python with atomics 1.0.3 (t_py_sb.py).
- M8, a dotted literal with a leading zero (t_octal.py): a listener on 127.0.0.8, a connect
  to "127.0.0.010".

| measurement | result |
|---|---|
| M1: aiohttp's reply headers | `Content-Length` present; `Connection: close`; EOF 0.04 to 0.06 ms after the last byte |
| M2: the drain | ended at 252 ms with the mission still in flight |
| M2: the halt, the stop | both REPLIED 200 at 253 ms |
| M2: the late mission | REPLIED 200 at 703 ms |
| M2: the mock's command log, in order | `/c/fly` (the halt), `/c/stop`, then `/c/fly` (the late mission) |
| M3: block, drain, halt, stop, healthy mock | p50 0.57 ms, p90 0.63 ms, max 1.00 ms |
| M4: chunked reply, then the server's close | NO_REPLY after 10.4 ms: ConnectionResetError; the whole reply was in hand |
| M4: chunked reply, connection kept open | NO_REPLY at the 1 s deadline |
| M4: a Content-Length reply; the reset arrives before the client reads | REPLIED 503 (Linux keeps the queued data readable after a reset) |
| M4: the same reply delimited by the close only; reset before the read | NO_REPLY: ConnectionResetError with 61 bytes (the status line) in hand |
| M4: a server that reads and never answers, 0.3 s deadline | NO_REPLY at 300.4 ms; the server saw ECONNRESET |
| M5: RTT 200 ms (netem delay 100 ms), 1 s deadline | 250 ms attempts: 20 of 20 REPLIED, 400 ms; one connect: the same |
| M5: RTT 300 ms (netem delay 150 ms), 1 s deadline | 250 ms attempts: 20 of 20 NOT_SENT (4 sockets each); one connect: 20 of 20 REPLIED, 600 ms |
| M5: RTT 300 ms, 3 s deadline | 250 ms attempts: 5 of 5 NOT_SENT (12 sockets each); one connect: 5 of 5 REPLIED, 600 ms |
| M5: delay 100 ms with 60 ms jitter, 1 s deadline | both forms 60 of 60 REPLIED (median 425 and 410 ms) |
| M5: every packet lost, 3 s deadline | NOT_SENT at 3,001 ms; 12 sockets, one at a time; none left in SYN-SENT |
| M6: one dropped SYN, 250 ms attempts | connected at 501 ms, three runs (the third socket's SYN) |
| M7: C11, plain `_Atomic` operations (seq_cst) | both missed in 0 of 1,000,000 |
| M7: C11, release store and acquire load | both missed in 347 and 547 of 1,000,000 |
| M7: Python, atomics `inc`/`load` and a plain bool | both missed in 0 of 20,000 |
| M8: `connect(("127.0.0.010", port))` | reached 127.0.0.8 (octal) |
| M8: `ipaddress.IPv4Address` and `inet_pton` | both refuse "127.0.0.010", "0127.0.0.1", "127.1" |

The atomics package is in tools/devenv/install-runtime-deps.sh but was not installed in this
container. I installed it into my scratch folder only.

### Sources
- RFC 8305, section 5: "Starting a new connection attempt does not affect previous attempts,
  as multiple connection attempts may occur in parallel." Also: "One recommended value for a
  default delay is 250 milliseconds." https://www.rfc-editor.org/rfc/rfc8305.html
- Linux, include/net/tcp.h: `#define TCP_RTO_MIN ((unsigned)(HZ / 5))`, that is 200 ms.
  https://github.com/torvalds/linux/blob/master/include/net/tcp.h
- ktor 2.3.12 (the phone app's version, build.gradle line 119), ServerPipeline.kt line 92:
  `connectionOptions = ConnectionOptions.parse(request.headers["Connection"])`; line 176:
  `if (isLastHttpRequest(version, connectionOptions)) break`. Line 149 copies the request body
  out of the socket. https://github.com/ktorio/ktor/blob/2.3.12/ktor-server/ktor-server-cio/jvmAndNix/src/io/ktor/server/cio/backend/ServerPipeline.kt
- ktor 2.3.12, ContentNegotiationConfig.kt line 14: `DefaultCommonIgnoredTypes` holds
  `String::class`. So the 503 texts go out as plain text, not JSON strings.
- The phone app's source (kcg/dr):
  - AircraftController.kt line 317: `private val scope = CoroutineScope(Dispatchers.IO)`.
    Dispatchers.IO is a thread pool, so two launched coroutines run in parallel.
  - AircraftController.kt lines 458 to 501, `fly`: it cancels the previous job and launches
    the new one. The new job joins the previous one, then calls `vSticks.takeControl()`
    (line 484). On success it calls `brake()` without returning the sticks.
  - AircraftController.kt lines 516 to 521, `stop`: `scope.launch { ac.stop(emergency);
    if (emergency) vSticks.relinquishControl() }`. It does not touch `flightJob`.
  - ApiServer.kt `/c/fly` and `/c/stop` (lines 443 to 458): each calls
    `controller.fly { ... }` or `controller.stop()`, then `call.respond` at once.
  - DJIVirtualStick.kt lines 60 to 109: `takeControl` waits for the DJI callback of
    `enableVirtualStick`. Then it enables the advanced mode with `delay(300 ms)` when that mode
    is off. `relinquishControl` returns at once when the virtual stick is not yet enabled.
  - AircraftController.kt lines 362 to 371, `onRCTouched`: an RC stick past 30 gives the
    sticks back and cancels the flight job. `returnControlPostOverrideAfter` is INFINITE
    (line 87), so the phone never retakes them by itself.
  - ApiServer.kt StatusPages (lines 140 to 148): `exception<Exception> { call, e ->
    call.respond(exceptResponse(e)) }`. No status is given, so the reply is HTTP 200 with
    `"ok": false`. Responses.kt: `nok` puts `"ok", false`.
  - ApiServer.kt, controllerRoute's interceptor: a fourth 503 text, "AircraftController not
    initialized.", on the /c routes only (line 402).

### Round 1, landed or moved
| round 1 | verdict in round 2 |
|---|---|
| R1-1, the overtaking mission | moved, not fixed, for Die: R2-2. The phone's own ordering opens a second path: R2-1 |
| R1-2, the deadline | landed: NO_REPLY at 300.4 ms for 0.3 s (M4). A reset after the reply is a new fault: R2-5 |
| R1-3, the GIL; no kept stop connection | the conclusion holds; its stated reason contradicts the document's own measurement: R2-9 |
| R1-4, a lost SYN | landed for a lost SYN (M6: 501 ms). It breaks a slow link: R2-3 |
| R1-5, the halt route | landed. Die's own halt now breaks RVW6 in manual mode: R2-1 |
| R1-6, Destroy's join | landed; the order reasoned below (not measured) |
| R1-7, the mock's build change | not measured again in this round |
| R1-8, the 503 texts | landed; ktor sends them as plain text (source above). A fourth text exists: R2-10 |
| R1-9, OPEN 6 | landed |
| R1-10, the fixed pairs | landed. The state of each pair is not written: R2-10 |
| R1-11, OPEN 5 | landed |
| R1-12, the passed deadline after the connect | landed |
| R1-13, TIME_WAIT | landed. A closed SYN-SENT socket leaves no TIME_WAIT (M5) |
| R1-14, non-ASCII digits | landed. Leading zeros remain: R2-6 |
| R1-15, R1-16 | landed, apart from R2-10's counts |

### Findings, most severe first

**R2-1 (high). The halt then the stop does not leave the RC in control. In manual mode the halt
takes the sticks from the pilot.**
- Claim: OPEN 1 says the sequence "cancels the job and hands the sticks to the RC in that
  order". The phone gives no such order. It answers /c/fly and /c/stop before it acts.
- Evidence: `fly` launches a coroutine and the route answers at once. The new job first joins
  the old one, then calls `takeControl()`. `stop` launches a second coroutine on the same
  Dispatchers.IO pool. That coroutine calls `relinquishControl()`. The two run in parallel.
- Evidence: `takeControl()` waits for DJI's `enableVirtualStick` callback when the virtual stick
  is off. It can add a 300 ms delay for the advanced mode. `relinquishControl()` returns at once
  when the virtual stick is not yet on. So the stop can run inside the halt's `takeControl()`.
  The end state is then the virtual stick ON, braked, with the app gone. The duration of
  `takeControl()` on the aircraft is unverified.
- Evidence: the virtual stick is off in exactly two cases: manual mode (module 11 sent the
  stop) and after an RC override (`onRCTouched`). In both, a human pilot is flying.
- Claim: Die's hand-over sends the halt whenever `real_allowed or mock_confirmed`. It does not
  know the manual flag. RVW6 rules "the halt in auto, the stop in manual". In manual mode, Die's
  halt enables the virtual stick and brakes. The pilot's sticks are overridden until the stop
  lands, or for good if the stop lands first. The pilot can still get them back by pushing a
  stick past 30 (`onRCTouched`), while the phone app runs.
- Claim: window (j) is wider than "in transfer". A mission whose 200 came back before the stop
  left can still take the sticks after the stop, for the same reason. Module 11's repeat rule
  compares send times only, so it misses this case.
- Why it matters: RVW4 asks the hand-over to give the RC control. In manual mode it takes it
  away. This is the one module that sends the hand-over, so the fact belongs here.
- Change: the hand-over sends the halt only in auto mode, as RVW6 rules. Module 11 owns the
  mode. So the endpoint gains one atomic, `mb_autoMode`, written only by module 11's mode
  switch and read only by the hand-over. Or the hand-over becomes the stop alone. Either way
  this is an owner decision: add it to OPEN 1.
- Change: OPEN 1 and window (j) state the phone fact: a 2xx means "the job was launched". The
  phone orders nothing between two connections, even after the first reply.
- Change: in auto mode, a second /c/stop near the end of the cap covers a halt job that
  started late. That is a second KeyEmergencyStop, so it waits for OPEN 6.

**R2-2 (high). The drain does not cover the mission it was added for.**
- Claim: round 1's answer says the hand-over "drains the one in flight (200 ms at most), then
  sends". When the drain times out, the halt and the stop go anyway. The mission's socket stays
  open until the worker's 3 s deadline. Its bytes can still reach the phone after the stop.
- Evidence: M2. The drain ended at 252 ms with the mission still in flight. The halt and the
  stop were answered at 253 ms. The mission arrived later and was answered 200 at 703 ms. The
  mock's log shows `/c/stop` before the late `/c/fly`.
- Evidence: a mission is in transfer for more than a few ms only after a lost segment. Linux
  retransmits after at least TCP_RTO_MIN, 200 ms. So the 200 ms drain ends about when the first
  retransmission leaves. It cannot cover even one loss.
- Why it matters: this is R1-1's fault, moved into Die. Module 11's repeat rule cannot cover
  it: during Die, module 11's threads may be the broken part (RVW4).
- Change: a motion send aborts itself on the block. Its recv loop waits in slices of at most
  20 ms. After each slice it loads `mb_motionBlocked`. When the block is set, it closes by reset
  and returns NO_REPLY. The reset discards the unsent bytes, and ktor's `call.receive` then
  fails on a part body. The drain then ends within one slice. 20 ms is my proposal and is
  unverified under the GIL.
- Change: the test drives M2's trickling mission, then reads the mock's log. Pass: no
  `/c/fly` after the hand-over's `/c/stop`.

**R2-3 (high). On a link slower than 250 ms per round trip, no send ever connects.**
- Claim: each attempt closes its socket after 250 ms and opens a new one. When the SYN-ACK
  takes longer than 250 ms, every attempt is cut before it can finish.
- Evidence: M5. With an RTT of 300 ms, the 250 ms attempts gave NOT_SENT in 20 of 20 sends (1 s
  deadline) and 5 of 5 (3 s deadline). One connect with the whole deadline gave REPLIED in all
  25, at 600 ms.
- Evidence: RFC 8305, the document's own source, says a new attempt "does not affect previous
  attempts". Happy Eyeballs keeps the earlier ones open in parallel. The design closes them.
- Why it matters: a slow link turns into a dead one. The stop is NOT_SENT. The probe fails, so
  the row turns WAITING and missions are refused. The hotspot also carries the video stream, so
  queueing delay is plausible. The RTT on the hotspot under load is unverified.
- Change: keep each earlier attempt open. Start a new socket every 250 ms. Wait on all open
  sockets with one poll against the deadline. Take the first that connects and close the rest.
  At most four sockets live within a 1 s deadline. Every one of them sent no request byte, so
  the rule "a failed attempt is always safe" still holds.
- Change: add the case to the failure matrix and a test: a netem delay of 150 ms in a private
  namespace.

**R2-4 (medium). A 2xx is not "accepted". The phone reports its errors as HTTP 200 with
`"ok": false`.**
- Claim: `PhoneResult` carries only the HTTP status. Instance 2 falls back to the stop on
  "any outcome but a 2xx". `PhoneProbeDecide` turns any 2xx into UP.
- Evidence: the phone's StatusPages handler for `Exception` answers with no status: HTTP 200.
  Its body is `{"ok": false, "error": ...}`. A mission that does not parse ends there. So does a
  DJI error on /status/. The quick routes answer `errorResponse`, also HTTP 200.
- Why it matters: a mission the phone rejected reads as sent. Module 11 then tells the
  operator the wrong thing. The mock answers `"ok": true` even for a bad body, so a desk test
  never shows it.
- Change: the raw exchange already reads the body for /status/. It also reads the `ok` field
  on every reply. `PhoneResult` gains `mb_phoneOk`. Instance 2's fallback reads it. The probe
  maps 2xx with `"ok": false` to BAD_STATUS.
- Change: the mock answers `"ok": false` for a body it cannot parse, as the phone does.

**R2-5 (low). A reset after a complete reply reads as NO_REPLY.**
- Claim: the read loop stops at Content-Length, or else at EOF. A chunked reply has no
  Content-Length, so the loop waits for EOF. A server that closes with unread request bytes
  sends a reset instead of a FIN. The loop then raises, and the code returns NO_REPLY.
- Evidence: M4. A full chunked reply, then a reset: NO_REPLY with the whole reply in hand. A
  reply delimited by the close, then a reset: NO_REPLY with the status line in hand. A
  Content-Length reply survived the same reset (Linux keeps the queued data readable).
- Evidence: ktor's CIO pipeline copies the request body out of the socket (line 149). ktor's
  JSON and text replies carry a known length. So this is unlikely on the phone (unverified).
- Change: on an error with a full status line in hand, return REPLIED with that status. End a
  chunked reply at its last chunk. A 204, a 304 and a 1xx end after their headers (RFC 9112,
  section 6.3). About five lines.

**R2-6 (low). The dotted-literal check and the connect read "010" differently.**
- Claim: the rule "each part ASCII digits, 0 to 255" accepts "127.0.0.010" as 127.0.0.10.
  Python's connect reads the part as octal.
- Evidence: M8. `connect(("127.0.0.010", port))` reached 127.0.0.8.
- Why it matters: window (d) says "the client connects to that same string". The string is
  the same; the address is not. The loopback guard still holds, since the first part must be
  "127". A real host typed with a leading zero connects elsewhere: "010.160.188.132" is
  8.160.188.132.
- Change: parse once with `ipaddress.IPv4Address` in Python, `inet_pton` in C. Both refuse
  leading zeros and short forms (M8). Connect with the parsed address. Add "127.0.0.010",
  "0127.0.0.1" and "127.1" to the test.

**R2-7 (low). OPEN 4 keeps a confirmation across a run of 503 replies.**
- Claim: `PhoneProbeDecide` keeps `wasConfirmed` on a 503 with a phone text. The mock never
  sends those texts. Only a real phone does.
- Why it matters: the mock dies, and an adb forward takes 8079. A real phone with no aircraft
  link answers 503. The confirmation then stays true. When the link returns, motion sends are
  allowed until the next probe, up to 2 s.
- Change: only a reply with `"mock": true` confirms. Every other reply clears the flag. The
  "kept" row of the table goes, so the rule gets simpler.

**R2-8 (low). Window (k) holds only with sequentially consistent atomics. The header does not
say so.**
- Evidence: M7. Plain `_Atomic` operations: 0 misses in a million trials. A release store and
  an acquire load: 347 and 547 misses. On x86 the release store compiles to a plain `mov`. The
  load of the count can then pass it.
- Change: the header states that the block's store and the count's load are seq_cst. In C this
  is the default `atomic_store` and `atomic_load`. In Python the GIL gives it (M7: 0 of 20,000).

**R2-9 (low). The reason given for rejecting a kept stop connection contradicts the document's
own table.**
- Claim: section 8 says a kept socket after "a phone reboot" swallows a stop "until its
  deadline". The document's own measurement says a kept connection after a mock restart fails
  in 0.075 ms. A rebooted phone answers with a reset.
- Claim: a kept socket is silent only when the phone cannot be reached. A new connection then
  also gets nothing until its deadline.
- Why it matters: the conclusion stands on simplicity: no reconnect code, no retry rule, and
  under 0.4 ms p50 either way under the stand-in load. The written reason would mislead a later
  reader.
- Change: state that reason. Drop the claim about the reboot.

**R2-10 (low). Names and numbers that disagree.**
- Gate item 11 and the rulings table say "twelve windows". The list has thirteen, (a) to (m).
- The top of phone_client.md says "three reviewer rounds" are done. Round 1 was.
- `PhoneMockReadyProbe` names 127.0.0.1:8079 in the header. The spec reads
  `config.MOCK_DJI_PORT`. The probe should take the same config value.
- `kPhoneRows`: the state of each pair is not written. NO_ANSWER and BAD_STATUS have no stated
  state. The header names four states for the row.
- The phone has a fourth 503 text on the /c routes: "AircraftController not initialized.".
  The probe never sees it, so the row reads UP while every motion send gets 503. Name it in
  the failure matrix.

**R2-11 (low). The prose rule: sentences over 20 words.**
- A rough script counts about 50 sentences over 20 words outside code and tables.
- The worst: section 4's "Decided by the design" (96 words); gate item 5 (48); gate item 7
  (48); section 8's "Module 11" bullet (46); the stand-in load bullet (33).
- No em-dash. No banned word (wire, seam, load-bearing, sieve).

### Checked and found sound
- `Connection: close` on the phone: ktor 2.3.12 CIO ends the connection after the reply
  (source above). aiohttp sends Content-Length and closes in 0.04 to 0.06 ms (M1).
- The 503 texts: ktor sends a String reply as plain text. A substring or equality match works.
- The reset on no reply: the server saw ECONNRESET at the deadline (M4).
- A new socket after a dropped SYN sends a new SYN at once: connected at 501 ms (M6).
- A host that never answers: 12 sockets in 3 s, one at a time, none left behind (M5).
- The increment-then-check order of window (k), with seq_cst atomics (M7).
- The probe's order for window (m): clear, check, GET, wait. A Destroy before the clear is
  seen by the check. A Destroy after the check leaves the wake set. The worst join is one
  probe call (reasoned, not measured in this round).
- The hand-over's sequence fits the cap: 200 + 400 + 400 ms is the 1 s at worst. On a healthy
  mock it took 0.57 ms p50 and 1.00 ms max (M3).
- The halt then the stop in auto mode, with the virtual stick already on: `takeControl()`
  returns at once, so the halt job normally ends before the stop arrives. That timing is
  unverified on the aircraft.
- OPEN 3, OPEN 5: unchanged and sound.

## Round 2: answer
All eleven findings accepted, with the change made. Both headers compile and passed the layout
tool. The new mechanisms were prototyped on 127.0.0.1 before the rewrite. The netem runs used a
private namespace (`unshare -rn`). The mock's log held only POST /c/stop and halt-body /c/fly.
- **R2-1, accepted.** The phone acts after it answers, on one shared thread pool. So the halt's
  `takeControl()` can land after the stop. In manual mode the halt takes a pilot's sticks.
  OPEN 1 now recommends two stops and no halt. The halt in auto mode is the "no" option, with
  an `mb_autoMode` flag written by module 11. Window (j) states both paths. Module 11's repeat
  rule now covers a mission whose reply came first (carried).
- **R2-2, accepted.** The drain and the in-flight count are gone. A motion send checks
  `mb_motionBlocked` before its connect and every 20 ms after, in the connect and the reply
  wait. Blocked, it closes by reset. Measured: a mission in transfer reset at 60 ms (blocked at
  50 ms); the halt body never reached the mock's handler. A send waiting for its reply aborted
  100.6 ms after the start, blocked at 100 ms. The hand-over then sends /c/stop at once, and
  again when 400 ms are left. Measured on a healthy mock: 611 to 613 ms for the whole step.
- **R2-3, accepted.** A new attempt starts every 250 ms; the earlier ones stay open; the first
  to connect wins (RFC 8305's form). Measured in the namespace: a 300 ms round trip gave 20 of
  20 REPLIED at 601 ms (1 s deadline) and 5 of 5 at 600 ms (3 s). With jitter: 40 of 40 at a
  412 ms median. With every packet lost: NOT_SENT at 3,001 ms, 12 sockets, none left.
- **R2-4, accepted.** `PhoneResult.mb_phoneOk` reads the body's `ok` on every reply. Module
  11's halt fallback reads it. The probe maps 2xx with `"ok": false` to BAD_STATUS. The mock's
  build change answers an unreadable /c/fly body with `"ok": false`.
- **R2-5, accepted.** A full status line in hand before an error is a reply. A chunked reply ends
  at its last chunk. A 204, a 304 and a 1xx end after the headers.
- **R2-6, accepted.** The host must pass `inet_pton` (`ipaddress.IPv4Address` in Python).
  Measured: "127.0.0.010", "0127.0.0.1" and "127.1" are refused.
- **R2-7, accepted.** Only `"mock": true` confirms. Every other reply clears the flag.
  `PhoneProbeDecide` lost its third argument.
- **R2-8, accepted; now moot.** The in-flight count is gone with the drain, so no store-load
  pair remains. The block is one flag, read in slices; a late read costs one slice at most.
- **R2-9, accepted.** The reason to refuse a kept stop connection is now simplicity: no
  reconnect rule, no retry rule, under 0.4 ms p50 either way under the stand-in load.
- **R2-10, accepted.** The windows read "thirteen, (a) to (m)". The state line says rounds 1
  and 2. The ready probe reads config's port. Each fixed pair states its state. The fourth 503
  text has its row in the failure matrix: the row stays UP, and motion gets 503.
- **R2-11, accepted.** Every prose sentence is under 21 words, checked by a script outside code
  and tables. No em-dash and no banned word.

## Round 3: reviewer

Scope: the revision after round 2 (phone_client.md, phone_client.h, phone_client_internal.h).
I read it against every finding of rounds 1 and 2 and the two answers. I also read the brief
(sections 0, 3, 4 and 8), runtime.h, runtime_internal.h, runtime.md, perf.h, the system design,
modules/README.md and the phone app's source (kcg/dr) again.

### Safety record
- Every request went to 127.0.0.1 only: my own socket servers on ephemeral ports, or a scratch
  copy of the mock on 127.0.0.1:8079.
- The mock got GET /status/ and one WebSocket on /c/ws/echo. No /c/fly, no /c/ws/sticks, no
  motion route. Its command log stayed empty.
- The mock exited on SIGINT. Port 8079 was free at the end (`ss -tln`).

### Measurements
Machine: Linux 7.0.0, 32 logical CPUs, Python 3.12.3, aiohttp 3.14.3. Scripts in my scratch
folder (`.../scratchpad/r3`), not in the repo.
- abort_gil.py: a motion send waits for a reply in 20 ms slices. The block is set at 100 ms
  plus a random 0 to 20 ms. The time from the block to the reset is measured. 40 sends per
  row, two runs. The stand-in load is the document's: 30 frames a second, 8 ms of Python and a
  6 MB copy each.
- loop_deadline.py: the document's read loop with a 300 ms deadline. My server sends a reply
  whose body keeps coming at loopback speed.
- mock_stop.py: a scratch copy of the mock with the document's build change applied whole.
  One WebSocket open on /c/ws/echo, then SIGINT. Two runs.
- The host check: `ipaddress.IPv4Address` and `socket.inet_pton` on ten strings.

| measurement | run 1 | run 2 |
|---|---|---|
| block to reset, idle, p50 / p90 / max (ms) | 9.8 / 18.6 / 19.4 | 8.8 / 17.1 / 19.3 |
| block to reset, the stand-in load | 14.5 / 24.6 / 27.6 | 9.3 / 24.5 / 27.3 |
| block to reset, 1 spinning thread | 21.3 / 25.2 / 340.2 | 16.0 / 25.2 / 371.2 |
| block to reset, 4 spinning threads | 30.0 / 763.7 / 5,234 | 101.0 / 865.7 / 6,069 |
| block to reset, 4 spinning threads, switch interval 1 ms | 36.1 / 177.5 / 1,260 | 91.1 / 231.1 / 659 |
| the read loop, 300 ms deadline, 1 kB body | 3 ms, complete | |
| the read loop, 300 ms deadline, 20 MB body | 1,808 ms, REPLIED; 206 recv calls with `settimeout(0.0)` | |
| the read loop, 300 ms deadline, 60 MB body | 16,790 ms, REPLIED; 833 such calls | |
| the mock's build change, SIGINT with an open WebSocket | exit 0 after 26 ms | exit 0 after 31 ms |
| the patched /status/ | `"mock": true`, `"ok": true`; no traceback in the log | |
| the host check | both refuse "127.0.0.١", "127.0.0.²", "127.0.0.010", "0127.0.0.1", "127.1", "localhost", "127.0.0.1 " | |
| the host check, the exception | `ipaddress`: AddressValueError, a ValueError; `inet_pton`: OSError | |

### Rounds 1 and 2, landed or not
| finding | landed | evidence |
|---|---|---|
| R1-1, the overtaking mission | yes | window (j), md 441-445; matrix row, md 607; `m_sentNs`, h 74 |
| R1-2, the deadline | in part | the raw exchange, md 476-503; the read loop has no deadline exit (R3-4) |
| R1-3, the GIL, in part | yes | the load tables, md 554-563; the carry to module 15, md 678 |
| R1-4, a lost SYN | yes | h 50 and 85; matrix, md 597 |
| R1-5, the halt route | yes | h 98-100 and 118-119; instance 2, md 88-91 |
| R1-6, Destroy's join | yes | md 509-511; window (m), md 454-456 |
| R1-7, the mock's build change | yes | md 320-356; measured again: 26 and 31 ms, exit 0 |
| R1-8, the 503 texts | yes | internal h 25-35 and 58-61; matrix, md 603 |
| R1-9, OPEN 6 | yes | md 185-197; h 108 |
| R1-10, the fixed pairs | yes | internal h 49-77; window (l), md 451-453 |
| R1-11, OPEN 5 | yes | md 173-183; h 143 |
| R1-12, a deadline passed in the connect | yes | md 481-483 |
| R1-13, TIME_WAIT | yes | md 405-406 |
| R1-14, non-ASCII digits | yes | replaced by R2-6; measured refused |
| R1-15, the constants without a reader | yes | none left in h; `m_sentNs` read by module 11, h 74 |
| R1-16, the counts | yes | h 87-88; md 45, 200, 426 |
| R2-1, the halt in manual mode | yes | OPEN 1, md 115-131; window (j), md 441-445; a new phone fact: R3-1 |
| R2-2, the drain | in part | h 18-19 and 86-87; md 446-450; the connect-to-send gap: R3-2; the GIL: R3-3 |
| R2-3, the slow link | yes | h 85-86; md 631-634; table, md 567-570 |
| R2-4, the "ok" field | yes | h 73 and 78; internal h 39, 45 and 82; md 90 and 348-351 |
| R2-5, a reset after a reply | yes | md 488-489 and 497-499 |
| R2-6, leading zeros | yes | h 16 and 28; md 421-423; measured refused |
| R2-7, the kept confirmation | yes | internal h 79-86; md 163 |
| R2-8, seq_cst | yes, moot | no in-flight count left in h |
| R2-9, the kept stop's reason | yes | md 623-626 |
| R2-10, the counts and states | in part | md 7, 249 and 411; internal h 55-63; h 142-143 still names 8079 (R3-6) |
| R2-11, the prose | yes | a script finds no sentence over 20 words; no em-dash; no banned word |

### Findings, most severe first

**R3-1 (high). Two stops leave the phone's flight job running. Its later actions still act
after Die.**
- Claim: OPEN 1 recommends two stops and no halt. On the phone, /c/stop never cancels
  `flightJob` (AircraftController.kt lines 516-521). Only a new /c/fly cancels it (line 467).
- Evidence: a running mission goes on to its next action. `Land` calls `aircraft.land()`, which
  starts DJI's auto-landing (Land.kt; AircraftController.kt line 551; DJIAircraft.kt line 56).
  `takeoff()` calls `vSticks.takeControl()` again after `ac.takeoff()` (line 540). So a stop
  that lands during a takeoff is undone by the job itself. `flyToSticks` calls `takeoff()`
  first (line 674).
- Evidence: the job ends early only when a stick passes 30, since `cancelFlightOnOverride` is
  true (lines 86 and 372). A pilot who holds the aircraft with centred sticks does not end it.
- Evidence: in auto mode the virtual stick is already on. The halt's `takeControl()` then
  returns at once (DJIVirtualStick.kt lines 64-68). So the halt in auto mode carries no late
  takeover. Round 2 found the same under "checked and found sound".
- Why it matters: RVW6's stop rule says "the running mission is cancelled". The recommended
  hand-over does not cancel it. The dead app's mission can then land or retake the sticks under
  a pilot. Whether DJI ignores virtual-stick input once it is off is unverified.
- Change: OPEN 1 states this fact beside the late `takeControl()`. Its recommendation is
  weighed again with it. The "no" option (the halt in auto mode, then the stops) cancels the job.
- Change: the failure matrix row "Die mid-flight" adds "the phone's flight job still runs" for
  the two-stop option.

**R3-2 (medium). A motion send that connects inside a slice sends after the block.**
- Claim: the header says a blocked motion send aborts "so no byte leaves later" (h 86-87).
  `http_exchange` checks the block in the connect and in the reply wait. It does not check
  between `connect_in_parallel` and `sendall` (md 478-487).
- Evidence: the connect's last check can see no block. The block is then set. The socket
  connects inside the same 20 ms slice. `sendall` then sends the whole mission after the block.
- Why it matters: window (k) is marked "Closed", yet its own text says bytes may have left. The
  second stop at 600 ms covers it only if `takeControl()` ends by then (unverified).
- Change: check `blocked()` just before `sendall`. Window (k) becomes "named": the residual is
  the one `sendall` call. Fix the header's "so no byte leaves later" to match.

**R3-3 (medium). The 20 ms abort is bounded by the GIL, not by the slice.**
- Claim: OPEN 1 and window (k) say every motion send aborts "within 20 ms".
- Evidence: idle, the reset came within 19.4 ms. Under the stand-in load, within 27.6 ms. With
  one spinning thread, up to 371 ms. With four, p90 764 to 866 ms and up to 6.1 s.
- Evidence: the 1 ms switch interval fixed the stops (md 562). It does not fix the abort: up to
  0.66 to 1.26 s with four spinning threads. Each slice must take the GIL back once.
- Why it matters: an abort past 600 ms resets after the second stop. A mission byte that the
  kernel retransmits can then reach the phone after both stops.
- Change: state the stand-in numbers in window (k) and the failure matrix. The module 15 carry
  says the rule "no thread spins pure Python" is required. The 1 ms lever alone is not enough.

**R3-4 (low). The read loop has no deadline exit, and its buffer grows with the reply.**
- Claim: at the deadline the time left is 0.0. `settimeout(0.0)` makes the socket non-blocking.
  The loop then goes on while bytes keep arriving (md 488-495).
- Evidence: a 300 ms deadline returned after 1,808 ms with a 20 MB body, and 16,790 ms with a
  60 MB body, as REPLIED. `reply += chunk` copies the whole reply on every chunk.
- Why it matters: gate item 9 says "nothing grows", and R1-2 promises one total deadline. The
  phone's replies are small, so this needs a broken peer (unverified on the phone).
- Change: no time left ends the loop: REPLIED with a status line in hand, else NO_REPLY. Cap the
  reply at a fixed size in a `bytearray`. The size is the author's (unverified).

**R3-5 (low). Two exceptions in the Python mapping break the house rule.**
- Claim: `http_exchange` raises its own `TimeoutError("motion blocked")` (md 490). The house rule
  says our code never throws.
- Claim: the host check's Python form throws too. `ipaddress.IPv4Address` raises a ValueError.
  `socket.inet_pton` raises OSError (measured). Item 8 names one try only, the HTTP domain.
- Change: on the block, reset and return NO_REPLY directly. Name the host check as
  `socket.inet_pton` inside the HTTP domain's guarded call, or another named domain.

**R3-6 (low). Local text that disagrees.**
- h 142-143: the spec's comment says "127.0.0.1 8079". The spec reads `config.MOCK_DJI_PORT`
  (md 310).
- md 312: the spec sets no `ready_probe_ctx`. runtime.h line 89 has the field.
- md 517: `PHONE_PROBE_PERIOD_S` is a second name for `PHONE_PROBE_PERIOD_NS`.
- internal h 83-84: "real allowed" and `"mock": true` can both hold. The table does not say
  which line wins.
- internal h 62: an enum comment holds a comma. The brief rules no commas in enum comments.
- md 623-662: eight lines of section 8 run to 114 characters. They were edited, not reflowed.
- md 631-634: the parallel connect names no wait call. Name poll (selectors), not select; runtime
  notes that select fails past fd 1023.
- runtime.h line 25 and runtime.md line 81 say "stop, then manual". OPEN 1 changes that text.
  Add it to section 8's list for runtime.

### Brief and template
- Section 4: all eight items are settled. Two depart from the brief on purpose: a deadline per
  call and the probe for the whole life. Both are listed under "Decided by the design".
- Section 8: open still are the "## Conclusions" of the record and checkpoint 5 of the log.
- MOD1: the order is kept, sections 1 to 9. The failure matrix ends section 7b.

### Checked and found sound
- Both headers compile (`gcc -fsyntax-only -Wall -Wextra -x c`, perf and runtime on the path).
  The layout tool changes nothing on copies of them.
- OPEN 1 to OPEN 6: each is marked in a header. Each has the problem, now, on "no" and
  recommended in the document.
- The hand-over's times: the first stop takes at most 400 ms. The second starts at the
  deadline less 400 ms. 2 x 400 ms fits the 1 s cap. The subtraction cannot wrap, since
  PerfNow is far past 400 ms.
- The socket count: 4 attempts per 1 s, 12 per 3 s, 2 per hand-over stop. It matches the
  12 measured in round 2.
- The probe's order: clear, check, GET, wait. The worst join is one probe call, 1 s.
- The verdict table: every reply maps to one row, apart from R3-6's overlap.
- The mock's build change: exit 0 in 26 and 31 ms with an open WebSocket. /status/ says
  `"mock": true`.
- Windows (a) to (m): each has its test in section 9.
- The phone source citations: AircraftController.kt 317, 458-501 and 516-521; ApiServer.kt
  140-148, 159-182 and 402; DJIAircraft.kt 92; DJIVirtualStick.kt 64-109. Each matches.
- The prose: no sentence over 20 words, no em-dash, no banned word.

### Verdict
Not ready for the owner yet. R3-1 changes what OPEN 1 tells him. R3-2 to R3-6 are local text and
one-line code changes. A round 4 is not needed; the manager checks the fixes by reading.

## Round 3: answer
All six findings accepted, with the change made. Both headers compile and passed the layout
tool. Every prose sentence is under 21 words (a script outside code and tables).
- **R3-1, accepted.** OPEN 1 now carries four source facts. /c/stop leaves the phone's job
  running; only a /c/fly cancels it. A running job lands or retakes the sticks on its next
  action. A `takeControl()` with the sticks off can land late. With the sticks already ours it
  returns at once. The endpoint gained `mb_sticksMaybeOurs`: set by a motion send before it
  leaves, cleared by a stop with a 2xx and `ok`. The hand-over now sends the halt when the
  sticks may be ours, then /c/stop, then /c/stop with 400 ms left. Measured on the mock: 603 to
  605 ms, in that order in the mock's log. The two-stop form is now the "no" option, with its
  cost stated. Window (n) names the flag's two writers and its bias toward "ours".
- **R3-2, accepted.** The block is checked before the send. Window (k) is now "named": the
  residual is the one send call. The header says the kernel drops the unsent bytes.
- **R3-3, accepted.** Window (k) and the failure matrix state the abort's measured times. The
  module 15 carry says the rule "no thread spins pure Python" is required; the 1 ms switch
  interval does not fix the abort.
- **R3-4, accepted.** No time left ends the read loop. The reply is a `bytearray`, capped at
  `kPhoneReplyMaxBytes`, 64 KiB. A status line in hand is a reply.
- **R3-5, accepted.** A blocked send breaks out of the loop and returns NO_REPLY; nothing
  raises. The host parse is `parse_ipv4` in util/guarded.py, the HTTP domain, and returns a
  pair.
- **R3-6, accepted.** The spec comment names config's port. The spec sets `ready_probe_ctx`.
  The probe waits `PHONE_PROBE_PERIOD_NS / 1e9`. The verdict table says the real-allowed line
  does not read the mock field. The enum comment has no comma. The long lines are reflowed. The
  parallel connect names `selectors` (epoll), never `select`. Runtime's "stop, then manual" text
  is carried to runtime.

## Conclusions
Three rounds, one reviewer each (general-purpose agent, model Opus): 16, 11 and 6 findings. All
were accepted; R1-3 in part (a kept stop connection was rejected on simplicity). Every request
of every round went to 127.0.0.1 only. No command reached any aircraft.

**Agreed.**
- One client, one send per route, a new TCP connection per request on the calling thread.
- One raw HTTP/1.1 exchange with one total deadline per call; parallel connect attempts every
  250 ms; a reply cap of 64 KiB; the phone's `ok` read on every reply.
- Three outcomes: NOT_SENT, NO_REPLY ("may have run"), REPLIED; plus REFUSED_HERE for motion.
- The probe for the client's whole life; the only writer of the "phone" row; eight fixed pairs.
- The app-held endpoint with three atomics, shared with Die's two actions; Die never touches
  the client.
- A motion send aborts with a reset once Die blocks motion.
- The mock's spec as a pure function; its build change for a 1 s stop and its WebSockets.
- The stop measured on the mock with a mission open: p50 0.21 to 0.37 ms, max 1.07 ms.

**Open for the owner (phone_client.md section 4).**
- OPEN 1: the hand-over: the halt when the sticks may be ours, then two stops; or two stops.
- OPEN 2: BUDGET_SPENT_WAIT_FOR_USER for the mock.
- OPEN 3: the TCP listener in speech in.
- OPEN 4: the mock check, "mock": true, now (against "a future consideration").
- OPEN 5: the spec's env as additions (runtime's contract).
- OPEN 6: what /c/stop's KeyEmergencyStop does in the air; the human's secured field test.

**Changed because of the review.**
- http.client replaced: its timeout did not bound a send (11.7 s for 0.5 s; now 500.6 ms).
- A lost SYN no longer costs the whole emergency budget; a slow link still connects.
- The halt became a route here; the phone's 503 texts and `ok` field are read.
- The hand-over went from "stop, then a second stop on failure" to the block, the halt when the
  sticks may be ours, and two stops. The phone's own source drove each step.
- The probe's Destroy race, the row's churn, the host's leading zeros and non-ASCII digits, and
  the mock's incomplete shutdown change were fixed.
- Carried: module 11's repeat rule and halt fallback; module 9's /tts 503; module 15's rule that
  no thread spins pure Python; runtime's env and "stop, then manual" text.

## Round 4: reviewer (skills: mattpocock-skills:codebase-design, mattpocock-skills:grilling, ponytail:ponytail-review)

Scope: phone_client.md, phone_client.h and phone_mock.h as revised after the owner's review of
2026-10-18. The sources: the brief (sections 0, 3, 4) and rounds 1 to 3 of this record.
Also runtime.h, perf.h, the system design (sections 9 to 11) and the gate in
modules/README.md.
The lenses: interface depth and information hiding (codebase-design); YAGNI and KISS
(ponytail-review); security of the access scheme. The author is not present, so the grilling
is written as questions with a recommended answer each. "Yes" accepts the recommendation.

### What I measured, and how
One measurement, on a socket server of my own on an ephemeral 127.0.0.1 port. No request went
to the mock, to the phone app, or to any other host. No request touched /c/ws/sticks.
- The script: `<scratchpad>/r4/dl.py`, outside the repo. It asserts the host 127.0.0.1.
- The server answers a 50-byte reply, one byte every 0.3 s, as round 1's M3 did.
- The client: Python's `http.client.HTTPConnection` with `conn.sock` set to a socket subclass.
  The subclass sets the time left as the timeout before every `recv_into` and `sendall`.
- The deadline: 0.5 s. Three runs.

| run | result | time (ms) |
|---|---|---|
| 1 | timeout | 500.9 |
| 2 | timeout | 500.8 |
| 3 | timeout | 500.2 |

One search: `grep -rn 'adb forward|adb reverse'` over every .sh, .py and .md file in the repo.
No script forwards a port. The only hits are review documents that ask the question.

### The module against the deep-module test
- **Depth.** `PhoneSend` hides the connect strategy, the one deadline and the token check.
  It also hides the HTTP exchange, the `ok` parse and the Die latch. Three callers would
  each rebuild these.
  So the module passes the deletion test.
- **The two constructors.** Two adapters, the phone and the mock, sit behind one interface.
  Two adapters make a real boundary. This is the right place for the target choice.
- **The leaks that remain.** Three, each small. The caller combines two result fields to
  learn success (R4-3). The result carries timing the caller already has (R4-4). The caller
  supplies the phone's body JSON (Q4-12).
- **The owner's point 3.** The revision fixes it; it does not move it. The target is fixed
  at Create. The latch can only remove access, never grant it. The one access decision left
  is `config.CONTROL`, which a human sets. That is the right owner.
- **The owner's point 2.** The client holds no tracer. It still uses `PerfTimestamp`, the
  clock's type, for deadlines. That is a clock, not perf. Moving the records to module 11 is
  right: module 11 owns the stage and the turn.
- **The owner's points 1 and 4.** `phone_mock.h` is right: the mock is a separate process
  with its own contract. The one-send interface is right. The overengineering left is inside
  the implementation (R4-2, R4-9), not in the header.

### The grilling: questions for the author

**Q4-1. The halt rule's facts.** Section 7b stamps `last_motion_sent_ns` at the entry of
`phone_send`, before the connect. Should the stamp move to just before the request bytes leave?
Should the stop's stamp be its send time, not its reply time?
- Recommended: yes to both. R4-1 gives the failing case.

**Q4-2. Always halt, or halt on a fact?** Fact 3 says a mission sent before the stop can act
after it. No timestamp on our side can prove the phone's job is cancelled. Should the
hand-over keep the conditional halt, with a margin after the last motion send?
- The other option: always halt. Its cost: a manual pilot loses the sticks for up to 600 ms
  while the aircraft brakes.
- Recommended: yes, keep the conditional halt with a margin. The margin is the phone's
  late-action bound, `PHONE_LATE_ACTION_NS`; its value is unverified until the human's field
  test.

**Q4-3. What does the 20 ms latch poll buy?** A mission body is a few KiB. Linux's default send
buffer is 16 KiB, so one `sendall` returns at once. The poll then helps only when a data segment
waits for a retransmit, and the reset drops it. Is that the case the poll is for?
- Recommended: yes. Keep the poll in the reply wait only. Delete it from the connect phase,
  where the check before the send already covers it (R4-9).

**Q4-4. The hand-written HTTP exchange.** The measurement above bounds `http.client` at 500.2
to 500.9 ms with a 12-line socket subclass. Should that replace the hand-written parser?
- Recommended: yes (R4-2).

**Q4-5. One field for success.** Should `mb_phoneOk` fold into the outcome, as `PHONE_OK` and
`PHONE_REFUSED`?
- Recommended: yes (R4-3).

**Q4-6. The result's two times.** Should `m_sentNs` and `m_doneNs` go, with the caller stamping
`PerfNow()` around the call?
- Recommended: yes (R4-4).

**Q4-7. OPEN 4 against YAGNI.** No script in the repo forwards a port. The owner called the adb
case "a future consideration" (RVW2, item 19). Should the per-request token check stay anyway?
- For it: it guards the aircraft path. It costs about 10 lines and 0 to 0.17 ms, on the
  mock only. It also catches a mock left over from an earlier run on the same port.
- Recommended: yes, keep it, with the threat model stated honestly (R4-5).

**Q4-8. Who makes the token, and where the port comes from.** The app makes the token and
passes `config.MOCK_DJI_PORT` to the client. The spec reads the same port from config itself.
Should the client read the port from config too, like the spec?
- Recommended: yes. The app keeps making the token, as carried to module 15 (R4-7).

**Q4-9. Destroy and Die.** Window (g) keeps a use-after-free in C: Die's actions hold the
client after Destroy frees it. Should the app clear Die's two actions before Destroy?
- This needs runtime to accept a NULL action as "skip this step". runtime.h does not say so.
- Recommended: yes, and carry the NULL rule to runtime. The concurrent case stays named.

**Q4-10. The probe's request.** Does the probe send one GET /status/ that gives both the token
and the phone's state? Or the token check, then a second GET?
- Recommended: one GET for both. The document should say so in `_probe_loop`.

**Q4-11. Parallel connect attempts.** The hotspot's SYN loss is unverified. Should the design
keep the attempts every 250 ms?
- For it: a lost SYN costs 1 s, the whole emergency budget. The netem runs show it works.
- Recommended: yes, keep them. GET /status/ is in CLAUDE.md's SAFE class. The human may
  measure the hotspot's connect times with it when convenient.

**Q4-12. The /tts body.** Module 9 builds the phone's `{"text", "lang", "rate"}`. Should it keep
that, rather than this module owning a `PhoneSendTts(text, lang, rate)`?
- Recommended: yes, keep it in module 9. It is the one sender of /tts. A second function would
  undo the owner's point 4.

**Q4-13. Module 11's halt after Die.** Once the latch closes, module 11's halt is a FLY, so it
gets NOT_SENT. Module 11 then falls back to the stop. Is that intended?
- Recommended: yes. A late halt would retake the sticks after Die's last stop (fact 4).
  Instance 2 should say it in one line.

### The findings, most severe first

**R4-1 (high, safety). The hand-over can skip the halt after a mission that reached the phone
after the last good stop.**
- Claim: the motion stamp is taken before the connect. The stop stamp is taken at its reply.
  So a slow connect makes a late mission look older than the stop.
- Evidence: `phone_send` sets `sent = perf_now()` at entry. It writes
  `c.last_motion_sent_ns = sent` before `http_exchange`, which connects. Parallel attempts let
  a connect last up to the deadline.
- The case: a mission send starts at 0 ms. Its first SYN is lost. The emergency stop leaves at
  100 ms and is answered "ok" at 101 ms. The mission connects and leaves at 300 ms. Die runs at
  500 ms. The hand-over compares 0 against 101 and sends no halt. The phone's job runs on.
  The two stops do not cancel it (fact 1). Its next takeoff retakes the sticks (fact 2).
- Change: stamp the motion right before the request bytes leave, after the latch check. Stamp
  the stop at its send, kept only when its reply is "ok". Halt unless the last good stop left
  more than `PHONE_LATE_ACTION_NS` after the last motion. This covers fact 3 too.
- Change: the stamp needs a place outside `util/guarded.py`. Split the exchange into a guarded
  connect and a guarded request. The client stamps between the two calls.
- Change: in C both stamps are `_Atomic uint64_t`. Section 7 names the latch's atomic, not
  these.
- Test: `test_handover_halts_after_a_mission_with_a_slow_connect` (netem, one lost SYN).

**R4-2 (medium, lean). A hand-written HTTP/1.1 parser where the standard library suffices.**
- Claim: the raw exchange exists only to bound the whole send. A socket subclass gives
  `http.client` that bound.
- Evidence: the measurement above, 500.2 to 500.9 ms for a 0.5 s deadline, three runs. Round 1
  measured 11,707 ms without the subclass. The subclass is 12 lines.
- What goes: the status-line parse, chunked decoding, the 1xx, 204 and 304 rules and the read
  loop. Rounds 2 and 3 each found a parser bug (R2-5, R3-4). That is the risk this deletes.
- Change: connect with the parallel attempts, then set `conn.sock`. The token GET and the
  command use one `HTTPConnection`. `NOT_SENT` against `NO_REPLY` is a flag set after
  `sendall` returns. The 64 KiB cap is `resp.read(65536)`.

**R4-3 (medium, interface). Success takes two fields, and every caller combines them.**
- Claim: `m_outcome == PHONE_REPLIED` alone means nothing to a caller. Each reader also tests
  `mb_phoneOk`.
- Evidence: instance 2 tests both. The stop stamp in `phone_send` tests both. The probe maps
  both. A caller that forgets the second test treats `200 "ok": false` as success.
- Change: four outcomes. `PHONE_OK`: a 2xx with `"ok": true`. `PHONE_REFUSED`: any other reply.
  `PHONE_NOT_SENT` and `PHONE_NO_REPLY` stay. `mb_phoneOk` goes. `m_httpStatus` stays for the
  record and the 503 row.

**R4-4 (low, lean). The result carries two times the caller already has.**
- Claim: `m_sentNs` is `PerfNow()` at the call's entry. `m_doneNs` is `PerfNow()` at its
  return. The caller can read both itself.
- Evidence: section 7b's `phone_send` takes `sent` before any work and `perf_now()` at the
  return. Module 11's records use nothing else.
- Change: delete both fields. Module 11 stamps around the call. The result then holds no
  timing at all, which finishes the owner's point 2.

**R4-5 (low, security wording). The token is called a secret; it is a run nonce.**
- Claim: section 8 says the token is "known only to our mock and our client". It is not.
- Evidence: the mock answers it to any local GET /status/. `/proc/<pid>/environ` shows it to
  the same user. This is fine for the real threat, a misrouted connection.
- Evidence: OPEN 4 says "adb is used on this machine". True, but no script forwards a port.
- Change: one line of threat model in OPEN 4. The token guards against a forward or an old
  mock on the port. It does not guard against a local attacker, and need not. State the grep
  result beside "adb is used".

**R4-6 (low, consistency). The system design still names `allowReal`.**
- Evidence: 01-system-architecture.md section 9: "the client refuses a non-loopback host
  without allowReal". The owner's point 3 deleted that flag.
- Change: carry it. Section 9 then reads: "two constructors; the phone one is human-run only;
  the mock one reaches 127.0.0.1 and proves the run's token".

**R4-7 (low, one home). The mock's port has two paths from config.**
- Evidence: instance 1 passes `config.MOCK_DJI_PORT` to `PhoneClientCreateForMock`. The spec
  reads `config.MOCK_DJI_PORT` itself.
- Change: the client constructor reads config's port too: `PhoneClientCreateForMock(token)`.
  The phone's port is already config's, inside the module.

**R4-8 (low, contract). The route and body pairing is unstated for a wrong pair.**
- Evidence: the header says "the body is JSON for FLY and TTS, NULL otherwise". FLY with NULL
  and STOP with a body are both callable. The document does not say what they do.
- Change: one line in the header. A body is sent only for FLY and TTS. FLY or TTS with NULL
  returns `PHONE_NOT_SENT`.

**R4-9 (low, lean). The latch poll runs in the connect phase, where it buys nothing.**
- Evidence: `http_exchange` checks the latch after the connect, before any byte leaves. A
  motion send blocked during its connect can therefore never send.
- Change: drop the 20 ms slices from the connect. Keep them in the reply wait, pending Q4-3.

### Verdict
The interface is deep and the owner's five points are answered. R4-1 is a safety fix of
three lines and must land before the owner's reading. R4-2 and R4-3 delete code and a
caller trap. The rest are one-line changes.

## Round 4: answer
Both headers compile (`gcc -fsyntax-only -Wall -Wextra`) and passed the layout tool. The
document passes the 20-word check. Every finding is accepted, with the change made.

The questions:
- **Q4-1, yes.** The motion stamp is now taken just before the bytes leave, after the second
  latch check. The stop stamp is its send time, kept only when the reply is PHONE_OK.
- **Q4-2, yes.** The halt stays conditional, with a margin. `PHONE_LATE_ACTION_NS` is 1 s,
  unverified until the human's field test (OPEN 6).
- **Q4-3, yes.** The 20 ms latch check stays in the reply wait only.
- **Q4-4, yes.** The hand-written parser is deleted (R4-2).
- **Q4-5, yes.** Four outcomes: PHONE_OK, PHONE_REFUSED, PHONE_NOT_SENT, PHONE_NO_REPLY (R4-3).
- **Q4-6, yes.** The result holds the outcome and the status only (R4-4).
- **Q4-7, yes.** The token check stays. OPEN 4 states the threat model and the grep result.
- **Q4-8, yes.** `PhoneClientCreateForMock(token)` reads config's port, like the spec.
- **Q4-9, yes.** The app clears Die's two actions before Destroy. The NULL rule is carried to
  runtime. Window (g) names the one kept case.
- **Q4-10, yes.** The probe sends one GET /status/ for the token and the phone's state.
- **Q4-11, yes.** The parallel attempts stay.
- **Q4-12, yes.** Module 9 keeps the /tts body.
- **Q4-13, yes.** Instance 2 says that after Die the halt is NOT_SENT and the stop follows.

The findings:
- **R4-1, accepted.** The two stamps are send times. The hand-over halts unless the last good
  stop left `PHONE_LATE_ACTION_NS` after the last motion. The send is split into a guarded
  connect (the parallel attempts and the token GET) and a guarded request; the client stamps
  between them. In C both stamps are private `_Atomic uint64_t`. Test added:
  `test_handover_halts_after_a_mission_with_a_slow_connect`.
- **R4-2, accepted.** `http.client` on a socket subclass that sets the time left per call. The
  status, chunked and 1xx rules of the parser are gone with it.
- **R4-3, accepted.** `mb_phoneOk` is gone; success is `PHONE_OK` alone.
- **R4-4, accepted.** `m_sentNs` and `m_doneNs` are gone. Module 11 reads the clock around the
  call (instance 2).
- **R4-5, accepted.** The token is called a per-run nonce. OPEN 4 says what it guards and what
  it does not.
- **R4-6, accepted.** Carried: the design document's section 9 drops "allowReal".
- **R4-7, accepted.** One path from config for the mock's port.
- **R4-8, accepted.** The header states the pairing; a wrong pair is PHONE_NOT_SENT.
- **R4-9, accepted.** No latch check in the connect; the check before the send covers it.

## Round 4: verdict
I read phone_client.md, phone_client.h and phone_mock.h again in full. Both headers compile
with `gcc -fsyntax-only -Wall -Wextra -x c` against perf.h and runtime.h. No new request was
sent.

**Landed.** Every one of the thirteen answers and nine findings is in the files.
- R4-1: both stamps are send times. The motion stamp follows the second latch check. The C
  stamps are private `_Atomic uint64_t`. The slow-connect test is listed.
- R4-2: `http.client` on `DeadlineSocket`. The parser is gone from section 7b and section 8.
- R4-3 and R4-4: `PhoneResult` holds the outcome and the status only. Instance 2 reads the
  clock around each call and tests `PHONE_OK` alone.
- R4-5 to R4-9: the nonce wording, the grep result, the two carries, config's port, the
  body rule and the connect without a latch check are all present.

**New findings from the changes.**

**V4-1 (medium, safety). A fresh client halts on every Die, even with no motion ever sent.**
- Evidence: the hand-over halts when
  `last_good_stop_left_ns < last_motion_left_ns + PHONE_LATE_ACTION_NS`. Both stamps start at
  0, so the test reads `0 < 1 s`. That is true.
- The case: a pilot flies on the RC, and no mission or stop is ever sent. Die then sends the
  halt, a /c/fly. It takes the pilot's sticks for up to 600 ms (fact 4).
- The design's own test, `test_handover_halts_only_after_motion`, fails on a fresh client.
- Change: halt only when a motion request has left. In Python:
  `if c.last_motion_left_ns and c.last_good_stop_left_ns < ...`. The header comment adds
  "after a motion request left".

**V4-2 (low). The 20 ms latch check in the reply wait has no code.**
- Evidence: a comment in `request_on` claims it. `DeadlineSocket.recv_into` sets only the
  time left.
- Change: show it. `recv_into` waits `min(time left, 20 ms)`. On a timeout it loops while the
  latch is open and time is left. The latch reaches the socket as one attribute. Python's
  `SocketIO.readinto` re-raises a timeout, so the loop must sit in `recv_into`.

**V4-3 (low). One measurement row describes the deleted parser.**
- Evidence: section 7b's row "NO_REPLY at 500.6 ms" measured the raw exchange of round 1.
- Change: the row gives plain `http.client` 11,707 ms and `DeadlineSocket` 500.2 to 500.9 ms
  (round 4, own 127.0.0.1 server, three runs).

**Grilling.** No answer is weak. One question stays for the owner's reading, not the author.
- Q4-2's margin, 1 s, is unverified until the human's secured field test (OPEN 6).

**Verdict.** The changes landed and are correct. V4-1 is a one-line fix. Ready for the owner
once V4-1 lands. V4-2 and V4-3 can land with it.

## Round 4: the verdict's fixes
- **V4-1, accepted.** The halt now needs a motion request that ever left. The header and the
  hand-over's code say so. A new client with no motion sends no halt.
- **V4-2, accepted.** `DeadlineSocket.recv_into` now waits in 20 ms slices for a motion send.
  It checks the latch and the deadline before each slice. Its raise stays inside the guarded
  HTTP domain; `request_on` catches it.
- **V4-3, accepted.** The trickle row gives the deadline socket's 500.2 to 500.9 ms.
- Open for the owner: the 1 s halt margin, unverified until the human's secured field test.

## After the reviews: the owner's six reviews of 2026-10-18
The conclusions above list the open points as they stood after round 3. The owner has since
ruled on every one; the module's document holds his words (phone_client.md section 6).
- The hand-over: option a (the halt after any motion, a stop, a second stop).
- The mock: the app's supervisor starts it when CONTROL is "mock"; BUDGET_SPENT_DIE.
- The phone microphone's listener: speech in. No mock token. The env: additions (RUN15).
- The groundstation never cuts the motors. phone_mock.h stays.
- The client is blind to its server: PhoneClientCreate(ipv4, port), one PhoneSend, four
  outcomes, no flag, no tracer.
