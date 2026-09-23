# Handoff — harden2 exception + structure refactor (started 2026-09-21)

## 1. Context for you (the agent)

You are continuing a code-quality refactor of `projects/integration_harden2`, a Hebrew voice-drone system.
Read this file, then `docs/spec-harden2-cleanup.md` (the law), then run the test suite once to confirm green.

How to work here, learned the hard way:
- ADHERE to the owner's per-item notes LITERALLY. When he wrote "NO TRY CATCH", it means zero try; use a
  non-throwing check (importlib.util.find_spec, shutil.which, os.path.exists) or let it propagate. Do NOT
  soften his rule into "a narrow catch is fine" -- that caused repeated friction.
- Import AND run the full test suite after EVERY file, not in batches. A module-level die() at import once
  crashed pytest silently and was caught late.
- Do not substitute your judgment for an explicit instruction. If two of his instructions conflict, surface
  the conflict; do not pick one silently.
- The owner is a strong systems programmer who audits replies per-item. One idea per bullet. Answer every
  point by number. Recommendations are not decisions.

## 2. Needed context (repo-wide, from CLAUDE.md and prior handoffs)

- DRONE SAFETY: never send arm/takeoff/land/stick/motor commands to a REAL drone. Control tools run only
  against the mock (127.0.0.1). Prepare real-drone commands for the human to run.
- GIT: the HUMAN owns every git write. Prepare commands in the house style; never run add/commit/push. No
  force-push, no history rewrite, ever.
- Use the RTK wrappers via Bash: `rtk read`, `rtk grep`, `rtk ls`, `rtk git <read-only>`. Not native Read/Grep.
- Exception rule (house): no exceptions in our own code. die() (fatal.py) on a fatal invariant. Status/error
  codes otherwise. try/except only to wrap a third-party call that throws, converting it to a status.
- perception2 supersedes perception (decided). projects/integration_tts is FROZEN.
- Test: `cd projects/integration_harden2 && MVD_HOME=integration_harden2 MVD_TRANSLATOR=none python3 -m pytest test/ -q`  (132 pass on 2026-09-22).
- Decisions go into repo docs immediately; chat is lost to compaction.

## 3. Context for these jobs (the refactor)

The five principles (owner-approved 2026-09-21), applied to EVERY file:
1. Invalid config or input -> die(). No silent degrade.
2. A missing required connection/resource -> die() at startup, not on first use. EXCEPTION: the drone link
   flags + reconnects, it does not die (see the drone ruling in the cleanup doc).
3. Prefer a proper library over a hand-rolled subprocess/CLI.
4. Choose dispatch once at construction. No branching in a hot loop.
5. Wrap an unavoidable third-party throw, but die on a SEVERE error, or handle it properly (status + flag +
   reconnect for the drone link). Never swallow to a quiet return.

Authoritative docs: `docs/spec-harden2-cleanup.md` (per-file plan + principles + drone ruling),
`docs/spec-perception2-backend-contract.md` (detect -> (status, hits)), `docs/review-harden2-thermonuclear-2026-09-21.md`
(the 52-finding review), `docs/audit-harden2-exceptions-2026-09-20.md` (the exception inventory).

## 4. Work checklist (rewritten 2026-09-22; self-tested against the code the same day)

The owner audits this list. Keep it CURRENT: tick an item only after a check proves it. Rulings in full:
docs/spec-harden2-cleanup.md (last sections). Suite: `test/` = 185 pass. Exceptions: tools/audit_exceptions.py.

### 4a. Rulings in force (owner, 2026-09-21/22)
- Five principles: invalid config/input -> die; missing required resource -> die at start (the drone link
  flags + reconnects instead); prefer a library to a hand-rolled CLI; choose dispatch once; wrap an
  unavoidable third-party throw, die on a severe error, never swallow to a quiet return.
- SAM3 = producer/consumer: ONE consumer thread (perception2/task_queue.py) makes every SAM3 call and writes
  highlight state. COUNT = one-shot task; HIGHLIGHT = gate, then a persistent record re-detected in budget
  until the 8 s give-up or CLEAR; CLEAR goes through the queue. Task cap VISION_MAX_TASKS = 8, a constant.
