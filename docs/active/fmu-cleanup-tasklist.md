# FMU cleanup / refactor — living tasklist

Update this every slice. Purpose: hold the goal + progress across the INCREMENTAL, build-then-Gazebo
refactor, so context survives between sessions.

## The goal (why)
`fmu_node.hpp` is one ~2600-LOC class that is BOTH declaration and implementation, with test
scaffolding and mixed units woven through the safety-critical control loop. Make it correct, readable,
and testable **without changing flight behaviour**. SITL/Gazebo is how we prove behaviour is unchanged
before flying a real drone -- the demo runs on DJI hardware, SITL is the behaviour-verification bench.

## Hard constraints
- Behaviour-sensitive changes (control loop, units): **build + human runs Gazebo per slice.** A compile
  is not proof of flight behaviour.
- **No bulk manual hpp->cpp migration** (error-prone). End-state target: `fmu.hpp / fmu.cpp /
  fmu_node.hpp / fmu_node.cpp` -- do it when there is an automated tool.
- **Incremental**: one small behaviour-preserving slice at a time.
- **Naming**: the per-tick per-command control functions are `step<Verb>` (stepGo, stepFollow, ...),
  NOT "servo" (plain word; writing-style.md no-jargon rule).
- No git writes (human owns git). `rtk` for reads. Edit tool blocked -> python3/Write.

## DONE (build-verified; unit tests pass)
- [x] Removed dead `VehicleTelemetry` (cm stub).
- [x] Battery read LIVE via `effectiveBatteryPct()` -- never cached.
- [x] `cmdName` moved to `command_id.hpp` beside `commandIdFromAction` + round-trip unit test.
- [x] Observability block -> `initDashboardDiagnostics()`.
- [x] VLM `max_tokens` 768 -> 1024 (stop clipping thoughts).
- [x] Pure helpers (`lateralComponent`, `labelMatchesTarget`) -> `fmu_helpers.hpp` + unit tests.
- [x] `runTestPlan` implementation moved to `fmu_node.cpp` (header keeps the declaration) -- the
      test-code migration pattern the human asked for.

## NEXT (incremental, Gazebo-gated)
- [ ] **E: decompose `controlLoop` per-tick control laws into `step<Verb>()` methods, ONE at a time.**
      - The per-tick laws are an `if/else-if` on `id = m_currTask.m_cmd.id()` inside `if (m_hasActive)`
        (~L837+), NOT the `activateTask` SETUP switch (~L1924). Pattern set: declare `step<Verb>()` in
        the hpp per-tick-law group (before `controlLoop`), DEFINE out-of-line in fmu_node.cpp under the
        "Per-tick control laws" banner (like `runTestPlan`). Movement laws take `(const Odometry& od)`
        and own their scratch; HOVER is argless.
      - Order: simplest first (HOVER/STOP), then GO/LAND, then ORBIT/FOLLOW, then the LOCKED
        SEARCH/APPROACH.
      - Each: build, human Gazebos the matching scenario, then next.
      - [x] **stepHover** extracted -> fmu_node.cpp. Build clean ([54/54] link). AWAITING GAZEBO (hover
            holds station at zero velocity, never completes). Next: stepGo (prepped -- reads n,e,d +
            m_goStart*/m_goDir*/m_activeSpeed/m_cfg cross-track; branch-private scratch).
- [ ] **D: units -> pure metres.** ATOMIC across: config (`drone_config.hpp` + `fmu_node_base.hpp`
      BOTH -- `*CmS` = cm/s, `*M`/`*Mps` = metres already), Cmd structs, `translateToBaseCommands`
      parse, and every `/100.0f` in the (decomposed) `step<Verb>` methods. Do per-step after E so each
      is Gazebo-testable in isolation. Perception depth cm (`medianDepthCmInRect`) is the vision-lib
      boundary -- out of fmu scope, note only.

## Build + test-harness fixes (2026-08-17, build-verified)
- [x] **Static/shared honoured.** px4/tello/dji backends dropped hardcoded `add_library(... STATIC)`
      -> bare `add_library` now respects `BUILD_SHARED_LIBS` (the `build.sh static|shared` arg).
      Gazebo plugin (`gstreamer_gz_udp_tx`) stays SHARED (runtime-loaded plugin). Verified: shared
      build emits `libpx4_backend.so`, FMU links it, resolves via build-tree rpath. Stale `.a`
      leftover beside the `.so` is cosmetic (clean rebuild drops it).
