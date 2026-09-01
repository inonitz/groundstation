# Groundstation Roadmap and Objective Tree

Living, consolidated list of every goal for the project, recursively, with status. This is the
single place the whole objective set lives; it was previously scattered across `NOTES.md`,
`ARCHITECTURE.md`, and the specs under `specs/`. Keep it updated as reality moves.

Status legend: `[x]` done, `[~]` partial / WIP, `[ ]` todo, `[GATE]` blocked on a dependency,
`[DEFER]` deliberate later horizon.

Last synced: 2026-08-20 (perception-first pivot; see the CURRENT PHASE banner below + the dated section at the END). Prior 2026-08-09 (spec-1/spec-2 SITL runs landed -- boundary/approach-impact/interrupt-storm/orbit/search all PASS; SEARCH return-to-start, tolerant plan extraction, APPROACH motion-gate, SLAM tracking spike; earlier: 2026-08-08 spec-3 failsafe supervisor + user override + SPSC backpressure; 2026-08-06 GenericBackend build-verify + build_yolo benchmark).

---

> **>>> CURRENT PHASE (2026-08-20): PERCEPTION-FIRST — read this before the tree below. <<<**
> The project PIVOTED. The DJI **Tello was DROPPED** (limited SDK, more problems than solutions); the
> platform is a **DJI drone** (video via DJI Fly Custom RTMP). The 2026-08-20 tech-credibility **GATE
> (prove smart, live, voice-driven CV) was PASSED** — with the perception demo, NOT flight. So:
> **the flight-core objective tree below (blocks 1-9: FMU, guidance, ROTATE/APPROACH/ORBIT/SEARCH,
> backends) is DEFERRED until after Demo Day.** It is real, SITL-verified work, but it is NOT the current
> priority and does NOT gate the demo. The perception stack (`archive/llm_cv_track` + `llm_cv_scene`) runs
> STANDALONE, not through the FMU. **Current priority + full plan = the `## 2026-08-20 — GATE PASSED`
> section at the END of this file.**

## Objective tree

