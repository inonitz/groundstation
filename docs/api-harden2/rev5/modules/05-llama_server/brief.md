# Brief: the llama server design agent (harden2 rev5, module 5)

The owner asked for this file on 2026-10-17 ("prepare their prompts and files"). It is the
agent's handoff document: the brief on top, the progress log at the bottom. The agent updates
the log at every checkpoint. The manager agent reads the log and every file this agent writes.

**The state on 2026-10-18.** Sections 1 to 8 below are the brief as given on 2026-10-17.
The owner's rulings have changed four of its facts since: 9 slots, not one (D2); a Unix
domain socket, not HTTP :18090 (D4); no hang rule (D3); no perf tracer in the client
(PHN1). The perf and runtime folders are now 01-perf and 03-runtime. The current design is
llama_server.md and llama_server.h.

## 1. Your job

Design the llama server module of harden2 and deliver two files the owner can review in 15
minutes: `llama_server.md` and `llama_server.h` in this folder. The module's job, in one
sentence: the one llama-server process of the app and its client, one request at a time.

You design from the owner's words and the architecture document. You do not transcribe
today's code into C. You do not copy the rev4 sketch; it was rejected.

## 2. Read first, in this order

1. /root/groundstation/CLAUDE.md and /root/groundstation/docs/guidelines.md (the house rules).
2. /root/groundstation/docs/api-harden2/rev5/modules/README.md: the document order (MOD1),
   the open-point form (MOD2), the eleven-point gate, the house split, the state table.
3. /root/groundstation/docs/api-harden2/rev5/01-system-architecture.md: section 2 (the
   processes; HTTP :18090), section 3 (the threads that send a request), section 8 (489 ms a
   plan alone, 1362 ms while SAM3 runs), section 9 (the failure handling), section 10.
4. /root/groundstation/docs/task-active-harden2-handoff-2026-10-02.md, section 2a3: part C
   (the procedure), part D (what each review taught), part E item 5 (this module), part F.
5. The three approved modules. The runtime module is your main contract:
   /root/groundstation/docs/api-harden2/rev5/modules/03-runtime/runtime.md, runtime.h and
   runtime_internal.h. The supervisor OWNS the process (RUN9). Your module gives a pure spec
   function that returns a ProcessSpec; it never launches or stops the process. Read
   ProcessSpec, ProcessStopPolicy, ReadyProbeFn, BudgetSpentPolicy, StatusRow and
   SupervisorWaitUntilReady. Then perf (perf.md, perf.h, and perf_record_llama.h, which moves
   into your header) and telemetry (telemetry.md, for the shape only).
6. The ledger rows that bind this module, in /root/groundstation/docs/spec-harden2-cleanup.md:
   PROC2, OWN1, REC1, RUN3, RUN4, RUN9, RUN14, RVW4, SYS1, TEL4, MOD1, MOD2, GATE1, DOC1.
   Quote the owner's words in the document's rulings section.
7. Today's code, to describe what is wrong with it, not to copy it:
   /root/groundstation/projects/integration_harden2/gemma/server.py (the spec, the argv, the
   ready check, the warm-up), gemma/client.py (the client),
   /root/groundstation/projects/integration_harden2/perception2/vlm_client.py (the describe
   request with an image), and /root/groundstation/projects/integration_harden2/config/ for
   every value (config is the one source; only defaults.py reads the environment).
8. One finished review record, as the model for yours:
   /root/groundstation/docs/api-harden2/rev5/test/runtime-conclusions.md and
   runtime-round-1-reviewer.md.

## 3. The facts you start from (handoff part E, item 5)

- One process, one slot (`-np 1`), one request at a time. Two callers: the recognizer's planner
  request on a turn thread, and the describe job with a JPEG of the held frame (Q4 a).
- The supervisor relaunches the process; the module's spec gives the stop policy: SIGINT, then
  SIGINT again after 2 s, then the kill after 10 s (measured in the runtime review).
