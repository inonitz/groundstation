# Groundstation — FMU Architecture Specification

> **Status:** PLANNING / SPEC. The committed `fmu_node.hpp` reflects an earlier design
> (`SYS-58`) and is behind this document. This file is the source of truth.
>
> **Scope:** `FlightManagementUnitNode` (`source/llm_to_action/fmu/`) — high-level VLM
> planner + deterministic 20 Hz control loop. Hardware-agnostic (PX4 sim and physical
> DJI Tello share one interface).

---

## 1. Design Goals

- **Off-board compute.** Drone is a dumb peripheral; all planning/perception/control math
  runs on the ground station.
- **VLM plans, math executes.** VLM produces flight *plans*; never in the per-command
  completion loop (1–2 s inference too slow). Completion = deterministic geometry vs odometry.
- **Hardware-agnostic.** No PX4/DJI specifics in the FMU. Both backends publish
  `nav_msgs/Odometry` and consume one generic setpoint abstraction.
- **No heap in steady state.** Fixed-size command structs, lock-free SPSC task queue,
  atomics for shared pose/flags.

### Hard coding constraints (non-negotiable)
- No `std::variant` → C-style POD union (`GenericCommand`).
- No exceptions/`try-catch` → `.empty()` (OpenCV), `.is_discarded()` (nlohmann).
- No mutex on image ptr → C++17 `std::atomic_load`/`atomic_store` on `shared_ptr`.
- C89 variable hoisting (locals at top of function).
- `FixedStringType`=`char[32]`, `LargeFixedStringType`=`char[128]`, fill via `strncpy`.
  No `std::string` in command/task structs.
- Enums one-per-line, lines ≤ 95 chars, struct default member inits kept.

---

## 2. Thread Architecture

Four decoupled units. `MultiThreadedExecutor` + callback groups isolate the blocking VLM
call from the real-time paths.

| Thread | Rate | Responsibility | Priority |
|--------|------|----------------|----------|
| **Depth (Model-D)** | ≥ 30 Hz | Center-frame proximity vs velocity-scaled boundary (§10) → assert `m_emergencyStop` + wake VLM. | Highest |
| **YOLO-Seg (Model-S)** | 25 Hz | Bounding boxes/segmentation; fused with depth into the perception snapshot (§9). | High |
| **VLM (async)** | event-driven | Sleeps on `condition_variable`; wakes only on a trigger (§5). Blocks seconds; never stalls control. | Low |
| **Control loop** | 20 Hz | Deterministic completion + continuous setpoint streaming; honors failsafe overrides (§11). | Real-time |

Shared flags are `std::atomic`: `m_emergencyStop`, and the failsafe state (§11).

---

## 3. Data Flow & Queue

```
VLM plan (JSON)
   │  translateToBaseCommands()   [VLM thread = single PRODUCER]
   ▼
m_taskQueue  (moodycamel::ReaderWriterQueue<ActiveTask>, FIFO, SPSC)   ── pending
   │  try_dequeue()              [20Hz control loop = single CONSUMER]
   ▼
m_currTask   (active — streamed as target setpoints at 20 Hz)
   │  deterministic completion (§4)
   ▼
m_chat.m_completedTasks  (history, feeds next prompt §6)
```

- **No "ReadyToPublish" queue.** Pipeline = pending → active → completed.
- **Queue = `moodycamel::ReaderWriterQueue`** (battle-tested SPSC). Custom
  `LockFreeSpscBufferedQueue` dropped.
- **Strictly SPSC.** Producer = VLM thread; consumer = 20 Hz loop. No third thread mutates
  the queue; the interrupt respects this (§5.1). Handle `enqueue` backpressure (don't drop
  plan steps silently).

---

## 4. Deterministic Task Completion (20 Hz loop)

VLM does not decide completion. On completion: record `m_currTask` (with `thought`) into
`m_completedTasks`, dequeue next.

