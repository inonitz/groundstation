# Groundstation — FMU Architecture Specification

> **Status:** PLANNING / SPEC. Not yet implemented. The committed `fmu_node.hpp`
> reflects an earlier design (`SYS-58`) and is behind this document. This file is the
> source of truth for the intended design.
>
> **Scope:** `FlightManagementUnitNode` (`source/llm_to_action/fmu/`) — the high-level
> VLM planner + deterministic 20 Hz control loop. Hardware-agnostic (PX4 sim and
> physical DJI Tello share one interface).

---

## 1. Design Goals

- **Off-board compute.** Drone is a dumb peripheral. All planning, perception, control
  math run on the ground station.
- **VLM plans, math executes.** The VLM produces flight *plans*. It is **never** in the
  per-command completion loop (1–2 s inference is far too slow). Completion is checked
  with deterministic geometry against live odometry.
- **Hardware-agnostic.** No PX4/DJI specifics in the FMU. Both backends publish
  `nav_msgs/Odometry` and consume one setpoint abstraction.
- **No heap in steady state.** Fixed-size command structs (`FixedStringType`), a
  lock-free SPSC ring for the task queue, atomics for shared pose/flags.

### Hard coding constraints (non-negotiable)
- No `std::variant` → C-style POD union (`GenericCommand`).
- No exceptions / `try-catch` → `.empty()` (OpenCV), `.is_discarded()` (nlohmann).
- No mutex on the image pointer → C++17 `std::atomic_load`/`atomic_store` on `shared_ptr`.
- C89 variable hoisting: all locals declared at the top of each function.
- `FixedStringType`=`char[32]`, `LargeFixedStringType`=`char[128]`; fill via `strncpy`.
  No `std::string` inside command/task structs.
- Enums one-per-line, lines ≤ 95 chars, struct default member initializers kept.

---

## 2. Thread Architecture

Four decoupled units. ROS2 `MultiThreadedExecutor` + callback groups isolate the
blocking VLM call from the real-time paths.

| Thread | Rate | Responsibility | Priority |
|--------|------|----------------|----------|
| **Depth (Model-D)** | ≥ 30 Hz | Center-frame proximity. Obstacle inside dynamic boundary → assert `m_emergencyStop` + wake VLM. | Highest |
| **YOLO-Seg (Model-S)** | 25 Hz | Bounding boxes / segmentation; fuse with latest depth into `TargetDetection[]`. | High |
| **VLM (async)** | event-driven | Sleeps on `condition_variable`. Wakes only on a trigger (§5). Blocks seconds; must never stall control. | Low |
| **Control loop** | 20 Hz | Deterministic completion check + continuous setpoint streaming to the drone. | Real-time |

Depth and segmentation are decoupled from each other and from control; depth has strict
priority and runs faster. `m_emergencyStop` is `std::atomic<bool>`.

---

## 3. Data Flow & Queue

```
VLM plan (JSON)
   │  translateToBaseCommands()   [VLM thread = single PRODUCER]
   ▼
m_taskQueue  (moodycamel::ReaderWriterQueue<ActiveTask>, FIFO, SPSC)   ── pending
   │  try_dequeue()              [20Hz control loop = single CONSUMER]
   ▼
m_currTask   (active — streamed to drone at 20 Hz)
   │  deterministic completion (§4)
   ▼
m_chat.m_completedTasks  (history, feeds next prompt §6)
```

- **No "ReadyToPublish" queue.** Pipeline is exactly pending → active → completed.
- **Queue = `moodycamel::ReaderWriterQueue`** (battle-tested SPSC). The custom
  `LockFreeSpscBufferedQueue` is dropped (bug list > reuse value).
- **Strictly SPSC.** Producer = VLM thread; consumer = 20 Hz loop. No third thread ever
  mutates the queue — the interrupt path respects this (§5.1).

---

## 4. Deterministic Task Completion (20 Hz loop)

The VLM does not decide completion. The loop compares live odometry against the active
target. On completion: record `m_currTask` (with its `thought`) into `m_completedTasks`,
then dequeue the next.

