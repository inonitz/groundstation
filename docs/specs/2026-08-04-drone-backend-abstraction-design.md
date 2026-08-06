# DroneBackend Abstraction — Design Spec

> **Status:** DESIGN / APPROVED-FOR-REVIEW. Phase-2 sub-project **A** of four
> (A: this doc · B: TelloBackend · C: perception/YOLO26 · D: event-driven VLM).
> **Scope of this slice:** extract a concrete `PX4Backend` seam + rewire the FMU to
> drive it through semantic verbs. **No** TelloBackend, perception, or VLM changes ship here.
> **Target:** C++17, no exceptions, PX4 SITL (gz_x500_gimbal).
>
> **Guiding principle (KISS/YAGNI):** the Day-1 core is the *smallest thing that flies
> tomorrow through a clean seam*. Every heavier mechanism we reasoned through — CRTP,
> a cross-thread concurrency primitive, a mid-flight odom-loss failsafe — is preserved,
> with its rationale, in **§10 Future Milestones**, each gated on the concrete trigger
> that makes it necessary. We harden when a real second consumer/thread/failure forces it,
> not a day early.

---

## 0. Why this exists (link to the top-level objective)

`groundstation` is an off-board **"VLM plans, deterministic math executes"** FMU
([ARCHITECTURE.md](../ARCHITECTURE.md) §1). Two goals from that doc drive this slice:

- **Hardware-agnostic** (§1, §7, §8): "Tello primary, PX4 SITL fallback. One generic
  setpoint + one odometry abstraction." Today the FMU is welded to PX4 — it streams
  `TrajectorySetpoint`, runs the arm/OFFBOARD handshake inline, and thinks in **NED**.
  That blocks the Tello and litters PX4-isms through the planner.
- **Isolation & testability**: the planner/state-machine should be understandable and
  verifiable without knowing how any drone talks on the wire.

This slice puts everything platform-specific behind **one concrete class, `PX4Backend`**,
exposing **semantic verbs**, so the FMU becomes a pure ENU state machine. It supersedes
ARCHITECTURE.md §7's "dumb translator": the backend is *thick* (owns the handshake + its own
publish loop). It resolves FORK-B (odometry) and FORK-C (offboard collapse) for PX4.

**What this unblocks:** when `TelloBackend` arrives (B), we will have **two real
implementations** to extract a shared interface from — see §10.M2. C/D then plug into an FMU
that no longer cares what drone is underneath.

---

## 1. Non-goals (YAGNI guard)

- **No abstraction machinery yet.** One concrete `PX4Backend`. No CRTP, no base class, no
  compile-time backend selection — there is exactly one backend today (see §10.M2 for when).
- **No cross-thread concurrency primitive.** The FMU runs on a **single-threaded executor**;
  all callbacks are serialized, so plain members need no mutex/atomics (see §10.M1).
- **No mid-flight odom-loss failsafe.** The known-good reference has none and flies; it is
  real-hardware hardening, not a tomorrow blocker (see §10.M3 — full contract preserved).
- No `TelloBackend`, perception, VLM, or new command types. No TF2/SLAM/metric depth.

---

## 2. Decisions locked (Day-1 core)

| # | Decision | Why |
|---|----------|-----|
| D1 | **Thick backend, semantic verbs**: `takeoff/land/set_velocity/disarm/force_disarm` | Tello has native `takeoff`/`land`; forcing streamed-velocity takeoff is the exact fragility we just debugged in SITL. Thin translator rejected. |
| D2 | **One concrete `PX4Backend` class** (no polymorphism) | With a single backend there is nothing to dispatch. Direct calls, zero indirection. Extract an interface later, from *two* real backends (§10.M2). |
| D3 | **Single-threaded `rclcpp` executor; plain member state** | Control timer, stream timer, and odom sub all run on one thread, serialized by the executor — no data races, so no mutex/atomics. Matches the known-good `speech_to_action` node. |
| D4 | **Backend owns its high-rate publish loop** (wall-timer on the *shared* FMU node) | Encapsulates the PX4 setpoint-watchdog at its native rate. One process, one node, one executor — not a separate node/process. |
| D5 | **Canonical ENU across the seam**; backend converts NED↔ENU | PX4's NED must not be the "generic" frame. Matches VLM/ROS ENU. *(User-directed: do ENU now; its sign-correctness is the LAST review gate, §8/§9 — isolated so structural extraction is proven flying first. NED-native is the fallback if ENU signs bite.)* |
| D6 | **Status-code POD returns, no exceptions** | C++17, deterministic control flow. Start **minimal** (`OK/PENDING/REJECTED/FAULT`); add a code only when a caller actually branches on it. |

