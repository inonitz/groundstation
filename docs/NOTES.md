# Architectural Notes

## PX4 OFFBOARD engage (fmu_node offboardPublishLoop)
- Stream `OffboardControlMode` + `TrajectorySetpoint` continuously from node start
  (zero-vel in STANDBY) — PX4 rejects an OFFBOARD switch without a live setpoint stream.
- **Do NOT arm on a wall-clock/setpoint timer.** Gate the engage on first odometry
  received (`m_gotFirstOdom`) so the estimator is actually valid — arming before the
  local-position/velocity estimate exists spins motors with nothing to act on -> no
  climb -> auto-disarm. This was the "rotors spun then stopped" bug.
- Proven order (from speech_to_action): **arm first, then request OFFBOARD**, and RETRY
  both every tick until `VehicleStatus` confirms `ARMING_STATE_ARMED (2)` +
  `NAVIGATION_STATE_OFFBOARD (14)`. Never fire-and-forget a single VehicleCommand.
- **Takeoff needs climb AUTHORITY, not a gentle setpoint.** A -1.0 m/s climb velocity
  did NOT track (altNED stuck ~0.04 for ~4s while commanding velz=-1.0): PX4's MC
  controller ramps thrust timidly while it still thinks the vehicle is *landed*, so a
  small velocity error lingers in ground effect - long enough for uneven terrain to tip
  the airframe onto its props before it gains height. Fix: climb at **-2.0 m/s to -2.0 m**
  (the proven speech_to_action profile). Bigger vz error -> more thrust -> clears ground fast.
  `kTakeoffClimbVelNed`/`kTakeoffTargetAltNed` in fmu_node_base.hpp.

## PX4 message versioning -> topic name suffixes (gotcha)
- PX4 appends `_vN` to a topic when its `.msg` has `MESSAGE_VERSION = N > 0`.
  - `VehicleStatus` (MESSAGE_VERSION=4) -> `/fmu/out/vehicle_status_v4`
  - `VehicleOdometry` (MESSAGE_VERSION=0) -> `/fmu/out/vehicle_odometry` (no suffix)
- A ROS2 sub on the wrong (unversioned) name fails SILENTLY — it just holds default
  values, no error. Cost us a dead VehicleStatus sub (nav/arm stuck at 0) that looked
  fine because the flight worked anyway via the odom-gate above.

## Coordinate frame (verified in sim)
- `flu_to_ned(flu, yaw)`: north = x·cosψ + y·sinψ, east = x·sinψ − y·cosψ, down = −z.
- Verified: "forward 1 m" at spawn yaw 2.10 rad produced NED (−0.50, +0.86) = (cosψ, sinψ)
  — drone flew along its heading. Forward mapping correct; y-left sign not yet exercised.

## GO traces a logarithmic-spiral ("golden ratio arc") — root cause (2026-08-05)
- Symptom: `go forward 1m` reaches target but the ground track ARCS (bulges then
  curves back), resembling a logarithmic spiral, near the waypoint.
- NOT a frame bug: measured vs commanded velocity agree in SIGN (N-,E+); the
  "forward -> ESE" is CORRECT (sim spawn yaw ~2.09 rad, matches prior NOTES).
- NOT weathervane: measured `yawrate ~= 0.00` throughout GO; yaw drifts only
  1.92->1.73 passively. Body is not rotating.
- Actual cause: the GO controller is constant-speed PURE PURSUIT with no
  deceleration. Every 20Hz tick it commands `unit(targetNED - posNED) * 0.30 m/s`
  toward a FIXED point. PX4's velocity controller lags (~0.3-0.5s) and the drone
  carries lateral momentum the weak 0.30 setpoint can't cancel:
    * measured speed |v| ~= 0.53 m/s while commanded is 0.30 (overspeed / coast),
    * measured velocity DIRECTION lags the rotating command,
    * -> position vector orbits the target while distance shrinks = spiral.
  Compounded by: (a) altitude SAG during translation (velocity-only offboard has
  no altitude hold; alt dropped 2.28->1.68m mid-GO), (b) residual takeoff climb
  velocity (meas vz=-1.28) still active at GO entry.
- Proposed fix (choose tomorrow):
    1. PREFERRED: send GO as a PX4 POSITION setpoint (position=target, velocity=NaN);
       PX4's position controller gives a straight line + smooth decel + altitude
       hold. Keep velocity setpoints only for takeoff/land climb/descent.
    2. Or proportional decel: v = clamp(Kp * dist, vmin, vmax) toward target, so it
       slows into the waypoint instead of coasting past. Band-aid, still lag-prone.
- Evidence: output.txt GO block; instrumentation added measVelNED + yawrate to the
  FMU DIAGNOSTICS + GO logs (px4_backend Odometry now carries vel + yawrate).
- OPEN (separate, lower priority): first odometry arrived ~20s after node start in
  both runs -> handshake stalled ~20s (CONFIRMED at setpoints=603). EKF/odom
  publish latency in this world? Not blocking, but investigate.

