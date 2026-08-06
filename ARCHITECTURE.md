# Groundstation — FMU Architecture Specification

> **Status:** IMPLEMENTED / LIVING SPEC. The committed FMU now implements this architecture
> (20 Hz control loop, odometry, event-driven VLM, ENU seam, GenericBackend seam, canned test
> rigs). `docs/NOTES.md` is the running change log. Sections below are annotated where reality has
> moved past the original plan; the remaining gap is perception integration + the APPROACH
> servo + the emergency/failsafe supervisor (§15).
>
> **Scope:** `FlightManagementUnitNode` (`source/llm_to_action/fmu/`) — high-level VLM
> planner + deterministic 20 Hz control loop, plus an in-process offboard translator (§7).
> Primary target = **DJI Tello**; PX4 SITL is a simulation fallback.

---

## 0. Forks Status

> **Update:** since this spec was written the FMU was implemented and several forks closed.
> FORK-A tuned (`-c 4096`, client `max_tokens 512`); FORK-B realized as the GenericBackend
> `Odometry` ENU seam; FORK-C collapsed into the concrete backends (no separate offboard node).
> The bullets below keep the original reasoning for history.

- **[FORK-A] VLM context — TUNED.** Strategy confirmed: manual context, zero-shot
  every call (KV never grows past `-c`; ~2.5–3 GB fits ~3 GiB). **But `-c 1024` cannot hold
  one shot:** `kSystemPrompt` alone ≈ 1.2–1.6k tokens, + image (~256–1024) + output.
  Resolution → raise `-c` to ~4096 (VRAM permitting, measure) **and/or** compress hard
  (trim system prompt ~60–70%, downscale image, 1–2 line history summary, small output cap).
- **[FORK-B] Odometry — RESOLVED (seam abstraction realized).** Consume `px4_msgs/VehicleOdometry` (NED) **directly**
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
- **Hardware-agnostic.** Tello primary, PX4 SITL fallback. One generic setpoint + one
  odometry abstraction (cross-hw migration pending, §8).
- **No heap in steady state.** Fixed-size command structs, SPSC task queue, atomic flags.
- Constraints: no `std::variant`/exceptions/mutex-on-image; C89 hoisting; `FixedStringType`;
  enums one-per-line ≤95 cols.

---

## 2. Thread Architecture

`MultiThreadedExecutor` + callback groups. Threads: **Depth (Model-D ≥30 Hz)**,
**YOLO-Seg (Model-S 25 Hz)**, **VLM (async, event-driven)**, **Control (20 Hz)**, and the
**Offboard publisher (~100 Hz)** streaming setpoints via the translator (§7). Shared state is
`std::atomic`: `m_emergencyStop`, failsafe state, user-override, latest pose, perception snapshot.

---

## 3. Data Flow & Queue

```
VLM plan (JSON) ── translateToBaseCommands() [VLM thread = PRODUCER]
   ▼
m_taskQueue (moodycamel::ReaderWriterQueue<ActiveTask>, FIFO, SPSC) ── pending
   ▼ try_dequeue() [20Hz loop = CONSUMER]
m_currTask (active) ── completion (§4) ──► m_completedTasks (history §6)
                    └─► setpoint ──► 100Hz offboard thread ──► drone
```
- No "ReadyToPublish" queue. Strictly SPSC (VLM produces, 20 Hz consumes). Interrupt drain
  is consumer-side (§5.1). Handle enqueue backpressure.

---

## 4. Deterministic Task Completion (20 Hz loop)

The FMU owns the flight **state machine** (STANDBY/TAKEOFF/FLIGHT/LANDING); the translator
(§7) is dumb. On completion: record `m_currTask` (with `thought`) → `m_completedTasks`, dequeue.