```
ROOT: Off-board VLM-driven autonomous system (DJI drone via RTMP; Tello DROPPED 2026; PX4 SITL for
      flight-core dev). Two subsystems: "VLM plans, deterministic math executes" (flight core, DEFERRED)
      + voice-driven open-vocab perception (the gate/Demo-Day demo, ACTIVE).

1. Flight core / FMU                                              [~]
   1.1 20 Hz deterministic control loop                          [x]
       1.1.1 GO guidance (carrot-chasing cross-track)            [x]  further tuning [DEFER, visual servo]
       1.1.2 ROTATE                                              [x]  parser + yaw law, SITL-verified
             2026-08-07 (was scaffolding-only / silently dropped): rotate parse branch
             (direction + angle_deg), a CommandID::ROTATE dispatch, and an accumulated-angle
             movement branch that integrates yaw progress in the commanded direction until the
             full magnitude is swept -- granular incl. >=180 deg (270 cw really turns 270 cw;
             360 = full turn), not shortest-path. SITL-verified 2026-08-07: 90 cw swept -86 deg,
             200 ccw swept +195 deg (long way CCW, not shortest-path).
             Regression test: `projects/llm_to_action/test/sitl-legacy/rotate-land/filter.sh` captures all sim panes and
             asserts the swept angle/direction of the canned 90 cw + 200 ccw turns.
             2026-08-11 (agent3): rotation testing on the REAL airframe is reframed
             as [GATE Agent-5 SLAM], not a yaw fix. The airframe drifts through space
             during a turn (whole-airframe drift, see 9.13 / Agent 0). A rotation test
             cannot separate a yaw-law error from that positional drift until SLAM
             stabilizes the pose. This is a test-gating problem, not a rotate-code bug.
             The once-seen ROTATE hang (no completion timeout, docs/NOTES.md) stays a
             separate open item.
       1.1.3 TAKEOFF state machine (arm, climb, FLIGHT)          [x]
       1.1.4 LAND state machine (descend, force-disarm)          [x]
       1.1.5 STOP / Hover                                        [x]
       1.1.6 ORBIT (target-anchored)                             [x]  odometry circle, SITL PASS 2026-08-08
             2026-08-09: also verified under a real (non-canned) live VLM-driven flight, not
             just the canned scenario -- see docs/NOTES.md.
       1.1.7 SEARCH (parallel-track lawnmower)                   [x]  SITL PASS 2026-08-08
             2026-08-09: fixed a real gap -- failed SEARCH left the drone stranded wherever
             the sweep ended; now returns to its start pose before completing. Grid size/shape
             still fixed at activation, blind to the room -- open, see docs/NOTES.md.
       1.1.8 CURVE                                               [dropped for POC]
   1.2 ENU convention (Task 4)                                   [x]  operator SITL re-gate [ ] (human)
   1.3 Offboard streaming ~100 Hz (collapsed into backend)       [x]
   1.4 SPSC task queue (moodycamel) + backpressure               [x]  bounded try_enqueue + reject-newest, every drop logged; SITL-verified (flood + flood-airborne)
   1.5 Interrupt + reflexive hold-clearance (ARCH 5.1)           [x]  SITL-verified 2026-08-08 (interrupt+stash+hold)

2. Backend abstraction                                           [x]
   2.1 GenericBackend interface (CRTP, builds both backends)     [x]
   2.2 PX4Backend (flies in SITL)                                [x]
   2.3 TelloBackend                                              [~]  first real-hardware
       flight verified 2026-08-06 -- telemetry, odometry, camera all confirmed live
       (see tasks_closed/2026-08-06-tello-real-world-bringup-telemetry-hardening.md)
       2.3.1 stick to m/s calibration (real hardware)            [ ]  (human, hardware-bound)
       2.3.2 Simpson-rule odometry in the driver                 [ ]  data now flows live;
             integration method itself still unverified
       2.3.3 real gstreamer H264 RX (udpsrc 11111, h264parse)    [x]  confirmed working on
             hardware via cv::VideoCapture/FFMPEG; no gstreamer swap needed
       2.3.4 runtime speed control (tello_teleop "more/less speed" [ ]  clamped min<=v<=max;
             keys, clamped)                                            low speed = practical
             indoor wind/prop-wash mitigation (found 2026-08-06)
       2.3.5 active stability correction against wind/prop-wash  [ ]  Tello drifts far more
             than SITL; control path must monitor + correct, not fly open-loop. Ties into
             GO/visual-servo work now that odometry is live.
       2.3.6 latency benchmarks + self-contained I/O tests        [ ]  no measurement exists
             for keypress->drone-response latency. Plan: record a real flight's input/command
             sequence + timestamps to disk, replay as a deterministic test fixture (no
             re-flying). Also: independent end-to-end latency tests for odometry (wire->parsed
             Odometry) and camera (drone frame->decoded frame). Not blocking, matters for
             trusting the control loop.
   2.4 Per-node CMake split                                      [x]
   2.5 Uniform backend-construction contract (kill factory wart) [DEFER]

3. VLM planner                                                   [x]
   3.1 Event-driven wake (queue-empty / reassess)                [x]
   3.2 Async off the control thread + single-flight guard        [x]
   3.3 Tolerant plan extraction (extractJsonArray)               [x]
       2026-08-09: the original first-'['-to-last-']' version was NOT actually tolerant --
       any stray bracket in the VLM's own prose (routine for Qwen3-VL describing what it
       sees) broke it, silently dropping a valid plan with no fallback; observed live as a
       drone stuck hovering ~2 min with no path to LAND. Rewritten to try each candidate
       bracket span and validate it as real JSON before accepting it. See docs/NOTES.md.
       Same day, better fix: llama-server's response_format/json_schema forces the model to
       emit ONLY a JSON array at the sampling level (verified empirically, then wired into
       llamaclient.hpp) -- extractJsonArray is now a backstop, not the primary defense. Live
       flight the same night with this change: 0 parse failures, full mission succeeded
       (takeoff/search/approach/land all _ok). See docs/NOTES.md.
   3.4 Dynamic prompt (state + history + perception JSON)        [x]  fed by PerceptionRuntime (4.2)
   3.5 Context budget FORK-A (-c 4096, max_tokens 512)           [x]
   3.6 System-prompt: APPROACH entry + interrupt text            [x]
   3.8 System-prompt: explicit failure-status replanning rule    [x]  2026-08-09: EXECUTED COMMAND
       HISTORY already carried real failure strings (search_exhausted, orbit_lost_failed, ...) but
       the model was never told they meant anything -- pure luck whether it noticed. Added DECISION
       RULE 9. Internally, TaskState::FINISHED_FAIL is still dead code (completeCurrent() always sets
       FINISHED_SUCCESS); a code-level failure-streak escalation (mirroring the interrupt-storm one)
       is a real option if rule 9 alone proves insufficient -- open, see docs/NOTES.md.
   3.9 Prompt-trim: drop grammar-enforced prompt scaffolding      [ ]  [DEFER, low-urgency]
       2026-08-11 (agent3): the GBNF grammar (buildPlanGrammar, llamaclient.hpp:111)
       now enforces the plan's JSON shape, thought-first ordering, the verb enum, and
       takeoff-first at the sampling level (docs/NOTES.md 2026-08-10). Two older prompt
       pieces are now redundant with it: the OUTPUT FORMAT block (llm_base.hpp:132) and
       the dynamic "your plan MUST start with {"action":"takeoff"}" line
       (fmu_node.hpp:1787). Trimming them shortens the prompt. The payoff is small: it
       only speeds the FIRST plan, and the grammar already guarantees the shape, so this
       is a cleanup, not a fix -- hence low-urgency. Keep the thought's 3-part content
       guidance (feasibility / flight strategy / landing-clearance). The grammar bounds
       that string's length but not its meaning, so only the structural scaffolding is
       safe to cut.
   3.7 Multi-takeoff / VLM-signalled mission end                 [DEFER]  (POC: LAND = end)

4. Perception                                                    [~]  vision lib done + FMU-integrated; APPROACH (5) next
   4.1 Vision lib (/root/build_yolo, vision/)                    [~]  mostly built
       4.1.1 YoloSegEngine (wraps yolos::seg)                    [x]
       4.1.2 YoloDepthEngine (wraps yolos::depth)                [x]
       4.1.3 fuse() to PerceptionSnapshot, per-det median depth  [x]
       4.1.4 canonical types (global TargetDetection /           [x]
             PerceptionSnapshot, 16 dets, median_depth_cm)
       4.1.5 export + quantization fp32/int8/int4                [x]  see findings below
       4.1.6 ORT thread cap (numThreads patched into YOLOs-CPP)  [x]
       4.1.7 benchmark sweep (py + C++)                          [x]
       4.1.8 PERF GAP: seg AND depth both miss target              [~]  OPEN
             corrected 2026-08-07 -- see Perception findings below + BUILD_YOLO/README.md
             for current numbers and methodology (not duplicated here).
             4.1.8a decouple depth onto its own slower loop      [ ]  accepted interim fix
             4.1.8b depth backbone swap decision                 [DEFER]  only after real-world obs
             4.1.8d survey alternative monocular-depth models    [ ]  scheduled ~2026-08-08;
                    both seg+depth miss target -- evaluate faster depth backbones as input to
                    4.1.8b and to the emergency-boundary (6.1) refresh-rate budget.
             4.1.8c re-measure on AVX2 laptop (cannot rely on)   [ ]
   4.2 FMU-side integration (PerceptionRuntime)                  [x]
       4.2.1 vendor/link vision lib (CPM, like sttserv)          [x]
       4.2.2 perception thread(s): seg loop + DECOUPLED depth    [x]
       4.2.3 atomic PerceptionSnapshot to prompt JSON            [x]
             (label / bbox / median_depth_cm per ARCH 6)
       4.2.4 drop FMU stub TargetDetection (fmu_node.hpp:168);   [x]
             name-clashes with the vision lib's global type
       4.2.5 thread / affinity budget vs the 20 Hz loop          [x]
             (kVisionSegThreads/kVisionDepthThreads ORT intra-op cap)
             Human follow-up open: build verify + SITL smoke test (not run by this session).

5. Visual servoing (the navigation pivot)                        [~]  APPROACH SITL-verified
   5.1 APPROACH <label>  (spec: specs/2026-08-05-visual-servoing-approach-design.md) [x]
       5.1.1 detectionByLabel lookup (ROS-free)                  [x]
       5.1.2 yaw-center + range-decel servo, recomputed per tick [x]
       5.1.3 done at standoff / lost = FAIL                      [x]
       5.1.4 tests (no YOLO needed)                              [x]  detection_query_test +
             canned rig (--canned-approach / projects/llm_to_action/test/sitl-legacy/approach/run.sh); SITL-verified both
             paths -- lost-target FAIL and reached-standoff approach_ok (2026-08-06)
       5.1.5 real-perception + VLM-driven end-to-end SITL         [~]  2026-08-06: real
             YOLO seg+depth (model paths were wrong since 4.2, never actually loaded
             until today -- fixed), real Qwen3-VL-2B planning, real detected object
             (vendored hatchback gz model). Servo itself works and completes; found +
             fixed along the way: FMU/PerceptionRuntime clock-epoch mismatch (bogus
             detection "age"), no motion-freshness gate on trusting a detection, class
             label drift on the real model ("car"->"boat" on the same object), cruise/
             standoff tuned for real depth noise. Outstanding: 6.4 (no collision check).
       5.1.6 APPROACH stop still trusts the depth backstop                [ ]  2026-08-08: the
             odometry travel-budget added this session is only a FAILSAFE -- in practice the depth
             backstop (median range < standoff) trips first, so stop distance is still governed by
             noisy depth (same car read 1.6-6.5 m tick to tick) and ends conservatively far. Once
             depth improves (4.1.8d) or 6.4's motion-check lands, make the travel budget primary
             and gate/drop the backstop for a tight, deterministic stop.
   5.2 live-YOLO GO (recompute direction per tick, drift-free)   [ ]
   5.3 landmark-relative safe landing ("go over spot", land)     [ ]

6. Safety / failsafe                                             [~]  6.2 SITL-verified; 6.1/6.3/6.4 code landed 2026-08-08, build+SITL pending
   6.1 Emergency boundary (velocity-scaled trigger distance)     [x]  SITL-verified (boundary 37 trips); +free-space depth for walls; thin/edge blind spot -- see spec-1 final review
   6.2 Battery / failsafe supervisor + user override (ARCH 11)   [x]  real PX4 battery bridge; 20%->RTH / 10%->land-in-place (latched); reversible manual override; SITL-verified 2026-08-08. Smart RTH deferred -> docs/scheduled/2026-08-07-battery-rth-energy-terrain-subsystem.md
   6.3 Interrupt storm / max-retries -> escalation prompt        [x]  SITL-verified escalation (escalated=1); VLM recovery model-limited (2B)
   6.4 APPROACH "reached" motion-gate (reject impact frames)     [x]  SITL-verified (approach-impact); underlying approach quality open (5.1.5/spec-4)
       (2026-08-06, live VLM run): a physical hit produced yawrate=6.9 rad/s and
       vertical vel -1.75 m/s (vs commanded ~-0.10 yawrate) and altitude collapsed
       0.99m -> 0.02m in ~1s -- APPROACH read range=1.83m off a frame taken during/
       after that impact and declared approach_ok. No check exists that a "reached"
       determination coincides with nominal (commanded-ish) vehicle motion. Fix (not
       yet implemented): reject "reached" if IMU/odometry is out of nominal range
       that tick; treat as INTERRUPT-worthy instead of silent success.
       Update 2026-08-08: the APPROACH servo now brakes on odometry, not depth -- it latches an
       early range as a fixed travel budget and dead-reckons the stop point, so a noisy depth
       frame can no longer re-accelerate into the target (docs/NOTES.md). Standoff also raised
       2.0 -> 3.0 m for margin against target parts protruding past the measured point. This is a
       PARTIAL mitigation only: it reconfirmed the range=1.83 hit on the pre-3.0 build, and the
       motion-sanity-check above is still unimplemented -- "reached" is still declared off a depth
       frame, so 6.4 stayed OPEN pending the motion-gate itself -- now landed and verified, see below.
       Update 2026-08-09: motion-gate IMPLEMENTED + SITL-verified. approachMotionNominal() checks
       yaw-rate and vertical velocity at the "reached" tick; off-nominal -> APPROACH raises an
       approach_impact interrupt instead of approach_ok. The approach-impact test forces the gate
       off-nominal at the standoff and confirms it fires (impact interrupt, no false approach_ok) -- PASS.
       Standoff is now 2.5 m (operator-tuned, was 3.0). Also this session: a target lost within the hold
       margin of the dead-reckoned stop now finishes on odometry instead of holding for a re-lock that may
       never come (a permanent loss used to deadlock into approach_lost_failed); the two canned approach
       tests run in the `empty` world so a real obstacle can't trip the boundary before the synthetic stop
       completes. The gate MECHANISM is proven; whether a real collision drives odometry off-nominal enough
       to catch is the remaining real-world unknown -> 5.1.5.

7. Advanced navigation = "Being B"                               [DEFER]  horizon
   7.1 SLAM/VIO pose (Stella-VSLAM / OpenVINS, projects/slam/source/)     [~]  tracking verified live
         in SITL 2026-08-09 after an OpenMP threading fix -- best case 2 PASS/1 FAIL (spread_ratio
         0.60-0.86) with VLM idling, marginal not solid. SITL-only (clean Gazebo render), untested
         on real camera; not yet wired to control (B3 -- see docs/NOTES.md 2026-08-09).
   7.2 OctoMap occupancy from SLAM cloud + depth                 [ ]
   7.3 A* global planning over the OctoMap                       [ ]
   7.4 local-to-global tf2 anchor                                [ ]

8. Sim / tooling                                                 [~]
   8.1 PX4 Gazebo SITL (projects/llm_to_action/test/sitl/run.sh <scenario>)                [x]
   8.2 camera TX to RX to FMU proven                             [x]
   8.3 simenv.sh migration to llm_to_action binaries            [ ]  (ARCH 14/16)
   8.4 canned rigs (cross/speed)                                 [x]
   8.5 --image-min-tokens 1024 for grounding                     [ ]  hold until vision confirmed
   8.6 SITL feature test suite (15 tests) -- all green 2026-08-08 -> Test matrix below [x]

9. Housekeeping / debt                                           [~]
   9.1 branch push (feature-llm-driver synced to origin, 0 ahead/behind) [x]
   9.2 zero ../ includes                                         [x]
   9.3 ARCHITECTURE.md refreshed to reality                      [x]
   9.4 rename backend atomics m_posN/E/D (hold ENU now)          [DEFER]  cosmetic
   9.5 remove dead option GROUNDSTATION_BUILD_SYSTEM_BACKEND_TYPE [x]  removed 2026-08-07; confirmed gone from CMakeLists.txt's option list
   9.6 reconcile build.sh vs build.ps1 backend/test divergence   [x]
       build.sh now takes a 4th arg <backend> (px4|tello|all), builds only the
       selected backend into build/<cfg>/<lib>/<backend>/, and gates px4_backend/
       offboard_ctrl/gstreamer_gz_udp_tx (+ px4_msgs, gz-sim8) out of a tello build.
       build.ps1 now mirrors build.sh: same 4th <backend> arg, same nested
       build/<cfg>/<lib>/<backend>/ output. Backend/test parity restored.
   9.7 reconcile takeoff climb height (2 m node vs FMU)          [ ]  maybe moot post-ENU
   9.8 investigate ~20 s first-odometry handshake latency        [ ]  low priority
   9.9 reduce ~15 s first-frame latency (QoS/DDS/keyframe)       [ ]  low priority
   9.10 build.sh has no target selection -- "build" always builds ALL     [ ]
        (llama.cpp, every test, everything). Cost seen directly: verifying
        detection_query_test (5.1) required a full ~1min all-target rebuild.
        Proposal (not yet implemented): ./build.sh <cfg> <lib> configure/build
        [all/tests/bench], default "all", so a test-only iteration doesn't
        pay for the whole workspace. Touches build.sh AND build.ps1 (9.6).
   9.11 LAND has no flare -- constant kLandDescendVelEnu (-0.5 m/s) all the [x]
        way to ground contact, no deceleration near touchdown. Seen in SITL
        (5.1 APPROACH verification, both the FAIL-path and approach_ok-path
        runs): odometry shows a velocity/yaw spike right after force_disarm,
        consistent with a hard-ish touchdown. Pre-existing, not caused by
        APPROACH. Fix LANDED 2026-08-07: descent tapers from kLandDescendVelEnu to
        kFlareTouchdownVelEnu below kFlareStartAltEnu (soft touch). SITL-verified 2026-08-07:
        vLand tapered -0.500 -> -0.139 toward touchdown as altitude dropped, reached STANDBY. Refined
        2026-08-09 to a quadratic (t*t) taper -- brakes harder near the ground than the original linear
        ramp; operator-confirmed a softer touch.
        Regression test: `projects/llm_to_action/test/sitl-legacy/land-flare/filter.sh` captures all sim panes and asserts
        vLand tapers toward touchdown (not a constant -0.5).
   9.12 Landing altitude is height-above-origin, not AGL          [ ]  2026-08-07 terrain-land
        finding (the "AGL gap"): LAND/flare key on `od.pos.z` = height above the takeoff ORIGIN,
        not height above ground. Over uneven terrain the ground is not at z=0, so the flare taper
        (9.11) mis-triggers -- starts too early/late and "touchdown" can be declared above the
        slope or into it. Exposed by `--canned-terrain-land` + the Rubicon world
        (`projects/llm_to_action/test/sitl-legacy/terrain-land/`). Fix (open): key landing on a rangefinder / terrain-relative
        altitude, not origin-relative z.
   9.13 GO/forward travels off-commanded-heading in SITL          [ ]  2026-08-07 terrain-land:
        takeoff -> GO forward -> land, the drone tracked ~10-30 deg clockwise off the commanded
        forward axis ("not forward whatsoever") and, with the pre-flare hard descent, landed
        violently ~5 m short. Flare (9.11) softened touchdown and SafeLand (spec-2 / 5.3) will own
        the "land gently on a spot" symptom, but the heading drift on a plain GO is a separate,
        un-root-caused issue (SITL yaw/heading hold, or GO acting on a stale bearing). Not yet
        investigated.
   9.14 tuning constants are compile-time constexpr, not runtime drone config  [ ]  [GATE real-Tello]
        SITL vs real-Tello values differ; one binary can't serve both without a
        recompile. Spec: docs/scheduled/2026-08-08-runtime-drone-config-constants.md
   9.15 vlm/approach-real/override SITL scenarios need ~12GiB VRAM              [ ]  2026-08-09
        finding: LAUNCH_VLM=1 loads Qwen3-VL-2B (-ngl 99 -c 65536, full GPU offload,
        64k context) on top of the seg+depth ONNX perception models every scenario
        already loads -- confirmed ~12GiB on the operator's machine, too much for a
        laptop-class GPU. projects/llm_to_action/test/sitl-legacy/run_all.sh (A1) gets a SKIP_HIGH_VRAM=1 knob
        to skip these three; not a fix, just a documented escape hatch for
        constrained hardware. A real fix (smaller VLM quant, lower context, or a
        low-VRAM SITL profile) is unscoped.
```

