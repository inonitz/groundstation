# DroneBackend Abstraction — Design Spec

> **Status:** DESIGN / APPROVED-FOR-REVIEW. Phase-2 sub-project **A** of four
> (A: this doc · B: TelloBackend · C: perception/YOLO26 · D: event-driven VLM).
> **Scope of this slice:** the `DroneBackend` seam + `PX4Backend` extraction + FMU
> rewire. **No** TelloBackend, perception, or VLM changes ship here.
> **Target:** C++17, no exceptions, no heap in steady state, PX4 SITL (gz_x500_gimbal).

---

## 0. Why this exists (link to the top-level objective)

`groundstation` is an off-board **"VLM plans, deterministic math executes"** FMU
([ARCHITECTURE.md](../../../ARCHITECTURE.md) §1). Two design goals from that doc drive this slice:

- **Hardware-agnostic** (§1, §7, §8): "Tello primary, PX4 SITL fallback. One generic
  setpoint + one odometry abstraction." Today the FMU is welded to PX4 — it builds
  `px4_msgs`, streams `TrajectorySetpoint`, runs the arm/OFFBOARD handshake inline, and
  thinks natively in **NED**. That blocks the Tello and litters PX4-isms through the planner.
- **Isolation & testability** (skill: brainstorming): the planner/state-machine should be
  understandable and verifiable without knowing how any drone talks on the wire.

This slice extracts everything platform-specific behind a compile-time interface so the FMU
becomes a **pure ENU state machine** that issues verbs. It **supersedes** ARCHITECTURE.md §7's
"dumb translator" wording: the backend is now *thick* (owns the handshake + its own publish
loop). It **resolves FORK-B** (odometry abstraction) and **FORK-C** (offboard collapse) for PX4.

**What this unblocks:** sub-project B (`TelloBackend`) drops into the same CRTP contract; C/D
plug into an FMU that no longer cares what drone is underneath.

---

## 1. Non-goals (YAGNI guard)

- No `TelloBackend` implementation (only its `_base.hpp` I/O contract, as a sibling home for B).
- No perception, VLM, or new command types (`ORBIT`/`SEARCH`/`CURVE` stay as-is).
- No runtime backend selection — **one backend per binary, chosen at compile time**.
- No TF2, no SLAM, no metric depth. Odometry stays the direct source (NED→ENU here).

---

## 2. Decisions locked (with rationale)

| # | Decision | Why (rejected alternative) |
|---|----------|----------------------------|
| D1 | **Thick backend, semantic verbs**: `takeoff/land/set_velocity/disarm/force_disarm` | Tello has native `takeoff`/`land`; forcing streamed-velocity takeoff is the exact fragility we just debugged in SITL. Thin translator rejected. |
| D2 | **Compile-time selection, static polymorphism via CRTP** | One binary per drone ("either/or"). Rejects vtables, `union`+placement-new, `unique_ptr`, and `std::variant`/`visit` (jump-table under the hood). |
| D3 | **Canonical ENU across the seam**; backends convert to platform frame | PX4's NED must not be the "generic" frame. Matches VLM/ROS ENU ([tello_backend_notes.md](../../tello_backend_notes.md)). |
| D4 | **Backend owns its high-rate publish loop** (wall-timer on the *shared* FMU node/executor — one process, one node) | Encapsulates PX4 setpoint-watchdog / Tello `rc`-keepalive at each platform's native rate. Not a separate node/process. |
| D5 | **`std::mutex` + `try_lock`** for composite structs across a thread boundary; **`std::atomic`** for scalar flags | Component-wise `atomic<f32> x,y,z` tears. A fenced seqlock is not human-maintainable (the maintainer is a person). `try_lock` on the ~100 Hz watchdog thread dodges priority inversion / executor starvation — a miss reuses the cached setpoint. |
| D6 | **Status-code POD returns, no exceptions** | C++17 (no `std::expected`); deterministic control flow across the thread boundary. |
| D7 | **Host-clock staleness on odometry** | Hardware clock drifts vs host; a `valid` bool can't express "frozen but present." |

