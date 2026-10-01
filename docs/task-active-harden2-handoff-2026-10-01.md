# harden2 handoff, 2026-10-01: to a fresh agent

You take over the harden2 work from an agent that worked with the owner for ten days (2026-09-21 .. 2026-10-01).
This file gives you the full context: the rules, the lessons, the system, the state, and the road ahead.
NEW RULES TAKE PRECEDENCE: where this file or a newer ruling differs from an older document, the newer one wins.

| section | content |
|---|---|
| 0. Read first | the reading order and the authority of each document |
| 1. Hard rules | safety, git, the repository, frozen code |
| 2. How to work with this owner | the lessons of five days, each with the incident that taught it |
| 3. The system | what harden2 is, its layout, how to run and check it |
| 4. The state at handoff | what is done, the gate, what is uncommitted |
| 5. The road ahead | the owner's order to the freeze, step by step, and the plan after it |
| 6. Open items and known issues | what is unexplained or unfinished |
| 7. Agents | how sub-agents were run, and what carries over |
| 8. Where everything is | the document map |
| 9. Notes from the previous agent | what is not written elsewhere |

## 0. Read first
1. This file, whole.
2. docs/harden2-status.md: the one-page human overview.
3. docs/guidelines.md: every standing rule ("All guidelines at a glance", then "Project rules learned in harden2").
4. docs/task-active-harden2-refactor-handoff.md, section 9h (the road), then 9d, 9f, 9g (the task lists, all ticked
   except the owner's items).
5. docs/spec-harden2-cleanup.md, "Decision ledger": every owner ruling from 2026-09-26, word for word; the spec's older dated
   sections hold 97 earlier rulings (2026-09-21 .. 09-25). Together they are the AUTHORITY on what was decided. Search it (rtk grep) before you recommend anything.
6. docs/HISTORY.md: the newest entries (2026-09-28 .. 2026-10-01) hold every result with its numbers and verdict.
CLAUDE.md loads by itself; read it too. The memory index (MEMORY.md) loads by itself.

## 1. Hard rules
- **Drone safety:** never send arm, takeoff, land, stick, velocity or motor commands to a real drone. Control runs
  only against the mock at 127.0.0.1. The owner runs every real-drone command, with the aircraft secured.
- **Git:** the owner runs EVERY git write, staging included. You read (status, log, diff, show) and suggest commands.
  The owner commits just before the freeze (ruling RM1). Never anything that rewrites or destroys the repository.
- **Frozen:** projects/integration_tts/ is never edited.
- **Audio never enters git** (ruling V1): .gitignore ignores every audio type; datasets/ JSON, JSONL and Markdown are
  public. The owner's voice clips stay local.
- **Recordings file:** never edit datasets/asr/recordings.json while the owner's labelling server runs (it rewrites
  the file at every save). Check with `ps -C python3 -o args= | grep server.py` first.