- SAM3 alone ~2.4 forwards/s; threads and batching give no gain (bench/sam3-concurrency-bench). ~2/s is
  enough for now. A GPU out-of-memory calls die(). detect -> (status, hits), DETECT_OK / DETECT_NOT_READY.
- gemma/ keeps Gemma alive + gives ONE interface (request -> (True, text) | (False, "")). No task code in it:
  the recognizer's planning and perception2's vision prompts stay with them (so vlm_client stays in perception2).
- THE APP STARTS EVERYTHING through ONE generic supervisor (3 restarts, then die with the reason). Every
  package starts its processes the SAME way: start_services(supervisor, log_dir[, source]). No unused abstractions.
- SYSTEM STATUS pane for every subsystem: green UP, red otherwise with state + detail. No ad-hoc chat errors.
- Layout: camera full width on top; below it status | chat; the chat scrolls.
- Tests: ONE test file per package (audio, control, gemma, perception2, recognizer, system, video) + one per
  root module (mvd, overlay, session_log). config has no tests. Each file must test ALL cases of its package.
- Git: the owner commits everything ONCE, after the cleanup is done and the webcam mock run works, just
  before the field test and freeze. Do not suggest commits before then.
- Global phase 7, after the webcam mock test: make SAM3.1 work and experiment with EOVSAM, both quantized.

### 4b. DONE (each verified by the 2026-09-22 self-test)
- [x] Phase 1 tts_io: one-slot mailbox + event (no poll, no queue); die on an invalid backend and on an
      unreachable phone; speak function chosen once; sounddevice, not aplay.
- [x] Phase 2 exception cleanup: phone_asr, ros2_asr, cam_list, config/defaults, dji_wire (die on a real host
      without allow_real; HTTP error -> code; unreachable -> 0), camera_stream, overlay, pipeline.
- [x] Review findings: SAM3 lock; docstrings before imports; shebangs on line 1; kill.py one-liners; install
      script (sounddevice + libportaudio2); tools/audit_exceptions.py (re-added 2026-09-22; the container wipes it).
- [x] Phase 3.0 concept.py dead VLM subsystem deleted.
- [x] Phase 3.1 text parsers -> perception2/text_parse.py.
- [x] Phase 3.2 engine -> perception2/engine.py; detect -> (status, hits) end to end (backend, mvd, engine,
      verify, 5 benches); GPU OOM -> die.
- [x] Phase 3.3 producer/consumer SAM3 (task_queue + mvd gate/count/clear/refresh as tasks).
- [x] Phase 3.4a Eyes (detectors.py), mvd.worker(), the background path deleted.
- [x] S1 system/status.py  S2 system/supervisor.py (+ deliberate restart)  S3 fatal.on_die cleanups.
- [x] S4/S5 gemma/server.py + gemma/client.py. recognizer/llama.py and run_llama_server.sh deleted.
- [x] S6 pipeline + vlm_client use gemma.client; a failed Gemma call is 'gemma-failed', not a user reject.
- [x] S7 the app starts Gemma, ASR, keys, gstreamer (dji), mock (mock mode); run.sh starts only the app and
      its panes tail <session>/proc-<name>.log. video_watchdog process -> StallGuard. Real run: all UP -> DOWN.
- [x] S8/S8b status pane; camera on top, status | chat below, chat scrolls (wheel, [ ]); shown while waiting.
- [x] Tests: 10 files (one per package / root module); 132 pass. Retired test files deleted.