- The L1 warm-up runs after the row says UP, on the app's start thread. The module owns its own
  "warm" row (a StatusRow).
- The request is timed from the app: PERF_LLAMA_REQUEST with req, label, ok, and the server's
  token timings. perf_record_llama.h moves into your header.
- Known gotchas, from the owner's runs: `--image-min-tokens` breaks the CLIP load; q4_0 KV with
  flash attention gives empty output; thinking off needs both flags (`--chat-template-kwargs`
  and `--reasoning-budget 0`).
- Native programs run only from build/release/shared/dji/bin (config.NATIVE_BIN_DIR), first on
  LD_LIBRARY_PATH.

## 4. What you must settle (each one lands in the document and the header)

1. The pure spec function: argv from config, env with the native path, GET /health as the
   probe (200 ready, 503 loading) under the 200 ms call cap, a 240 s ready timeout, the stop
   policy above, BUDGET_SPENT_DIE (a laptop part).
2. The client's connection handling. One persistent connection or one per request; what happens
   to a kept connection after the supervisor relaunches the server (a stale socket); the client
   closes its connections before a normal shutdown. This is a TOCTOU item (gate item 11): the
   row read as UP, then the request sent to a dead server. State the rule: the reply is the
   truth, the row is a hint.
3. The warm-up: who sends it, what it sends (the planner's warm sentence; the recognizer builds
   the messages, REC1), and how the "warm" row changes.
4. The request call: the messages JSON, an optional grammar, max tokens, a timeout, an optional
   image (the describe job's JPEG), the reply, and the server's timings parsed from the reply.
   One function or two; state the reason.
5. The timeouts: a plan alone 489 ms, 1362 ms while SAM3 runs; the request timeout, and what the
   caller gets on a timeout (false, never an exception; our code never throws).
6. The perf record: PerfLlamaRequest moves here with its keys (req, label, ok, cn, pn, gn, pm,
   gm). The payload stays under the 128-byte record.
7. The failure matrix: the server down, RECOVERING, a timeout, an invalid reply, a GPU
   out-of-memory, the budget spent. The aircraft is never touched by this module.

## 5. The rules of the deliverable

- Only `llama_server.md` and `llama_server.h` in this folder, plus `llama_server_internal.h`
  only if the owner must see a mechanism to judge the design (RUN4). No drawing. No other file
  (DOC1).
- `llama_server.md` follows the MOD1 order in modules/README.md: the job, the picture (one
  text diagram), the usage (two pseudocode instances in the Python of the build), the open
  points (MOD2, the four-line form: the problem, now, on "no", recommended), then today, the
  rulings, the gate answers with the failure matrix, the notes.
- The header reads without its comments (RUN3). Create and Destroy; handles the app owns;
  `_Atomic` types for every shared value; m_ prefixes; no implementation comments. Anonymous
  `typedef enum {`; comment blocks above enums; no commas inside enum comments; 64-bit and
  float constants as macros (`UINT64_C`), never `static const`.
- Lay the header out with `python3 /root/groundstation/tools/style/header_layout.py <file>`.
  The tool reflows comments and realigns spacing; edit with line ranges, not exact strings.
  Compile with `gcc -fsyntax-only -Wall -x c <file>` with the perf and runtime folders on the
  include path.
- Prose in STE: one idea per sentence, under 20 words. Standard field terms (a persistent TCP
  connection, a keep-alive, a readiness probe). Banned words: wire, seam, load-bearing, sieve.
  No em-dashes. No Hebrew inside an English sentence.
- No git write of any kind. No file outside this folder and your one record file.
- Mark every number you did not measure "unverified".

## 6. The procedure

1. Read everything in section 2. Write the full picture of the module in the system before
   any design: the process, its probe, the two callers, the rates, the timings.
2. Design. Reason from the forces to one proposal per point in section 4. Where the owner must
   choose, write the four-line form. Where the design is clear, decide and state the reason.
3. Write `llama_server.md` and `llama_server.h`. Run the layout tool and gcc.
4. Run the eleven-point gate yourself. Each item gets the failure you tried and the mechanism
   that stops it, written in the document's gate section. Item 9 needs measurements (section
   7). Put the numbers and the commands in the document. Do not add scripts to the repo.