| Cmd | Predicate | Notes |
|-----|-----------|-------|
| **GO** | 3-D Euclidean dist < **0.20 m** | Pose quality depends on §8 integration (Tello). |
| **ROTATE** | \|yaw − target\| < **5°** | — |
| **TAKEOFF** | altitude ≥ target (low default ~100 cm) AND vz≈0 | **Stall guard:** climb commanded but altitude flat N ticks → emergency (suspected ceiling). Only ceiling detector without hardware. |
| **LAND** | altitude≈0 AND vz≈0 (settled); + backend "landed" state if exposed | Odometry primary; forward-cam frame-diff a weak confirm at best. **Depth estimator gated OFF only in the final 10–30 cm descent, after clear-to-land** — not for the whole maneuver. WHERE to land (two-phase inspect/verify, kSystemPrompt) is planning, distinct from this predicate. |
| **STOP** | emit one hover cycle → **complete instantly** | Hover is the idle default; STOP is near-redundant, kept for VLM expressiveness. |
| **ORBIT** | ≥ 360° accumulated (default 1 rev) OR time limit | **Two modes:** (a) orbit a **point in space** — relative coord, pure odometry arc, no vision (simpler/safer default); (b) orbit a **detected target** — visual servo: keep bbox in frame, hold `median_depth ≈ radius`. Target lost (mode b) → abort → re-assess. Micro go/rotate steps kept small so the target never leaves frame. |
| **SEARCH** | success = target label detected; fail = timeout/expected_time | **2-D horizontal circle** (no vertical zigzag — see §13). Initial 360° step-rotate-**settle**-detect, then expand outward. Record pre-search pose as **anchor**; on fail return via `GO anchor` + mark FAILED. **Default post-search:** success → append re-assess; fail → re-assess. |
| **CURVE** | — | **Dropped for POC** (`GO`-waypoint sugar). |

### 20 Hz streaming contract (PX4 offboard)
Offboard drops if setpoints stop. Every tick: active task → stream its target; queue
empty/none → stream **Hover** (zero velocity). Never send once.

---

## 5. VLM: Event-Driven (no polling)

5-second `m_vlmTimer` **removed**. VLM runs only on: (1) queue empty, (2) `re-assess`
reached, (3) `m_emergencyStop`. Wake via `condition_variable::notify_one()`.

### 5.1 Interrupt & Reassessment (one mechanism, deterministic-first)

1. **Reflexive hold-clearance (deterministic, control loop — no VLM).** Depth sets
   `m_emergencyStop`. The 20 Hz loop immediately commands a setpoint **behind** current
   position: `target = pos + reverse_vec · backoff`, where
   `reverse_vec = -normalize(recent odometry velocity)`, `backoff ≈ 20–30 cm`. This
   *actively holds clearance* — passive hover would overshoot toward the hazard on momentum.
2. **Consumer drains the queue.** The 20 Hz loop (the only legal consumer) drains
   `m_taskQueue` and records the interrupted `m_currTask` as `STOPPED`/`INTERRUPTED` with
   its `thought`. This is the SPSC-safe "wipe"; no third thread clears the queue.
3. **Wake VLM to reassess.** It is told what it was executing, what was queued, and shown
   the current depth map + YOLO-segmented frame highlighting the hazard. It replans to
   clear the hazard and resume the objective.
4. **Producer refills.** VLM pushes the fresh plan into the now-empty queue; loop resumes.

Consumer-drain and interrupt are the **same** mechanism, sequenced.

---

## 6. Dynamic Prompt Construction

Built fresh per VLM invocation (`m_chat.m_systemPrompt` static):

```
[SYSTEM CONFIGURATION]      kSystemPrompt
[COORDINATE FRAME]          FLU (+X Forward, +Y Left, +Z Up)   ← stated to the VLM
[MISSION OBJECTIVE]         initial user goal
[VEHICLE STATE]             Alt, Vx, Vy, Vz, Battery%          (VehicleTelemetry)
[PERCEPTION DATA]           JSON: label, bbox, median_depth_cm (from snapshot §9)
[EXECUTED COMMAND HISTORY]  ALL completed actions: {status, thought, action}
[ACTIVE PENDING QUEUE]      remaining unexecuted commands
```

- **Full history** (~150–200 actions ≈ 17 k tokens, safe < 32 k+).
- **Send both** marked image AND perception JSON (VLM can't read metric depth from pixels;
  JSON carries `median_depth_cm` truth).
- **Preserve `thought`** (`LargeFixedStringType m_thought` per `ActiveTask`); `status`-prefixed.
- Targets addressed by `label`/`id`.

---

## 7. Coordinate Frames & Setpoint Output

- **To the VLM:** FLU (+X fwd, +Y left, +Z up), declared in the prompt.
- **FMU output:** a **generic target setpoint** (position/velocity, body/FLU). The FMU
  stays hardware-agnostic and does **not** speak PX4 or Tello.
- **Per-drone adapter** converts generic setpoint → backend frame + protocol:
  - **PX4:** FLU → NED, streamed as PX4 offboard (`px4_offboard_node`, already ~100 Hz).
  - **Tello:** generic setpoint → `rc a b c d`.
  FLU→NED conversion lives here, written with the adapters (deferred until then).