- [x] **run_all.sh stopped lying.** Folders with no `filter.sh` (colors/crowd/dashboard/rubicon/
      rubicon_orbit/search_follow) now SKIP instead of spurious FAIL; `UNVERIFIABLE_SCENARIOS` synced
      to real names (`approach approach-real cross vlm follow`), dead `forward/speed/orbit/search`
      removed. `bash -n` clean.

## Test workflow (as-built, cold-start reference)
- Engine: `projects/llm_to_action/test/lib/sim_core.sh` (sourced by every `<feature>/run.sh`; sets objective +
  `FMU_CANNED_FLAG`, launches tmux sim; HEADLESS path waits on `wait_for_ground_truth.sh`).
- Per feature: `<feature>/run.sh` + `filter.sh` (grep FMU log -> verdict) + `README.md`.
- Interactive: `cd projects/llm_to_action/test/sitl-legacy/<feature> && ./run.sh` then `./filter.sh`; or `./logtest.sh <f>`
  (timestamped log under runs/) then `./digest.sh`.
- Headless regression: `projects/llm_to_action/test/sitl/run.sh --all` (config-driven, replaces run_all.sh).
- `scripts/simenv.sh` is OUTDATED/reference-only -- do NOT use it (user, 2026-08-17).
- Per-command coverage GAP: HOVER/ROTATE/STOP have no dedicated folder; ORBIT (`rubicon_orbit`) +
  SEARCH (`search_follow`) folders lack a verdict `filter.sh`. No fast isolated unit test of any
  step<Verb> law (they are node methods -> need the ApproachCommand-style extraction, deferred).
  PLAN: as each step<Verb> is cut, add/repair its feature folder + `filter.sh` so
  `run_all.sh --only <cmd>` becomes that slice's regression gate.

## Rename + per-command test scenarios (2026-08-17)
- [x] **Renamed "canned plan" -> "test-scenario"** (user pick). `TestPlan`->`TestScenario`,
      `parse/runTestScenario`, `scenario*Json`, `fmu_test_plans.hpp`->`fmu_test_scenarios.hpp`,
      flags `--canned-*`->`--scenario-*`, env `FMU_CANNED_FLAG`->`FMU_SCENARIO_FLAG`; JSON "thought"
      labels de-"canned". C++ build clean. NOTE: the internal **"canned approach rig"** members
      (`m_useCannedApproachRig`, `m_cannedApproachTargetEnu`, `updateCannedApproachRig`,
      `m_forceApproachImpact`) are a DIFFERENT concept (synthetic-perception rig) -- left as-is;
      follow-up: rename that cluster to "synthetic..." (behaviour-adjacent, its own pass).
- [x] **Added scenarios Hover/Rotate/Orbit** (enum + parse + JSON + runScenario + unit-test CHECKs).
      Gotcha hit + fixed: a `(...)` immediately before the closing `"` made `)"` which terminates a
      `R"(...)"` raw string early -> reworded. Watch for `)"` inside scenario JSON.
- [x] **New SITL folders** projects/llm_to_action/test/sitl-legacy/{hover,rotate,orbit}/:
      - hover/ (NEW): scenario [takeoff, go +1.5m, hover, go -1.5m, land]. HOVER never completes so
        the back-go can't dequeue; filter.sh AUTO-verdicts PASS iff NO GO activity after
        'HOVER activated' (absence of the reversal proves the hold). Drives the extracted stepHover.
      - rotate/ (recovered from archive/rotate-land): real swept-angle awk verdict (90cw/200ccw +-15).
      - orbit/ (recovered from archive/orbit): runs in **rubicon_tree** world (per request; law flies
        a fixed circle so it needs no real object). Milestone-only filter -> UNVERIFIABLE in run_all.
- [x] **run_all.sh wired**: hover=flight:75 (never lands -> wait times out exit0 -> filter judges),
      rotate=flight:90, orbit already flight:120 + added to UNVERIFIABLE. `bash -n` clean.