5. Three reviewer rounds with subagents, one at a time. Each round: spawn one subagent
   (general-purpose, model opus, maximum care, the web for sources). Give it the module's files,
   this brief's section 3 and 4, and the three lenses of round 1 (storage and hardware;
   concurrency and real time; YAGNI and decoupling). It writes only its section into
   /root/groundstation/docs/api-harden2/rev5/test/llama_server-review.md under
   "## Round N: reviewer". You answer under "## Round N: answer": accepted with the change made,
   or rejected with the reason. Rounds 2 and 3 are the push-back and the landing check. End the
   file with "## Conclusions": agreed, open, changed.
6. Update the document and the header after every round. Re-run the layout tool and gcc.
7. Write the progress log below. Return one line to the chat.

## 7. The machine and the measurements

- A llama-server launch uses the GPU. Take the GPU before any launch:
  `/root/groundstation/tools/lock.sh wait llama_server gpu`. Release it after:
  `/root/groundstation/tools/lock.sh release llama_server all`. Launch the binary from
  config.NATIVE_BIN_DIR with today's argv from gemma/server.py.
- Measure, in your scratch folder: the /health probe time while loading and when ready; one
  plan request alone (compare with 489 ms); the cost of a new connection per request against a
  kept connection; what a kept connection does after SIGINT and a relaunch. Record the numbers
  and the commands in the document.
- Two other agents work at the same time on the frame buffer and the phone client. You do not
  edit their folders, the ledger, the handoff, or modules/README.md. The manager records the
  owner's rulings there.

## 8. Done when

- Both files exist, the header compiles, the layout tool ran clean, every gate item has its
  proof in the document, the review record holds three rounds and the conclusions, every open
  point is in the four-line form with an OPEN mark in the header, and the log below says so.

## Progress log (newest at the end)