---

## SITL test matrix (2026-08-08)

All 20 `projects/llm_to_action/test/sitl-legacy/<feature>/` runs are green in PX4 Gazebo SITL: the 15 baseline rows (operator-run, 2026-08-08) plus the 3 spec-1 + 2 spec-2 rows at the bottom, which were new the same day and have since run to PASS too (see their Status column) -- nothing in this matrix is still pending a run. **Type:**
Auto = `filter.sh` asserts PASS/FAIL from the captured log; Milestone = operator confirms the digest
against expected behavior. Per-run pane captures are git-ignored (regenerated each run).

| Test | Verifies | ROADMAP | Type | Status |
|------|----------|---------|------|--------|
| forward | takeoff -> GO 1m fwd -> land (FLU sanity) | 1.1.1 | Milestone | PASS |
| cross | 4-axis GO out-and-back 1m (frame sanity) | 1.1.1 | Milestone | PASS |
| speed | GO fwd+return at 15 vs 80 cm/s | 1.1.1 | Milestone | PASS |
| rotate-land | ROTATE 90 cw + 200 ccw granularity + land | 1.1.2 | Auto | PASS |
| land-flare | LAND flare taper (not a constant -0.5) | 9.11 | Auto | PASS |
| terrain-land | landing over uneven terrain | 9.12 | Diagnostic | PASS* |
| approach | closed-loop APPROACH on a synthetic detection | 5.1 | Milestone | PASS |
| approach-real | APPROACH with real ONNX seg+depth vs the car | 5.1.5 | Milestone | PASS |
| vlm | full Qwen3-VL-driven flight, no canned plan | 3 / 5.1 | Milestone | PASS |
| flood | startup queue flood stays bounded | 1.4 | Auto | PASS |
| flood-airborne | mid-air command storm stays bounded | 1.4 | Auto | PASS |
| battery | real PX4 drain -> our RTH failsafe | 6.2 | Auto | PASS |
| battery-rth | forced 18% -> RTH home + land | 6.2 | Auto | PASS |
| battery-landnow | forced 8% -> land-in-place | 6.2 | Auto | PASS |
| override | reversible manual takeover, failsafe outranks | 6.2 | Auto | PASS |
| boundary | emergency boundary trips + interrupts on a close obstacle | 6.1 | Auto | PASS (2026-08-08) |
| approach-impact | motion-gate rejects approach_ok on a collision | 6.4 | Auto | PASS (2026-08-08) |
| interrupt-storm | N trips in window -> escalation prompt, then reset | 6.3 | Auto | PASS escalation (2026-08-08); recovery is VLM-limited |
| orbit | ORBIT traces a full odometry circle around the real car | 1.1.6 | Milestone | PASS (--canned-orbit; SITL 2026-08-08) |
| search | SEARCH parallel-track lawnmower finds the car + notifies | 1.1.7 | Milestone | PASS (--canned-search; SITL 2026-08-08) |