- [x] **STOP needs no flight test.** Queued STOP auto-completes (no-op -> covered by translate unit
      test). Spoken "stop" == spoken "hover" == `emergencyHoldNow()` (identical). Only queued HOVER
      (persistent hold) is behaviourally distinct -> hover/ covers the meaningful case.

## Readability backlog (user-flagged 2026-08-17)
- [ ] Use `util/base.hpp` aliases (`PublisherPtr<T>`, `SubscriberPtr<T>`, `TimerSharedPtr`) in place
      of raw `rclcpp::Publisher<...>::SharedPtr` etc. in fmu_node.hpp; move shared verbose base types
      into util/base.hpp. Low-risk cosmetic slice.

## Gazebo feedback round 1 (2026-08-17)
- [x] **Hover PASS** in Gazebo -> stepHover extraction CONFIRMED (slice 1 of E done).
- [x] **Rotate precision.** Was undershooting ~5 deg (stopped at completion band). Fix:
      kRotateCompletionDeg 5->1.5, added kRotateMinYawRate=0.15 rad/s floor so the last few deg
      close promptly instead of creeping; rotate/filter tolerance 15->5 deg. BEHAVIOUR CHANGE (also
      touches the SEARCH scan, which shares kRotateCompletionRad) -> re-Gazebo rotate (+ eyeball a
      search). Build-verified.
- [x] **Orbit fixed.** Was a fixed 7m circle in rubicon_tree (wrong world, too big, ignored the
      VLM's radius_cm). Now the law HONOURS radius_cm (clamped [kOrbitMinRadiusM=3, kOrbitMaxRadiusM=12];
      unset -> 7m fallback) with centre still R-ahead (starts ON the circle). New world
      assets/gz_world/orbit_car.sdf = default_car with the car at (4,7) = the 4m orbit centre; scenario
      radius_cm=400. orbit/filter.sh now AUTO-verdicts radius-hold error (max<1.0m, mean<0.5m) + full
      sweep -> orbit removed from UNVERIFIABLE. NOTE: the demo VLM already emits radius_cm=600, so the
      building demo now orbits at 6m (was 7m) -- more correct (does what it commands), flag for re-demo.
      Build-verified.

## Remaining per-command test gaps (answer to "what other tests do we need")
- FOLLOW: follow/ exists but filter is milestone-only ("confirm what you saw") -> wants a real verdict
  (hold standoff, stable track id). Needed before stepFollow extraction.
- SEARCH: search_follow/ is DEAD (Tello demo that never happened, no filter). SEARCH (advance-and-scan)
  is used in the real demo -> needs a fresh scenario + filter. Needed before stepSearch extraction.
- GO/ROTATE/ORBIT/APPROACH/boundary/battery/flood/storm all have working auto-verdict tests.