### 2026-10-17, checkpoint 1: the design written
- Read: section 2 in full (CLAUDE.md, guidelines, modules/README.md, the architecture,
  handoff 2a3 C to F, runtime.md/.h/_internal.h, perf.h, perf_record_llama.h, the ledger
  rows, today's gemma/ and vlm_client.py, the runtime review record).
- Measured on the real binary under the GPU lock (port 18991; the lock released): the probe
  while loading and ready; plans on a new and a kept connection; the keep-alive idle close
  (between 4 s and 6 s); a kept connection after SIGINT and a relaunch; an image request;
  a plan behind it; the server's cancel after a client timeout; SIGINT idle and in flight.
  The numbers: llama_server.md section 6. The script stayed in the session scratchpad.
- Decided: one TCP connection per request; no client lock (the server queues); the client
  reads no row; one request function; a result enum; timeouts 10 s, 20 s, 30 s; the warm-up
  at start only, its failure a start-up death.
- Open for the owner: OPEN 1 (a warm-up after a relaunch), OPEN 2 (a plan behind an image
  request).
- Files: llama_server.md, llama_server.h (gcc -Wall -Wextra clean; the layout tool ran).
- Carried, not mine to edit: perf_record_llama.h is now duplicated by this header (the
  manager deletes it at the move); the preflight's free-port check (runtime); whether the
  supervisor merges m_env with the app's environment (runtime); util/guarded.py's HTTP
  helper must return the failure kind.
- Not invoked: /superpowers:brainstorming. It needs a dialogue with the owner; this agent
  has none. The full picture came first, as CTX1 asks.

### 2026-10-17, checkpoint 2: review round 1
- The reviewer (general-purpose, opus) wrote 12 findings: 2 high, 5 medium, 5 low.
- All 12 are accepted; six only in part, with the reason in the record. The new items: OPEN 3
  (a hung server: two timeouts in a row, then a planned restart), LLAMA_CUT, --cache-ram
  512, the alias probe on /v1/models, the deadline test before each socket step. The
  timeouts moved to config.
- Carried, new: the vision module keeps one image request in flight; runtime counts or caps
  a restart on purpose for a hang; the /v1/models probe replaces /health for llama-server.

### 2026-10-17, checkpoint 3: review round 2
- The push-back reviewer wrote 10 findings: 2 high, 5 medium, 3 low. All accepted; R2-5 and
  R2-7 in part.
- New: OPEN 4 (the identity probe, a change to RUN14's /health); the reply's "model"
  checked against the alias; the hang count reset at the fire; T8 and T9; a hard deadline
  on the body read; the image lock with a deadline and a stop-flag check (carried).
- OPEN 3 now names three changes to runtime's approved contract: the planned restart wins
  over a kill; it applies only when UP; a hang restart counts against the budget.

### 2026-10-17, checkpoint 4: review round 3, done
- The landing-check reviewer wrote 6 findings: 0 high, 2 medium, 4 low. All accepted. R3-1
  took another path: the app's onHung callback counts the hang restarts and dies at the
  fourth, so runtime's budget rules stay as approved. The OPEN 3 item "count the hang
  restart" from checkpoint 3 is gone.
- The record test/llama_server-review.md holds rounds 1 to 3, the answers and the
  conclusions (28 findings, all accepted).
- Final state: llama_server.md (697 lines) and llama_server.h (210 lines). The header
  compiles with gcc -Wall -Wextra -Wpedantic -std=c11 against perf/ and runtime/. The
  layout tool leaves it unchanged. Every prose and code line is 89 characters or less.
  No banned word, no em-dash. Every header name appears in the document.
- Gate items 1 to 11 are answered in section 7b, with the failure matrix; TOCTOU T1 to
  T9, each with a test or a named window.
- Open for the owner: OPEN 1 to OPEN 4, each in the four-line form, each marked OPEN n in
  the header.
- Carried (not edited by this agent): runtime (the planned restart after a kill; only when
  UP; a free-port message; the m_env merge; the HTTP helper's failure kind and deadline
  loop); the vision jobs (one image request in flight, with the time left and the stop
  flag); perf (perf_record_llama.h deleted at the move).
- Files written by this agent: llama_server.md, llama_server.h, this log, and its sections
  of test/llama_server-review.md. No git write. The GPU lock is released.

### 2026-10-18, checkpoint 5: the owner's four answers
- The owner answered OPEN 1 to OPEN 4 (his words: llama_server.md section 4). None is ruled
  yet; each asks a question or a confirmation. The manager copies his words to the ledger.
- OPEN 1: his "yes" (re-warm after a relaunch) rests on "re-launching the app"; corrected:
  only the child relaunches. My recommendation changed to his.
- OPEN 2: the image paths found (describe only, by default). -np measured: -np 2
  --kv-unified -c 8192 costs 88 MiB and cuts a plan behind an image request from 3053 ms to
  1315 ms. The note "Why one slot" was wrong and is replaced. Recommended: -np 2.
- OPEN 3: the mechanism and the two runtime rule changes written as code.
- OPEN 4: a Unix domain socket measured (it works; a stale file blocks a relaunch, so the
  supervisor must remove it). Recommended over the alias.
- The header is unchanged: it changes after the owner's rulings.

### 2026-10-18, checkpoint 6: D1 and D4 ruled; OPEN 2 and OPEN 3 answered again
- The owner: "D1 - Yes"; on D4: "Too me it sounds like the payoff is worth it. Does
  llama-server actually support .sock?" It does (help text, common/arg.cpp:3190; our run),
  so D4 is taken as the Unix domain socket. His words are in llama_server.md section 4.
  The manager copies them to the ledger.
- Applied to the header: the warm-up after every relaunch (D1); --host
  <session dir>/llama.sock, LlamaServerHealthProbe on /health, no alias, no port, the
  108-byte sun_path limit (D4). Carried to runtime: ProcessSpec.m_removeBeforeLaunch (a
  stale socket file blocks a relaunch, measured).
- OPEN 2: several vision jobs are measured (2 and 4 image requests at once on -np 1, 2,
  4). Recommended: -np 4 --kv-unified -c 8192, at most 3 image requests at once.
- OPEN 3: rewritten as pseudocode with numbered notes, as the owner asked.
- The perf and runtime folders were renamed 01-perf and 03-runtime by someone else; this
  folder keeps its name. gcc runs with -I 01-perf -I 03-runtime: clean. The layout tool ran.

### 2026-10-18, checkpoint 7
- D4 approved: "I agree. Approved."
- OPEN 2: the design plans for 9 requests at once (one plan, the pool of 8). -np 9
  --kv-unified -c 8192 measured: 233 MiB over -np 1; every request got a slot; the plan
  took 5823 ms beside 8 image requests. Recommended; not ruled.
- OPEN 3: the owner called it too complicated. My view: he is right; no hang was ever seen.
  Recommended: drop the hang rule. Not ruled; the header keeps it until he rules.
- The folder renames (01-perf, 03-runtime): the owner had the manager do them, to keep the
  build order. This folder is not renamed yet.

### 2026-10-18, checkpoint 8
- D2 ruled: "D2 - Option A". Applied: kLlamaServerSlots = 9, -np 9 --kv-unified -c 8192;
  the image lock and its carry to the vision module removed. gcc clean; layout ran.
- The folder is now 05-llama_server (renamed by the manager).
- D3: the owner asked why the hang rule derailed. The analysis is at the end of
  test/llama_server-review.md. Proposed process changes (P1 to P4) wait for his ruling.

### 2026-10-18, checkpoint 9: D3 and D8 ruled and applied
- D3: "D3 - Drop. We need to pass a message to the "manager', s.t. this would not happen in
  the future." Applied: the hang rule is gone from both files (LlamaHungFn, m_onHung,
  m_timeoutsInARow, OPEN 3, T7, T8, the runtime carries). LlamaClientCreate(socketPath,
  perf).
- D8: "D8 - Drop". Applied: one socket timeout per step, as today's code; the per-read
  deadline loop and the "socket deleted by a human" row are gone.
- gcc -Wall -Wextra -Wpedantic clean; the layout tool ran; every line 89 or less.

## MESSAGE TO THE MANAGER (2026-10-18, from the llama server agent, at the owner's order)
The owner ordered this message (D3, above) so that a review does not derail again.

1. **Copy these rulings into the ledger, verbatim.** All are in llama_server.md section 4.
   - D1, a warm-up after every relaunch: "D1 - Yes".
   - D2, -np 9 --kv-unified -c 8192, a slot per caller: "D2 - Option A".
   - D3, no hang rule: "D3 - Drop. We need to pass a message to the "manager', s.t. this
     would not happen in the future."
   - D4, a Unix domain socket in the session folder: "I agree. Approved."
   - D5: "Oh, this is what I was talking about in D3" (its content: the REV7 record).
   - D8, the leftovers dropped: "D8 - Drop".
2. **The derailment of this review, ledger REV7: DONE 2026-10-18.** The manager wrote his
   own mitigation first, then compared it with the advice below. The two sessions agreed
   on one merged text (gate item 12, proposed). The full record: "REV7 RECORD" below. The
   owner rules on it in the manager's session.
3. **D6 and D7** became part of that merged text. Nothing goes into the guidelines
   before the owner rules.
4. **Carried from this module.**
   - runtime: ProcessSpec gains m_removeBeforeLaunch; the supervisor removes that path
     before each launch (a stale socket file blocks the relaunch, measured).
   - runtime: whether m_env merges with the app's environment.
   - util/guarded.py: the HTTP helper returns the failure kind, not a repr; it connects to
     a Unix domain socket path.
   - config: LLAMA_SERVER_SLOTS = VISION_POOL_SIZE + 1; PLAN_TIMEOUT_NS 10 s,
     VISION_LLAMA_TIMEOUT_NS 20 s, PLAN_WARM_UP_TIMEOUT_NS 30 s, LLAMA_CACHE_RAM_MIB 512.
   - the vision review: 8 image requests at once took 10.7 s without SAM3; under SAM3 they
     may pass the 20 s timeout (unverified).
   - perf: perf_record_llama.h moves into llama_server.h; delete it at the move.
   - modules/README.md: the state row still names llama_server/brief.md; the folder is
     05-llama_server.
   - perf: how a caller reaches the one tracer (P1 in llama_server.md). The manager
     answered: he fixes perf.h, telemetry.h and perf.md; the form is the owner's ruling.

### 2026-10-18, checkpoint 10
- At the owner's order: ledger row REV7 (the facts and the reading procedure only; the
  owner's order overrides PAR1's "the agents never edit the ledger"). The causes and the
  advice moved into the sealed section below, out of the review record.

