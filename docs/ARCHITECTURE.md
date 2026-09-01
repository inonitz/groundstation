# Groundstation — FMU Architecture Specification

> **Status:** IMPLEMENTED / LIVING SPEC. The committed FMU now implements this architecture
> (20 Hz control loop, odometry, event-driven VLM, ENU convention, GenericBackend interface, canned test
> rigs). `NOTES.md` is the running change log. Sections below are annotated where reality has
> moved past the original plan; the remaining gap is Tello hardware bring-up and SLAM-based position (§15). Reactive safety
> (interrupt + emergency boundary + APPROACH motion-gate, Spec 1) and the ORBIT / SEARCH motion verbs
> (Spec 2) shipped and are SITL-verified (2026-08-09); live-YOLO GO and safe-land stay deferred.
>
> **Scope:** `FlightManagementUnitNode` (`projects/llm_to_action/source/fmu/`) — high-level VLM
> planner + deterministic 20 Hz control loop, plus an in-process offboard translator (§7).
> Primary target = **DJI drone** (Tello DROPPED 2026; video via DJI Fly Custom RTMP); PX4 SITL for flight-core dev. NOTE (2026-08-20): the gate/Demo-Day demo is the STANDALONE **perception stack** (see the 'Perception stack' section at the end + archive/llm_cv_track/README.md) — a parallel subsystem to this FMU, which is currently DEFERRED. See docs/ROADMAP.md CURRENT PHASE banner.

---

## 0. Forks Status

> **Update:** since this spec was written the FMU was implemented and several forks closed.
> FORK-A tuned (`-c 4096`, client `max_tokens 512`); FORK-B realized as the GenericBackend
> `Odometry` ENU convention; FORK-C collapsed into the concrete backends (no separate offboard node).
> The bullets below keep the original reasoning for history.
>
> **Update (2026-08-06):** the live launch harness (`projects/llm_to_action/test/sitl/run.sh <scenario>` over `projects/llm_to_action/test/lib/sim_core.sh`) invokes
> `llama-server` with `-c 65536`, not the `-c 4096` this doc and §16 originally marked DONE.
> This is a deliberate temporary overshoot (user-confirmed) -- generous headroom to avoid
> context-blowup failures while the rest of the stack (perception, APPROACH) is still under
> active test, not a tuned value. **Still open:** properly measure real per-call token usage
> and right-size `-c` for the actual target hardware (a low-end machine, not the dev box this
> was tuned against) -- 65536 is not the intended shipping number.

- **[FORK-A] VLM context — TUNED.** Strategy confirmed: manual context, zero-shot
  every call (KV never grows past `-c`; ~2.5–3 GB fits ~3 GiB). **But `-c 1024` cannot hold
  one shot:** `kSystemPrompt` alone ≈ 1.2–1.6k tokens, + image (~256–1024) + output.
  Resolution → raise `-c` to ~4096 (VRAM permitting, measure) **and/or** compress hard
  (trim system prompt ~60–70%, downscale image, 1–2 line history summary, small output cap).
  **Live script currently uses `-c 65536`** (deliberate temporary headroom during testing,
  not tuned -- see the Update note at the top of §0). Right-sizing `-c` for the real target
  hardware is still open.
- **[FORK-B] Odometry — RESOLVED (backend interface realized).** Consume `px4_msgs/VehicleOdometry` (NED) **directly**
  for sim. **⚠ MUST be migrated to a cross-hardware odometry abstraction** — the Tello does
  not publish `VehicleOdometry`; its driver dead-reckons `nav_msgs/Odometry` (§8).
- **[FORK-C] Offboard collapse — RESOLVED.** (a) Phase 1 reuses the existing
  `px4_offboard_node` (re-enable Twist+Bool subs), collapse in Phase 2; or (b) collapse now.
  Target architecture is the in-process translator either way (§7).

---

## 1. Design Goals

- **Off-board compute.** Drone is a dumb peripheral; all planning/perception/control on the
  ground station.
- **VLM plans, math executes.** VLM produces plans; never in the per-command completion loop.
- **Hardware-agnostic.** DJI drone (Tello DROPPED 2026), PX4 SITL for flight-core dev; the perception stack ingests any video source (RTMP/webcam/GStreamer). One generic setpoint + one
  odometry abstraction (cross-hw migration pending, §8).
- **No heap in steady state.** Fixed-size command structs, SPSC task queue, atomic flags.
- Constraints: no `std::variant`/exceptions/mutex-on-image; C89 hoisting; `FixedStringType`;
  enums one-per-line ≤95 cols.

---

## 2. Thread Architecture