---

## 3. Folder layout

```
source/llm_to_action/
  drone_backend/
    drone_backend.hpp        # canonical types: Vec3, Odometry, BackendStatus, IOState;
                             # Shared<T> (mutex+try_lock); CRTP DroneBackendBase<Derived>; DroneController;
                             # compile-time `using ActiveDroneBackend = ...` (CMake #define)
  px4_backend/
    px4_backend_base.hpp     # PX4 ROS2 I/O contract: topic names, msg usings, QoS,
                             # NED<->ENU conversion, NED constants, msg builders
                             # (absorbs the old offboard_translator.hpp)
    px4_backend.hpp / .cpp   # PX4Backend : DroneBackendBase<PX4Backend>
  tello_backend/
    tello_backend_base.hpp   # Tello I/O contract only (from tello_backend_notes.md).
                             # NOT implemented this slice — sibling home for sub-project B.
  fmu/
    fmu_node.hpp             # owns ONE DroneController; ENU flight state machine + completion
    fmu_node_base.hpp        # loop rates + ENU tuning constants (NED constants removed)
```
`offboard_translator.hpp` is deleted; its logic moves into `px4_backend_base.hpp`.
`OffboardTranslator::Vec3` dies — the canonical `Vec3` lives in `drone_backend/`.

---

## 4. The interface (CRTP contract)

```cpp
// drone_backend/drone_backend.hpp  — canonical, platform-neutral, ENU.
struct Vec3 { f32 x{0}, y{0}, z{0}; };              // ENU world (East, North, Up+)

struct Odometry {
    Vec3 pos;             // ENU position, meters, Up positive
    Vec3 vel;             // ENU velocity, m/s (needed for LAND vz~0 predicate, ARCH §4)
    f32  yaw{0};          // ENU heading, CCW from East (radians)
    u64  host_stamp_us{0};// steady-clock receipt time on the HOST (not the drone clock)
    bool valid{false};    // false until first sample ever received
};

struct BackendStatus {
    enum class Code : u8 { OK, PENDING, TIMEOUT, NOT_READY, REJECTED, STALE_ODOM, FAULT };
    Code code{Code::OK};
};

enum class IOState : u8 { STANDBY, HANDSHAKING, FLIGHT, FAULT };  // backend-owned; std::atomic. LANDING dropped (PX4 land = FMU-streamed descent + force_disarm); FAULT is a STATE, not a separate bool.

// CRTP base: non-virtual forwarders -> Derived::*_impl. Missing impl = compile error.
template <class Derived>
struct DroneBackendBase {
    // lifecycle
    BackendStatus start()  { return d()->start_impl(); }   // create subs/pubs + stream timer
    void          stop()   { d()->stop_impl(); }           // JOIN stream timer BEFORE pub destroy

    // discrete verbs (non-blocking intents; progress observed via state()/engaged())
    BackendStatus takeoff(f32 altEnu) { return d()->takeoff_impl(altEnu); }
    BackendStatus land()              { return d()->land_impl(); }
    BackendStatus disarm()            { return d()->disarm_impl(); }
    BackendStatus force_disarm()      { return d()->force_disarm_impl(); }

    // continuous. ENU velocity + yaw-rate. Stored under a mutex; the stream timer
    // publishes it at the native rate. ALWAYS accepted (FMU streams climb/descent too).
    BackendStatus set_velocity(Vec3 velEnu, f32 yawRate) { return d()->set_velocity_impl(velEnu, yawRate); }

    // telemetry (pull) + observable state
    Odometry odometry() { return d()->odometry_impl(); }   // mutex try_load; cached on a miss
    IOState  state()    { return d()->state_impl(); }
    bool     engaged()  { return d()->state_impl() == IOState::FLIGHT; }

private:
    Derived* d() { return static_cast<Derived*>(this); }
};
```

