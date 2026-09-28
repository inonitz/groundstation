# Spec - harden2 exception and structure cleanup

Owner-reviewed 2026-09-21. Scope: remove exceptions from our code, rehome perception into perception2,
unify the llama-server launcher, and redesign the tts queue. Implementation follows this doc.

## Sections

| section | content |
|---|---|
| Objective | why this cleanup exists, and the quality bar |
| Tooling | the static check for try/except and raise |
| Exception policy | the rule every file follows |
| Per-file plan | one bullet per point, per file |
| tts_io redesign | the poll removal |
| perception migration | rehome, then delete perception |
| llama launcher | one Python launcher |
| Change impact | behavior, tests, blast radius |
| Phases | the implementation order |

## Objective

Our code must not use exceptions for control or error flow. It crashes on a fatal invariant through die().
It converts a third-party throw to a status code at that throw's boundary.

The quality bar for every line written here: fast, readable, and matched to docs/guidelines.md. That means
guard clauses, small units a reader holds at once, hoisted loop locals, house naming, and no exceptions in
our code. The code must read cleanly for any reviewer, not only for the author.

## Tooling

tools/audit_exceptions.py lists every try, except, and raise under a directory. It uses the stdlib ast
parser, so the dev container never needs an install. Run it to check this work, and next time.

## Exception policy

- Our code raises no exceptions. It returns status or error codes.
- die() (fatal.py) handles a fatal config or safety invariant: it logs, then os._exit.
- try/except is allowed only to wrap a third-party call that throws, converting it to a status there.
- A missing required dependency calls die() with a one-line install command, not a silent import guard.
- Why status over exceptions: a status lets the caller choose the response. An exception removes that
  choice, and can leave a lock held or a socket half-open. That is why error codes exist.

## Per-file plan

One bullet per point. Each names the target, the current problem, and the fix.

### audio/phone_asr.py
- _extract: json.loads throws on bad phone input. A safe-parse helper returns a status. No try in the caller.
- _on_text: it is the injected callback (dependency injection); the ASR delivers each transcript through it.
  The variable stays. Remove the try around it; the handler returns a status, never throws.
- readline(): a socket read throws on a dropped connection. End that one connection on the error, no broad catch.
- writer.close(): close() does not throw. Remove the guard.
- asyncio.start_server(): a taken port is reported only by a throw. Catch it once and die() with a clear message.
- call_soon_threadsafe(): the loop-stop can throw. Log it, do not swallow it.

### audio/ros2_asr.py
- Teardown (destroy_node, shutdown) can throw. Log it, do not swallow it.

### audio/tts_io.py  (worker redesign below)
- requests import: it is a hard dependency. Import it plainly at the top. No guard.
- phonikud import: it is optional per mode. On a missing package, die() with the install line.
- The queue drain and the worker poll: replace the queue with one slot and a threading.Event. No poll, no queue.Empty.
- p.terminate(): check poll() first, then terminate. No try.
- _say_phone: it throws through requests on a network error. Return a status; a narrow requests catch converts the throw.
- _say_phonikud: it raised our own RuntimeError on a bad aplay code, and phonikud and piper can throw.
  Delete our raise. Return a status.

### cam_list.py
- cv2 is a hard dependency. If it is missing, the app is already dead. Remove the import guard.

### config/defaults.py
- The ip-route subprocess: read its return code. Do not catch.
- The torch import: a hard dependency imports plainly; an optional one is checked, not guarded.
- open(/proc/net/route): the gateway lookup returns a status. A status lets the caller decide.

### control/dji_wire.py
- ipaddress.ip_address throws by design on a hostname. Replace it with a plain loopback string check.
  No ValueError, no try. That is the ValueError-without-an-exception path.
- HTTPError (lines 52, 85): urllib reports an HTTP failure only by throwing. Keep one narrow catch that returns the code.
- The re-raise (lines 59, 92): delete it. Return a status code the caller reads.
- Line 33 RuntimeError: a real-drone target without allow_real is a fatal safety invariant. Call die().

### overlay.py
- draw_pane: rewrite it readably.
- Font missing: crash. die() with the one-line download command.
- Imports: a hard dependency imports plainly; an optional one is checked, not guarded.

### recognizer/llama.py
- urllib and subprocess throws convert to a status.
- This file folds into the one Python launcher (below).

### recognizer/pipeline.py
- Imports: a hard dependency imports plainly; an optional one is checked, not guarded.
- The json.loads of model output returns a status.

### session_log.py
- Full rewrite. Status-based errors, no exception flow.
- Reconsider whether each lock is needed and simplify it. No exception can ever leave a lock held.

### video/camera_stream.py
- The rclpy import: a hard dependency imports plainly.
- ROS2 teardown (spin, join, remove, destroy): log, do not swallow.
- The frame parse (np.frombuffer, reshape): return a status.

### mvd.py
- Every catch becomes a status check.
- All imports move to the top of the file. No inline imports.

### test/test_router.py
- Unchanged. The functions under test can raise, so the except is legitimate in a test.

## tts_io redesign

Replace the polling queue with a single latest-value slot and a threading.Event.
- say(text): store the latest text under a lock, cut current playback, set the event.
- worker: event.wait() blocks at zero CPU, then reads and clears the slot and speaks. Latest wins by overwrite.
- shutdown(): set a stop flag, then set the event so the worker exits.
This removes both queue.Empty catches and the 0.2 second poll. It matches the C++ consumer pattern.
Status: BUILT in phase 1 (2026-09-21). 70 tests pass.

## perception migration

perception2 supersedes perception. Rehome by concern, then delete perception.
- parse_highlight, parse_count, ascii_only move to recognizer. They are text parsing, not vision.
- vlm_client wraps the one Python llama-server launcher.
- Eyes (YOLO26 background) is deleted. It is off by default and has drawn nothing for weeks.
- PerceptionEngine stays, focused, moved into perception2 as the vision-orchestration layer.
  It loses the text parsers and the dead VLM-highlight path.
- The app then talks to perception2 through the backend contract (spec-perception2-backend-contract.md).

## llama launcher

One Python launcher, config-driven, owned by the app and shared with the bench. recognizer/llama.py's
LlamaServer is the right shape. Keep a two-line shell wrapper only for the tmux pane log.
Today there are three paths: run.sh's tmux pane, vlm_client.ensure_server, and the bench's LlamaServer.

## Change impact

- A degrade becomes a crash only where directed: a missing font, a missing required dependency, a bind
  failure now call die(). A dead drone link or a dead TTS still degrades to a status, not a crash.
- detect's return changes to (ok, hits) per the backend contract; its callers adopt it.
- Regression gate: the 70 tests pass unchanged after each phase.
- Rewritten tests: the session_log tests (the file is rewritten); the tts tests (the worker changed);
  the perception tests (test_perception, test_perception_capture, test_scene_wiring) repoint to perception2.
- New tests: the tts latest-wins slot; the dji_wire status-code return; the safe-json parse.

## Phases

1. tts_io redesign. Self-contained and testable. DONE 2026-09-21.
2. The self-contained exception files: phone_asr, ros2_asr, cam_list, config, dji_wire, camera_stream, overlay, llama, pipeline.
3. The perception migration: rehome, one launcher, delete Eyes, delete perception.
4. mvd.py exception and import cleanup.
5. session_log.py full rewrite.

Each phase runs the 70 tests, adds the new tests, and reports the diff and the die-versus-status choices.

## Folded-in review findings (from the thermo-nuclear review, 2026-09-21)