| Cmd | Predicate | Notes |
|-----|-----------|-------|
| **GO** | 3-D Euclidean dist < **0.20 m** | **Two impls — `go_vel` and `go_pos` — both built, chosen per-drone/empirically.** `go_vel`: velocity-toward-waypoint (`vel = dir·speed`), robust to drift. `go_pos`: discrete XYZ (Tello `go`/PX4 position setpoint), drift-prone. |
| **ROTATE** | \|yaw − target\| < **5°** | yawspeed (vel) or discrete. |
| **TAKEOFF** | FMU state machine: arm → climb to target → FLIGHT | Completion = odom altitude ≥ target. Reconcile climb height (offboard node hardcodes 2 m). Stall guard (ceiling-blind). |
| **LAND** | FMU state machine: descend → force-disarm near ground | Odom alt≈0 ∧ vz≈0. **Depth estimator gated OFF only in final 10–30 cm**, after clear-to-land. WHERE-to-land = planning, separate. |
| **STOP** | one hover cycle → instant | Near-redundant; kept for VLM expressiveness. |
| **ORBIT** | ≥360° accumulated (default 1 rev) OR time limit | **Anchor to a detected target in-frame only** (no SLAM = no reliable global anchor). Visual servo: bbox in frame, `median_depth ≈ radius`, small steps. Target lost → abort → re-assess. Future: pinhole-model 3D target point (§9) as a better anchor. |
| **SEARCH** | success = detected; fail = timeout | **2-D horizontal circle.** 360° step-rotate-settle-detect, expand outward. Record pre-search **anchor**; fail → `GO anchor` + FAILED. post-search → re-assess. |
| **CURVE** | — | Dropped for POC. |

**20 Hz streaming contract:** active task → setpoint; queue empty → Hover. Never send once.

> **Frame (realized):** completion predicates + setpoints are evaluated in the canonical **ENU**
> seam frame (Task 4 done): TAKEOFF climbs to `+kTakeoffTargetAltEnu`, LAND descends to
> `≤ kGroundContactEnu`, GO uses `flu_to_enu(relFlu, yaw)`. NED exists only on the PX4 wire.

---

## 5. VLM: Event-Driven

Timer removed. Triggers: queue empty, `re-assess`, `m_emergencyStop`. Wake via
`condition_variable::notify_one()`.

### 5.1 Interrupt & Reassessment (deterministic-first)
1. **Reflexive hold-clearance (control loop, no VLM).** `target = pos + reverse_vec·backoff`,
   `reverse_vec = -normalize(recent velocity)`, `backoff ≈ 20–30 cm`. Actively holds clearance
   vs hover overshoot. **Requires internal state:** short last-velocity history (also feeds §8).
2. **Consumer drains the queue**, records interrupted task as `STOPPED` (+`thought`). SPSC-safe.
3. **Wake VLM** with: what it was doing, what was queued, depth map + segmented hazard frame.
4. **Producer refills** the empty queue; loop resumes.

---

## 6. Dynamic Prompt Construction

> **⚠ Governed by FORK-A.** At `-c 1024` the prompt must be compressed hard; history is a
> short summary, not the full log, unless `-c` is raised.

Sections: system config · FLU coordinate frame · mission objective · vehicle state
(telemetry) · perception JSON (label/bbox/median_depth from snapshot §9) · executed history
(`{status,thought,action}`) · active pending queue.

- **Send both** marked image AND perception JSON. Preserve `thought`
  (`LargeFixedStringType m_thought`, `status`-prefixed). Targets addressed by `label`/`id`.

---

## 7. Setpoint Output — In-Process Offboard Translator

> **STATUS (realized):** collapsed. The translation this section specced now lives inside the
> concrete backend (`PX4Backend` → PX4 wire; `TelloBackend` → `rc`/`go`), selected at compile
> time via the `GenericBackend` seam. No separate offboard node/process; the FMU owns the flight
> state machine and calls `backend->set_velocity(...)` in the canonical ENU frame.

**Target (points 3 & 5):** the offboard controller is a **dumb `OffboardTranslator` struct**
(generic setpoint → PX4 `VehicleCommand`/`TrajectorySetpoint`, or Tello `rc`/`go`), driven by
a **~100 Hz publisher thread inside the FMU process**. No separate ROS node/process. The
**flight state machine lives in the FMU**, not the translator.

- Translation reference already exists in `px4_offboard_node`: ENU/FLU→NED flip
  (`external_velocity_callback`), OFFBOARD mode set, arming, ~100 Hz velocity streaming, PX4
  best-effort/transient-local QoS. Extract this logic into the translator.