| Cmd | Completion predicate | Notes |
|-----|----------------------|-------|
| **GO** | 3-D Euclidean dist < **0.20 m** | Degrades as dead-reckon drift → 20 cm. |
| **ROTATE** | \|yaw − target\| < **5°** | — |
| **TAKEOFF** | altitude ≥ target (low default ~100 cm) AND vz≈0 | **Stall guard:** climb commanded but altitude flat for N ticks → emergency (suspected ceiling). Only ceiling detector without hardware. |
| **LAND** | altitude≈0 AND vz≈0 (settled); + backend "landed" state if exposed | Odometry is **primary**. Forward-cam frame-diff is at most a weak confirm. **Depth emergency gated OFF during LAND / low altitude.** Landing *WHERE* (two-phase inspect/verify, kSystemPrompt) is planning, distinct from this predicate. |
| **STOP** | zero-velocity held for a **dwell** (N ticks, vel≈0) | Needs a duration or completes instantly (hover is the idle default). |
| **ORBIT** | ≥ 360° accumulated around target (default 1 rev) OR time limit | Dedicated hardcoded visual-servo controller: keep target bbox in frame, hold `median_depth ≈ radius`, emit micro go/rotate setpoints. **Target lost → abort → re-assess.** |
| **SEARCH** | success = target label detected; fail = timeout/expected_time | Step-rotate-**settle**-detect (not continuous spin; blur kills detection). Initial 360° sweep, then zigzag in default-radius sphere along the *initial heading*. On fail: return to pre-search pose, mark FAILED. **Default post-search: hand to VLM (append re-assess).** |
| **CURVE** | — | **Dropped for POC.** `GO`-with-waypoints sugar; expand to N `CmdGo` at translate-time only if ever needed. |

### 20 Hz streaming contract (PX4 offboard)
Offboard mode drops if setpoints stop. Every tick: active task → stream its setpoint;
queue empty / no active task → stream **Hover** (zero velocity). Never send once.

---

## 5. VLM: Event-Driven (no polling)

The 5-second `m_vlmTimer` is **removed**. VLM runs only on:
1. **Queue empty** — needs a new plan.
2. **`re-assess` reached** — planned look-around stop.
3. **Emergency override** — depth thread asserted `m_emergencyStop`.

Wake: `condition_variable::notify_one()` on the VLM thread.

### 5.1 Interrupt & Reassessment (single mechanism)

On interrupt the **deterministic layer acts first, VLM second**:

1. **Reflexive stop (deterministic, control loop).** Depth thread sets `m_emergencyStop`.
   The 20 Hz loop immediately streams Hover — and, if inside the hard boundary, a
   reflexive **reverse** ("back off N cm") to actively hold clearance. No VLM in this path.
2. **Consumer drains the queue.** The control loop (the *only* legal consumer) drains
   `m_taskQueue` to empty and records the interrupted `m_currTask` as
   `STOPPED`/`INTERRUPTED` **with its `thought`**. This is the SPSC-safe "wipe": no third
   thread ever clears the queue.
3. **Signal clear → VLM reassesses.** Once drained/holding, wake the VLM. It sees: what
   it was executing, what it had queued, and the new (obstacle) frame, and replans.
4. **Producer refills.** VLM pushes the fresh plan into the now-empty queue; the loop
   resumes streaming.

The consumer-drain and the interrupt are the **same** mechanism, just sequenced.

---

## 6. Dynamic Prompt Construction

Built fresh each VLM invocation. `m_chat.m_systemPrompt` stays static; dynamic context
is assembled per call:

```
[SYSTEM CONFIGURATION]      kSystemPrompt
[COORDINATE FRAME]          FLU (+X Forward, +Y Left, +Z Up)   ← stated to the VLM
[MISSION OBJECTIVE]         initial user goal
[VEHICLE STATE]             Alt, Vx, Vy, Vz, Battery%          (VehicleTelemetry)
[PERCEPTION DATA]           JSON: label, bbox, median_depth_cm (TargetDetection[])
[EXECUTED COMMAND HISTORY]  ALL completed actions: {status, thought, action}
[ACTIVE PENDING QUEUE]      remaining unexecuted commands
```

- **Full history, not a sliding window** (~150–200 actions ≈ 17 k tokens, safe < 32 k+).
- **Send both** the marked/overlaid image AND the perception JSON (VLMs can't extract
  reliable metric depth from pixels; JSON carries `median_depth_cm` ground truth).
- **Preserve `thought`** (`LargeFixedStringType m_thought` per `ActiveTask`) — stripping
  reasoning breaks reflection and invites oscillation. `status`-prefixed history entries.
- Targets addressed by `label`/`id`; VLM references `target_object` by that name.

---

## 7. Coordinate Frames

- **To the VLM:** FLU (+X fwd, +Y left, +Z up), declared in the prompt.
- **At output/publish:** backend frame may differ (PX4 = NED). **FLU → backend-frame
  conversion lives in the per-drone setpoint adapter** (written alongside the adapters,
  not in the FMU planner). Deferred until adapter work.

---

## 8. Odometry (POC — no SLAM yet)

Both backends feed **`nav_msgs/Odometry`** on `odom`. FMU stores X/Y/Z (and yaw) in
`std::atomic` for the 20 Hz loop.

- **PX4 sim:** native odometry.
- **Physical Tello:** no absolute X/Y → dead-reckon `pos += vel·dt` from `TelloState`
  in the Tello driver node, published as standard `nav_msgs/Odometry`. Drift accepted for POC.