Kept from docs/review-harden2-thermonuclear-2026-09-21.md. Done AFTER the per-file plan above.
- [ ] sam3_backend concurrency: one backend is called from three threads with no lock. Guard detect+mask_for_box as one critical section (a lock), so the mask cache cannot race.
- [ ] mvd.py dead code: px is always None after the gate; delete the px plumbing. The `english` record key never exists; read he2 or drop the branch.
- [ ] concept.py dead VLM subsystem: extract_concepts and friends (~100 lines) are unused. Delete with the perception migration (the offline phrase_concepts stays).
- [ ] test/capture_golden_config.py: retired but present, stale env vars. Owner git-rm.
- [ ] test/live_mock_smoke.py: asserts the deleted English tier; would fail. Rewrite to the harden2 path or retire.
- [ ] video_watchdog.py: no __main__ guard; it runs at import. Wrap the runtime in main() under a guard.
- [ ] Imports before the module docstring (dead literal): vlm_client.py, prompts.py; show_session/score_session code above the shebang. Docstring first.
- [ ] File-handle leaks: open() without `with` in concept, session_log, llama, trace, cam_list.
- [ ] kill.py: killed/refused are shared across threads with no lock. Add a small lock or document the GIL assumption.

## General principles (owner-approved 2026-09-21) — apply to EVERY file

1. Invalid config or input calls die(). No silent degrade.
2. A missing required connection or resource calls die() at startup, not on first use. EXCEPTION: the drone
   link, which flags and reconnects instead of dying (see the drone-link ruling below).
3. Prefer a proper library over a hand-rolled subprocess or CLI. (tts: aplay -> sounddevice, approved.)
4. Choose dispatch once at construction. No branching in a hot loop. (tts worker picks self._say once.)
5. Wrap an unavoidable third-party throw (requests/urllib/subprocess/rclpy/json), but die on a SEVERE error
   or handle it properly (status + flag + reconnect for the drone link). Never swallow to a quiet return.

Verified applied to tts_io 2026-09-21: invalid backend -> die; phone unreachable at startup -> die (socket
check); worker dispatch chosen once; requests wrapped, a phone that answered at startup going silent -> die.

## Drone-link resilience (owner ruling 2026-09-21) — NEW feature work, scope separately from the cleanup

The drone link (DjiWire + the ApiServer on the phone) does NOT die on failure. Instead:
- A DIAGNOSTIC WINDOW shows what succeeded and what failed, with a specific error code and explanation per
  item at the bottom, so a failure is easy to spot.
- dji_wire._request already returns a status code (0 = unreachable), not an exception. KEEP that.
- RECONNECT: on a runtime POST failure, retry reconnecting to the ApiServer for a bounded time, then drop.
- KEEP-ALIVE: whenever flight is NOT occurring, periodically send a Noop command/pair so the drone does not
  enter sleep/eco mode. The drone sleeps if it is connected to the controller but idle past a timeout.
- Two failure modes: (A) ApiServer lost connection -> flag it; the aircraft keeps hovering (the Kotlin side's
  job, likely not ours); the human takes over with the RC controller. (B) ApiServer alive but drone in eco/
  sleep -> the keep-alive Noop prevents this.
- These are NEW features (diagnostic window, keep-alive, bounded reconnect). Build them AFTER the cleanup,
  as their own task; the cleanup only keeps the status-code contract (no exceptions) in place.

## Owner rulings 2026-09-22: the gemma package and the system status panel

Gemma serves both the recognizer (planning) and perception2 (vision). It is a shared resource.
- A new `gemma/` package owns ONLY two jobs: keep Gemma alive, and give one uniform interface to it.
  No recognizer or perception task code lives there. Prompts and parsing stay with their callers.
- The gemma package RECOVERS: if the server dies, it restarts it. If recovery fails, crash (die) with
  a clear message.
- SYSTEM STATUS PANEL, for EVERY subsystem (applies the drone-link diagnostic-window ruling to all):
  - Each subsystem shows a status "checkbox" on screen: GREEN when up, RED when down.
  - A red entry shows its current state, for example FAILED or RECOVERING, and the error.
  - This replaces ad-hoc chat lines such as "[VLM unavailable]". A failure changes a colour and a
    state; it is not a chat message.

### Follow-up rulings 2026-09-22 (same session)
- Status data: ONE small module (report(system, state, detail) + a snapshot). The module holds only the
  internals. The panel UI is drawn by overlay.py, not by this module.
- Panel placement: to the right of the chat pane, or below the image and chat.
- gemma client: request() returns (status, text). status is True on success, False on failure. No
  "Gemma down" text: the caller reads the bool; the panel shows the system state.
- THE APP STARTS EVERYTHING. Every process the stack needs is started (and supervised) by the app,
  not only Gemma. run.sh stops being the orchestrator.
- Recovery: 3 restarts, a constant in config/constants.py; then die() with the reason.

### Rulings 2026-09-22 (later)
- The ASR server, the keyboard hook and the gstreamer receiver are started from Python (the supervisor),
  like every other process. run.sh stops starting them.
- Screen layout: the camera stream takes the full width on top. Below it: the status pane and the
  chat pane side by side. The chat scrolls. (Reason: at 1280x720 the stream takes most of the window.)

- 2026-09-22: the phone TTS recovers like every supervised service: RECOVERING, retry up to the restart
  budget (3), back to UP when the phone answers, else FAILED + die() with the reason.

## Owner rulings 2026-09-23

- try/except: 28 in the app is too many. Each one must be proven unavoidable (sourced). Audit:
  docs/audit-harden2-try-except-necessity-2026-09-23.md.
- `raise SystemExit` has no place: use die().
- Commit everything now, in stages, on the feature branch. Every commit message warns: BUILD BROKEN,
  do not pull expecting a working app. The owner reviews the code AFTER the commit.
- Every system gets a proper interface (an API). The UI too. Draft v1 rejected; v2: docs/api-harden2/.
- Rename DjiWire / control/dji_wire.py: "wire" is a banned word, identifiers included. DONE (step 3):
  dji_app/client.py, class DjiApp; every "wire" identifier renamed.
- ONE transmit switch. The drone link sends every command laptop -> phone, so it owns an enable/disable
  switch in its API. Replaces KillSwitch.MOTION + pipeline.flight_allowed. SUPERSEDED same day: control is
  the switch's only user (see below). DONE (step 4).
- Recovery: the supervisor supervises every process the app starts. No per-system retry loops.
  CORRECTED same day: phone TTS is POST /tts on the same phone app and port as the drone commands.
  It is not a separate service. Its health is the phone app's health.
- Drone link recovery: RESOLVED (step 5): only laptop -> phone app is ours; no answer = WAITING (orange)
  + a GET /status/ probe; the app never dies because of the phone.
- Files: small and modular, each one does one small job or manages one system (KISS).
  If mvd.py stays too big, make an app/ (or main/) folder.
- Display loop: measure first. Camera redraws every frame; chat updates only on new text; status is
  monitored, not necessarily redrawn.
- Benches: each one is documented in docs/HISTORY.md in time order: why it ran, the result, the verdict.
- Dependencies: one file checks every dependency at start-up (replaces the scattered find_spec guards
  and the pipeline flat-import try).
- SAM3 tasks (owner design, restated): a dispatcher thread on a condition variable spawns one thread per
  task, max 8. Count is fire and forget. A highlight thread lives until clear or give-up. Only the SAM3
  forward is serialized. DONE (step 6, 2026-09-23): perception2/{dispatcher,sam3_lock,vision}.py.