Division of labor: **FMU decides targets @20 Hz; the adapter streams protocol @its rate.**

---

## 8. Odometry & Position Estimation (POC — no SLAM)

Both backends feed `nav_msgs/Odometry` on `odom`; FMU stores X/Y/Z + yaw in `std::atomic`.

- **PX4 sim:** native odometry (true position).
- **Physical Tello:** no absolute X/Y → integrate `TelloState` velocity in the driver node,
  published as `nav_msgs/Odometry`. **Use trapezoidal quadrature**
  `pos += ½(v[t]+v[t-1])·dt` (or Simpson over 3 samples), **not** forward-Euler — velocity
  is a sampled signal at 10 Hz, so classic RK4 (needs midpoint ODE evals) does not apply;
  higher-order *quadrature* is the correct, cheap accuracy gain. Drift accepted for POC.
- **SLAM / OctoMap / A\*** (Stella-VSLAM, OpenVINS) explicitly deferred post-POC. No TF2.

---

## 9. Perception Ingestion (engine seam)

Design the FMU **now** against two concrete, stubbed engine structs — the FMU knows
nothing of ONNX/YOLO internals, only `TargetDetection[]` + depth stats. Real models drop
in later with zero FMU changes.

```cpp
struct YoloDetectionEngine {   // Model-S, 25 Hz
    size_t detect(const cv::Mat& frame, TargetDetection* out, size_t max);
};
struct YoloDepthEngine {       // Model-D, 30 Hz+
    void   estimate(const cv::Mat& frame, DepthResult& out); // min/med/max + center proximity
};
```

- **Concrete structs, not virtual interfaces** — perception is identical for sim and real
  drone; no runtime polymorphism; keeps POD/perf leanings.
- **Atomic perception snapshot:** a fusion step stamps Model-S + Model-D results **for the
  same frame** into one struct; both the emergency check and the VLM read that snapshot →
  internally consistent perception (see §13 lag). Slightly stale but coherent.
- Stubs return empty data today → control/planning fully buildable/testable before any real model.

---

## 10. Emergency Boundary (velocity-scaled)

A constant fails both ways (50 cm excessive when slow; 30 cm too little when fast):

```
d_trigger = d_hard + v·t_react + v²/(2·a_max)
   d_hard  ≈ 0.25 m    (hard buffer)
   t_react ≈ 0.15–0.20 s (sense + control latency)
   a_max   ≈ 2–4 m/s²  (max braking decel, drone-specific)
   clamp to [0.30, 1.0] m ; all constants tuned in sim
```
`v=0 → ~0.25 m`, `v=1 m/s → ~0.60 m`. Depth thread evaluates this each tick vs current speed.

---

## 11. Battery & Failsafe Supervisor (deterministic, atomic, overrides VLM)

Independent of the VLM. `home` = odometry anchor at mission start; `dist_home = ‖pos−home‖`.
Return feasibility estimate: `cost ≈ dist_home / cruise_speed · drain_rate + reserve`.

| Battery | Action |
|---------|--------|
| > 20% | Normal. |
| ≤ 20% | If return feasible (`remaining > cost`) → **RTH** (queue `GO home` + `LAND`). Else → **land-in-place now**. |
| 10–15%, not RTH, no user override | **Land-in-vicinity.** |
| ≤ 10% (any time) | **Force-land immediately** (abort RTH if active). |

Failsafe state is an atomic; the 20 Hz loop honors it **above** normal queue streaming.

---

## 12. Resolved Decisions

| # | Decision |
|---|----------|
| 1 | No "ReadyToPublish" queue. pending → active → completed. |
| 2 | `start(objective)` bootstrap: first frame → perception APIs → one VLM call for the first command buffer → flip the bool releasing the task-thread `condition_variable`, starting the 20 Hz loop. |
| 3 | FLU→backend conversion in the per-drone setpoint adapter (§7, deferred). |
| 4 | Task queue = `moodycamel::ReaderWriterQueue`. |
| 5 | `GenericCommand::operator= = default` (POD hygiene). |
| 6 | Interrupt = reflexive hold-clearance (reverse) → consumer drain → VLM reassess (§5.1). |
| 7 | `CURVE` dropped for POC. |
| 8 | STOP completes instantly; ORBIT gains point-in-space mode; SEARCH is 2-D circle. |
| 9 | Tello odometry uses trapezoidal integration (§8). |
| 10 | Velocity-scaled emergency boundary (§10). |
| 11 | Deterministic battery/failsafe supervisor (§11). |
| 12 | Atomic perception snapshot for frame-coherent perception (§9). |

