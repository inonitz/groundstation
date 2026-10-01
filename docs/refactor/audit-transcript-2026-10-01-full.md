# Transcript audit 2026-10-01: the full item table

Every owner message of the harden2 session, split into items, each checked against the records.
The summary, the gaps and the contradictions: docs/refactor/audit-transcript-2026-10-01.md.

| section | content |
|---|---|
| Sources | the transcript, the records, the files this audit wrote |
| Classes | what each class means |
| Items | one row per item, in message order |
| Reverse check | records that contradict a later owner message |

## Sources
- Transcript: /root/.claude/projects/-root-groundstation/1d8b196b-7abe-45b9-a9d6-ddf7daef5fae.jsonl,
  read up to 2026-10-01T05:23:00Z. 157 owner messages (M1 .. M157), 2026-09-21 .. 2026-10-01.
- Records: docs/task-active-harden2-handoff-2026-10-01.md, docs/harden2-status.md,
  docs/spec-harden2-cleanup.md, docs/guidelines.md, docs/task-active-harden2-refactor-handoff.md,
  docs/HISTORY.md, CLAUDE.md, and the memory folder (memory/*.md).
- Mechanical layer (reproducible): tools/audit/transcript_coverage.py wrote
  docs/refactor/audit-transcript-2026-10-01-coverage.tsv (one row per owner sentence of 4+ words:
  EXACT, NEAR or NONE, with the best record file:line). Two runs gave the same md5.
- Judgment layer: this table. Message numbers are the script's numbers. A message holds one or
  more items; each item names its evidence (a record and line, a ledger row, or the agent's
  reply with its time). Spec line numbers are as of the audit; a few are within 2-3 lines.
- Sentence join: docs/refactor/audit-transcript-2026-10-01-judgment.tsv gives every NONE
  sentence and every NEAR sentence under 0.75 the item it belongs to. A gap item gets only the
  sentences listed by hand; the other sentences go to the item of the same message whose words
  overlap most (column assigned_by: manual or overlap).

## Classes
| class | meaning | items |
|---|---|---|
| RECORDED | its substance is in a record (the evidence names where) | 279 |
| SUPERSEDED | a later owner ruling changed it (the evidence names the later ruling) | 15 |
| ANSWERED | a question answered in the agent's next replies; nothing durable to record | 38 |
| NOISE | go-aheads, procedure, a partial re-send; no ruling | 16 |
| MISSING | not in any record: a gap | 7 |
| CONTRADICTED | a record says the opposite of a later owner message | 1 |
| total | | 356 |

## Items
| item | date | type | class | evidence (record) | the owner's words, short |
|---|---|---|---|---|---|
| M1.1 | 09-21 | instruction | RECORDED | spec "Owner rulings 2026-09-23" (try/except audit); guidelines "Errors" | review the agent; static check for try-catches, "There should be almost none" |
| M1.2 | 09-21 | instruction | SUPERSEDED | handoff-2026-10-01 s.0 (new reading order) | (pasted) read the refactor handoff, then the spec "the law"; run the suite |
| M1.3 | 09-21 | rule | RECORDED | refactor-handoff:10-15 | (pasted) adhere LITERALLY; import and run tests after EVERY file; do not substitute judgment |
| M1.4 | 09-21 | instruction | RECORDED | memory/perception2-supersedes-perception.md; refactor-handoff 4b | start at phase 3, perception -> perception2 migration |
| M1.5 | 09-21 | rule | RECORDED | CLAUDE.md "Execution Rules" | owner owns all git writes |
| M2.1 | 09-21 | question | ANSWERED | agent reply; M4-M14 thread ended in greenlight (M14) | "What is the current Control Flow here?" |
| M2.2 | 09-21 | question | SUPERSEDED | spec "Owner rulings 2026-09-23" (mvd.py -> app/) | "When was mvd supposed to be refactored?" |
| M2.3 | 09-21 | ruling | SUPERSEDED | ledger K3 (09-28 commit), RM1 (commits just before the freeze) | no git commands until cleanup+refactor done and the webcam mock works, just before field test and freeze |
| M3.1 | 09-21 | complaint | RECORDED | memory/owner-wants-short-reports.md; guidelines "Writing style" | "Your explanation is not good, too much words." |
| M3.2 | 09-21 | ruling | SUPERSEDED | spec 09-23 (mvd.py split into app/) | authorized to touch mvd.py for phase 3 |
| M4.1 | 09-22 | fact | MISSING | no record says why Gemma does not draw boxes | "We don't use Gemma to creating bounding boxes since its not designed for this task. Qwen3-VL was better at this, but not better than SAM3." |
| M4.2 | 09-22 | noise | NOISE | owner: "don't make too much of this" | fine-tuning Qwen3/Gemma, thinking out loud |
| M4.3 | 09-22 | design | RECORDED | spec:255-257; refactor-handoff:59 | SAM3 backend = detect, highlight (mask from box), count; count fire-and-forget; highlight loops until gone+timeout or Clear |
| M4.4 | 09-22 | question | ANSWERED | thread M5-M14, greenlight M14 | "Where is your issue exactly?" |
| M5.1 | 09-22 | complaint | RECORDED | CLAUDE.md "Recommendations are not decisions"; memory/recommendations-are-not-decisions.md | "I NEVER TOLD YOU THAT I ACCEPTED THIS DESIGN!" |
| M5.2 | 09-22 | design | RECORDED | spec:255-257; spec X2 (detect returns (status, hits)) | detect returns boxes + status; highlight returns masks; gate re-detects until timeout or override |
| M6.1 | 09-22 | question | RECORDED | memory/sam3-concurrency-batching-not-a-lever.md | how many parallel SAM3 requests; 8 parallel realistic? |
| M6.2 | 09-22 | design | RECORDED | spec:255-257 (dispatcher on a condition variable, max 8) | task queue, max 8 threads, no polling (condition variable) |
| M7.1 | 09-22 | instruction | RECORDED | bench/sam3-concurrency-bench; memory/sam3-concurrency-batching-not-a-lever.md | run the rig in bench/; no Gemma contention; can we batch? |
| M8.1 | 09-22 | fact | RECORDED | memory/sam3-concurrency-batching-not-a-lever.md | benchmark conclusive: no benefit |
| M8.2 | 09-22 | question | ANSWERED | M9-M14 thread | "What do we do about the algorithm in this case?" |
| M9.1 | 09-22 | fact | RECORDED | refactor-handoff:72; ledger POST (2) | contenders SAM3.1 and EOVSAM |
| M9.2 | 09-22 | ruling | RECORDED | refactor-handoff:59 (VISION_MAX_TASKS = 8, a constant) | keep 8 as a constant, change it per hardware limits |
| M9.3 | 09-22 | design | RECORDED | handoff-2026-10-01 s.9 VT6; ledger VT6 (4) | SAM3 for the gate, another model tracks, re-ground every once in a while |
| M9.4 | 09-22 | question | ANSWERED | M14 greenlight | "Does my design cause any issues besides the already addressed contention issues ...? Be honest" |
| M10.1 | 09-22 | fact | MISSING | (same as M4.1) | "We don't use Gemma for this, we stopped doing that BECAUSE it was inaccurate!" |
| M10.2 | 09-22 | question | SUPERSEDED | ledger VT5 (2) (SAM3 kept for now) | "Assume we Use SAM3.1 for everything. What then?" |
| M11.1 | 09-22 | fact | RECORDED | memory/sam3-concurrency-batching-not-a-lever.md (~2.4 fwd/s) | "~2 Requests in parallel per second ... For now, this is enough." |
| M12.1 | 09-22 | instruction | RECORDED | refactor-handoff:336 (diagrams) | draw a diagram with diagram-authoring |
| M13.1 | 09-22 | preference | MISSING | no record; RM1 walk-through is related but not this | "Diagrams are for someone else to understand the high level details, but I wanted to really understand everything" (show the task-queue interaction) |
| M13.2 | 09-22 | instruction | NOISE | conditional go-ahead; the greenlight came in M14 | "This will work for now ... I'll give you the greenlight after we reorient ourselves" |
| M14.1 | 09-22 | ruling | RECORDED | guidelines:120 (producer/consumer); spec:255 | "The basic Idea is a producer and consumer pattern. I expect this in your code." greenlight |
| M15.1 | 09-22 | noise | NOISE | pointer to M14 | "See last mesage" |
| M16.1 | 09-22 | ruling | SUPERSEDED | spec 09-23 "The recognizer parses EVERY command"; ascii_only now in app/draw.py | parse_highlight, count, ascii_only -> a utility file in perception2 |
| M16.2 | 09-22 | ruling | RECORDED | spec "llama launcher" | phase 3 answers 2-5 "Yes" (the python llama launcher) |
| M16.3 | 09-22 | ruling | SUPERSEDED | refactor-handoff:72 -> ledger POST (2), S6 (2), handoff 9h | add phase 7 after the webcam mock test: SAM3.1 + EOVSAM, both quantized |
| M17.1 | 09-22 | ruling | RECORDED | guidelines "Tests"; spec Module map | too many tests; one test file per module |
| M18.1 | 09-22 | ruling | RECORDED | spec:205-207 (request() returns (status, text)) | "don't call it ok then, call it status" |
| M18.2 | 09-22 | question | ANSWERED | M19.1 ruling follows | other way to find OOM than catching it? search the web |
| M18.3 | 09-22 | complaint | NOISE | covered by memory/owner-wants-short-reports.md | "What is the point of telling me this? rephrase" |
| M18.4 | 09-22 | question | ANSWERED | M19.4 "Yes. Good." | "What do you mean by failed frame" |
| M19.1 | 09-22 | ruling | RECORDED | spec "Module map" (GPU out of memory -> die) | "Catch the OOM and effectively crash the app, for now." |
| M19.2 | 09-22 | rule | RECORDED | guidelines "Change-impact analysis" | behaviour changed, so tests change with it |
| M19.3 | 09-22 | question | SUPERSEDED | not answered in the next reply (20:59); settled by the status-panel rulings, spec:203-209 (a failure turns its row red) | "Am I notified of the failure?" |
| M20.1 | 09-22 | question | RECORDED | memory/check-agent-work-whole-files.md; guidelines "Agents" | "Are you sure you finished steps 1-3 properly? ... config constants in their correct places? Prove it" |
| M21.1 | 09-22 | instruction | RECORDED | memory/check-agent-work-whole-files.md | double check that every refactor landed |
| M22.1 | 09-22 | ruling | RECORDED | guidelines "Tests" (one test file per module) | "thousand fucking tests ... Each module should have its own test file" |
| M22.2 | 09-22 | question | RECORDED | spec:198-202 (gemma package; prompts stay with callers); refactor-handoff:63 | "Why do we use vlm_client inside perception2 ... We never said to do this." |
| M22.3 | 09-22 | ruling | RECORDED | spec:368-370 (verbatim); guidelines "Errors" (no recovery for a failure that does not happen) | "Why would gemma go unreachable mid-session? What fucking failure case is this?" |
| M23.1 | 09-22 | ruling | RECORDED | guidelines "Tests"; spec "Module map" | 6 folders, config needs no tests -> 5 test files |
| M24.1 | 09-22 | ruling | RECORDED | spec:163-164; refactor-handoff:352 | split the mvd/session_log tests; "delete it for crying out loud" (live_mock_smoke.py) |
| M25.1 | 09-22 | ruling | RECORDED | spec:200 ("Gemma serves both ... a shared resource") | "gemma is a shared resource. Recogizer AND perception2 need it." |
| M25.2 | 09-22 | question | RECORDED | spec:205-207 (status panel replaces "[VLM unavailable]") | "Does this also mean that Gemma in general, is unavailable?" |
| M26.1 | 09-22 | ruling | RECORDED | spec:200-203 | gemma package: uniform interface, keeps Gemma alive, no task code |
| M26.2 | 09-22 | ruling | RECORDED | spec:203-204 | gemma package recovers; if not recoverable, crash with a message |
| M26.3 | 09-22 | ruling | RECORDED | spec:205-209 | status "checkbox" per system: green up, red down with state |
| M27.1 | 09-22 | ruling | RECORDED | spec:213-214 | status panel right of the chat, or below image and chat |
| M27.2 | 09-22 | ruling | RECORDED | spec:215-216 | client returns a status code, True/False, no "Gemma Down" |
| M27.3 | 09-22 | ruling | RECORDED | spec:212-213 (status data one small module; UI drawn elsewhere) | "How many fucking files ... the UI goes somewhere else" |
| M27.4 | 09-22 | ruling | RECORDED | spec:217-218 | "THE APP SHOULD START EVERYTHING!" |
| M28.1 | 09-22 | ruling | RECORDED | refactor-handoff:64, 275 | "I want a generic supervisor." |
| M29.1 | 09-22 | instruction | RECORDED | memory/check-agent-work-whole-files.md | "check that all of your intended work landed, and then CHECK AGAIN!" |
| M30.1 | 09-22 | ruling | RECORDED | spec:223-224 | ASR, keyboard hook, gstreamer started from Python |
| M30.2 | 09-22 | ruling | RECORDED | spec:225-226 | layout: camera full width; status + chat (scroll) below |
| M31.1 | 09-22 | instruction | RECORDED | refactor-handoff 4b (self-test) | self test your task checklist |
| M31.2 | 09-22 | rule | RECORDED | refactor-handoff:65 ("No unused abstractions"); guidelines YAGNI | "I don't want abstractions all over the place not being used." |
| M31.3 | 09-22 | rule | RECORDED | guidelines "Docs"; memory/record-rulings-verbatim.md | "where is it documented, is the document up-to-date regarding your tasks?" |
| M32.1 | 09-22 | rule | RECORDED | refactor-handoff:308 ("use the skills (code-review, simplify, run)") | "Claude you have skills ... Why aren't you using them wherever possible and useful?" |
| M33.1 | 09-22 | ruling | SUPERSEDED | spec:245-247 (phone TTS is the phone app; its health is the phone app's) | TTS: try to recover it like all services |
| M34.1 | 09-23 | instruction | NOISE | procedural (context dump) | 3% context left: dump context into the handoff, with next steps |
| M35.1 | 09-23 | instruction | NOISE | procedural | another check; write it down |
| M36.1 | 09-23 | instruction | NOISE | procedural | "Do One last check, Be thorough." |
| M37.1 | 09-23 | question | ANSWERED | agent status reply | "where are we!" |
| M38.1 | 09-23 | question | ANSWERED | M39.1 follows | "How many try excepts?" |
| M38.2 | 09-23 | instruction | RECORDED | spec 09-23 "API" rulings (review by headers) | owner reviews every touched system himself |
| M38.3 | 09-23 | ruling | RECORDED | spec:251-252 | if mvd.py is too big, an app/ or main/ folder |
| M38.4 | 09-23 | question | RECORDED | spec:258 (benches in HISTORY); spec:466-478 (rule A-D) | which benches are dead? committed? documented on a linear timeline? |
| M39.1 | 09-23 | ruling | RECORDED | spec:232-233 | too many try/excepts; each must be proven unavoidable |
| M39.2 | 09-23 | ruling | RECORDED | spec:234; guidelines "Errors" | no raise SystemExit; use die() |
| M39.3 | 09-23 | ruling | SUPERSEDED | spec:235-237 -> ledger D, K3, RM1 | commit in stages with a BUILD BROKEN warning |
| M39.4 | 09-23 | ruling | RECORDED | spec:238; docs/api-harden2 | "A PROPER INTERFACE FOR EVERY GOD DAMN THING ... DRAFT A C HEADER" |
| M39.5 | 09-23 | ruling | RECORDED | spec:241-244; guidelines banned words | one transmit switch; "wire" banned |
| M39.6 | 09-23 | ruling | SUPERSEDED | spec:245-247 (TTS is the phone app) | TTS is a system, restart it by the supervisor |
| M39.7 | 09-23 | question | RECORDED | spec:248-249 (drone link: WAITING, never dies) | "Can we recover the drone link?" |
| M39.8 | 09-23 | ruling | RECORDED | spec:250-251 | files small, one job each, KISS |
| M39.9 | 09-23 | ruling | RECORDED | spec:252-253 | display loop: measure first; camera redraws, chat on text, status monitored |
| M39.10 | 09-23 | ruling | RECORDED | spec:254 + 265-266 | benches documented in HISTORY in the right format |
| M39.11 | 09-23 | ruling | SUPERSEDED | spec:255 -> ledger Q5 a, 3.2.3 (the preflight is the one place) | a file to test for dependencies |
| M39.12 | 09-23 | question | ANSWERED | agent reply 2026-09-23T13:33 (task design) | "Explain to me why you were so opposed to this, and instead opted for a SPSC pattern" |
| M40.1 | 09-23 | ruling | RECORDED | spec:262-263 | API v1 undersells the system |
| M40.2 | 09-23 | ruling | RECORDED | spec:264-265 | no DroneLink; one module for every DJI app service (like llm_to_action) |
| M40.3 | 09-23 | ruling | RECORDED | spec:245-247 | "CAN YOU EVEN FUCKING KNOW IF THE TTS DIES ON THE PHONE???" |
| M40.4 | 09-23 | ruling | RECORDED | spec:266-267; guidelines "Docs" | document ALL useful information in HISTORY, the WHY |
| M40.5 | 09-23 | ruling | RECORDED | spec:268-269 (corrected by M41 to "keep raising them") | "nothing burger ... issues like these ... should not exist" |
| M40.6 | 09-23 | ruling | RECORDED | spec:270 | task design chosen because easier to reason about, not speed |
| M40.7 | 09-23 | question | ANSWERED | agent reply 2026-09-23T13:33 (rt_mutex, Zephyr links) | "find me resources in C/C++ [on priority locks]" |
| M40.8 | 09-23 | question | ANSWERED | agent reply 2026-09-23T13:33 (rclpy executor.shutdown) | "Why does ROS need to catch its shutdown exception?" |
| M40.9 | 09-23 | ruling | RECORDED | spec:271-272 (self-tests move into test files) | "What do you mean by if _smoke(): die() ... LOOKS LIKE CODE YOU WRITE IN A TEST" |
| M41.1 | 09-23 | remark | NOISE | API v2 approved (spec:309-311); the remark changed nothing | "Still DJI App Centric, but for now this is fine." |
| M41.2 | 09-23 | question | RECORDED | spec:274 + "Module map" (crash / restart / wait per system) | which systems crash the app, restart themselves, or wait for the user |
| M41.3 | 09-23 | question | ANSWERED | agent reply 13:44 ("Am I finished? No ...") | "Can I assume you're finished?" |
| M41.4 | 09-23 | ruling | RECORDED | spec:268-269 | "No no, keep raising them. This is an issue of code quality" |
| M41.5 | 09-23 | ruling | RECORDED | spec:270-272 | test_<system>.py for every system; a passing suite must predict a working app |
| M42.1 | 09-23 | complaint | RECORDED | guidelines "No task IDs to describe work"; memory/no-task-id-jargon.md | "DONT MENTION R*BLAH* TO R*BLAH*, MENTION THE WORK DONE!" |
| M42.2 | 09-23 | ruling | RECORDED | spec:278 (no "System" abstraction); spec:280-281 (test per module) | each package is a module; is there a "System" abstraction?; no test for app/ |
| M43.1 | 09-23 | ruling | RECORDED | spec:275-281 (module map) | the systems list, gemma, config, test per MODULE |
| M43.2 | 09-23 | ruling | RECORDED | spec:282-283 | test_app.py: headless, 3 questions, manual mode, revert, check a recovery |
| M44.1 | 09-23 | question | RECORDED | spec:357-360, 366-370 (9a-1 closed) | "What about the TTS from the Laptop?" |
| M44.2 | 09-23 | question | RECORDED | spec:298-299 | "Define a SAM3 failure." |
| M44.3 | 09-23 | question | RECORDED | spec:300-301 | "Logging => Why should the logging fail?" |
| M44.4 | 09-23 | ruling | RECORDED | spec:284-288 | UI in its own file in app/; the phone API decoupled with its own status; name log/ |
| M44.5 | 09-23 | ruling | RECORDED | spec:289-292 | test_app sends ASR over the ROS2 topic and M over the keyboard node |
| M45.1 | 09-23 | ruling | RECORDED | spec:296 | "Why move the PTT keys inside Audio? IT STAYS IN CONFIG!" |
| M46.1 | 09-23 | ruling | RECORDED | spec:298-301 | SAM3: die on OOM for now; logging: check the session folder at start, crash if not writable |
| M46.2 | 09-23 | ruling | RECORDED | spec:302 | dji_app its own module: "Unfortunately I have to agree with you" |
| M46.3 | 09-23 | question | RECORDED | spec:304-308 (safety gap, fixed with F4) | "Why are we not subbed to the /keyboard/in/raw? ... how did we never notice this?" |
| M47.1 | 09-23 | instruction | RECORDED | refactor-handoff s.9 (plan agreed 2026-09-23) | repeat the full plan before we begin |
| M48.1 | 09-23 | ruling | SUPERSEDED | spec:352-355 (util/ agreed); guidelines (shared helper in util/) | "All helpers should exist where fatal.py exist." |
| M48.2 | 09-23 | ruling | MISSING | refactor-handoff:410 says "propose a name at step 3"; no proposal or ruling found; runtime/fatal.py unchanged | "maybe rename it" (fatal.py) |
| M48.3 | 09-23 | ruling | SUPERSEDED | spec:466-478 (rule A-D, 2026-09-26) | "If they are documented and commited then they are not relevant anymore." (benches) |
| M48.4 | 09-23 | rule | RECORDED | refactor-handoff s.9 ("2 passes" per step); guidelines "suite twice" | write the list into a file; check every step in 2 passes, in our style |
| M49.1 | 09-23 | ruling | RECORDED | spec:309-311 (WAITING is orange) | "Then make it orange" |
| M49.2 | 09-23 | question | RECORDED | spec:312-316 | "what does the pipeline look like now from start to finish?"; recognizer does too much |
| M50.1 | 09-23 | ruling | RECORDED | spec:312-316 | recognizer parses everything incl. the fast path; critical commands go straight to control |
| M51.1 | 09-23 | question | ANSWERED | M52-M53 ("Yes, you may continue") | "I don't understand what your proposal fixes." |
| M52.1 | 09-23 | ruling | RECORDED | spec:317-321 | who uses the comms interface: control; both paths end in control |
| M53.1 | 09-23 | instruction | NOISE | go-ahead | "Yes, you may continue" |
| M54.1 | 09-23 | question | ANSWERED | agent reply 16:59 (Pylance 3.7 GiB) | "something that is consuming ~4GiB of memory ... Check that you actually closed everything" |
| M55.1 | 09-23 | question | ANSWERED | agent reply 17:03 | "What is currently fucking one of my cpu cores constantly?" |
| M56.1 | 09-23 | question | RECORDED | guidelines "Terms" (9a-7 closed); ledger C.8 | "what is the single interface that every Module exposes?" |
| M56.2 | 09-23 | ruling | RECORDED | guidelines "Code style" (lines under 90) | "140 older lines are over 100 chars ... make them less than 90" |
| M56.3 | 09-23 | rule | RECORDED | memory/check-agent-work-whole-files.md | validate against the doc checklists AND the conversation's checklist |
| M57.1 | 09-23 | complaint | RECORDED | memory/ask-before-spawning-agents.md; guidelines "Agents" | "Why did you spawn 6 other fucking agents? ... Did I give you permission?" |
| M58.1 | 09-23 | question | RECORDED | spec:327-329 (9a-7 reframed); guidelines "Terms" | "What interface does each module expose for the various Systems to use?" |
| M58.2 | 09-23 | complaint | RECORDED | spec:323-325 | "Your code looks too fucking dense." |
| M58.3 | 09-23 | question | RECORDED | refactor-handoff:435, 477 (LlamaServer deleted, one start mechanism) | "9a-3: Why is LlamaServer (where is it?) the bench launcher?" |
| M58.4 | 09-23 | rule | RECORDED | spec:326 | "you ARE documenting, right claude? EVERYTHING!" |
| M59.1 | 09-23 | question | RECORDED | refactor-handoff:453-454 (9a-10 closed) | "Why does recognizer use the dji_app?" |
| M59.2 | 09-23 | complaint | SUPERSEDED | refactor-handoff:482 (no ruling found) -> spec:336-341 (one speech-in interface) | "We already abolished Ears. Why did you bring it back?" |
| M59.3 | 09-23 | ruling | RECORDED | spec:345-351 (lifecycle); guidelines "Architecture" | 9a-9: "WHAT THE FUCK ARE CONSTRUCTORS FOR???" no "internals by hand" |
| M59.4 | 09-23 | ruling | RECORDED | spec:352-355; guidelines "Architecture" (shared helper in util/) | "WHY ARE UTILITIES NOT MOVED TO A UTIL FOLDER?" |
| M59.5 | 09-23 | ruling | RECORDED | refactor-handoff:511 (regrouped by intent) | "They should be grouped logically, by intent." |
| M59.6 | 09-23 | ruling | RECORDED | spec:366-370 | "9a-1: Why would the laptop speak output fail?" |
| M59.7 | 09-23 | ruling | RECORDED | refactor-handoff:477 (LlamaServer deleted; one launcher) | "9a-3 ... DECIDE WHICH ONE LAUNCHES IT AND HOW!" |
| M60.1 | 09-23 | ruling | RECORDED | spec:333-335 (http.HTTPStatus) | "ITS A FUCKING HTTP CODE!!! SURELY THERE IS AN OBJECT FOR THIS" |
| M60.2 | 09-23 | ruling | RECORDED | spec:336-341 | speech in: one audio interface receives the backend(s) |
| M60.3 | 09-23 | ruling | RECORDED | spec:343-344 | class shape: constructor, destructor, internal methods, static, a user |
| M60.4 | 09-23 | ruling | RECORDED | spec:345-350; guidelines "Architecture" | init every service; give modules their services; crash and say why; close modules then services |
| M61.1 | 09-23 | ruling | RECORDED | spec:336-339 | speech in: a configurable list of sources; a remote ASR source must not take away ground control |
| M62.1 | 09-23 | ruling | RECORDED | spec:339-341 | speech out follows the same rule (a list of outputs) |
| M63.1 | 09-23 | question | ANSWERED | M64 "Now I understand your point. I fully agree." | "The supervisor's processes depend on the settings: <<<< Why?" |
| M63.2 | 09-23 | ruling | RECORDED | spec:352-355 | Keys its own module; "Control is the Way we interact with the autonomous system, ONLY" |
| M63.3 | 09-23 | ruling | RECORDED | spec:356-358, 342 | video gets a process handle, not the supervisor; one video option |
| M63.4 | 09-23 | question | RECORDED | spec:359 (the UI reads the status board) | "What does board mean inside the UI?" |
| M64.1 | 09-23 | question | ANSWERED | M65 ("I had a brainfart"; "Your proposal is correct") | "What do you mean by The mock: only when control is mock" |
| M65.1 | 09-23 | ruling | RECORDED | spec:352-355 ("More may move to util/ later") | util/ agreed; "I'd like more functions to migrate to util/* but this is good enough now" |
| M65.2 | 09-23 | ruling | RECORDED | spec:361-366; guidelines "Code style" (Vision._track is the reference) | the owner's own rewrite of _track |
| M65.3 | 09-23 | rule | RECORDED | spec:366-370; guidelines "Working with the owner" (quote verbatim) | "I'm still waiting for you to quote my response to 9a-1 ... You may not begin until You've quoted me." |
| M66.1 | 09-23 | rule | RECORDED | handoff-2026-10-01 s.0; guidelines "All guidelines at a glance" | check your work after; "peek at my previous general instructions before starting a big batch of work" |
| M67.1 | 09-24 | instruction | NOISE | procedural (context dump before compaction) | save ALL session history to a file before compaction |
| M68.1 | 09-24 | rule | RECORDED | handoff-2026-10-01 s.2 item 17 (offload state to files) | "Anything you belive won't survive fully intact post-compaction SHOULD be moved to your log file." |
| M69.1 | 09-24 | noise | NOISE | procedural | "Make the most out of your 6% of context left." |
| M70.1 | 09-24 | question | NOISE | procedural | anything else not written into a file yet? |
| M71.1 | 09-24 | rule | RECORDED | same as M66.1 | "Check your work after you finish ... peek at my previous general instructions" |
| M72.1 | 09-24 | ruling | RECORDED | guidelines "Agents"; memory/check-agent-work-whole-files.md | 2 more Opus 5.5 subagents on medium; check their work against the docs and the session history |
| M73.1 | 09-24 | rule | RECORDED | spec:389-393 | "check The agents' work again. Don't insist that you're done" |
| M73.2 | 09-24 | question | RECORDED | spec:394-396, 407-412 | "What is the meaning of this? and 5 ... whats the context here?" (the vav-number case) |
| M73.3 | 09-24 | ruling | RECORDED | spec:378-379 | "Well HOW ABOUT YOU UPDATE THEM CLAUDE??? NOW???" (stale docstrings) |
| M73.4 | 09-24 | ruling | RECORDED | spec:380-386 | "Why does a supervisor take a BOARD???" |
| M73.5 | 09-24 | complaint | RECORDED | refactor-handoff:511 (9a-12, files regrouped); spec:386-388 (try count 5) | not all files follow the style; still see try excepts; "ARE YOU ACTUALLY GOING ONE BY ONE???" |
| M74.1 | 09-24 | ruling | RECORDED | spec:413-417 | pipeline.py "look like shit"; recognizer.py 800 lines |
| M74.2 | 09-24 | ruling | RECORDED | spec:418-422 | utilities used in EVERY module |
| M74.3 | 09-24 | question | RECORDED | spec:423-427 | "Are the connections correct, as we planned" |
| M74.4 | 09-24 | ruling | RECORDED | spec:407-412 | the vav-number case "mostly a non-issue ... If your patch should fix it ... do it" |
| M74.5 | 09-24 | ruling | RECORDED | spec:399-406 | each service reports its own status; the StatusBoard iterates |
| M74.6 | 09-24 | instruction | RECORDED | guidelines "Tools" (tools/audit_exceptions.py) | "HOW MANY TRY CATCHES ... USE THE SCRIPT YOU MADE" |
| M74.7 | 09-24 | question | RECORDED | spec:428-433 | "Why does trace.py record twice to logs/traces/?" |
| M75.1 | 09-24 | ruling | RECORDED | spec:431-433 | "Yes, delete trace.py" |
| M75.2 | 09-24 | question | ANSWERED | agent reply 2026-09-24T02:07 (steps 8-13 left) | "are you done with the steps? What do we have left ... can we commit and finally test the app?" |
| M76.1 | 09-25 | fact | RECORDED | HISTORY 2026-09-25 "Gemma died on every image question" (SIGBUS, ggml mix) | "Everything is slow as a fuck ... gemma keeps restarting with code -7?" |
| M77.1 | 09-25 | instruction | RECORDED | HISTORY 2026-09-25 (Gemma SIGBUS, ggml mix) | "I just closed the app. Look at whats up." |
| M78.1 | 09-25 | fact | RECORDED | HISTORY:3760-3772 | "The app never crashed due to VRAM issue up until now." |
| M79.1 | 09-25 | ruling | RECORDED | spec:434-439; guidelines "Architecture" (NATIVE_BIN_DIR) | "Only use the binaries from release/shared/dji, not from anywhere else." |
| M79.2 | 09-25 | ruling | RECORDED | spec:441-444 (perf approved) | measure the slowness on the next run; a flag to test every system |
| M79.3 | 09-25 | ruling | RECORDED | spec:440 | no CMake install change now |
| M79.4 | 09-25 | question | ANSWERED | agent reply 2026-09-25T01:01 ("Your side: ...") | "Anything else I need to do on my side?" |
| M80.1 | 09-25 | rule | RECORDED | guidelines "Docs" (newest last); memory/docs-newest-last.md | "THE MOST UP TO DATE NOTES SHOULD BE THE LAST NOTES" |
| M81.1 | 09-25 | ruling | RECORDED | spec:441-444 | "ASR Time should be measured when we use ASR." plan approved |
| M81.2 | 09-25 | ruling | RECORDED | spec:445 | the preflight must be fast (no 5-10 s pause after the SAM3 line) |
| M82.1 | 09-25 | question | ANSWERED | agent reply 2026-09-25T01:31 (chat-pane line-break bug, fixed) | "the app crashed. Did you close anything?" |
| M83.1 | 09-25 | fact | RECORDED | HISTORY:3797-3810 | (pasted) the first run.sh perf report |
| M84.1 | 09-25 | noise | NOISE | correction of an agent claim | "No its not running, what are you on about?" |
| M85.1 | 09-25 | rule | RECORDED | guidelines "Docs" (measurements AND verdicts) | "All the measurements should be added to history, including the verdicts" |
| M85.2 | 09-25 | question | RECORDED | HISTORY:3813-3814 (C920 ceiling 1080p30) | "the camera is able to do 1080p 60fps ... Please check." |
| M86.1 | 09-25 | question | ANSWERED | agent reply 2026-09-25T18:32 (status in handoff 9c) | "Is the status that you gave me updated anywhere?" |
| M86.2 | 09-25 | fact | RECORDED | spec "Objective" (code reads cleanly for any reviewer) | harden2 grew because "I want ... our systems ... legible for future development and refactoring" |
| M86.3 | 09-25 | instruction | RECORDED | guidelines "Agents" (triple coverage); HISTORY speedrun entries | document everything, git commands, speedrun the local task list with subagents, triple check |
| M86.4 | 09-25 | question | RECORDED | guidelines "All guidelines at a glance" (2026-09-25) | "what exactly are our guidelines currently ... in full detail?" |
| M87.1 | 09-25 | question | ANSWERED | refactor-handoff 9c/9d (F1 runs last over the finished state) | "How do you suppose Step 12 would happen if the docs are not fully updated" |
| M87.2 | 09-25 | rule | RECORDED | guidelines "Agents" (validate against the brief); memory/check-agent-work-whole-files.md:13 | validate an agent's work against the brief you gave it; reading its files is part of that |
| M87.3 | 09-25 | question | RECORDED | guidelines "All guidelines at a glance" | "Are all of these guidelines DOCUMENTED? ... Where does each guideline here come from?" |
| M88.1 | 09-25 | instruction | RECORDED | guidelines (merged 2026-09-25) | "Document all of the guidelines please." |
| M89.1 | 09-26 | noise | NOISE | go-ahead | "You may continue!" |
| M90.1 | 09-26 | question | ANSWERED | agent reply 09-26 (xkbcomp for xdotool); then ledger 0.1 | "What the hell are you doing with the xkbcomp? ... What does it need it for?" |
| M91.1 | 09-26 | question | ANSWERED | agent reply 09-26 (xkbcomp for xdotool), then ledger 0.1 | "Give me a full explanation Claude. What does it need it for?" |
| M92.1 | 09-26 | ruling | RECORDED | ledger 0.1 | "why reinvent the wheel ... SEND A KEYPRESS OVER ROS2" |
| M93.1 | 09-26 | fact | RECORDED | ledger C2 (keyboard_node.hpp Q, C, M bound, committed 9fc6c67) | "I already recompiled ... Q/C/M Transmit in the ROS2 network" |
| M94.1 | 09-26 | ruling | RECORDED | spec:447-456 | move Q and the other keys to function keys (typing in the background) |
| M95.1 | 09-26 | rule | RECORDED | handoff-2026-10-01 s.2 item 2 (full context per item) | "Give me a full debrief on all tasks, don't just hand-wave something I have to do." |
| M96.1 | 09-26 | ruling | RECORDED | ledger 1.1-1.5 | run_all.sh readable; bench docs for the agent; test it fully; rule A-D; the sed |
| M96.2 | 09-26 | question | RECORDED | ledger 1.7 + D3 (route() / handle()) | "Measure, and tell me how it happened this way. Is this a door to any issues in the future?" |
| M96.3 | 09-26 | question | RECORDED | guidelines "Terms"; ledger 1.8 | "Did we document what is a service, System or Module? If so, where?" |
| M96.4 | 09-26 | question | RECORDED | ledger D1 (whole-system bench retired) | "What is the point of the performance logs we do to our app given a flag?" |
| M96.5 | 09-26 | ruling | RECORDED | ledger 2.1-2.4, D5, D6 | two mains in app/; disk.py exposes internals; session.py looks good |
| M96.6 | 09-26 | ruling | RECORDED | ledger 3.1, D7, D13; spec:481-482 | deps check speed; why 3 new tests; phonikud; the TTS flag phone/laptop/both/off |
| M96.7 | 09-26 | ruling | RECORDED | ledger D9/Q9; ledger 4.2 (docs/spec-harden2-run-arguments.md) | "test_the_whole_app_over_ros"?; document all runs, how to run, measure, the flags |
| M96.8 | 09-26 | ruling | RECORDED | ledger 5, 6.2, B.1 | keybindings good; double check config; headers synced with the python |
| M96.9 | 09-26 | question | RECORDED | ledger C.1-C.12 | part C points (dips, vav word, verbose hook log, 9a-7, ticks, ste_check) |
| M96.10 | 09-26 | ruling | RECORDED | ledger D; spec:572-574 | "I'll not commit this ... We'll finish them and commit." |
| M96.11 | 09-26 | rule | RECORDED | guidelines "Working with the owner" (decision table, every point) | "Address EVERY SINGLE POINT ... Make it easy for me to respond to you in a list" |
| M97.1 | 09-27 | ruling | RECORDED | ledger 1.2-1.5, D1, D2 | 1.2 "Question D1 it is"; 1.4 what are we testing; 1.5 produce the documents, D2 |
| M97.2 | 09-27 | ruling | RECORDED | ledger 1.8 (decide/act); guidelines "Terms" (verbatim) | "separate functions that are chained together"; module/service/system definitions |
| M97.3 | 09-27 | question | RECORDED | ledger 1.10, Q3 (pynvml); ledger D4/D5/Q4 (scripted run) | "What is the overhead of measuring the performance here? define scripted run exactly?" |
| M97.4 | 09-27 | ruling | RECORDED | ledger 2.1, D5, Q4 | "If it for testing, shouldn't it be inside test/*?" |
| M97.5 | 09-27 | question | ANSWERED | agent reply 09-27 (files checked); ledger 2.2 | "Tell me which files you've checked." |
| M97.6 | 09-27 | ruling | RECORDED | ledger D13, Q6 | load phonikud only when TTS_OUTPUTS has laptop |
| M97.7 | 09-27 | complaint | RECORDED | ledger 4.1; test/README.md | "you should've told me this from the start ... Give me the list of all tests" |
| M97.8 | 09-27 | ruling | RECORDED | ledger 5, C.1, C.2, C.8, C.9 | window keys to config; "Why does it only hold the mean"; C.2; "Yes, close it" |
| M97.9 | 09-27 | rule | RECORDED | guidelines:439-440 | "Don't use hebrew and english in the same sentence." |
| M97.10 | 09-27 | fact | RECORDED | spec:579-583; ledger C.4 | keyboard hook reads the mouse because the laptop keyboard's driver reports mouse events |
| M97.11 | 09-27 | rule | RECORDED | guidelines:442 | "I don't have context in my brain for every single here" |
| M97.12 | 09-27 | ruling | RECORDED | ledger D1-D7 | D1 "I tend to agree with option A"; D2 A; D3; D4 A; "DOES THE PREFLIGHT ACTUALLY DO THAT JOB?" |
| M97.13 | 09-27 | question | ANSWERED | ledger D1 (run_list merged, U2) | "Explain the reason for keeping run_list.py." |
| M98.1 | 09-27 | ruling | RECORDED | spec:578; ledger R1/M2 (accuracy.py) | "rename it - This is literally just a benchmark of the recognizer as a function of the backend" |
| M98.2 | 09-27 | ruling | RECORDED | ledger 1.7 | "The guards are a part of the recognizer, so they should be TESTED!" |
| M98.3 | 09-27 | ruling | RECORDED | ledger 1.8.1 | "we encompass a whole module inside a folder. Does that rule not hold ...?" |
| M98.4 | 09-27 | ruling | RECORDED | ledger 1.10, Q3 | "IT COSTS THAT MUCH FOR JUST MEASURING TIME?" |
| M98.5 | 09-27 | ruling | RECORDED | ledger 2.1, Q4 | feed.py renamed and moved to test/ |
| M98.6 | 09-27 | ruling | RECORDED | ledger 3.2.3, M3 | "This should not be part of main ... Don't increase the loading time of main.py, we were supposed to hit <1s e2e" |
| M98.7 | 09-27 | complaint | RECORDED | ledger 3.3 (measured 14-18.5 s) | "WHO TAKES MORE THAN 30 SECONDS?" |
| M98.8 | 09-27 | complaint | RECORDED | ledger 4.1, R6 | "do you seriously expect me to read through the whole of your 217 test names?" |
| M98.9 | 09-27 | ruling | RECORDED | ledger C.1 | "Record everything and calculate metrics later! Keep P25, P50, P75, P95, P99, min & max." |
| M98.10 | 09-27 | ruling | RECORDED | ledger C.3, Q8 | "we should just convert the vav to and"; how to catch the connection letters |
| M98.11 | 09-27 | ruling | RECORDED | ledger D1, D5-D15 | D1 A; D5 A; D6 A; D8 A; D12 give commit; D13; D14; D15 |
| M98.12 | 09-27 | rule | RECORDED | ledger Z2, M4 (ironing rounds closed before building) | "you won't do anything until we've ironed out ALL of these issues" |
| M99.1 | 09-27 | ruling | RECORDED | ledger Q1 | "Q1 it is." |
| M100.1 | 09-27 | ruling | RECORDED | ledger 1.8.1, R3, R4, R5 | SAM3 own folder; keyboard to its own folder; log readers?; system/ is not the right word |
| M100.2 | 09-27 | ruling | RECORDED | ledger 1.8.2 | "I agree with everything said here." |
| M100.3 | 09-27 | rule | RECORDED | guidelines "Working with the owner" (measure in the same turn); ledger 3.3 | "Well fucking measure it? You already do things between turns" |
| M100.4 | 09-27 | ruling | RECORDED | ledger Q7, R6 | coverage: use it to learn its value; "Line Coverage Is a stupid metric" |
| M100.5 | 09-27 | ruling | RECORDED | ledger C.1, R7 (buffer, flush every 5 s, die() flushes) | buffer deferred to disk; how much is lost on a crash; buffer size at 5 s |
| M100.6 | 09-27 | ruling | RECORDED | ledger C.3, R8 | fractions: what about the Hebrew words for "and a quarter" and "and an eighth"? "I can go on & on." |
| M100.7 | 09-27 | ruling | RECORDED | ledger D15 (one function builds the services) | "the app should simply call a single function that builds all the services"; "Why do we need to Build specific services?" |
| M100.8 | 09-27 | question | RECORDED | ledger R9 (SAM3 lives in the app; perception uses it) | "is SAM3 only used by the perception system?" |
| M100.9 | 09-27 | ruling | RECORDED | ledger Q1-Q9 | Q1 B; Q3 A; Q4 name; Q5 A; Q6 YES; Q7 YES; Q8 ALL SEVEN; Q9 A |
| M101.1 | 09-27 | ruling | RECORDED | spec:531; ledger 3.3 | "Everything ... be loaded eagerly - I don't want load times to slip into the app runtime." |
| M101.2 | 09-27 | ruling | RECORDED | ledger C.1, C.3, D15 | C.1 draft the perf module; C.3 good; D15 "You win." |
| M101.3 | 09-27 | ruling | RECORDED | ledger R1-R5, R7 | R1 not a good name; R2 do we need unified_bench; R3 a; R4 file sizes; R5 agreed; R7 config, 5 s |
| M101.4 | 09-27 | ruling | RECORDED | ledger R6, U4 | "I agree with everything besides mutation checks ... fuzzing ... not for now" |
| M101.5 | 09-27 | question | RECORDED | ledger R8 | "is gemma not good enough to understand these, or do we just not have good enough solutions to verify ...?" |
| M101.6 | 09-27 | rule | RECORDED | guidelines:445-446 (never a yes-or-no frame) | "R10 - ... this is not a yes or no question. Don't belittle this point" |
| M102.1 | 09-27 | ruling | RECORDED | ledger C.1 approved, D15, R4, R8, R9 | "Draft Looks Great!"; D15 agree; R4 for now; R8 agree; R9 agreed |
| M102.2 | 09-27 | rule | MISSING | ledger R6 holds only "besides mutation checks"; no rule says a test that passes without checking is to be fixed | "The fact that a test can pass without checking anything just tells me that same test is not good." |
| M102.3 | 09-27 | ruling | RECORDED | ledger T6, R10, T7, U6 | "Surely there is a way that we don't have to send 2.7MiB Per request"; assess SAM3; phone app fine, 2 s |
| M103.1 | 09-28 | ruling | RECORDED | ledger U1, U2, U4-U7 | U2 "Yes, Merge" + a file option; where are the ~500 sentences and their expected values; U4-U7 |
| M104.1 | 09-28 | ruling | RECORDED | ledger U2.2, U2.3, V1-V3 | two input paths A/B; one scorer, not in log/; "Why does a scripted run need to benchmark?" |
| M105.1 | 09-28 | ruling | RECORDED | ledger V3 | "V3: I was talking about my response at the start of the message." |
| M106.1 | 09-28 | ruling | RECORDED | ledger U2.2, U2.3 | "A recorded session should have an expected value"; "We never needed to benchmark a live session" |
| M106.2 | 09-28 | ruling | RECORDED | ledger V2 -> X1-X3, Y1 | "WE LITERALLY ALREADY CREATED A TOOL TO CREATE DATASETS FOR BBOXES" (vision-verify-bench) |
| M107.1 | 09-28 | question | ANSWERED | agent reply 2026-09-28T01:43 (tools/session-replayer and log/show.py stay) | "WHAT DO YOU MEAN THE WHOLE-SYSTEM REPLAY OF OLD SESSIONS GOES WITH THEM???" |
| M107.2 | 09-28 | ruling | RECORDED | ledger X2 ("ONLY THE VISION") | measure the vision system only; the script was never updated for a week |
| M108.1 | 09-28 | ruling | RECORDED | ledger Z1, X1-X3, Y1, Y2 | recordings need their JSON; X3 each benchmark its own scorer; Y2 b |
| M109.1 | 09-28 | ruling | RECORDED | ledger Z1, Z2; spec:567 (audit 2026-09-28) | Z1 a; "Do a pass over our whole conversation history" |
| M110.1 | 09-28 | ruling | RECORDED | ledger M1-M7; spec:558-566 | M1 check it; M2 yes; M3 ROADMAP; M4; M5 not phase 2; M6 fuck it for now; M7 ok |
| M111.1 | 09-28 | instruction | RECORDED | refactor-handoff 9d | the local full task list so the owner can divide the work |
| M112.1 | 09-28 | rule | RECORDED | guidelines:432-434; memory/record-rulings-verbatim.md | "YOU SHOULD WRITE TO YOUR FUCKING DOUCMENTS!!! THAT WAY YOU WONT LOSE ANYTHING!" |
| M113.1 | 09-28 | complaint | RECORDED | spec "Decision ledger"; spec:567 "Rulings recovered by the audit" | "DONT TELL ME THAT YOU LOST SOME OF THESE DECISIONS!" |
| M114.1 | 09-28 | question | RECORDED | ledger P3; HISTORY 2026-09-28 "the handoff documents, oldest to newest" | the full list of decisions; what about the other handoff docs? |
| M115.1 | 09-28 | question | RECORDED | ledger P3 | "what is the order? from oldest to newest, and how relevant is each one? ... in HISTORY.md?" |
| M115.2 | 09-28 | ruling | RECORDED | ledger P1, P2; refactor-handoff 9e | P1 a; 4 Opus 5.5 agents on medium; the LOCK.md protocol |
| M115.3 | 09-28 | instruction | RECORDED | spec:840 | "do not start yet, we're not done ... thoroughly prepare for that" |
| M116.1 | 09-28 | ruling | RECORDED | ledger L1-L4; refactor-handoff 9e | L1-L4; each agent's doc docs/refactor/<id>_doc.md; triple coverage |
| M117.1 | 09-28 | instruction | NOISE | procedural | a final checkup of docs and plan |
| M118.1 | 09-28 | ruling | RECORDED | ledger G1 | "tell me what is the purpose of each file ... can be safely ignored" |
| M119.1 | 09-28 | ruling | RECORDED | ledger G2 | "Option A!" |
| M120.1 | 09-28 | question | ANSWERED | agent reply (the plan) | "before you begin! What are you going to do!" |
| M121.1 | 09-28 | ruling | RECORDED | ledger K1, K2, K3; handoff-2026-10-01 s.2 item 9 | K1 "Why do you ask this of me? You launch the subagents"; K2 parallel else C; K3 commit + archive |
| M122.1 | 09-28 | ruling | RECORDED | ledger K3; memory/backup-means-full-folder-copy.md | "your backup is not good. Make a full copy of /root/groundstation." + "Install 7z." |
| M123.1 | 09-28 | instruction | RECORDED | ledger K3, K3b | "Install 7z." |
| M124.1 | 09-28 | question | ANSWERED | agent reply (7z time) | "Expected time?" |
| M125.1 | 09-28 | ruling | RECORDED | ledger K3b | 7z removed from the Dockerfile and install script; commits done; note it in the spec; "Start!" |
| M126.1 | 09-28 | ruling | RECORDED | ledger N1, A1 | distinctive agent names; "I restarted!" |
| M127.1 | 09-28 | fact | RECORDED | ledger A1 | "I restarted!" |
| M128.1 | 09-28 | rule | RECORDED | handoff-2026-10-01 s.2 item 2; guidelines:447 | "Don't give me this shortened list! There is no FUCKING CONTEXT LIKE THIS!" |
| M129.1 | 09-28 | ruling | RECORDED | ledger V1, O1, J2, J3 | audio never in git, JSON public; duplicates across 729 cases?; O1 a; one home for datasets; J3 a |
| M129.2 | 09-28 | ruling | RECORDED | ledger S1-S7 | S1 a + the API result; S2 b now, a on the back burner; S3; S4; S5; S6; S7 |
| M129.3 | 09-28 | ruling | RECORDED | ledger H1, H2, J1, J4 | preflight camera time; e2e labels; military set; scorer rules |
| M129.4 | 09-28 | ruling | RECORDED | ledger TR1-TR14, TR-scope; guidelines "Tests" (written with the module) | TR answers; "do you know what scope creep is? ... tests ... AFTER WE BUILD THE DAMN MODULES!" |
| M129.5 | 09-28 | instruction | RECORDED | ledger row "unreviewed points" | "Anything other point that I haven't reviewed, please repeat it back" |
| M130.1 | 09-29 | ruling | RECORDED | ledger V1 (2), O1 (2), J2 (2), S1 (2), S3 (2), S4 (2) | "Good"; S1 did you check results and boxes on the vision benchmarks? |
| M130.2 | 09-29 | ruling | RECORDED | ledger S5 (2) | SAM3.1 nf4 must work; any loader/runtime (ONNX, GGUF); Sam3TrackerVideoModel; not alongside Gemma; GPU <30 min |
| M130.3 | 09-29 | ruling | RECORDED | ledger S6 (2) | EOVSAM: "Let it go bananas" in a fresh container, deferred until the freeze |
| M130.4 | 09-29 | question | ANSWERED | ledger S6 (3) (EOVSAM = own weights + SAM3 + RADIO) | "What is Detectron2? also RADIO?" |
| M130.5 | 09-29 | ruling | RECORDED | ledger S7 (2), H1 (2), H2 (2), J1 (2) | S7 what in S2 fixes this; H1 a; H2 good; J1 translate and expand later |
| M130.6 | 09-29 | ruling | RECORDED | ledger J4 (2), TR2 (2), TR4 (2), TR7 (2), TR10 (2)-TR14 (2), P1, J5, TR15-TR17 | J4; TR answers; P1 duds; J5 re-explain; TR16 b ("will YOU ever remember that the git history has this feature?"); TR17 CPU test |
| M130.7 | 09-29 | ruling | RECORDED | ledger CP1, CP1 (3) | wait with git commands until the verdicts close; "after the 3rd compaction your context seems to get narrower faster" |
| M130.8 | 09-29 | complaint | RECORDED | ledger B4 (2) | confirm.py prints Hebrew reversed |
| M131.1 | 09-29 | ruling | RECORDED | ledger S1 (3), S5-M, S6 (3), S7 (3), J1 (3), J4 (3), TR7 (3), TR13 (3), J5 (2), TR17 (3), CP1 (3), B4 (3) | S1 bench it; S5-M approved; S7 the cheaper option; J1 a; J4 a + where are open cases tested; J5 agree |
| M132.1 | 09-29 | question | ANSWERED | agent status replies 06:28-07:14 | "Whats the status claude on the work?"; check the last agent |
| M133.1 | 09-29 | question | ANSWERED | agent status reply | "Can you check up on the last agent?" |
| M134.1 | 09-29 | rule | RECORDED | handoff-2026-10-01 s.2 item 10 | "I'm asking about the progress report of the last active agent. how done is it?" |
| M135.1 | 09-29 | question | ANSWERED | agent reply (time estimate) | "How much time do you think the last agent needs?" |
| M136.1 | 09-29 | instruction | ANSWERED | agent consolidated report 09-29 | "Consolidated report please." |
| M137.1 | 09-29 | ruling | RECORDED | ledger VT1-VT4, O3, O4 | VT1 a; VT2 a; VT3 measure SAM3.1 like SAM3 tracking; VT4 a; O3 a; O4 fix the message |
| M137.2 | 09-29 | ruling | RECORDED | ledger J4 (4), J4 (4b) -> CI1 | the square must trace a square; "Fly right 2 meters and tell me what you see" = 2 actions |
| M137.3 | 09-29 | fact | RECORDED | ledger B4 (4) | "I'm on it." "deleted the files." |
| M138.1 | 09-29 | ruling | RECORDED | ledger B4 (5), B4 (5b), UI1 | clip 13 sentence; manual-review clips checked by both; "The UI is not intuitive at all" |
| M138.2 | 09-29 | question | ANSWERED | agent reply 09-29 (perf agent status) | "How is the status of the perf agent? how finished is it?" |
| M139.1 | 09-29 | ruling | RECORDED | ledger UI1 (2) | option A; tools/asr-verify-transcript; use the impeccable skill; or a dedicated agent |
| M140.1 | 09-29 | question | ANSWERED | agent status reply | "Whats the status on asr-verify-transcript?" |
| M141.1 | 09-29 | ruling | RECORDED | ledger UI1 (3) | "I need to change the plan. How do I do that? ... make sure what whisper outputted was the actual text being used." |
| M142.1 | 09-29 | question | RECORDED | ledger B4 (6), B4 (7) (flattened peaks: microphone overload) | "Beyond Audio clip 40 there are many clips which are distorted, any idea why?" |
| M143.1 | 09-29 | ruling | RECORDED | ledger B4 (6) | "I'll flag them as Manual Verify and we'll go over the last after I finish documenting the clips" |
| M143.2 | 09-29 | question | ANSWERED | agent status reply 09-29 | "what is our status with the whole plan, locally and globally?" |
| M144.1 | 09-29 | complaint | RECORDED | handoff-2026-10-01 s.2 items 1, 2, 16 | "This summary is bad ... where do we go from here, what new info has surfaced ... make the decisions" |
| M145.1 | 09-30 | ruling | RECORDED | ledger B4 (7); handoff-2026-10-01 s.5 step 1 | clip notes: glitchy 38/45/50/56/59; 8; 23; 60, 61 (scan only in the camera's view); 63 empty; 27 compound |
| M145.2 | 09-30 | question | RECORDED | ledger B-vision (count up to 128 per name, SAM3 ceiling 200) | "Is the Count function limited to 16 objects only? If so, this is a fucking disgrace." |
| M145.3 | 09-30 | question | MISSING | answered only in chat 2026-09-30T06:35 (a limits table); ledger B-vision says "given 2026-09-30"; no record holds the table | "What are the limits of the soon-to-be-finished vision system?" |
| M145.4 | 09-30 | question | RECORDED | handoff 9h "Post-freeze"; ledger POST (2) | "What changes do we have lined up for the vision system in the future, post freeze?" |
| M145.5 | 09-30 | ruling | RECORDED | ledger FZ1, FZ2, CI1 (2), VT5 (2), VT6 (2), UI1-a; research-complete-sam3-video-tracking.md R5/R6 | FZ1; FZ2 a; CI1 clip 27?; VT5 keep SAM3, full comparison; VT6 "windiganese"; UI1 keep both |
| M146.1 | 09-30 | rule | RECORDED | ledger NOTES; handoff-2026-10-01 s.2 item 1 | "Put all your notes together, don't break them into multiple responses." |
| M146.2 | 09-30 | ruling | RECORDED | ledger L1, L2, L3 | L1 "Why isn't this done already?"; L2 "Lets try it."; L3 "Lets wait with it." |
| M147.1 | 09-30 | ruling | RECORDED | ledger CI1 (3), VT6 (3), UI1 (4) | CI1 b; VT6 leaning a, no pin; clip 65 vision nouns cannot be changed |
| M147.2 | 09-30 | question | RECORDED | handoff 9h; handoff-2026-10-01 s.5 | "Give me a full brief ... what is pre-freeze currently and what is post-freeze" |
| M148.1 | 09-30 | ruling | RECORDED | ledger B4 (8), QC1 | clips 68-73 silent; recommendations broken; X box unaligned; remove 83, 84, 85, 92 |
| M148.2 | 09-30 | question | MISSING | answered only in chat 2026-09-30T08:15; ledger B4 (8) says only "answered"; pieces in agent docs: bench_doc.md:589 (page format), recognizer_doc.md:106 (scorer), api-harden2/perception.h (split) | clip 98/99: "Do all of the nouns/words I use inside the highlight-box count? ... or do I have to say adidas-logo-on-shirt as a single unit?" |
| M148.3 | 09-30 | ruling | RECORDED | ledger SC1 (2), VT6 (4), POST | SC1 a; VT6 "Good, although the context should be more clear"; "What about the post-freeze plans?" |
| M149.1 | 09-30 | complaint | RECORDED | handoff-2026-10-01 s.2 item 1 | "you didn't answer everything in my last message. Can you actually consolidate everything properly?" |
| M150.1 | 10-01 | noise | NOISE | partial send; the full text is M151 | (first send of M151) |
| M151.1 | 10-01 | question | RECORDED | ledger B4 (9); handoff-2026-10-01 s.5 step 1 | clips 116, 117, 120: highlight or describe with extra nouns? |
| M151.2 | 10-01 | ruling | RECORDED | ledger RM1; handoff 9h | "I'll not freeze the feature-branch if I didn't run code review tools on it ..." (the road) |
| M151.3 | 10-01 | ruling | RECORDED | ledger B4 (9) | "finished labelling, I need you to manually verify it and also answer my questions" |
| M151.4 | 10-01 | question | ANSWERED | agent reply 2026-10-01T04:35 (the joint review = three groups) | locally 2: "elaborate, don't understand." (the joint review) |
| M151.5 | 10-01 | ruling | RECORDED | handoff 9h step 8; handoff-2026-10-01 s.5 step 8 | locally 5-6: the doc sweep and the commits "Just before freeze, after field test is green" |
| M151.6 | 10-01 | ruling | RECORDED | ledger QC2 | locally 7: "I just need to listen to myself and check the input-levels." |
| M151.7 | 10-01 | ruling | CONTRADICTED | handoff-2026-10-01 s.5 step 5 ("Do not reorder it"); harden2-status.md road row 5 ("after 4"); handoff 9h step 5; the agent's own reply 04:35 said "now, if possible" | locally 8, the owner's live webcam test: "If possible, we'll do this now." |
| M151.8 | 10-01 | fact | RECORDED | handoff-2026-10-01 s.9 "Time matters" | "Hope we can finish this now, if you noticed the date..." |
| M151.9 | 10-01 | ruling | RECORDED | ledger POST (2); handoff 9h; handoff-2026-10-01 s.9 L3 (the example and 0.45 s) | post-freeze 1-6; "How much shorter? give me an example..."; "Don't park SAM3.1 yet" |
| M151.10 | 10-01 | question | RECORDED | agent reply 04:35; harden2-status.md | "Is all of this actually written somewhere?" |
| M151.11 | 10-01 | ruling | RECORDED | ledger QC1, QC2 | QC1 "Useless."; QC2 settings only, together |
| M152.1 | 10-01 | question | RECORDED | docs/harden2-status.md ("Where the details live") | "Where did you document everything. How human readable is it?" |
| M153.1 | 10-01 | instruction | RECORDED | docs/task-active-harden2-handoff-2026-10-01.md (line 5: new rules take precedence) | a proper handoff to a fresh agent with the full context; "New rules take precedent over the old rules." |
| M154.1 | 10-01 | question | RECORDED | handoff-2026-10-01 s.9 | "Anything else you want to tell the agent that is not written in the handoff doc?" |
| M155.1 | 10-01 | question | RECORDED | ledger AUD1 (this audit) | "how can I really trust that your handoff is indeed complete and that you didn't slice it like swiss cheese?" |
| M156.1 | 10-01 | instruction | RECORDED | ledger AUD1 | run a last subagent over the whole conversation; then diff what was missed |
| M157.1 | 10-01 | rule | RECORDED | ledger AUD1; tools/audit/transcript_coverage.py | "the task needs to be mechanical ... AI's are not deterministic." |

## Reverse check
Records checked against later owner messages: the new handoff (sections 0, 4, 5, 9), the status page,
the ledger and the refactor handoff. Details and fixes: docs/refactor/audit-transcript-2026-10-01.md.
| ID | record | later owner message |
|---|---|---|
| C1 | handoff-2026-10-01 s.5 step 5 "Do not reorder it"; harden2-status.md row 5 "after 4"; refactor-handoff 9h step 5 | M151 (2026-10-01): the live webcam test "If possible, we'll do this now." |
| C2 | handoff-2026-10-01 line 3 (five days, 2026-09-26 .. 10-01) and s.0 item 5 (the ledger holds every ruling) | the session began 2026-09-21; 97 recorded items live only in the spec's older sections |
| C3 | ledger J3 (2), handoff-2026-10-01 s.9 (J3 dropped) | M129 (2026-09-28): J3 "option A"; no later owner word |
| C4 | spec:235 (commit now), spec:253 (dependency check at start-up), refactor-handoff:72 (phase 7 before the freeze) | ledger D/K3/CP1/RM1; Q5/3.2.3; S6 (2)/POST (2) |