---

## 3. Folder layout

```
source/llm_to_action/
  px4_backend/
    px4_backend_base.hpp     # PX4 ROS2 I/O contract: topic names, msg usings, QoS,
                             # NED<->ENU conversion, NED constants, msg builders
                             # (absorbs the old offboard_translator.hpp)
    px4_backend.hpp / .cpp   # class PX4Backend  (concrete; canonical types live here for now)
  fmu/
    fmu_node.hpp             # owns ONE PX4Backend; ENU flight state machine + completion
    fmu_node_base.hpp        # loop rates + ENU tuning constants (NED constants removed)
```
`offboard_translator.hpp` is deleted; its logic moves into `px4_backend_base.hpp`.
The canonical `Vec3`/`Odometry`/`BackendStatus`/`IOState` types live in `px4_backend.hpp`
for now; **when M2 introduces a second backend they move up into a `drone_backend/` folder**
(the future home noted in §10.M2). Keeping them local today avoids a folder that holds one file.

---

## 4. The interface (concrete — no CRTP yet)

```cpp
// px4_backend/px4_backend.hpp  — canonical, platform-neutral, ENU.
struct Vec3 { f32 x{0}, y{0}, z{0}; };               // ENU world (East, North, Up+)

struct Odometry {
    Vec3 pos;             // ENU position, meters, Up positive
    Vec3 vel;             // ENU velocity, m/s (LAND vz~0 predicate, ARCH §4)
    f32  yaw{0};          // ENU heading, CCW from East (radians)
    u64  host_stamp_us{0};// steady-clock receipt time on the HOST (kept now; consumed in §10.M3)
    bool valid{false};    // false until first sample ever received
};

struct BackendStatus {                               // minimal set; grow on demand (D6)
    enum class Code : u8 { OK, PENDING, REJECTED, FAULT };
    Code code{Code::OK};
};

enum class IOState : u8 { STANDBY, HANDSHAKING, FLIGHT, FAULT };  // the handshake genuinely needs these 4

// Concrete class. Plain methods, direct calls, no vtable, no template.
class PX4Backend {
public:
    explicit PX4Backend(rclcpp::Node* node);
    ~PX4Backend();                                   // stops stream timer first (RAII, see note)

    BackendStatus start();                           // create subs/pubs + stream timer
    void          stop();                            // explicit early-out (dtor also handles it)

    // discrete verbs (non-blocking intents; progress observed via state()/engaged())
    BackendStatus takeoff(f32 altEnu);
    BackendStatus land();
    BackendStatus disarm();
    BackendStatus force_disarm();

    // continuous: ENU velocity + yaw-rate. Stored in a plain member; the stream
    // timer publishes it at the native rate. ALWAYS accepted (FMU streams climb/descent too).
    BackendStatus set_velocity(Vec3 velEnu, f32 yawRate);

    // telemetry (pull) + observable state
    Odometry odometry() const;                       // returns a copy of the plain member
    IOState  state()    const;
    bool     engaged()  const { return state() == IOState::FLIGHT; }

private:
    rclcpp::Node* m_node;
    // subs/pubs, plain members: m_odom, m_setpoint, m_ioState, m_handshakeStart, m_gotFirstOdom
    // (no guards — single-threaded executor serializes every access, D3)
    rclcpp::TimerBase::SharedPtr m_streamTimer;      // LAST member -> destroyed first (see note)
};
```

