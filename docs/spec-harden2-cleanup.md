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
- Every system gets a proper interface (an API). The UI too. Draft: docs/draft-harden2-app-api.h (not ruled yet).
- Rename DjiWire / control/dji_wire.py: "wire" is a banned word, identifiers included. New name: open.
- ONE transmit switch. The drone link sends every command laptop -> phone, so it owns an enable/disable
  switch in its API. The main app is the one caller. Replaces KillSwitch.MOTION + pipeline.flight_allowed.
- Recovery: the supervisor supervises EVERY system, the phone TTS included. No per-system retry loops.
- Drone link recovery: open; the owner asked where in the chain it can recover.
- Files: small and modular, each one does one small job or manages one system (KISS).
  If mvd.py stays too big, make an app/ (or main/) folder.
- Display loop: measure first. Camera redraws every frame; chat updates only on new text; status is
  monitored, not necessarily redrawn.
- Benches: each one is documented in docs/HISTORY.md in time order: why it ran, the result, the verdict.
- Dependencies: one file checks every dependency at start-up (replaces the scattered find_spec guards
  and the pipeline flat-import try).
- SAM3 tasks (owner design, restated): a dispatcher thread on a condition variable spawns one thread per
  task, max 8. Count is fire and forget. A highlight thread lives until clear or give-up. Only the SAM3
  forward is serialized. The single-consumer build did NOT follow this design.