---

## 13. Known Risks (open / accepted)

- **Reassess latency window (1–2 s):** drone holds on drifting odometry while VLM thinks;
  reflexive layer must actively hold clearance. Single hazard frame may under-inform escape.
- **Interrupt oscillation:** need hysteresis (resume margin > trigger margin) + max-retries
  → land/abort, else live-lock against a wall.
- **Odometry drift** (dead reckoning) erodes the 0.20 m completion bar and return-home
  accuracy; trapezoidal integration mitigates, not eliminates.
- **Perception coherence/lag:** mitigated by the atomic snapshot (§9); residual staleness
  bounded by keeping speed low in tight spaces (prompt rule).
- **Ceiling-blind takeoff:** only mitigations are low default climb + stall guard (§4).
- **SEARCH 2-D:** accepted blindness to targets at very different altitude; VLM must
  explicitly command an altitude change + re-search for those.
- **ORBIT/SEARCH target loss:** recovery only partially defined (abort → re-assess).

---

## 14. POC Build Slice — usable today, in PX4 Gazebo sim

**Phase 1 (today, sim, NO real perception):**
- `odom` subscriber (PX4 native) → atomic pose/yaw.
- `moodycamel::ReaderWriterQueue` + `translateToBaseCommands` (+ backpressure handling).
- 20 Hz loop: GO/ROTATE/TAKEOFF/LAND completion + Hover default + **generic setpoint out**.
- Setpoint output wired to PX4 offboard via the adapter / `px4_offboard_node`.
- Event-driven VLM (triggers: queue empty, `re-assess`).
- Battery/failsafe supervisor (§11) from sim telemetry.
- `GenericCommand::operator= = default`.
- Perception **stubbed** (empty engines); emergency/interrupt path **disabled** for first bring-up.

**Phase 2 (after Phase 1 flies):** real Model-S/Model-D + snapshot fusion, velocity-scaled
emergency + interrupt/reassess (§5.1/§10), ORBIT/SEARCH controllers, Tello backend +
trapezoidal odometry.

---

## 15. Implementation Gap (repo vs. spec)

Committed `fmu_node.hpp`: 5-second VLM timer; empty `yolo`/`cmdQueue` callbacks; no odom
sub/atomic pose/completion; no threads/emergency/CV; telemetry+targets unpopulated; **no
setpoint output**; ignores enqueue backpressure. `SYS-10` odom + 20 Hz loop + queue swap
drafted, never applied.

---

## 16. Open Items

- [ ] Interrupt hysteresis + max-retries → land/abort.
- [ ] Tune §10 constants (`t_react`, `a_max`) and §11 battery model (`drain_rate`, reserve) in sim.
- [ ] `start()` bootstrap (decision #2).
- [ ] Generic setpoint message type + PX4 adapter wiring (§7).
- [ ] Perception engine stubs + snapshot fusion (§9).
- [ ] ORBIT visual-servo + point-in-space controllers; SEARCH pattern.
- [ ] Rephrase kSystemPrompt interruption text to match §5.1 (draft in Appendix A).
- [ ] Confirm `GenericCommand` stays same-machine only (raw-byte union not network-portable).

---

## Appendix A — Draft kSystemPrompt "Execution Model" (replaces old interrupt text)

```
EXECUTION MODEL
The host executes your plan sequentially, streaming each command to the drone until
deterministic sensors confirm it is complete. You are NOT polled continuously. You are
woken to (re)plan ONLY when:

1. QUEUE EMPTY   — your previous plan finished; produce the next plan.
2. YOUR re-assess — you deliberately paused to look around.
3. INTERRUPT     — the host's high-rate depth monitor detected an imminent collision.
                   Before waking you, the host has ALREADY reflexively stopped the drone
                   and backed it a short distance from the hazard to hold clearance. The
                   drone is now hovering safely.

On an INTERRUPT you are given: what you were executing, what remained queued, and the
current post-processed depth map + YOLO-segmented frame highlighting what you came too
close to. Reassess: Why was I stopped? What was I trying to do? How do I get around
<hazard> without colliding and still make progress toward the mission? Output a NEW plan
that first clears the hazard, then resumes the objective. The old queue is discarded —
your new plan fully replaces it.
```
```