`MultiThreadedExecutor` + callback groups. Threads: **YOLO-Seg (Model-S, ~30 Hz, meets
target)**, **Depth (Model-D, ~13 Hz measured -- the slow one, not a real 40Hz refresh)**,
**VLM (async, event-driven)**, **Control (20 Hz)**, and the **Offboard publisher (30 Hz PX4 /
20 Hz Tello)** streaming setpoints via the backend (§7). Shared state is `std::atomic`:
`m_flightState`, `m_missionActive`, `m_planning`, `m_frameCount`, `m_currImg`, latest pose,
perception snapshot. The **battery/failsafe supervisor + manual override (§11) are now
implemented** (Spec 3, SITL-verified). The emergency boundary (§10) and the interrupt reflex
(`m_emergencyStop`) remain designed, not implemented (§15).

---

## 3. Data Flow & Queue

```
VLM plan (JSON) ── translateToBaseCommands() [VLM thread = PRODUCER]
   ▼
m_taskQueue (moodycamel::ReaderWriterQueue<ActiveTask>, FIFO, SPSC) ── pending
   ▼ try_dequeue() [20Hz loop = CONSUMER]
m_currTask (active) ── completion (§4) ──► m_completedTasks (history §6)
                    └─► setpoint ──► offboard thread (30Hz PX4 / 20Hz Tello) ──► drone
```
- No "ReadyToPublish" queue. Strictly SPSC (VLM produces, 20 Hz consumes). Interrupt drain
  is consumer-side (§5.1). **Enqueue backpressure shipped** (Spec 3): bounded `try_enqueue`,
  reject-newest, every drop logged.

---

## 4. Deterministic Task Completion (20 Hz loop)

The FMU owns the flight **state machine** (STANDBY/TAKEOFF/FLIGHT/LANDING); the translator
(§7) is dumb. On completion: record `m_currTask` (with `thought`) → `m_completedTasks`, dequeue.

| Cmd | Predicate | Notes |
|-----|-----------|-------|
| **GO** | 3-D Euclidean dist < **0.20 m** | **One law, shipped:** carrot-chasing cross-track guidance -- line-of-sight direction frozen at activation + a cross-track PID pulling back onto the line (`vel = dir·speed`). Neither `go_vel` nor `go_pos` exists as a name; there is no separate discrete-XYZ impl. |
| **APPROACH** | `range < kApproachStandoffM` (3.0 m) | **Shipped + SITL-verified on real YOLO (ROADMAP 5.1/5.1.5).** Anchored to a live YOLO detection, recomputed every tick (no world point stored): yaw-to-center + range-decel forward + vertical match + lateral damp. Two-threshold fresh/lost model (§9/spec) coasts on a stale detection, FAILs on a fully lost one past `kApproachLostTimeoutMs`. Braking is on a dead-reckoned odometry travel budget (latched from an early median range), not on noisy per-tick depth. |
| **ROTATE** | \|yaw − target\| < **5°** | **Shipped + SITL-verified (ROADMAP 1.1.2).** Parsed from the VLM plan (`direction`+`angle_deg`); the accumulated-angle law integrates swept angle in the commanded direction, so it is granular and correct for ≥180°/360° (not shortest-path), completing within `kRotateCompletionDeg`≈5°. |
| **TAKEOFF** | FMU state machine: arm → climb to target → FLIGHT | Completion = odom altitude ≥ target. Reconcile climb height (offboard node hardcodes 2 m). Stall guard (ceiling-blind). |
| **LAND** | FMU state machine: descend → force-disarm near ground | Odom alt≈0 ∧ vz≈0. **Flare shipped (ROADMAP 9.11):** descent tapers from `kLandDescendVelEnu` to `kFlareTouchdownVelEnu` below `kFlareStartAltEnu`. Depth estimator gated OFF only in final 10–30 cm, after clear-to-land. WHERE-to-land = planning, separate. |
| **STOP** | one hover cycle → instant | Near-redundant; kept for VLM expressiveness. |
| **ORBIT** | swept angle ≥ target OR lock timeout | **Shipped, parsed from the VLM plan (`fmu_node.hpp` `action == "orbit"`), live-VLM-verified 2026-08-09** (real Qwen3-VL flight, not canned): locks a fixed odometry center from a detection, then flies a pure-odometry circle at that radius while vision only aims the camera -- vision never touches the path. Lost lock past `kApproachLostTimeoutUs` → `orbit_lost_failed`. |
| **SEARCH** | success = detected above `kSearchMinConfidence`; fail = lane cap or timeout | **Shipped, parsed from the VLM plan (`fmu_node.hpp` `action == "search"`).** Parallel-track (lawnmower) sweep, `kSearchMaxLanes` lanes capped so it always terminates. On failure (`search_exhausted`) the drone now flies back to its SEARCH-activation pose before completing (fixed 2026-08-09 -- previously left the drone wherever the last lane ended). Known gap, not yet fixed: the swept area is a fixed-size grid computed once at activation, blind to the room's actual size/shape -- see `docs/NOTES.md` 2026-08-09. |
| **CURVE** | — | Dropped for POC. Also not parsed from the VLM plan (silently dropped before enqueue), on top of being scoped out. |