### 4c. REMAINING (in order)
- [x] CODE-REVIEW FINDINGS (code-review skill, 2026-09-22; R10 still OPEN) -- fix first, most severe first:
  - [x] R1 (fixed: dji_wire.sent(code); kill/router/pipeline say FAILED + 'take over with the RC'; 3 tests) SAFETY kill.py: wire.stop() now returns 0 when unreachable, but kill() still says "Motion stopped".
        Report the real result; unreachable = KILL FAILED + use the RC / power button. Same for the pipeline halt.
  - [x] R2 (fixed: strict dotted-IPv4 127.x parse; adversarial test) SAFETY dji_wire._is_loopback accepts any host starting "127." (e.g. "127.drone.lan"). Accept only
        localhost / ::1 / a dotted IPv4 127.x.x.x, parsed without a throw.
  - [x] R3 (fixed: run.sh exports PHONE_IP only in real mode) gstreamer gets config.PHONE_IP, but run.sh exports PHONE_IP=127.0.0.1 in mock mode: dji+mock video
        breaks. PHONE_IP must mean the phone; export it only in real mode.
  - [x] R4 (fixed: die(); proven: child stopped + DOWN) main() returns when the source never opens: every supervised child is orphaned. The source is
        required at start: die() (which stops the children).
  - [x] R5 (fixed: fatal.install_crash_hooks + asyncio_crash_handler; test) an uncaught exception kills a thread silently (the SAM3 consumer -> every later task queued forever).
        Crash hooks: any uncaught thread / asyncio exception -> die() with the trace.
  - [x] R6 (fixed: typed walk of the reply, no KeyError path; 5 bad-reply tests) gemma.client lets a malformed 200 body escape (JSON, IncompleteRead, missing keys, null content):
        all are a failed request -> (False, "").
  - [x] R7 (fixed: safe-parse, dropped/short reads end one connection; real-socket test) phone_asr: a malformed JSON line or a short HTTP body kills that connection's handler. Safe-parse the
        line (skip it, logged); end the one connection on a short read.
  - [x] R8 (fixed: cache removed; 2 tests changed with the behavior) mvd's phrase-throttle cache makes count frames 2 and 3 reuse frame 1 (median of one frame). The
        queue now paces the refresh by itself: remove the throttle (its 2 tests change: behavior changed).
  - [x] R9 (fixed: config SESSIONS_ROOT was one level short; SessionLog uses config.SESSION_DIR) ASR records to config.CLIPS_DIR but SessionLog picks its own dir when MVD_SESSION_DIR is unset.
        One home: SessionLog uses config.SESSION_DIR / config.CLIPS_DIR.
  - [x] SECOND code-review pass (2026-09-22, on the R1-R9 fixes):
  - [x] R11 (fixed: HTTPException -> UNREACHABLE, no e.read(); real garbage-server test) dji_wire._request lets http.client.HTTPException (and e.read() in the HTTPError branch) escape;
        with the R5 hooks a malformed phone reply during a KILL would die(). Convert every one to a status.
  - [x] R12 (fixed: ValueError + reset end one connection; 70 KiB real-socket test) phone_asr: a line over 64 KiB (ValueError) or a reset before drain() escapes -> die. End that one
        connection instead (untrusted input).
  - [x] R13 (fixed: sent(); FAILED-HTTP-<code>; test) pipeline._fly reads any status except 409/0 as "flown" (a 400/500 looks like success). Use sent().
  - [x] R14 (fixed; test: meta.json written) session_log meta.json: the R9 edit left `host` undefined; a broad except hid the NameError.
  - [x] R15 (fixed: default_gateway(); _default_route_ip deleted) config.PHONE_IP falls back to the FIRST default route (any interface); use the wireless-aware
        default_gateway() (one home for the lookup).
  - [x] R16 (fixed: launch + register + stopping check in one lock; test) supervisor: a watcher can relaunch a child after stop_all took its snapshot -> an orphan.
  - [x] R17 (fixed: run-once lock, each cleanup guarded, always os._exit; test) die(): a cleanup that throws never reaches os._exit; no guard against two threads dying at once.
  - [x] R18 (fixed: reads <session>/proc-*.log via app.sh; video from [status] lines) run.sh status still reads the old pane logs (asr.log, dog.log, run_dir mock log).
  - [x] R19 (fixed: dji_wire.LATCHED; 'refused: the kill latch is on'; test) the kill latch's 409 reads as "did NOT reach the aircraft -- take over": a false alarm. Say the
        latch refused it (press M to re-arm).
  - [x] R20 NOT A BUG (owner ruling, cleanup spec): a taken phone-ASR port die()s at start-up. Kept.
  - [x] R10 (fixed: tts _post + recovery loop; real-HTTP tests: recovers, and dies after the budget) RULED 2026-09-22: the phone TTS RECOVERS like every service (RECOVERING, retry up to
        SUPERVISOR_MAX_RESTARTS, then FAILED + die). Was: tts _say_phone die()s on ONE 3 s timeout -> kills the UI + the M kill switch
        while a mission flies. Recommendation: report tts RECOVERING/FAILED on the status pane instead.