### Follow-up rulings 2026-09-23
- The API draft v1 is REJECTED: it undersells the system. Redo it. v2 (one header per module):
  docs/api-harden2/ (2026-09-23), waiting for the owner's review.
- No new DroneLink. The one module that talks to the DJI phone app owns every DJI app service
  (commands, TTS, the transmit switch), like llm_to_action's DjiBackend.
- HISTORY.md: record every useful finding and decision, not only benches. Format: Why / Setup /
  Result / Verdict / Where, in time order.
- Problems that should not exist (e.g. the pipeline flat-import try): KEEP RAISING them (code quality).
  The owner's anger was that such errors exist at all, not that they were reported.
- SAM3 task design: chosen because it is easier to reason about, not for speed.
- Tests: test/test_<system>.py for EVERY system. A passing suite must mean each piece works, so the app
  works when the pieces are put together. Tests exercise the real component, not a canned fake.
  The four module self-tests (_smoke / selftest) move into these files.
- RESOLVED (owner module map + rulings below; built in step 5): which systems crash the app, which
  restart themselves, which wait for the user.

### Module map (owner, 2026-09-23)
- Systems: video, audio (ASR + TTS), perception (vision), control, recognizer (the router for audio),
  logging (exists, not a module yet).
- system/ (status, supervisor): makes sure every system works. No "System" abstraction is needed.
- gemma/: a module used by the recognizer and by vision for simple requests.
- config/: every constant and start-up parameter of the whole of integration_harden2.
- test/: one test file per MODULE (not per system).
- test_app.py (owner): open the app headless, ask 3 questions, enter manual mode, leave it, check that
  one system recovers. Done.
- (owner, 2026-09-23, cont.) The UI is its own file in app/. The logging module is named log/.
- The phone app API is a resource of its own, decoupled from video, audio and control, with its own
  status. Those modules use it; none of them owns it.
- test_app.py injects input the way the real system does: questions as ROS2 messages on the ASR topic
  (/asr_server/transcribe), the M key as a key event on /keyboard/in/raw (llm_to_action keyboard node).
  Gap found: the app reads M from the OpenCV window only; it must also take M from /keyboard/in/raw.
- RESOLVED 2026-09-23 (rulings below; built in step 5): laptop TTS failure policy; what counts as a
  "SAM3 failure"; whether logging can fail at all.
- (owner, 2026-09-23) The push-to-talk keys stay in config/. They do not move into audio/.
- (owner, 2026-09-23) SAM3: load failure -> die; GPU out of memory -> die (no retry for now); any other
  forward error -> crash hook -> die. "Not ready" and "no hits" are not failures.
- Logging: at app start, check the session folder can be created and written. If not, crash at start.
  Recording has no status row and no recovery.
- The phone app API becomes its own module, dji_app/, with its own status.
- Test files per module, as listed 2026-09-23 (test_video ... test_dji_app, test_app).
- SAFETY GAP (found 2026-09-23): the app reads the M kill key only through cv2.waitKey, so M works only
  while the OpenCV window has focus. The app already launches the global keyboard hook
  (llm_to_action_keyboard_hook, "keys") for push-to-talk, and it publishes /keyboard/in/raw, but the
  app never subscribes. Fix: the app subscribes to /keyboard/in/raw. DONE (step 1) with F4, not M.
- STEP 1 FINDINGS (2026-09-23), RESOLVED: the kill key is F4 (a function key, owner); letters are
  ignored globally. DONE (step 1). The findings:
  - llm_to_action_keyboard_hook binds only W S A D H, the arrows, Enter, Space and F1-F5
    (keyboard_node.hpp). It never publishes M, Q or Esc. Binding M is a C++ change (owner-written code).
  - The hook reads /dev/input with no exclusive grab: it sees every key typed in ANY window. A global M
    would toggle the kill whenever the operator types an "m" anywhere (e.g. "make" in a terminal).
    Engaging the kill by accident is the safe direction; RE-ARMING by accident is not.
- (owner, 2026-09-23) API v2 approved except control/recognizer. The WAITING state (external, the user
  must fix it) is shown ORANGE, not red (DONE, step 5). One transmit switch: yes (its user is control,
  ruled below).
- (owner, 2026-09-23) The recognizer parses EVERY command, the fast path included. A critical command
  (emergency, manual, auto) goes straight to control; otherwise it parses on (bypass, guards, Gemma) and
  routes: missions to control, vision requests to perception. Control parses nothing; it executes
  flight. API v2.1: docs/api-harden2/control.h, recognizer.h, app.h.
- (owner, 2026-09-23) Control USES the drone interface: it owns the comms to the drone. The cut-off
  happens in control, through dji_app's switch. Both paths end in control: F4 (app) -> control, and
  spoken manual/auto (recognizer) -> control. dji_app provides the switch; control is its only user.
  Vision requests go to perception typed, not as re-parsed English.

### Owner rulings 2026-09-23 (evening)
- Code density: the code is too dense. Use blank lines between logical steps, one statement per line,
  no packed tuple assignments or dense lambdas. Applies to every file touched this session.
- Document EVERYTHING (restated): every ruling here, every step in the handoff plan, every finding in
  HISTORY.md.
- 9a-7 reframed by the owner: which interface does each module expose to the other modules? Answered in
  chat 2026-09-23 with a table; leaks found (see the plan, 9a-9 .. 9a-11).

### Owner rulings 2026-09-23 (night): object lifecycle and backends
- HTTP results use the standard library (http.HTTPStatus: .is_success, CONFLICT, ...), not our own
  sent()/BLOCKED/UNREACHABLE layer. "No answer at all" is None.
- Speech IN works like speech OUT: ONE audio interface receives which backends to use and initializes
  them. CORRECTED by the owner the same night: speech in takes a LIST of sources (config option, today
  ros + phone, both on); running several at once is intended (a remote ASR source must never take away
  ground control). It was only wrong that the list was hard-coded. SAME RULE for TTS (owner): speech out
  takes a LIST of outputs (config option, e.g. phone + laptop); every sentence goes to each of them.
- Video works the same way: ONE video interface receives its backend (webcam, dji/ros, file, stream).
- Every class follows the C++ shape: constructor, destructor (close), internal methods, maybe static
  ones; then something that uses the class.