**Selection** (`drone_backend.hpp`, tail):
```cpp
#if   defined(DRONE_BACKEND_PX4)
  #include "px4_backend/px4_backend.hpp"
  using ActiveDroneBackend = PX4Backend;
#elif defined(DRONE_BACKEND_TELLO)
  #include "tello_backend/tello_backend.hpp"
  using ActiveDroneBackend = TelloBackend;
#else
  #error "Set -DDRONE_BACKEND=px4|tello in CMake"   // fail loudly (review item #8)
#endif
```

`DroneController` — the single seam the FMU holds; owns lifetime + teardown order:
```cpp
class DroneController {
public:
    explicit DroneController(rclcpp::Node* node) : m_backend(node) {}
    ~DroneController() { m_backend.stop(); }        // stop() joins timer before pubs die (#7)
    ActiveDroneBackend& backend() { return m_backend; }
private:
    ActiveDroneBackend m_backend;                   // concrete, compile-time. No dispatch.
};

> **Teardown (review #7, RAII):** declare each backend's `rclcpp::TimerBase` (the stream timer)
> as the **last** member. Reverse-order destruction stops it ticking before the publishers /
> subscriptions / `Shared` mutexes it touches are torn down — no publish-after-free on Ctrl-C.
> `stop()` is an explicit early-out; member order is the guarantee.
```

---

## 5. Thread-boundary data — `std::mutex` + `try_lock` (NOT a seqlock)

Reassessed for **human maintainability** (the maintainer is a person, not an AI). Scalars that
cross threads are `std::atomic` (`IOState`, `m_gotFirstOdom`). **Composite** structs — the
setpoint (`Vec3` vel + yaw) and the `Odometry` snapshot — use a tiny mutex wrapper.

**One rule:** *writers `lock()`; readers `try_lock()` and fall back to their cached copy.* The
low-rate writer blocking briefly is fine; the ~100 Hz watchdog reader must **never** block — a
blocked lock there is priority inversion → ROS executor starvation → lost telemetry.

```cpp
template <class T> class Shared {              // T: trivially copyable POD
    mutable std::mutex m_mtx;
    T                  m_val{};
public:
    void store(const T& v) {                                   // writer (low-rate): may block
        std::lock_guard<std::mutex> lk(m_mtx); m_val = v;
    }
    bool try_load(T& out) const {                              // reader (high-rate): never blocks
        std::unique_lock<std::mutex> lk(m_mtx, std::try_to_lock);
        if (!lk.owns_lock()) return false;                     // contended -> keep cached copy
        out = m_val; return true;
    }
};
```
The reader keeps a private `T m_cached{}` (seeded to zero) touched only by its own thread:
`if (s.try_load(tmp)) m_cached = tmp;` then use `m_cached`. Uncontended ~25 ns (0.00025 % of a
100 Hz budget). No fences, no `cpu_relax`, readable at 2 AM. **Replaces the earlier seqlock.**

---

## 6. Threading model (one process, one node, one executor)

```
                          rclcpp::MultiThreadedExecutor (Reentrant cbgroup)
   ┌───────────────────────────────────────────────────────────────────────┐
   │  FMU control timer (20 Hz)          PX4Backend stream timer (~100 Hz)   │
   │  ───────────────────────           ──────────────────────────────      │
   │  reads m_odom  ─────────────────► (backend odom cb writes m_odom)   │
   │  runs flight SM                                                         │
   │  writes m_setpoint ─────────────► reads m_setpoint, publishes wire  │
   │  calls verbs ─────────────────────► mutates IOState, runs handshake     │
   └───────────────────────────────────────────────────────────────────────┘
```
The backend registers **its own** wall-timer + pubs/subs on the FMU's `rclcpp::Node`. No
second node, no second process — shared memory, ROS handles the executor threads.

---

## 7. How it actually runs — full canned mission (the async, made concrete)