- [x] S9 every system reports: gemma sam3 asr keys mock gstreamer video tts 'drone link' 'phone speech'
      (the drone link turns red on no answer and never dies; its reconnect is the resilience task).
- [x] Phase 3 step 5 (2026-09-22): perception/ deleted. overlays.py + vlm_compare.py repointed to perception2;
      run_list.py's import repointed. README package table rewritten to the current layout.
- [x] A flaky test exposed a race in the R17 die(): a second die() exited before the first ran its
      cleanups. Now it waits for the first. 25/25 runs of the die tests pass.
- [x] Tests for ALL cases, first pass (2026-09-22): a gap check (public names vs their package test) found
      59 of 163 names untested; tests added for the wire verbs + from_env + the real-host die, the recognizer
      helpers + Trace, open_capture + CameraStream frame handling, mvd helpers, overlay, reject_why,
      apply_masks, ascii_only. The mouse-wheel test caught a REAL bug: cv2 4.11 has no getMouseWheelDelta, so
      the first scroll would have crashed the app. Fixed. 174 pass. Still untested by design: the GPU
      Sam3Backend (its bench + the real smoke cover it) and mvd.main/teardown (the webcam mock test covers them).
- [x] Phase 4 mvd.py (2026-09-22): 11 catches -> 0 (setup_drone_router built explicitly; a SAM3 load
      failure now dies via the crash hook instead of running without highlights; count/gate/verify/say/ears
      catches removed). ROS guard = find_spec. Imports at the top; the ONE lazy import left is tts_io (it
      loads the offline-TTS stack). Dead code removed: px/vlm_box plumbing, the `english` key, cap_raw/
      cap_kept, json/textwrap. 0 semicolons, 0 inline bodies. 174 pass.
- [x] Phase 5 session_log.py rewrite (2026-09-22): 7 broad catches -> 4 narrow OSError at filesystem calls.
      Every write returns a status; a failed write turns the `recording` row red, the next good one green.
      One lock, over in-memory state + the one trace append only. end_request keeps the request in memory
      (no leaky re-read). SessionLog.current() replaces mvd's reach into the private _tl. trace.py: the same
      status policy. All 174 existing tests passed unchanged; 4 new tests. 178 pass.
- [x] THIRD code-review pass (2026-09-22, on phases 4-5 + recovery):
  - [x] R21 (fixed: queue + one delivery thread; the test FAILS on the old code, passes on the new) SAFETY phone_asr runs on_text INSIDE the asyncio loop: a ~3 s Gemma plan blocks it, the duplicate
        REST/TCP copy is read after the 1.5 s dedup window, and the mission is flown TWICE. Dedup at receipt;
        deliver on one consumer thread (order kept, loop never blocked).
  - [x] R22 (fixed: _vision_not_ready; test) _gate_task ignores the detect status: SAM3 still loading reads as "absent" and clears a live highlight.
  - [x] R23 (fixed; same test) _count_task with every frame failed reports and speaks 0 and clears the highlight.
  - [x] R24 (fixed: no try/finally; teardown only on a normal quit) main's try/finally: teardown's os._exit(0) swallows a display-loop crash (no die, exit 0).
  - [x] R25 (fixed: TaskQueue.submit(capped=False) for a continuation; test) a highlight refresh refused by a FULL queue ends the refresh loop silently (frozen boxes). A refresh
        continues an existing task: it must never be refused by the cap.
  - [x] R26 (fixed: vision/describe slots; test) SessionLog has ONE open request shared by the SAM3 thread and the Gemma thread: they close and
        write into each other's requests. Separate slots: vision vs describe.
  - [x] R27 (fixed: source travels with the transcript; mic-only claim under the lock; 2 tests) _claim_clip: a phone transcript (no audio) steals the mic's clip; two begin() calls race outside
        the lock. Claim only for mic utterances, under the lock.
  - [x] R28 (fixed: non-2xx = failed; retries speak the newest; test) tts: an HTTP error status (500) reads as delivered; recovery replays the stale text while a newer
        answer waits. Non-2xx = a failed delivery; each retry speaks the newest text.
  - [x] R29 (fixed) run.sh status: the router grep uses ERE with BRE escapes and never matches.
  - [x] R30 (fixed: docstrings aligned; dead fallback removed) start_session_log now die()s on an unwritable session dir (principle 2: the recording is
        required at start-up) but the session_log docstring says it never crashes; the SESSION-None
        fallback for log_dir is dead. Align the words; keep the die at start-up.