## Gazebo feedback round 2 (2026-08-17) -- precision
- [x] **Rotate -> dead-on (user won't retest, trusts it).** kRotateCompletionDeg 1.5->0.3, floor
      0.15->0.05 rad/s (terminal tick ~0.14 deg -> final error <0.5 deg). rotate/filter TOL ->1.5 deg.
- [x] **Orbit tighter.** Radius rode 0.07m outside (proportional radial lag) -> kOrbitRadialGainHz
      0.5->1.5. Heading lagged the centre (drone not exactly at start heading) -> added YAW FEEDFORWARD
      (omega = m_orbitDir*strafe/R) so the P term only trims; kOrbitYawGain 1.0->1.5. orbit/filter
      tightened max 1.0->0.30, mean 0.5->0.15. Round-1 run was mean 0.09/max 0.18 at old gains; expect
      tighter now. NO cross-orbit accumulation: m_orbitSweptRad resets per orbit command; within-orbit
      overshoot is bounded to one tick (~0.5 deg). Re-Gazebo orbit (gain change).

## Roadmap (as of round 2)
1. Confirm rotate (trusted) + orbit (retest) precision build. [build in flight]
2. Close the 2 test gaps: FOLLOW real verdict, SEARCH fresh scenario+filter.
3. Continue step<Verb> extraction (behaviour-preserving, build+Gazebo each): stepGo (cross-gated) ->
   stepFollow -> stepRotate -> stepOrbit -> stepSearch -> stepApproach.
4. Units -> metres (task D), per extracted step.
5. Folder restructure (user-deferred to after tests pass).
6. Deferred: hpp->cpp 4-file split (needs auto tool); "canned approach rig"->"synthetic" rename;
   util/base.hpp alias cleanup.

## Follow + Search tests + housekeeping (2026-08-17)
- [x] **Orbit filter tightened** to lock in achieved precision (mean 0.03/max 0.09): max<0.15, mean<0.06.
- [x] **ros2 bags default OFF.** sim_core RECORD_BAG default was ON for attended runs (piled up, e.g.
      rubicon_orbit's 15). Now RECORD_BAG=0 default; opt in with RECORD_BAG=1. bag_*/ already gitignored.
- [x] **FOLLOW test = scripted + real verdict.** Upgraded follow/ from VLM-driven to scripted
      (--scenario-follow, VLM off, real perception; approach-real proves perception runs without VLM).
      Scenario [takeoff, follow target_index=0 standoff_cm=200] in moving_person. filter.sh verdicts:
      sustained FOLLOW(yaw-only) ticks (>=20), stable track id, no follow_no_target. Removed from
      UNVERIFIABLE. RISK: if perception isn't warm at follow-activation the lock may not resolve
      (law logs "hover until a lock") -> if it hovers without locking in Gazebo, revisit the follow
      acquisition/settle. crowd/ still covers VLM-driven follow.
- [x] **SEARCH test = new folder.** search/ replaces the dead search_follow (Tello demo). Scripted
      (--scenario-search, VLM off): [takeoff, search person] in three_people, spawned facing away.
      filter.sh PASS iff SEARCH activated then SEARCH DETECTED target=person. (On find it auto-hands to
      APPROACH.) search_follow/ left in place for now (folder restructure will remove it).
- Enum now: ...Orbit=12, Follow=13, Search=14. Build + unit test [verifying].

## Test-today checklist (post rename + static-shared + precision)
- MUST (new/changed, no Gazebo yet): follow, search.
- SMOKE (rename touched every run.sh flag + binary rebuilt shared; not run today): cross, approach,
  approach-real, approach-impact, battery-rth, battery-landnow, boundary, flood, flood-airborne,
  interrupt-storm, override. Run headless: projects/llm_to_action/test/sitl/run.sh --all (SKIP_HIGH_VRAM=1 to skip
  the 3 VLM-heavy ones). hover/rotate/orbit already verified.

## Gazebo feedback round 3 (2026-08-17) -- follow spin + search world
- [x] **Search -> rubicon.** Was contrived three_people; now rubicon_targets (real rubicon map, 2
      people + 2 cars), spawned facing away so it must scan. (The three_people run actually PASSED --
      it DETECTED the person; "stops the search" = found it. But the world was the objection.)
- [x] **Follow de-spun (user chose: stay-put + track-only).** Log diagnosis: it DID lock the person
      (track_id=4, label=person) and the servo converged at first (errX 0.13->0.04, sign correct), but
      the person was ~16m away and FOLLOW is yaw-only (never closes), so it twitched on a far noisy box;
      errX then drifted to -0.58 with yawRate PINNED at the 1.5 max -> spin (heartbeat yaw 0->1.57).
      Fix: kFollowYawGain 5->2, kFollowYawMaxRps 1.5->0.6, +deadband (|err|<0.06 -> 0), +box-jump reject
      (one-tick errX leap >0.30 -> hold). Build-verified.
      OPEN SUSPECT if it still spins: the heartbeat showed od.yaw STUCK at 0.00 for seconds then jumping
      to 1.57 -- the yaw command may not have executed during early flight then dumped at once (takeoff/
      offboard mode?), which the gentle gains only *limit*, not cure. Re-run tells us; if so, dig into
      the takeoff->offboard yaw handoff, not the follow law.

## Gazebo feedback round 4 (2026-08-17) -- log_test_runs.txt triage
FIXED (build/verified where code):
- [x] **cross FAIL (hovered).** ROOT: the keyboard hook is a GLOBAL key grabber; stray keystrokes
      (human typing elsewhere) toggled /fmu/in/override, and the handback DRAINS the queue + forces a
      VLM re-plan (fmu_node.hpp overrideCallback ~1829). Scripted+VLM-off -> plan gone -> hover forever.
      FIX: sim_core only launches the keyboard hook when LAUNCH_KEYBOARD=1 (override/ sets it). This
      also de-flakes EVERY scripted test (and may incidentally fix the search 160deg).
- [x] **flood filter FAIL.** Stale grep ("FLOOD test: injecting"); real logs are "FLOOD test: N actions
      vs queue cap" + "overflow dropped by backpressure". Rewrote verdict. (flood never taking off is
      BY DESIGN -- ground-only queue-backpressure test.)
- [x] **approach too slow.** kApproachSpeedDefault 80->120 cm/s, kApproachFwdGainHz 0.35->0.55 (hold
      cruise longer then brake harder), coast 0.15->0.30. Build [in flight].
- [x] follow de-spun (round 3) build CONFIRMED clean.
- [x] battery-rth, battery-landnow, boundary: PASS in Gazebo.

PENDING (next round, honest):
- [ ] **approach-real HITS the car.** Different bug from speed: the range LOCK (fmu_node.hpp ~1053
      m_approachTravelBudget = m_approachLastRange - standoff) uses monocular DEPTH, unreliable close-up
      for the real car -> stops late; the boundary-looming backstop (fill>0.40) fires but too late +
      VLM-off can't reassess. Needs depth/perception work, NOT a speed tweak (speed-up makes it worse).
- [ ] **search 160deg** after DETECT. No search log captured; retest AFTER the keyboard gate (likely a
      stray-key artifact). If it persists, need the search/captured log to see if it's the scan dir or
      the search->approach handoff yaw (shortest-angle?).
- [ ] **Renames (user: names piss me off / unclear):** boundary -> obstacle-stop?, flood/flood-airborne
      -> queue-overflow?/airborne-... . Touches enum+parse+runScenario+JSON+folder+flag. Batch later.
- [ ] **ASR tests MISSING:** basic ASR (voice launch), emergency ASR ("land"/"stop"), override ASR.
      New scenarios -- need the ASR injection path (post transcript to /asr_server/transcribe topic).
- [ ] interrupt-storm, override: user hasn't retested yet.

## Gazebo feedback round 5 (2026-08-18) -- systematic-debugging pass
Root-caused (skill: systematic-debugging), then fixed + build [in flight]:
- [x] **cross PASS**, flood PASS, approach-impact PASS (synthetic -- clarified README), battery/boundary PASS.
- [x] **FOLLOW lag.** NOT perception rate (seg=30Hz, snapshot fresh). Causes: (1) the de-spin dropped
      kFollowYawGain 5->2 = too sluggish (yawRate 0.26 for errX 0.13, mean|errX| 0.163); (2) 26% detection
      GAPS (person at 11m, conf 0.40 -> YOLO intermittently misses). Fix: gain 2->3.5, maxRps 0.6->0.9
      (deadband+jump-reject still prevent the spin). Gaps are a far-target perception limit; the drone
      holds through them (safe). NOTE: some perceived lag is the ~10Hz annotated STREAM the human watches,
      not the 30Hz control.
- [x] **approach-real COLLIDES.** Root: log shows repeated "APPROACH coasting target=car (lost)" -- the
      car detection drops, so it dead-reckons a DEPTH-estimated budget (R0=7.32) that's unreliable, and
      my speed bump made the looming backstop fire too late. Fix: DEPTH-INDEPENDENT bbox-fill brake in the
      approach servo (ramp spF to 0 from fill 0.18->0.35; the canned rig's fixed tiny box never trips it,
      so canned stays fast) + kBoundaryLoomFillFrac 0.40->0.28 (earlier brake for the lost/coasting case).
- [x] **search -> car** (rubicon_targets has 2 cars + 2 people); folder/filter/README updated.
- [x] **RENAMES (done, not deferred):** boundary->obstacle-stop, flood->queue-overflow, flood-airborne->
      queue-overflow-airborne (enum+flag+folder+run.sh+run_all+filter+README+unit-test). Internal safety
      law "emergency boundary" + m_flood* fault-injection members KEPT (different concept from the test name).

STILL OPEN: interrupt-storm + override + ASR tests (basic/emergency/override) not built yet; approach
still a touch slow per the user (canned uses budget, fill-brake only bites the real target).

## DEFERRED
- [ ] Move the `controlLoop` fault-injection test hooks (`m_floodArmed`/`m_obstacleArmed`/
      `m_batForce*`) to `fmu_node.cpp` like `runTestPlan`. They read inside the safety block -> batch
      with the E pass, Gazebo-gated. (These stay -- they drive the SITL safety-law tests.)
- [ ] Full hpp->cpp split to the 4-file layout -- needs an automated refactoring tool.
- [ ] Replace the demo hacks (hardcoded ORBIT, auto-land-after-approach, no-YOLO rig) with the modular
      perception/tracking path -- gated on the perception work, not a blind delete.

## Verify
- Build: `cmake --build build/release/shared/px4 -- -j4` (must link)
- Unit test: `g++ -std=c++17 -I<util2/include> -Iprojects/llm_to_action/source projects/llm_to_action/source/fmu/test/fmu_translate_test.cpp -o /tmp/t && /tmp/t`
- Behaviour: Gazebo/SITL scenarios under `projects/llm_to_action/test/sitl-legacy/` -- **human runs these.**

## Key context (cold-start — read after a compaction)
- **Project**: voice-commanded drone demo, Israeli MOD contest 2026-08-27. Linux stack
  (perception + planning) drives a drone backend. Demo = DJI hardware; SITL/Gazebo = behaviour bench.
- **Platform**: DJI Mini via an Android bridge. The teammate's Kotlin app (`recon-swarm`,
  github ExoSkeletons/DJI-android-sdk-v5-recon-swarm) is a Ktor `ApiServer` over LAN. MSDK is
  Android-only. Tello is dead (no indoor position). Manager role: I own the fmu cleanup; a SEPARATE
  agent owns the DJI backend.
