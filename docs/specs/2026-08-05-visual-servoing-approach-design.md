# Visual-Servoing APPROACH — Design Spec

> **Status:** DESIGN / APPROVED-FOR-REVIEW. Continuation of Phase-2 sub-project **A**
> (DroneBackend abstraction). Prerequisite: the PX4Backend extraction Tasks 1–3 (done, flying)
> plus Task 4 (ENU seam) land **before** this. See `2026-08-04-drone-backend-abstraction-design.md`
> and `../plans/2026-08-04-px4-backend-extraction.md`.
> **Scope of this slice:** add a camera-driven `APPROACH <label>` command that flies toward a
> detected target by re-computing the line-of-sight to it every control tick, plus the small
> shared detection-lookup it stands on. **No** real YOLO, no ORBIT/SEARCH behavior, no VLM
> changes ship here — the servo is exercised against a stubbed/synthesized detection.
> **Target:** C++17, no exceptions, PX4 SITL (gz_x500_gimbal), ENU seam.

---

## 0. Why this exists

Today's `GO` freezes a single world point at activation (one FLU delta → one world coordinate)
and flies to it open-loop. That is the wrong shape for the real job: chasing a
camera-detected target. Two problems it can't solve:

1. **Drift.** With no GPS and no persistent vision lock, the drone's world-position estimate
   drifts over a flight (the system prompt in `llm_base.hpp` even says so: "No absolute
   coordinates exist. Drone tracks go and curve commands using downward optical flow"). A
   waypoint frozen from a stale estimate is chased blind.
2. **Open loop.** A moving or mis-localized target is never re-acquired; the drone flies to a
   ghost point.

The prior session's GO-spiral had two stacked causes: bearing computed toward a fixed point
from a **laggy position estimate** (so the bearing itself rotated), and constant speed with no
deceleration. This redesign removes the first cause structurally: the bearing becomes a
**measured line-of-sight from the camera**, not a value dead-reckoned from drifting odometry.
That is the core reason a camera servo is better-conditioned than the odom-based pursuit that
spiraled — see §9 (Risks) for the residual that remains.

## 1. Non-goals (YAGNI guard)

- **No real perception.** YOLO26n-depth and the fused perception snapshot are sub-project C.
  This slice reads a **stubbed** `PerceptionSnapshot`; a canned test synthesizes it (§7).
- **No ORBIT / SEARCH behavior.** They will reuse the shared *lookup* (§4) but own their own
  control loops and done/fail rules; none of that ships here.
- **No fat "TargetTracker".** GO/ORBIT/SEARCH are three different behaviors with three
  different done/fail rules (§4). We share the detection *query*, not a control state machine.
- **No change to blind `GO`.** It stays for dead-reckoned FLU moves (still used by the reflexive
  hold-clearance path, ARCH §5.1).
- No VLM/system-prompt wiring beyond adding the command entry (§8 — it's small; the servo does
  not depend on it).

## 2. Decisions locked

| # | Decision | Why |
|---|----------|-----|
| D1 | **New command `APPROACH <label>`**, separate from `GO` | Different input (a target name, not an FLU delta) and different loop (closed-loop servo vs open-loop waypoint). One command, one job. Blind `GO` stays unchanged. |
| D2 | **Metric depth per detection** (YOLO26n-depth) | We commit to metric range from the detector; if it is too slow that is a later problem. This is *not* MiDaS relative depth — range is a real distance, so the done rule is a real standoff distance. |
| D3 | **Share the lookup, not the tracker** | A ROS-free `detectionByLabel(...)` returns the newest matching detection as a body-frame direction + range + age. ORBIT/SEARCH call the same query later; each keeps its own control + timeout policy. |
| D4 | **Aim is recomputed every tick; no stored world point** | Each tick converts the live body-FLU line-of-sight to a world-ENU velocity using the *instantaneous* yaw. Nothing is integrated, so nothing drifts. This is the whole anti-drift argument. |
| D5 | **Keep the tick-owned velocity-command loop** | Same substrate as the cross-track GO built last session: the tick computes a fresh command from an error signal. Only the *error source* changes (live detection, not a frozen NED line). The frozen-line cross-track *law itself* is dropped — it needed a fixed world line we deliberately discard (see §9 R1). |
| D6 | **Yaw-to-center keeps the target in frame** | For a forward-facing camera, turning to center the bbox (yaw-rate) is how "keep the target in frame until reached" falls out for free — no separate framing logic. |
| D7 | **Built on the ENU seam** (Task 4 first) | New servo code targets the final frame, not soon-to-be-dead NED. Avoids writing it twice. |

## 3. Folder layout

```
source/llm_to_action/
  perception/
    detection_query.hpp      # ROS-free: camera intrinsics, bbox+range -> body-FLU vector,
                             # detectionByLabel(snapshot,label) -> TargetRelative. Unit-testable.
    test/detection_query_test.cpp
  fmu/
    fmu_node.hpp             # + CmdApproach, APPROACH control branch, canned detection rig
    fmu_node_base.hpp        # + APPROACH servo tunables
    llm_base.hpp             # + "approach" command entry in the system prompt (§8)
```
`detection_query.hpp` mirrors the `px4_backend/frame_convert.hpp` pattern: pure `Vec3` math, no
ROS include, testable with a standalone `g++` run. Camera intrinsics live here because this is
where they are consumed. Servo *control* tunables (gains, standoff, timeouts) live in
`fmu_node_base.hpp` (FMU-only tuning), consistent with the process rule.

> **Note:** `perception/` holds only the ROS-free query today. The real fused-snapshot producer
> (sub-project C) will add sibling files behind the same `PerceptionSnapshot` type; the servo
> does not change when it does.

## 4. Interfaces

### 4a. Perception snapshot (the stubbed input the servo reads)
```cpp
// Consumed by the servo; produced by the canned rig now, by YOLO later. Fused per §9 (ARCH).
constexpr u32 kMaxDetections = 16;
struct PerceptionSnapshot {
    TargetDetection dets[kMaxDetections];   // existing struct: label, bbox_[xy]min/max, median_depth_cm
    u32  count{0};
    u64  host_stamp_us{0};                  // frame receipt time (staleness clock)
    bool valid{false};
};
```
The FMU holds it as an atomic snapshot pointer, written by the producer and read by the control
tick — same shape as the existing `m_currImg` atomic image handoff. `median_depth_cm` carries the
**metric** range for the matched detection (D2).

### 4b. Shared lookup (ROS-free, in `detection_query.hpp`)
```cpp
struct CameraIntrinsics { f32 fx, fy, cx, cy; u32 width, height; };  // gz_x500_gimbal fwd cam

struct TargetRelative {
    Vec3 dirFlu;      // unit body-FLU direction to the target (forward+, left+, up+)
    f32  range;       // metric distance, meters (from median_depth_cm/100)
    f32  errX;        // normalized horizontal bbox-center offset [-1..1] (right +)
    f32  errY;        // normalized vertical   bbox-center offset [-1..1] (down +)
    u64  age_us;      // now - snapshot.host_stamp_us
    bool found{false};
};

// Finds the freshest detection whose label matches; back-projects its bbox center through the
// pinhole model, scales by metric range, converts camera->FLU. found=false if no match.
TargetRelative detectionByLabel(PerceptionSnapshot const& snap, char const* label,
                                CameraIntrinsics const& cam, u64 now_us);
```
Camera→FLU convention (forward-facing cam, optical z forward, x right, y down):
`dirFlu = { camZ, -camX, -camY }` after back-projecting `(u,v)` with the intrinsics. Pure math;
no odom, no world frame — the anti-drift property lives here.

### 4c. Command
```cpp
enum class CommandID : u8 { ..., REASSESS = 8, APPROACH = 9, MAX_ID = 10 };
struct CmdApproach {
    FixedStringType target{"\0"};   // YOLO label to chase
    f32             speed{0.0f};    // optional cruise ceiling cm/s; 0 -> kApproachSpeedDefault
};
```
Add the matching `GenericCommand(CmdApproach const&)` ctor (memcpy pattern, like the others).

## 5. Control law (20 Hz tick, `CommandID::APPROACH` branch)

```
approachTick():
    od   = backend.odometry()                          # yaw only; NEVER pos for the aim
    tr   = detectionByLabel(perception(), label, cam, now_us)

    if not tr.found or tr.age_us > kApproachLostTimeoutUs:
        if m_haveLastAim and (now - m_lastAimUs) <= kApproachLostTimeoutUs:
            hold m_lastAimFlu at low speed              # brief coast on last good aim
        else:
            backend.set_velocity(0,0,0); completeCurrent("approach_lost_failed")   # FAIL (D)
        return

    m_lastAimFlu = tr.dirFlu; m_lastAimUs = now; m_haveLastAim = true

    if tr.range < kApproachStandoffM:
        backend.set_velocity(0,0,0); completeCurrent("approach_ok"); return        # DONE

    speedCeil = (cmd.speed > 0 ? cmd.speed : kApproachSpeedDefault) / 100.0       # m/s, frozen at activation
    # forward speed decelerates as range approaches standoff
    sp        = clamp(kApproachFwdGainHz * (tr.range - kApproachStandoffM), 0, speedCeil)
    # yaw to center the target horizontally -> keeps it in frame (D6)
    yawRate   = -kApproachYawGain * tr.errX
    # match target height
    vUp       =  -kApproachVertGain * tr.errY
    # forward along body-x, plus vertical; convert body-FLU aim -> world ENU by CURRENT yaw
    aimFlu    = { sp, 0, vUp }
    velEnu    = flu_to_enu(aimFlu, od.yaw)
    # damp lateral world-velocity to kill the pursuit arc (R1)
    velEnu   -= kApproachLateralDamp * lateral_component(od.vel, flu_to_enu({1,0,0}, od.yaw))
    clamp |velEnu| <= speedCeil
    backend.set_velocity(velEnu, yawRate)
```
Notes:
- `flu_to_enu` and the ENU velocity path come from Task 4. Yaw is instantaneous each tick, so
  the FLU→world conversion carries no accumulated error (D4).
- `lateral_component(measVel, forwardDir)` = the part of measured velocity perpendicular to the
  current forward aim; subtracting a fraction of it is the spiral mitigation (§9 R1). This is
  **not** the old frozen-line cross-track term — there is no frozen line.

## 6. Completion / lost / fail rules

| Event | Predicate | Action |
|---|---|---|
| Reached | `range < kApproachStandoffM` | stop, `completeCurrent("approach_ok")` |
| Lost (brief) | `not found` or `age > timeout`, within the coast window | hold last aim at low speed |
| Lost (gone) | still lost past the coast window | stop, `completeCurrent("approach_lost_failed")` → task FAILED |

The standoff done-rule is specific to *approach*. ORBIT (hold `range ≈ radius`) and SEARCH (no
approach at all) will use `detectionByLabel` but their own range logic — out of scope here.

## 7. Testing (no YOLO needed)

Mirror the existing canned-plan philosophy (`injectCannedPlan` / `scripts/simenv_llm.sh`):

- **Standalone unit test** `detection_query_test.cpp` (`g++`, ROS-free, like
  `frame_convert_test.cpp`): a bbox at image center with known range → `dirFlu ≈ {1,0,0}`,
  `range` correct; a bbox offset right → `errX > 0` and `dirFlu.y < 0` (target to the right);
  label mismatch → `found == false`.
- **Canned SITL detection rig** `injectCannedApproachPlan()` + `--canned-approach` +
  `scripts/simenv_llm.sh approach`: place a **known static world point** (the "target"). Each
  tick the rig **synthesizes** a `PerceptionSnapshot` by projecting that world point through the
  drone's *current* pose + camera into a bbox + metric range, and publishes it. The servo
  consumes only the synthesized detection (never the world point), so it is a real closed loop:
  the operator verifies the drone turns to face the point, flies in, and **stops at
  `kApproachStandoffM`**, and that killing the synthesized detection mid-approach makes the
  command FAIL after the coast window. This is the parity gate for this slice.

> The rig uses odom ground truth to *fake perception*; the servo under test uses odom only for
> instantaneous yaw. Keep that separation — it is what makes the test meaningful.

Verification workflow unchanged: operator compiles + runs; the implementer diffs `output.txt`
(`FMU_NODE_DEBUG`/`FMU_NODE_DIAGNOSTICS`), un-wrapping tmux line wraps first.

## 8. VLM system-prompt entry (`llm_base.hpp`)

Add alongside `orbit`/`search` (which already take `target_object`):
```
approach            Fly toward target_object until within standoff distance. Target must be
                    visible in view. Fails if the target is lost.
{"action": "approach", "target_object": "<name_string>", "speed": <int>}
```
And a `translateToBaseCommands` case mapping it to `CmdApproach`. The servo does not depend on
this; it is here so a plan can name the command once perception exists.

## 9. Risks

- **R1 — Pursuit arc / residual spiral.** Camera servo removes the *false-bearing* driver
  (bearing is measured, not from drifting odom), but lateral momentum can still curve the path.
  Mitigations: `kApproachLateralDamp` (perpendicular-velocity damping), a low `speedCeil`, and
  yaw-to-center keeping the target ahead. **This must be re-validated in SITL** — the prior
  session proved plausible control fixes can make things worse; do not assume the swap is free.
  Fallback if the arc is bad: cap yaw-rate and lower the forward gain so the approach is nearly
  straight-in before tuning further.
- **R2 — Depth latency/accuracy.** YOLO26n-depth may be slow or noisy. The done rule keys on
  `range`; a noisy range near standoff could early-stop or oscillate. Mitigation: a small
  standoff hysteresis and/or a short range median if it bites (deferred until the real detector
  exists — the stub is clean).
- **R3 — Lost-target flicker.** A target that drops for one frame should not fail the command.
  The coast window (`kApproachLostTimeoutUs`) absorbs brief dropouts; only a sustained loss
  fails.
- **R4 — Camera intrinsics.** `gz_x500_gimbal` FOV/intrinsics must match the sim camera or the
  bearing is wrong. Pin them from the sim camera config; the unit test asserts center/offset
  geometry.

## 10. Tunables (all in `fmu_node_base.hpp` unless noted)

As shipped (2026-08-06, tuned against real seg+depth inference in SITL, not just the canned
rig this table originally targeted):

```cpp
constexpr f32 kApproachStandoffM     = 2.00f;   // stop this far from the target (slack against
                                                 // jittery real depth, not just a stop point)
constexpr f32 kApproachSpeedDefault  = 80.0f;   // cm/s, if CmdApproach.speed == 0
constexpr f32 kApproachFwdGainHz     = 0.35f;   // (range-standoff) -> forward speed
constexpr f32 kApproachYawGain       = 1.0f;    // horiz bbox error -> yaw-rate
constexpr f32 kApproachVertGain      = 0.5f;    // vert bbox error -> vertical velocity
constexpr f32 kApproachLateralDamp   = 0.5f;    // perpendicular measured-velocity damping (R1)
constexpr f32 kApproachCoastSpeedMps = 0.15f;   // speed while coasting on a stale-or-lost target
constexpr u32 kApproachLostTimeoutMs = 3000;    // coast window before FAIL on lost target
constexpr u32 kApproachFreshMs       = 200;     // detection older than this is untrusted for
                                                 // closing speed; falls back to coast
// CameraIntrinsics live in perception/detection_query.hpp (consumed there).
```
All values SITL-tuned, not first-guess -- real depth inference on this CPU can freeze for 1s+
under load, so the single "lost" threshold this section originally specced was replaced by a
**two-threshold fresh-vs-lost model**: a detection older than `kApproachFreshMs` is stale (not
trusted for closing speed -- acting on a frozen range means never decelerating) and the servo
coasts at `kApproachCoastSpeedMps`; only past `kApproachLostTimeoutMs` with no detection at all
does the task FAIL. Gains reuse the "Hz" (1/s) convention of the existing GO tunables.

## 11. Definition of done (this slice)

- [x] `perception/detection_query.hpp` + unit test pass (`g++`, geometry asserts).
- [x] `CmdApproach` + `CommandID::APPROACH` + `GenericCommand` ctor added; blind `GO` unchanged.
- [x] `PerceptionSnapshot` type + atomic handoff in the FMU -- REAL, not stubbed: block 4.2
      landed `PerceptionRuntime` before this slice started (see plan deviation note above §11).
- [x] APPROACH control branch: yaw-to-center + range-decel forward + vertical match + lateral
      damp; recomputes aim every tick, stores no world point.
- [x] Standoff done rule; coast-then-FAIL lost rule.
- [x] `injectCannedApproachPlan` rig + `scripts/simenv_llm.sh approach` -- built and compiles;
      **operator SITL confirmation of turn-face-approach-stop and lost→FAIL is still open**
      (human check, not run by this session, same status as the ENU convention's SITL re-gate).
- [x] `approach` entry in `llm_base.hpp` + `translateToBaseCommands` case (landed earlier as
      ROADMAP 3.6, before this slice).
- [x] Runs on the existing Reentrant + atomics model; no new mutex.

## 12. Sequencing

1. **Task 4 (ENU seam)** from the PX4Backend plan — first, unchanged.
2. This slice, in DoD order.
3. Real perception (sub-project C) drops the fused snapshot behind `PerceptionSnapshot`; the
   servo does not change.
4. ORBIT/SEARCH reuse `detectionByLabel` with their own control loops (future).