- [x] Simplify-skill pass (2026-09-22; 4 parallel reviewers: reuse, simplification, efficiency, altitude).
      APPLIED (behavior-preserving; 185 pass): 13 dead config names removed (8 aliases incl. LLAMA_URL, the
      offline flags, font resolver, chat colours); dead params (die trace=, begin_request he2=, det_payload
      extras, submit_vision options); dji_wire _post/_post_json wrappers; KillSwitch.REFUSED -> LATCHED;
      status.fail() = FAILED + die in one call (5 sites); supervisor.port_open = the ONE port probe (tts,
      mock); tts on urllib (one HTTP library; requests no longer used by the app); the task cap counts only
      commands (no capped= flag); camera_stream.source_kind = the ONE source classifier; StallGuard without
      redundant state; _snapshot_frame (5 copies -> 1, copy outside the lock); one lock block per frame; fps
      a local; unreachable Voice "off" path; np.frombuffer without an extra copy; clips glob audio_*.wav.
      SKIPPED, need the owner (4d): see the simplify items there.
- [ ] Webcam mock test with the REAL app (the run skill / run.sh up webcam mock); checklist in section 8.
- [ ] Stale-doc sweep (list in section 8b): harden2 README beyond the table, spec-harden2-architecture.md,
      perception2/README.md "Tests", tools/prewarm_llama.sh.
- [ ] Ask the owner every 4d item + the 8b first-audit leftovers; record each ruling in the docs at once.
- [ ] Apply the rulings, one more code-review pass, then prepare (never run) the owner's ONE commit (8b).

### 4d. OPEN (owner to rule)
- Simplify-pass items that change behavior or design (skipped, not argued):
  - One `dji_wire.outcome(action, code)` for the 4 places that word a wire status (router, pipeline x2, kill).
    Changes chat/log wording.
  - One motion gate inside DjiWire (kill latch + manual mode) instead of KillSwitch's verb list + the
    pipeline's flight_allowed.
  - A shared `system.Recovery` policy for the supervisor, TTS and (later) the drone link.
  - A `perception2.VisionService` owning the queue, backend and highlight state (would take mvd to ~500 lines).
  - Display-loop efficiency (MEASURE first): block on a new ROS frame instead of re-rendering the last one;
    cache the chat/status panes by a version counter; blend masks in place; fewer full-frame copies;
    move pass-file I/O off the SAM3 thread (or drop fsync for replay files).
  - mvd's module-level config aliases and one-key dict globals (tests patch them; churn only).
  - LlamaServer (bench launcher) duplicates the supervisor's start/wait/stop.
- mvd.py is 769 lines (guideline ceiling ~400). Split TextHandler + its task bodies into their own module?
  - OWNER RULING 2026-09-23: if mvd.py is too big, make an app/ (or main/) folder and move mvd.py's parts there.
    The owner reviews every touched file by hand first (list given in chat 2026-09-23); wait for that review.
- Three benches were ALREADY dead before this refactor. Delete them? bench/sam3-mask-bench/compare_engines.py
  (calls perception2.build_engine, removed 2026-09-11, and OmDet), bench/sam3-mask-bench/run_indepth.py
  (OmDet), bench/whole-system/run_list.py (QWEN3VL_EXTRA / MODELS["qwen3vl"], removed 2026-09-19).
- Refresh period: count from the task START for a true 1 Hz (today ~0.7 Hz)?
- Count frames as delayed tasks instead of sleeping 0.6 s on the SAM3 consumer?
- recognizer/pipeline.py keeps a package-vs-flat import try (the bench runs it flat). Remove it?
- The camera_stream / ros2_asr teardown catches are broad "log, do not swallow" (owner-sanctioned). Keep?