> **Teardown (RAII):** declare the `m_streamTimer` as the **last** member. Reverse-order
> destruction stops it ticking before the publishers/subscriptions it touches are torn down —
> no publish-after-free on Ctrl-C. `stop()` is an explicit early-out; member order is the guarantee.

The FMU holds it directly: `PX4Backend m_backend;`. No wrapper, no selection macro — those
arrive with the second backend (§10.M2).

---

## 5. Threading model (one process, one node, ONE thread)

```
              rclcpp::SingleThreadedExecutor  (all callbacks serialized on one thread)
   +--------------------------------------------------------------------------+
   |  odom sub cb        FMU control timer (20 Hz)     PX4 stream timer (~30 Hz)|
   |  writes m_odom      reads m_odom, runs SM,         reads m_setpoint+m_ioState|
   |                     writes m_setpoint, calls verbs  publishes wire, handshake|
   +--------------------------------------------------------------------------+
```
Because one executor thread runs everything one-at-a-time, `m_odom` / `m_setpoint` /
`m_ioState` are **ordinary members** — no mutex, no atomics, no tearing. This is why the KISS
core has *zero* concurrency primitives. (If a future need forces a background thread or a
multi-threaded executor, §10.M1 has the fully-reasoned `Shared<T>` design ready to drop in.)

---

## 6. How it actually runs — full canned mission (concrete)

### 6a. FMU control loop — 20 Hz (planner side; pure ENU; never touches the wire)
```
controlLoop():                                   # every 50 ms
    odom = m_backend.odometry()                  # plain member copy (single thread; no guard)
    switch m_flightState:
      STANDBY:
        if dequeue(task): activateTask(task)     # TAKEOFF task -> case below
      TAKEOFF:
        m_backend.set_velocity(climbEnu, 0)      # FMU streams the climb; backend relays it
        if m_backend.state() == FAULT:           # handshake timed out
            m_flightState = STANDBY; completeCurrent("takeoff_faulted"); return
        if odom.pos.z >= kTakeoffTargetAltEnu:   # ENU Up+, e.g. +2.0
            m_flightState = FLIGHT; completeCurrent("takeoff_ok")
      FLIGHT:
        if hasActive and id == GO:
            toTarget = targetEnu - odom.pos
            if |toTarget| < kGoRadius:
                m_backend.set_velocity({0,0,0}, 0); completeCurrent("go_ok")
            else:
                m_backend.set_velocity(normalize(toTarget) * speed, 0)
        elif dequeue(task): activateTask(task)   # LAND task -> case below
        else: m_backend.set_velocity({0,0,0}, 0) # hover
      LANDING:
        m_backend.set_velocity(descendEnu, 0)    # FMU streams the descent
        if odom.pos.z <= kGroundContactEnu and |odom.vel.z| < eps:
            m_backend.force_disarm(); m_flightState = STANDBY; completeCurrent("land_ok")

activateTask(task):
    switch task.id:
      TAKEOFF:
        auto beginTakeoffHandshake = [&]{ return m_backend.takeoff(kTakeoffTargetAltEnu); };
        if beginTakeoffHandshake().code == REJECTED: completeCurrent("takeoff_rejected"); return
        m_flightState = TAKEOFF                  # FMU streams the climb each tick (case above)
      GO:   targetEnu = odom.pos + flu_to_enu(relFlu, odom.yaw)   # stays FLIGHT
      LAND: m_backend.land(); m_flightState = LANDING             # PX4 land()=no-op; FMU streams descent
```
*(Verb dispatch stays this flat: one named helper per verb, each returning a `BackendStatus`
we log/branch on. If a verb ever grows past a couple of lines it gets a verbosely-named lambda,
as `beginTakeoffHandshake` above, so intent reads off the call site.)*