=====================================================================================
The seal is lifted (2026-10-18): the manager wrote his mitigation first, then read this.
=====================================================================================

## SEALED: the advice (the llama server agent, 2026-10-18; the seal lifted the same day)

### The causes, as the author sees them
- No reality check at accept time. The standing rule "Do not build recovery for a failure
  that does not happen" (guidelines.md) was never applied to R1-1.
- "Every finding accepted" was treated as the goal, as in the runtime record (44 of 44).
- A new mechanism went to the next round before the owner saw it. So the rounds polished
  the mechanism instead of asking whether it should exist.
- The reviewer's brief rewards found faults. A simulated failure was rated high.

### The advice
**The author side (D5 ruled the first step; the rest is open as D6).**
1. Before accepting a finding, the author names its cause class with its own evidence:
   - SEEN: our runs recorded the failure (a log, HISTORY.md, a measurement in normal use);
   - DESIGNED: our design produces it in normal operation, shown by a test or a trace;
   - FORCED: someone caused it by hand (SIGSTOP, a kill, a deleted file).
   A FORCED finding gets no mechanism. It becomes a named window in the failure matrix.
2. A fix to a fix: a finding against a mechanism added in an earlier round sends the author
   back to the first finding's cause class, before any new code.
3. Each round's answer ends with what it added: new types, fields, functions, and items
   carried to other modules. If that grows round after round, the conclusions say why.