## 2. How to work with this owner
Each lesson cost real friction. The rule is first; the incident is in brackets.
1. **Answer every point, by number, in ONE response.** Gather ALL open items in one "Open with the owner" section,
   each with its full context, even if you gave them before. (2026-09-30: "Put all your notes together, don't break
   them into multiple responses.")
2. **A decision item carries its full context:** what was found, the numbers, what each option does and costs, and
   your recommendation with its reason. Never a one-line table of decisions. (2026-09-28: "Don't give me this
   shortened list! There is no FUCKING CONTEXT LIKE THIS!") End with IDs the owner can answer in one line ("X1 a").
3. **Record every ruling verbatim in the ledger IN THE SAME TURN**, also in discussion rounds. (Failed twice.)
4. **A recommendation is not a decision.** Before recommending, search the docs for an earlier ruling on the same
   subject, and name it. (The previous agent recommended deferring SAM3.1 against the owner's 2026-09-04 ruling
   "PRIORITIZED ... NOT abandoned".)
5. **Measure, never guess.** A number you state is measured or labelled "unverified" or "estimate". When asked for a
   number, measure it in the same turn. ("Well fucking measure it?")
6. **Researching a model means downloading, loading and testing it**, not summarizing its paper. (EOVSAM: "THE
   RESEARCH WAS TO DOWNLOAD & LOAD & TEST THE MODEL!")
7. **Never delete working code because "git keeps it".** Nobody reads old diffs. Unused code gets a test or a ruling.
8. **Tests are written WITH the module**, before it is called done. A review must not hand the owner a backlog.
9. **Don't ask what you can decide** yourself (how you configure your own agents, tools, file layout inside a task).
   ("Why do you ask this of me? You launch the subagents, not me.") Ask only real owner decisions.
10. **Answer the exact question.** "How done is X?" wants a fraction and a list, not a narrative.
11. **Never frame a multi-part finding as yes or no.** Give each part its own answer.
12. **Never put Hebrew and English in one sentence.** A Hebrew example goes in its own line or table cell.
13. **Plain words for the owner.** Task IDs only as references after a plain name. Explain every term once.
    Banned words: wire, seam, load-bearing, sieve. ("You're speaking windiganese to me.")
14. **Prose rules (a hook enforces them):** STE: one idea per sentence, at most 20 words. A heading or a bold label
    followed by a list counts as one sentence until a period: end labels with a period or keep them short.
15. **Concrete commands with absolute paths**, ready to paste.
16. **Status updates short; decisions full.** The owner reads long replies, but hates noise and missing context.
17. **The owner tracks your context.** Offload decisions and state to files continuously; keep reads narrow.
18. **User-facing tools must be designed for a human:** the owner rejected a terminal labelling tool and the first
    web page ("The UI is not intuitive at all and it pisses me off"). Use the impeccable skill for UI; verify with
    screenshots (a headless browser exists for tools/asr-verify-transcript).
19. **Tool quirks:** use the rtk wrappers for reads and searches; the Write tool is denied in this project, so write
    files with Bash heredocs; the auto-mode classifier often refuses rm and downloads: hand the owner the exact command.

## 3. The system
**Goal:** a drone a person commands by voice in Hebrew, that understands what it sees, and acts. The live system is
projects/integration_harden2 (branch feature-hardening-mvd). Long-term it fuses onto the C++ llm_to_action engine.

**Layout (folders of projects/integration_harden2):**
| folder | job |
|---|---|
| app/ | main.py builds the services (class Services), then the modules; turns.py (one transcript -> a turn); ui.py and the panes |
| keys/ | the global keys over ROS2 (F1 quit, F2 clear, F4 kill toggle, F5 push-to-talk) |
| audio/ | speech in (the ROS ASR server, the phone) and speech out (the phone, the laptop voice) |
| video/ | one video source; cam_list.py for the preflight |
| sam3/ | the SAM3 service: contract, loader (warm-up at start), model (one image encoding per pass; nf4 weights saved once) |
| perception2/ | the vision system: highlight, count, describe; the gate, verify, the engine |
| recognizer/ | route() decides, act() acts; the fast path, the guards (numbers with all seven front letters and fractions) |
| gemma/ | the Gemma server process (warm-up before its row is UP) and the client |
| dji_app/, control/ | the phone-app client (loopback-guarded) and flight control |
| log/ | the session record, the perf record (every frame; run.sh perf), show |
| runtime/ | die(), the status rows, the supervisor, the package check, ROS |
| util/, config/ | shared helpers; config is the ONE source of every value |

**Run and check (absolute paths):**
- The app on the webcam and the mock: `bash /root/groundstation/projects/integration_harden2/run.sh up webcam mock`;
  the preflight: `run.sh preflight webcam`; the perf report: `run.sh perf`. Every setting: docs/spec-harden2-run-arguments.md.
- The gate (from projects/integration_harden2): `python3 -m flake8 --isolated --select=E30,E501,E70,E731
  --max-line-length=89 .`; `python3 -m pyflakes .`; `python3 /root/groundstation/tools/audit_exceptions.py
  /root/groundstation/projects/integration_harden2` (expect "except handlers: 5"); `python3 -m pytest -q test/` twice
  (expect 248 passed, 2 skipped); the end-to-end test: `HARDEN2_APP_TEST=1 python3 -m pytest -q test/test_app.py -k end_to_end`
  (needs the GPU and real Gemma; take the locks gpu webcam display suite through tools/lock.sh).
- Benchmarks: bench/recognizer/accuracy.py (545 sentences in datasets/recognizer; `--print NAME` prints a live list);
  bench/perception (the vision system, 137 labelled rows); bench/sam3-assessment and bench/sam3-video (research).
- The labelling page: `python3 /root/groundstation/tools/asr-verify-transcript/server.py` (port 8766).

## 4. The state at handoff
- **All agent tasks are done and validated** (handoff 9d, 9f, 9g ticked; HISTORY 2026-09-28 .. 2026-09-30).
- **The gate is green:** lint clean; audit 5; 248 passed, 2 skipped; the end-to-end test passes.
- **Key results:** a highlight shows its first box about 0.95 s after the transcript (3.8 s before, cold); a planned
  mission 0.77 s; the number guard reads 40 of 40 (was 7); the recognizer benchmark 458 PASS of 545 sentences, each once;
  SAM3 and SAM3.1 video tracking fit 8 GiB in nf4 with a 16-frame limit. Details: docs/harden2-status.md.
- **Uncommitted:** about 150 paths (everything since the owner's commits 81b1865, 3c20847, fdd2550, 9fc6c67 of
  2026-09-28). All validated. The owner commits just before the freeze.
- **The owner finished labelling the 139 recordings** (datasets/asr/recordings.json) and wants every label verified.

## 5. The road ahead
The owner's order (ruling RM1, 2026-10-01; handoff 9h). Do not reorder it. The owner first reviews the current state WITH YOU
(2026-10-01: "No, we won't run it now, I want to review the current state with the handoff agent.").
1. **The joint review: verify every label with the owner** (he asked: "I need you to manually verify it and also
   answer my questions"). Go clip by clip (manifest.jsonl gives whisper's text; recordings.json the saved label) and
   present them in batches, each with its full context. Known items:
   - remove as inaudible: clips 67-73 and 82 (ruling QC1); clip 63 stays (nothing was said; empty sentence, nothing flies);
   - already removed: 83, 84, 85, 92 (with reasons);
   - clips 116, 117, 120: highlight or describe? (highlight = a box on a named object; describe = a spoken answer);
   - glitchy 38, 45, 50, 56, 59: measured microphone overload (flattened peaks); keep or remove, with the owner;
   - unclear intent 8 and 23; scan requests 60 and 61 (no scan capability yet: manual review);
   - clip 27 is a flight plus a vision request: compound plans come after the freeze (CI1): grade as review;
   - how target words are graded (clips 98, 99): Gemma writes one English target; the vision system splits it into
     the main object (SAM3 searches it as one phrase), the relation and the related object (verify checks them). In
     the page each comma-separated word must appear in Gemma's target, any order ("logo" matches "logos");
   - clip 13's sentence must be the Hebrew for "fly back 8 meters" (check it was fixed);
   - the 34 expected-result drafts (21 military, 13 open cases) and the 144 drafted vision kinds: review tables in
     docs/refactor/recognizer_doc.md ("Review for the owner"); the square must trace a square (four legs).
2. **B2 and the benchmark rerun:** whisper plus the recognizer on the recordings (path B: whisper prepass, then
   route(); report whisper's word error rate; clips 63-100 have no whisper text in the manifest, so run whisper);
   then rerun bench/recognizer/accuracy.py with the confirmed drafts and kinds.
3. **Finish the cleanup and the refactor.** Settle the 9 old unticked lines of handoff sections 4-9a (done or open);
   docs in the owner's terms; the architecture spec's old paths (system/, perception2/sam3_backend); the roadmap.
4. **Code review with the review tools** (the code-review skill; the project's thermo-nuclear review), then fix.
   ("I'll not freeze the feature-branch if I didn't run code review tools on it.")
5. **The owner's live webcam test**, with a joint microphone input-level check (QC2: settings only; the clips swing
   from overload to almost silent).
6. **The field test on the real drone**, secured, until done. The owner runs it.
7. **A walk-through** so the owner understands the whole system.
8. **The doc sweep and the owner's commits**, just before the freeze; then the freeze (a git tag).
**After a successful freeze** (handoff 9h): benchmarks (whisper under noise, SAM3 low light); the recognizer (a
shorter plan answer + a flight and a vision request in one sentence); near-term: SAM3 in its own process, and SAM3.1
and EOVSAM evaluated BY THE OWNER AND YOU TOGETHER (EOVSAM in a fresh container); later: the vision tracker (box way,
16-frame limit), scan, vision-driven action; far: the C++ fusion.

## 6. Open items and known issues
- Unexplained, seen once each: the end-to-end test failed after 0.18 s; one warm-up run's plan took 735 ms in the app
  against 371 ms in llama-server's log.
- The start stutter (the first 9-11 s, while SAM3 loads) stays; only SAM3 in its own process removed it.
- A mutation-check script can leave stale bytecode when a file is restored within the same second: clear __pycache__
  after mutation checks.
- Meta's SAM3.1 code gives an empty box-prompt output after frame 0 (bench/sam3-video reads the tracker state instead).
- The phone app: unverified whether /c/fly answers when a flight ends or when it starts (matters for compound plans).

## 7. Agents
- The agent type `harden2-agent` (.claude/agents/harden2-agent.md: Opus, medium effort) loads at session start.
- The previous four agents (recognizer, perf, bench, investigator) belonged to the old session; you cannot resume them.
  Their docs (docs/refactor/<name>_doc.md) hold every brief, note and checkpoint: a new agent continues from them.
- Ask the owner before spawning (how many, what scope). Write each brief into the agent's doc; the shared rules are
  docs/refactor/README.md (locks via tools/lock.sh and LOCK.md; one GPU job at a time; its own ROS_DOMAIN_ID).
- Validate every task three ways: the agent's own checks; its report against its brief; YOUR reading of every file
  it touched and your own gate run. Only then tick the task and write the HISTORY entry. Only you write HISTORY, the
  ledger, the handoffs and the session log.

## 8. Where everything is
See the table in docs/harden2-status.md ("Where the details live"). In short: this file (the handoff), the overview,
the guidelines, handoff 9h, the ledger, HISTORY, the research-complete documents, the agents' docs. Older handoff
documents (docs/task-active-restructure-progress.md, task-active-harden2-session-handoff.md) are history only.

## 9. Notes from the previous agent (not written elsewhere)
- **Time matters.** The owner wants the live webcam test and the field test soon ("Hope we can finish this now, if
  you noticed the date..."). Keep momentum: do what is ruled, ask only real decisions, batch questions.
- **Keep docs/harden2-status.md current** after every change. It is the owner's entry point; when it lags, he loses
  his footing. Its "Open with the owner" section is the one list of open items.
- **Agents overclaim sometimes.** Seen: a "done" with a failing test, a lock breach, an unlocked GPU run, a test that
  checked only a shape, a desk study reported as research. Re-run the gate yourself and read the touched files.
- **Drafts are not decisions.** datasets/recognizer cases carry a `draft` field until the owner confirms them; the
  scorer ignores drafts. Promote a draft only after the owner's word, then rerun the benchmark.
- **J3:** util/mission.step_text stays in util/ (the owner, 2026-10-01: "Yes, just keep it in util/").
- **Audit C4:** three old spec and handoff lines still read as in force; mark them superseded (see
  docs/refactor/audit-transcript-2026-10-01.md, C4).
- **fatal.py is not renamed** (the owner: "nah, forget it.").
- **VT6, the future tracker (decided: the box way):** a normal SAM3 detect finds the objects and gives the tracker a
  rectangle each; the tracker follows them with a memory of the last 16 frames (masks identical to no limit); a new
  detect every few seconds adds objects that entered the view. The word way (the tracker finds objects from a word)
  is slower (888 against 604 ms for 4-5 objects) and drifts up to 5.6 % with the limit. Tracking costs about a detect
  per frame: it adds identity, not speed. Not measured: tracking next to Gemma on the GPU. Numbers:
  docs/research-complete-sam3-video-tracking.md (R1, R2, R6).
- **L3, the shorter plan answer (after the freeze):** Gemma writes about 45 tokens of JSON per two-step mission at
  13.9 ms each; a compact format of about 12 tokens would save about 0.45 s (estimate; needs the benchmark rerun).
- **The labelling tool's own tests:** `cd /root/groundstation/tools/asr-verify-transcript && python3 -m pytest -q .`
  gives 21 passed, 5 skipped without the browser; 26 with it (install-browser.sh; Playwright in a separate folder).
- **Where the side environments live:** SAM3.1 (Meta's code) in /root/venvs/sam31 (bench/sam3-video/setup_sam31_venv.sh);
  the browser in /root/.venvs/asr-verify-browser; the nf4 SAM3 in /root/models/vision/sam3-nf4 (sam3/save_nf4.py, run
  by tools/devenv/install-runtime-deps.sh). The main torch/transformers/bitsandbytes stay 2.11.0+cu128 / 5.17.0 / 0.50.2.
- **Nothing is pending for the owner to delete:** the refused rm commands were all run by him (10 files, datasets/e2e).
- **Recommended first task (a recommendation, not a ruling; ask the owner):** audit this handoff against the source.
  The whole conversation is on disk: /root/.claude/projects/-root-groundstation/1d8b196b-7abe-45b9-a9d6-ddf7daef5fae.jsonl
  (about 72 MB). Extract every owner message and check that each ruling, question and complaint appears in the
  ledger, this handoff or docs/harden2-status.md; report the gaps. The same method recovered 13 lost rulings on
  2026-09-28, and a smaller mechanical check on 2026-10-01 found 24 ledger rows still marked "open" (fixed).