- **DJI app state (2026-08-17)**: CAMERA STREAMING WAS ADDED (commits: `add camera` -> `add camera
  straming` -> `quality` -> `error catching`), plus `add status listening` and `re-add lookat, goto`,
  latest `suspending actions`. Video (the #1 gap) now EXISTS; transport/codec still TBD -- the DJI
  agent must inspect `ApiServer.kt` + camera code and mock it.
- **Latency**: laptop<->phone WiFi p95 ~12 ms on 2.4 GHz sustained. GO (no 5 GHz needed).
- **Docs**: mission-brief-2026-08-15.md (platform + goals), spec-fmu-cleanup.md (this refactor's
  plan A-G), spec-dji-backend.md (agent spec), dji-apiserver-review.md (punch list for the app
  author), spec-dji-websocket-protocol.md (FROZEN wire contract), spec-android-docker-bridge.md,
  fmu-node-split-map.md. Mock: tools/dji_mock/{mock_apiserver.py, ws_latency.py}.
- **Env**: this box HAS colcon/cmake/g++/ROS jazzy + a warm `build/release/shared/px4`. Build ~3 min.
- **Gotchas**: switch @ ~L1924 = `activateTask` (one-time SETUP), not the per-tick laws; speed config
  is mixed cm/s vs m and DUPLICATED across drone_config.hpp + fmu_node_base.hpp; `medianDepthCmInRect`
  is the vision-lib cm boundary (out of fmu scope).

## DjiBackend agent hand-off (relay this)
The recon-swarm app now streams camera (2026-08-17 commits above) -- our #1 blocker is unblocked.
Agent action items:
1. **VIDEO (critical)**: inspect the new streaming route in `ApiServer.kt` + the camera code. Pin:
   (a) endpoint path, (b) WS or HTTP, (c) codec (H264 NAL / MJPEG / JPEG frames / RTMP). Add that exact
   endpoint to `tools/dji_mock/mock_apiserver.py` (serve a looped test clip, same transport) so
   DjiBackend's video consumer builds + tests against the mock.
2. Re-check the other review items in the new commits: did takeoff/land gain response bodies? is there
   velocity clamping? `status listening` = telemetry -- confirm `/status` still matches the protocol.
3. Contract stays spec-dji-websocket-protocol.md; the video transport is the one piece to nail.
4. Disconnect is a non-issue (drone brakes to hover on stick-loss). Don't spend time there.
Report back the video transport (path + codec) so we lock it into the protocol spec + mock.