\* `terrain-land` is a **diagnostic**: it lands over ground at a different height than takeoff to
expose that landing keys on `od.pos.z` (height above the takeoff origin), not AGL. It behaves as
designed and confirms the AGL gap (9.12); the rangefinder / terrain-relative-altitude fix is the
follow-up.

---

## Perception findings (build_yolo)

Full benchmark methodology, numbers, and analysis live in `/root/BUILD_YOLO/README.md`'s
`## Benchmarks` section (separate, intentionally modularized repo) -- not duplicated here. Targets:
seg <= 33 ms (30 Hz), depth <= 25 ms (40 Hz).

- **Current status: both seg and depth MISS target** at the best config found (static-384, 4
  threads, fp32). Measured seg roughly 50-70 ms (~1.5-2.1x over), depth roughly 87-116 ms
  (~3.5-4.6x over) -- separate reruns of the identical config disagree by more than expected noise
  (open question, see BUILD_YOLO/README.md), so treat these as ranges pending that being pinned
  down, not precise figures.
- **int8 (dynamic) fails to load entirely** in the C++ engine, both models, every thread count --
  not yet root-caused. Do not ship it.
- **Accepted plan (unchanged):** integrate as-is, depth runs on its own slower loop decoupled from
  seg (shipped, see 4.2.2). Seg needs the same scrutiny now that it's also confirmed missing
  target. Decide on a backbone swap once observed against real-world FMU load, not just synthetic
  benchmarks.

