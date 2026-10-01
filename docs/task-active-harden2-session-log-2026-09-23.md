RESUME HERE (2026-10-01): a FRESH AGENT starts from docs/task-active-harden2-handoff-2026-10-01.md (the full handoff),
then docs/harden2-status.md. All agent tasks are done; the owner finished labelling; next is handoff 9h step 1.
# harden2 session log, 2026-09-23 / 24 (for the next agent after compaction)

SUPERSEDED by line 1 (was RESUME HERE, 2026-09-25): read docs/guidelines.md ("All guidelines at a glance") FIRST, then the
handoff's section 9c (the current status + the speedrun split: agent A = step 11, agent B = 9a-2,
me = steps 8, 9 + the 3.6 fps dips, step 12 LAST). Ask nothing more: the owner approved the split.
Older pointer: docs/task-active-harden2-refactor-handoff.md section 9 (the plan), 9a (validation +
open items), 9b (the built design). Rulings: docs/spec-harden2-cleanup.md, sections dated
2026-09-23 (evening, night). History: docs/HISTORY.md, entries dated 2026-09-23 / 24.

## State at the end of this session
- 195 tests pass (MVD_HOME=integration_harden2 MVD_TRANSLATOR=none python3 -m pytest test/ -q, from
  projects/integration_harden2). flake8 E30x/E501(89)/E70x/E731 clean on all harden2 .py. pyflakes clean.
- NOT committed after the owner's 6 WIP commits (3e3aacc and before). Everything since is uncommitted.
- The app has NOT run end to end since these changes (step 13 = the webcam mock run).

## Done this session (plan steps; details in the handoff and HISTORY)
1. F4 global kill key via /keyboard/in/raw (app/keys.py); letters never act.
2. API v2 -> v2.2 headers in docs/api-harden2/ (compile with gcc -fsyntax-only).
3. Layout: app/, log/, dji_app/, util/, system/fatal.py, video/cam_list.py; "wire" renamed out.
4. One transmit switch (dji_app), control/flight.py = the drone ONLY; recognizer fast path.
5. Failure policies: WAITING (orange); phone app waits for the user; laptop parts restart then die;
   laptop TTS dies at once (9a-1); log start check.
6. SAM3: dispatcher (thread per task, max 8) + priority lock + vision service; typed routing (Routed).
9b. Services -> modules -> reverse shutdown (app/main.py); SpeechIn/SpeechOut lists (ASR_SOURCES,
    TTS_OUTPUTS); Video(source, gstreamer handle); ProcessSpec + Process handle; Gemma object;
    http.HTTPStatus; util/; benches start Gemma via the supervisor (LlamaServer deleted).
- All lines <= 89 (4 agents wrapped them, AST-proven). Density: packed assignments, ';', one-line ifs split.

## Bugs found and fixed this session
- asr_phone close left asyncio tasks pending -> crash handler died at shutdown (fixed: cancel + stop).
- PhoneAsr read its port at import (fixed: read when built).
- The "wire" rename changed 2 bench data keywords in cases_perception.py (restored; audit clean).
- A test wrote real session folders (fixed; the empty leftovers removed).
- show_session looked one folder too high (fixed: config.SESSIONS_ROOT).

## Owner rules learned this session (also in memory / spec)
- ASK before spawning any agent (memory: ask-before-spawning-agents.md).
- Code style = the owner's _track rewrite: guard clause first, one argument per line in long calls,
  blank lines by intent, short trailing comments ok, loop vars at the top, lines < 90.
- Do not build recovery for failures that do not happen (9a-1, the Gemma "space radiation" quote).
- A word ban covers names and prose, never data.
- Keep raising code-quality problems; document EVERY ruling and finding at once.

## Progress after 2026-09-23 (oldest first; append new lines at the END)
- 2026-09-24: 9a-12 DONE (older files regrouped by intent), 9a-5 DONE. 196 tests.
- 2026-09-24: owner: "You can start 2 more Opus 5.5 subagents on medium if you need to. You need to
  make sure that once you rendevouz with them (when they finish), you actually check their work
  according to the documentation and the session history" -- used for 9a-12 (agents A, B); briefs
  and reports: scratchpad regroup-brief.md / regroup-report-{A,B}.md. Permission was for that batch.
- 2026-09-24: step 7 DONE (5 except handlers, all in util/guarded.py + fatal.py), 9a-6 DONE, env reads
  -> config/defaults.py, stale docs fixed, agents' files re-read whole. 207 tests.