4. "Every finding accepted" is not a goal. The conclusions count findings accepted,
   narrowed and rejected.

**The reviewer side (open as D7).**
1. Every finding names its cause class: SEEN, DESIGNED or FORCED.
2. High or medium needs SEEN or DESIGNED. A FORCED finding is low; its only change is a
   named window in the matrix.
3. Rounds 2 and 3 begin by re-checking the cause class of the finding behind every
   mechanism added since round 1. Only then do they look for faults inside it.

**Why this needs no person in the loop.** Both sides run the check inside the rounds. The
owner sees only the final state. Applied to this review, step 1 of each side stops R1-1:
its hang was FORCED (SIGSTOP).
## REV7 RECORD (2026-10-18): the llama server session's full report for the owner

### 1. The module, in short
- The job: the app's one path to llama-server, from its launch spec to each request.
- Files: docs/api-harden2/rev5/modules/05-llama_server/llama_server.md and llama_server.h.
  The header compiles (gcc -Wall -Wextra -Wpedantic -std=c11) and the layout tool ran.
- The review record: docs/api-harden2/rev5/test/llama_server-review.md (3 rounds, 28
  findings).
- The design now: one connection per request; the client reads no status row, so the
  reply is the truth; one request function with a result enum; never an exception.

### 2. The owner's rulings in this session (verbatim; to copy into the ledger)
- D1, a warm-up after every relaunch of llama-server: "D1 - Yes".
- D2, -np 9 --kv-unified -c 8192, a slot per caller (the pool of 8 plus the planner):
  "D2 - Option A". Measured: 233 MiB more VRAM; no request waits for a slot.
