# Groundstation — Project Overview

*A short architectural and technological briefing, written to frame a discussion with an
advisor. It describes what the system is, the deliberately simple navigation method running
today ("Being A"), and the more principled mapping-and-planning method we have specced but
not yet built ("Being B"). It closes with open questions and candidate next steps.*

---

## 1. What the system is

Groundstation is an **off-board autonomous flight stack** for small drones (primary target:
DJI Tello; PX4 software-in-the-loop in Gazebo as the simulation fallback). The guiding
principle is **off-board compute**: the aircraft is a dumb peripheral that only streams
H.264 video and telemetry over the local network. All perception, planning, and control run
on a ground-station computer.

The control philosophy is **"the VLM plans, deterministic math executes."**

- A local **Vision-Language Model** (Qwen3-VL served by `llama-server`) acts as a high-level,
  event-driven planner. When the task queue drains, it is shown the current camera frame,
  a compact vehicle-state summary, a perception JSON (YOLO detections + metric depth), and
  the executed-command history, and it returns a **plan**: a JSON array of discrete verbs
  (`takeoff`, `go`, `rotate`, `land`, `stop`, and — specced — `approach`, `orbit`, `search`).
  It is never in the per-command completion loop; inference runs off the control thread.
- A **deterministic 20 Hz control loop** consumes that plan one task at a time, owns the
  flight state machine (STANDBY / TAKEOFF / FLIGHT / LANDING), and streams setpoints to the
  flight controller through a **~100 Hz offboard publisher**.

### Technology stack

| Layer | Choice |
|---|---|
| Language / build | C++17, CMake + Ninja, dependency fetch via CPM |
| Middleware | ROS 2 (Humble) |
| Planner (VLM) | Qwen3-VL, local `llama-server` over HTTP |
| Perception | YOLO detection + metric depth (YOLO26n-depth), OpenCV, cv_bridge |
| Speech front-end | Whisper/Sherpa ASR, X11 push-to-talk keyboard hook |
| Video transport | GStreamer (H.264 over UDP) |
| Flight controllers | PX4 (SITL, `px4_msgs`) and DJI Tello (`ctello`) |
| Simulation | Gazebo + PX4 SITL |

### Backend abstraction

The two flight controllers are hidden behind a **compile-time backend interface** (CRTP,
`GenericBackend<Derived>`): a single set of verbs (`start/takeoff/land/set_velocity/odometry/
state/...`) with no virtual dispatch. One backend is selected at configure time and produces one
FMU binary. Across that interface the canonical world frame follows the **ENU convention**; PX4
speaks **NED** on the wire and the Tello uses
**FLU** stick commands, and each backend converts internally.

---

## 2. Being A — the current WIP navigation method ("the dumb odometry trick")

This is what flies today in SITL. It is intentionally the **simplest thing that produces a
demonstrable autonomous flight**, chosen because integrating full SLAM was out of scope for
an initial proof of concept.

**How movement works.** There is **no map and no global localization**. Position is
**dead-reckoned relative to the takeoff ("home") point** using the flight controller's own
onboard estimator — PX4's EKF `VehicleOdometry` in sim, and the Tello driver's dead-reckoned
`nav_msgs/Odometry` on hardware. A `go forward 1 m` command is interpreted as a **relative
FLU displacement**, converted **once** into a fixed world waypoint, and then flown by a
velocity-guidance law (line-of-sight direction frozen at activation + a cross-track PID that
pulls the aircraft back onto the line — standard "carrot-chasing" guidance). Task completion
is a simple predicate (e.g. 3-D distance to waypoint < 0.20 m).

**Known weaknesses (measured in SITL).**

- The absolute position estimate **drifts** over a long flight with no GPS or vision anchor,
  so one-shot "convert a displacement into a world point and fly to it open-loop" accumulates
  error.
- Velocity-only offboard control has **no altitude hold** and the FC's velocity controller
  lags, producing a characteristic **arc / logarithmic-spiral ground track** near a waypoint
  (root-caused: constant-speed pure pursuit toward a fixed point with lateral momentum the
  weak setpoint can't cancel).

**The pragmatic pivot already underway.** Rather than keep tuning point-to-point flight, the
plan is to drive `go`-style motion from a **continuously re-computed visual error signal**:
recompute the direction vector to a **YOLO-detected target every tick** and nudge toward it,
so the control is **re-anchored to ground truth (the object in frame) every cycle** instead
of dead-reckoning from a stale estimate. This sidesteps the drift problem without a map, and
is the substrate for the specced `approach` / `orbit` / `search` behaviors — all of which are
explicitly **anchored to an in-frame target only**, precisely because there is no reliable
global anchor yet.

**In one sentence:** *home-relative dead reckoning plus in-frame visual servoing — no world
model, no obstacle awareness, good enough to demo, brittle over distance and time.*

---

## 3. Being B — the prepared advanced method (SLAM + OctoMap + A*)

This is the specced-but-not-yet-integrated target architecture that would replace Being A's
dead reckoning with a **consistent, GPS-denied global metric frame and planned,
collision-free paths**. Scaffolding lives in `source/slam/`.

**The three pieces.**

1. **Localization — monocular VSLAM / VIO.** Stella-VSLAM (visual) and/or OpenVINS (visual-
   inertial) provide a **globally consistent 6-DoF pose** in GPS-denied environments,
   anchored to the initial home-flight position. This gives a metric position estimate that
   does not drift the way raw dead reckoning does.
2. **World model — OctoMap.** A probabilistic **3-D occupancy map** (octree of voxels) built
   incrementally from the SLAM/VIO point cloud and depth, representing free / occupied /
   unknown space.
3. **Global planning — A\* over the OctoMap.** Search for a **collision-free path** through
   the occupancy grid to a goal, enabling **dynamic obstacle avoidance** rather than blind
   straight-line flight.

**Why it is a separate "being" and not an increment of A.** It changes the *substrate* of
navigation — from "fly a remembered displacement" to "localize in a persistent metric map and
plan a route through it." It introduces real-time constraints (SLAM tracking rate, map update
cost, replanning latency), robustness questions (relocalization after tracking loss, scale
drift in monocular SLAM, map staleness), and a much larger integration surface. It is the
principled answer to the exact weaknesses Being A papers over.