**20 Hz streaming contract:** active task → setpoint; queue empty → Hover. Never send once.

> **Frame (realized):** completion predicates + setpoints are evaluated under the canonical
> **ENU convention** (Task 4 done): TAKEOFF climbs to `+kTakeoffTargetAltEnu`, LAND descends to
> `≤ kGroundContactEnu`, GO uses `flu_to_enu(relFlu, yaw)`. NED exists only on the PX4 wire.

---

## 5. VLM: Event-Driven

Triggers: queue empty, `re-assess`. **No `condition_variable`; no `m_emergencyStop`** (that
trigger describes the unimplemented emergency boundary, §10/§15). Wake is poll-based: every
20Hz `controlLoop()` tick, if the task queue is empty, calls `maybePlan()`, which checks a
cooldown + an `m_planning` single-flight atomic guard, then fires the VLM call on
`std::async` (off the control thread) so the 20Hz loop never blocks on inference.

### 5.1 Interrupt & Reassessment (deterministic-first)

**✓ Implemented (Spec 1, SITL-verified 2026-08-09).** Shipped as a hover-then-stash reflex:
`raiseInterrupt(reason)` hovers the vehicle, copies `m_currTask` into `m_stashedTask`
(`m_hasStashed=true`), clears `m_hasActive`, and lets the next VLM plan land normally --
the stash is surfaced in the prompt (`[INTERRUPT] reason=... stashed=...`) but never
auto-resumed. Evidence: `INTERRUPT (reason=...) stashed=... hover+reassess` in the
boundary/approach-impact SITL logs. This is a different concrete mechanism than the
`TaskState::STOPPED` enum value named below -- `STOPPED` is declared but never assigned
anywhere in the tree; the stash flag does that job instead, and `STOPPED` is dead code.

1. **Reflexive hold-clearance (control loop, no VLM).** `target = pos + reverse_vec·backoff`,
   `reverse_vec = -normalize(recent velocity)`, `backoff ≈ 20–30 cm`. Actively holds clearance
   vs hover overshoot. **Requires internal state:** short last-velocity history (also feeds §8).
2. **Consumer drains the queue**, stashes the interrupted task (+`thought`). SPSC-safe.
3. **Wake VLM** with: what it was doing, what was queued, depth map + segmented hazard frame.
4. **Producer refills** the empty queue; loop resumes.

---

## 6. Dynamic Prompt Construction

> **⚠ Governed by FORK-A.** At `-c 1024` the prompt must be compressed hard; history is a
> short summary, not the full log, unless `-c` is raised.

Sections, as actually built in `buildDynamicPrompt()`: system prompt · FLU coordinate frame ·
mission objective · vehicle state (`alt_up_m`/`speed_mps`/`airborne`) · perception JSON
(label/bbox/confidence/median_depth from snapshot §9) · executed command history
(`{status,thought,id}`). **No active-pending-queue section exists** -- the queue is drained
before the VLM is ever woken (§5), so there is nothing pending to list.

- **`status` carries real failure information, and the system prompt now says so.**
  `completeCurrent()` stores whatever status string the caller passes (`search_exhausted`,
  `orbit_lost_failed`, `approach_lost`, ...; anything not ending `_ok` is a failure) but
  `TaskState::FINISHED_FAIL` itself is declared and never assigned -- every task is internally
  marked `FINISHED_SUCCESS` regardless of outcome, so nothing downstream can filter on task
  state, only on the free-text string. Until 2026-08-09 the system prompt never told the model
  these non-`_ok` strings existed or meant anything; DECISION RULE 9 (`fmu/llm_base.hpp`) now
  spells this out explicitly. See `docs/NOTES.md` 2026-08-09.

- **Send the raw, unmarked camera frame** (JPEG-encoded, resized to 640x640) AND the
  perception JSON as text -- there is no bbox/label drawing onto the image; "marked image"
  describes a future annotated-frame option, not what ships. Preserve `thought`
  (`LargeFixedStringType m_thought`, `status`-prefixed). Targets addressed by `label`/`id`.

---