Implication for the FMU integration (4.2): the perception thread design is **two rates** from the
start (seg near 30 Hz, depth on a slower cadence), and the emergency boundary (6.1) must tolerate a
low depth refresh rate.

---

## Time estimate (very rough)

Assumption: continuous ("around the clock") pairing with Claude-opus-4.8 on High. Numbers are
**ideal focused engineering-days for the code**. The real wall-clock is dominated by
human-in-the-loop cycles that do not compress with model speed: SITL flight tests, real-Tello
hardware iteration, model retraining. Those are flagged.

| Objective block | Code effort | Notes / wall-clock gating |
|---|---|---|
| 4.2 FMU perception integration | 0.5-1 d | contract known; two-rate thread; SITL smoke test |
| 3.4 real perception JSON in prompt | folded into 4.2 | needs one vision-grounded SITL run |
| 5.1 APPROACH servo | 1-2 d | tests exist without YOLO; **SITL tuning loop** dominates |
| 5.2 live-YOLO GO | 0.5-1 d | shares APPROACH substrate |
| 5.3 safe-landing servo | ~0.5 d | downstream of 5.1/5.2 |
| 1.1.6/1.1.7 ORBIT + SEARCH | ~1 d | + SITL tuning |
| 6 safety/failsafe (6.1-6.3) | 1-2 d | needs battery in the backend interface; **SITL tuning** of constants |
| 3.6 prompt refinements | ~0.5 d | |
| 2.3 Tello hardware bring-up | 1-2 d code | **hardware-bound**: real flights, calibration, you-in-loop |
| 4.1.8 depth speed (decouple now / swap later) | 0.5 d now | backbone swap is its own multi-day research if taken |
| 8 sim/tooling | 0.5-1 d | |
| 9 housekeeping/debt | ~0.5 d | |
| **Subtotal: finish the POC (blocks 1-6, 8, 9)** | **~6-10 focused days** | wall-clock likely 2-4x that from SITL/hardware cycles |
| 7 Being B (SLAM + OctoMap + A*) | **2-4 weeks** | SLAM bring-up + calibration + mapping + planning + heavy real-world validation |