- App lifecycle (owner's preferred option):
  1. Init every SERVICE that needs init (processes, the phone app, SAM3, Gemma, the session log...).
  2. Give every MODULE the services it needs (passed into its constructor).
  3. Anything fails during init -> crash and say why.
  4. On shutdown the app closes every module, then every service (reverse order).
- Replaces 9a-9 / 9a-13 / 9a-14 (plan) with this design.
- (owner, 2026-09-23 night) Control = the way we interact with the autonomous system (the drone) ONLY.
  Keys is its own module (the keyboard hook's ROS node): it reports key presses through a callback;
  the app connects F4 to control. Keys does not receive control.
- Only process handles are passed, never the Supervisor itself: Video(dji) receives the gstreamer
  process handle (to restart it on a stall). No other module restarts a process.
- The keyboard hook is ALWAYS started: F4 (the kill key) needs it, whatever the ASR sources are.
- (owner, 2026-09-23 night) Design 9b agreed: process handles, Keys separate, Control = drone only,
  Video = one video option, the UI reads the status board.
- 9a-1 CLOSED: the laptop speaker fails only when the laptop sound system itself breaks (the host
  PulseAudio socket, the device unplugged). A retry fixes none of that, so there is nothing to
  recover: a playback error dies at once with the reason. The 3-try re-open loop is removed.
- (owner, 2026-09-23 night) util/ agreed: util/net.py (port_open), util/process.py (native_env),
  util/hebrew.py (hebnum_to_digits), util/guarded.py (step 7's wrapped third-party calls). lexicon.py and
  reject_why move to recognizer/. system/ keeps fatal, status, supervisor. More may move to util/ later.
- (owner, 2026-09-23 night) Code style, by the owner's own rewrite of Vision._track:
  - a guard clause for the unusual case first (e.g. `if frame is None:`), not a nested normal path;
  - a long call wraps with ONE argument per line, the closing paren on its own line;
  - a short trailing comment on the line it explains is fine;
  - blank lines group the steps by intent; two blank lines before the final block;
  - loop variables declared at the top of the function.
- 9a-1, the owner's words (2026-09-23 20:10): "Why would the laptop speak output fail? genuinely!
  Besides using ALSA, what kind of issue could cause this??????" Same principle as 2026-09-22: "Why
  would gemma go unreachable mid-session? What fucking failure case is this?" -> do not build recovery
  for a failure that does not happen: the laptop voice dies at once on a playback error.

## Owner rulings 2026-09-24
- (owner, 2026-09-24) Every environment read lives in ONE file: config/defaults.py ("Yes", to the
  question whether all env overrides should move there). config/__init__.py only maps names.
  Done: 15 reads moved from config/__init__.py, plus PULSE_SERVER (was read in audio/asr_ros.py),
  SCENE_TMUX_SESSION (was read in app/main.py), WEBCAM_DEV (was read in video/cam_list.py) and the
  two env WRITES (MIOPEN_FIND_MODE, OPENCV_FFMPEG_CAPTURE_OPTIONS).
- (owner, 2026-09-24) Stale docstrings are fixed NOW, not in the step 12 sweep ("Well HOW ABOUT YOU
  UPDATE THEM CLAUDE??? NOW???").
- (owner, 2026-09-24) "Why does a supervisor take a BOARD???" Answer given: the supervisor is the
  only code that knows each process's state, so it writes that row; the defect was the hidden
  global BOARD plus a test-only `board=` hook (two mechanisms). Fixed to the 9b design already
  ruled: the app builds ONE StatusBoard as a service and passes it (required, `board=` keyword) to
  the supervisor, the phone-app client, video, the SAM3 loader and the phone speech listener. The
  global BOARD is deleted.
- (owner, 2026-09-24) Step 7 done, file by file: the try blocks left are the ONE per failure domain
  in util/guarded.py (HTTP, JSON, filesystem, asyncio streams) plus fatal.py's crash-path catch
  (5 in total, was 22). No SystemExit / sys.exit in app code. Self-tests live in test files.
- (owner, 2026-09-24) "Check the agents' work again. Don't insist that you're done, actually
  properly check." A full read of every agent-touched file found what the diff review missed
  (show.py's sys.exit calls and stale message, cam_list's hardcoded size and stale up.sh name,
  box-drawing comments). Rule: re-check an agent's files by reading them WHOLE, not by its diff.
- OPEN for the owner: `_number_token` (stage 2) and `_is_number_he` (the number guard) differ on a
  digit glued to "and" ("ו5"); see the answer of 2026-09-24 in chat and the session log.
- OPEN for the owner: log/trace.py writes a second per-utterance record to <repo>/logs/traces
  (317 files) that no code reads; the session log's trace.jsonl holds the same data. Its docstring
  calls it "the owner's database (2026-09-02)". Keep or delete?

## Owner rulings 2026-09-24 (later)
- (owner) The status board: "the supervisor managing the status board is stupid ... Each service
  should report its own status with a function in its API, that way the StatusBoard can iterate
  through each service, grab its status and call it a day." DONE: every part with a row owns a
  Status and answers status() -> [(name, state, detail)]: each supervised Process handle, DjiApp,
  BackendLoader (sam3), Video, SpeechIn (its PhoneAsr; the ROS source has no row of its own).
  StatusBoard(sources) only asks; the app builds it once from [processes, dji, sam3, video,
  speech_in]. The supervisor writes no status except its processes' own rows (held by the handles).
- (owner) "ו5" is mostly a non-issue ("the vast majority of people never talk like this"); fix it if
  the patch does. DONE: numbers.meter_has_number: a number after מטר that starts with ו begins the
  next item (except וחצי); one rule for the rewrite and the number guard. Proven on all 305 bench
  sentences: none changes. FLAGGED, not changed: a leading ו-number word (וחמישה) is never turned
  into digits, so the number guard does not see it; fixing it changes Gemma's input (needs a bench
  re-measure).
- (owner) "Why is recognizer.py 800 something lines?" / "Why does pipeline.py look like shit?" DONE:
  recognizer/ split by job: parse.py (the front half), fast_path, bypass, guards, rewrites,
  numbers, lexicon, prompts; recognizer.py is the API class Recognizer (the module table's name;
  was Pipeline in pipeline.py). plan() is public (the benches measure it); the test hook plan2_fn
  is gone (tests pass a PlannerStub as Gemma).
- (owner) "Are you actually utilizing the utilities ... in EVERY SINGLE MODULE?" DONE, one home each:
  system/ros.Subscription (keys, asr_ros, ros_stream), util/mission.step_text (turns, score),
  log/session.latest_session (show, score), util/hebrew.HE / is_hebrew (rewrites, render),
  perception2/boxes.frame_area (vision, verify, engine), util/net.JSON_HEADERS (gemma, dji_app),
  test/support.wait_for (5 test files).
- (owner) "Are the connections correct, as we planned?" Checked by the real import graph: every
  cross-package edge is an allowed API name (recognizer -> control.outcome_text, perception2
  TASK_FULL, log.Trace; control -> dji_app HALT_MISSION). Fixed: the UI read control through the
  global S.control; it now gets a manual_on callback (S.control removed).
- OPEN for the owner (trace): log/trace.py (2026-09-02) writes logs/traces/session-<time>.jsonl per
  Recognizer; log/session.py (2026-09-12) writes the same utterance to <session>/trace.jsonl. Since
  2026-09-12 every live utterance is recorded twice; nothing reads logs/traces. The tests also wrote
  there (3 files per run): fixed, the tests now write to their tmp folder. Keep or delete trace.py?
- (owner, 2026-09-24) "Yes, delete trace.py." DONE: log/trace.py deleted; the Recognizer records
  only through the session log (kind, target, mission, action, timings). The old files in
  <repo>/logs/traces are the owner's to delete (gitignored data).
- (owner, 2026-09-25) The ggml mix: the owner rebuilds the whole project. "Only use the binaries from
  release/shared/dji, not from anywhere else." Already so: config.NATIVE_BIN_DIR is the one home;
  every native program starts from it and native_env() puts it first on LD_LIBRARY_PATH. Added:
  run.sh preflight now checks llama-server too, and fails when the libggml*.so.0 names point at
  more than one ggml version.
- (owner, 2026-09-25) No CMake install change now (one library folder per program): not the focus.
- (owner, 2026-09-25) Performance measurement APPROVED: always-on perf.jsonl in the session, a
  scripted run (fixed sentences on the ASR topic), and `run.sh perf` (p50/p95/max per stage).
  "ASR Time should be measured when we use ASR": the mic path is timed from the push-to-talk
  release to the transcript.
- (owner, 2026-09-25) run.sh preflight must be fast: no 5-10 s pause after the SAM3 model check.

## Owner rulings 2026-09-26

- (owner, 2026-09-23, recovered 2026-09-26) The full 2026-09-23 answer on the global C, M and Q:
  "Just don't use them in the app? Again, Use the fucking function keys lol". Only the first half
  reached this spec ("letters are ignored globally"), so quit and clear were never moved. On
  2026-09-26 the owner restated it: "the QWERTY keys that are common when typing could work against
  the tester if hes doing something in the background - research, etc... move Q and the other keys
  to other function keys". DONE 2026-09-26: every global action is a function key over the ROS2
  hook: F1 quit (far from F4 kill and F5 talk), F2 clear the highlight, F4 kill. Every letter does
  nothing over ROS (Q, C, M included). The window keys (q/Esc, c, t, x, [ ]) act only while the app
  window has the focus. (A Q-quits-globally version existed for ~1 hour on 2026-09-26; removed.)
- (owner, 2026-09-26) The whole-app test draws on the owner's display when a flag says so:
  HARDEN2_APP_TEST_SCREEN=1 -> DISPLAY (:0); otherwise a virtual screen (Xvfb). The quit key goes
  over ROS, so no window tool (xdotool) is needed.
- (agent decision, open to the owner) Step 8: every python package is REQUIRED, the laptop voice
  (phonikud) included: the install script installs them all. A phone-only run now imports phonikud
  too: +0.4 s at start (measured, 3 runs).
- (owner, 2026-09-26) Deleting benchmarks: A benchmark may be deleted only when ALL four hold (owner ruling 2026-09-26, for every
  benchmark, now and in the future):
    A. it is of no use to us anymore;
    B. it is documented in the git history (committed);
    C. its results were moved into a docs/research-complete-*.md document;
    D. it has not been touched since, and HISTORY.md documents it.
  Owner's words: "Those tests are not relevant, SO LONG THAT: A. Are not of use to us anymore
  B. ACTUALLY DOCUMENTED THEM IN THE GIT HISTORY C. We moved them to the docs/research-complete
  designation D. We haven't touched them since & have documented them in HISTORY.md. The
  following rules apply to all benchmarks we have currently and will create in the future(!)"
  Applied to compare_engines.py + run_indepth.py: A, B, D hold; C did not. Owner 2026-09-27: D2
  "Option A". DONE: docs/research-complete-sam3-vs-omdet.md (C now holds). The owner runs the rm.
- (owner, 2026-09-26) The API headers stay, for the owner to read the design: "Make sure you actually
  update the systems in the header files if you also update the python files, I don't want
  mismatch. If I have hard time reading your python, reading the C definition headers is what
  allows me to easily understand what you're trying to implement." DONE 2026-09-26: v2.4, six
  headers synced (app, log, system, gemma, audio, perception; perception.h had drifted since step 6).
- (owner, 2026-09-26) Keys: "Good Fix & Choice for keybindings" (F1 quit, F2 clear, F4 kill).
- (owner, 2026-09-26) Step 8: "As long as it works and doesn't take 10 years, I'm satisfied." Speech
  out: "We said that there is a flag to control phone/laptop/both/off, that is it." (TTS_OUTPUTS.)
- (owner, 2026-09-26) bench docs: "It is for you (MAINLY(!)), not me."
- (owner, 2026-09-27) The recognizer: "All of these should be at the least, separate functions that
  are chained together. One should make the decision, one should do the acting on said decision."
  OPEN: build it (Recognizer.route() decides and sends nothing; handle() = route + act).
- (owner, 2026-09-27) Terms module / service / system: verbatim in docs/guidelines.md "Terms".
- (owner, 2026-09-27) 9a-7: "Yes, close it." DONE.
- (owner, 2026-09-27) Window keys: "Why are the window keys still defined in ui.py even though we
  have config/* for this?" DONE: they, the window title and the HUD colours moved to config.
- (owner, 2026-09-27) The frame record: "Why does it only hold the mean....?" DONE: it keeps the
  worst read / draw / show and the longest frame gap per second.

## Owner rulings 2026-09-27 and 2026-09-28 (the "ironing" rounds; build plan in the handoff, section 9d)

Benchmarks
- D1 a: bench/whole-system is research-complete: its results go into a docs/research-complete-*.md
  document, then its scripts and run_all.sh are deleted under rule A-D.
- U2 (owner): merge unified_bench.py and run_list.py into ONE recognizer benchmark in
  bench/recognizer/ (Q1 b). Two input paths only: "A. Literally make json files out of
  cases_commands.py & perception, load the json files and iterate over all elements. B. ... the
  json input of a wav file, do a prepass on all voice recordings to turn them into transcriptions,
  then proceed almost identically as option A." A recordings file carries its expected values:
  "A recorded session should have an expected value." Plus an option to run one given file.
- U2.3 (owner): "Scorer: Should only be one. Definitely doesn't belong in log/*". "We never needed to
  benchmark a live session." -> log/score.py, `run.sh score` and run_list's --from-clips matching go.
- V3 (owner): the ~500 cases move to JSON as they are; no separate review of the expected values.
- The guards are part of the recognizer, so the recognizer benchmark measures them, through the
  recognizer's own decide function (D3); no copy of the routing in any benchmark.
- X1: the 138 perception sentences stay in the recognizer benchmark, graded on the kind and the
  target words. X2 + Y1: bench/vision-verify-bench measures ONLY the vision system ("NOT THE WHOLE
  SYSTEM NOR THE RECOGNIZER! ONLY THE VISION"), keeps its English input, is fixed (detect() returns
  (status, hits) since 2026-09-23) and moves to bench/perception/. X3: each benchmark has its own
  scorer ("SINCE WE ARE MEASURING DIFFERENT THINGS").
- Z1 a: a confirm tool for the 139 recordings in datasets/asr/ (propose the sentence and expected
  result from the nearest case, the owner listens and confirms); the result is the recordings file.
- Y2 b: no benchmark smoke tests; a change lists the benchmarks that call the changed module
  (guidelines, change-impact analysis), and those are checked by hand.
- U4 a: mutation checks only when a new test is written; not part of reviews.
- R6 + Q7: the test review = each module's purpose -> its real-world behaviours -> the test that
  proves each; coverage only to find never-run code ("Line Coverage Is a stupid metric"). Fuzzing later.

Perf (C.1 draft approved: "Draft Looks Great! No complaints from me.")
- Record every event, every frame included, into a memory buffer; a writer thread writes it every
  config.PERF_FLUSH_SECONDS (R7: "configurable inside the config folder, default to 5s"); die()
  flushes first. The report: n, min, P25, P50, P75, P95, P99, max per stage; V1 a: the 20 slowest
  frames with their times. Q3 a: GPU samples through pynvml (0.018 ms vs 22.8 ms for nvidia-smi).
  A "startup" stage per status row.

Start-up and services
- 3.3 (owner): "Everything, should it be necessary, be 'loaded eagerly' - I don't want load times to
  slip into the app runtime." D13/Q6: phonikud loads at start only when TTS_OUTPUTS has "laptop".
- Q5 a + 3.2.3: no dependency check in main.py; the preflight is its one place ("If a service
  crashes then we will run the preflight and understand why it happend"). deps tests 1 and 3 go.
- D15 a: the start-up builds every service through ONE function ("the app should simply call a
  single function that 'builds' all the services"); the supervisor keeps processes alive.
- U6 a: the phone-app check every 2 s; process restarts (mock, gstreamer) stay at 5 s.

Layout and terms
- SAM3 gets its own folder; keys -> keys/keys.py (R3 a); system/ -> runtime/ (R5); feed.py ->
  test/scripted_e2e_run.py (Q4); show, score, perf_report stay in log/ "for now" (R4) (score.py goes
  with U2.3); D8 a: the remaining drawing values (chat colours, pane layout, font paths) -> config.
- D6 a: the disk test goes through SessionLog; disk.py keeps its underscore names.
- Q9 a: the whole-app test is renamed test_app_end_to_end_over_ros.
- D14 via 1.8.2 ("I agree with everything said here"): docs and headers use the owner's terms:
  services first, then systems.

Recognizer numbers
- C.3 + Q8: all seven front letters (and, the, in, to, from, about, that), not only vav. R8/T5 a:
  measure Gemma and the guard on a sentence set with fractions and front letters first, then
  complete the tables (numbers, fractions incl. quarter, third, eighth, ...).

SAM3
- R9 + R10 + U5 a: a SAM3 assessment before any SAM3 change ("properly assess what we're going to
  do with SAM3, instead of hacking it around"): today's in-app design, its own process with a shared
  frame buffer (no 2.7 MB per request), phase 7 (SAM3.1, EOVSAM), and C.2 (558 vs ~400 ms).
- (owner, 2026-09-28) M2: the recognizer benchmark is bench/recognizer/accuracy.py.
- (owner, 2026-09-28) M3: "I meant what ROADMAP.md said": command->action latency < 1 s on the real link
  (docs/ROADMAP.md line 40). It gets its own perf stage "e2e" (F5 release or phone transcript -> the
  command reaches the phone app, or -> the first box drawn).
- (owner, 2026-09-28) M5: "This is not phase 2 work. This should be done." Path B of the recognizer
  benchmark also reports whisper's accuracy (its text vs the confirmed sentence, word error rate).
- (owner, 2026-09-28) M6: the keyboard hook's mouse-event log: "Fuck it for now". Dropped.
- (owner, 2026-09-28) M1: "Yes, check it". Measured: the preflight takes 2.1-2.3 s; the camera listing
  (video/cam_list.py) is 2.1 s of it; system.deps 37 ms; the binary path from config 27 ms. OPEN: the fix.

## Rulings recovered by the audit of 2026-09-28 (were only in the chat)
- (owner, 2026-09-26) "session.py looks good." log/session.py stays at 266 lines; the SessionLog split
  is closed, not open.
- (owner, 2026-09-26) "I never modified ste_check. That was you." A Claude session changed
  .claude/hooks/ste_check.py on 2026-09-19 (grade only the current reply) and never committed it.
  D12: the owner commits it with the rest (task F2).
- (owner, 2026-09-26) "I'll not commit this. We are not finished with some of the steps ... We'll
  finish them and commit." No commits until the task list is done (F2).
- (owner, 2026-09-27) C.2, SAM3 558 vs ~400 ms: "Good. Correct. If its not, then this is a cause for
  expanding investigations." If Gemma loaded-but-idle does not explain it, the SAM3 assessment (E2)
  widens the investigation.
- (owner, 2026-09-27) The recognizer benchmark's purpose: "This is literally just a benchmark of the
  recognizer as a function of the backend."
- (owner, 2026-09-27) C.4, why the keyboard hook reads the mouse: "the keyboard wasn't detected with
  the previous laptop, and with this device also, because the drivers report mouse events through the
  laptop keyboard, which then causes the 'device filter' function to not detect the laptop keyboard".
  M6 (2026-09-28): left as is; trim the logs by hand or with a tool later.
- (owner, 2026-09-27) R4: the three log readers stay in log/ "For now" (revisit later).

## Decision ledger 2026-09-26 .. 2026-09-28 (every question asked in the refactor rounds, one row each)

The ledger of the owner's answers to every question asked in the refactor rounds (question IDs
D, Q, R, T, U, V, W, X, Y, Z, M, P, and the numbered points of the 2026-09-26 debrief). Built from the
transcript on 2026-09-28 (every question ID checked by script). "Answer" is the owner's words. "Task" is the build task in the handoff,
section 9d. A later row supersedes an earlier one where it says so. New decisions: append a row.

### The debrief points (owner, 2026-09-26 and 2026-09-27)

| point | question | owner's answer | decision | task / state |
|---|---|---|---|---|
| 0.1 | how the test presses keys | "why reinvent the wheel ... YOU LITERALLY SEND AN EVENT THROUGH THE ROS NETWORK" (2026-09-26) | the test sends keys over ROS2 like the hook; no xdotool | done |
| 0.2 | where the whole-app test draws | "make this a flag - True means :0, false means whatever the hell you want" (2026-09-26) | HARDEN2_APP_TEST_SCREEN=1 -> your display; else Xvfb | done |
| 1.1 | run_list.py after step 11 | "Python Looks Phenomenal! Just please make the run_all.sh script readable too." | superseded by D1 a (run_all.sh goes) | B6 |
| 1.2 | bench docs | "Double check documentation. It is for you (MAINLY(!)), not me." | bench docs are written for the agent | F1 |
| 1.3 | testing run_list | "Test it fully." | done: text mode on Gemma 30/2/18; replay path runs | done (HISTORY 2026-09-26) |
| 1.4 | the two SAM3 scripts | rule A-D for every benchmark, now and future | A-D rule; applied, research-complete doc written, owner deleted both | done |
| 1.5 | the INTEGRATION-HANDOFF sed | "I see." (after the explanation) | no edit: it records 2026-09-03 | closed |
| 1.7 | guards in the bench | "The guards are a part of the recognizer, so they should be TESTED!" | the recognizer benchmark measures the guards through route() | A1, B1 |
| 1.8 | decide and act | "separate functions that are chained together. One should make the decision, one should do the acting" | route() decides, handle() = route + act | A1 |
| 1.8 | terms | module = a folder; service = a module others depend on; system = modules with one purpose | written in guidelines "Terms"; docs use "services, then systems" | F1 |
| 1.8.1 | one module, one folder | SAM3 "Yes, correct"; keyboard "Might need to move to a different folder with a single file"; system/ "Doesn't sound to me like system/* is the right word" | sam3/ own folder; keys/keys.py; system/ -> runtime/ | D1-D3 |
| 1.8.2 | the code in the owner's terms | "I agree with everything said here." | services: gemma, SAM3, dji_app, log, runtime; systems: recognizer, perception, flight, speech, screen | F1 |
| 1.10 | perf overhead / GPU sampling | "IT COSTS THAT MUCH FOR JUST MEASURING TIME?" | pynvml (Q3 a) | C1 |
| 2.1 | two mains in app/ | "If it for testing, shouldn't it be inside test/*?" / "Yes, I agree." | feed.py -> test/scripted_e2e_run.py | D4 |
| 2.3 | disk.py exposes internals | "Alright." then D6 "Option A" | the disk test goes through SessionLog | D6 |
| 2.4 | session.py | "session.py looks good." | 266 lines accepted; no SessionLog split | closed |
| 3.1 | dependency check speed | "As long as it works and doesn't take 10 years, I'm satisfied." | 0.008 s check kept | done |
| 3.2.3 | check in main.py | "This should not be part of main ... Don't increase the loading time of main.py" | no check in main; the preflight is its one place | C3 |
| 3.3 | start time | "Well fucking measure it?" | measured: 14-18.5 s to every row UP | done (HISTORY 2026-09-27) |
| 3.3 | loading | "Everything, should it be necessary, be 'loaded eagerly' - I don't want load times to slip into the app runtime." | load at start, never during a run | C3 |
| 4.1 | test list | "do you seriously expect me to read through the whole of your 217 test names?" | test review by behaviours (R6); test/README.md exists | E3 |
| 4.2 | run docs | "Good Work." | docs/spec-harden2-run-arguments.md | done |
| 5 | window keys | "Why are the window keys still defined in ui.py even though we have config/* for this?" | moved to config (with the title and HUD colours) | done |
| 5 | global keys | "Good Fix & Choice for keybindings" | F1 quit, F2 clear, F4 kill, F5 talk; letters never act over ROS | done |
| 6.2 | headers | "Make sure you actually update the systems in the header files if you also update the python files" | every API change updates its header in the same change | every task |
| B.1 | checks | "Double after we finish part A" | lint + suite twice after every task | every task |
| C.1 | frame record | "Why does it only hold the mean....?" then "Record everything and calculate metrics later! Keep P25, P50, P75, P95, P99, min & max." | the perf draft (approved) | C1 |
| C.2 | SAM3 558 ms | "Good. Correct. If its not, then this is a cause for expanding investigations." | measure alone / Gemma idle / Gemma busy; widen if needed | E2 |
| C.3 | front letters | "we should just convert the 'vav' to 'and'"; "What about 'ורבע'? What about 'ושמינית'?" | Q8: all seven letters; the fraction table | A2 |
| C.4 | keyboard hook log | the laptop keyboard reports mouse events, so the device filter cannot separate them; M6 "Fuck it for now" | left as is | closed |
| C.8 | 9a-7 | "Yes, close it." | closed; answer in guidelines "Terms" | done |
| C.9 | handoff ticks | "Well, what are you waiting for...?" | 9a-9, 9a-10, 9a-11 ticked | done |
| C.12 | ste_check.py | "I never modified ste_check. That was you." | a Claude session changed it (2026-09-19) | F2 (D12) |
| D | commits | "I'll not commit this. We are not finished ... We'll finish them and commit." | no commits until the list is done | F2 |

### The question IDs

| ID | question | owner's answer | decision | task / state |
|---|---|---|---|---|
| D1 | the whole-system bench | "I tend to agree with option A" / "I agree with A" | research-complete document, then its scripts and run_all.sh go | B6 |
| D2 | the two SAM3 scripts | "Option A" | research-complete-sam3-vs-omdet.md; owner deleted the scripts | done |
| D3 | routing copied in benches | "Already said my piece about this" (1.8) | route() / handle() | A1 |
| D4 | glossary | "A" | guidelines "Terms"; 9a-7 closed | done |
| D5 | feed.py | "option A" | test/, with a new name (Q4) | D4 |
| D6 | disk.py and its test | "Option A" | the test goes through SessionLog; underscores stay | D6 |
| D7 | deps tests | trace discussed; "your last answer is good" | test 1 and test 3 go, test 2 stays; no check in main | C3 |
| D8 | other drawing values | "option A" | chat colours, pane layout, font paths -> config | D5 |
| D9 | whole-app test name | -> Q9 "option A" | test_app_end_to_end_over_ros | D7 |
| D10 | window keys | (5) | moved to config | done |
| D11 | vav number word | "Already Addressed" -> Q8 | all seven front letters + fractions | A2 |
| D12 | ste_check.py | "Give commit" | the commit command given; the owner commits it | F2 |
| D13 | phonikud loading | "Yes!" / "Already Addressed this stupid narrative." | loaded at start only when TTS_OUTPUTS has "laptop" | C3 |
| D14 | our terms vs the owner's | "See my comments" -> 1.8.2 | docs and headers in the owner's terms | F1 |
| D15 | who builds the services | "You win." / "I agree with your proposal." + "the app should simply call a single function that 'builds' all the services" | the start-up builds them through ONE function; the supervisor keeps processes alive | C3 |
| Q1 | run_list's home | "option B" | bench/recognizer/ | B1 |
| Q2 | folders breaking one-folder | answered by 1.8.1 | see 1.8.1 | D1-D3 |
| Q3 | GPU sampling | "option A" | pynvml | C1 |
| Q4 | feed.py's name | "test/scripted_e2e_run" | test/scripted_e2e_run.py | D4 |
| Q5 | app.main without run.sh | "option A. If a service crashes then we will run the preflight" | no check when started directly | C3 |
| Q6 | phonikud by flag | "YES" | as D13 | C3 |
| Q7 | coverage report | "YES" + R6 | coverage only for never-run code | E3 |
| Q8 | which front letters | "ALL SEVEN! THIS WONT ARISE JUST WITH VAV!" | and, the, in, to, from, about, that | A2 |
| Q9 | whole-app test name | "option A" | test_app_end_to_end_over_ros | D7 |
| R1 | the benchmark's file name | "Not a good name, suggest another one." -> M2 "yes" | bench/recognizer/accuracy.py | B1 |
| R2 | unified_bench | "Do we even need the unified_bench?" -> U2 "Yes, Merge." | merged into accuracy.py | B1 |
| R3 | keys folder | "option a" | keys/keys.py | D3 |
| R4 | log readers | "For now, I agree." | show, perf_report stay in log/ (score.py goes, U2.3) | B1 |
| R5 | system/ name | "Agreed" | runtime/ | D1 |
| R6 | test review | "I agree with everything besides mutation checks"; fuzzing "not for now" | purpose -> behaviours -> tests; e2e | E3 |
| R7 | perf write interval | "Make this configurable inside the config folder, default to 5s." | PERF_FLUSH_SECONDS = 5 | C1 |
| R8 | fractions | "if there is no other way then we should add more"; "I agree with everything said here" | measure Gemma + guard first, then complete the tables | A2 |
| R9 | SAM3 "not good" | "You're right about both." | SAM3 failure ends the app; SAM3 lives in the app's process | E2 |
| R10 | three start-time findings | "you need to properly assess what we're going to do with SAM3, instead of hacking it around"; phone app: "Nothing to change ... reduce the interval from 5s to 2s" | torch -> SAM3 assessment; phonikud by flag; phone check 2 s | E2, C3 |
| T1 | slow-frame threshold | -> U1 -> V1 | see V1 | C1 |
| T2 | recognizer benchmarks | -> U2 "Yes, Merge." | merge | B1 |
| T3 | log readers | -> R4 | see R4 | — |
| T4 | mutation checks | -> U4 "Option A" | only when a new test is written | every new test |
| T5 | fractions | -> R8 | see R8 | A2 |
| T6 | SAM3 own process | "Agreed. Surely there is a way that we don't have to send 2.7MiB Per request" | assess the shared frame buffer | E2 |
| T7 | phone-app false WAITING | "Nothing to change, this behaviour is fine" + 2 s | U6 a | C3 |
| T8 | torch loading | -> R10 | part of the SAM3 assessment | E2 |
| T9 | done ironing? | -> U7 -> Z2 | see Z2 | — |
| U1 | slow-frame framing | "I don't understand the framing" -> explained -> V1 | see V1 | C1 |
| U2 | merge | "Yes, Merge." + "add an option to run a specific file of sentences" | accuracy.py with a file argument | B1 |
| U2.2 | inputs | "we should only have 2 ways to process inputs: A. ... json files ... B. ... json input of a wav file, do a prepass" + "A recorded session should have an expected value" | path A (sentences) and path B (WAV + expected) | B1, B2 |
| U2.3 | scorer | "Scorer: Should only be one. Definitely doesn't belong in log/*"; "We never needed to benchmark a live session." | one scorer in bench/recognizer/; log/score.py, run.sh score and --from-clips matching go | B1 |
| U4 | mutation checks | "Option A" | only for new tests | every new test |
| U5 | SAM3 assessment | "I agree with your assessment. Option A" | its own step before any SAM3 change | E2 |
| U6 | 2 s retry | "Option A" | phone check 2 s; process restarts 5 s | C3 |
| U7 | done ironing? | "We're just shy of this, yes." | -> Z2 | — |
| V1 | slow frames | "Option A" | the 20 slowest frames, no threshold | C1 |
| V2 | perception expected results | "Bad question. Lets discuss it properly." -> X1-X3 | see X1-X3 | — |
| V3 | review of expected values | "I was talking about my response at the start of the message." (U2.2) | converted to JSON as they are; no separate review | B1 |
| W1 | grading a live session | -> U2.3 "We never needed to benchmark a live session" | not done | B1 |
| W2 | perception JSON | -> X1-X3 | see X1 | B1 |
| W3 | review | -> V3 | see V3 | — |
| X1 | 138 perception sentences | "Yes" | stay in the recognizer benchmark: kind + target words | B1 |
| X2 | the vision benchmark | "Yes" + "we care about measuring the vision system, NOT THE WHOLE SYSTEM NOR THE RECOGNIZER" | English input kept; fixed; moved | B5 |
| X3 | scorers | "Yes, each benchmark has its own way of measuring" | one scorer per benchmark | B1, B5 |
| Y1 | vision bench home | "answered" | bench/perception/ | B5 |
| Y2 | silent benchmark breakage | "option B." | a change lists the benchmarks that call it; checked by hand | every task |
| Z1 | expected values for 139 recordings | "Option A." | the confirm tool; the owner labels | B3, B4 |
| Z2 | done ironing? | "I'm pretty sure. Do a pass" | the pass; this ledger | done |
| M1 | preflight speed | "Yes, check it" | measured: camera listing 2.1 of 2.2 s | C4 (P1) |
| M2 | benchmark name | "yes" | accuracy.py | B1 |
| M3 | <1 s e2e | "I meant what ROADMAP.md said." | the "e2e" perf stage (command -> action) | C2 |
| M4 | build order | "We already discussed them and finalized" | every decision is in this ledger and 9d | done |
| M5 | whisper accuracy | "This is not phase 2 work. This should be done." | path B reports the word error rate | B2 |
| M6 | keyboard log | "Fuck it for now" | left as is | closed |
| M7 | ste_check commit | "Ok." | in F2 | F2 |
| P1 | preflight camera listing | "option A" (2026-09-28) | the preflight checks only the selected camera (WEBCAM_DEV); the full list moves to `run.sh status` | C4 |
| P2 | wave-1 split | "Use 4 sub agents running Opus 5.5 On Medium. Divide them as you wish. Make sure that every agent checks the resources its trying to access ... Have the agents maintain a LOCK.md file for each file/resource that they're using. The top of the file should contain the contention status of the document - LOCKED ... FREE ... Each agent should: Check status of LOCK.md; Try to lock the files/resources it needs; If succeeds, it continues his work => When Finished, it unlocks ...; Otherwise, it waits or tries to start other work" (2026-09-28) | 4 agents, Opus 5.5, medium effort; the LOCK.md protocol (design: handoff 9e) | 9e |
| P3 | the stale handoff documents | "I asked about this right now. Answer my question." (the order and relevance of the documents) | answered; the order recorded in HISTORY 2026-09-28 "the handoff documents, oldest to newest" | done |
| L1 | atomic LOCK.md changes | "Agreed" (2026-09-28) | tools/lock.sh acquire / release / status, under flock | 9e |
| L2 | where LOCK.md lives | "Yes" | /root/groundstation/LOCK.md, in .gitignore | 9e |
| L3 | parallel test runs | "Sure." | each agent its own ROS_DOMAIN_ID | 9e |
| L4 | a dead agent's lock | "Yes" + "Make sure to have every subagent document his work in docs/refactor/subagent_id_doc.md, these would effectively be handoff documents for each subagent - at the bottom of their docs they'd update their progress ... Once they're finished, you'll double verify their progress reports vs the task-list you gave them in the handoff at the top. And for a final check, you'd actually check the files that they modified/wrote-to ... This gives us triple coverage for every subagent" | the main agent clears it after confirming the agent is gone; every agent keeps docs/refactor/<agent-id>_doc.md; triple coverage | 9e |
| G1 | the rest of bench/hebrew-command-bench after B1 (bench.py, the typing and contention scripts, perf.py, cases_typing_fresh*.py) | "tell me what is the purpose of each file. If they already served their purpose and are not used, then they can be safely ignored ... Otherwise, tell me what is wrong." (2026-09-28) | the typing study's scripts served their purpose (docs/research-2026-09-18-command-typing-fast-vs-gemma.md; decision 2026-09-19) and nothing uses them: ignored. What is wrong: see G2 | B1 |
| G2 | the ignored scripts break under D1/D2/B1; contention.py + real_cadence.py measure SAM3 + Gemma sharing the GPU (E2's question) | "Option A!" (2026-09-28) | retire under A-D: the study doc becomes docs/research-complete-2026-09-18-command-typing.md with no banned word (C); HISTORY holds it (D); then delete type_compare.py, type_fresh.py, type_english.py, perf.py, cases_typing_fresh*.py, and bench.py after B1. contention.py + real_cadence.py go to E2 (reuse or replace, then retire) | B7, E2 |
| K1 | the agents' model and effort | "Why do you ask this of me? You launch the subagents, not me. You should have a way to control the specific agent that you launch, i.e. giving the specific subagent type (for instance, claude-opus-4-8) alongside the effort. Am I wrong here?" (2026-09-28) | the main agent decides. The Agent tool sets the model per call ("opus" = claude-opus-5-5, checked in the Claude Code 2.1.280 binary) but takes no effort; effort comes only from an agent definition's `effort:` field. So the main agent writes .claude/agents/harden2-agent.md (model opus, effort medium), launches every agent with that type, and each agent writes its model and $CLAUDE_EFFORT at the top of its progress | S0 |
| K2 | one shared working tree (a half-written file can fail another agent's suite run) | "What can be in parallel, should be done in parallel. Otherwise, option C. i don't mind waiting." (2026-09-28) | tasks on different files and resources run in parallel (the waves in 9d); a task that shares a file or a resource waits for its lock, one at a time; the full suite is the lock "suite"; an agent never fixes a failure in another agent's files: it notes it and reruns after that agent's checkpoint; the main agent's validation run decides. Worktrees stay out: the tool would make git writes | 9e |
| K3 | a safety copy before the agents | "Lets commit now, and also make an archive inside /root/groundstation. I'd move it outside the container just incase." (2026-09-28; replaces "I'll not commit this" of 2026-09-26) | the main agent made backups/harden2-2026-09-28-before-agents.tar.gz (.git + every tracked and untracked file; git-ignored files excluded); /backups/ and /LOCK.md are in .gitignore; the owner commits the 55 paths (the main agent suggests the commands, runs no git write). /root/groundstation is the host folder /home/swapgs/workspaces/groundstation | S0 |
| — | start | "do not start yet, we're not done ... thoroughly prepare for that [compaction]" (2026-09-28) | nothing is built until the owner says start | — |