### 6b. PX4Backend stream timer — ~30 Hz (wire side; the only thing that publishes)
```
streamTick():                                    # backend-owned; the ONLY publisher
    pubMode.publish( OffboardControlMode{velocity=true} )        # watchdog: EVERY tick
    Vec3 vel = m_setpoint.vel                                    # plain member read
    switch m_ioState:                                            # backend's OWN 4-state SM
      STANDBY:
        pubTraj.publish( velNed = enu_to_ned(vel) )             # FMU keeps vel ~0 here
      HANDSHAKING:
        pubTraj.publish( velNed = enu_to_ned(vel) )             # stream FMU's climb (pre-offboard OK)
        if not m_gotFirstOdom: return                            # gate on estimator (prior fix)
        if armState != ARMED:    pubCmd.publish(arm(true))       # arm FIRST
        if navState != OFFBOARD: pubCmd.publish(set_offboard())  # then OFFBOARD (retry each tick)
        if armState==ARMED and navState==OFFBOARD:      m_ioState = FLIGHT
        elif now_us() - m_handshakeStart > kHandshakeTimeoutUs:  m_ioState = FAULT   # bounded
      FLIGHT:
        pubTraj.publish( velNed = enu_to_ned(vel), yawspeedNed = enu_yawrate_to_ned(m_setpoint.yawRate) )
      FAULT:
        pubTraj.publish( velNed = 0 )                           # hold; FMU sees state()==FAULT

# verbs set state / setpoint (non-blocking); the tick does the work:
takeoff(alt):        if m_ioState != STANDBY: return REJECTED;
                     m_handshakeStart = now_us(); m_ioState = HANDSHAKING; return PENDING
set_velocity(v,y):   m_setpoint = {v,y}; return OK              # always accepted
land():              return OK                                  # PX4: no-op; FMU streams descent
disarm():            pubCmd.publish(disarm());       m_ioState = STANDBY; return OK
force_disarm():      pubCmd.publish(force_disarm()); m_ioState = STANDBY; return OK

odomCallback(msg):                               # msg is NED
    m_odom.pos = ned_to_enu(msg.position)        # (E,N,U) = (msg.y, msg.x, -msg.z)
    m_odom.vel = ned_to_enu(msg.velocity)        # same swap+negate-z
    m_odom.yaw = enu_yaw_from_ned_quat(msg.q)    # NED CW-from-N -> ENU CCW-from-E (named, self-documenting)
    m_odom.host_stamp_us = host_now_us()         # CLOCK_MONOTONIC, host clock (consumed in §10.M3)
    m_odom.valid = true; m_gotFirstOdom = true
```

### 6c. Timeline (what a human sees in the logs — one event per line, tagged by source)
```
t0  [FMU_NODE_DEBUG]        STANDBY; dequeued TAKEOFF -> takeoff(+2.0).
t0  [FMU_NODE_DEBUG]        flight state STANDBY -> TAKEOFF.
t0  [PX4_BACKEND_DEBUG]     IOState STANDBY -> HANDSHAKING; stream timer priming zero-vel watchdog.
t0+ [PX4_BACKEND_DEBUG]     streaming climb setpoint; waiting for first odom.
t0+ [PX4_BACKEND_DEBUG]     first odom rx -> arm requested -> OFFBOARD requested (retrying).
tA  [PX4_BACKEND_DEBUG]     armed + OFFBOARD confirmed; IOState HANDSHAKING -> FLIGHT (engaged).
tA+ [FMU_NODE_DIAGNOSTICS]  climbing; odom.pos.z tracking toward +2.0.
tB  [FMU_NODE_DEBUG]        odom.pos.z >= +2.0; flight state TAKEOFF -> FLIGHT; completeCurrent("takeoff_ok").
tB  [FMU_NODE_DEBUG]        dequeued GO; targetEnu = pos + flu_to_enu(forward 1m, yaw).
tB+ [FMU_NODE_DIAGNOSTICS]  each 20Hz tick: set_velocity(dir*speed); 30Hz tick converts ENU->NED, streams.
tC  [FMU_NODE_DEBUG]        |target-pos| < 0.2; set_velocity(0); completeCurrent("go_ok").
tC  [FMU_NODE_DEBUG]        dequeued LAND; land() [PX4 no-op]; flight state FLIGHT -> LANDING.
tD  [FMU_NODE_DEBUG]        odom.pos.z ~ 0 and settled; force_disarm(); LANDING -> STANDBY. Mission complete.
```
The asynchrony is bounded and legible: **the FMU only writes a setpoint and reads an odometry
snapshot + a state enum; the backend only reads that setpoint and drives the wire** — and all
of it on one thread.