- **FORK-C sequencing:** Phase 1 *may* keep the existing node (re-enable its Twist+Bool subs,
  FMU publishes to them) to fly fastest; collapse into the translator in Phase 2.
- Full collapse vs a retained node boundary depends on Tello/PX4 interop — revisit.

---

## 8. Odometry & Position Estimation

> **STATUS (realized):** the seam `Odometry{pos,vel,yaw,yawrate,valid}` (ENU) is the FORK-B
> abstraction. ENU is canonical across the seam; NED exists only on the PX4 wire, converted at
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

---

## 9. Perception Ingestion (engine seam)

FMU designed against two concrete, stubbed engine structs; real models drop in with zero FMU
changes.

```cpp
struct YoloDetectionEngine { size_t detect(const cv::Mat&, TargetDetection*, size_t); }; // Model-S 25Hz
struct YoloDepthEngine     { void   estimate(const cv::Mat&, DepthResult&); };            // Model-D 30Hz+
```
- Concrete structs (not virtual). **Atomic perception snapshot:** fuse Model-S + Model-D for
  the **same frame** (align via header PTS from `rx_node`) → coherent perception.
- **Reuse, don't rewrite (`BUILD_YOLO`):** adapt the **`modular-vision-api`** branch
  (`ObjectDetector` + `DepthEstimator`/`midas_small_engine` + `vision_fusion` + `VisionResult`
  — already the seam architecture) behind these structs. **Shelve `ggml-depth-experiment`**
  (unfinished YOLO26-depth→GGUF metric spike, validated only to layer 0–1) as the future
  metric-depth track.
- **POC depth = YOLO26n METRIC depth (SUPERSEDES MiDaS Small relative).** The perception-library
  design (`docs/specs/2026-08-05-perception-library-design.md`) selects YOLO26n metric
  depth; the earlier MiDaS-relative plan is dropped. With metric cm available, §10's emergency
  boundary can use absolute distance directly (relative-depth time-to-contact no longer required).
  The engine seam is real, built in the standalone `/root/build_yolo` repo, pending FMU integration.

---

## 10. Emergency Boundary (velocity-scaled)

```
d_trigger = d_hard + v·t_react + v²/(2·a_max)
   d_hard ≈ 0.25 m ; t_react ≈ 0.15–0.20 s ; a_max = per-drone var (Tello ≠ PX4)
   clamp [ d_hard_floor , depth_sensor_reliable_range ] ; tune in sim
```
**Metric caveat (§9):** with relative-depth POC, replace absolute `d_trigger` with a
time-to-contact / looming threshold until metric depth exists.

---

## 11. Battery & Failsafe Supervisor (deterministic, atomic, overrides VLM)

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
| 2 | `start()` bootstrap: first frame → perception → one VLM call → release task-thread CV. |
| 3 | Offboard = in-process `OffboardTranslator` struct + 100 Hz thread; **state machine in FMU** (§7). FORK-C sequences the collapse. |
| 4 | GO = both `go_vel` + `go_pos`, chosen empirically. STOP instant. ORBIT target-anchored only. SEARCH 2-D circle. CURVE dropped. |
| 5 | Interrupt = reflexive hold-clearance → consumer drain → VLM reassess (§5.1). |
| 6 | Camera: FMU subscribes **`camera/stream`** (rx_node output), PTS-timestamped. |
| 7 | Odometry: direct `VehicleOdometry` (sim) — **migrate to cross-hw abstraction** (FORK-B). |
| 8 | Velocity-scaled emergency boundary, `a_max` per-drone (§10). |
| 9 | Battery/failsafe + user override (§11). |
| 10 | Perception: **refactor `BUILD_YOLO` modular-vision-api behind the seam**; shelve ggml-depth-experiment; POC depth = MiDaS relative (§9). |

---

## 13. Known Risks

- **[FORK-A] 1024-token context** vs prompt size — top blocker; needs compression or larger `-c`.
- **Depth is now metric (YOLO26n, §9)** — the emergency boundary (§10) can use absolute cm. (An earlier MiDaS-relative POC would have needed time-to-contact.)
- **Cross-hw odometry migration** debt (§8).
- Reassess latency window (1–2 s) on drifting odom; interrupt oscillation (needs hysteresis +
  max-retries → land/abort); odom drift vs 0.20 m bar; ceiling-blind takeoff; SEARCH 2-D off-plane blindness.