## 5. Updates from me (nuances you will not get from the docs)

- LAZY imports are legitimate where a module top import would load a heavy/optional dep for everyone:
  config.resolve_device's `import torch`; tts_io's `import sounddevice` (native PortAudio, phonikud-only);
  the phonikud packages (module-level find_spec guard). Keep these lazy; flag, do not blindly hoist.
- sam3_backend's `compile` param shadows the builtin, BUT bench/sam3-mask-bench/quant_bench.py passes
  `compile=`, so a rename must update that bench too. Left intentionally.
- SUPERSEDED 2026-09-22 (R10): _say_phone no longer dies on the first failure. It RECOVERS like every service
  (RECOVERING, 3 tries speaking the newest text, then status.fail). The drone link never dies: today it only
  turns its row red; the bounded reconnect is the later drone-link resilience task. Do not make it die.
- SUPERSEDED 2026-09-22: TTS uses urllib now (one HTTP library in the app); requests is no longer used by the
  app. sounddevice (not aplay) stays: Popen.communicate() handled a killed pipe with no exception (verified).
- The pipeline dual package/flat import (recognizer/pipeline.py) is kept for dual-mode execution (bench runs it
  flat). OPEN in 4d; confirm with the owner before removing it.
- config/__init__.py has SCENE_VERIFY flipped to ON (a separate 2026-09-20 feature, not this refactor).

## 6. Git

The owner runs every git write, ONCE, after the cleanup and the webcam mock run (ruling in 4a). No commit
commands are prepared before then.

## 7. After the cleanup/rewrite — the broader roadmap (what you work on next, with the owner)

This refactor is one step inside the harden2 freeze arc (docs/task-scheduled-harden2-field-test-and-freeze.md).
When the cleanup (phases 3-5) and the review findings are done and green, the next steps, in order:

0. The webcam mock test, then global phase 7 (SAM3.1 + EOVSAM, quantized), then the owner's one commit.
1. Outdoor FIELD TEST on the real drone. The owner runs it, aircraft secured; the assistant never fires motor
   commands. Field-test commands live in docs/task-active-restructure-progress.md ("Field test" block):
   run.sh preflight dji -> run.sh up dji real, PHONE_IP = the WiFi gateway.
2. FREEZE the tested commit as the baseline: a git tag on the exact commit that passed the field test.
3. POST-FREEZE benches (run on the frozen system, not before): tools/power_profile.py for the laptop field
   draw + a one-shot resource snapshot (GPU mem/util, CPU %, RAM, with TTS active); then whisper-noise and
   SAM3 low-light benches. See the freeze-arc doc and the power_profile notes.
4. DRONE-LINK RESILIENCE feature (its own task): keep-alive Noop + bounded reconnect from the cleanup doc's
   drone ruling. (Its diagnostic window is now the general status pane, built in S8.)
5. FUSE perception2 into llm_to_action (the C++ embedded system, the global objective): the Python perception
   here is the prototype; the real system is C++ (projects/llm_to_action). Port the SAM3 backend behind its
   C header contract; depth-anything.cpp is the related C++ depth path. This is the "feature-total-integration"
   goal -- the backpack/embedded target measures Wh/flight, not just latency.

Invariants for all of the above: temperature 0, one model on the GPU at a time, full bench tables, the owner
runs every boot and every git write. perception2 supersedes perception; projects/integration_tts is FROZEN.


## 8. SESSION DUMP 2026-09-22/23 (review-2 agent, Opus) -- RESUME HERE

Read section 4 first (4a rulings, 4b done, 4c remaining, 4d open). This section adds what 4 does not say.

### State at hand-off
- Suite: `cd /root/groundstation/projects/integration_harden2 && MVD_HOME=integration_harden2 MVD_TRANSLATOR=none python3 -m pytest test/ -q` = 185 pass (run twice, stable).
- Exceptions: `python3 /root/groundstation/tools/audit_exceptions.py /root/groundstation/projects/integration_harden2`
  (the tool is re-added; the container wipes it). Only narrow third-party catches remain, plus the sanctioned
  "log, do not swallow" rclpy teardown catches in video/camera_stream.py and audio/ros2_asr.py.
