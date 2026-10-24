# Brief: the phone client design agent (harden2 rev5, module 7)

The owner asked for this file on 2026-10-17 ("prepare their prompts and files"). It is the
agent's handoff document: the brief on top, the progress log at the bottom. The agent updates
the log at every checkpoint. The manager agent reads the log and every file this agent writes.

## 0. Drone safety, before anything else (CLAUDE.md, verbatim in part)

"The assistant NEVER sends arm / takeoff / land / stick / velocity / motor commands to a real
drone." "The assistant runs these ONLY against the mock (`127.0.0.1`), NEVER against a real
phone/drone IP." "Default to read-only. When in doubt, do not send."
For you: every request you send goes to the mock at 127.0.0.1:8079, which you launch yourself.
You never type a phone IP. If a config value points at a real host, you stop and write that in
the log.

## 1. Your job

Design the phone client module of harden2 and deliver two files the owner can review in 15
minutes: `phone_client.md` and `phone_client.h` in this folder. The module's job, in one
sentence: the one client of the phone app, or of the mock that stands in for it.
The module covers the client, the probe of the phone, Die's hand-over and notify actions, and
the mock's process spec.

You design from the owner's words and the architecture document. You do not transcribe
today's code into C. You do not copy the rev4 sketch; it was rejected.

## 2. Read first, in this order

1. /root/groundstation/CLAUDE.md and /root/groundstation/docs/guidelines.md (the house rules).
2. /root/groundstation/docs/api-harden2/rev5/modules/README.md: the document order (MOD1),
   the open-point form (MOD2), the eleven-point gate, the house split, the state table.
3. /root/groundstation/docs/api-harden2/rev5/01-system-architecture.md: section 2 (HTTP :8080
   on the phone, :8079 the mock; the phone's server is ktor CIO and concurrent), section 3 (the
   platform worker thread and the emergency thread), section 4 (the message queue; the
   PlatformReply message), section 9 (the phone dead: WAITING, a probe every 2 s; a real drone
   is human-only; the loopback check), section 10.
4. /root/groundstation/docs/task-active-harden2-handoff-2026-10-02.md, section 2a3: part C
   (the procedure), part D (what each review taught), part E item 7 (this module), items 8, 9
   and 11 (your consumers), part F.
5. The three approved modules. Runtime is your main contract:
   /root/groundstation/docs/api-harden2/rev5/modules/03-runtime/runtime.md, runtime.h and
   runtime_internal.h. Read Die: DieSetHandover and DieSetNotify take one DieActionFn
   (ctx, reason, deadlineNs); the hand-over sends two POSTs itself on its own connection, under
   1 s; the notify is one POST /tts under 0.5 s. Read ProcessSpec, ProcessStopPolicy,
   ReadyProbeFn, BudgetSpentPolicy and StatusRow for the mock's spec and the "phone" row. Then
   perf (perf.md, perf.h, perf_record_platform.h, which moves into your header) and telemetry
   (telemetry.md and telemetry_record_dispatch.h: the stop's reply reaches the main thread as a
   PlatformReply message, TEL7).
6. The ledger rows that bind this module, in /root/groundstation/docs/spec-harden2-cleanup.md:
   NAM2, D2, PROC2, OWN1, A15, TEL7, RUN3, RUN4, RUN9, RUN14, RVW3, RVW4, SYS1, SK4, MOD1,
   MOD2, GATE1, DOC1. Quote the owner's words in the document's rulings section.
7. Today's code, to describe what is wrong with it, not to copy it:
   /root/groundstation/projects/integration_harden2/dji_app/client.py (the client, from_env,
   the mock spec), /root/groundstation/tools/dji_mock/mock_apiserver.py (the mock: its routes,
   its shutdown), and /root/groundstation/projects/integration_harden2/config/ for every value.
8. One finished review record, as the model for yours:
   /root/groundstation/docs/api-harden2/rev5/test/runtime-conclusions.md and
   runtime-round-1-reviewer.md.

## 3. The facts you start from (handoff part E, item 7)

- The routes: POST /c/fly (a mission JSON), /c/stop, /c/takeoff, /c/land, /tts; GET /status/.
- The owner's names PlatformCommandDispatcher, SetManualControlMode, SendEmergencyStop and
  SendCmdList belong to the dispatcher (module 11, NAM2). Your client SENDS; it decides nothing
  and holds no manual flag. The dispatcher keeps no log (D2).
