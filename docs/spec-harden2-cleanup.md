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
