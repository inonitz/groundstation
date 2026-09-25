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
- SUPERSEDED 2026-09-23 (owner design: a dispatcher spawns one thread per task, max 8; see spec-harden2-cleanup.md).
  Old text: SAM3 = producer/consumer: ONE consumer thread (perception2/task_queue.py) makes every SAM3 call and writes
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
- Git: SUPERSEDED 2026-09-23. The owner commits now, in stages, each message marked BROKEN BUILD / not run
  end to end. The owner reviews the code after the commit.
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

## 9. PLAN (agreed with the owner 2026-09-23) -- supersedes the 4c order
Rulings behind each step: docs/spec-harden2-cleanup.md, "Owner rulings 2026-09-23" and after.
0. Owner commits the current state in stages, each marked BROKEN BUILD (commands given in chat).
1. [x] SAFETY (done 2026-09-23, 2 passes): the kill key is F4 from /keyboard/in/raw (app/keys.py), any window.
   M removed from the window. ROS2 is now required (the kill key needs it). Quit stays window-only.
2. [x] API v2 written (2026-09-23): docs/api-harden2/, one header per module. WAIT for the owner's review
   before step 3 (the layout follows the headers).
3. [x] Module layout (done 2026-09-23, 2 passes): app/{main,ui,render,state,keys}.py, log/{session,trace,
   show,score}.py, dji_app/client.py (class DjiApp), system/fatal.py, video/cam_list.py. The banned word is
   gone from every identifier (DJI_HOST, MOCK_DJI_PORT, ...). Launch: python3 -m app.main. Tests: one file
   per module (10). PUSH_TO_TALK_KEY_NAME in config. LEFT FOR LATER: app/main.py is 621 lines; its vision
   tasks move to perception2 (step 6) and its turn handler to the recognizer (step 4). Long lines in the
   moved tests are fixed when step 9 rewrites the tests.
4. [x] (done 2026-09-23, 2 passes + 3 mutation checks) dji_app client owns the transmit switch (BLOCKED=409;
   /c/stop never blocked); control/flight.py executes flight and is the switch's ONLY user; one wording:
   control.flight.outcome_text. The recognizer parses every sentence: fast path (recognizer/fast_path.py:
   emergency/manual/auto) -> control. Deleted: control/{router,kill,commands}.py, KillSwitch.MOTION,
   flight_allowed, the 8 unused helper verbs, the pipeline flat-import try (benches import the package).
   Emergency in manual -> /c/stop. Every failed mission is SAID. Status row renamed "dji app".
   CARRIED to step 5: TTS through dji_app + the WAITING (orange) state. CARRIED to step 6: the typed
   Routed result (the recognizer stops calling say()) and typed vision requests; app/main.py long lines.
5. [x] (done 2026-09-23, 2 passes) New state WAITING (orange). The phone app: a request with no answer ->
   WAITING + a probe (GET /status/, read-only) every WAITING_RETRY_SECONDS -> UP; never dies. Supervisor
   start(required=False) for the mock and gstreamer: past the budget WAITING + slow retry, no die. Laptop
   processes stay required (3 restarts, then die). Phone TTS = DjiApp.speak() (POST /tts, same app/port;
   in mock mode the mock gets it); its retry loop, row and TTS_HOST/PORT/TIMEOUT are gone. Laptop TTS:
   PortAudio error -> re-open 3 times, then die. Log: start check (folder creatable + writable) or die;
   no 'recording' row; a later failed write dies; a missing audio clip is skipped. SAM3 unchanged (die).
   The flaky SIGKILL log test now waits for the first write.
9b. [ ] Line-length pass (added 2026-09-23): ~140 older lines over 100 chars in the touched files. Do it
   AFTER steps 6-9 rewrite them; guideline ceiling ~95.
6. [x] (done 2026-09-23, 2 passes + 3 mutation checks) perception2/dispatcher.py (a condition-variable thread
   starts one thread per task, max 8), sam3_lock.py (priority lock: commands before refreshes), vision.py
   (count / highlight / clear / describe; results through Sinks callbacks; the period counts from the
   detect START; one highlight at a time). The recognizer routes vision TYPED and returns a Routed (it
   never speaks); a spoken clear (EN + HE) is routed without Gemma. app/main.py 609 -> 182 lines: the
   turn and the vision results live in app/turns.py. Removed: task_queue.py, text_parse.py, the one-key
   dict globals (9a-4). Session log: one record slot per task. All .py lines <= 89 chars.