## GO controller iteration (2026-08-05, continued) — landed state + what's still open
- Tried, in order, with SITL evidence each time (`output.txt` snapshots per attempt):
  1. Proportional decel, pure pursuit (recompute bearing every tick), no damping —
     WORKED (completed cleanly) but bearing swept ~220 deg over a 1m hop (visible arc).
  2. Added a D term (damp measured velocity) on top of #1 — did NOT reduce the arc
     at kDampingGain=0.6 OR 1.0 (tested both). Pure-pursuit's instability is
     geometric (bearing recomputed from a laggy/overshooting position every tick),
     not a magnitude/damping problem. Reverted.
  3. Line-of-sight with direction FROZEN at activation, zero further feedback
     (pure dead reckoning) — catastrophically worse: any real disturbance drifts
     the drone off the line and it NEVER corrects, distance grows unbounded,
     GO never completes, drone never lands. Reverted hard.
  4. **Current: line-of-sight direction frozen at activation + cross-track PID
     correction** (perpendicular-to-line term pulls back drift; forward speed
     P-decays with along-line remaining distance). This is the standard "carrot
     chasing" guidance law. Converges reliably, bounded modest wobble, no runaway.
  5. Added a momentum-settle dwell between tasks (`kGoSettleMs`=500,
     `completeCurrent()` sets `m_settleTicksRemaining`, controlLoop holds zero-vel
     until it elapses before dequeuing the next task) — residual velocity from the
     PRIOR leg (worst: TAKEOFF's climb velocity bleeding into the first GO) was
     getting baked into the next leg's frozen direction/line math with zero time to
     decay. Measurably reduced bearing-spread across all 8 legs of the cross test
     (forward: 56.5 deg -> 42.3 deg; most other legs also improved).
- Built two canned test rigs to interrogate this without a VLM in the loop
  (`fmu_node.hpp`: `injectCannedCrossPlan()`, `injectCannedSpeedPlan()`;
  `fmu_node.cpp`: `--canned-cross` / `--canned-speed`; `scripts/simenv_llm.sh
  [forward|cross|speed]`):
  - `cross`: forward/left/back/right 1m, each immediately UNDONE (return to
    start) before the next axis, so per-axis error doesn't chain into the next
    axis's start point. Confirms `flu_to_ned` is NOT the bug (spread trends down
    across the mission, doesn't sit on a fixed axis).
  - `speed`: forward+return at 15cm/s then again at 80cm/s. **Finding: this test
    was flawed as designed** — `kGoApproachGainHz * remain` (0.5/s x ~1m) caps
    commanded speed around 0.5 m/s for a hop this short regardless of the
    requested cruise ceiling, so "80cm/s" never actually ran faster than ~0.50
    m/s. Real signal in the data: `dist` decayed MORE monotonically at the higher
    setpoint (no overshoot bump), ruling out actuator-lag-scales-with-speed as
    the driver of the residual wobble.
- Still open / not chased further today (explicitly deprioritized for time — see
  decision below): cross-track gain (`kGoCrossTrackGainHz`=1.0) not retuned;
  forward leg (right after TAKEOFF) still has the largest bearing-spread of any
  leg, consistent with the climb-velocity residual only being PARTIALLY absorbed
  by the 500ms settle dwell, not fully.

## Decision: stop tuning point-to-point GO, redesign for visual servoing instead
- Point-to-point GO (fly to a fixed NED point computed once from an FLU delta)
  is the WRONG shape for the actual use case. It was only ever a stand-in for
  "fly toward a YOLO-detected target."
- User's direction (2026-08-05): when GO is driven by a YOLO-tracked target,
  recompute the DIRECTION VECTOR to that target every iteration and keep nudging
  toward it — don't convert one detection into a fixed world-NED waypoint and
  fly to it open-loop. Two concrete implications:
    1. Don't require re-deriving the drone's own local/global position every
       tick to do this — track the last position at which the target was seen
       and take small relative nudges toward the current detection, rather than
       depending on absolute local-position accuracy staying good over time.
    2. This sidesteps the local-frame-drift problem raised earlier in the
       session (absolute NED position estimates drift over a long flight with
       no GPS/vision anchor) — a continuously-refreshed visual error signal
       doesn't accumulate that drift the way a one-shot NED conversion does,
       because it's re-anchored to ground truth (the object in frame) every
       cycle instead of dead-reckoning from a stale estimate.
  This matches why the velocity-command architecture (not PX4 position-setpoint
  mode) was chosen back when go_pos vs go_vel was decided: the tick-owned error
  computation this session's cross-track law already does is the right substrate
  — the fix now is swapping WHAT the error is computed against (live YOLO
  detection) rather than a frozen NED point, not rebuilding the control loop.
- Next session resumes with a docs/* re-read (architecture spec + plans) before
  touching code, specifically to figure out where target-tracking state (last
  known detection position, staleness handling) should live relative to the
  existing PX4Backend/FMU split.


## VLM integration wired (2026-08-05) + visual-servoing APPROACH spec
- Reprioritized per user: VLM integration + tests + real SITL before the APPROACH
  servo and before Task 4 ENU (VLM is planner-side, frame-agnostic, fastest to a
  real demo; APPROACH needs the ENU seam so it comes after).
- **VLM event-driven wake wired** (was defined-but-never-called). `callLlamaServer`
  now fires from `controlLoop()` when the task queue drains, via `maybePlan()`:
    - Runs the blocking inference OFF the control thread with `std::async`
      (`m_planFuture`), so the 20Hz loop + backend stream watchdog never stall.
    - `m_planning` atomic = single-flight guard; the async task is the SPSC queue's
      only producer. Planning fires only in the idle gap (no active task, queue
      empty), so it never races `completeCurrent()`'s `m_completedTasks` writes.
    - `kPlanCooldownMs` (2000) in `fmu_node_base.hpp` throttles the queue-empty
      re-plan poll so an empty/unparseable plan doesn't hammer the server.
    - Gated on the first camera frame arriving (`m_currImg` non-null).
    - `start()` sets `m_missionActive` true only for VLM runs; canned runs pre-fill
      the queue and must not poll a (possibly absent) server after they drain.
    - dtor drains `m_planFuture` before `m_vlmClient.destroy()` (no VLM call on a
      dead client).
- **Tolerant plan extraction**: new ROS-free `fmu/plan_parse.hpp::extractJsonArray`
  slices the outermost `[...]` from Qwen3-VL output (survives ```json fences /
  prose prefix). `translateToBaseCommands` runs it before `json::parse`. Standalone
  test `fmu/test/plan_parse_test.cpp` passes (`g++`, no ROS).
- **Prompt now carries live vehicle state** (`alt_up_m`, `speed_mps`) from backend
  odometry, ahead of the executed-history block.
- **`./scripts/simenv_llm.sh vlm`** new mode: launches the Qwen3-VL llama-server
  pane (`-c 4096`) + runs the FMU with no canned flag (VLM-driven). Objective:
  "Take off, fly forward 1 meter, then land."
- Known risks to watch in the first run: llama-server must be up on :8080 before
  the FMU's first plan; `-c 4096` context vs the large system prompt + image
  tokens (FORK-A: may need harder prompt compression); Qwen3-VL must emit a JSON
  array of the 4 wired actions (takeoff/land/stop/go) — others are skipped.
- Visual-servoing APPROACH design approved + specced:
  `docs/superpowers/specs/2026-08-05-visual-servoing-approach-design.md`. New
  `APPROACH <label>` command (blind GO unchanged); shared ROS-free
  `detectionByLabel` lookup (not a fat tracker); yaw-to-center + range-decel servo
  recomputed every tick from live detection (no stored world point -> no drift);
  metric depth from YOLO26n-depth (NOT MiDaS); done at standoff, lost->FAIL.
  Sequenced AFTER Task 4 ENU seam.


## VLM-driven flight WORKS end-to-end (2026-08-05)
- First fully VLM-driven SITL flight: text-only Qwen3-VL (no camera frame yet)
  planned takeoff -> forward -> forward -> forward -> land, executed through the
  real translateToBaseCommands path. TAKEOFF reached altNED=-2.03, three GO legs
  each completed within 0.2m, LAND force_disarmed at altNED=-0.08.
- The VLM re-plans on every queue-empty (event-driven wake): it emitted takeoff+go,
  then go, then go, then land across 4 planning cycles (929/1213/925 char plans) --
  hence "went forward a couple of times." Working as designed.
- Two root causes found + fixed this session's runs:
  1. Camera plugin never loaded: built as `libGazeboGstCamera.so` but every script's
     SDF patch loads `libGazeboGstCameraPlugin.so`. Fixed via CMake OUTPUT_NAME in
     gstreamer_gz_udp_tx/CMakeLists.txt (artifact now matches the scripts). NOTE:
     scripts/simenv.sh has the SAME wrong name -- fixed centrally by the rename.
  2. VLM returned 0 chars (fast ~10ms HTTP fail): llamaclient send() always emitted
     an image_url block; with an empty base64 payload the server 400s instantly.
     Fixed: omit the image block when no frame (text-only path). Added HTTP status/
     error diagnostics to callLlamaServer.
- Fix for "VLM keeps running after landing": LAND now marks the mission terminal
  (m_missionActive=false in the land_ok path), so maybePlan stops soliciting new
  plans once landed. Limitation: assumes LAND = end of mission (fine for POC;
  revisit if a mission needs multi-takeoff / VLM-signalled completion).
- Landing "violence" observed this run was NOT a landing-mechanics bug -- it was a
  text-only run (no camera), so the VLM could not frame a landing zone and emitted a
  blind `land`. Per the system prompt's SAFE LANDING PROTOCOL (llm_base.hpp lines
  79-92), landing is VLM-owned: frame the zone in the forward camera, check
  clearance, then output [go over spot, land] (or search for another spot if
  obstructed). Do NOT add a hardcoded NAV_LAND / auto-land verb -- that bypasses the
  "VLM plans, deterministic math executes" architecture. Landing quality rides on
  (a) vision working (camera plugin now fixed) and (b) the landmark-relative
  positioning primitive = the same visual-servoing GO/APPROACH work already specced.
  "go over spot" IS a detection-relative move; safe landing is downstream of the
  visual servo, not a separate control-law fix.


## Camera frames never reached FMU: udpsink missing-space bug (2026-08-05)
- With the plugin name fixed, the TX plugin loaded (1280x720) but the model still
  planned vision=0. Root cause: gstreamer_gz_udp_tx/gazebo_cam_plugin.cpp built the
  pipeline as `"udpsink host=" + kUdpHostIpAddress + "port=" + port` -> produces
  `udpsink host=127.0.0.1port=11111` (NO space). gstreamer parses the whole
  `127.0.0.1port=11111` as the host string; the port property stays default (5004),
  so nothing is sent to 127.0.0.1:11111 where the RX node's udpsrc listens. RX got
  no frames -> FMU m_currImg stayed null -> every plan was text-only.
- Fix: one space -> `" port="`. Requires rebuilding the GazeboGstCamera plugin.
- Added FMU debug to confirm the path end-to-end (per user request): imgCallback
  logs throttled `camera frame rx: WxH encoding=... count=N`; callLlamaServer logs
  `VLM request: image=yes/no b64Bytes=... promptChars=...` so we can see the image
  is actually encoded into the request, plus the existing `(vision=N)` on the wake.
- NOTE: llama-server still warns Qwen-VL needs >=1024 image tokens; add
  `--image-min-tokens 1024` to the server line for grounding accuracy once frames
  flow (kept off until vision is confirmed reaching the model).


## Frames reach FMU, but plan still fired before them (2026-08-05)
- udpsink fix CONFIRMED: `camera frame rx: 1280x720 encoding=bgr8 count=1..N`
  climbs at ~18fps. Camera path TX->RX->FMU works end to end.
- BUT the first (mission-halting) plan fired at t+3.5s `image=no`, while the first
  frame arrived at t+~15s -> model still planned text-only. First-frame latency is
  ~15s after FMU start (DDS discovery + gst H264 pipeline + first keyframe).
- Fix: kVisionWarmupMs 3000 -> 25000. maybePlan plans the instant a frame arrives
  (img non-null); the 25s is only the dead-camera fallback ceiling. Added a
  throttled "waiting for first camera frame" log so the pre-takeoff pause is legible.
- FOLLOW-UP (not chased): ~15s first-frame latency is slow. Worth reducing later
  (QoS match between RX publisher and FMU sub? DDS discovery? gst keyframe interval
  key-int-max=30). Not blocking; the warmup masks it for now.
- Once next run shows image=yes/vision=1: add `--image-min-tokens 1024` to the
  llama-server line (Qwen-VL grounding warning).


## Vision-grounded planning CONFIRMED + 2nd-plan hang fixed (2026-08-05)
- With warmup=25s, the flying plan now fires vision=1, image=yes b64Bytes~94k --
  the model IS getting the frame. Camera path fully proven end to end.
- New bug: "drone doesn't go down." Plan #1 (with image) = takeoff/go/STOP (VLM chose
  to stop & re-assess, not land). Queue drained -> VLM wake #2 (image=yes) -> the
  async fut->get() NEVER returned (~73s), so m_planning stayed true, no re-wake, no
  landing plan -> drone hovered at 2m indefinitely.
- ACTUAL root cause (from the llama-server pane, which IS in output.txt): NOT a
  socket hang. task 207 (plan #2) was a RUNAWAY generation -- n_decoded climbed
  434 -> 867 -> ... -> 11630+ and still going when the operator killed it. The model
  hit a no-EOS degenerate loop and kept decoding toward its token ceiling. With
  n_ctx_slot=65536 that is minutes of generation, so fut->get() never returned.
- Why uncapped: fmu_node.hpp created the client with max_tokens = 65536/2 = 32768
  (NOT 1024 as I mis-stated earlier). max_tokens WAS honored -- it was just set
  absurdly high for a ~200-token JSON plan. Fix: create(kSystemPrompt, 0.2f, 512).
  512 bounds any runaway to ~4s; temp 0.4->0.2 (client was overriding server --temp
  0.2) reduces degenerate loops.
- The earlier llamaclient.cpp change (keep_alive=false + connection/read/write
  timeouts) was NOT the fix -- it is a harmless backstop kept for hygiene (a genuine
  hang now returns after 45s instead of forever). Root cause was the token cap.
- HOLD --image-min-tokens 1024 for now: it raises image tokens/context; verify the
  runaway fix (plans keep coming, drone lands) before adding more tokens.
- VLM planning style note: it plans incrementally (takeoff+go+stop, then re-assess),
  not one-shot. Landing arrives in a later cycle -- so the planner MUST stay
  responsive across cycles (hence the timeout fix mattering).

## Task 4 DONE: ENU seam flipped (2026-08-05)
- Canonical frame across the DroneBackend seam is now ENU (E,N,Up+). NED exists
  ONLY on the PX4 wire, converted at exactly two isolated points in px4_backend.cpp:
  odomCallback (NED->ENU on ingest: ned_to_enu + enu_yaw_from_ned + yawrate negate),
  streamTick (ENU->NED on egress: enu_to_ned(vel) + enu_yawrate_to_ned(yawsp)).
- FMU is now pure ENU: kTakeoff/Land/Ground consts -> *Enu (px4_backend_base.hpp),
  takeoff done `d >= +2.0`, land done `d <= 0.1`, GO uses flu_to_enu(relFlu, od.yaw).
  All DIAG/DEBUG labels relabeled NED->ENU (posENU/measVelENU/altENU/targetENU/dirENU).
  buildDynamicPrompt alt_up_m now = od.pos.z directly (ENU up), no negate.
- frame_convert_test.cpp already carried the ENU direction asserts (heading
  preserved, forward=+E facing East); passes standalone g++.
- Backend atomics still named m_posN/E/D but now HOLD ENU (x=East,y=North,z=Up) --
  documented in-code; renaming deferred (cosmetic, per spec "rename mentally").
- OPERATOR GATE (spec section 8.2 numeric direction assert): rebuild + run vlm/canned;
  confirm climb reaches +2.0 ENU, "forward 1m" GO displaces ALONG heading (compare
  to flu_to_enu prediction / the NED-verified spawn-yaw ~2.10 result), clean land at
  ~0.1 + disarm. A NED<->ENU sign flip would pass "it flew" but fail direction.


## Perception (sub-project C) handoff prepared for a separate session (2026-08-05)
- Next unlock is structured perception (the VLM currently sees a raw image, no
  detections/depth -> drone only does blind takeoff/go/land). Handoff written for a
  fresh Claude session to build a ROS-free YOLO26 library in isolation:
  - Spec: docs/superpowers/specs/2026-08-05-perception-library-design.md
  - Prompt: docs/superpowers/handoff-perception-agent-prompt.md
- Library = source/llm_to_action/vision/ wrapping YOLOs-CPP (Geekgineer): YOLO26
  seg (det+masks) + YOLO26 monocular METRIC depth, fused -> PerceptionSnapshot.
  Owns canonical TargetDetection/PerceptionSnapshot (supersede the fmu_node.hpp
  stub; new agent must NOT touch the FMU). Alias-namespace lib (Perception::vision)
  added via add_subdirectory; YOLOs-CPP wired via safe_cpm_add_package / a
  cmake/FetchYOLOsCPP.cmake (same pattern as existing deps).
- Perf: benchmark fp32/int8/int4 x 1/2/4 threads vs targets ~40Hz depth (~25ms) /
  ~30Hz seg (~33ms). NOT a gate -- measure honestly, report, humans reassess if
  short. HARD requirement: cap ORT threads (SetIntraOpNumThreads, disable spinning)
  so it can't starve the FMU control loop / sibling nodes in-process.
- Models (user fetches, /root/models/vision/): yolo26n-seg + yolo26n-depth ONNX
  (dynamic) + int8 (quantize_dynamic) + optional int4 (MatMul4BitsQuantizer) +
  coco.names. Export/quantize commands in spec section 7.
- ON RETURN (this/main session): integrate Perception::vision into the FMU
  (perception thread -> snapshot -> VLM prompt label/bbox/median_depth JSON per
  ARCH section 6 + APPROACH detectionByLabel), apply benchmark's thread/rate/affinity
  recommendation. THEN build the APPROACH servo.


## Sub-project B: TelloBackend built + two-tier tested (2026-08-05)
- Second concrete drone backend (`source/llm_to_action/tello_backend/`), matching
  the PX4Backend verb-shape convention (takeoff/land/set_velocity(ENU)/disarm/
  odometry()/state()). Tello is the PRIMARY hardware target; PX4 SITL is fallback.
- ROS-FREE by design (unlike PX4Backend, which is a ROS node). Own std::thread
  loops + steady_clock: a ~10Hz state-poll thread (ctello GetState -> parse ->
  atomics) and a ~20Hz `rc a b c d` stream thread. Tello needs no DDS, so none is
  dragged in; a thin ROS adapter comes later at FMU integration.
- ctello (carlospzlz/ctello) via CPM DOWNLOAD_ONLY -- we compile only its client
  `src/ctello.cpp` into the lib (skips its example exes + hard find_package(OpenCV)).
  spdlog fetched via CPM, linked header-only. ctello's GetState() binds 8890 and
  returns the state string, so Gemini's manual 8890 socket was redundant/dropped.
  ctello does NOT decode video -- H264 on 11111 is ours (VideoCapture in the test
  harness only; the real path is gstreamer at integration).
- Concurrency: proven std::atomic scalar model for shared telemetry (no mutex).
  The one mutex (m_cmdMtx) only serialises the single command socket across
  takeoff/land/stream threads. sendCmd bounds the ack wait (7s deadline) so a lost
  "ok" can't hang forever -- Gemini's `while(!ReceiveResponse())` could.
- Frame math promoted: px4_backend/frame_convert.hpp -> frame/frame_convert.hpp
  (a second backend now consumes it) + added `enu_to_flu` (inverse of flu_to_enu).
  Updated the px4_backend_base include, the px4 frame-test include, and the FMU
  CMake source-list path. PX4 flight path unchanged: FMU node rebuilds clean, px4
  frame_convert_test still green.
- Command frames: seam-compliant set_velocity(worldVel ENU, yawspeed rad/s CCW+)
  converts ENU->FLU->stick via currentYawRad. NOTE Tello's yaw origin is its
  power-on heading (no true East), so that "world" is pseudo -- fine for relative
  moves. Teleop instead drives set_body_velocity (body FLU, W=+forward) so it never
  depends on the drifting yaw. yawrate_to_stick flips sign (ENU CCW+ -> Tello CW+).
- Stick<->m/s map: kTelloMaxSpeedMps=1.0 (first estimate, calibrate on the teleop
  run); mps_to_stick/stick_to_mps/flu_to_rc all clamp to +/-100.
- TESTS. Tier-1 (hardware-free, green via g++ AND CMake target tello_convert_test):
  enu_to_flu round-trip + facing-East/North axes, parse_tello_state_branchless (all
  16 fields + malformed/null -> false), velocity<->stick clamp/round-trip,
  flu_to_rc axis mapping, yawrate sign. Tier-2 = tello_teleop harness (builds;
  OpenCV-guarded): AsyncKeyHook hold-to-move at fixed velocity (WASD/RF/QE, T/L,
  Space hover, Esc quit) + ~2Hz telemetry print + camera window. USER runs this on
  a real Tello -- the "reality, not castles of sand" checkpoint.
- OUT of scope (flagged): FMU integration + the virtual-DroneBackend-vs-template
  decision (still no interface today); real gstreamer camera (Tello sends RAW
  H264, not RTP -- existing rx_node's rtph264depay won't work; needs
  `udpsrc port=11111 ! h264parse ! avdec_h264 ! videoconvert ! appsink`);
  hardware calibration of the stick<->m/s constant.

## GenericBackend CRTP seam — PX4 & Tello interchangeable (2026-08-05)

- **Problem:** FMU was hard-wired to `unique_ptr<PX4Backend>`; `BackendStatus`/`IOState`/`Odometry`
  were defined twice (px4 + tello) and had already diverged (IOState 4 vs 3 values; Odometry
  yawrate). No shared interface.
- **Mechanism (locked with user):** CRTP, **no virtual**, force-inlined. `template<class Derived>
  struct GenericBackend` in new `source/llm_to_action/generic_backend/`. Nine seam verbs
  (start/stop/takeoff/land/set_velocity/disarm/force_disarm/odometry/state) forward to `*_impl` on
  the derived backend. Missing an `*_impl` = clean compile error at the forwarder, not template spew.
- **Shared types promoted** to `generic_backend/generic_backend_types.hpp` (single definition,
  reconciled to the SUPERSET: IOState keeps PX4's HANDSHAKING; Odometry keeps yawrate — Tello leaves
  it 0). `Vec3` stays single-source in `frame/frame_convert.hpp` (not promoted).
- **FMU stays NON-templated** (explicit user constraint — no `FmuNode<T>`). `active_backend.hpp`
  selects `using ActiveBackend = …` from one macro. Backend chosen at **CMake configure time** via
  three boolean `OPTION`s in the **top-level** CMakeLists.txt — `FMU_BACKEND_PX4` /
  `FMU_BACKEND_TELLO` / `FMU_BACKEND_ALL` — of which **exactly one** must be ON (top-level counts
  them; !=1 ⇒ config error, so no default). The FMU subdir only consumes them (ALL⇒`px4 tello`),
  emitting one `llm_to_action_fmu_<be>` target each with the matching `FMU_BACKEND_<BE>` compile
  def; tello links `Drone::tello_backend`. The old single `llm_to_action_fmu` target is gone.
  build.sh / build.ps1 gained `buildpx4` / `buildtello` actions that pass the full
  `-DFMU_BACKEND_*` triple (resetting the others OFF so switching backends can't leave two ON).
- **Ctor asymmetry** (PX4 needs `Node*`+cbGroup; Tello is ROS-free, needs nothing) hidden behind
  `make_active_backend(Node*, cbg)` in active_backend.hpp — a per-build factory, NOT an `if
  constexpr` (which in the non-templated FMU would fully compile the dead, wrong-arity branch and
  fail). active_backend.hpp is FMU-only glue so it may name ROS types; **TelloBackend itself stays
  ROS-free**.
- **Off-seam (kept, not promoted):** Tello `set_body_velocity` (teleop), `gotFirstState()` /
  PX4 `gotFirstOdom()` — liveness is already uniform via `Odometry.valid`.
- **Deferred wart:** the factory still special-cases construction per backend; a uniform
  backend-construction contract is a later cleanup (user: "figure it out later").
- **Verification:** static checks green (single type def, verbs renamed). Full compile gate
  (`-DFMU_BACKEND=PX4/TELLO/ALL` build, unset FATAL_ERROR, standalone backends + tests) pending —
  user builds manually.

## PerceptionRuntime — vision lib integrated into the FMU (2026-08-06)

- **Problem:** the vision lib (`/root/build_yolo`, `vision::YoloSegEngine`/`YoloDepthEngine`/
  `fuse()`) was built and benchmarked standalone (block 4.1) but not reachable from the FMU; the
  FMU still carried a stub `struct TargetDetection` (fmu_node.hpp:168) that name-clashed with the
  library's global type of the same name.
- **Vendoring:** added a `safe_cpm_add_package(NAME vision GIT_REPOSITORY
  nurmilkov/BUILD_YOLO GIT_TAG feature-vision-api ...)` block to the top-level CMakeLists.txt,
  same pattern as `sttserver` — OPTIONS turn its own tests/benchmarks/sanitizers off so only
  `Perception::vision` builds. Linked into `llm_to_action_fmu_<backend>` in
  `fmu/CMakeLists.txt`. Pinned to a **branch**, not a tag/commit, on purpose: see
  `docs/handoffs/2026-08-06-build-yolo-vision-generic-backend-refactor.md` for a planned CRTP
  backend-boundary refactor on that same branch that has **not** landed yet (confirmed against
  `origin/feature-vision-api` HEAD at integration time) — this session wired against the current
  `YoloSegEngine`/`YoloDepthEngine`/non-template `fuse()` API deliberately, deferring the
  refactor rather than doing both in one pass (human call, asked directly).
- **Two-rate thread design (not `vision::fuse()` in a loop):** `PerceptionRuntime`
  (`fmu/perception_runtime.hpp`, new) runs two independent `std::thread` loops — segmentation
  near its measured ~30Hz ceiling, depth on its own measured ~13Hz ceiling (depth is ~3x over its
  40Hz target on this CPU, block 4.1.8) — calling `segment()`/`estimate()` directly rather than
  `fuse()`, which bundles both models into one blocking call and would force segmentation to wait
  on depth every cycle, collapsing the two rates into one. Each seg tick re-samples median depth
  over the freshest bbox against whichever depth map the depth loop last produced (own ~15-line
  median-over-bbox/mask sampling, mirroring `perception_fusion.cpp`'s private helper — reimplemented
  because splitting the two engines onto separate cadences means fusing across two
  independently-timed calls instead of one `fuse()` call on a single frame; nothing in
  `/root/build_yolo` was touched). Accepted consequence: `median_depth_cm` can lag the current
  bbox by up to one depth cycle — ARCH §10's emergency boundary must tolerate that.
- **Atomic snapshot:** published with the same atomic-`shared_ptr` idiom the FMU already used for
  `m_currImg` (`std::atomic_load`/`std::atomic_store`), not a mutex.
- **Stub removal:** deleted `struct TargetDetection` + unused `m_targets` from `fmu_node.hpp`;
  the global `TargetDetection`/`PerceptionSnapshot` now come from `vision/perception_types.hpp`
  via `perception_runtime.hpp`.
- **Prompt wiring:** `buildDynamicPrompt()` now emits a `[PERCEPTION]` JSON block
  (label/bbox/confidence/median_depth_cm per detection) from `PerceptionRuntime::snapshot()` —
  closes ROADMAP 3.4 (was a stub).
- **Thread budget:** `kVisionSegThreads`/`kVisionDepthThreads` (`fmu_node_base.hpp`, default 2
  each) cap ORT intra-op threads so perception can't starve the 20Hz control loop; model paths
  (`kVisionSegModelPath`/`kVisionDepthModelPath`) point at `/root/models/vision/`, mounted or
  produced separately (not this session's concern).
- **Naming (round 2 — first pass was still an alias-swap, called out and redone):** "seam" was
  doing three unrelated jobs project-wide (GenericBackend's CRTP dispatch, the ENU/NED coordinate
  agreement, and the perception-engine contract) — one vague word standing in for three different
  mechanisms, and swapping it for another catch-all ("interface"/"boundary") in just one heading
  didn't fix that. Replaced with three separate, mechanism-specific terms, applied consistently
  across ARCHITECTURE.md/ROADMAP.md/project_overview.md and the current backend/frame source
  comments (historical dated docs under handoffs/plans/specs left as point-in-time record, not
  rewritten):
  - **backend interface** — the `GenericBackend<Derived>` CRTP verb set PX4Backend/TelloBackend
    implement (was "CRTP seam" / "backend seam" / "FMU seam").
  - **ENU convention** — the project-wide agreement that ENU is the canonical world frame
    everywhere except the PX4 wire; a convention, not an API object (was "ENU seam").
  - **perception contract** — the `TargetDetection`/`PerceptionSnapshot`/`YoloSegEngine`/
    `YoloDepthEngine` types `PerceptionRuntime` is built on (was "engine seam"/"perception seam";
    ARCHITECTURE.md §9 heading now "vision engine interface" implemented by `PerceptionRuntime`).
- **Scope respected:** no edits inside `/root/build_yolo` (vision lib internals untouched, per
  the handoff's explicit boundary); block 5 (APPROACH) not started.

## Comparison repo: pratikPhadte/LLM-controlled-drone (2026-08-06, time-boxed idea-harvest)

Cloned to `/root/llm_drone` (not part of this repo). Read `README.md`, `brain_node.py`,
`llm_client.py`, `yolo_detector.py`, `command_translator.py`.

- **Their architecture:** 3 ROS2 (Jazzy) Python nodes in one workspace — `brain_node`
  (orchestrator: PX4 telemetry subs, 10Hz offboard `TrajectorySetpoint` publisher, LLM call every
  7s **or** on YOLO detection-class change), `yolo_detector` (Ultralytics YOLOv8 in Python,
  frame-skip param, publishes JSON detections), `ros_gz_bridge` (Gazebo camera → ROS2 Image).
  LLM is Ollama-local (mistral/llama3.2/qwen2.5) or Gemini-cloud; PX4 SITL + Gazebo, same
  target as our PX4 fallback. All Python, no C++.
- **Diff/resemblance:** resembles us on PX4/Gazebo/offboard-streaming and on decoupling the LLM
  call from the control loop's cadence. Differs sharply on where "thinking" stops: their system
  prompt hands the LLM the **GPS→NED conversion formula and expects it to do the arithmetic**
  inline; our "VLM plans, deterministic math executes" tenet (ARCH) keeps all arithmetic off the
  LLM by design — theirs is a correctness/reliability risk we deliberately avoided. Their
  "found target while orbiting" handling (`_target_found`) is a one-off hardcoded callback (fixed
  descend-to-40%-altitude, fixed move distance, bearing from `bbox_center` x-offset + FOV) bolted
  onto the ROS callback, not a reusable primitive — our planned APPROACH (block 5.1, recomputed
  every tick) is the same core idea done as a real, testable servo. They have **no metric depth**
  at all (bbox position only, no distance) and throttle perception with a blunt frame-skip
  counter, vs. our measured two-rate seg/depth threads with an ORT thread cap — our extra
  perception complexity (4.1/4.2) buys something they don't have, not gold-plating.
- **Cheap-to-borrow:** their bearing formula `bearing_offset = (bbox_cx - 0.5) * FOV_rad` is the
  same math our planned APPROACH yaw-center servo (5.1.2) needs — cheap sanity-check reference for
  when we implement it. Their second LLM-wake trigger ("detection class set changed since last
  prompt", in addition to a fixed timer) is a cheap complementary condition to our
  queue-empty/reassess wake (3.1) — LATER, once perception is actually feeding the prompt and we
  can tell if queue-empty alone is reactive enough.
- **Simplify NOW:** none found. Their system reads simpler mainly because it *drops* capability we
  specifically need (metric depth for the emergency boundary, deterministic-math servo) — not a
  legitimate simplification to borrow; our current design isn't over-built relative to a working
  reference.
- **Simplify LATER (only after the system flies and is tested):** (1) a fixed-interval LLM
  re-plan as a fallback wake condition alongside the event-driven one, cheap insurance against a
  stuck queue-empty/reassess state; (2) detection-class-change as a second prompt-retrigger
  condition (see above).
- Guardrail respected: idea-harvest only, no scope change to 4.2 or block 5.

## System-prompt: APPROACH entry + EXECUTION MODEL text (2026-08-06, ROADMAP 3.6)

- **APPROACH command scaffolding (spec `2026-08-05-visual-servoing-approach-design.md` §4c/§8):**
  added `CommandID::APPROACH=9`, `struct CmdApproach{target, speed}`, its `GenericCommand` ctor,
  and a `translateToBaseCommands` case parsing `{"action":"approach", "target_object", "speed"}`.
  **No control-law branch** — `activateTask`'s `default:` case auto-completes it immediately,
  exactly like `ORBIT`/`SEARCH`/`ROTATE`/`REASSESS` already do today (none of those have a real
  branch either; only TAKEOFF/LAND/GO do). The actual yaw-center + range-decel servo is block
  5.1 (`detectionByLabel`, per-tick recompute), explicitly not this task — spec §8 says so
  directly ("the servo does not depend on this").
- **Prompt entry:** added the `approach` block to `kSystemPrompt` (`llm_base.hpp`), alongside
  `orbit`/`search`, matching their `target_object` style.
- **Interrupt text replaced:** swapped the old ad-hoc interrupt paragraph for the
  "EXECUTION MODEL" text drafted in `ARCHITECTURE.md` Appendix A (QUEUE EMPTY / YOUR re-assess /
  INTERRUPT). **Caveat surfaced, not hidden:** INTERRUPT describes the depth-triggered reflexive
  hold-clearance from ARCH §5.1 — that control logic (ROADMAP 1.5) is not built yet, only
  QUEUE EMPTY and re-assess are real today. Same already-established pattern as the unwired
  `orbit`/`search`/`rotate` prompt entries; flagged in ARCHITECTURE.md's Appendix A status line
  so it is not mistaken for a shipped guarantee.