- 2026-09-24: status owned by each part (status()), recognizer split + class Recognizer, shared helpers
  deduplicated, UI gets manual_on (S.control removed), API headers v2.3.
- 2026-09-24: log/trace.py deleted (owner). 205 tests.
- 2026-09-25: first live run: Gemma SIGBUS on image questions = mixed ggml 0.15.3/0.18.0 sonames in
  build/release/shared/dji/bin (HISTORY 2026-09-25). The owner rebuilds the whole project; run.sh
  preflight now fails on a ggml mix. No CMake install change now (owner).
- 2026-09-25: HISTORY.md entries of 2026-09-24/25 put back in date order (owner: newest LAST).
- 2026-09-25: perf measurement BUILT (owner approved): log/perf.py, `run.sh perf`, the scripted run
  (SCRIPT=default, mock only). Chat line-break crash fixed. Preflight 1.3 s. 210 tests.
- 2026-09-25: first measured run: the screen (15 fps) is limited by the dark room (C920 alone 16-18 fps
  auto, 30 fps manual but black). Open: the 3.6 fps dips; SAM3 558 ms on the shared GPU.
- 2026-09-25: every standing guideline written into docs/guidelines.md (a summary at the top +
  "Project rules learned in harden2" at the end). Speedrun split approved (handoff 9c).
- 2026-09-26: step 8 DONE: system/deps.py checks every package, program and model file at start
  (main.py runs it before any import; `run.sh preflight` calls `python3 -m system.deps`). Binary paths
  moved into config (LLAMA_SERVER_BIN, ...). The PIL/bidi guard + ASCII pane and the phonikud guard gone.
- 2026-09-26: 9a-2 DONE (agent B, validated): render.py -> draw, chat_rows, chat_pane, status_pane;
  session.py -> disk, session_files (session.py 266, open). Cross-file names made public in app/.
  bench/vision-verify-bench/annotate.py repointed.
- 2026-09-26: step 11 DONE except two deletions (agent A, validated): run_list.py repointed. The rm of
  compare_engines.py + run_indepth.py and the INTEGRATION-HANDOFF.md line 118 edit were refused by the
  tool classifier: handed to the owner.
- 2026-09-26: step 9 DONE: test_the_whole_app_over_ros (HARDEN2_APP_TEST=1): the real app, 3
  questions, F4 on/off, Gemma kill -9 -> recovers, F1 over ROS quits. Passed.
- 2026-09-26: global keys = function keys only (owner 2026-09-23, "Use the function keys", half of it
  was lost in the spec): F1 quit, F2 clear, F4 kill; every letter does nothing over ROS.
- 2026-09-26: suite 213 passed, 2 skipped (twice); audit 5; logs/ clean. NEXT: the 3.6 fps dips, then
  step 12 (stale docs) LAST, then step 13 (code review).
- 2026-09-26: owner debrief round: bench deletion rule A-D recorded (bench/README.md, guidelines,
  spec); headers v2.4 synced (perception.h had drifted); docs/spec-harden2-run-arguments.md rewritten
  (every command, setting, key, flag); run.sh BIN from config, dead scene_input removed; KEY_ACTION_RELEASED
  -> config; 7 shebangs removed from library files; 9a-9/10/11 ticked; run_list tested on real Gemma.
  WAITING on the owner's list answers (see the chat reply of 2026-09-26) before run_all.sh.
- 2026-09-27: owner round 2: definitions of module / service / system recorded verbatim
  (guidelines "Terms"); 9a-7 closed; D2 done (research-complete-sam3-vs-omdet.md); window keys, title
  and HUD colours -> config; frame record keeps the worst frame (C.1 part 1); perf overhead measured;
  test/README.md lists all 217 tests. Owner ruled D3 (decide and act as separate chained functions),
  D4 a. WAITING on the owner's answers of the 2026-09-27 reply.
- 2026-09-28: the ironing rounds ended with every decision in the spec's ledger (70 question IDs + 34
  debrief points, checked by script); the task list (handoff 9d); the agent split + LOCK.md protocol
  (handoff 9e, open points); HISTORY records the handoff documents' order. Waiting: the owner's answers on
  9e (L1-L4 approved 2026-09-28: tools/lock.sh + flock, LOCK.md in .gitignore, ROS_DOMAIN_ID per agent,
  docs/refactor/<agent-id>_doc.md per agent, triple coverage).