Headline: the **POC-completion path is on the order of one to two focused weeks of code**, with
wall-clock stretched by flight-test iteration. **Being B roughly triples the whole project** and is
the dominant unknown — it is research-grade integration, not plumbing.

Critical path to the next real capability:
**4.2 (FMU perception plumbing) -> 3.4 (real perception JSON) -> 5.1/5.2 (APPROACH + live-YOLO GO)**.
Everything in block 5 and most of block 6 gates on perception landing in the FMU.
(2026-08-20: for the GATE/Demo Day the perception stack runs STANDALONE — llm_cv_track/llm_cv_scene — NOT via the FMU. FMU-integrated perception is deferred with the rest of flight-core.)

# ============================================================================
# 2026-08-20 — GATE PASSED. Reassessment + Demo Day plan (~week of 08-25)
# ============================================================================
Timeline: today Thu 08-20. Integration-ready target Sat 08-22. RIGOROUS TESTING + feature tweaking
Sun 08-23 + Mon 08-24. Demo Day ~08-28. Land-platform integration ONLY if time remains after Monday.

## WHERE WE ARE (done / working)
- **STAR — archive/llm_cv_track/scene_omdet.py.** Voice -> OmDet-Turbo open-vocab detect (box follows) ->
  SAM2.1 mask -> Qwen3-VL Q&A, full chat-pane UI. Loads OmDet locally/offline in ~1s. Runs on webcam +
  drone RTMP. Validated headless; verified live at the gate (with fixes below). See llm_cv_track/README.md.