- NOTHING is committed. Owner ruling: ONE commit by the owner after the cleanup + a working webcam mock run.
- Packages now: audio, config, control, gemma (new), perception2, recognizer, system (new), video. perception/ is DELETED.
- Tests: one file per package + test_mvd, test_overlay, test_session_log (10 files).

### Architecture as built this session
- system/status.py: BOARD.report(system, state, detail); states STARTING UP RECOVERING FAILED DOWN; fail(system,
  detail, message) = FAILED + die. overlay.render_status draws it; layout = camera on top, status | chat below.
- system/supervisor.py: generic; start(name, argv, env, ready, ready_timeout_s, log_path); proc.wait (no poll);
  3 restarts (config SUPERVISOR_MAX_RESTARTS) then fail(); restart(name, reason) = deliberate, not counted;
  port_open(); native_env(). fatal.on_die(stop_all) + install_crash_hooks (any uncaught thread/main/asyncio
  exception -> die). die() runs cleanups once; a 2nd die waits.
- Every package starts its processes the same way: <pkg>.start_services(supervisor, log_dir[, source]):
  gemma/server.py (Gemma), audio/ros2_asr.py (ASR server + keyboard hook), video/camera_stream.py (gstreamer,
  dji only), control/dji_wire.py (mock, mock mode only). Logs: <session>/proc-<name>.log. run.sh starts only the
  app; its tmux panes tail those logs. The video_watchdog PROCESS is gone -> camera_stream.StallGuard.
- gemma/client.request(messages, grammar, max_tokens, timeout_s, port) -> (True, text) | (False, "").
  Pipeline: a failed call = action "gemma-failed" (never the "I did not understand" reject).
  vlm_client.ask -> (status, reply); presence gate fails open.
- SAM3: perception2/task_queue.py ONE consumer; mvd gate/count/clear/refresh are tasks; only start/clear/
  refresh_highlight write highlight state; the cap counts only commands. detect -> (DETECT_OK|DETECT_NOT_READY,
  hits); GPU OOM -> die. "Not ready" answers the user and keeps a live highlight (never "absent" / "0").
- Drone commands: dji_wire returns codes (UNREACHABLE=0, LATCHED=409); sent(code) = 2xx. Kill switch, router
  and pipeline say "FAILED ... take over with the RC" when a stop did not arrive; the latch says "refused".
  The drone link row turns red on no answer and NEVER dies (owner drone ruling). Loopback guard is strict.
- TTS: recovers like every service (RECOVERING, 3 tries, newest text, then fail). HTTP via urllib.
- phone_asr: dedup at receipt; one delivery thread (fixed a DOUBLE-MISSION bug: a slow Gemma plan used to let
  the duplicate REST/TCP copy through). Garbage / over-long / dropped input ends only that connection.
- session_log: status writes; `recording` row; slots "vision" / "describe"; only mic utterances claim a clip.

### Code-review + simplify history (all in 4c)
- Three code-review passes: R1-R30. All fixed except R20 (kept: owner ruling, a taken phone-ASR port dies).
- Simplify pass: applied items listed in 4c; skipped design items listed in 4d.

### Gotchas learned
- `pgrep -f <name>` matches the calling shell's own command line: use `pgrep -x`.
- cv2 4.11 has NO getMouseWheelDelta (the wheel handler reads the sign of flags).
- A test that only fakes the layer above a fix proves nothing: check it FAILS on the old code (done for R21).
- run.sh `_sig` uses grep -E: no BRE escapes.
- The app needs a ROS-sourced shell (run.sh app.sh does it) for ASR/keys/gstreamer.
- Owner process: answer every point by number; never call your own suggestion "settled"; record rulings in
  docs at once; use the skills (code-review, simplify, run) -- the owner had to remind the agent.

