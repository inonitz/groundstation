# PX4Backend Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every PX4-specific wire detail (publishers, subscriptions, arm/OFFBOARD handshake, ~30 Hz stream loop, NED math) out of `FlightManagementUnitNode` into one concrete `PX4Backend` class, so the FMU becomes a platform-neutral flight state machine that issues semantic verbs.

**Architecture:** A concrete `PX4Backend` (no CRTP, no base class — one backend exists today) owns the PX4 pubs/subs/timer/handshake and the shared `std::atomic` state. The FMU holds one `PX4Backend m_backend`, drives it through verbs (`takeoff/land/set_velocity/disarm/force_disarm`), and reads back an `Odometry` snapshot + an `IOState`. The extraction lands NED-through (structural parity first); a final task flips the seam to canonical ENU behind a numeric direction assert.

**Tech Stack:** C++17, ROS 2 Humble (`rclcpp`), `px4_msgs`, single ROS node with a `Reentrant` callback group, `std::atomic` for cross-callback state. No exceptions.

## Global Constraints

- **The implementer does NOT compile or run ROS/SITL.** The human operator compiles and runs `scripts/simenv_llm.sh` (canned takeoff → go 1 m → land). Per-task verification = (a) operator compiles, (b) operator runs the canned smoke test, (c) operator/agent diffs the `[DIAG]` log against the known-good baseline (`output.txt`). Frame-math tasks additionally ship a **standalone, ROS-free** numeric test the implementer CAN run with `g++`.
- **Preserve the proven concurrency model.** Keep the `Reentrant` callback group and `std::atomic` scalar sharing that flies today. Do NOT introduce a mutex, a `Shared<T>`, or a single-threaded executor in this slice (deferred to Future-Milestone M1 in the spec).
- **Do NOT touch planner-side code:** `GenericCommand`/`Cmd*` unions, `translateToBaseCommands`, `injectCannedPlan`, `buildDynamicPrompt`, `callLlamaServer`, the `spsc_queue<ActiveTask>`, `HistoryBuffer`, `kSystemPrompt`. They are frame-agnostic and stay byte-for-byte.
- **Tuning values (verbatim, NED):** `kTakeoffTargetAltNed = -2.0f`, `kTakeoffClimbVelNed = -2.0f`, `kLandDescendVelNed = 0.5f`, `kGroundContactAltNed = -0.1f`, `kGoCompletionRadiusM = 0.20f`, `kDefaultGoSpeedCmS = 30.0f`. ENU equivalents (Task 4): target `+2.0`, climb `+2.0`, descend `-0.5`, ground `~-0.1`→`z<=0.1`.
- **PX4 gotchas (verbatim):** VehicleStatus topic is `/fmu/out/vehicle_status_v4` (MESSAGE_VERSION=4); odometry is `/fmu/out/vehicle_odometry` (no suffix). Arm FIRST, then request OFFBOARD, retry every tick until `ARMING_STATE_ARMED` + `NAVIGATION_STATE_OFFBOARD`. Gate the handshake on `m_gotFirstOdom` + warmup (`kOffboardWarmupSetpoints = 40`).
- Commit after each task with a descriptive message. Branch: `feature-showcase-v2` (already checked out).

---

### Task 1: ROS-free frame conversions + `px4_backend_base.hpp` (absorb the translator)

Splits the old `offboard_translator.hpp` into (a) pure `Vec3` math with **no** ROS include (so it is unit-testable) and (b) the PX4 message builders/QoS/constants. Adds the NED↔ENU conversions the ENU seam will need in Task 4 (defined now, exercised later).

**Files:**
- Create: `source/llm_to_action/px4_backend/frame_convert.hpp`
- Create: `source/llm_to_action/px4_backend/px4_backend_base.hpp`
- Test: `source/llm_to_action/px4_backend/test/frame_convert_test.cpp`
- (Delete in Task 3, not now: `source/llm_to_action/fmu/offboard_translator.hpp`)