- **BACKUP — archive/llm_cv_scene.** Voice -> Qwen3-VL describes+localizes -> SAM2. 100% local, always
  loads. The safety net.
- **Static tools** — recognize_omdet.py (OmDet) + recognize.py (VLM): image + prompt -> boxes/masks + log.
- **Drone feed** — DJI RC2 + DJI Fly Custom RTMP -> MediaMTX -> RTSP -> app. Working.
- **Fixed this session** — OmDet offline load (was hanging on HF); VLM off the ASR thread (no voice
  bottleneck); vlm.ask not analyze for Q&A (no JSON garbage); os._exit clean exit; tmux teardown;
  ASR_CAPTUREID=5 mic; whole-frame garbage-mask guard.

## NOT DONE / GAPS (honest)
- **Persistent tracking through occlusion.** follow.py (BoT-SORT + colour re-id) is fragile (look-alikes,
  ID churn). Parked. Needs OSNet re-id to be demo-worthy.
- **Full AGPL escape.** OmDet is Apache, but YOLO26 background + SAM2 + BoT-SORT are Ultralytics/AGPL.
  Productization needs permissive replacements (D-FINE bg, a permissive tracker). Not a Demo Day blocker.
- **Control side (command -> platform).** The perception demo does NOT fly/drive anything yet; flight was
  cut for the gate. Real drone control (llm_to_action DjiBackend over the real link) is separate,
  unfinished work — see docs/specs/spec-dji-endtoend-bringup.md.
- **Live reliability** under demo conditions (stream drops, mic, warmup) is only lightly hardened.

## DEMO DAY PLAN
### Track A — harden the perception demo  [PRIORITY 1, Sun+Mon]
- Repeated full live run-throughs on the drone; fix whatever breaks live. [Sun, ongoing]
- ASR reliability: confirm ASR_CAPTUREID, mic gain, handle empty-transcript gracefully. [~2h]
- Highlight tuning: mask-rate throttle, optional multi-object, update-rate feel. [~2h]
- Robustness: stream-drop recovery, pre-warm script, stale-llama guard (pkill+relaunch if hung). [~2h]
- Rehearse the pitch: 3-layer story (YOLO context / OmDet open-vocab / VLM reasoning) + star-vs-backup. [Mon]

### Track B — platform-agnostic proof  [PRIORITY 2, cheap]
- Run the SAME stack on THREE feeds with no new hardware: DJI drone (RTMP) + webcam + a phone/IP camera
  (RTSP/GStreamer). One brain, three platforms -> proves agnosticism for the judges. [~1h]

### Track C — land platform (DJI RoboMaster) — STRETCH ONLY, see assessment below.

## LAND PLATFORM ASSESSMENT — DJI RoboMaster (S1 / EP)
Question from the human: worth pursuing to show platform-agnostic nature? (Tello burned us: limited SDK,
more problems than solutions.) Realistic take:

**Technically: yes, it is a genuinely good target — far better than the Tello.**
- The RoboMaster **EP / EP Core** ship the OFFICIAL open Python + plaintext SDK
  (github.com/dji-sdk/RoboMaster-SDK): chassis motion control, gimbal, **video streaming (H.264)**, audio,
  intelligent-ID APIs; runs INDEPENDENTLY of the DJI app (unlike Tello's thin SDK). **The S1 ships with
  the SDK DISABLED** -- DJI never released it for the S1 officially. The S1 needs a community root/unlock
  (sandbox escape in the app's Lab), which DJI patched in later firmware -> unlock only works on
  compatible/older firmware. Verified 2026-08-26; field kit + scripts in `source/robomaster/`.
  Once unlocked the S1 speaks the SAME plaintext SDK as the EP (TCP 40923 control, 40921 H.264).
- Connectivity: WiFi (direct AP or router) or USB. Video-in is trivial for us (SDK stream -> our
  perception). A community simulator (github.com/jeguzzi/robomaster_sim) lets us develop with NO hardware.
- **Scope clarified by the human (2026-08-20): the RoboMaster demo would be SIMPLE** — the same voice + CV
  we show on the drone, just pointed at the RoboMaster's camera. NOT autonomous ground control. So the work
  is mostly **video-in**: take the SDK's H.264 stream into the existing perception stack (scene_omdet), the
  same way the drone's RTMP feed does. Little/no new control code. Do it on a FEATURE BRANCH; migrate only
  what fits without changing/breaking the working system.
- That makes it a CHEAP stretch (~a few hours: SDK video-in + a GStreamer/RTSP shim + a live test), not a
  control project. The Tello risk (flaky SDK) is largely gone with the RoboMaster's open Python SDK.

**Recommendation:** still a STRETCH, but a cheap one. Pursue if the core drone demo is solid AND an EP unit
is in hand. Path: (1) get the SDK video stream into our RTSP/GStreamer input (trivial), (2) run scene_omdet
against it + a live voice test, (3) done — that already proves "same perception brain, different platform."
Develop video-in against robomaster_sim first if no unit yet. Keep it on a feature branch so it can't
destabilize the Demo Day build. If no unit / no time, prove agnosticism with drone+webcam+phone.
Sources: dji-sdk/RoboMaster-SDK (GitHub), dji.com/robomaster-s1/programming-guide, jeguzzi/robomaster_sim.

---

## 2026-08-25 — MVD INTEGRATION DONE (voice -> router -> DJI + smart CV)

Full detail + command table + next tracks: `docs/active/2026-08-25-mvd-integration-handoff.md`.
The `projects/integration/` MVD is **DONE and considered effective**. Demo-Day system is the perception +
voice-controlled drone stack (NOT the FMU/`llm_to_action`, which stays DEFERRED as the destination product).

- [x] 4-tier deterministic router (EMERGENCY>OVERRIDE/RESUME>BASIC>COMPLEX), voice + phone ASR.
- [x] Full `dji_wire.py` DJI REST client (all `/c/fly` mission actions, `/key`, `/tts`, `/status`).
- [x] Expanded verbs: spin, scan/search (orbit OUTWARDS/INWARDS), track/follow/come_home (phone-GPS),
      gimbal look forward/down/up, wave, directionals -> native `fly_by`, `go <unknown>` no-op guard.
- [x] `stop` = `POST /c/fly [{delay:0}]` (preempts + keeps control); `manual`/`resume` = RC handoff/pop.
- [x] Phone->GS ASR channel (`phone_ears.py`, `/input` + raw TCP, matches the app), receipt logging.
- [x] TTS out (`voice.py`): phone `/tts` + laptop espeak; LONG (screen) / SHORT (spoken) split.
- [x] Perception hardened: OmDet offline load, executor starvation, VLM `-np 1`, VLM `:18090`, video
      watchdog/doctor, live `[dji]`/`[phone_ears]`/`[voice]` logging. 7 router tests pass.
- [x] Self-contained `projects/integration/` (no llm_cv_scene/llm_cv_track traces).

- [ ] `[GATE]` **BACKEND (DJI app dev):** dynamic groundstation-IP discovery; fix gimbal commands
      (broken backend-side; `fly_by` works); `ApiServerService` foreground-service reliability.
- [DEFER] laptop TTS `apt install espeak-ng` (tomorrow; phone `/tts` works; must not break integration/*).

**Next tracks (Demo Day = Thu 2026-08-27):** (1) pitch prep around the working MVD; (2) `llm_to_action`
assessment + possible end-to-end VLM flight (connect current Python perception to the C++ FMU);
(3) Robomaster backend + acquisition (S1 has no remote SDK -> buy EP/EP Core; video-in is the cheap
path); (4) diagnostic dashboard (spec only — youtu.be/vO6SWG-jxvE ~1:25; consumes the stdout logging).