---

## 7. Frame conversions (single source of truth: `px4_backend_base.hpp`)

| Quantity | ENU (canonical) | NED (PX4 wire) | Conversion (named function) |
|----------|-----------------|----------------|-----------------------------|
| position | (E, N, U) | (N, E, D) | `enu_to_ned`: `(enu.y, enu.x, -enu.z)` |
| velocity | (vE, vN, vU) | (vN, vE, vD) | same swap+negate-z |
| yaw | CCW from East | CW from North | `enu_yaw_from_ned_quat` / `enu_yawrate_to_ned`: `pi/2 - yaw` (wrap -pi..pi), rate negated |

Every conversion is a **named function** so the call site documents intent — no bare `-` on a
sign flip. VLM body-relative commands stay **FLU**; the FMU converts FLU->ENU with `odom.yaw`
(`flu_to_enu`). Every `*Ned` tuning constant moves into `px4_backend_base.hpp`; the FMU keeps
only ENU constants (`kTakeoffTargetAltEnu = +2.0`, `kGoRadius`, etc.).

---

## 8. Verification (parity against known-good)

The PX4-backend binary must fly the canned smoke test **functionally identically** to the
current commit. Beyond "full cycle completed," the parity check **numerically asserts frame
correctness** (a NED->ENU sign flip crashes silently past an "it flew" check):

1. Full cycle: STANDBY->TAKEOFF->FLIGHT(GO)->LANDING->STANDBY, `engaged` confirmed, clean disarm.
2. **Direction:** for "forward 1 m" at spawn yaw, assert the GO displacement vector points along
   the heading (ENU), matching the NED-verified result recorded in NOTES.md.
3. Takeoff profile: climb reaches +2.0 m ENU without the pre-fix ground-lingering tip.
4. Handshake timeout path exercised (delay/deny arming) -> backend FAULT -> FMU aborts the takeoff,
   no infinite TAKEOFF hang.

User compiles/runs (per workflow); I diff the new DIAG log against the baseline.

---

## 9. Definition of done (this slice)

- [ ] `px4_backend/` created; `offboard_translator.hpp` removed.
- [ ] `PX4Backend` (concrete) defines the canonical types + all verbs; absorbs handshake +
      stream loop + odom/status subs (incl. `_v4`) + NED<->ENU; stream timer is the LAST member.
- [ ] FMU holds one `PX4Backend m_backend`, is pure-ENU, has no `px4_msgs`/`OffboardTranslator`
      include, no inline handshake.
- [ ] Runs on a **single-threaded executor**; no mutex/atomics anywhere in the new code.
- [ ] Smoke test passes §8 parity incl. numeric direction assert + handshake-timeout path.

---

## 10. Future Milestones (preserved rationale; each gated on a concrete trigger)

These were fully reasoned through during design. They are **not** deleted — they are sequenced
behind the specific event that makes each one *necessary*, so the Day-1 core stays simple.

### M1 — Cross-thread concurrency primitive · **Trigger:** we move the stream loop to a background `std::thread` or a `MultiThreadedExecutor`
Only needed if we abandon the single-threaded executor (D3). Then plain members race and we
need guards. **Design ready:** scalars (`IOState`, `m_gotFirstOdom`) -> `std::atomic`; composite
structs (setpoint, odometry) -> a `Shared<T>` = `std::mutex` + `try_lock`-with-cache — writers
`lock()`, the high-rate reader `try_lock()`s and falls back to a private cached copy (dodges
priority inversion / executor starvation; a component-wise `atomic<f32> x,y,z` would tear; a
fenced seqlock is not human-maintainable). **Do NOT add this while single-threaded** — it would
be a mutex guarding a race that cannot happen.