- **Sim integration debt:** binaries named `ros2_speech_to_action_*`; llama-server + FMU panes
  need adding to `simenv.sh`; camera topic wiring.

---

## 14. POC Build Slice — usable today, PX4 Gazebo sim

**Prereqs in `simenv.sh`:** add an FMU pane + enable the llama-server pane; switch binaries to
`llm_to_action_*`; ensure `rx_node` (camera/stream) runs. **Resolve FORK-A** so the prompt fits.

**Phase 1 (today, NO real perception):**
- Odom sub → atomic pose/yaw, `SensorDataQoS` (direct `VehicleOdometry`).
- `moodycamel` queue + `translateToBaseCommands` (+ backpressure). `operator= = default`.
- 20 Hz loop: `go_vel` + ROTATE + Hover default; TAKEOFF/LAND via FMU state machine.
- FMU subscribes camera at **`camera/stream`**.
- Setpoint output: **FORK-C** — reuse `px4_offboard_node` (re-enable subs) *or* in-process translator.
- Event-driven VLM (queue empty, `re-assess`) — or **canned/hardcoded plan injection** to test
  the control chain without the VLM first (recommended first bring-up).
- Battery/failsafe supervisor. Perception **stubbed**; emergency path **disabled**.

**Phase 2:** refactor BUILD_YOLO modular-vision-api behind the seam (MiDaS relative), snapshot
fusion, relative-depth emergency + interrupt/reassess, ORBIT/SEARCH controllers, Tello backend +
Simpson odom, offboard collapse (if not done), context/prompt final form.

---

## 15. Implementation Status (repo vs. spec)

The committed FMU now implements the core of this spec: the 20 Hz control loop with GO
(carrot-chasing cross-track guidance) / ROTATE / TAKEOFF / LAND / STOP, odometry + pose via the
GenericBackend seam, event-driven VLM planning (async, off the control thread), tolerant plan
extraction, the ENU seam (Task 4), canned test rigs (`--canned-cross` / `--canned-speed`), and
the camera path (TX→RX→FMU, vision-grounded planning confirmed). Both FMU binaries build
(`llm_to_action_fmu_px4` / `_tello`).

**Remaining gap (what this spec still describes but the repo does not yet do):**
- **Perception integration** — real detections/metric depth (§9). The YOLO26 library is built in
  the standalone `/root/build_yolo` repo but not yet wired into the FMU; `TargetDetection` in
  `fmu_node.hpp` is still a stub.
- **APPROACH / visual-servo GO** — specced
  (`docs/specs/2026-08-05-visual-servoing-approach-design.md`), gated on perception.
- **Emergency boundary + battery/failsafe supervisor** (§10/§11) — designed, not implemented.
- **Tello hardware bring-up** — backend built + unit-tested; real gstreamer H264 camera RX
  (`udpsrc port=11111 ! h264parse ! avdec_h264`) still to do.

---

## 16. Open Items

- [x] **FORK-A:** DONE — `-c 4096`, client `max_tokens 512` (bounds runaway ~4 s).
- [x] **FORK-C:** DONE — collapsed into the concrete backends via the GenericBackend seam.
- [ ] Reconcile takeoff climb height (2 m node default vs FMU target).
- [x] Cross-hw odometry abstraction — realized as the GenericBackend `Odometry` ENU seam (Tello Simpson integ. remains).
- [ ] Interrupt hysteresis + max-retries → land/abort; relative-depth time-to-contact model.
- [ ] Tune §10/§11 constants in sim. `start()` bootstrap.
- [ ] Adapt BUILD_YOLO `modular-vision-api` behind the seam.
- [ ] Rephrase kSystemPrompt interruption text → Appendix A (+ compress for FORK-A).
- [ ] `simenv.sh` migration to FMU + `llm_to_action` binaries.

---

## Appendix A — Draft kSystemPrompt "Execution Model" (replaces old interrupt text)

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
```