Two timers, two mutex-guarded structs, one status contract. Below is the *entire* takeoff→go→land cycle.

### 7a. FMU control loop — 20 Hz (planner side; pure ENU; never touches the wire)
```
controlLoop():                                   # every 50 ms
    odom = ctrl.backend().odometry()             # mutex try_load + cached fallback (no tearing)

    # --- odom-loss failsafe: ONE trigger -> ONE verb -> ONE outcome -----------
    # m_lastGoodOdomUs is refreshed in odomCallback on every VALID frame;
    # m_haveHadFirstOdom latches after the first valid frame so startup
    # (stamp==0) cannot trip us. host_now_us() is CLOCK_MONOTONIC, so the
    # unsigned delta can never underflow on a wall-clock step. Threshold is
    # PER-BACKEND: kOdomStaleUs = kOdomExpectedPeriodUs * kOdomStaleFrames
    # (PX4 ~30-50Hz, Tello ~10Hz -> sized off ODOM rate, not control rate).
    if m_haveHadFirstOdom and (host_now_us() - m_lastGoodOdomUs) > kOdomStaleUs:
        abort()          # the single failsafe path; contract in the Failsafe section
        return

    st = m_flightState
    switch st:
      STANDBY:
        if dequeue(task): activateTask(task)     # TAKEOFF task -> case below
      TAKEOFF:
        ctrl.backend().set_velocity(climbEnu, 0)   # FMU streams the climb; backend relays it
        if ctrl.backend().state() == FAULT:      # handshake TIMEOUT etc.
            abort("takeoff faulted"); return
        if odom.pos.z >= kTakeoffTargetAltEnu:   # ENU Up+, e.g. +2.0
            m_flightState = FLIGHT; completeCurrent("takeoff_ok")
      FLIGHT:
        if hasActive and id == GO:
            d   = targetEnu - odom.pos            # vector to waypoint (ENU)
            if |d| < kGoRadius: 
                ctrl.backend().set_velocity({0,0,0}, 0); completeCurrent("go_ok")
            else:
                ctrl.backend().set_velocity(normalize(d) * speed, 0)   # writes m_setpoint
        elif dequeue(task): activateTask(task)   # LAND task -> case below
        else: ctrl.backend().set_velocity({0,0,0}, 0)                  # hover
      LANDING:
        ctrl.backend().set_velocity(descendEnu, 0)                    # FMU streams the descent
        if odom.pos.z <= kGroundContactEnu and |odom.vel.z| < eps:       # ~0 and settled
            ctrl.backend().force_disarm(); m_flightState = STANDBY; completeCurrent("land_ok")

activateTask(task):                              # verb dispatch (FMU sequences, backend executes)
    switch task.id:
      TAKEOFF: 
        s = ctrl.backend().takeoff(kTakeoffTargetAltEnu)   # non-blocking; backend goes HANDSHAKING
        if s.code == REJECTED: abort(...) 
        m_flightState = TAKEOFF   # FMU streams climb each tick (TAKEOFF case above)
      GO:      targetEnu = odom.pos + flu_to_enu(relFlu, odom.yaw); m_flightState stays FLIGHT
      LAND:    ctrl.backend().land(); m_flightState = LANDING   # PX4 land()=no-op; FMU streams descent
```

