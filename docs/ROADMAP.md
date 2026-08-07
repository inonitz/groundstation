# Groundstation Roadmap and Objective Tree

Living, consolidated list of every goal for the project, recursively, with status. This is the
single place the whole objective set lives; it was previously scattered across `NOTES.md`,
`ARCHITECTURE.md`, and the specs under `specs/`. Keep it updated as reality moves.

Status legend: `[x]` done, `[~]` partial / WIP, `[ ]` todo, `[GATE]` blocked on a dependency,
`[DEFER]` deliberate later horizon.

Last synced: 2026-08-06 (after the GenericBackend interface build-verify + the build_yolo perception
benchmark results landed).

---

## Objective tree

```
ROOT: Off-board VLM-driven autonomous drone (Tello primary, PX4 SITL fallback)
      "VLM plans, deterministic math executes"

1. Flight core / FMU                                              [~]
   1.1 20 Hz deterministic control loop                          [x]
       1.1.1 GO guidance (carrot-chasing cross-track)            [x]  further tuning [DEFER, visual servo]
       1.1.2 ROTATE                                              [~]  parser + yaw law LANDED
             2026-08-07 (was scaffolding-only / silently dropped): added a rotate parse branch
             (direction + angle_deg), a CommandID::ROTATE dispatch that freezes the target
             heading, and a clamped-P-yawrate movement branch done within kRotateCompletionDeg.
             Code landed, SITL-verify pending (human).
       1.1.3 TAKEOFF state machine (arm, climb, FLIGHT)          [x]
       1.1.4 LAND state machine (descend, force-disarm)          [x]
       1.1.5 STOP / Hover                                        [x]
       1.1.6 ORBIT (target-anchored)                             [ ]  [GATE perception]
       1.1.7 SEARCH (2D circle)                                  [ ]  [GATE perception]
       1.1.8 CURVE                                               [dropped for POC]
   1.2 ENU convention (Task 4)                                   [x]  operator SITL re-gate [ ] (human)
   1.3 Offboard streaming ~100 Hz (collapsed into backend)       [x]
   1.4 SPSC task queue (moodycamel) + backpressure               [~]  backpressure path unverified
   1.5 Interrupt + reflexive hold-clearance (ARCH 5.1)           [ ]  [GATE depth]

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
   3.4 Dynamic prompt (state + history + perception JSON)        [x]  fed by PerceptionRuntime (4.2)
   3.5 Context budget FORK-A (-c 4096, max_tokens 512)           [x]
   3.6 System-prompt: APPROACH entry + interrupt text            [x]
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
             canned rig (--canned-approach / simenv_llm.sh approach); SITL-verified both
             paths -- lost-target FAIL and reached-standoff approach_ok (2026-08-06)
       5.1.5 real-perception + VLM-driven end-to-end SITL         [~]  2026-08-06: real
             YOLO seg+depth (model paths were wrong since 4.2, never actually loaded
             until today -- fixed), real Qwen3-VL-2B planning, real detected object
             (vendored hatchback gz model). Servo itself works and completes; found +
             fixed along the way: FMU/PerceptionRuntime clock-epoch mismatch (bogus
             detection "age"), no motion-freshness gate on trusting a detection, class
             label drift on the real model ("car"->"boat" on the same object), cruise/
             standoff tuned for real depth noise. Outstanding: 6.4 (no collision check).
   5.2 live-YOLO GO (recompute direction per tick, drift-free)   [ ]
   5.3 landmark-relative safe landing ("go over spot", land)     [ ]

6. Safety / failsafe (designed, unimplemented)                   [ ]
   6.1 Emergency boundary (velocity-scaled trigger distance)     [ ]  [GATE depth]
   6.2 Battery / failsafe supervisor + user override (ARCH 11)   [ ]  needs battery field in the backend interface
   6.3 Interrupt hysteresis + max-retries then land/abort        [ ]
   6.4 APPROACH "reached" has no motion sanity check             [ ]  real SITL collision
       (2026-08-06, live VLM run): a physical hit produced yawrate=6.9 rad/s and
       vertical vel -1.75 m/s (vs commanded ~-0.10 yawrate) and altitude collapsed
       0.99m -> 0.02m in ~1s -- APPROACH read range=1.83m off a frame taken during/
       after that impact and declared approach_ok. No check exists that a "reached"
       determination coincides with nominal (commanded-ish) vehicle motion. Fix (not
       yet implemented): reject "reached" if IMU/odometry is out of nominal range
       that tick; treat as INTERRUPT-worthy instead of silent success.

7. Advanced navigation = "Being B"                               [DEFER]  horizon
   7.1 SLAM/VIO pose (Stella-VSLAM / OpenVINS, source/slam/)     [~]  scaffolding only
   7.2 OctoMap occupancy from SLAM cloud + depth                 [ ]
   7.3 A* global planning over the OctoMap                       [ ]
   7.4 local-to-global tf2 anchor                                [ ]

8. Sim / tooling                                                 [~]
   8.1 PX4 Gazebo SITL (simenv_llm.sh vlm/canned)                [x]
   8.2 camera TX to RX to FMU proven                             [x]
   8.3 simenv.sh migration to llm_to_action binaries            [ ]  (ARCH 14/16)
   8.4 canned rigs (cross/speed)                                 [x]
   8.5 --image-min-tokens 1024 for grounding                     [ ]  hold until vision confirmed

9. Housekeeping / debt                                           [~]
   9.1 branch push (feature-llm-driver synced to origin, 0 ahead/behind) [x]
   9.2 zero ../ includes                                         [x]
   9.3 ARCHITECTURE.md refreshed to reality                      [x]
   9.4 rename backend atomics m_posN/E/D (hold ENU now)          [DEFER]  cosmetic
   9.5 remove dead option GROUNDSTATION_BUILD_SYSTEM_BACKEND_TYPE [ ]
   9.6 reconcile build.sh vs build.ps1 backend/test divergence   [ ]
   9.7 reconcile takeoff climb height (2 m node vs FMU)          [ ]  maybe moot post-ENU
   9.8 investigate ~20 s first-odometry handshake latency        [ ]  low priority
   9.9 reduce ~15 s first-frame latency (QoS/DDS/keyframe)       [ ]  low priority
   9.10 build.sh has no target selection -- "build" always builds ALL     [ ]
        (llama.cpp, every test, everything). Cost seen directly: verifying
        detection_query_test (5.1) required a full ~1min all-target rebuild.
        Proposal (not yet implemented): ./build.sh <cfg> <lib> configure/build
        [all/tests/bench], default "all", so a test-only iteration doesn't
        pay for the whole workspace. Touches build.sh AND build.ps1 (9.6).
   9.11 LAND has no flare -- constant kLandDescendVelEnu (-0.5 m/s) all the [~]
        way to ground contact, no deceleration near touchdown. Seen in SITL
        (5.1 APPROACH verification, both the FAIL-path and approach_ok-path
        runs): odometry shows a velocity/yaw spike right after force_disarm,
        consistent with a hard-ish touchdown. Pre-existing, not caused by
        APPROACH. Fix LANDED 2026-08-07: descent tapers from kLandDescendVelEnu to
        kFlareTouchdownVelEnu below kFlareStartAltEnu (soft touch). SITL-verify pending.
```

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