## 7. Setpoint Output — In-Process Offboard Translator

> **STATUS (realized):** collapsed. The translation this section specced now lives inside the
> concrete backend (`PX4Backend` → PX4 wire; `TelloBackend` → `rc`/`go`), selected at compile
> time via the `GenericBackend` interface. No separate offboard node/process; the FMU owns the flight
> state machine and calls `backend->set_velocity(...)` in the canonical ENU frame.

**Target (points 3 & 5):** the offboard controller is a **dumb `OffboardTranslator` struct**
(generic setpoint → PX4 `VehicleCommand`/`TrajectorySetpoint`, or Tello `rc`/`go`), driven by
a publisher thread inside the FMU process, at **30Hz for PX4** (`kOffboardPublishRateHz`,
`px4_backend_base.hpp`) and **20Hz for Tello** (`kTelloStreamRateHz`, Tello can't reliably
ingest setpoints above ~20Hz). No separate ROS node/process. The **flight state machine lives
in the FMU**, not the translator.

- Translation reference already exists in `px4_offboard_node`: ENU/FLU→NED flip
  (`external_velocity_callback`), OFFBOARD mode set, arming, high-rate velocity streaming, PX4
  best-effort/transient-local QoS. Extract this logic into the translator.
- **FORK-C sequencing:** Phase 1 *may* keep the existing node (re-enable its Twist+Bool subs,
  FMU publishes to them) to fly fastest; collapse into the translator in Phase 2.
- Full collapse vs a retained node boundary depends on Tello/PX4 interop — revisit.

---

## 8. Odometry & Position Estimation

> **STATUS (realized):** the backend interface's `Odometry{pos,vel,yaw,yawrate,valid}` (ENU) is
> the FORK-B abstraction. ENU is the canonical convention across it; NED exists only on the PX4
> wire, converted at
> two isolated points in `px4_backend.cpp`. The Tello Simpson-rule integration remains open.

**FORK-B: direct `px4_msgs/VehicleOdometry` (NED) for sim; ⚠ MUST migrate to a cross-hardware
odometry abstraction.** FMU stores X/Y/Z + yaw in `std::atomic`, `SensorDataQoS` sub.

- **PX4 sim:** native `VehicleOdometry` on `/fmu/out/vehicle_odometry` (`position[2]` down+).
- **Physical Tello (primary):** integrate `TelloState` velocity in the driver → `nav_msgs/
  Odometry`. **Simpson's rule over 3 samples** (velocity is a *sampled* signal → quadrature,
  not RK4). Same estimate feeds `VehicleTelemetry`. Drift-bias = tuning open.
- We do **not** rely on PX4 EKF2 video-odometry (too complex/unnecessary for sim).
- **Future:** pinhole camera model → local-3D target points; later local→global via tf2 from
  SLAM (OctoMap/A*). Deferred post-POC. No TF2 now.

**stella_vslam considerations (2026-08-09):** picked over ORB-SLAM3 for being the actively
maintained fork (ORB-SLAM3 upstream has seen little activity in years). First live SITL pass
failed intermittently; root cause was our own build compiling its feature extractor
single-threaded (an upstream `USE_OPENMP` flag defaulting off, never enabled on our side), not a
stella_vslam ceiling. Fixed and re-verified across repeated SITL trials — full numbers and
methodology in `docs/NOTES.md` ("B1 stella_vslam live SITL verification + OpenMP fix"). Not yet
verified with the VLM running concurrently or against real (non-SITL) camera footage.

---

## 9. Perception Ingestion (vision engine interface)

> **STATUS (realized):** `PerceptionRuntime` (`fmu/perception_runtime.hpp`) owns the two
> concrete engines below and publishes an atomic `PerceptionSnapshot` `buildDynamicPrompt()`
> reads (§6). Block 4.2 (ROADMAP) closed this out; **block 5 (APPROACH) has since shipped and
> is SITL-verified (ROADMAP 5.1, 5.1.5) -- see §15, no longer gated/pending.**

Concrete engines (not virtual), from the vendored `Perception::vision` library
(`safe_cpm_add_package`, `nurmilkov/BUILD_YOLO` `feature-vision-api`, top-level `CMakeLists.txt`):

