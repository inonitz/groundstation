# harden2 session log, 2026-09-23 / 24 (for the next agent after compaction)

RESUME HERE (2026-09-25): read docs/guidelines.md ("All guidelines at a glance") FIRST, then the
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