- Two threads send: the platform worker (missions, takeoff, land, tts) and the emergency thread
  (the stop). The emergency thread has its own connection and never waits for the worker.
- The stop's reply reaches the main thread as a PlatformReply message from the emergency thread
  (TEL7). Die is a third sender of the stop; it uses its own connection (the hand-over: a stop,
  then manual, 400 ms each).
- The phone dead: the "phone" row says WAITING and the probe runs every 2 s until /status/
  answers. A real drone is human-only; the loopback check decides mock against real.
- The mock's spec: /status/ as the probe, ready within 25 s, SIGINT, a 1 s shutdown, the TCP
  line closed in on_shutdown, BUDGET_SPENT_WAIT_FOR_USER. The mock reports "mock: true" in its
  status (A15, a future consideration).
- PERF_DJI_REQUEST (path, status) and PERF_EMERGENCY (turn, status) move into your header.
- Open since RVW3: the stop response time on the mock, never measured.

## 4. What you must settle (each one lands in the document and the header)

1. The client's API: Create with host, port, the real-allowed flag, a timeout and the perf
   tracer; one send function per route, each returning a status and the duration; Destroy
   closes every connection. No decision logic inside.
2. The connections: one per sending thread (the worker, the emergency thread, Die), persistent
   or per request, and what a stale connection does after the phone app restarts. The emergency
   path must never queue behind a mission POST; show it.
3. The hand-over and the notify as DieActionFn functions of this module, registered by the app
   once the client exists: two POSTs, 400 ms each, on their own connection, under the 1 s cap;
   one POST /tts under 0.5 s. They run when our own code is broken (RVW4), so they use nothing
   that can be broken: no queue, no row, no lock shared with the worker.
4. The probe: GET /status/ every 2 s while the phone does not answer; the "phone" row the module
   owns (a StatusRow); who runs the probe thread and when it stops. TOCTOU (gate item 11): the
   row read as UP, then a POST to a phone that just went away; state the rule.
5. The mock's pure spec function (argv, env, the probe, 25 s, the stop policy, the budget
   policy, the log path). Question BUDGET_SPENT_WAIT_FOR_USER for a laptop part: the handoff
   says it, you give the reason for or against, as an open point.
6. The TCP line. Speech in (module 8) names this module "the TCP line's owner": the phone sends
   its speech text over a persistent TCP socket to the laptop. Settle where that listener lives
   and how speech in receives the lines, as an open point in the four-line form.
7. The measurement (section 7): the stop response on the mock, p50, p90 and max over at least
   200 requests, with a mission POST in flight on the other connection.
8. The failure matrix: the phone dead, a timeout, a 4xx or 5xx, a stale connection, the mock
   budget spent, Die mid-flight. For each: the row, the record, and whether the aircraft is
   touched. Nothing in this module arms or moves the aircraft; the stop and manual are the only
   motion-related sends, and they come from the dispatcher or Die.

## 5. The rules of the deliverable

- Only `phone_client.md` and `phone_client.h` in this folder, plus `phone_client_internal.h`
  only if the owner must see a mechanism to judge the design (RUN4). No drawing. No other file
  (DOC1).
- `phone_client.md` follows the MOD1 order in modules/README.md: the job, the picture (one
  text diagram), the usage (two pseudocode instances in the Python of the build), the open
  points (MOD2, the four-line form: the problem, now, on "no", recommended), then today, the
  rulings, the gate answers with the failure matrix, the notes.
- The header reads without its comments (RUN3). Create and Destroy; handles the app owns;
  `_Atomic` types for every shared value; m_ prefixes; no implementation comments. Anonymous
  `typedef enum {`; comment blocks above enums; no commas inside enum comments; 64-bit and
  float constants as macros (`UINT64_C`), never `static const`.
- Lay the header out with `python3 /root/groundstation/tools/style/header_layout.py <file>`.
  The tool reflows comments and realigns spacing; edit with line ranges, not exact strings.
  Compile with `gcc -fsyntax-only -Wall -x c <file>` with the perf, runtime and telemetry
  folders on the include path.
- Prose in STE: one idea per sentence, under 20 words. Standard field terms (a persistent TCP
  connection, a readiness probe, a keep-alive). Banned words: wire, seam, load-bearing, sieve.
  No em-dashes. No Hebrew inside an English sentence.
- No git write of any kind. No file outside this folder and your one record file.
- Mark every number you did not measure "unverified".

## 6. The procedure

1. Read everything in section 2. Write the full picture of the module in the system before
   any design: the three senders, their threads, the phone's concurrent server, the rates.