### 7b. PX4Backend stream timer — ~100 Hz (wire side; the only thing that publishes)
```
streamTick():                                    # every ~10 ms, backend-owned; the ONLY publisher
    pubMode.publish( OffboardControlMode{velocity=true} )   # watchdog: EVERY tick
    if m_setpoint.try_load(tmp): m_cachedSetpoint = tmp           # never blocks; else reuse cache

    switch m_ioState.load():                          # atomic scalar; backend's OWN 4-state SM
      STANDBY:                                   # FMU keeps m_cachedSetpoint ~0 here
        pubTraj.publish( velNed = enu_to_ned(m_cachedSetpoint.vel) )
      HANDSHAKING:
        pubTraj.publish( velNed = enu_to_ned(m_cachedSetpoint.vel) )  # stream FMU's climb (pre-offboard OK)
        if not m_gotFirstOdom: break                            # gate on estimator (prior fix)
        if armState != ARMED:    pubCmd.publish(arm(true))      # arm FIRST
        if navState != OFFBOARD: pubCmd.publish(set_offboard()) # then OFFBOARD (retry each tick)
        if armState==ARMED and navState==OFFBOARD: m_ioState = FLIGHT              # engaged()
        elif now_us() - m_handshakeStart > kHandshakeTimeoutUs: m_ioState = FAULT  # bounded (review #2)
      FLIGHT:
        pubTraj.publish( velNed = enu_to_ned(m_cachedSetpoint.vel), yawspeed = -m_cachedSetpoint.yawRate )
      FAULT:
        pubTraj.publish( velNed = 0 )            # hold; FMU observes state()==FAULT and aborts

# verbs just set the atomic state / shared setpoint (non-blocking); the tick does the work:
takeoff_impl(alt):      if m_ioState != STANDBY: return REJECTED;
                        m_handshakeStart = now_us(); m_ioState = HANDSHAKING; return PENDING
set_velocity_impl(v,y): m_setpoint.store({v,y}); return OK           # always accepted
land_impl():            return OK                                    # PX4: no-op; FMU streams descent
disarm_impl():          pubCmd.publish(disarm());       m_ioState = STANDBY; return OK
force_disarm_impl():    pubCmd.publish(force_disarm()); m_ioState = STANDBY; return OK

# odom subscription callback (whatever rate PX4 publishes):
odomCallback(msg):                               # msg is NED
    o.pos = ned_to_enu(msg.position)             # (E,N,U) = (msg.y, msg.x, -msg.z)
    o.vel = ned_to_enu(msg.velocity)             # same swap+negate-z
    o.yaw = pi/2 - yaw_from_quat(msg.q)          # NED CW-from-N -> ENU CCW-from-E (wrap)
    o.host_stamp_us = host_now_us()              # HOST steady clock (review #3)
    o.valid = true
    m_gotFirstOdom = true
    m_odom.store(o)
```

### 7c. Timeline (what a human sees in the logs)
```
t0    FMU STANDBY, backend STANDBY. stream timer already publishing zero-vel (watchdog primed).
t0    dequeue TAKEOFF -> takeoff(+2.0) -> backend STANDBY->HANDSHAKING, FMU->TAKEOFF.
t0..  streamTick streams climb setpoint; waits for first odom; then arm -> set_offboard, retry.
tA    armed+OFFBOARD confirmed -> IOState FLIGHT (engaged). [bounded: FAULT if > timeout]
tA..  climb continues; control loop watches odom.pos.z.
tB    odom.pos.z >= +2.0 -> FMU TAKEOFF->FLIGHT, completeCurrent("takeoff_ok").
tB    dequeue GO -> targetEnu = pos + flu_to_enu(forward 1m, yaw).
tB..  each 20 Hz tick: set_velocity(dir*speed) -> shared setpoint -> 100 Hz tick converts ENU->NED, streams.
tC    |target-pos| < 0.2 -> set_velocity(0); completeCurrent("go_ok").
tC    dequeue LAND -> land() [PX4 no-op] -> FMU->LANDING; FMU streams descent.
tD    odom.pos.z ~ 0 and settled -> force_disarm() -> STANDBY. Mission complete.
```
The asynchrony is bounded and legible: **the FMU only ever writes a setpoint and reads an
odometry snapshot + a state enum; the backend only ever reads that setpoint and drives the
wire.** No shared mutable state beyond the two mutex-guarded structs and the atomic `IOState`.

---

## 8. Frame conversions (single source of truth: `px4_backend_base.hpp`)