7. [x] DONE 2026-09-24 (file by file; 2 checks). 22 try blocks -> 5: util/guarded.py holds ONE
   per failure domain (http_request, parse_json, file_op, stream_call); fatal.py keeps its crash-path
   catch. Replaced by non-throwing calls: port_open (connect_ex), the supervisor's stop (poll loop,
   util/process.wait_exit), the ROS frame (checked sizes before reshape), the phone port (a check
   before bind). Removed as redundant with the crash hook: SAM3 out-of-memory, laptop PortAudio.
   Self-tests moved into test files (recognizer/selftest.py deleted; engine/concept self-tests and
   sam3_backend._smoke -> test_perception2.py; the real SAM3 test is opt-in: HARDEN2_GPU_TESTS=1,
   run once, passed). No SystemExit/sys.exit in app code. The board is a passed service (no global).
   Test rewrites (behavior unchanged, construction changed): tests that relied on the global board
   or SessionLog() now pass a StatusBoard / a folder; the laptop-voice death test checks the
   PortAudioError text (the crash hook's words); the Gemma HTTP-error test uses a real HTTP 500
   from the stand-in server instead of patching urllib. New: 8 recognizer rule tests (were the
   self-test), 4 engine tests, 1 concept test, 1 box-math test, 1 GPU test.
   Was: try/except to the minimum (audit 2026-09-23): 4 shared helpers that live WITH fatal.py in system/
   (owner: maybe rename fatal.py; propose a name at step 3); rclpy stop via executor.shutdown();
   remove the pipeline flat-import try (owner: committed+documented benches are no longer relevant);
   self-tests move into test files, ideally leaving only fatal's cleanup catch.
   Method (owner): after EVERY step, check the work in 2 passes: did it do what the step says, and does
   it follow docs/guidelines.md and the house exception rule. Tick the step here when both pass.
8. One dependency-check file at start-up (replaces the scattered find_spec guards).
9. Tests: one file per module against real components; test_app.py over ROS topics (headless, 3 questions,
   M on, M off, kill Gemma and see it recover, quit).
10. Measure the display loop; change it only if the numbers say so.
11. Dead benches: repoint run_list.py; delete compare_engines.py and run_indepth.py (recorded in HISTORY.md).
12. Stale-doc sweep. HISTORY.md updated at every step (Why / Setup / Result / Verdict / Where).
13. Code review, the webcam mock run of the real app, then prepare the owner's commits.
After: phase 7 (SAM3.1, EOVSAM quantized), field test (owner, aircraft secured), freeze, fuse into llm_to_action.

### 9a. Validation of steps 1-5 (2026-09-23, against sections 4c/4d/8b/9 and the spec rulings)
Verified in the code: F4 global kill (step 1); API v2.1 headers compile and match the code after
two fixes (system.h SupProcess.required, control.h emergency-in-manual); layout, no banned
identifier, one test file per module (step 3); one switch, control its only user, fast path in
the recognizer (step 4); WAITING orange, supervisor required flag, phone TTS via dji_app, log
start check (step 5). Spec entries that read OPEN but were resolved are now marked RESOLVED/DONE.
Gaps found, added to the plan (none were in it before):
- [x] 9a-1 CLOSED 2026-09-23 night: die at once, remove the re-open loop (spec). Was: Laptop TTS keeps its own re-open loop (3 tries). It is not a process, so the supervisor
      cannot restart it, but the ruling says "no per-system retry loops". ASK the owner.
- [x] 9a-2 (recognizer part) DONE 2026-09-24: recognizer/ split by job (largest file 284). render.py (542) and log/session.py (363) remain. Was: recognizer/recognizer.py is 470 lines; app/render.py 298; log/session.py 256. Only
      app/main.py (609) had a planned split (steps 4/6). Split these too (KISS, ~150-200).
- [ ] 9a-3 gemma/server.py LlamaServer (bench launcher) repeats the supervisor's start/wait/stop
      (4d leftover, never ruled). ASK: benches use the supervisor, or keep it.
- [x] 9a-4 (done in step 6) app/main.py module-level one-key dict globals (OM, ENGINE, VISION, SUPERVISOR) and config
      aliases (4d leftover). Resolve in the step 6 rewrite.
- [x] 9a-5 DONE 2026-09-24: renamed use_compile (quant_bench.py updated). Was: sam3_backend's `compile` parameter shadows the builtin (8b leftover); rename it and the
      bench caller (bench/sam3-mask-bench/quant_bench.py).
- [x] 9a-6 DONE 2026-09-24: SessionLog(folder); the app passes config.SESSION_DIR. Was: log/session.py reads MVD_SESSION_DIR from the environment directly: a config bypass
      (config.SESSION_DIR already reads it). Use config only.
- [ ] 9a-7 No single interface is shared by every module (owner question 2026-09-23). Only gemma,
      audio, video and dji_app expose start_services(supervisor, log_dir). OPEN for the owner.
- [x] 9a-8 Line length: ALL harden2 .py lines <= 89 chars (owner 2026-09-23, "less than 90"),
      replacing 9b. Done by 4 parallel agents, each file proven AST-identical by
      scratchpad/check_wrap.py, tests green.
- [ ] 9a-9  perception2 leaks its assembly: app/main.py builds BackendLoader + PerceptionEngine +
      vlm_client by hand. perception2 should expose ONE factory that returns the Vision service.
- [ ] 9a-10 the recognizer imports dji_app's status codes (BLOCKED, UNREACHABLE, sent). It should
      only talk to control; control gives it the outcome.
- [ ] 9a-11 the recognizer imports perception2.lexicon (the HE->EN target fix). Only the recognizer
      uses it: it belongs in recognizer/.
- [ ] 9a-12 Density pass (owner 2026-09-23): blank lines between logical steps, one statement per line,
      no packed assignments or dense lambdas, in every file touched this session.
- 9a-10 detail: pipeline._fly reads raw HTTP codes (BLOCKED / UNREACHABLE / sent) because control.fly()
      returns the phone's HTTP code. Fix: control returns its own result; the recognizer never sees HTTP.
- [ ] 9a-13 "Internals by hand" in app/main.py (owner: constructors exist for this): build_vision wires
      BackendLoader + PerceptionEngine + Vision with a two-phase set_engine; build_flight REPLACES
      dji.fly_mission / dji.halt with recording wrappers from outside; the app opens the video source,
      retries it, reports the "video" row and builds StallGuard itself. Each module's constructor must
      build its own parts.
- [ ] 9a-14 Speech in vs speech out: Voice hides its two backends in one object, but speech IN is two
      objects (Ears, PhoneEars) the app builds and wires by hand. One audio object for speech in.
- [ ] 9a-15 Shared standalone helpers living inside one module (owner: shared = a shared folder):
      port_open, native_env (system/supervisor.py; used by dji_app, audio, gemma, video), sent
      (dji_app; used by control, recognizer), hebnum_to_digits (recognizer; used by log/score.py).
      Misplaced single-user helpers: perception2/lexicon.py (only the recognizer uses it),
      log.session.reject_why (words the recognizer's rejects; used by app/turns.py).
- 9a-3 DECIDED by the agent (owner: "decide"): the benches start Gemma through the SAME launcher as the
      app: system.supervisor.Supervisor + gemma.server.start_services(sup, log_dir, port=..., thinking=...).
      LlamaServer is deleted. One start mechanism.
- 9a-1 finding: in this setup laptop audio goes to the host through the PulseAudio socket
      (PULSE_SERVER=unix:/tmp/pulse-socket). It fails when the host sound server restarts, the output
      device is unplugged, or the socket is missing; a retry 1 s later fixes none of these reliably.
      Recommendation: die at once (no retry loop). Waiting for the owner.
- Ears: the owner says Ears was abolished. No ruling found in the docs, the git history (class Ears
      exists since 3ccbcf7) or this session's messages. Asked the owner which ruling (Eyes was deleted
      in phase 3.4a).

### 9b. Target design (owner rulings 2026-09-23 night) -- replaces 9a-9, 9a-10, 9a-13, 9a-14
Every class: constructor, close(), internal methods; then a user of the class.
SERVICES (the app creates them first, choosing each from config ONCE; any failure -> die):
  StatusBoard | SessionLog(folder) | Supervisor | process handles from Supervisor.start():
  Gemma server (always), keyboard hook (always: F4), ASR server (only if "ros" in ASR_SOURCES),
  gstreamer (only if VIDEO=dji), the mock (only if CONTROL=mock) | Gemma(port) client |
  DjiApp(host, port) | Sam3 (backend loader).
  A process runs only when a configured option needs it: no idle GPU/CPU, no false red rows.
MODULES (each gets the services it needs in its constructor; callbacks, not other modules):
  SpeechIn(sources=config.ASR_SOURCES, on_heard) | SpeechOut(outputs=config.TTS_OUTPUTS, dji) |
  Video(source=config.VIDEO, gstreamer handle or None) | Control(dji, log) -- the drone ONLY |
  Vision(sam3, gemma, video, sinks) | Recognizer(control, vision, gemma, log) | Keys(on_key) |
  Ui(video, status board, chat). The app connects callbacks (on_heard -> recognizer, F4 -> control).
SHUTDOWN: the app closes every module (reverse order), then every service (reverse order).
HTTP results: http.HTTPStatus (.is_success; 409 = CONFLICT = blocked); None = no answer.
- [x] 9b-1 BUILT 2026-09-24 (2 passes). Services -> modules -> reverse shutdown in app/main.py; every
      class has close(). ProcessSpec + Process handle (supervisor); gemma/server.process() is the ONE Gemma
      launcher (app + benches; LlamaServer deleted; 9a-3). Gemma, DjiApp, BackendLoader, SessionLog are
      service objects. SpeechIn(ASR_SOURCES) / SpeechOut(TTS_OUTPUTS) with asr_ros/asr_phone/tts_phone/
      tts_laptop; laptop voice dies at once (9a-1). Video(source, gstreamer handle). Control(dji, log) records
      missions itself (no method replaced from outside). Vision builds its own engine. Keys(on_key); the app's
      on_global_key acts on F4 only. Ui(video, board). http.HTTPStatus everywhere; the recognizer no longer
      imports dji_app. util/ (net, process, hebrew); lexicon + reject_why -> recognizer/. system/ros.py = one
      ROS2 context. All harden2 .py pass flake8 E30x/E501(89)/E70x/E731. 195 tests, 3 clean runs.
      Closes 9a-3, 9a-9, 9a-10, 9a-13, 9a-14, 9a-15 (guarded helpers: step 7).
- [x] 9a-12 DONE 2026-09-24 (2 passes). Older files regrouped by intent in the owner's _track style:
      recognizer.py, render.py, session.py, perception2/{verify,engine,concept,counting,sam3_backend,
      vlm_client}.py (by the agent); log/{score,show,trace}.py, video/cam_list.py, recognizer/prompts.py
      (helper agent A); config/*, app/{turns,ui}.py (helper agent B); both agents' work re-checked by the
      agent (diffs read, config values compared old vs new: identical). Box overlap math: one home,
      perception2/boxes.py (was 3 copies) + a test pinning its values (mutation-checked). Removed dead
      code: EN_NUM_REV, LOG_DIR, _wrap_px's unreachable ASCII branch, render's `if not cur: cur = []`.
      score.py reads config.SESSIONS_ROOT (was a second home) and dies when no session exists.
      196 tests, 2 runs; flake8 layout + pyflakes clean on all harden2 .py; bench audit CLEAN.
      Left open (owner calls): _number_token vs _is_number_he differ on 'ו5' (merging changes behavior);
      env overrides read in both config/__init__.py and config/defaults.py; stale docstrings in
      prompts.py (names removed prompts) and config (names config_constants.py / config_defaults.py).

### 9c. STATUS 2026-09-25 (the current state of plan 9; supersedes the ticks above where they differ)
| item | state |
|---|---|
| 1-7, 9b, 9a-5, 9a-6, 9a-12 | DONE |
| status owned by each part (status()); recognizer split + Recognizer; shared helpers; UI manual_on | DONE (2026-09-24) |
| log/trace.py | DELETED (owner, 2026-09-24) |
| measurement: log/perf.py, `run.sh perf`, the scripted run (SCRIPT=default, mock only) | DONE; first measured run recorded (HISTORY 2026-09-25) |
| 10 display loop | MEASURED: the dark room limits the C920 (16-18 fps auto); our loop is 16 ms. OPEN: the 3.6 fps dips |
| 13 webcam mock run | ONE live run done (fixed: the ggml mix via the owner's rebuild, the chat line-break crash). OPEN: code review, owner commits |
| 8 one dependency-check file at start | OPEN |
| 9 test_app.py end to end over ROS (headless) | OPEN (app/feed.py is a first part) |
| 11 dead benches (run_list.py, compare_engines.py, run_indepth.py) | OPEN |
| 12 stale docs outside harden2 | OPEN |
| 9a-2 split app/render.py (542) and log/session.py (363) | OPEN |
Open findings: the number guard does not see a leading ו-number word (וחמישה); SAM3 558 ms p50 on the
shared GPU (vs ~400 alone, unverified cause); the keyboard hook wrote 28,291 log lines in ~4 min
(1.5 MB, proc-keys.log; the owner's C++ decides); both webcams read black in a dark room.
After plan 9 (global): phase 7 (SAM3.1, EOVSAM quantized), field test (owner, aircraft secured),
freeze, fuse into llm_to_action.
Speedrun split (owner 2026-09-25): agent A = step 11; agent B = 9a-2 (render.py, session.py);
the main agent = steps 8, 9 and the 3.6 fps dips; step 12 runs LAST, over the finished state
(owner: a doc sweep before the other steps land would go stale again). Standing rules: now all in
docs/guidelines.md ("Project rules learned in harden2").