**Interfaces:**
- Produces (`frame_convert.hpp`, all `static inline`, operate on `struct Vec3 { f32 x,y,z; }`):
  - `Vec3 flu_to_ned(Vec3 flu, f32 yawNed)` — carried over verbatim from the translator.
  - `Vec3 flu_to_enu(Vec3 flu, f32 yawEnu)` — FLU→ENU (Task 4 consumer).
  - `Vec3 ned_to_enu(Vec3 ned)` → `{ned.y, ned.x, -ned.z}`.
  - `Vec3 enu_to_ned(Vec3 enu)` → `{enu.y, enu.x, -enu.z}` (self-inverse).
  - `f32 enu_yaw_from_ned(f32 yawNed)` → wrap(`M_PI_2 - yawNed`); `f32 ned_yaw_from_enu(f32)` (same form).
  - `f32 enu_yawrate_to_ned(f32 r)` → `-r`.
- Produces (`px4_backend_base.hpp`): the existing `OffboardTranslator` builders unchanged — `mode_velocity(u64)`, `velocity_setpoint(u64, Vec3, f32)`, `arm(u64,bool)`, `set_offboard(u64)`, `force_disarm(u64)`, `make_command(...)`, msg `using`s (`TrajectorySetpoint`/`OffboardControlMode`/`VehicleCommand`), `kDroneSysId`/`kGroundSysId`. Plus a QoS helper `static rclcpp::QoS px4_qos()` (best_effort + transient_local, depth 10) and the NED tuning constants (moved out of `fmu_node_base.hpp`).

- [ ] **Step 1: Write the failing test** (`frame_convert_test.cpp`)

```cpp
#include "../frame_convert.hpp"
#include <cmath>
#include <cstdio>
#include <cassert>

static bool close(f32 a, f32 b) { return std::fabs(a - b) < 1e-4f; }
static bool vclose(Vec3 a, Vec3 b) { return close(a.x,b.x) && close(a.y,b.y) && close(a.z,b.z); }

int main() {
    // ned_to_enu and enu_to_ned are inverses.
    Vec3 ned{1.0f, 2.0f, 3.0f};
    assert(vclose(enu_to_ned(ned_to_enu(ned)), ned));
    // Axis identities: NED north(+x) -> ENU north(+y); NED down(+z) -> ENU up(-z).
    assert(vclose(ned_to_enu({1,0,0}), {0,1,0}));
    assert(vclose(ned_to_enu({0,0,1}), {0,0,-1}));
    // "Forward 1m" FLU at spawn yaw 2.10 rad (NED) matches the NOTES.md-verified result.
    Vec3 f = flu_to_ned({1.0f,0.0f,0.0f}, 2.10f);
    assert(close(f.x, std::cos(2.10f)) && close(f.y, std::sin(2.10f)));
    // ENU "forward 1m" points along ENU heading: flu_to_enu -> (cos,sin) in E,N.
    Vec3 fe = flu_to_enu({1.0f,0.0f,0.0f}, 0.0f);   // yawEnu 0 = facing East
    assert(vclose(fe, {1,0,0}));
    std::printf("frame_convert_test OK\n");
    return 0;
}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `g++ -std=c++17 -I <util2-include> source/llm_to_action/px4_backend/test/frame_convert_test.cpp -o /tmp/fct && /tmp/fct`
Expected: FAIL to compile — `frame_convert.hpp` does not exist yet.
(`util2/C/base_type.h` supplies `f32`; point `-I` at its include root, same one CMake uses.)

- [ ] **Step 3: Write `frame_convert.hpp`**

```cpp
#pragma once
#include <cmath>
#include <util2/C/base_type.h>

struct Vec3 { f32 x{0.0f}, y{0.0f}, z{0.0f}; };