| Quantity | ENU (canonical) | NED (PX4 wire) | Conversion |
|----------|-----------------|----------------|------------|
| position | (E, N, U) | (N, E, D) | `ned = (enu.y, enu.x, -enu.z)` |
| velocity | (vE, vN, vU) | (vN, vE, vD) | same swap+negate-z |
| yaw | CCW from East | CW from North | `yaw_ned = π/2 − yaw_enu` (wrap to −π..π) |
| yaw-rate | CCW+ | CW+ | negate |

VLM body-relative commands stay **FLU**; the FMU converts **FLU→ENU** with `odom.yaw`
(`flu_to_enu`, replacing the old `flu_to_ned`). Every `*Ned` tuning constant moves into
`px4_backend_base.hpp`; the FMU keeps only ENU constants
(`kTakeoffTargetAltEnu = +2.0`, `kGoRadius`, etc.).

---

## 9. Verification (parity against known-good, review item #6)

The PX4-backend binary must fly the canned smoke test **functionally identically** to the
current commit. Beyond "full cycle completed," the parity check **numerically asserts frame
correctness** (a NED→ENU sign flip crashes silently past a "it flew" check):

1. Full cycle: STANDBY→TAKEOFF→FLIGHT(GO)→LANDING→STANDBY, `engaged` confirmed, clean disarm.
2. **Direction:** for "forward 1 m" at spawn yaw, assert the GO displacement vector points
   along the heading (ENU), matching the NED-verified result we recorded in NOTES.md.
3. Takeoff profile: climb reaches +2.0 m ENU without the pre-fix ground-lingering tip.
4. Handshake timeout path exercised (e.g., delay/deny arming) → backend FAULT → FMU abort,
   no infinite TAKEOFF hang.

User compiles/runs (per workflow); I diff the new DIAG log against the baseline.

---

## 10. Risks & open items

- **R1 — ENU migration sign errors.** Highest risk; §9.2 direction assert is the guard.
- **R2 — try_lock staleness.** Under (near-impossible) sustained contention the reader keeps its cached setpoint; bounded by the writer's ~ns hold. Seed the cache to zero so pre-first-setpoint ticks hover.
- **R3 — Handshake timeout value.** `kHandshakeTimeoutUs` needs a sane default (~5 s) tuned in sim; too tight = false aborts on slow EKF, too loose = long hang.
- **R4 — Stale-odom threshold.** `kOdomStaleUs` vs PX4's actual odom rate; must not false-trip.
- **R5 — Destruction order.** Stream timer declared LAST in each backend (reverse-order destruction stops it before pubs/mutexes); `DroneController::stop()` is the explicit early-out. Verify no publish-after-free on Ctrl-C.
- **R6 — CRTP contract drift (future).** When `TelloBackend` lands (B), the compile-time forwarders enforce the shape, but semantic conformance (e.g., `takeoff` completion meaning) is on the author — documented here, not compiler-checked.

---

## 11. Definition of done (this slice)

- [ ] `drone_backend/`, `px4_backend/`, `tello_backend/` created; `offboard_translator.hpp` removed.
- [ ] `DroneBackendBase<Derived>`, `Shared<T>` (mutex+try_lock), `DroneController`, canonical types defined.
- [ ] `PX4Backend` implements all `_impl`; absorbs handshake + stream loop + odom/status subs (incl. `_v4`) + NED↔ENU.
- [ ] FMU holds one `DroneController`, is pure-ENU, has no `px4_msgs`/`OffboardTranslator` include, no inline handshake.
- [ ] CMake `-DDRONE_BACKEND=px4` selects; unset → hard `#error`.
- [ ] Smoke test passes §9 parity incl. numeric direction assert + handshake-timeout path.

---

## 12. Delivery sequence (deadline: PX4 SITL proven tomorrow; Tello ≤ 3 days)