### M2 — Backend abstraction (CRTP + compile-time selection) · **Trigger:** `TelloBackend` exists (sub-project B)
With a *second* real backend we finally know the true shared shape. Then: promote the canonical
types into a new `drone_backend/` folder; introduce `template<class Derived> DroneBackendBase`
(CRTP — static polymorphism, **no vtables**, per the "either/or per binary" requirement — a
missing `_impl` is a compile error); add `tello_backend/` as a sibling; select at compile time
with `-DDRONE_BACKEND=px4|tello` (`using ActiveDroneBackend = ...`; unset -> hard `#error`); wrap
in a `DroneController` the FMU holds. **R (contract drift):** CRTP enforces *structural*
conformance only; *semantic* conformance (what "takeoff complete" means per platform) is on the
author + the parity test — documented, not compiler-checked. Rejected alternatives for this
seam: `virtual`, `union`+placement-new, `unique_ptr`, `std::variant`/`visit`.

### M3 — Odom-loss failsafe (`abort()` single path) · **Trigger:** real-hardware bring-up, or any flight where an EKF dropout is credible
The known-good reference has none; SITL doesn't need it. When added, it is **one bite-sized unit
with its own acceptance test**, not four lines smeared across the control loop.
- **Trigger logic (FMU):** `odomCallback` refreshes `m_lastGoodOdomUs` on each *valid* frame and
  latches `m_haveHadFirstOdom` (kills the startup `stamp==0` false-trip). Control loop:
  `if m_haveHadFirstOdom and (host_now_us() - m_lastGoodOdomUs) > kOdomStaleUs: abort()`.
  `host_now_us()` is `CLOCK_MONOTONIC` (no wall-clock underflow); `kOdomStaleUs` is sized off the
  **odom** rate per backend (PX4 ~30-50Hz, Tello ~10Hz), not the control rate. This is why
  `Odometry.host_stamp_us` already exists in the Day-1 struct — the field is cheap; only the
  *logic* waits.
- **`abort()` contract (one path, backend-agnostic):** (1) store a descent setpoint so the stream
  stops relaying cruise velocity; (2) call `m_backend.abort()`; (3) `IOState -> FAULT` (latched).
- **`abort()` per backend — "get the vehicle to a non-flying state WITHOUT reading FMU odom":**
  PX4 -> `VEHICLE_CMD_NAV_LAND` (PX4's onboard estimator does the blind descent); Tello -> native
  `land` (onboard sensors). The failsafe is odom-independent *by delegation*, so no hand-rolled
  timed descent.
- **Acceptance (parity) test:** mid-flight, kill the odom source against each backend; assert
  within `kOdomStaleUs + margin` that `IOState == FAULT`, the shared setpoint is a descent (not
  the prior cruise), the vehicle reaches a non-flying state, and feeding frozen/garbage odom
  after the cut changes nothing.

### M4 — `TelloBackend` (sub-project B) · **Days 2-3**
Bench then flight. **[ANNOTATED: needs additional review/testing]**; imperfect-but-noted is
acceptable per the 3-day deadline. Forces M1 (its UDP driver runs off-executor) and M2.

### M5 / M6 — Perception (C) / event-driven VLM (D)
In scope for the 3 days, sequenced after A/B. Plug into the now hardware-agnostic FMU.

---

## 11. Risks (Day-1 core)

- **R1 — ENU migration sign errors.** Highest risk; §8.2 direction assert is the guard. NED-native
  is the documented fallback if signs fight us under deadline (D5).
- **R2 — Handshake timeout value.** `kHandshakeTimeoutUs` needs a sane default (~5 s) tuned in sim;
  too tight = false aborts on slow EKF, too loose = long hang.
- **R3 — Destruction order.** Stream timer declared LAST (reverse-order destruction stops it before
  pubs die); `stop()` is the explicit early-out. Verify no publish-after-free on Ctrl-C.