```cpp
vision::YoloSegEngine   { bool ok(); std::vector<SegDetection> segment(cv::Mat, conf, iou); };  // ~30Hz
vision::YoloDepthEngine { bool ok(); cv::Mat estimate(cv::Mat); };                               // ~13Hz measured
```
- **Two-rate, decoupled loops, not one fused call.** `PerceptionRuntime` runs a fast
  segmentation loop (near the seg engine's ~30Hz ceiling) and a slower, independent depth loop
  (measured ~75ms/frame vs a 40Hz/25ms target — see ROADMAP 4.1.8) as two `std::thread`s. It
  calls `segment()`/`estimate()` directly rather than the library's `vision::fuse()` helper,
  which runs both models back-to-back in one blocking call and would collapse the two rates back
  into one. Each seg tick re-samples median depth over the freshest bbox against whatever depth
  map the depth loop last produced — median_depth_cm can therefore lag bbox by up to one depth
  cycle. §10's emergency boundary must tolerate that staleness (ROADMAP 4.1.8a).
- **Atomic perception snapshot:** published via the same atomic-`shared_ptr` idiom the FMU
  already uses for `m_currImg` (`std::atomic_load`/`store`), not a mutex.
- **POC depth = YOLO26n METRIC depth (SUPERSEDES MiDaS Small relative).** The perception-library
  design (`specs/2026-08-05-perception-library-design.md`) selects YOLO26n metric depth. With
  metric cm available, §10's emergency boundary can use absolute distance directly
  (relative-depth time-to-contact is not needed).
- Thread counts (`kVisionSegThreads`/`kVisionDepthThreads`, `fmu_node_base.hpp`) cap ORT
  intra-op parallelism so perception cannot starve the 20Hz control loop.

---

## 10. Emergency Boundary (velocity-scaled)

> **STATUS (realized — Spec 1, SITL-verified 2026-08-09):** the velocity-scaled boundary shipped
> (37 trips in the `boundary` scenario), plus a free-space depth cone that catches walls with no
> detection and a bounding-box looming backstop for close objects depth over-reads. The APPROACH
> motion-gate (6.4) rejects a false "reached" on off-nominal motion (`approach-impact`). Known limit:
> the monocular cone misses thin obstacles and frame edges.

```
d_trigger = d_hard + v·t_react + v²/(2·a_max)
   d_hard ≈ 0.25 m ; t_react ≈ 0.15–0.20 s ; a_max = per-drone var (Tello ≠ PX4)
   clamp [ d_hard_floor , depth_sensor_reliable_range ] ; tune in sim
```
**Metric caveat (§9):** with relative-depth POC, replace absolute `d_trigger` with a
time-to-contact / looming threshold until metric depth exists.

---

## 11. Battery & Failsafe Supervisor (deterministic, atomic, overrides VLM)

> **STATUS (realized — Spec 3, SITL-verified 2026-08-08):** implemented on real PX4 battery
> (`/fmu/out/battery_status_v1`). Shipped laws: **≤20% -> RTH then land** (latched), **≤10% ->
> land-in-place** (latched), `-1` = UNKNOWN (skipped). Manual override is a **reversible** takeover
> and the **failsafe outranks it** (failsafe > pilot > autonomy) — this supersedes the original
> table's "override yields" row below. Smart energy/terrain RTH deferred
> (`docs/scheduled/2026-08-07-battery-rth-energy-terrain-subsystem.md`).

`home` = odom anchor; `cost ≈ dist_home/cruise_speed·drain_rate + reserve`.

| Condition | Action |
|-----------|--------|
| **User override** (any %, except <5% floor) | Yield — assume the user is saving the drone. |
| > 20% | Normal. |
| ≤ 20% | Return feasible → **RTH** (`GO home`+`LAND`); else **land-in-place now**. |
| 10–15%, not RTH, no override | **Land-in-vicinity.** |
| < 5% (hard floor) | **Force-land**, override included. |

---

## 12. Resolved Decisions

| # | Decision |
|---|----------|
| 1 | pending → active → completed; no ReadyToPublish. Queue = `moodycamel::ReaderWriterQueue`. `operator= = default`. |
| 2 | `start()` bootstrap: `m_missionActive` atomic flips true; `maybePlan()` waits up to `kVisionWarmupUs` for a first camera frame (else plans text-only) then fires the first VLM call. **No condition_variable** -- gated by an atomic flag + timeout, checked each 20Hz poll (§5). |
| 3 | Offboard = in-process backend publish loop (30Hz PX4 / 20Hz Tello); **state machine in FMU** (§7). FORK-C collapse done -- concrete backends, no separate node. |
| 4 | GO = one carrot-chasing cross-track law (no `go_vel`/`go_pos` split). STOP instant. APPROACH, ROTATE, ORBIT, SEARCH all shipped and parsed from the VLM plan (§4). CURVE remains dropped for POC, not parsed. |
| 5 | Interrupt = reflexive hold-clearance → consumer drain → VLM reassess (§5.1). |
| 6 | Camera: FMU subscribes **`camera/stream`** (rx_node output), PTS-timestamped. |
| 7 | Odometry: direct `VehicleOdometry` (sim) — **migrate to cross-hw abstraction** (FORK-B). |
| 8 | Velocity-scaled emergency boundary, `a_max` per-drone (§10). |
| 9 | Battery/failsafe + user override (§11). |
| 10 | Perception: **refactor `BUILD_YOLO` modular-vision-api behind the perception contract**; shelve ggml-depth-experiment; POC depth = YOLO26n metric (§9). |

---

## 13. Known Risks

- **[FORK-A] context size** — resolved directionally (raised well past 1024) but not finally
  tuned: the live script runs `-c 65536` as deliberate testing headroom (§0), and still needs
  proper per-call measurement + right-sizing for the actual (low-end) target hardware.
- **Depth is now metric (YOLO26n, §9)** — the emergency boundary (§10) can use absolute cm. (An earlier MiDaS-relative POC would have needed time-to-contact.)
- **Cross-hw odometry migration** debt (§8).
- Reassess latency window (1–2 s) on drifting odom; interrupt oscillation (needs hysteresis +
  max-retries → land/abort); odom drift vs 0.20 m bar; ceiling-blind takeoff; SEARCH 2-D off-plane blindness.
- **Sim integration debt: resolved.** The launch harness is now `projects/llm_to_action/test/sitl/run.sh <scenario>` over `projects/llm_to_action/test/lib/sim_core.sh` (one
  folder per feature; `simenv_llm.sh` was removed, its logic folded into `sim_core.sh`). It runs
  the `llm_to_action_*` binaries, an FMU pane, a `llama-server` pane, and camera (`rx_node`)
  wiring end-to-end (the 2026-08-06 real-hardware Tello flight + the 20-test SITL suite).

---

## 14. POC Build Slice — usable today, PX4 Gazebo sim

> **STATUS (realized):** this section describes the original Phase-1 bring-up plan.
> **Prereqs done** -- `projects/llm_to_action/test/sitl/run.sh <scenario>` (over `projects/llm_to_action/test/lib/sim_core.sh`) runs the FMU
> pane, llama-server pane, `llm_to_action_*` binaries, and `rx_node`. **FORK-A** raised to `-c 65536`
> as deliberate testing headroom, real tuning still open (§0); **FORK-C** collapsed into the
> concrete backends, no retained `px4_offboard_node` (§7).

**Phase 1 (today, NO real perception):**
- Odom sub → atomic pose/yaw, `SensorDataQoS` (direct `VehicleOdometry`).
- `moodycamel` queue + `translateToBaseCommands` (+ backpressure). `operator= = default`.
- 20 Hz loop: `go_vel` + ROTATE + Hover default; TAKEOFF/LAND via FMU state machine.
- FMU subscribes camera at **`camera/stream`**.
- Setpoint output: **FORK-C resolved** — in-process translator inside the concrete backend
  (`PX4Backend`/`TelloBackend`); `px4_offboard_node` not retained.
- Event-driven VLM (queue empty, `re-assess`) — or **canned/hardcoded plan injection** to test
  the control chain without the VLM first (recommended first bring-up).
- Battery/failsafe supervisor. Perception **stubbed**; emergency path **disabled**.

**Phase 2:** refactor BUILD_YOLO modular-vision-api behind the perception contract (YOLO26n metric), snapshot
fusion, relative-depth emergency + interrupt/reassess, ORBIT/SEARCH controllers, Tello backend +
Simpson odom, offboard collapse (if not done), context/prompt final form.

---

## 15. Implementation Status (repo vs. spec)

The committed FMU now implements the core of this spec: the 20 Hz control loop with GO
(carrot-chasing cross-track guidance) / ROTATE / TAKEOFF / LAND / STOP, odometry + pose via the
GenericBackend interface, event-driven VLM planning (async, off the control thread), tolerant plan
extraction, the ENU convention (Task 4), canned test rigs (`--canned-cross` / `--canned-speed`), and
the camera path (TX→RX→FMU, vision-grounded planning confirmed). Both FMU binaries build
(`llm_to_action_fmu_px4` / `_tello`).

**Remaining gap (what this spec still describes but the repo does not yet do):**
- **live-YOLO GO** (ROADMAP 5.2) — APPROACH recomputes per-tick off a live detection; plain GO
  is still a one-shot dead-reckoned waypoint. Visual-servo GO redesign not started
  (`docs/active/2026-08-05-go-controller-visual-servo.md`).
- **Tello hardware bring-up** — backend flight-verified on real hardware 2026-08-06 (telemetry,
  odometry, camera all confirmed live); stick-to-m/s calibration, Simpson-rule odometry
  integration, and wind/prop-wash stability correction still open (ROADMAP 2.3.1/2.3.2/2.3.5).

Resolved, previously listed here as still open: **APPROACH's "reached" motion sanity check**
(ROADMAP 6.4) and the **emergency boundary** (§10, ROADMAP 6.1) are both shipped and
SITL-verified (Spec 1, 2026-08-09) -- see §10/§11 above, which already carried the correct
status. This list just hadn't been reconciled against them.

Resolved since this section was last written: perception (real YOLO seg+depth) IS wired into
the FMU and confirmed working end-to-end against a real object with a live VLM planning off it
(2026-08-06) -- see ROADMAP 4.2 and 5.1.5. Also shipped + SITL-verified 2026-08-08 (Spec 3/4):
the battery/failsafe supervisor + reversible manual override (§11), bounded SPSC backpressure (§3),
the ROTATE accumulated-angle law and the LAND flare (§4) — all covered by the 15-test
`projects/llm_to_action/test/sitl/` suite (ROADMAP §SITL test matrix).

---

## 16. Open Items

- [x] **FORK-A:** DONE — `-c 4096`, client `max_tokens 512` (bounds runaway ~4 s).
- [x] **FORK-C:** DONE — collapsed into the concrete backends via the GenericBackend interface.
- [ ] Reconcile takeoff climb height (2 m node default vs FMU target).
- [x] Cross-hw odometry abstraction — realized as the GenericBackend `Odometry` under the ENU convention (Tello Simpson integ. remains).
- [ ] Interrupt hysteresis + max-retries → land/abort; relative-depth time-to-contact model.
- [ ] Tune §10/§11 constants in sim. `start()` bootstrap.
- [x] Adapt BUILD_YOLO `modular-vision-api` behind the perception contract -- vendored via
      `nurmilkov/BUILD_YOLO` `feature-vision-api` (`CMakeLists.txt`), consumed as
      `Perception::vision` by `PerceptionRuntime` (§9).
- [x] Rephrase kSystemPrompt interruption text → Appendix A -- installed in `llm_base.hpp`
      (see Appendix A below; the INTERRUPT behavior it describes is still unbuilt, §5.1).
- [x] Sim launch migrated to FMU + `llm_to_action` binaries -- now the per-feature
      `projects/llm_to_action/test/sitl/run.sh <scenario>` harness over `projects/llm_to_action/test/lib/sim_core.sh` (`simenv_llm.sh` removed).

## 17. Dev Environment Networking (real-hardware bring-up, 2026-08-06)

Two machines: **`swapgs`** (dev box — editing/git/this session) and **`mint0`** (laptop joined
to the Tello's Wi-Fi AP — builds and flies the drone code). Edits on swapgs need push+pull to
reach mint0; a fix living in `devenv.sh` applies automatically once mint0 pulls and relaunches.

The dev container launches `--net=host --privileged`, so it shares the host's netfilter
tables 1:1 — `iptables` run inside the container edits the real host kernel tables.
**`ufw`'s apply mechanism is broken in this container image**: `ufw allow` reports success and
`ufw status verbose` shows the rule active, but the ACCEPT never lands in the actual
`ufw-user-input` chain (confirmed via `iptables -L`), and the `INPUT` chain's jump to
`ufw-user-input` can itself go missing after a `ufw` uninstall/reinstall mid-session. Tello
state telemetry (unsolicited inbound UDP 8890) was silently dropped this way for an entire
session even though the command channel (UDP 8889, outbound-initiated) worked fine.
**Fix: bypass ufw, insert raw netfilter rules directly, inside the container (root, no
`sudo`):**
```bash
iptables -I INPUT 1 -p udp --dport 8890 -j ACCEPT
iptables -I INPUT 1 -p udp --dport 11111 -j ACCEPT
```
This now lives in `devenv.sh`'s container startup. Do not add these to the host's iptables —
every working command that session ran inside the container, and the host may not even have
`iptables`.

---

## Appendix A — kSystemPrompt "Execution Model" (ROADMAP 3.6)

> **STATUS (integrated):** installed in `llm_base.hpp`'s `kSystemPrompt`, replacing the old
> interrupt paragraph. **Describes intended behavior, not yet built** — QUEUE EMPTY and YOUR
> re-assess are real (ARCH §5); INTERRUPT (the host's depth-triggered reflexive hold-clearance,
> ARCH §5.1) is still open (ROADMAP 1.5, gated on depth — depth itself landed in 4.2, the
> interrupt/hold-clearance control logic has not). Same forward-declared-ahead-of-implementation
> pattern already used for `orbit`/`search`/`rotate`/`re-assess` in the prompt.

```
EXECUTION MODEL
The host executes your plan sequentially, streaming each command to the drone until
deterministic sensors confirm it is complete. You are NOT polled continuously. You are
woken to (re)plan ONLY when:

1. QUEUE EMPTY    — your previous plan finished; produce the next plan.
2. YOUR re-assess — you deliberately paused to look around.
3. INTERRUPT      — the host's high-rate depth monitor detected an imminent collision.
                    Before waking you, the host has ALREADY reflexively stopped the drone
                    and backed it a short distance from the hazard to hold clearance. The
                    drone is now hovering safely.

On an INTERRUPT you are given: what you were executing, what remained queued, and the
current depth map + segmented frame highlighting what you came too close to. Reassess:
Why was I stopped? What was I doing? How do I get around <hazard> without colliding and
still make progress? Output a NEW plan that first clears the hazard, then resumes the
objective. The old queue is discarded — your new plan fully replaces it.
```

---
## Perception stack: llm_cv_track / llm_cv_scene (2026-08-20)
Two sibling apps share one perception spine; only the HIGHLIGHT localizer differs.

Layers (both apps):
1. **Ears** — ROS2 `asr_server` (Parakeet) transcribes on push-to-talk (H) -> topic -> `Ears` subscriber.
2. **Background** — YOLO26n-seg draws faint always-on boxes (worker thread).
3. **Highlight (the difference):**
   - `llm_cv_scene` (backup): **Qwen3-VL** localizes the phrase itself (slow, static box).
   - `llm_cv_track` (star): **OmDet-Turbo** open-vocab detector re-detects each frame (box follows).
4. **Segment** — SAM2.1 masks the highlighted box; whole-frame garbage masks dropped, box tightened to mask.
5. **Reason** — Qwen3-VL (llama-server) answers spoken questions; runs OFF the ASR thread.

Threading: a display thread at camera FPS + a perception worker + the ASR callback thread + a VLM thread.
Portability: torch device is vendor-neutral (CUDA/ROCm/CPU); the VLM is llama.cpp/Vulkan.
Input: webcam index, RTSP (drone via DJI Fly Custom RTMP -> MediaMTX), or a GStreamer pipeline.
OmDet loads from a local vendored copy offline (~1s); see archive/llm_cv_track/README.md.

Not fully AGPL-free yet: YOLO26 + SAM2 + BoT-SORT (Ultralytics) remain AGPL; OmDet-Turbo is Apache.

---

## Integration MVD — voice -> 4-tier router -> DJI backend + perception (2026-08-25)

> **Status:** DONE / the Demo-Day system. Lives in `projects/integration/` (self-contained). A PARALLEL
> subsystem to the FMU above — the FMU (`llm_to_action`) remains the destination C++ product; this
> Python MVD is the shipped prototype. Full detail: `docs/active/2026-08-25-mvd-integration-handoff.md`.

**Data flow.** `voice (laptop mic / phone ASR) -> on_text -> Router.classify (4 tiers) -> {BASIC verb ->
DjiWire -> DJI REST (POST /c/...) | COMPLEX -> perception (Qwen-VL + OmDet/SAM2)}`. Drone camera ->
phone `:5600` raw-H.264/TCP -> `gstreamer_rx` -> ROS `camera/stream` -> perception window. Perception
answer -> LONG (screen) + SHORT (spoken: phone `/tts` + laptop espeak).

**Control authority model.** Total user control: deterministic verbs move the drone; the VLM never
drives motion. Tiers: EMERGENCY (`stop`=`POST /c/fly [{delay:0}]`, preempts + keeps control) >
OVERRIDE (`manual`=`/c/stop` RC handoff) / RESUME > BASIC verbs > COMPLEX (perception, no drone POST).
`controller.fly{}` cancels the prior mission and re-`takeControl()`s, so missions naturally preempt.

**Interfaces.** `dji_wire.py` is the sole aircraft client (full REST/WS: `/c/fly` mission actions,
`/key`, `/tts`, `/status`, `/c/ws/sticks`). Inbound phone ASR via `phone_ears.py` (laptop `:8080`,
`/input` + raw TCP, matches `GroundStationSpeechResolver.kt`). VLM on `llama-server :18090` (`-np 1`).
Ports: phone `:8080` (control+tts) / laptop `:8080` (phone_ears) / `:5600` (video) / `:18090` (VLM).

**Backend gaps (DJI app dev):** dynamic groundstation-IP discovery; gimbal commands (broken backend-side);
API-Server foreground-service reliability. See the handoff §9.