- **SLAM / OctoMap / A\*** (Stella-VSLAM, OpenVINS) explicitly deferred post-POC. No TF2.

---

## 9. Perception Ingestion (engine seam)

Design the FMU **now** against two concrete, stubbed engine structs. The FMU knows
nothing of ONNX/YOLO internals — only `TargetDetection[]` and depth stats. Real models
drop in later with **zero FMU changes**.

```cpp
struct YoloDetectionEngine {   // Model-S, 25 Hz
    size_t detect(const cv::Mat& frame, TargetDetection* out, size_t max);
};
struct YoloDepthEngine {       // Model-D, 30 Hz+
    void   estimate(const cv::Mat& frame, DepthResult& out); // min/med/max + center proximity
};
```

- **Concrete structs, not virtual interfaces** — perception is identical for sim and real
  drone (just camera frames); no runtime polymorphism needed; keeps POD/perf leanings.
- Seg thread → `detect()`; depth thread → `estimate()`; a fusion step merges per-target
  depth into `TargetDetection[]`.
- Stubs return dummy/empty data today → the control/planning architecture is fully
  buildable and testable before any real model exists.

---

## 10. Resolved Decisions

| # | Decision |
|---|----------|
| 1 | No "ReadyToPublish" queue. Pipeline = pending → active → completed. |
| 2 | `start(objective)` bootstrap: grab first frame → call perception APIs → invoke VLM once for the first command buffer → flip the bool that releases the task-thread `condition_variable`, starting the 20 Hz loop. |
| 3 | FLU → backend-frame conversion in the per-drone setpoint adapter (deferred). |
| 4 | Task queue = **`moodycamel::ReaderWriterQueue`**. Custom `LockFreeSpscBufferedQueue` dropped. |
| 5 | `GenericCommand::operator= = default` (POD hygiene; not load-bearing for moodycamel). |
| 6 | Interrupt = reflexive deterministic STOP/reverse first, then VLM reassess (§5.1). Queue drain is the consumer's job, folded into the interrupt handshake. |
| 7 | `CURVE` dropped for the POC. |

---

## 11. Known Architecture Risks (open)

- **Braking distance.** Fixed 50 cm trigger is unsafe at speed. Emergency boundary must
  scale with current velocity (reaction-latency × speed + margin). Reflexive reverse, not
  just hover, when inside the hard boundary.
- **Reassess latency window (1–2 s).** Drone holds on drifting dead-reckoned odometry;
  the reflexive layer must actively hold clearance during VLM thinking. Single obstacle
  frame may give too little context to plan an escape.
- **Interrupt oscillation.** Need hysteresis (resume-clearance margin > trigger margin)
  and a max-retries → land/abort fallback to avoid live-lock against a wall.
- **Landing vs depth emergency.** Ground reads as "close" — depth emergency must be gated
  during LAND / low altitude.
- **Odometry drift** (dead reckoning) erodes the 20 cm completion bar and "return-home"
  accuracy over time and after emergencies.
- **Orbit/Search target loss.** Recovery on target-out-of-frame only partially defined.
- **No deterministic mission abort** on low battery / global timeout (VLM may not
  self-preserve). Needs a hard rule.
- **Frame/time sync** across perception ↔ VLM ↔ emergency (detections may lag the
  emergency frame).
- **Ceiling-blind takeoff** — no upward sensor; mitigated only by low default climb + the
  stall guard (§4).
- **Threshold reconciliation:** depth emergency **50 cm** (SYS-59) vs **30 cm**
  (kSystemPrompt) — pick one.

---

## 12. Implementation Gap (repo vs. spec)

Committed `fmu_node.hpp` still has: the 5-second VLM wall timer; empty
`yolo`/`cmdQueue` callbacks; **no** odom subscriber / atomic pose / deterministic
completion; no depth/YOLO threads; no emergency flag / condition_variable; telemetry &
targets never populated; **no setpoint output at all**; and `translateToBaseCommands`
ignores enqueue backpressure. The `SYS-10` odom + 20 Hz loop + queue swap were drafted,
never applied.

---

## 13. Open Items

- [ ] Velocity-scaled emergency boundary + reflexive reverse (§11).
- [ ] Interrupt hysteresis + max-retries → land/abort fallback.
- [ ] Depth-emergency gating during LAND / low altitude.
- [ ] Deterministic mission abort rule (battery / global timeout).
- [ ] ORBIT visual-servo controller; SEARCH pattern + post-search default.
- [ ] `start()` bootstrap sequence (decision #2).
- [ ] Perception engine stubs + fusion step (§9); telemetry ingestion.
- [ ] Reconcile 30 cm vs 50 cm emergency threshold.
- [ ] Rephrase kSystemPrompt interruption text to match §5.1.
- [ ] Confirm `GenericCommand` stays same-machine only (raw-byte union not portable
      across a network boundary).
```
