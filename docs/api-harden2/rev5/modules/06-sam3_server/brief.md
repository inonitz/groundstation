# Brief: the SAM3 server design agent (harden2 rev5, module 6)

The owner asked for this brief on 2026-10-18 ("I want the other subagents that I'd like to run
to do their own thing, along with their respective review agents"). It is the agent's handoff
document: the brief on top, the progress log at the bottom. The agent updates the log at every
checkpoint. The manager agent reads the log and every file this agent writes.


> **UPDATE 2026-10-18 (RCD1, RCD2): perf and telemetry are folded into ONE module, the recorder.**
> Read `01-recorder/recorder.md`, `recorder.h`, `record_span.h`, `record_event.h`, `record_frame.h`,
> `record_file.h`, `frame_types.h`, `recorder_internal.h` and `recorder.html` FIRST among the finished modules. Wherever this brief says perf.h, MonotonicNs, MonotonicNow, PERF_<x>,
> perf_record_<owner>.h, telemetry.h or telemetry_record_<owner>.h, read instead: recorder.h,
> MonotonicNs, MonotonicNow, SPAN_<x>, record_<owner>.h, RecordEvent and RecordFrame.
> The contracts: RecordSpan(stage, start, end, fields, count), RecordEvent(topic, at, fields, count) with typed fields
> (record_field.h: a key REGISTERED once at your module's start by RecordKeyRegister, a type, a
> value; NEVER a JSON string on the hot path); the file's keys and line kinds: record_file.h,
> RecordFrame(channel, name, at, const FrameView*). No sample contract: a gauge is an event. No handle:
> RecorderCreate once per process, no recorder argument anywhere. The parked rule "keep the
> tracer as the first parameter" is VOID. Your helpers live in `record_<owner>.h` inside your
> module and take no recorder argument; carry the keys of the former perf_record_<owner>.h and
> telemetry_record_<owner>.h into them. General structures with one home in `00-util/`:
> `spsc_record_queue.h` (a byte ring with one producer and one consumer, written in place by reserve
> and commit, typed endpoints), `index_queue.h` (a bounded queue of slot indexes under one
> lock, safe for any threads) and `fixed_text.h` (a named fixed-size text). A type's name and
> its endpoints must say its concurrency contract; a comment is not enough (RCD9). Use them instead of writing your own; a structure two modules need goes to
> util, carried to the manager, never a second copy. The frame types `FrameSize`, `PixelFormat` and `FrameView` live in `frame_types.h`, one home.

## 1. Your job

Design the SAM3 server module of harden2 and deliver two files the owner can review in 15
minutes: `sam3_server.md` and `sam3_server.h` in this folder. The job in one sentence is in
section 3. You design from the owner's words and the architecture document. You do not transcribe
today's code into C. You do not copy the rev4 sketch; it was rejected.

## 2. Read first, in this order

1. /root/groundstation/CLAUDE.md and /root/groundstation/docs/guidelines.md (the house rules; the drone safety rules first).
2. /root/groundstation/docs/api-harden2/rev5/modules/README.md: the document order (MOD1), the open-point form (MOD2), the twelve-point
   gate (item 12 is new), the house split, the state table, the carried items.
3. /root/groundstation/docs/api-harden2/rev5/01-system-architecture.md: section 2 (the SAM3 process: a priority queue, command before refresh), section 6 (the frame buffer), section 8 (410 ms a pass alone, 630 ms with Gemma busy, 1.9 s for three concepts), section 9 (a GPU out-of-memory dies and is relaunched), section 10.
4. /root/groundstation/docs/task-active-harden2-handoff-2026-10-02.md, section 2a3: part C (the procedure),
   part D (what each review taught), part E item 6 (this module), and item 13 (the vision jobs, your one caller), part F.
5. The finished modules, as the reference for the shape and the depth, and as your contracts:
   - 04-framebuffer/framebuffer.md, framebuffer.h and framebuffer_internal.h: the block is a NAMELESS memfd the app creates and passes at launch (FB2, RUN15: ProcessSpec.m_passFds); the server opens it from the descriptor (FramebufferOpen takes the descriptor); a job HOLDS its slot across your request and you read pixels only (RVW3); the slot count is 12 (FB5); the owner edited the header himself (FB7), so take every name from it
   - 03-runtime/runtime.md, runtime.h, runtime_internal.h: the supervisor owns your process; your pure spec function returns a ProcessSpec with a ReadyProbeFn (200 ms call cap), a ProcessStopPolicy, BUDGET_SPENT_DIE, m_passFds for the memfd, m_env with additions only
   - 01-recorder (read it first, as the UPDATE above says): the spans and events you own, with their
     typed fields; MonotonicNow for every timestamp
   - 05-llama_server/llama_server.md: the other GPU process; its socket is a Unix domain socket in the session folder (LLM1 D4), a precedent for yours
   - 01-recorder, record_frame.h: RecorderCreate takes the frame size, so the size probe runs BEFORE
     the recorder and the buffer exist (the start order, carried in modules/README.md)
6. The ledger rows that bind this module, in /root/groundstation/docs/spec-harden2-cleanup.md:
   T6, R2, RVW3, RVW4, RVW5, SYS1, FB2, FB4, FB5, FB7, RUN9, RUN14, RUN15, LLM1, REV8, PRF7, MOD1, MOD2, GATE1, DOC1, PAR2. Quote the owner's words in the document's rulings section.
7. Today's code, to describe what is wrong with it, not to copy it:
   - /root/groundstation/projects/integration_harden2/sam3/model.py, loader.py, contract.py (in-process today, with a lock; T6 and R2 rule its own process)
   - /root/groundstation/projects/integration_harden2/perception2/sam3_lock.py and vision.py (the callers today)
   - /root/groundstation/bench/ (the SAM3 benches and their READMEs: the measured numbers and the nf4 weights)
   - /root/groundstation/projects/integration_harden2/config/ for every value
8. One finished review record, as the model for yours:
   /root/groundstation/docs/api-harden2/rev5/test/phone_client-review.md (its conclusions and the note on the
   owner's six reviews) and /root/groundstation/docs/api-harden2/rev5/test/runtime-round-1-reviewer.md.

## 3. The facts you start from (handoff part E, item 6, and the rulings)

- One process, launched by the supervisor from your spec: python3 -m sam3.server with the nf4 weights, the memfd descriptor and its socket path; it answers "ready" only after the load and one warm pass; up to 120 s.
- It opens the frame block from the passed descriptor and reads pixels by the slot the request names; it never writes a slot and never holds a count (RVW3: the job holds the slot).
- A priority queue inside: a command request before a refresh request. One request runs at a time on the GPU (the measured rule: threads and batching give no throughput win).
- The reply: boxes as corners with a score and a label; masks as 0-or-nonzero bytes at the frame size, at most 3; the request id echoed; a status (ok, not ready, frame gone).
- Its own SIGINT handler sets its stop event; the stop policy SIGINT, then the kill after the grace. A GPU out-of-memory dies and is relaunched by the supervisor (section 9).
- Its own perf tracer (perf-sam3-<pid>.jsonl): PERF_SAM3_PASS with req, wait and boxes; the app side times PERF_SAM3_REQUEST; the two files join by req.
- One image encoding per frame, then one detection per concept; the nested-box dedup (TR17) is the vision jobs' or yours: settle it.

## 4. What you must settle (each one lands in the document and the header)

1. The process boundary: the frame by its slot in the passed memfd; the request over a Unix domain socket in the session folder with the frame's sequence number; the message format of request and reply as code; the frame size from the block's descriptor, never from config.
2. The pure spec function: argv from config, env additions only, the descriptor in m_passFds, the probe (a status line on the socket under 200 ms), the ready timeout, the stop policy, BUDGET_SPENT_DIE, the log path.
3. The priority queue and its bound: what happens to a refresh request that waits behind commands; who drops; the job's timeout against the measured 1.9 s for three concepts.
4. The reply format in full, as code, with the masks' size and the "frame gone" case: the slot was overwritten before you read it (the sequence number no longer matches; how you detect that with the frame buffer's read-only reference).
5. The warm pass before "ready" and the relaunch: after a GPU out-of-memory the supervisor relaunches you; the vision jobs see a failed request, never a crash of the app.
6. TOCTOU (gate item 11): the slot read while the writer claims it; the socket reply after the job gave up; name every window and the mechanism that closes it.
7. The failure matrix with gate item 12: a GPU out-of-memory is SEEN (the benches); a slot overwritten mid-read is DESIGNED (the buffer's claim); anything else needs its cause before a mechanism.

## 5. The rules of the deliverable

- Only `sam3_server.md` and `sam3_server.h` in this folder, plus `sam3_server_internal.h` only if the owner must see a
  mechanism to judge the design (RUN4). No drawing. No other file (DOC1). The brief stays.
- `sam3_server.md` follows the MOD1 order in modules/README.md: the job, the picture (one text
  diagram), the usage (two pseudocode instances in the Python of the build), the open points
  (MOD2, the four-line form: the problem, now, on "no", recommended), then today, the rulings,
  the gate answers with the failure matrix, the notes, the tests.
- The gate has TWELVE items now. Item 12, "Need" (REV8, 2026-10-18): every failure-matrix row
  and every accepted finding names its cause, SEEN, DESIGNED or FORCED. A forced failure, or a
  row with no cause, gets the generic handling only and no mechanism. Read item 12 in full
  before you write the failure matrix. The owner dropped a whole hang mechanism for breaking it.
- The header reads without its comments (RUN3). Create and Destroy; handles the app owns;
  `_Atomic` types for every shared value; m_ prefixes; no implementation comments. Anonymous
  `typedef enum {`; comment blocks above enums; no commas inside enum comments; 64-bit and
  float constants as macros (`UINT64_C`), never `static const`.
- Record helpers (RCD1, RCD11): your `record_<owner>.h` interns its keys and topics once at your
  module's start and offers one function per span or event that packs typed fields; no
  recorder argument, no JSON string, never on the hot path a text of your own making.
- The supervisor OWNS every process (RUN9). A module gives a pure spec function that returns a
  ProcessSpec; it never launches, stops or restarts its process. The environment in a spec
  lists only the additions (RUN16). Descriptors to pass go in m_passFds (RUN15).
- Lay the header out with `python3 /root/groundstation/tools/style/header_layout.py <file>`.
  The tool reflows comments and realigns spacing; edit with line ranges, not exact strings.
  Compile with `gcc -fsyntax-only -Wall -x c <file>` with the folders of the modules you include
  on the include path (-I.../modules/00-util -I.../modules/01-recorder and so on).
- Prose in STE: one idea per sentence, under 20 words. Standard field terms. Banned words:
  wire, seam, load-bearing, sieve. No em-dashes. No Hebrew inside an English sentence.
- No git write of any kind. No file outside this folder and your one record file.
- The ledger (docs/spec-harden2-cleanup.md): you write a row only when the owner tells you to,
  and only under your prefix `SAM`. Never RUN, PRF, TEL, FB, LLM or PHN. A change you need in an
  approved module is an open point carried to the manager, never an edit of that module (PAR2).
- Mark every number you did not measure "unverified".

## 6. The procedure

1. Read everything in section 2. Write the full picture of the module in the system before
   any design: the threads, the processes, the queues, the rates, the sizes.
2. Design. Reason from the forces to one proposal per point in section 4. Where the owner must
   choose, write the four-line form. Where the design is clear, decide and state the reason.
3. Write `sam3_server.md` and `sam3_server.h`. Run the layout tool and gcc.
4. Run the twelve-point gate yourself. Each item gets the failure you tried and the mechanism
   that stops it, written in the document's gate section. Item 9 needs measurements (section
   7). Put the numbers and the commands in the document. Do not add scripts to the repo.
5. Three reviewer rounds with subagents, one at a time. Each round: spawn one subagent
   (general-purpose, model opus, maximum care, the web for sources). Give it the module's files,
   this brief's sections 3 and 4, gate item 12, and the three lenses of round 1 (storage and
   hardware; concurrency and real time; YAGNI and decoupling). It writes only its section into
   /root/groundstation/docs/api-harden2/rev5/test/sam3_server-review.md under
   "## Round N: reviewer". You answer under "## Round N: answer": accepted with its cause and
   the change made, or rejected with the cause and the generic handling that covers it. Rounds
   2 and 3 first re-check the cause behind every mechanism added since round 1. End the file
   with "## Conclusions": agreed, open, changed, every item the review added with its cause, and
   the counts accepted, narrowed, rejected.