static inline f32 wrap_pi(f32 a) {
    while (a >  (f32)M_PI) a -= 2.0f*(f32)M_PI;
    while (a < -(f32)M_PI) a += 2.0f*(f32)M_PI;
    return a;
}
// Body FLU (fwd,left,up) -> world NED (north,east,down). yaw is NED (CW+ from north).
static inline Vec3 flu_to_ned(Vec3 flu, f32 yawNed) {
    f32 c = std::cos(yawNed), s = std::sin(yawNed);
    return { flu.x*c + flu.y*s, flu.x*s - flu.y*c, -flu.z };
}
static inline Vec3 ned_to_enu(Vec3 v) { return { v.y, v.x, -v.z }; }
static inline Vec3 enu_to_ned(Vec3 v) { return { v.y, v.x, -v.z }; }
static inline f32  enu_yaw_from_ned(f32 yawNed) { return wrap_pi((f32)M_PI_2 - yawNed); }
static inline f32  ned_yaw_from_enu(f32 yawEnu) { return wrap_pi((f32)M_PI_2 - yawEnu); }
static inline f32  enu_yawrate_to_ned(f32 r) { return -r; }
// Body FLU -> world ENU: derive by composing through NED so signs stay consistent.
static inline Vec3 flu_to_enu(Vec3 flu, f32 yawEnu) {
    return ned_to_enu(flu_to_ned(flu, ned_yaw_from_enu(yawEnu)));
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `g++ -std=c++17 -I <util2-include> source/llm_to_action/px4_backend/test/frame_convert_test.cpp -o /tmp/fct && /tmp/fct`
Expected: `frame_convert_test OK`.

- [ ] **Step 5: Write `px4_backend_base.hpp`** — copy the `OffboardTranslator` struct body from `offboard_translator.hpp` verbatim (builders `mode_velocity`/`velocity_setpoint`/`arm`/`set_offboard`/`force_disarm`/`make_command`, the msg `using`s, `kDroneSysId`/`kGroundSysId`), replacing its private `Vec3`/`flu_to_ned` with `#include "frame_convert.hpp"`. Add:

```cpp
static rclcpp::QoS px4_qos() { rclcpp::QoS q(10); q.best_effort(); q.transient_local(); return q; }
// NED tuning constants moved here from fmu_node_base.hpp (kept NED for Tasks 1-3):
constexpr f32 kTakeoffTargetAltNed = -2.0f;
constexpr f32 kTakeoffClimbVelNed  = -2.0f;
constexpr f32 kLandDescendVelNed   =  0.5f;
constexpr f32 kGroundContactAltNed = -0.1f;
```
(Include `<rclcpp/rclcpp.hpp>` for the QoS helper.)

- [ ] **Step 6: Commit**

```bash
rtk git add source/llm_to_action/px4_backend/frame_convert.hpp source/llm_to_action/px4_backend/px4_backend_base.hpp source/llm_to_action/px4_backend/test/frame_convert_test.cpp
rtk git commit -m "feat(px4_backend): ROS-free frame_convert + base (absorb translator)"
```

---

### Task 2: `PX4Backend` class — owns wire, handshake, stream loop, atomics

Lifts `offboardPublishLoop`, `odomCallback`, `statusCallback`, the three publishers, two PX4 subscriptions, and every PX4-related atomic out of the FMU into one class. Behavior is preserved 1:1; the only new concept is `IOState` replacing the `m_offboardEngaged` bool (STANDBY/HANDSHAKING/FLIGHT/FAULT). Still NED end-to-end.

**Files:**
- Create: `source/llm_to_action/px4_backend/px4_backend.hpp`
- Create: `source/llm_to_action/px4_backend/px4_backend.cpp`

**Interfaces:**
- Consumes: `frame_convert.hpp` (`Vec3`), `px4_backend_base.hpp` (`OffboardTranslator`, `px4_qos`, NED constants).
- Produces (public API the FMU will call in Task 3):
  ```cpp
  struct BackendStatus { enum class Code : u8 { OK, PENDING, REJECTED, FAULT }; Code code{Code::OK}; };
  enum class IOState : u8 { STANDBY, HANDSHAKING, FLIGHT, FAULT };
  struct Odometry { Vec3 pos; f32 yaw{0}; u64 host_stamp_us{0}; bool valid{false}; };  // NED for now

  class PX4Backend {
  public:
      PX4Backend(rclcpp::Node* node, rclcpp::CallbackGroup::SharedPtr cbg);
      void start();                         // create pubs/subs + stream timer
      void stop();                          // cancel stream timer (dtor also calls it)
      BackendStatus takeoff();              // STANDBY->HANDSHAKING, arm warmup start; else REJECTED
      BackendStatus land();                 // no-op OK (FMU streams descent)
      void set_velocity(Vec3 worldVel, f32 yawspeed);  // NED vel; stored in atomics
      void disarm();
      void force_disarm();
      Odometry odometry() const;            // snapshot from atomics
      IOState  state() const;               // atomic load
      bool     gotFirstOdom() const;
  };
  ```

- [ ] **Step 1: Write `px4_backend.hpp`** — declare the structs/enums/class above. Private members (each `std::atomic`, ported verbatim from the FMU): `m_posN,m_posE,m_posD,m_yaw`; setpoint `m_vx,m_vy,m_vz,m_yawsp`; `m_ioState{IOState::STANDBY}`, `m_navState,m_armingState (u8)`, `m_setpointCount (u64)`, `m_handshakeStart (u64)`, `m_gotFirstOdom (bool)`. Non-atomic: `rclcpp::Node* m_node; rclcpp::CallbackGroup::SharedPtr m_cbg;` the three `Publisher::SharedPtr` (traj/mode/cmd), two `Subscription::SharedPtr` (odom/status). **Declare `rclcpp::TimerBase::SharedPtr m_streamTimer;` as the LAST member** (RAII: destroyed first). Private methods: `void streamTick(); void odomCallback(OdomMsgType::ConstSharedPtr); void statusCallback(StatusMsgType::ConstSharedPtr);`. Add `using OdomMsgType = px4_msgs::msg::VehicleOdometry; using StatusMsgType = px4_msgs::msg::VehicleStatus;` and a `nowUs()` helper `m_node->get_clock()->now().nanoseconds()/1000`.

- [ ] **Step 2: Write `px4_backend.cpp` — `start()` / subs / callbacks**

```cpp
void PX4Backend::start() {
    rclcpp::SubscriptionOptions o; o.callback_group = m_cbg;
    m_pubTraj = m_node->create_publisher<OffboardTranslator::TrajectorySetpoint>("/fmu/in/trajectory_setpoint", OffboardTranslator::px4_qos());
    m_pubMode = m_node->create_publisher<OffboardTranslator::OffboardControlMode>("/fmu/in/offboard_control_mode", OffboardTranslator::px4_qos());
    m_pubCmd  = m_node->create_publisher<OffboardTranslator::VehicleCommand>("/fmu/in/vehicle_command", OffboardTranslator::px4_qos());
    m_subOdom = m_node->create_subscription<OdomMsgType>("/fmu/out/vehicle_odometry", rclcpp::SensorDataQoS(),
        std::bind(&PX4Backend::odomCallback, this, std::placeholders::_1), o);
    m_subStatus = m_node->create_subscription<StatusMsgType>("/fmu/out/vehicle_status_v4", rclcpp::SensorDataQoS(),
        std::bind(&PX4Backend::statusCallback, this, std::placeholders::_1), o);
    m_streamTimer = m_node->create_wall_timer(std::chrono::milliseconds{kOffboardPublishPeriodMs},
        std::bind(&PX4Backend::streamTick, this), m_cbg);
}
```
Port `odomCallback` verbatim (store `position[0..2]` into `m_posN/E/D`, extract yaw from `q`, set `m_gotFirstOdom`, and additionally `host_stamp_us` is left for M3 — set it now to `nowUs()` in the snapshot). Port `statusCallback` verbatim (`m_navState`, `m_armingState`). `stop()` = `if (m_streamTimer) m_streamTimer->cancel();`. Destructor calls `stop()`.

- [ ] **Step 3: Write `streamTick()`** — port `offboardPublishLoop` with `IOState` replacing the `m_offboardEngaged` bool:

```cpp
void PX4Backend::streamTick() {
    u64 ts = nowUs();
    Vec3 vel{ m_vx.load(rlx), m_vy.load(rlx), m_vz.load(rlx) };   // FMU streams climb/descent
    f32  yawsp = m_yawsp.load(rlx);
    m_pubMode->publish(OffboardTranslator::mode_velocity(ts));
    m_pubTraj->publish(OffboardTranslator::velocity_setpoint(ts, vel, yawsp));   // NED
    u64 cnt = m_setpointCount.fetch_add(1, rlx) + 1;

    if (m_ioState.load(rlx) == IOState::HANDSHAKING) {
        if (!m_gotFirstOdom.load(rlx)) return;
        if (cnt - m_handshakeStart.load(rlx) < kOffboardWarmupSetpoints) return;
        u8 nav = m_navState.load(rlx), arm = m_armingState.load(rlx);
        if (arm != StatusMsgType::ARMING_STATE_ARMED)       m_pubCmd->publish(OffboardTranslator::arm(ts, true));
        if (nav != StatusMsgType::NAVIGATION_STATE_OFFBOARD) m_pubCmd->publish(OffboardTranslator::set_offboard(ts));
        if (arm == StatusMsgType::ARMING_STATE_ARMED && nav == StatusMsgType::NAVIGATION_STATE_OFFBOARD) {
            m_ioState.store(IOState::FLIGHT, rlx);
            RCLCPP_INFO(m_node->get_logger(), "[PX4_BACKEND_DEBUG] OFFBOARD+ARM confirmed at setpoints=%lu", (unsigned long)cnt);
        }
    }
    RCLCPP_INFO_THROTTLE(m_node->get_logger(), *m_node->get_clock(), 1000,
        "[PX4_BACKEND_DEBUG] io=%d setpoints=%lu nav=%d arm=%d altNED=%.2f velz=%.2f",
        (int)m_ioState.load(rlx), (unsigned long)cnt, (int)m_navState.load(rlx),
        (int)m_armingState.load(rlx), m_posD.load(rlx), vel.z);
}
```
(`rlx` = `std::memory_order_relaxed`. NOTE the handshake no longer keys on `FlightState::TAKEOFF` — the FMU triggers it via `takeoff()`; the warmup/gate logic is otherwise identical to the proven loop. No timeout→FAULT yet; that is spec R2/Task-3 Step and can be added as a bounded `cnt` guard once the happy path is confirmed.)

- [ ] **Step 4: Write the verbs**

```cpp
BackendStatus PX4Backend::takeoff() {
    if (m_ioState.load(rlx) != IOState::STANDBY) return { BackendStatus::Code::REJECTED };
    m_handshakeStart.store(m_setpointCount.load(rlx), rlx);
    m_ioState.store(IOState::HANDSHAKING, rlx);
    return { BackendStatus::Code::PENDING };
}
BackendStatus PX4Backend::land() { return { BackendStatus::Code::OK }; }       // FMU streams descent
void PX4Backend::set_velocity(Vec3 v, f32 y) { m_vx.store(v.x,rlx); m_vy.store(v.y,rlx); m_vz.store(v.z,rlx); m_yawsp.store(y,rlx); }
void PX4Backend::disarm()       { m_pubCmd->publish(OffboardTranslator::arm(nowUs(), false)); m_ioState.store(IOState::STANDBY, rlx); }
void PX4Backend::force_disarm() { m_pubCmd->publish(OffboardTranslator::force_disarm(nowUs())); m_ioState.store(IOState::STANDBY, rlx); }
Odometry PX4Backend::odometry() const {
    return { { m_posN.load(rlx), m_posE.load(rlx), m_posD.load(rlx) }, m_yaw.load(rlx), 0, m_gotFirstOdom.load(rlx) };
}
IOState PX4Backend::state() const { return m_ioState.load(rlx); }
bool PX4Backend::gotFirstOdom() const { return m_gotFirstOdom.load(rlx); }
```

- [ ] **Step 5: Add to CMake** — append the new sources to the `llm_to_action_fmu` target in `source/llm_to_action/CMakeLists.txt` and add `source/llm_to_action` to its include dirs so `px4_backend/…` resolves. (Header-only pieces need only the include path; `px4_backend.cpp` must be listed in the target's sources.)

- [ ] **Step 6: Verify (operator) + commit** — this task does not change runtime behavior yet (FMU not rewired), so verification is **compiles clean**. Hand to operator: "compile `llm_to_action_fmu`; report errors." On green:

```bash
rtk git add source/llm_to_action/px4_backend/px4_backend.hpp source/llm_to_action/px4_backend/px4_backend.cpp source/llm_to_action/CMakeLists.txt
rtk git commit -m "feat(px4_backend): concrete PX4Backend (wire+handshake+stream), NED"
```

---

### Task 3: Rewire the FMU onto `PX4Backend` (structural parity, still NED)

Delete the wire layer from `fmu_node.hpp` and route the flight state machine through the backend. **This is mostly deletion.** Planner-side code (Global Constraints) is untouched. Semantics stay NED so this task proves the *seam* flies before Task 4 touches frame signs.

**Files:**
- Modify: `source/llm_to_action/fmu/fmu_node.hpp`
- Modify: `source/llm_to_action/fmu/fmu_node_base.hpp` (remove the NED constants now living in `px4_backend_base.hpp`; keep loop-rate + `kGoCompletionRadiusM`/`kDefaultGoSpeedCmS`/`kDefaultPromptHistorySize`)
- Delete: `source/llm_to_action/fmu/offboard_translator.hpp`

**Interfaces:**
- Consumes: `PX4Backend`, `BackendStatus`, `IOState`, `Odometry`, `Vec3` from `px4_backend/px4_backend.hpp`.

- [ ] **Step 1: Swap includes + member.** In `fmu_node.hpp` replace `#include "offboard_translator.hpp"` with `#include "px4_backend/px4_backend.hpp"`. Remove the `px4_msgs` includes, the `OdomMsgType`/`StatusMsgType` usings, the three publisher members, two subscription members, `m_offboardTimer`, and every PX4-shared atomic now owned by the backend (`m_posN/E/D`, `m_yaw`, `m_activeVx/y/z`, `m_activeYaw`, `m_navState`, `m_armingState`, `m_offboardEngaged`, `m_setpointCount`, `m_takeoffWarmupStart`, `m_gotFirstOdom`). Add one member: `std::unique_ptr<PX4Backend> m_backend;` (constructed in the ctor after `m_cbGroup`, then `m_backend->start()`). Keep `m_subImg` (camera), `m_controlTimer`, `m_taskQueue`, `m_flightState`, `m_currTask`, `m_hasActive`, `m_chat`, VLM members, and the GO target fields `m_targetN/E/D`, `m_activeSpeed`.

- [ ] **Step 2: Delete `offboardPublishLoop`, `odomCallback`, `statusCallback`, `setActiveVel`** from `fmu_node.hpp` (all now in the backend). Remove their timer/subscription wiring from the ctor.

- [ ] **Step 3: Rewrite `controlLoop()`** to read the backend and stream velocity through it (NED preserved):

```cpp
void controlLoop() {
    Odometry od = m_backend->odometry();
    f32 n = od.pos.x, e = od.pos.y, d = od.pos.z;
    FlightState st = m_flightState.load(rlx);

    if (st == FlightState::TAKEOFF) {
        m_backend->set_velocity({0.0f, 0.0f, kTakeoffClimbVelNed}, 0.0f);   // FMU streams the climb
        if (m_backend->state() == IOState::FAULT) { m_flightState.store(FlightState::STANDBY, rlx); completeCurrent("takeoff_faulted"); return; }
        if (d <= kTakeoffTargetAltNed) { m_flightState.store(FlightState::FLIGHT, rlx); completeCurrent("takeoff_ok"); }
        return;
    }
    if (st == FlightState::LANDING) {
        m_backend->set_velocity({0.0f, 0.0f, kLandDescendVelNed}, 0.0f);    // FMU streams the descent
        if (d >= kGroundContactAltNed) { m_backend->force_disarm(); m_flightState.store(FlightState::STANDBY, rlx); completeCurrent("land_ok"); }
        return;
    }
    if (m_hasActive) {
        if (m_currTask.m_cmd.id() == CommandID::GO) {
            f32 dx=m_targetN-n, dy=m_targetE-e, dz=m_targetD-d, dist=std::sqrt(dx*dx+dy*dy+dz*dz);
            if (dist < kGoCompletionRadiusM) { m_backend->set_velocity({0,0,0},0); completeCurrent("go_ok"); }
            else { f32 sp=m_activeSpeed/dist; m_backend->set_velocity({dx*sp,dy*sp,dz*sp},0); }
        } else { completeCurrent("noop_ok"); }
        return;
    }
    ActiveTask next;
    if (m_taskQueue->try_dequeue(next)) activateTask(next);
}
```

- [ ] **Step 4: Rewrite `activateTask()`** verbs to call the backend; keep GO's `flu_to_ned` math (NED):

```cpp
case CommandID::TAKEOFF: {
    if (m_backend->takeoff().code == BackendStatus::Code::REJECTED) { completeCurrent("takeoff_rejected"); break; }
    m_flightState.store(FlightState::TAKEOFF, rlx);
} break;
case CommandID::LAND:
    m_backend->land(); m_flightState.store(FlightState::LANDING, rlx); break;
case CommandID::GO: {
    CmdGo g = m_currTask.m_cmd.m_extractCmd.m_goto;
    Odometry od = m_backend->odometry();
    Vec3 relFlu{ g.x/100.0f, g.y/100.0f, g.z/100.0f };
    Vec3 relNed = flu_to_ned(relFlu, od.yaw);
    m_targetN = od.pos.x + relNed.x; m_targetE = od.pos.y + relNed.y; m_targetD = od.pos.z + relNed.z;
    m_activeSpeed = (g.speed > 0.0f ? g.speed : kDefaultGoSpeedCmS)/100.0f;
} break;
```
`completeCurrent` loses its `setActiveVel` call → replace with `m_backend->set_velocity({0,0,0}, 0.0f);`.

- [ ] **Step 5: Delete `offboard_translator.hpp`.** Confirm no other file includes it (`rtk grep offboard_translator source/`; expect only the now-removed include).

- [ ] **Step 6: Verify (operator) — the real parity gate.** Hand to operator: "compile `llm_to_action_fmu`, run `scripts/simenv_llm.sh`." Expected `[DIAG]` sequence, functionally identical to baseline `output.txt`: STANDBY→TAKEOFF, first-odom, arm→OFFBOARD confirmed, `altNED` reaches ~-2.0 (no ground-lingering tip), TAKEOFF→FLIGHT `takeoff_ok`, GO activates and `go_ok` within 0.2 m, LAND→`land_ok`, clean disarm. Diff the log; investigate any divergence before committing.

- [ ] **Step 7: Commit**

```bash
rtk git add source/llm_to_action/fmu/fmu_node.hpp source/llm_to_action/fmu/fmu_node_base.hpp
rtk git rm source/llm_to_action/fmu/offboard_translator.hpp
rtk git commit -m "refactor(fmu): drive PX4Backend via verbs; remove inline wire layer (NED parity)"
```

---

### Task 4: Flip the seam to canonical ENU (LAST gate — annotated)

Only after Task 3 flies. Converts the seam so the FMU thinks in ENU (Up+, CCW-from-East) and the backend converts at the wire. Guarded by the numeric direction assert so a sign flip cannot pass silently.

**Files:**
- Modify: `source/llm_to_action/px4_backend/px4_backend.{hpp,cpp}` (odometry→ENU, set_velocity→ENU)
- Modify: `source/llm_to_action/px4_backend/px4_backend_base.hpp` (add ENU constants)
- Modify: `source/llm_to_action/fmu/fmu_node.hpp` (ENU constants + `flu_to_enu`)
- Test: extend `source/llm_to_action/px4_backend/test/frame_convert_test.cpp`

**Interfaces:**
- `Odometry.pos`/`yaw` become ENU. `set_velocity(Vec3 velEnu, f32 yawRateEnu)`.

- [ ] **Step 1: Extend the failing test** — add a GO-direction assert mirroring `activateTask`:

```cpp
// "forward 1m" in ENU must displace the target along the ENU heading.
{ f32 yawEnu = 0.30f; Vec3 rel = flu_to_enu({1.0f,0.0f,0.0f}, yawEnu);
  assert(close(std::atan2(rel.y, rel.x), yawEnu)); }   // heading preserved, +1m forward
```
Run `g++ … && /tmp/fct` → expect PASS already (math added in Task 1); if it fails, the Task-1 `flu_to_enu` is wrong — fix there.

- [ ] **Step 2: Backend → ENU.** In `odomCallback`, store the ENU snapshot: `Vec3 enu = ned_to_enu({pos0,pos1,pos2}); m_posN=enu.x…` and `m_yaw = enu_yaw_from_ned(rawYawNed)`. In `streamTick`, convert on the way out: `m_pubTraj->publish(OffboardTranslator::velocity_setpoint(ts, enu_to_ned(vel), enu_yawrate_to_ned(yawsp)))`. `odometry()` now returns ENU (rename fields mentally; struct unchanged).

- [ ] **Step 3: Add ENU constants** to `px4_backend_base.hpp`: `kTakeoffTargetAltEnu = +2.0f; kTakeoffClimbVelEnu = +2.0f; kLandDescendVelEnu = -0.5f; kGroundContactEnu = 0.1f;`.

- [ ] **Step 4: FMU → ENU.** In `controlLoop`: climb `set_velocity({0,0,kTakeoffClimbVelEnu},0)`, takeoff-done `if (d >= kTakeoffTargetAltEnu)`; descent `kLandDescendVelEnu`, land-done `if (d <= kGroundContactEnu)`. In `activateTask` GO: `Vec3 relEnu = flu_to_enu(relFlu, od.yaw); m_targetN = od.pos.x + relEnu.x…`. Update `[DIAG]` altitude logs to say ENU.

- [ ] **Step 5: Verify (operator) — the ENU gate.** Run `scripts/simenv_llm.sh`. Assert: climb reaches `+2.0` ENU; GO "forward 1 m" moves the drone **along its heading** (compare displacement to `flu_to_enu` prediction, matching the NOTES.md NED-verified direction); clean land + disarm. **⚠ ANNOTATED: needs additional review/testing** — record the direction-assert numbers in `NOTES.md`.

- [ ] **Step 6: Commit**

```bash
rtk git add source/llm_to_action/px4_backend source/llm_to_action/fmu/fmu_node.hpp NOTES.md
rtk git commit -m "feat(px4_backend): canonical ENU seam + direction assert (annotated)"
```

---

## Self-Review

**Spec coverage:** §3 folder layout → Tasks 1–2 (`px4_backend/`, note `drone_backend/` deferred to M2). §4 concrete interface (no CRTP) → Task 2 API block. §5 threading → Global Constraint (reconciled to the *real* Reentrant+atomics model, overriding the spec's idealized single-thread D3 — flagged to user). §6 mission flow → Tasks 3 (NED) + 4 (ENU). §7 frame conversions → Task 1 + Task 4. §8 verification/parity + direction assert → Task 3 Step 6, Task 4 Steps 1/5. §9 DoD → Tasks 1–4 collectively. §10 Future Milestones (M1 concurrency, M2 CRTP, M3 abort) → explicitly NOT in this plan (Non-goals). §11 risks R2 (handshake timeout) → noted as a bounded-`cnt` follow-up in Task 2 Step 3; R3 (teardown) → Task 2 Step 1 (timer last member) + `stop()`.

**Placeholder scan:** No TBD/TODO left as work items. The one "can be added later" (handshake timeout→FAULT) is explicitly deferred with the mechanism named, not a hidden gap. All code steps carry real code.

**Type consistency:** `Vec3` (frame_convert.hpp) used everywhere; `Odometry{pos,yaw,host_stamp_us,valid}`, `BackendStatus::Code{OK,PENDING,REJECTED,FAULT}`, `IOState{STANDBY,HANDSHAKING,FLIGHT,FAULT}` consistent across Tasks 2–4. Verb names (`takeoff/land/set_velocity/disarm/force_disarm/odometry/state/gotFirstOdom`) match between the Task 2 API and the Task 3/4 call sites. `flu_to_ned` (Task 3) vs `flu_to_enu` (Task 4) is an intentional NED→ENU migration, not a naming bug.

**Deviation from spec (surfaced, not silent):** the spec's D3 (single-threaded, no atomics) is overridden by reality — the shipping FMU flies on a `Reentrant` group with atomics, and destabilizing it under a 1-day deadline is the sand we're avoiding. The `Shared<T>`/single-thread design remains recorded in spec §10.M1 for when a real off-executor thread (Tello driver) forces it.