2. Design. Reason from the forces to one proposal per point in section 4. Where the owner must
   choose, write the four-line form. Where the design is clear, decide and state the reason.
3. Write `phone_client.md` and `phone_client.h`. Run the layout tool and gcc.
4. Run the eleven-point gate yourself. Each item gets the failure you tried and the mechanism
   that stops it, written in the document's gate section. Item 9 needs measurements (section
   7). Put the numbers and the commands in the document. Do not add scripts to the repo.
5. Three reviewer rounds with subagents, one at a time. Each round: spawn one subagent
   (general-purpose, model opus, maximum care, the web for sources). Give it the module's files,
   this brief's sections 0, 3 and 4, and the three lenses of round 1 (storage and hardware;
   concurrency and real time; YAGNI and decoupling). It writes only its section into
   /root/groundstation/docs/api-harden2/rev5/test/phone_client-review.md under
   "## Round N: reviewer". You answer under "## Round N: answer": accepted with the change made,
   or rejected with the reason. Rounds 2 and 3 are the push-back and the landing check. End the
   file with "## Conclusions": agreed, open, changed.
6. Update the document and the header after every round. Re-run the layout tool and gcc.
7. Write the progress log below. Return one line to the chat.

## 7. The machine and the measurements

- Launch the mock yourself: `python3 /root/groundstation/tools/dji_mock/mock_apiserver.py
  127.0.0.1 8079` (check its arguments in the file first). Stop it with SIGINT when done.
- Measure, in your scratch folder, against 127.0.0.1:8079 only: POST /c/stop p50, p90 and max
  over at least 200 requests, with a /c/fly POST in flight on a second connection; the cost of
  a new connection per request against a kept connection; GET /status/ time. Record the numbers
  and the commands in the document.
- No GPU is needed. Port 8079 is yours while the mock runs. Take it before:
  `/root/groundstation/tools/lock.sh wait phone_client port-8079`. Release it after:
  `/root/groundstation/tools/lock.sh release phone_client all`.
- Two other agents work at the same time on the frame buffer and the llama server. You do not
  edit their folders, the ledger, the handoff, or modules/README.md. The manager records the
  owner's rulings there.

## 8. Done when

- Both files exist, the header compiles, the layout tool ran clean, every gate item has its
  proof in the document, the review record holds three rounds and the conclusions, every open
  point is in the four-line form with an OPEN mark in the header, the stop response is
  measured, and the log below says so.

## 9. Superseded by the owner's rulings (2026-10-18; added by the phone client agent)
The brief above stays as written. These parts of it no longer hold; phone_client.md section 6
has the owner's words.
- Section 3: "a real drone is human-only; the loopback check decides mock against real". The
  client is blind to its server now; the launcher picks it from CONTROL.
- Section 3: "the TCP line closed in on_shutdown", "BUDGET_SPENT_WAIT_FOR_USER", "mock: true".
  The mock closes its WebSockets; its policy is BUDGET_SPENT_DIE; no mock check exists.
- Section 3: "a stop, then manual, 400 ms each". Die sends option a: the halt after any motion,
  a stop, a second stop.
- Section 4, item 1: "Create with host, port, the real-allowed flag, a timeout and the perf
  tracer; one send function per route". Create takes an address and a port; one PhoneSend;
  no flag, no timeout, no tracer.
- Section 4, item 6: the TCP line. Speech in owns it.
- Section 5: "Only phone_client.md and phone_client.h ... plus phone_client_internal.h only if".
  phone_mock.h is a fourth file, kept by the owner (D7).

## Progress log (newest at the end)


- 2026-10-17, checkpoint 1 (read). Read every source of section 2. Findings that shape the
  design: the phone API has no "manual" route (today manual = POST /c/stop plus a local flag,
  control/flight.py), so the hand-over's second POST needs an owner point; the TCP line is
  dialled by the phone into a laptop listener (audio/asr_phone.py), so this client never holds
  it; the mock has no on_shutdown and the aiohttp default shutdown_timeout of 60 s; today's
  loopback check accepts "localhost", a name that resolves at connect time. CONTROL defaults to
  mock; no config value points this agent at a real host.