6. Update the document and the header after every round. Re-run the layout tool and gcc.
7. Write the progress log below at every checkpoint. The owner reviews in your session; write
   his words into the log verbatim. Return one line to the chat when done.

## 7. The machine and the measurements

- Your measurements need the GPU. Take it before any model load:
  `/root/groundstation/tools/lock.sh wait sam3_server gpu`. Release it after:
  `/root/groundstation/tools/lock.sh release sam3_server all`. The llama agent and the recognizer agent share that lock with you.
- Measure, in your scratch folder: one pass alone (compare with 410 ms); the socket round trip for a request and a reply with three masks at 1280x720; the open of the memfd in a child and one slot read at 720p and 1080p. Record the numbers and the commands in the document.
- Other agents work at the same time on other modules. You do not edit their folders, the
  approved modules, the handoff, or modules/README.md. The manager records the owner's rulings
  there and carries your items to the approved modules.

## 8. Done when

- Both files exist, the header compiles, the layout tool ran clean, every gate item has its
  proof in the document, the review record holds three rounds and the conclusions, every open
  point is in the four-line form with an OPEN mark in the header, and the log below says so.

## Progress log (newest at the end)


### 2026-10-18, checkpoint 1: the reading is done
- Read: CLAUDE.md, guidelines.md, modules/README.md (the 12-item gate), 01-system-architecture.md
  sections 1 to 11, handoff 2a3 (C, D, E items 6 and 13, F), the recorder (md, h, internal h),
  the frame buffer (md 1 to 4b, h, internal h), runtime (h, internal h), the llama server (md,
  h), the ledger rows (T6, S2, FB2 to FB8, RUN9, RUN14 to RUN16, LLM1, REV8, PRF7, PAR2, RCD1 to
  RCD4, SYS1, RVW3 to RVW5, MOD1, MOD2, GATE1, DOC1, TR17), research-complete-sam3-assessment.md,
  today's sam3/ and perception2/ code, config/constants.py.