- D3, no hang rule: "D3 - Drop. We need to pass a message to the "manager', s.t. this
  would not happen in the future."
- D4, a Unix domain socket in the session folder, not TCP 18090: "I agree. Approved."
  llama-server supports it (common/arg.cpp:3190; measured).
- D5, a reality check before a finding is accepted: "Oh, this is what I was talking about
  in D3".
- D6 and D7 (the author-side and reviewer-side checks): the owner did not want his
  feedback inside the rounds ("I don't want to cause the reviews to be serialized &
  throttled by my human feedback"). He ordered REV7 instead.
- D8, the per-read deadline loop and the "deleted socket" row dropped: "D8 - Drop".

### 3. What went wrong (the facts)
1. My first failure matrix had a row "a timeout (a hung server)". The brief asked only
   for "a timeout".
2. Round 1's reviewer forced a hang with SIGSTOP and rated it high. No real hang was ever
   recorded.
3. I accepted it and built a timeout count, a callback and a planned restart.
4. Round 2 found three true faults inside that mechanism. I fixed each with more
   mechanism; two of the fixes changed runtime's approved contract.
5. Round 3 found that runtime's 60 s reset defeats it. I added a death at the fourth hang.
6. The owner: "This is way too fucking complicated, seemingly for no reason". He dropped
   it (D3). The same pattern produced the per-read deadline loop (dropped, D8).

### 4. How REV7 was run
- The owner ordered: the manager writes his own fix first, then reads my advice, then we
  compare. My advice sat in a sealed section of brief.md, below a STOP line.
- A mishap: my first message told the manager not to reply to my session. The owner
  corrected that: the comparison is a conversation between the two sessions. I sent a
  correction.
- The manager's disclosure: he wrote his fix before he read my advice. The same tool call
  then printed my advice. So his fix was not shaped by mine.

### 5. The manager's proposal (his five rules)
1. Every failure-matrix row names its evidence: a session log line, a measurement on this
   machine, or the owner's words. A row without evidence is "never seen" and gets the
   generic handling only.
2. A failure the reviewer forces is a test of the generic handling, never a requirement.
3. Every answer is "accepted: evidence X, change Y" or "rejected: never seen; the generic
   handling covers it: Z".
4. No review round adds a thread, a callback, a counter with a policy or a restart path.
   Each mechanism added by review is an open point for the owner.
5. The manager checks the "added by review" list before the owner reads, and stops a
   round that grew the header.
- His added cause: the template's failure matrix invites rows without evidence.

### 6. My advice (the sealed section)
- The author names a cause class per finding: SEEN, DESIGNED or FORCED. A FORCED finding
  gets no mechanism.
- A fix to a fix sends the author back to the first finding's cause.
- Each round's answer lists what it added. "Every finding accepted" is not a goal.
- The reviewer names the cause class too. High or medium needs SEEN or DESIGNED. Rounds 2
  and 3 first re-check the cause behind every mechanism added since round 1.

### 7. The comparison and the four disagreements
- Agreed from the start: evidence before acceptance; a forced failure gets no mechanism;
  a fixed answer form; no "all accepted" goal; his added cause.
- D-a, the kind of evidence against the cause. Mine: in rev5 nothing runs, so faults come
  from tracing; a SIGSTOP hang is also a measurement. He agreed, and tightened DESIGNED:
  its trigger must happen in a flight or a session, with a trace or a test from it.
- D-b, his list of mechanism types. I proposed one rule instead: a change to an approved
  module's contract is an open point. He kept both. An added thread, callback, counter
  with a policy or restart path is always an open point, since the owner has cut them
  again and again. I accepted: the cost is one reading at the end.
- D-c, a header that grows. Mine: growth with a cause is legitimate (LLAMA_CUT, the socket
  path). He agreed: the manager stops only for an item without SEEN or DESIGNED.
- D-d, the owner's words as evidence. Mine: a ruling is not evidence of a failure. He
  agreed and split it: the owner's words are SEEN only when he names the failure as seen;
  a ruling that requires a handling stands on his authority, outside the cause test.

### 8. The conclusion: the merged text, proposed as gate item 12 (for the owner to rule)
12. Need. Every failure-matrix row and every accepted finding names its cause:
  - SEEN: a session log line, a measurement in normal use, or the owner naming the failure
    as seen;
  - DESIGNED: the trigger is named as something that happens in a flight or a session,
    and a trace or a test runs from it through our design;
  - FORCED: someone made it by hand (SIGSTOP, a kill, a cut cable, a full disk).
  A ruling of the owner that requires a handling is a requirement, not evidence. It stands
  on his authority, outside this test.
  A FORCED row, or a row with no cause, gets the generic handling only: the supervisor's
  restart on exit, or a request timeout that returns false. It becomes a test of that
  handling. No mechanism is built for it.
  Answers take two forms. "Accepted: cause, evidence, change." "Rejected: cause, the
  generic handling that covers it."
  A finding against a mechanism that an earlier round added sends the author back to the
  first finding's cause, before any new code.
  Reviewer side: a finding is high or medium only for SEEN or DESIGNED. Rounds 2 and 3
  first re-check the cause behind every mechanism added since round 1.
  Conclusions: list every item that review added, each with its cause, and count findings
  accepted, narrowed and rejected. An added thread, callback, counter with a policy, or
  restart path is an open point for the owner, whatever its cause. So is a change to an
  approved module's contract. The owner reads them once, at the end.
  The manager checks that list before the owner reads. He stops the review for any item
  without SEEN or DESIGNED.
- Both sessions agree on this text. No disagreement is left.
- Nothing goes into the guidelines or modules/README.md before the owner rules.

### 9. Still to do for the manager
- Copy D1 to D5 and D8 into the ledger, verbatim.
- The items carried from this module: ProcessSpec.m_removeBeforeLaunch and the m_env merge
  (runtime); the HTTP helper's failure kind and the socket path (util/guarded.py); the
  config values; the vision timeout under SAM3 load (unverified); perf_record_llama.h
  deleted at the move.
- modules/README.md: the llama server's state row names the old folder.

### 2026-10-18, checkpoint 11: no tracer in the client
- The owner: "Why do you hold a handle to m_perf? What did we establish regarding the
  performance module?" Established in PHN1 (the phone client): a client takes no tracer;
  the caller times the call. My header broke it.
- Fixed: LlamaClient holds only m_socketPath and m_warmRow; LlamaClientCreate(socketPath);
  m_perf, m_nextReq and LlamaRequest.m_label are gone. PerfLlamaRequest stays here as the
  callers' helper; req is the caller's turn or job number. gcc clean; the layout tool ran.

### 2026-10-18, checkpoint 12: the staleness pass
- The owner: "Please double check the staleness of all documents in your module, and
  update them accordingly."
- llama_server.md: the state line; the re-warm in Instance 1; D2 cut to the question, the
  measurements and the ruling; P1 added (the perf tracer, open in the manager's session);
  the TCP-era measurements marked; the label left Data in; the command line and the argv
  count (27); gate items 2, 3, 9 and 11; three notes; the name table; the tests.
- llama_server.h: the first comment; OPEN 1 (P1) on PerfLlamaRequest; the warm-up's two
  callers. gcc clean; the layout tool ran.
- brief.md: a state note above the original brief; the manager message marked done; the
  seal lifted.
- test/llama_server-review.md: a note that its conclusions predate the PHN1 fix.