Priority is **SITL first** — it's cheap to test and verify. ENU stays in the design (D3),
but its frame-conversion *correctness* is the **last review gate**, deliberately isolated so
the structural extraction can be proven flying before we scrutinize sign conventions. The
ENU-conversion module and (Phase B) Tello code are explicitly allowed to ship
**"good-enough + annotated for follow-up review/testing"** — they do **not** block the SITL proof.

**Day 1 (tomorrow) — bite-sized units, each ≤ ~200 LOC, reviewed in order (one before the next):**

1. **U1** `drone_backend/drone_backend.hpp` — frame-neutral contract: types, `Shared<T>` (mutex+try_lock), CRTP base, `DroneController`, `-D` selection.
2. **U2** `px4_backend/px4_backend_base.hpp` — topics / QoS / msg-usings / builders / constants (NED-native builders).
3. **U3** `px4_backend/px4_backend.{hpp,cpp}` — class: subs/pubs/timer, IOState handshake + timeout, stream tick, odom callback. (split decl/impl)
4. **U4** `fmu/fmu_node.hpp` — verb rewire; strip `px4_msgs`/`OffboardTranslator`; ENU constants. (mostly deletion)
5. **U5 — ENU REVIEW GATE (LAST):** the NED↔ENU + FLU→ENU conversion module + the SITL **numeric direction assert** (§9.2). Proven in sim before sign-off. **⚠ ANNOTATED: needs additional review/testing.**

**Verification order mirrors the review order:** first get the full cycle flying (structural
parity — "it still flies through the seam"), *then* gate on §9.2's numeric direction assert for
ENU correctness. A structural regression and a frame-sign bug are thus diagnosed separately.

**Day 2–3:** `TelloBackend` (sub-project B) — bench then flight. **⚠ ANNOTATED: needs additional
review/testing**; imperfect-but-noted is acceptable per deadline.

**Deferred past deadline:** perception (C), event-driven VLM (D).


## Failsafe contract (single path)  <!-- finalized -->

There is exactly ONE failsafe entry point: `DroneController::abort()`. The FMU
never decides *how* to get the vehicle down; it declares the emergency once and
delegates the descent to the backend, which uses the platform's OWN onboard
controller (odom-independent by construction).

`abort()` (FMU-side, backend-agnostic):
1. `store()` a descent setpoint into the shared setpoint so the stream thread
   stops relaying the last cruise velocity.
2. call `m_backend.abort_impl()`.
3. transition `IOState -> FAULT` (latched; no auto-recovery even if odom returns).

`abort_impl()` contract (each backend MUST satisfy):
> Bring the vehicle to a non-flying state WITHOUT reading FMU odometry.

  * PX4Backend  -> `VEHICLE_CMD_NAV_LAND`; PX4's onboard estimator/land logic
    performs the blind descent. FMU odom staleness is irrelevant to it.
  * TelloBackend -> native `land`; Tello descends on its own onboard sensors.

Invariant (pin in code): `host_now_us()` uses `CLOCK_MONOTONIC`, and
`host_stamp_us` is written ONLY at the odom receipt site in `odomCallback`
(never from the vehicle clock). Debug `assert(stamp <= now)` at that one site.

## Parity test — odom-loss failsafe  <!-- annotated per review -->

Run the identical mission against both backends; mid-flight, kill the odom
publisher and assert a controlled descent-to-non-flying:

1. takeoff -> confirm FLIGHT.
2. begin a GO setpoint (vehicle moving).
3. externally stop the odom source (SITL: kill the odom bridge; Tello: drop
   state UDP).
4. assert within kOdomStaleUs + margin: `IOState == FAULT`, shared setpoint is a
   descent (not the prior cruise velocity), and the vehicle reaches a non-flying
   state (PX4 disarms after land; Tello lands).
5. assert NO dependency on post-blackout odom (feed frozen/garbage odom after the
   cut and confirm the outcome is unchanged).

This unit ("odom-loss failsafe") is built and reviewed as its own bite-sized
unit, with the above as its acceptance test — not scattered across the control
loop.