- The human's note (2026-10-18), verbatim: "The recorder is bound to change and its contract is
  still a little volatile. Please be wary of that when writing your code. Not only that, perf &
  telemetry are effectively redundant due to their replacement, recorder. That doesn't mean that
  the insights are invalid, though."
- Found: the ledger's R2 is the unified bench, not SAM3; the own-process rulings are T6, S2 (a, on
  the back burner) and FB4. The "at most 3 masks" of handoff E item 6 has no owner ruling; today's
  code masks up to HL_MAX (128) boxes. This becomes an open point.
- Found: recorder.h and framebuffer.h both define FrameSize, so one translation unit cannot include
  both until the fold (RCD2 carries it). The public header avoids framebuffer.h.
- Next: the measurements of brief section 7, under the GPU lock.

### 2026-10-18, checkpoint 2: the measurements and the first draft
- Measured under tools/lock.sh (numbers in sam3_server.md section 6): a pass 405 ms (1 concept),
  527 ms (3), 799 ms (7) at 720p; load 6.3 s, warm pass 1.3 s; the socket round trip with 3
  masks 0.25 ms (720p) and 0.50 ms (1080p); the memfd open and map in a child 16.9 ms and 38.4
  ms, a writable map refused; the PIL colour copy 24.7 ms at 1080p against cv2.cvtColor 0.21 ms.