- 2026-10-17, checkpoint 2 (designed, measured). phone_client.md, phone_client.h and
  phone_client_internal.h written; both headers compile (gcc -Wall -Wextra) and passed
  header_layout.py. Measured on the mock at 127.0.0.1:8079 only (lock port-8079 held): POST
  /c/stop with a /c/fly held open on a second connection, 300 per row, two runs: p50 0.208 and
  0.365 ms, p90 0.251 and 0.435 ms, max 0.862 and 1.074 ms (new connection per request); a
  kept connection after a mock restart fails with RemoteDisconnected; today's mock ignores
  SIGINT with an open WebSocket (no exit in 8 s), a patched copy in the scratchpad exits in
  41 ms. The mock's command log holds only /c/stop and the HALT mission. Four open points.
  Next: three reviewer rounds.
- 2026-10-17, checkpoint 3 (round 1). The reviewer gave 16 findings (1 critical, 4 high, 5
  medium, 6 low); 15 accepted, R1-3 in part (the kept stop connection rejected: a half-open
  socket swallows a stop). Changes: a raw HTTP/1.1 send with one total deadline (measured
  500.6 ms for 0.5 s); 250 ms connect attempts; a halt route; three atomics in the endpoint
  (the motion block and in-flight count for Die, the mock confirmation); fixed row pairs with
  the phone's 503 texts; the hand-over now blocks, drains, halts, then stops; OPEN 5 (the
  spec's env) and OPEN 6 (/c/stop's KeyEmergencyStop in the air, unverified). Measured the stop
  under a stand-in load: p50 0.2 ms; four spinning threads push it past 1 s. Headers compile.