### NEXT STEPS (in order)
1. Webcam mock test with the REAL app (the run skill or `bash run.sh up webcam mock`; mock only -- safe per
   CLAUDE.md). Check: every status row goes UP (gemma, sam3, asr, keys, mock, video, tts if on, phone speech,
   recording, drone link after the first command); a Hebrew highlight, a count, a clear, a describe; the M
   kill switch message; the chat scroll; `bash run.sh status`; `bash run.sh down` leaves nothing running.
   Fix what breaks, with a test that fails first.
2. Ask the owner the 4d items (outcome wording, one motion gate, shared Recovery, VisionService / mvd split
   (769 lines), display-loop caching after measuring, dead benches: compare_engines.py, run_indepth.py,
   run_list.py; the pipeline flat-import try; refresh period from task start; count frames as delayed tasks).
3. After the owner's rulings: apply them, re-run code-review once more, then the owner commits.
4. Then the roadmap in section 7: global phase 7 (SAM3.1 + EOVSAM, quantized) after the webcam test, the
   field test (owner runs it, aircraft secured), freeze, post-freeze benches, drone-link resilience
   (keep-alive Noop + bounded reconnect), fuse into llm_to_action.

### 8b. ADDENDUM (second check before the context ran out)
Measured evidence (bench/sam3-concurrency-bench, RTX 5070 Laptop, SAM3 nf4, SAM3 ALONE = optimistic):
single detect p50 409 ms / p95 438 ms (~2.4 forwards/s); N concurrent threads 0.97-0.99x (no gain);
batching K prompts in ONE forward WORKS (Sam3Processor images=[pil]*K, text=[...], no `padding` kwarg) but is
1.02-1.04x and costs VRAM (3457 MiB at K=8). Memory note: sam3-concurrency-batching-not-a-lever.md.
Real-GPU runs this session: highlight/count/clear through the queue; Gemma under the supervisor (UP 15 s,
SIGKILL -> RECOVERING 0.4 s -> UP 3 s); gemma + asr + keys + mock all UP then DOWN, nothing left running.

Docs created or changed this session (all uncommitted):
- docs/review-harden2-agent-adherence-2026-09-21.md (the first audit of the previous agent's phases 1-2)
- docs/spec-harden2-cleanup.md (rulings appended: gemma package, status panel, app starts everything,
  layout, TTS recovery) + docs/spec-perception2-backend-contract.md (detect -> (status, hits), OOM -> die)
- docs/harden2-sam3-controlflow.{dot,png,svg} + docs/harden2-sam3-worker-arch.{dot,png,svg} (diagrams of the
  producer/consumer design) + docs/harden2-status-panel-preview.png (layout preview, sample states)
- bench/sam3-concurrency-bench/ (README, concurrency.py, RESULTS.md, raw.json); tools/audit_exceptions.py

STALE docs still to sweep (not done): projects/integration_harden2/README.md beyond the layout table (data flow,
run commands), docs/spec-harden2-architecture.md (still describes perception/, the watchdog pane, the llama
wrapper, tmux panes that start processes), perception2/README.md "Tests" section (lists old per-module files),
tools/prewarm_llama.sh assumptions. The two diagrams show the design, not every later fix (R21-R30).

Still-open items from the FIRST audit (docs/review-harden2-agent-adherence-2026-09-21.md):
- camera_stream's rclpy uses a find_spec guard, not the plain import the spec named: the owner never confirmed.
- P3-A (SAM3 lock granularity) is SUPERSEDED: the one-consumer queue makes the lock a safety net only.
- sam3_backend's `compile` param shadows the builtin; bench/sam3-mask-bench/quant_bench.py passes compile=.

For the owner's ONE commit (prepare commands then; never run them): it must include the DELETIONS
(projects/integration_harden2/perception/, recognizer/llama.py, run_llama_server.sh, video/video_watchdog.py,
the old test files, test/capture_golden_config.py + golden_config.json + live_mock_smoke.py) and the NEW
dirs (gemma/, system/, the new test files, perception2 new files). The earlier SCENE_VERIFY feature
(perception2/verify.py, bench/vision-verify-bench/, docs/task-active-harden2-session-handoff.md) was meant as a
SEPARATE commit per the previous handoff. Also modified by others: .claude/hooks/ste_check.py, docs/HISTORY.md.
Scratchpad backups under /tmp/claude-0/... are disposable.