- Found: today's post-process brings every hit's mask to the CPU: 1224 ms and 1816 MiB of GPU
  memory for 82 hits at 1080p. Masks for the 3 best boxes only: 2.2 ms, 43 MiB. The design takes
  its own post-process.
- Found: a phrase fans out to up to 7 concepts ("all the vehicles"), so kSam3MaxConcepts is 8.
- Written: sam3_server.h, sam3_server_internal.h (one thread, the queue, the pass steps, W1 to
  W7), sam3_server.md (the MOD1 order, OPEN 1 the mask limit, the gate's 12 items, the failure
  matrix). gcc -Wall -Wextra -std=c11 -pedantic clean on both; header_layout.py ran.
- Next: reviewer round 1.

### 2026-10-18, checkpoint 3: round 1 taken
- Round 1 (test/sam3_server-review.md): 12 findings, HIGH 2, MEDIUM 2, LOW 8; 10 accepted (one
  carried to module 4), 2 narrowed; one more found by the author (R1-13, the clamp).
- Applied to both headers and the document: the merge across the request's concepts; the
  client's bound of the concepts; one MSG_WAITALL read per part on a blocking socket; no
  upsample for no box; the probe a bare connect (STATUS and READY removed); no echoed id (the
  reply header 8 bytes); PYTHONPATH as the one env addition; W8; the corners clamped.