- 2026-10-17, checkpoint 4 (round 2). 11 findings (3 high, 1 medium, 7 low), all accepted. The
  hand-over is now the motion block and two stops (no halt: on the phone a late takeControl()
  can take a pilot's sticks); a motion send aborts itself within one 20 ms slice once blocked
  (measured 60 ms and 100.6 ms); parallel connect attempts every 250 ms (a 300 ms round trip
  connects at 601 ms, measured with netem in a private namespace); the phone's "ok" field; a
  strict inet_pton host check. The prose passes a 20-word check. Next: round 3.
- 2026-10-17, checkpoint 5 (done). Round 3: 6 findings (1 high, 2 medium, 3 low), all
  accepted. The hand-over is now the motion block, the halt when the sticks may be ours (the
  phone's /c/stop leaves its flight job running), then two stops; measured 603 to 605 ms on the
  mock. The record ends with "## Conclusions". Done-when check: phone_client.md,
  phone_client.h and phone_client_internal.h exist; both headers compile (gcc -Wall -Wextra)
  and passed header_layout.py; every gate item has its proof and the failure matrix; three
  rounds and the conclusions are in rev5/test/phone_client-review.md; six open points in the
  four-line form, each marked OPEN n in a header; the stop response measured (p50 0.21 to
  0.37 ms, max 1.07 ms with a mission open). Port lock released; the mock is stopped; no git
  write. Not done by this agent: the ledger, the handoff and modules/README.md (the manager's).
- 2026-10-18, the owner's review of the design, verbatim: "1. You shoved way too many
  contracts into a single header 2. Why do you have ownership/a handle of the performance
  module? 3. Using booleans to establish whether access is allowed or not is extremely terrible
  security practice? Claude, I know you're good at cybersecurity, why make such a dumb mistake?
  4. internal API Seems overengineered, including the external contract. 5. Perform another
  single review with a subagent that'll use the skills available to it. I installed recently
  the skills for architecture design and review of matt peacock, he can use them to interrogate
  you about your design, YAGNI, KISS, you name it." Not yet in the ledger (the manager's).
- 2026-10-18, checkpoint 6 (revised for the owner's points 1 to 4). phone_client_internal.h
  deleted; phone_client.h cut from 179 to 80 lines (two constructors, one PhoneSend with a
  route enum, three outcomes, no tracer, no endpoint struct); the mock's contract in
  phone_mock.h (18 lines; OPEN 7 asks for this second header under DOC1); the mock proves a
  per-run token on the same connection before every request (measured: 0 to 0.17 ms p50 on the
  mock); the Die latch private and one-way. Both headers compile and passed the layout tool.
  Next: the single review with Matt Pocock's skills (round 4 in the record).
- 2026-10-18, checkpoint 7 (round 4, the skills review). The reviewer loaded
  mattpocock-skills:codebase-design, mattpocock-skills:grilling and ponytail:ponytail-review:
  13 questions, 9 findings (1 high, 2 medium, 6 low), all accepted. The high one: the hand-over
  could skip the halt after a mission with a slow connect; the stamps are now send times with a
  1 s margin (unverified). Also: http.client on a deadline socket replaces the hand-written
  parser; four outcomes replace the ok flag; the result holds no times.
- 2026-10-18, checkpoint 8 (round 4 verdict). Every round 4 change landed. Three new items
  (V4-1 medium: no halt before any motion; V4-2, V4-3 low) fixed. Headers compile; prose
  check clean. Ready for the owner; the ledger entry for the owner's five points is the
  manager's.
- 2026-10-18, the owner's second review, verbatim: "1. I have a couple more points before I
  address your questions: * Why 2 functions that practically do the same thing?
  PhoneClientCreateForMock & PhoneClientCreateForPhone should each call a singular
  PhoneClientCreate() with their specific arguments. They should be helper functions. * Now
  that the phoneclient is opaque, what the hell is its internal structure? How does it actually
  work? Sure You gave me a contract, you detailed the contract for everyone to use, and then
  down the bottom you detailed the functions required for Die() to call s.t. a proper exit
  happens. * phone_mock looks good? I think? How does you actually create & destroy it? 2. Now
  your questions: D1 - Speak to the managing agent regarding this D2 - What kind of fuckass
  situation did you get to that this actually happens? D3 - What does "Phone's transcript
  listener" mean? D4 - What would this entail? D5 - Be more specific D6 - No. The groundstation
  doesn't have that kind of authority. Never. D7 - I mean, you already did it lol."
- 2026-10-18, checkpoint 9. Rulings applied: D6 closes OPEN 6 (the groundstation never cuts
  the motors); D7 keeps phone_mock.h. One PhoneClientCreate(PhoneTarget) in
  phone_client_internal.h (back, 69 lines: the struct and the send's steps in call order); the
  two public functions are helpers over it. D2 measured: a handler bug gives a 500 and the mock
  lives; a held port exits 1 in 195 ms; a missing aiohttp fails at import: so OPEN 2 now
  recommends BUDGET_SPENT_DIE. D3, D4, D5 rewritten plainly. D1 sent to the managing agent.
  Headers compile; prose check clean.
- 2026-10-18, checkpoint 10 (D1 from the manager, groundstation-0f). The manager confirmed
  facts 1 to 3 and added fact 4 (every fly job takes the sticks, line 484, and never gives
  them back) and fact 5 (a timed retake after an RC override, lines 364 to 399). Verified in
  the source: the phone uses the defaults (AircraftControlVM.kt line 17), so this source has
  no timed retake. Applied: the hand-over's skip condition is dropped (a stop never ends the
  job); the halt now follows any motion request this run; one atomic count replaces the two
  timestamps; PHONE_LATE_ACTION_NS is gone. Measured: the halt holds a pilot's sticks 0.59 ms
  p50, 1.55 ms max on the mock until the first stop is answered. OPEN 1 now holds options a,
  b and d (the manager's two Kotlin lines in stop()); it stays open; the manager carries it.
- 2026-10-18, the owner's third review, verbatim: "1. I don't understand the options for D1,
  explain yourself more clearly. Also, as soon as a stick sends commands to the drone, I'm
  aware that it always takes precedence, no matter the situation. Have the manager check this
  and verify/refute it. 2. D2 - Why do we launch the mock in the first place? The mock should
  be run separate from the program we create. Not only that, don't we use a script to start
  all relevant programs? Or is it simply that, we have the supervisor prepare the whole
  environment, only to finally launch our program? What is the order here exactly? Create a
  diagram if you want. 3. WHAT THE FUCK DOES "PHONES SPOKEN TEXT" MEAN????? WHAT DOES THIS
  MEAN????? 4. What the fuck does this mean? 5. Is there such a big overlap between the
  initial env vars and the process being launched? Simply by design, the env vars should be
  empty in the initial process, unless we set the env char array to an addition between the
  current vars + whatever we want to additionally include. Does this kind of answer your
  question? Did I miss the mark?"
- 2026-10-18, checkpoint 11. D1's options renamed a, b, c (the manager's d is now c). OPEN 2
  rewritten: the mock inside the supervisor or started by run.sh like the phone (the 2026-09-22
  rule covers only processes the app starts). OPEN 5 marked answered by the owner's words:
  the child's env is the current env plus the spec's additions. The stick-precedence claim
  sent to the manager to verify.
- 2026-10-18, checkpoint 12. The manager's verdict on the stick claim (ledger PHN4): refuted as
  "always"; it holds only while the phone app runs. Written into OPEN 1 with its four points
  and fact 6 (DJIVirtualStick.kt line 47 ignores the firmware's owner, verified). D5 is ledger
  RUN15. D1 to D4 still wait for the owner.
- 2026-10-18, the owner's fourth review, verbatim: "D1 - We will not modify the code on the app
  side. What choices do we have? Can you actually formulate the options properly? D2 - I don't
  like that we write to app.sh. What is this shit? Furthermore, I do not understand the deal
  with the Token passed to PhoneClientCreateForMock? ALSO WHAT DID I SAY REGARDING
  PHONECLIENT??? REGARDING BOTH FUNCTIONS?? YOU COMPLETELY IGNORED IT! D3 - Correct. Speech In
  owns this module, ITS IN THE GOD DAMN NAME! WHAT IS THIS ? SPEECH OUT? WHAT IS THE MODULE WE
  ARE CURRENTLY WORKING ON FORMALLY CALLED IN OUR DESIGN??? D4 - In what universe does this
  situation happen, HUH BUBBA? D5 - Good!"
- 2026-10-18, checkpoint 13. Rulings: D1 no change to the phone app (option c gone); D3 speech
  in owns the listener; D4 the token is dropped (no realistic case: a deliberate adb forward,
  which no script makes); D5 approved. PhoneClientCreate is public again, with the two helpers
  as one-line inline calls to it, as the owner asked on 2026-10-18. app.sh is replaced by
  tmux -e in the proposed start order (tested: tmux 3.4).
- 2026-10-18, checkpoint 14. The manager reports the owner's ruling to it (ledger PHN6),
  quoted: "Leave that aside for the subagent and me. Not your responsibility currently." So
  OPEN 1 (Die's hand-over) is settled between this agent and the owner. The three laptop-only
  options stay as written. When the owner rules, his words go into this log; the manager copies
  them into the ledger and edits runtime.h line 25.
- 2026-10-18, the owner's fifth review, verbatim: "D1 - I approve A! D2 - * Why do we try to
  kill the old stack if we properly close everything on our own? This is a applying a bandaid
  that is un-necessary, a wound that doesn't exist. * Why does PhoneClientCreate have the phone
  guard here? Does the phone client care? It only does what its being told to! IT IS OUR
  RESPONSIBILITY TO LAUNCH THEM PROPERLY AND NOT MIX OIL WITH WATER! CLAUDE! D3 - Good! D4 -
  GOOD! I'll say another additional comment regarding D2 - Would it be easier for us to manage
  the telemetry/perf from the mock by launching it from the supervisor, say, by enabling a flag
  upon init to the main, which, in turn, will cause the mock to begin? This way, the "Mock
  Mode" is hard-wired into the app, and the false state (real control, not mock), will only
  launch with the correct settings. I know that I should strive to separate concerns, but since
  our main is technically a launcher anyways, this doesn't stray too far from such a design in
  the first place - IF its actually useful, as I described, or in any other way, and doesn't
  hurt us in the long term with architecture. Needless to say, the phone client should be
  agnostic to the server its sending the data to, and it should not need to know whether its
  sending data to the mock, or to the real control."
- 2026-10-18, checkpoint 15. Rulings: D1 = option a (halt, stop, stop), for the manager's ledger
  and runtime.h line 25; D3 and D4 confirmed. Applied: the client is agnostic of its server:
  PhoneClientCreate(ipv4, port) checks only that the host is a dotted IPv4 literal; the mock or
  real choice and its guard move to the launcher (config's CONTROL); the two helpers go, since
  they encoded mock and real in the client. No "kill the old stack" in the start order.
- 2026-10-18, the owner's sixth review, verbatim: "I approve all of what you said! I think you
  now understand who I want to start the mock, too. After you tell me what has been decided
  (if you correctly guess on this turn), then please double check the staleness of all
  documents inside your module, and update them accordingly."
- 2026-10-18, checkpoint 16. Read as the ruling: the app's supervisor starts the mock when
  CONTROL is "mock" (his proposal of the fifth review); approved with it: no stack kill, no
  app.sh, the client blind to its server, the helpers gone. Next: a staleness pass over every
  file of the module.
- 2026-10-18, checkpoint 17 (staleness pass done). phone_mock.h: the supervisor starts the mock
  (ruled), BUDGET_SPENT_DIE, the env addition. phone_client.md: no open point; the mock's spec
  and start order as ruled; the failure matrix's mock rows; the carried items; the tests. This
  brief: section 9 lists the superseded parts. The review record: a closing note. All three
  headers compile; the document passes the 20-word check. modules/README.md's state row is the
  manager's.