- 2026-09-28: final check before compaction: C4 decided in 9d; setup task S0 + the baseline (215 passed, 2
  skipped, lint clean, audit 5) in 9e; outside callers named in D1/D2; per-task doc updates listed in 9d.
  G1 + G2 answered (task B7 retires the typing study; E2 takes contention.py + real_cadence.py; HISTORY now
  records the study). ALL GREEN: no question open. Next: the owner compacts, then says "start"; begin with S0.
- 2026-09-28, after the compaction: K1-K3 answered (spec ledger). The safety archive is made
  (backups/); the owner commits the 55 paths; S0 begins on 'start'.

## Next (the plan's remaining steps; handoff section 9)
- The next run: `SCRIPT=default WEBCAM_DEV=2 run.sh up webcam mock`, then `run.sh perf`; read the
  numbers with the owner, then decide what to speed up (this covers step 10's measurement).
- Step 8: one dependency-check file at start.
- Step 9: test_app.py headless over ROS topics (3 questions, F4 on/off, kill Gemma -> recovers, quit).
- Step 10: measure the display loop.
- Step 11: dead benches (run_list.py still uses LlamaServer/QWEN3VL; compare_engines.py, run_indepth.py).
- Step 12: stale-doc sweep outside harden2.
- Step 13: code review, the webcam mock run, the owner's commits.
- 9a-2 remainder: app/render.py (542 lines) and log/session.py (363) are still long.

---------------------------------------------------------------------------------------------
## DETAIL (written so nothing is lost at compaction)

### A. Module map as built (projects/integration_harden2), key API per file
- app/main.py: parse_source(); start_processes(supervisor, log_dir, source) -> gstreamer Process|None
  (gemma + keys ALWAYS; asr if "ros" in config.ASR_SOURCES; mock if not config.DJI_REAL; gstreamer if
  source_kind(source)=="ros", dies without config.PHONE_IP); on_global_key(code, control, say) (F4 only);
  use_masks(); main(): SERVICES log=SessionLog(), supervisor=Supervisor(), start_processes, gemma=Gemma(),
  dji=DjiApp.from_env(), sam3=BackendLoader(config.SEG); MODULES speech_out=SpeechOut(TTS_OUTPUTS, dji),
  say=say_with(speech_out), video=Video(source, gstreamer), control=Control(dji, log), S.control=control,
  sinks=VisionSinks(log, speech_out.say), vision=Vision(sam3, gemma, video.snapshot, sinks.sinks(),
  use_masks), recognizer=Pipeline(control, vision, gemma, log), turns=Turns(recognizer, say, log),
  speech_in=SpeechIn(ASR_SOURCES, turns), keys=Keys(lambda code: on_global_key(...)), ui=Ui(video, BOARD,
  log.dir); ui.run(on_clear=vision.clear); close modules reverse (ui, keys, speech_in, recognizer, vision,
  control, video, speech_out) -> ros.stop() -> sam3/dji/gemma.close() -> supervisor.stop_all() ->
  log.close() -> tmux kill (SCENE_TMUX_SESSION) -> os._exit(0).
- app/turns.py: fmt_step, chat(role,text,kind), Turns(recognizer, say, session).__call__(text, source)
  (chat user line, session.begin, routed=recognizer.handle, say(routed.say), FULL -> end_request refused,
  _record_turn); VisionSinks(session, speak).sinks() -> Sinks(on_start, on_count, on_highlight,
  on_describe(task, ok, desc, spoken, frame), on_pass); say_with(voice) -> say(text).
- app/ui.py: Ui(video, board, session_dir).run(on_clear)/close(); helpers source_label, dji_label,
  draw_overlays(display, boxes, masks, use_masks), compose_canvas(display, fps, src_label, dji_text,
  session_dir, board), on_mouse, handle_key(key, on_clear) (q/Esc quit, c clear, t masks, [ ] scroll,
  x clear chat). WINDOW="integration:mvd".
- app/render.py: render_status (STATUS_COLOURS: UP green, WAITING orange, else red), render_chat,
  draw_box, chat_kind, ascii_only (moved here), FONT, PANE_GROUND.
- app/state.py: S = Shared(): lock, hl_dets, hl_masks, target, thinking, use_sam, chat, control,
  chat_scroll. (S.control is a shared global read by the UI for the MANUAL header: known smell.)
- app/keys.py: Keys(on_key) (press only; release/repeat ignored; short msg ignored), close(),
  process(log_dir) = keyboard hook ProcessSpec. Topic config.KEYBOARD_RAW_TOPIC "/keyboard/in/raw",
  data [evdev code, action]; KEY_ACTION_PRESSED=1; KILL_KEY_CODE=62 (F4), KILL_KEY_NAME "F4";
  PUSH_TO_TALK_KEY_NAME "F5" (binding compiled in llm_to_action asr_node.hpp). The owner added
  C/M/Q bindings to llm_to_action keyboard_node.hpp (uncommitted C++ by the OWNER); the app ignores them.
- audio/: speech_in.SpeechIn(sources, on_heard) SOURCES={"ros": RosAsr, "phone": PhoneAsr}, unknown
  dies; asr_ros.RosAsr(on_heard) (+ argv(), process(log_dir): makes CLIPS_DIR, PULSE_SERVER env);
  asr_phone.PhoneAsr(on_heard, host="0.0.0.0", port=None->config.PHONE_ASR_PORT, dedup 1.5 s) REST+TCP
  one port, delivery thread (R21), clean close() (cancel tasks; _listening Event); speech_out.SpeechOut(
  outputs, dji) OUTPUTS={"phone": PhoneTts, "laptop": LaptopTts}, one-slot mailbox, say() never blocks;
  tts_phone.PhoneTts(dji).say -> dji.speak -> status.is_success; tts_laptop.LaptopTts(dji=None): phonikud,
  PortAudioError -> die at once.
- video/: video.Video(source, gstreamer=None, board=BOARD): kind=source_kind, live, read() (+ stall guard
  for ros: WATCHDOG_STALL_SEC/RETRY_SEC -> RECOVERING + gstreamer.restart), snapshot() copy, close();
  ros source opens at once ("waiting" screen until frames; row UP on first frame); cv sources retry until
  OPEN_TIMEOUT then fail() dies. ros_stream.RosStream (topic camera/stream, frames counter, close order),
  process(log_dir, phone_ip) required=False. source_kind: ros|webcam|gstreamer|stream|file.
- dji_app/client.py: DjiApp(host, port, allow_real, timeout, board) (non-loopback w/o allow_real dies),
  from_env(), close(); _http -> HTTPStatus|None (_status maps unknown code -> BAD_GATEWAY);
  _request (UP / probe); probe GET /status/ every WAITING_RETRY_SECONDS -> WAITING/UP; set_transmit,
  transmitting, _motion (CONFLICT when off); takeoff, land, stop (never blocked), fly_mission, halt,
  speak(text) (/tts, never blocked); mock_ready(), mock_process(log_dir) required=False. Row "dji app".
- control/flight.py: outcome_text(action, status); Control(dji, log): manual (switch off THEN /c/stop),
  auto, toggle_manual -> (action, status), emergency_halt (manual -> /c/stop, auto -> halt), fly (records
  mission in log), manual_on, close.
- recognizer/: fast_path.py (EMERGENCY_RE, MANUAL_RE, AUTO_RE, CLEAR_RE EN+HE, critical(), is_clear());
  recognizer.py recognize_direct -> ("emergency"|"manual"|"auto"|"clear"|"mission"|"reject"|"direct", ...);
  pipeline.py reject_why(action), Routed(kind, action, say, vision_task, vision_status), Pipeline(control,
  vision, gemma, log=None, trace_dir=None, plan2_fn=None): handle(text)->Routed, observe(**)->log.set,
  _fly, _vision(kind, target) typed, _route_plan, _critical, _plan2 (gemma.request, UNIFIED_GRAMMAR,
  max_tokens 300, PLAN_TIMEOUT_S), close(); lexicon.py (fix_target, find_nouns; moved from perception2).
- perception2/: vision.Vision(sam3, gemma, snapshot, sinks, use_masks, max_tasks): builds its own
  PerceptionEngine (detect=_locked_detect(sam3.detect), vlm_ask=partial(vlm_client.ask, gemma), config
  DETECT_FLOOR/HL_CONF/HL_REL/HL_MAX); count/highlight/describe -> (TASK_OK|TASK_FULL, task); clear();
  _track (owner style, period from START, HL_GIVEUP -> LOST, clear -> CLEARED, one highlight at a time);
  dispatcher.Dispatcher(max_tasks) (condvar thread, thread per task, FULL past cap); sam3_lock.PriorityLock
  (PRIORITY_COMMAND 0 < PRIORITY_REFRESH 1, FIFO within); backend.BackendLoader(seg, loader, board)
  (row "sam3", NOT_READY until loaded), vlm_client.ask(gemma, frame, question, dets). Deleted:
  task_queue.py, text_parse.py.
- gemma/: server.py thinking_flags, port_up, argv(port, thinking), process(log_dir, port, thinking);
  client.py Gemma(port).request(messages, grammar, max_tokens, timeout_s) -> (bool, text), close().
- system/: fatal.py (die, on_die, crash hooks), status.py (STARTING UP RECOVERING WAITING FAILED DOWN,
  BOARD, fail), supervisor.py (ProcessSpec(name, argv, env, ready, ready_timeout_s, log_path, required),
  Process(restart, wait_up), Supervisor.start(spec)->Process, restart, up_event, stop_all; required=False
  -> WAITING + retry every WAITING_RETRY_SECONDS), ros.py (start/stop, SignalHandlerOptions.NO).
- util/: net.port_open, process.native_env, hebrew.hebnum_to_digits + NUM_* tables.
- log/: session.SessionLog (start check dies; writes die on failure; slot per task id; trace_file(root);
  close), trace.Trace, show.py / score.py (tools).
- config: ASR_SOURCES (env ASR_SOURCES, default "ros,phone"), TTS_OUTPUTS (env TTS_OUTPUTS, default
  "phone", "" = silent) in defaults.py; SESSIONS_ROOT exported; WAITING_RETRY_SECONDS=5.0;
  COL_STATUS_WAITING; KEYBOARD_RAW_TOPIC etc. Removed: TTS_BACKEND, PHONE_ASR_ENABLED, TTS_HOST/PORT/
  TIMEOUT, SERVICE_RETRY_SECONDS. run.sh exports TTS_OUTPUTS (was SCENE_TTS); launches python3 -m app.main.
- test/: support.py (RecordingPhone(code, port) real HTTP server + real DjiApp + Control, own StatusBoard;
  dead_port(); CAR; StandInBackend(hits, delay) (matches first concept; records overlap); GemmaStub(reply)).
  One file per module: app, audio, control, dji_app, gemma, log, perception2, recognizer, system, util, video.

### B. Benches changed
- bench/hebrew-command-bench: bench.py gemma_server() context (Supervisor + gemma.server.process on
  PORT 18091, THINKING from GEMMA4_THINK, atexit stop); 7 scripts use `with gemma_server() as gemma:` and
  Pipeline(W(), None, gemma); W has emergency_halt/fly/manual/auto. Audit: python3 bench.py --audit CLEAN.
  Unverified: bench Gemma now also loads --mmproj (like the app); latency/VRAM not re-measured.
- bench/whole-system/run_list.py still DEAD (LlamaServer, QWEN3VL_EXTRA, recognizer.recognize,
  parse_highlight removed). Step 11: repoint or delete (HISTORY has its record).
- bench/vision-verify-bench/annotate.py imports app.render (renamed from overlay).

### C. Scratchpad tools (may vanish; recreate if needed)
- /tmp/claude-0/-root-groundstation/1d8b196b-.../scratchpad/check_wrap.py (AST-equal vs backup + lines
  <=89), refill.py (reflow ONE docstring: `python3 refill.py <file> '<first-line substring>'`), layout.py
  (flake8 E701/E30x fixer, AST-checked). Backup of pre-wrap tree: /tmp/claude-0/harden2-before-wrap.
- Check commands: python3 -m flake8 --isolated --select=E30,E501,E70,E731 --max-line-length=89
  --exclude=__pycache__ .   ;   python3 -m pyflakes .

### D. Owner rulings of this session, in order (full text in docs/spec-harden2-cleanup.md)
try/except must be proven unavoidable; no raise SystemExit (use die / move self-tests to tests);
commit in stages marked BROKEN (done by owner); an API per module (v2.2 headers); rename the banned
word everywhere in identifiers (not data); ONE transmit switch, control is its only user, F4 (not M:
letters are typed elsewhere) + spoken manual/auto end in control; control = the drone ONLY; keys its
own module; the recognizer parses EVERY command (fast path -> control); phone TTS = a phone-app request,
health = the "dji app" row; WAITING = orange; phone app/mock/gstreamer wait for the user; laptop parts
restart 3x then die; SAM3 failures die (OOM no retry); log: start check, no row; laptop TTS dies at
once; util/ for shared helpers; lexicon + reject_why -> recognizer; module map (video, audio, perception,
control, recognizer, log; system; gemma; config; test per module; app/ with UI file); services first,
modules get services, crash on init failure, close modules then services; speech in AND out = LISTS
from config (all run); video = one source; only process handles are passed (Video gets gstreamer's);
keyboard hook always runs; HTTP = http.HTTPStatus; benches start Gemma the app's way; style = owner's
_track rewrite; SAM3 threads: dispatcher + thread per task, chosen for clarity not speed; document
everything, keep raising problems, ask before spawning agents.

### E. Caveats / honest gaps
- Not run end to end (no GPU run this session). Real F4 via the real keyboard hook: unverified.
- 21 try blocks remain in app code (step 7). Audit: docs/audit-harden2-try-except-necessity-2026-09-23.md
  (its rclpy verdict is WRONG: no catch needed with system/ros.py's order).
- Files still over ~200 lines: recognizer/recognizer.py, app/render.py, log/session.py, perception2/vision.py.
- Older files not yet regrouped by intent (9a-12 remainder); tests keep some inline imports.
- Laptop-voice tests use a stand-in sounddevice (a device cannot fail on demand); vision tests use a
  stand-in SAM3 (GPU-only).
- English "stop tracking" still triggers the emergency (fast path "stop" first) -- unchanged, flagged.
- In mock mode, speech goes to the mock, not the real phone (behavior change, flagged to the owner).

### F. Before EVERY report to the owner (self-checks; I failed these this session)
1. flake8 layout command (section C) clean; pyflakes clean; no line > 89 in files I wrote.
2. Full suite twice (timing tests); no new folders under /root/groundstation/logs/sessions.
3. No inline imports, no packed assignments, no `a; b`, no one-line ifs in new code.
4. Every ruling of the turn written to the spec; every step ticked in the handoff; HISTORY entry.
5. The tools are now in tools/style/ (copied from the scratchpad).
6. `pgrep -f app.main` matches its OWN command line: check a process with `pgrep -f 'app[.]main'`
   (2026-09-25: I wrongly told the owner the app was running).
7. Before any run: HISTORY / progress notes are appended at the END (newest last), with verdicts.

### G. How the owner wants answers (learned the hard way this session)
- Answer the EXACT question asked. "What interface does each module expose to the others?" is not
  "is there a shared interface". "Why would it fail?" wants the causes, then the conclusion.
- When asked to quote the owner, quote the owner's exact words with the date.
- Answer every numbered point, in order; never mention review IDs (R1..R30) to describe work.
- Give recommendations with a reason; when the owner says "decide", decide and state it.
- Short sentences (STE), tables for comparisons, no filler; ask before spawning agents.
- 2026-09-28: S0 done (tools/lock.sh race-tested; LOCK.md; .claude/agents/harden2-agent.md; docs/refactor/ README +
  4 briefs; names per ledger N1). The launch failed: "Agent type 'harden2-agent' not found". The running session
  does not load a new agent type. Without it an agent inherits this session's effort, measured: CLAUDE_EFFORT=xhigh,
  not medium (P2). No agent runs; asked the owner (A1-A3 in the reply).
- 2026-09-28: the owner restarted the session (ledger A1 a); harden2-agent loaded. Wave 1 launched in the
  background: recognizer (A1), perf (C1), bench (B5 + B6), investigator (E2). Next: check each doc's first
  Progress line (model + effort = medium), then validate each checkpoint (triple coverage) as the agents report.
- 2026-09-28: all four agents run on claude-opus-5-5 with CLAUDE_EFFORT=medium (their docs). bench finished
  B5, B6 (except the refused rm) and B3; validated three ways (its doc; against its brief; every file read,
  the vision verdicts compared by the main agent). B5 + B3 ticked; B6 waits for the owner's rm. Found: the
  whole datasets/ folder is git-ignored, so recognizer's JSON cases (datasets/recognizer/) are untracked:
  asked the owner (V1), with bench's O1 (where recordings.json lives). bench WAITING for B1 and B4.
- 2026-09-28: investigator finished E2; validated three ways (its doc; against its brief; the document and all
  8 scripts read in full; R2 + R4 checked against the raw JSON; the EOVSAM citation checked online). E2
  ticked; D2's caller list updated. The main agent disagrees with the document's S2 a (own process): no SAM3
  failure in 40 sessions, and the guidelines forbid recovery for a failure that does not happen -> recommends
  S2 b + S3 a. investigator WAITING for C1 (E1). Open with the owner: V1, O1, S1-S6.
- 2026-09-28: perf finished C1-C4; validated three ways (its doc; against its brief; every file read: log/perf.py
  and perf_report.py in full, every other diff; the halt still skips the transmit switch). The main agent
  measured record() at 1.08 us and ran its own gate: lint clean, audit 5, suite 229 passed, 2 skipped, twice.
  C1-C4 ticked. investigator resumed for E1. perf WAITING for the layout brief (needs A1 + B1). Open with the
  owner: V1, O1, S1-S6, H1 (camera check), H2 (scripted e2e start).
- 2026-09-28: recognizer finished A1, B1, A2; validated three ways (its doc; against its brief; every file read:
  recognizer.py, numbers.py, util/hebrew.py, guards.py diffs, accuracy.py and scorer.py in full, tests, READMEs,
  header; the flight order of checks unchanged; the benchmark cannot send). The main agent fixed one false
  line in recognizer/README.md (stage 2 does NOT write prefixed numbers as digits) and ran its gate: lint
  clean, audit 5, suite 229 passed, 2 skipped, twice. A1, A2, B1 ticked; B6 ticked; both wait for the
  owner's rm. perf got "Brief 2" (D1, D3-D7; D2 waits for S1-S3) and resumes; bench resumes for B7.
  Open with the owner: V1, O1, S1-S6, H1, H2, R1-R4; the rm of 9 files.
- 2026-09-28: bench finished B7; validated (its doc; against its brief; the study diff against HEAD, the
  README, the bench list row; no banned word). B7 ticked; bench.py joins the owner's rm (its two importers
  are in the same command). bench WAITING for B4 (the owner's labels) before B2. bench's O2 (retire
  cases_commands.py, cases_perception.py, CASES.md) depends on V1.
- 2026-09-28: investigator finished E1; validated (its doc; against its brief; load_vs_frames.py read in full;
  the four sessions recounted by the main agent: 47/425 slow frames before "sam3" UP, 1/5735 after). E1
  ticked. investigator has no task left. New owner question S7 (the start dips if S2 b). Running: perf (D).
- 2026-09-28: perf finished D1, D3-D7; validated three ways (its doc; against Brief 2; every moved file diffed
  against HEAD, scripted_e2e_run.py read in full with its mock-only check, the D5 diffs, the default script
  compared). Main agent gate: lint clean, audit 5, suite 230/2 twice, the end-to-end test passed. D1, D3-D7
  ticked; guidelines.md paths updated (runtime/, keys/, scripted_e2e_run.py). No agent runs now.
  Left: D2 (owner S1-S3), B4 (owner) -> B2, E3, F1, F2. Open with the owner: V1, O1, S1-S7, H1, H2, J1-J4, the rm.
- 2026-09-28: E3 (the test review, a report, no changes) given to investigator (Brief 2 in its doc): it has
  no task left, D2's file moves do not change behaviours, and the owner ruled "What can be in parallel,
  should be done in parallel".
- 2026-09-28: investigator finished E3; validated (the review read in full; the bypass and echo findings
  checked against the tests; "config has no tests" found in handoff 4a). Its decision IDs renamed TR1-TR17
  (T1-T9 exist in the ledger). E3 ticked. No agent runs. Left: D2 (owner S1-S3), B4 -> B2, F1, F2.
  Open with the owner: V1, O1, S1-S7, H1, H2, J1-J4, TR1-TR17, the rm of 10 files.
- 2026-09-28: the owner rejected a shortened decision table; rule written to guidelines (full context per item) and memory.
- 2026-09-28: the owner's answers to V1..TR14 recorded in the ledger (verbatim). V1 applied to .gitignore. New rules: tests with the module; check earlier rulings before recommending; model research = download, load, test. Found: 4 session clips in HEAD and on GitHub (P1).
- 2026-09-29: the owner's answers of round 2 recorded (ledger rows marked (2), P1, J5, TR15-17, CP1). confirm.py prints Hebrew through python-bidi (B4). No git command until the owner says (CP1). S6-M deferred to a fresh container after the freeze.
- 2026-09-29: round-3 rulings recorded; confirm.py instructions rewritten; handoff 9f + Brief 3 (perf, investigator), Brief 2 (recognizer, bench) written; the four agents resumed.
- 2026-09-29: bench's TR tests validated (read in full, re-run by the main agent); ticked in 9f. B8 waits for J5.
- 2026-09-29: investigator finished S5-M; validated (the document read; every table checked against the raw JSON; the 05:45 incident touched no result). Decision IDs renamed VT1-VT4. S5-M ticked.
- 2026-09-29: recognizer's Brief 2 validated (code read; the square/r_dis4 conflict traced to the owner's two lists; the labels file checked: 1 clip, untouched in content); ticked. The owner reviews the J1/J4 drafts; datasets/e2e rm added to the owner's list.
- 2026-09-29: bench's B8 validated and ticked. bench WAITING for B4 (B2).
- 2026-09-29: perf's Brief 3 validated (old paths searched; the nf4 loader and install line read; the 6 tests listed; main gate green incl. end-to-end). Ticked. New owner questions O3 (preflight retry after down), O4 (GATE=vlm refusal message). No agent runs.
- 2026-09-29: consolidated report given to the owner. D2 ticked in 9d. F1 must also settle 9 old unticked lines of handoff sections 4-9a (done or open).
- 2026-09-29: round-4 rulings recorded; Brief 4 for investigator (VT3, VT4) and perf (O3, O4); handoff 9g; line 1 updated.
- 2026-09-29: perf's Brief 4 (O3, O4) validated and ticked. investigator runs VT3 + VT4.
- 2026-09-29: owner: clip 13 correction (apply when confirm.py closes); manual reviews done jointly; confirm.py UI rejected -> UI1 proposed. Typed Hebrew in the terminal is garbled (clip 13 evidence).
- 2026-09-29: UI1 a ruled; bench Brief 3 (web page, impeccable) written; bench resumed.
- 2026-09-29: UI1 validated and ticked (tests, binding, no outside links); first browser render is the owner's.
- 2026-09-29: UI1 (3): plan editor rows + whisper text default -> bench Brief 4. investigator finished VT3 + VT4 (to validate).
- 2026-09-29: UI1 (3) validated (tests re-run); the owner must restart the server.
- 2026-09-29: VT3 + VT4 validated and ticked. Owner flags distorted clips as Manual Verify (joint review later).
- 2026-09-30: owner's clip notes, vision questions, FZ1/FZ2, CI1, VT5, VT6, UI1-a recorded; bench Brief 5 (empty sentence), perf Brief 5 (FZ2).
- 2026-09-30: bench Brief 5 (empty sentence, 'Nothing was said') validated: 15 tests re-run; the owner must restart the server.
- 2026-09-30: FZ2 validated (e2e rows = raw records) and ticked; FZ1 asked with cuts L1-L3.
- 2026-09-30: rule: all open notes in one response. L1 go, L2 go, L3 after freeze; FZ1 decided; perf Brief 6.
- 2026-09-30: CI1 b; VT6 open (leaning a); UI1 (4) vision-request editor -> bench Brief 6.
- 2026-09-30: UI1 (4) validated (19 tests). New open item SC1 (scorer ignores the vision kind). No server runs: the owner starts it.
- 2026-09-30: L1 + L2 validated (gate green incl. end-to-end) and ticked: highlight 0.93-0.97 s from the transcript.
- 2026-09-30: clips 68-73 measured; B4 (8) page bugs + removed clips -> bench Brief 7; SC1 a -> recognizer Brief 3; VT6 a; post-freeze plan asked.
- 2026-09-30: recognizer SC1 done (vision field; 144 drafted kinds); bench breached recognizer's locks on labels.py/test_server.py (told; rebases). The owner's file intact: 97 clips; no server running.
- 2026-09-30: SC1 + B4 (8) validated (removals mapped to clips 83, 84, 85, 92; clip 73 unsaved). The owner may start the server.
- 2026-10-01: mechanical check: 24 ledger rows still said 'open' though later rows closed them; fixed (superseded/closed) + a reading rule; result docs' decision tables annotated with the rulings.
- 2026-10-01: AUD1: the transcript audit agent runs; its coverage check is a deterministic script (owner: 'the task needs to be mechanical').
- 2026-10-01: audit applied (C1-C4, G1-G6, the start date 2026-09-21).
- 2026-10-01: J3 closed (stays in util), fatal.py rename dropped, the live webcam test waits for the owner's review with the new agent.