- Carried to the manager: FramebufferOpen closes the inherited read-write descriptor; the frame
  buffer's comment on the request id; config.PROJECT_DIR.
- gcc clean on both headers; header_layout.py ran. Next: round 2.

### 2026-10-18, checkpoint 4: round 2 taken
- Round 2: 11 findings, HIGH 1, MEDIUM 2, LOW 8; all accepted, two of them narrowings of round-1
  mechanisms (the merge: containment within one concept only; the reply: one read for the whole
  reply).
- Applied: the fixed reply layout (128 box places, masks from byte 2056) and one recvmsg; the
  server accepts into an unread set and reads only after the poll (W9); 128-byte concepts, a
  1040-byte request; the tokenizer truncates at 32 tokens (the processor does not; measured);
  OPEN 1 marked above the enum; the frame buffer's FramebufferOpen named as the one change to an
  approved contract. sam3_server.md rewritten whole. gcc clean; header_layout.py ran.
- Next: round 3, the landing check.

### 2026-10-18, checkpoint 5: round 3 taken; done
- Round 3: 9 findings, MEDIUM 1, LOW 8; all accepted. R3-1 (a command read one pass late)
  narrowed R2-3's loop: one accept per round, no pop in an accepting round (W10). The rest:
  ECONNRESET and EPIPE as SAM3_CLOSED, the reply lengths stated, die() on our bugs, the
  traces of the bounds rewritten, a uint32_t merge count, two config values and recorder.md's
  example carried.
- The review record ends with the conclusions: 32 findings, 30 accepted, 2 narrowed, 0
  rejected, 1 by the author.
- For the owner: OPEN 1 (the mask limit, recommended 3) and one change to an approved contract
  (module 4: FramebufferOpen closes the inherited descriptor).
- For the manager: the carried list in the conclusions and in sam3_server.md section 4.
- Done: sam3_server.md, sam3_server.h, sam3_server_internal.h exist; gcc -Wall -Wextra
  -std=c11 -pedantic clean on both headers; header_layout.py ran clean; every gate item has its
  proof in section 7b; the open point is in the four-line form with "OPEN 1" in the header.
- The human's note on the recorder was kept: the module uses only RecordSpan, MonotonicNow,
  RecorderCreate with no frames and RecorderFlushInDie, and its one helper sits in one section
  of the header, so a recorder change moves one section. No git write was run.