**In one sentence:** *localize globally with SLAM, remember the world as an OctoMap, and plan
through it with A* — the proper solution to obstacle-aware GPS-denied autonomy.*

---

## 4. How the two relate

```
Being A (today):   VLM plan ─► relative displacement ─► FC-odometry dead reckoning ─► velocity guidance
                                                   (+ in-frame YOLO visual servoing to fight drift)

Being B (target):  VLM plan ─► goal in a global metric frame ─► A* path over OctoMap ─► guidance
                                     ▲                                   ▲
                              SLAM/VIO pose                     occupancy from SLAM cloud + depth
```

Being A and Being B share the same **planner (VLM), backend interface, and 20 Hz executor**. The
swap is confined to *what the motion commands are computed against*: a stale dead-reckoned
waypoint (A) versus a planned path in a SLAM-anchored map (B). The visual-servoing work in A
is not wasted — a live, re-anchored error signal is complementary to, and a stepping stone
toward, the map-based approach.

---

## 5. Questions that might be answered by someone a little more experienced than me

**On the advanced method (Being B):**

1. For a **single monocular camera** on a small drone, is **VIO (OpenVINS)** clearly
   preferable to pure monocular VSLAM (Stella-VSLAM) given the scale-observability and drift
   issues, or is the added IMU-calibration burden not worth it at this scale?
2. What is a realistic expectation for **relocalization / loop closure** reliability indoors,
   and how should the control loop behave during **tracking loss** (hold? descend? revert to
   Being A dead reckoning as a fallback)?
3. Is **OctoMap** still the right choice for the mapping layer, or would a modern alternative
   (e.g. ESDF-based or GPU voxel maps) better serve **real-time A\* replanning** on a ground
   station?
4. At what **update/replanning rates** does A*-over-OctoMap remain tractable for reactive
   avoidance, and where is the usual bottleneck — map integration, or the search itself?
5. Is there a principled **intermediate milestone** between A and B (e.g. SLAM for pose only,
   no mapping/planning yet) that de-risks the integration?

**On the current WIP (Being A):**

6. Is **continuously re-anchored visual servoing to an in-frame target** a defensible interim
   navigation strategy for a POC, or does it hide problems that will resurface the moment a
   goal is *not* visible?
7. For the waypoint arc/spiral: is switching `go` to a **PX4 position setpoint** (straight
   line + smooth deceleration + altitude hold) the right fix, or does committing to
   position-mode setpoints undercut the hardware-agnostic velocity abstraction we need for
   the Tello?
8. How should we think about **frame consistency** (ENU convention / NED wire / FLU body) as we add
   a SLAM frame — one more transform, or a source of subtle bugs to design against up front?

**On sequencing / best next steps:**

9. Given limited time, what is the highest-value next step: hardening Being A's visual
   servoing to a solid demo, or beginning the Being B SLAM-pose integration behind a fallback?
10. What would you want to **see measured** to consider the current approach validated before
    moving on?

---

## 6. Candidate next steps (our current thinking, for critique)

- **Short term (Being A):** convert `go` toward the recommended fix for the arc, and wire the
  live-YOLO-target servo so motion is re-anchored every tick; land a clean end-to-end
  SITL demo.
- **Medium term (bridge):** bring up **SLAM/VIO for pose only** (`source/slam/`), publish a
  global pose, and let the FMU consume it as an *optional, better* odometry source behind the
  existing backend interface — no mapping or planning yet.
- **Long term (Being B):** add OctoMap from the SLAM cloud + depth, then A* global planning
  with dynamic replanning, and route VLM goals through the planner instead of dead reckoning.

---

*Repository references: `ARCHITECTURE.md` (FMU spec), `NOTES.md` (SITL debugging log and
control-law iteration history), `source/llm_to_action/` (FMU, backends, perception glue),
`source/slam/` (VSLAM/VIO scaffolding).*
