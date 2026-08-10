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
  `fmu_node.cpp`: `--canned-cross` / `--canned-speed`; `scripts/test/{forward,cross,speed}/run.sh`):
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
- **`scripts/test/vlm/run.sh`** mode: launches the Qwen3-VL llama-server
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
  `docs/tasks_todo/2026-08-06-build-yolo-vision-generic-backend-refactor.md` for a planned CRTP
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

## APPROACH visual servo implemented (2026-08-06, ROADMAP 5.1)

- **detectionByLabel** (`source/llm_to_action/perception/detection_query.hpp`, new folder,
  header-only -- mirrors `frame/`, no CMakeLists of its own): ROS-free pinhole back-projection,
  unit-tested without YOLO (`fmu/test/detection_query_test.cpp`, built from `fmu/CMakeLists.txt`
  alongside `plan_parse_test` -- **not** a new per-folder CMake project; first pass wrongly gave
  `perception/` its own `project()`+CMakeLists, caught and fixed). Reconciled against block 4.2:
  consumes the real vendored `vision/perception_types.hpp` directly, not the stub the spec was
  written against.
- **Camera intrinsics are real, not guessed, and defined exactly once:** derived from
  PX4-Autopilot's own `Tools/simulation/gz/models/gimbal/model.sdf` (`horizontal_fov=2.0`,
  1280x720) -- the exact sim camera the FMU flies against, addressing spec §9 R4 directly. The
  concrete constant (`kGzX500GimbalCam`) lives once in `detection_query.hpp`; `fmu_node_base.hpp`
  (`kApproachCamera`) and the unit test both reference it instead of repeating the literal
  numbers -- first pass duplicated the literal in two places, caught and fixed.
- **Control branch** (`fmu_node.hpp` `controlLoop`): per-tick yaw-center + range-decel + lateral
  damping, per spec §5/§9 R1. No stored world point (spec D4) -- every tick re-reads
  `PerceptionRuntime::snapshot()` via `detectionByLabel`.
- **Canned rig deviation:** spec §7 left the "operator kills the detection mid-approach" step
  interactive/unspecified. Implemented deterministically instead --
  `kCannedApproachRigKillAfterMs` stops the synthetic detection a fixed time after activation --
  since this system has no mid-flight interactive control channel. `PerceptionRuntime` gained
  `injectSynthetic()` for this, reusing the existing atomic-publish path; safe because the real
  engines only publish when `ok()`, so a canned run (no models mounted) never races it.
- **Build verification:** `GROUNDSTATION_BUILD_TESTS` is `OFF` by default in `build.sh`; flipped
  to `ON` temporarily via `build.sh` (not a raw `cmake` cache edit) to run
  `detection_query_test`/`plan_parse_test`/`frame_convert_test` (all pass), then reverted --
  `git diff build.sh` is clean. Logged the cost: verifying one new test forced a full ~1min
  all-targets rebuild (ROADMAP 9.10 -- build.sh has no per-target selection yet, noted not
  implemented).
- **Still open:** SITL re-gate (`./scripts/simenv_llm.sh approach`) is a human check, same as
  the ENU convention's SITL re-gate before it -- not run by this session. Block 5.2 (live-YOLO
  GO) reuses `detectionByLabel` next.

## APPROACH SITL-verified: two stale-environment bugs, one design bug, one pre-existing finding (2026-08-06)

First `./scripts/simenv_llm.sh approach` runs surfaced problems -- none in the servo math itself:

- **Stale binary:** `simenv_llm.sh` launched `llm_to_action_fmu` (no backend suffix), a leftover
  from before the per-backend rename to `llm_to_action_fmu_<backend>`. Confirmed by the running
  binary's own log format string missing the `approach=%d` field entirely -- it predated
  CommandID::APPROACH existing at all. Fixed: launch `llm_to_action_fmu_px4`.
- **Missing onnxruntime lib:** binary loads `libonnxruntime.so.1` from
  `build/release/shared/_deps/onnxruntime/.../lib`, never installed into the bin dir alongside
  everything else. Fixed: added that dir to the FMU pane's `LD_LIBRARY_PATH` in `simenv_llm.sh`.
  Verified clean with `ldd` before re-running.
- **Canned target could land behind the camera:** `kCannedApproachTargetEnu` was a fixed
  absolute ENU point ("3m north"), but SITL spawn heading isn't North (~-0.3 rad observed) --
  so the target sat behind the drone at APPROACH activation on the very first tick, and the
  "not found, no prior aim" path correctly FAILed instantly. Every downstream piece
  (behind-camera check, detectionByLabel, instant-FAIL-with-no-coast-on-first-tick) was working
  correctly on a wrong input. Fixed: target is now computed once at activation, body-relative
  to wherever the drone is actually facing at that moment (`fmu_node.hpp` activateTask,
  same `flu_to_enu(relFlu, od.yaw)` pattern GO already uses) --
  `kCannedApproachTargetFwdM`/`kCannedApproachTargetUpM` replace the fixed ENU constant.
- **Both control paths now confirmed in SITL:** first real run (6s kill timer) exercised the
  lost-target coast-then-FAIL path -- target was still 0.98m out (standoff 0.5m) when the rig's
  timer cut the detection, coasted, FAILed correctly. User then raised
  `kCannedApproachRigKillAfterMs` to 15s to also see the happy path: `APPROACH reached
  target=canned_target range=0.50` -> `approach_ok`, range converged 3.16m -> 0.50m monotonically
  the whole way. Both paths verified working from real SITL flight, not just unit tests.
- **Pre-existing finding, logged not fixed (ROADMAP 9.11):** LAND has no flare -- constant
  `kLandDescendVelEnu` (-0.5 m/s) all the way to ground contact. Odometry shows a velocity/yaw
  spike right after `force_disarm` in both approach runs (FAIL-path landing and approach_ok-path
  landing alike), consistent with a hard-ish touchdown. Not caused by APPROACH; out of this
  block's scope.


## Real perception + live VLM, end-to-end: worked, but hit the target (2026-08-06)

Same-day follow-up: pushed past the canned rig to real seg/depth ONNX models and a real
VLM (Qwen3-VL-2B) planning live off actual detections. Target: a hatchback gz model
vendored from github.com/monemati/PX4-ROS2-Gazebo-YOLOv8 (SITL world had no usable
object -- the Fuel "Rubicon" asset is a house, not a vehicle, despite the name).

- **4.2's model paths were wrong, silently, since it was written:** `kVisionSegModelPath`/
  `kVisionDepthModelPath` pointed at `/root/models/vision/*.onnx`; real files landed at
  `/root/models/vision/vision/*.onnx` (nested) once actually mounted today. Real inference
  had never run before today -- not caught earlier because models didn't exist yet to catch
  it against. Fixed: paths corrected, switched to the `-384` input-res variant (matches the
  perf number already recorded in ROADMAP 4.1.8).
- **Clock-epoch mismatch:** `FlightManagementUnitNode::nowUs()` used the ROS clock;
  `PerceptionRuntime::nowUs()` used `steady_clock`. Diffing the two for a detection's "age"
  produced garbage (49.6 real hours between two ticks 50ms apart) -- APPROACH instantly
  treated every real detection as infinitely stale. Fixed: both now `steady_clock`.
- **No freshness gate:** APPROACH only checked total staleness (3s) before giving up, with
  no check that a detection was fresh enough to trust for closing speed. Real depth froze
  for 1s+ stretches under this CPU's load; the servo kept commanding a range-based speed off
  a frozen number. Added `kApproachFreshUs` (200ms) -- anything staler falls back to slow
  coast instead of confidently closing distance on old data.
- **Label drift:** the real model reclassified the same object mid-approach ("car" -> "boat")
  at closer range/angle -- a real model-accuracy limitation on this synthetic mesh, not a
  logic bug. Added a narrow fallback: if the exact label misses but exactly one detection is
  in frame, track it anyway (nothing else it could be). Does not touch `detectionByLabel`'s
  tested exact-match behavior.
- **Standoff tuned twice for real depth noise:** 0.5m (canned-rig value) -> 1.0m -> 2.0m.
  Real range readings routinely jittered 3-7m tick to tick even when "fresh." First hit
  happened with 1.0m standoff: range hovered right at the threshold without a clean
  below-standoff reading, so the drone sat close-range yaw-chasing (errX ~0.3, yawRate
  ~-0.3 rad/s) instead of committing to stop, and clipped the target.
- **Second collision, this time with a live VLM plan (slower cruise, VLM chose its own
  `speed`):** confirmed by raw odometry, not inferred -- yawrate spiked to 6.9 rad/s
  (commanded ~-0.10), vertical velocity hit -1.75 m/s, altitude collapsed 0.99m -> 0.02m in
  ~1s, all in the same tick APPROACH read `range=1.83` and declared `approach_ok`. That
  reading was taken during/after the impact; the code has no way to know the difference.
  **Logged, not fixed (ROADMAP 6.4):** APPROACH's "reached" check has no motion sanity
  check at all -- it trusts a single range reading regardless of what the vehicle is
  actually doing that instant. This is the real gap, not a tuning number.

## Tello real-world bring-up: telemetry was 100% dead, ufw is broken in this container (2026-08-06)

First real-hardware flight. State telemetry (UDP 8890, unsolicited inbound) was silently
dropped by the host firewall's default-deny INPUT policy -- confirmed via `tcpdump` (585 real
Tello state packets on the wire, zero reaching the app). The command channel (UDP 8889) worked
only because our own outbound sends create a conntrack ESTABLISHED entry; state traffic has no
such flow. `ufw allow 8890/udp` reported success and `ufw status verbose` showed it active, but
the ACCEPT never actually landed in the kernel's `ufw-user-input` chain -- ufw's apply
mechanism is broken in this container image (worse after a mid-session ufw uninstall/reinstall
desynced its rule files from live netfilter). **Fixed: bypass ufw, insert raw `iptables` rules
directly in the container startup** (`devenv.sh` -- container runs `--net=host --privileged`,
so this edits the real host tables). Full detail: `docs/ARCHITECTURE.md` §17,
`docs/tasks_closed/2026-08-06-tello-real-world-bringup-telemetry-hardening.md`.

Also resolved this session: camera stream was never actually broken (early misread -- H264
`no frame!` errors are normal before the first keyframe, then stop); confirmed the physical
drone is a standard Tello on **SDK 1.3, not an EDU** (`sn?`/`sdk?` -> `unknown command`), so no
firmware flash is possible or needed (`docs/tello_backend_notes.md` updated, was mislabeled
SDK 2.0). ROADMAP 2.3 updated: telemetry/odometry/camera now verified live on real hardware;
2.3.4/2.3.5/2.3.6 added for wind-sensitivity speed control, active stability correction, and
latency benchmarking -- all carried forward, none implemented yet.

## docs/ lifecycle re-triage: two "active" docs were already done (2026-08-06)

Renamed the task buckets (`tasks_todo/active/closed` -> `scheduled/active/closed`) and
re-checked every doc's bucket against *current* truth instead of trusting each doc's own
frozen text. Found: `2026-08-04-px4-backend-extraction.md` (plan) and
`2026-08-05-px4-backend-extraction.md` (handoff) both still said "Task 4 (ENU seam) NOT
started" -- true when written, but `ARCHITECTURE.md` §15's own Implementation Status already
listed "the ENU convention (Task 4)" as committed, and the GO-spiral fix the same handoffs
call open is confirmed fixed in the sibling `go-controller-visual-servo.md` handoff. Moved
both to `closed/`. Also closed: `fmu-perception-integration.md` (block 4.2, done well before
today, then further exercised by today's real-perception/VLM work) and the docs-reorg ticket
itself (its two placement caveats + the SDK-1.3 fold-in are resolved). Lesson: a task doc's
bucket should track ROADMAP/ARCHITECTURE, not get frozen at whatever the doc said the day it
was written -- cross-check both before trusting one in isolation.

## Session note (2026-08-07)

- Perception seg/depth benchmarks re-run and reconciled in `/root/BUILD_YOLO` (separate,
  intentionally modularized repo). Full numbers, methodology, and run instructions live in
  `BUILD_YOLO/README.md`'s `## Benchmarks` section -- not duplicated here. `ROADMAP.md`'s
  perception status updated to match: still misses both targets. `perception_test`'s run friction
  was root-caused (a global RPATH setting silently ignored the per-target fix; onnxruntime's .so
  needed copying next to the binary, not just pointing at) and fixed via a plain `./test.sh` in
  BUILD_YOLO -- mechanism not documented here, see that repo.

## SITL test suite green + runtime-constants gap (2026-08-08)
- All 15 `scripts/test/<feature>/` runs pass in PX4 Gazebo SITL (operator-run, 2026-08-08). The full
  per-test matrix (with Auto vs Milestone type) lives in `docs/ROADMAP.md` -> `## SITL test matrix`.
  Per-run pane captures (`captured_*.txt`) are git-ignored -- each `filter.sh` regenerates them.
- **Runtime-constants gap flagged.** Every tuning value (takeoff/flare, battery thresholds, manual
  velocity, GO/ROTATE/APPROACH gains) is a compile-time `constexpr` in `fmu_node_base.hpp`. SITL and
  the real Tello need different values, and one binary can't serve both without a recompile. They
  must move to a runtime, drone-selected config before real-Tello flight. Spec:
  `docs/scheduled/2026-08-08-runtime-drone-config-constants.md`.

## Battery failsafe + manual operator override + queue backpressure (Spec 3, 2026-08-07)

- **Real PX4 battery.** `px4_backend` now subscribes `/fmu/out/battery_status_v1`
  (`px4_msgs::msg::BatteryStatus`) and publishes `int(remaining*100)`; disconnected/NaN maps to
  `kBatteryReadingUnknown = -1` (new, in `generic_backend_types.hpp`). Was a hard `-1` stub.
- **Failsafe supervisor** (`batteryFailsafeTick`, control thread, before dispatch): `-1` skipped
  (no false alarm; a real 0% still fires). `<=kBatteryReturnPct (20)` latches return-to-origin —
  a synthetic GO to ENU origin reusing the GO law + `enu_to_flu`, then the dispatch site lands.
  `<=kBatteryLandPct (10)` latches land-in-place. Latched RTH is not overridden by the 10% rule.
  **No mid-air force_disarm** (only at ground contact). The smart version (energy models, 10–15%
  window, terrain flat-site) is deferred: `docs/scheduled/2026-08-07-battery-rth-energy-terrain-subsystem.md`.
- **Manual operator override (ARCH 11):** Bool `/fmu/in/override` toggles an atomic; while engaged,
  raw keys from `/keyboard/in/raw` map to a constant body-FLU velocity (`kManualTeleopVelCmS`,
  TUNE) streamed as ENU. Handback abandons the stale task and forces a fresh VLM re-plan (it lost
  positional context while disengaged — true context recovery is future fusion/map work). Failsafe
  outranks manual. Also fixed a latent bug: `keyboard_node` never constructed its publisher.
- **SPSC backpressure (1.4):** producer switched from `enqueue` (unbounded growth) to `try_enqueue`
  against the fixed cap (60) — reject-newest, every drop logged (`m_taskDropCount`). Draining on the
  control thread is consumer-side only; the control thread never enqueues (keeps SPSC valid).
- Thresholds/manual speed/queue policy are SITL-tunable; `scripts/test/battery/run.sh`
  drains PX4 SITL to exercise the failsafe without the `pxh>` console.


## Test harness migration (2026-08-07)
- SITL tests moved to per-feature folders `scripts/test/<feature>/`: `run.sh` sources the shared
  `scripts/test/lib/sim_core.sh` engine; a self-contained `filter.sh` captures panes + asserts/greps.
- `scripts/simenv_llm.sh` (monolithic PLAN_MODE launcher) and `scripts/debug_sim_logs.sh` (later
  renamed `test_filter_rotate_land_logs.sh`) were REMOVED — every mode is now a folder. Add a feature
  = copy a folder + set knobs in `run.sh`; no launch code to duplicate.

- **Spec-3 HITL fix (2026-08-08):** battery RTH could fire *during* TAKEOFF (weak battery never hit `kTakeoffTargetAltEnu`). `returnToOrigin()` queued a GO but the control loop stayed in the TAKEOFF branch (which streams climb + ignores active tasks), so the drone hung with motors armed and never disarmed. Fix: `returnToOrigin()` forces `FlightState::FLIGHT` before the GO, so it executes, completes at origin, then hands off to LANDING+`force_disarm`. Also: flood test asserts the real moodycamel bound (cap 60 -> 63 usable slots), not a magic 60/40 split.

- **Spec-3 airborne backpressure test (2026-08-08):** `--canned-cross-flood` flies the canned cross, then ~5s after reaching FLIGHT injects a 100-action flood from a producer-role `std::async` (mirrors the VLM path) so SPSC holds (control thread only launches it). Proves an in-air command storm is absorbed: queue bounded (63 usable), excess dropped, and the live maneuver is not hijacked (FIFO queues the storm behind the running plan). Test: `scripts/test/flood-airborne/`. Also: battery `SIM_BAT_DRAIN` is seconds-to-empty-from-arm, not %/s (2.0 killed it on the pad) -> retuned to 45.

## Vision model path + fail-loud on load (2026-08-08)
- **Bug:** `kVisionSegModelPath`/`kVisionDepthModelPath` (fmu_node_base.hpp) pointed at
  `/root/models/vision/vision/...` — a **doubled `vision/` dir**. The models actually live at
  `/root/models/vision/...`. Wrong path -> `YoloSegEngine::ok()==false` -> the seg loop emitted
  **zero detections silently** -> every real APPROACH (`approach-real`, `vlm`) FAILed ~50ms in.
  Cost hours because nothing warned. Fixed both paths.
- **Guard added:** `PerceptionRuntime::ready()` (`m_seg.ok() && m_depth.ok()`) is checked at FMU
  startup; a failed model load now logs `RCLCPP_FATAL` then `std::abort()` (no exception, per the
  no-exceptions rule) instead of flying blind. A mispathed/missing model can never silently pass again.


- **Spec-3 battery behaviour tests (2026-08-08):** the cross+drain `battery/` test can't show real RTH (drone sits at origin) or land-in-place (gradual drain latches 20%-RTH before 10% can fire). Added a test-only battery override in the FMU (`m_batteryForce`, -2=off) fired ~15s into FLIGHT: `--canned-battery-rth` flies ~8m out then forces 18% -> RTH all the way home; `--canned-battery-landnow` forces a discrete 8% -> land-in-place far from home. Filters assert via posENU distance (flew out >3m; RTH ends <1.5m from origin, land-now ends >2m). `battery/` retained as the real-PX4-bridge smoke test. Tests: `scripts/test/battery{,-rth,-landnow}/`.

- **Spec-3 land-vs-RTH latch fix (2026-08-08):** `batteryFailsafeTick` short-circuited only on `mb_batteryReturn`, so after a <=10% land-in-place latched (`mb_batteryLand`), the next tick's <=20% branch still fired RETURN-to-origin and overrode it; the RTH->LANDING handoff (`mb_batteryReturn && !mb_batteryLand`) was then skipped -> drone flew home and hovered, never disarmed. Fix: guard is now `if (mb_batteryReturn || mb_batteryLand) return false` — once EITHER latches we're committed to a landing. Caught by scripts/test/battery-landnow.

- **Spec-3 real-drain battery test fix (2026-08-08):** the old cross+drain `battery/` test was invalid -- (a) cross returned to origin so RTH was a no-op, and (b) PX4's OWN low-battery failsafe entered Hold at 'Critical battery', froze our LANDING descent at ~0.34m and dropped the drone (PX4, not us, ended the flight). Rebuilt as a real-drain PATROL: `--canned-patrol` flies a box 6-10m out; `COM_LOW_BAT_ACT=0` disables PX4's action so OUR FMU is the sole authority; RTH speed raised to 0.8 m/s (returnToOrigin) so it gets home before the pack empties. Filter asserts flew-out + our-RTH + home + disarm + NO PX4 Hold. `scripts/test/battery/`.

- **Spec-3 battery test polish (2026-08-08):** (1) land-in-place now drains the task queue so the outbound plan's leftover `land` can't re-run after touchdown (was double-disarming). (2) battery behaviour tests moved to a new flat empty world `dependencies/empty.sdf` -- in `default_car` the car sits at world 6,7, right on the +8m outbound path, and land-in-place (no obstacle awareness -- deferred subsystem) dropped onto it. (3) battery filters infer 'airborne' from maxDist>3m, since a ~2.5min real-drain run overflows tmux's 2000-line pane scrollback and evicts the early TAKEOFF->FLIGHT line (false-failed an otherwise-perfect run).
- **Spec-3 randomized real drain (2026-08-08):** fixed `SIM_BAT_DRAIN` made the real-drain `battery/`
  failsafe fire at the SAME patrol spot every run. `run.sh` now randomizes it per run
  (`140 + RANDOM % 61` = 140..200 s-to-empty, `${VAR:-...}` so an exported value pins it for repro),
  so the 20% crossing -- and the RTH break-off point -- lands at a different spot each run.
- **Spec-3 COMPLETE + SITL-verified (2026-08-08):** ROADMAP 6.2 (battery/failsafe supervisor +
  reversible user override) and 1.4 (SPSC backpressure) are done and verified end-to-end across a
  6-test suite (`scripts/test/{battery,battery-rth,battery-landnow,flood,flood-airborne,override}/`),
  all PASS. Final laws: `≤20% -> RTH then land`, `≤10% -> land-in-place` (both latched, either latch
  commits to a landing); bounded `try_enqueue` reject-newest; failsafe > manual override > autonomy.
  Full narrative + the 8 HITL defect fixes: bottom of the spec-3 file. Uncommitted (manager review).

## APPROACH servo: brake on odometry, not depth (2026-08-08)
- **Problem:** the depth range to the target is too noisy near it to brake on -- in SITL the same
  parked car read 1.6-6.5 m tick to tick. The old servo set forward speed from `(range - standoff)`,
  so every noisy-high read re-accelerated the drone. It crept forward until a fluke low read tripped
  `reached`, by which point it had hit the car ("push, halt, push, crash").
- **Fix (fmu_node.hpp):** once a stable early range estimate exists (>= median-window samples, target
  still far), latch the drone position + a fixed travel budget = `R0 - standoff`. From then on the stop
  point is dead-reckoned from odometry travel, which is exact, so a noisy high depth read can no longer
  re-accelerate into the target. Depth is kept only as a backstop (median `range < standoff` also
  stops). Whichever fires first wins, so both failure directions are safe: depth-high-all-the-way ->
  travel budget stops you (no overshoot); depth-low fluke -> backstop stops you early (short, never
  late). Lost-target handling is travel-aware: complete by travel if past the stop point, HOLD if near
  it, coast only while still far.
- **Standoff (fmu_node_base.hpp):** `kApproachStandoffM` 2.0 -> 3.0 m. Depth ranges to the target's
  centroid; a closer-protruding part (car mid-back) sat inside 2 m and got clipped. 3 m clears it.
- **Observed:** in practice the depth backstop trips before the travel budget is consumed (median dips
  under standoff first), so the budget acts as the failsafe. The stop is conservative (can end a bit
  far); tightening it needs better depth, not servo logic. Adequate + safe for the POC.
- Removed the temporary `[PERCEPTION_DEBUG]` stderr logging from perception_runtime.hpp (ship-clean).


## 2026-08-09 -- APPROACH close-out (canned tests + lost-target completion)

- **Canned/synthetic APPROACH tests run in the `empty` world, not `default_car`.** The canned rig
  injects a fully synthetic detection; a real car in the world was still seen by real perception, and
  its looming backstop (fill > 40%) correctly tripped at ~2.8 m -- before the synthetic dead-reckon
  stop could complete. A synthetic-detection test must have no real obstacle to fight. `approach` and
  `approach-impact` now both run `empty`. This is test isolation, not a control change.
- **APPROACH finishes on dead-reckon when the target is lost inside the hold margin.** The canned rig
  drops the phantom a fraction of a metre short of the stop (projection artifact at close range). The
  old code entered a HOLD (zero velocity) and waited for a re-lock; on a permanent loss that deadlocked
  at rem~0.2 m until the coast window expired -> approach_lost_failed. Fix: once latched and within
  kApproachCoastHoldMarginM of the dead-reckoned stop, complete on odometry (approach_impact if motion
  is off-nominal, else approach_ok) instead of holding. Stopping up to the margin short of standoff is
  safe -- it leaves the drone farther from the target, never closer, and never coasts blind. Touches
  the spec-1 6.4 APPROACH branch in fmu_node.hpp.


## 2026-08-09 -- A1 headless SITL runner: two design decisions worth recording

- **Headless completion is judged from real PX4 topics, not FMU log text.** `wait_for_ground_truth.sh`
  polls `/fmu/out/vehicle_status_v4` (arming_state) and `/fmu/out/vehicle_land_detected` (landed) to
  decide a canned run is over -- never by grepping the FMU's own printed "reached"/"complete" claims.
  Reason: the FMU's self-reported state has been wrong before (ROADMAP 6.4, the impact-frame false
  approach_ok). Cross-checking the FMU's *claims* against this same ground truth (not just using it for
  a stop signal) is a deliberate fast-follow, not done in A1.
- **`filter.sh` keeps its `OUT` variable after switching from tmux capture to the log file.** All 20
  filters run under `set -u` and reference `$OUT` several times downstream (the grep/awk digest logic);
  dropping the assignment aborts every scenario with `OUT: unbound variable`. Where `LOG_FILE` and `OUT`
  resolve to the same path (14 of the 20 scenarios use the shared default filename), the copy step is
  skipped via a same-inode check rather than run unconditionally -- `cp x x` errors, and 6 of those 20
  filters run under `set -e` so that error would otherwise be fatal.


## 2026-08-09 -- B1 stella_vslam comparator: drift alone cannot certify tracking

- **Monocular SLAM has no metric scale or fixed origin** -- comparing its trajectory against PX4 EKF2
  ground truth needs a Umeyama similarity fit (rotation + scale + translation) first; a raw position
  subtraction is meaningless.
- **A collapsed alignment makes raw drift look deceptively small.** First version of the comparator used
  a path-length-ratio check; synthetic testing showed it read 6.68 on a known-good track (30 Hz
  per-sample jitter dominates arc length at that rate) -- not usable as a signal. Replaced with an RMS
  spread-ratio metric. Validated against injected noise: a fit that collapses onto its centroid (total
  tracking failure) reports `drift_m` as small as 0.55 m, but `spread_ratio` correctly drops to ~0.22 and
  flags `collapsed-fit`. Without the second metric, this would rubber-stamp a non-tracking run as PASS.
  `scripts/test/slam/compare_ground_truth.py` reports both; treat `drift_m` as meaningless whenever
  `spread_ratio` is near zero.


## 2026-08-09 -- B1 stella_vslam live SITL verification + OpenMP fix

Why stella_vslam at all: it was picked over ORB-SLAM3 for being the actively maintained fork (ORB-SLAM3
upstream has seen little activity in years; stella_vslam absorbed dependency/tooling modernization
stella_vslam never got). First live SITL run against real Gazebo camera frames (not synthetic noise)
came back FAIL: tracking rate stayed healthy (11-18 Hz, never near 0, so the node was live and
publishing) but `spread_ratio` oscillated between a healthy ~0.5-0.6 and a collapsed ~0.1-0.4, landing
on a collapsed window at verdict time.

- **Root cause: stella_vslam's own per-frame feature extraction was compiled single-threaded.** Upstream
  `find_package(OpenMP REQUIRED)` runs unconditionally in stella_vslam's CMake, but the actual
  `#pragma omp parallel for` loops in `orb_extractor.cc` (FAST keypoint detection across pyramid levels +
  ORB descriptor computation -- the exact per-frame hot path) are gated behind a `USE_OPENMP` option that
  **defaults OFF**. `cmake/FetchStellaSLAM.cmake` never passed `-DUSE_OPENMP=ON`, so every build up to
  this point extracted features on one core while competing against Gazebo/PX4/the FMU's own real YOLO+
  depth perception threads for that one core.
- **Fix: added `-DUSE_OPENMP=ON` to `STELLA_OPTIMIZED_COMPILER_FEATURE_FLAGS`** in
  `cmake/FetchStellaSLAM.cmake`. Confirmed via `CMakeCache.txt` (`USE_OPENMP:BOOL=ON` vs the old build's
  `OFF`), not just assumed from the flag being passed.
- **Verified with repeated live SITL trials, not one run.** Full stack each time: PX4 SITL + Gazebo,
  the FMU running a canned (non-VLM) plan with its real `PerceptionRuntime` (YOLO seg + depth, ONNX)
  running throughout -- `PerceptionRuntime::start()` is unconditional in the FMU constructor, so this
  load is present regardless of canned vs. VLM-driven flight. VLM/`llama-server` itself was not running
  (`LAUNCH_VLM` unset). Baseline (OpenMP off, cross maneuver): peak rate ~17 Hz, `spread_ratio` 0.48-0.62
  (straddling the 0.5 pass line), 1 FAIL of 3. OpenMP on, same maneuver: peak rate 25-27 Hz (camera is
  30 Hz), `spread_ratio` 0.60-0.86, 3 PASS of 3 (4th trial pass-quality but its log file was corrupted by
  a harness race, excluded from the count rather than fudged in).
- **A side test refuted an earlier hypothesis.** Guessed the cross maneuver's direction reversals were
  hurting tracking; tested a single smooth forward hop instead (`--canned`, no reversals) and it failed
  *more* consistently (`spread_ratio` 0.40-0.45, 3 FAIL of 3) than the cross. Reversals are not the
  problem -- a short hop just doesn't give the fit enough time/distance to converge before landing cuts
  it off.
- **Not yet tested: with the VLM (`llama-server`/Qwen3-VL) running concurrently.** All trials above ran
  with `LAUNCH_VLM=0`; the VLM is a real GPU/CPU consumer that would compete with stella_vslam's now
  multi-threaded extraction for cores. Worth a follow-up run with `LAUNCH_VLM=1` before calling this
  closed for the full stack. Also SITL-only: Gazebo's camera is a clean, distortion-free render, easier
  to track than real Tello video (compression, motion blur, rolling shutter, real lens distortion) --
  the numbers above should not be read as a real-hardware prediction.
- Full trial-by-trial numbers, verdict lines, and the harness script used live in this session's
  transcript; ask for the raw log files if they're needed again -- not duplicated here.

**Follow-up (same day): 3 more trials with `LAUNCH_VLM=1`.** Closes the gap flagged above. Same
cross maneuver, same OpenMP build, `llama-server` (Qwen3-VL-2B, Vulkan GPU offload,
`--threads 1`) genuinely running -- confirmed by process check mid-flight, not assumed. One
caveat worth stating plainly: `--canned-cross` never enters the VLM replanning loop
(`m_missionActive` is forced false for any canned run), so this tests "VLM resident in GPU memory
and idling" contention, not "VLM actively answering queries" contention -- the harder test would
need a real (non-canned) VLM-driven flight.

- **Result: 2 PASS (spread_ratio 0.67, 0.67), 1 FAIL (spread_ratio 0.34).** `rate` (24.6-25.0 Hz
  peak) and `tracking_frac` (1.00, all three) were unaffected -- essentially identical to the
  VLM-off OpenMP numbers above. The one failure was a scale/alignment event (`scale` swung to
  3.657 vs 0.497/0.937 on the passing runs), not a throughput drop, and run-to-run
  `spread_ratio` variance this size was already present in the VLM-off data before any VLM was
  involved. Read: an idling VLM does not appear to measurably hurt SLAM throughput; whether it
  raises the alignment-failure rate specifically needs a larger sample than n=3 to say with
  confidence, and the harder question (VLM under real, actively-queried load) is still open.



## Per-backend build trees + dependency prune (2026-08-09)

- `build.sh` gained a 4th positional arg: `build.sh <cfg> <lib> <backend> <action>`, where
  `<backend>` is `px4`, `tello`, or `all`. Output moved from `build/<cfg>/<lib>/` to
  `build/<cfg>/<lib>/<backend>/` -- the SITL px4 tree is now `build/release/shared/px4`, the
  real-drone tree is `build/release/shared/tello`.
- Only the selected backend's library builds now. The subdirs `px4_backend`, `offboard_ctrl`,
  and `gstreamer_gz_udp_tx` are gated to px4/all; `tello_backend` to tello/all. A Tello build
  therefore never configures `gz-sim8`/`gz-plugin2` (the Gazebo camera plugin) and never needs
  `px4_msgs` (the px4_ws overlay). Confirmed: the tello CMakeCache has zero `gz-sim8`/`px4_msgs`
  entries, and its configure dropped from 348s to 178s.
- `px4_msgs` was linked into EVERY node by the shared `define_ros2_node` helper, though only
  `offboard_ctrl` uses it. Removed from the helper; re-added to `offboard_ctrl` alone.
  `find_package(px4_msgs)` is now guarded by the px4/all backend condition.
- `frame_convert.hpp` and `generic_backend_types.hpp` are already px4_msgs-free (an earlier grep
  false-matched the word inside a comment), so no FMU/backend header changes were needed.
- `gstreamer_rx` no longer links `CameraPlugin::GazeboGstCameraLibrary`; it reads the shared UDP
  port constant from `gstreamer_gz_udp_tx/gazebo_cam_plugin_base.hpp` (a gz-free header) through the
  `util_base_header` module include root, so gating the Gazebo plugin does not break the receiver.
- `build.ps1` was given the same 4th `-Backend` arg (px4|tello|all) and the same nested
  `build/<cfg>/<lib>/<backend>/` layout, so Windows/Linux build entry points stay in parity
  (closes ROADMAP 9.6).
- Consequence: the old flat `build/release/shared` px4 tree and the earlier `build/release/tello`
  are now stale layout; both need a fresh configure under the new nested paths.

## VLM plan-execution bugs found during live (non-canned) flight testing (2026-08-09)

First real, non-canned, VLM-driven live SITL flight of the day (`slam/run.sh`, `LAUNCH_VLM=1`,
`FMU_CANNED_FLAG=none`, real Qwen3-VL planning throughout) surfaced three real bugs that no canned
scenario could have caught, because canned scenarios never enter the VLM replanning loop at all.

- **Plan-parsing bug, fixed: a valid plan could be silently discarded and the drone left hovering
  forever with no path to LAND.** `extractJsonArray()` (`source/llm_to_action/fmu/plan_parse.hpp`)
  used to slice from the first `[` to the last `]` in the whole VLM response. Qwen3-VL routinely
  describes what it sees (pixel coordinates, bounding boxes) in the prose around its JSON plan, and
  that prose often contains its own stray brackets. Any stray bracket before or after the real plan
  made the whole slice invalid JSON, `nlohmann::json::parse` rejected it, and the plan was dropped
  with no fallback -- observed live: 10 consecutive dropped plans after an ORBIT finished, ~2 minutes
  of hover, never reached LAND. Root cause found by dumping the tmux session's full pane scrollback
  (`tmux capture-pane` per pane) and reading the FMU pane's own `[FMU_NODE_DEBUG] plan JSON parse
  failed / not array.` warnings against the VLM pane's `llama-server` request log.
  Fix: try every `[` in the string in turn; for each, walk forward with quote-aware bracket-depth
  counting to find its own matching `]`, then check the resulting span actually parses as a JSON
  array; return the first one that does. Survives stray brackets on *either* side of the real plan,
  not just after it. 3 new regression cases added to `fmu/test/plan_parse_test.cpp` reproducing the
  leading-bracket, trailing-bracket, and both-sides shapes; all 11 assertions (8 original + 3 new)
  pass under a standalone `g++ -std=c++17` build (no ROS, no CMake reconfigure needed). A live
  re-run with the fix in place was still in progress as of this entry -- the unit tests prove the
  parser is now correct in isolation, not yet that a full live flight reaches LAND.

- **SEARCH gaps, one fixed, two deferred.** Live behavior (search sweeps a fixed lawnmower grid,
  6 lanes x 2m spacing, computed once at activation) was flagged as "a gimmick": (1) the swept area
  never adapts to the room's actual size/shape, (2) on failure the drone was simply left wherever the
  last lane ended, no return to its start point, (3) the only obstacle awareness during the sweep is
  the same reactive emergency-boundary check every command gets, not the reactive vs. gimmicky.
  Fixed (1.5 of the 3): on `search_exhausted`, the drone now flies back to `m_searchOriginPos` (the
  true SEARCH-activation pose -- note this is a *different* field from the pre-existing
  `m_searchStartPos`, which is reused/overwritten every lane transition for the sweep's own
  per-leg distance tracking, so it could not be reused for this) before completing the task, capped
  at `kSearchReturnTimeoutMs` (40s, sized for the worst-case ~13.4m diagonal at
  `kSearchSweepSpeedMps`) so a return leg cannot itself hang forever. `search_ok` (target found) is
  untouched -- returning to start after a *successful* search would fight whatever the VLM plans
  next (ORBIT/APPROACH on the now-visible target). Deferred: making the sweep grid size/shape
  actually aware of the room (gap 1) and giving it more than reactive-only obstacle handling during
  the sweep itself (part of gap 3) are real redesign work, scoped separately rather than rushed in.

- **Replanning-on-failure gap, fixed cheaply.** Asked directly: when a command like SEARCH or
  APPROACH fails (not a safety INTERRUPT, just "didn't achieve its goal"), does the VLM actually get
  told, and does anything push it to adapt instead of blindly continuing? Traced the whole path:
  `completeCurrent()` unconditionally sets `TaskState::FINISHED_SUCCESS` for every finished task --
  `TaskState::FINISHED_FAIL` is declared in the enum but never actually assigned anywhere, dead code.
  The free-text `status` string (e.g. `"search_exhausted"`, `"orbit_lost_failed"`, `"approach_lost"`)
  does reach the model verbatim, in `[EXECUTED COMMAND HISTORY]` inside `buildDynamicPrompt()`, and
  the queue-empty wake condition does re-invoke the VLM after any task ends, success or failure. But
  the system prompt (`fmu/llm_base.hpp`) never told the model that non-`_ok` statuses exist or mean
  anything -- it was entirely up to the base model to notice an odd-looking status string in a JSON
  history dump, unprompted, and choose to react. Fixed cheaply: added DECISION RULE 9, explicitly
  telling the model any non-`_ok` status is a failure, listing the concrete status shapes it can see,
  and instructing it to diagnose and adjust rather than silently continue the original plan. Did NOT
  touch `TaskState::FINISHED_FAIL` / add a code-level failure-streak escalation (mirroring the
  existing interrupt-storm escalation) -- that is a real option if rule 9 alone proves insufficient
  in practice, but is bigger, riskier surgery than today's window supports.

- **Harness bug found as a side effect: `FMU_OBJECTIVE` could not actually be overridden.**
  `scripts/test/slam/run.sh` set `FMU_OBJECTIVE="Fly a canned cross while SLAM tracks."` as a plain,
  unconditional assignment (not the `: "${VAR:=default}"` pattern `FMU_CANNED_FLAG` correctly uses),
  so any `FMU_OBJECTIVE=...` passed in from outside was silently thrown away every time, regardless
  of `FMU_CANNED_FLAG`. This means the "find the car, approach it, then land" live-VLM run earlier
  today was actually run under the harness's hardcoded default objective text, not the intended one
  -- the model's search-and-orbit behavior was it improvising against a mismatched/underspecified
  goal, not proof it can follow an arbitrary stated objective. Fixed with the same `:=` pattern
  `FMU_CANNED_FLAG` already uses. A clean re-run with the *actual* intended objective text is still
  needed before treating "can the VLM complete a stated real-world objective end to end" as verified.

## Live-flight verification chain, harness hardening, and the real root-cause fix (2026-08-09, cont.)

Continuing directly from the section above (plan-parsing bug, SEARCH gaps, replanning-on-failure gap,
`FMU_OBJECTIVE` override bug). This section covers what happened when actually re-verifying those
fixes live, and a better fix than the original one for the plan-parsing problem.

- **ROTATE hang, found live, root cause still unknown.** A verification flight got stuck commanding
  a yaw rotation that never happened: `ROTATE remainRad=1.560 cmdYawrate=0.800 measYaw=3.04
  measYawrate=0.00` repeated unchanged for 20+ minutes, altitude frozen low (~0.52-0.54m). `ROTATE`
  has no timeout in its completion predicate (unlike SEARCH/APPROACH), so once yaw genuinely stops
  responding it waits forever. The SLAM comparator's numbers degraded to `note=collapsed-fit` with
  `drift_max_m` over 21m during this -- a symptom of the frozen drone (nothing to fit a trajectory
  against), not a new SLAM regression. **Only observed once. Not investigated further, not fixed.**
  If this recurs (SITL or real hardware), land manually rather than waiting for it to resolve.

- **Harness bug, fixed: a timeout that doesn't kill anything is worse than no timeout.** The
  external watcher script used to verify live flights polled for a landing event for up to 400s,
  but if that expired without success it just silently gave up -- no kill, no signal, nothing --
  and fell through into a `wait` that then blocked indefinitely on the SITL script. This is why a
  hung run sat for 23 minutes with zero warning instead of failing loud at 7 minutes. Separately
  confirmed `scripts/test/lib/wait_for_ground_truth.sh` itself DOES correctly exit at its own stated
  timeout (reads clean) -- the hang was downstream of that, in `sim_core.sh`'s post-wait cleanup
  path, not fully root-caused. Fixed the verification harness with a real external `timeout
  --kill-after=Ns` wrapper plus unconditional cleanup (`pkill` by process name) that runs regardless
  of how the wrapped command exited. First hardened attempt used too tight a margin (480s outer vs.
  400s inner) and got killed by its own outer bound before the inner one had a fair chance --
  inconclusive, not a real data point. Second attempt (600s outer vs. 300s inner) gave real margin
  and worked correctly.

- **Real successful live-flight verification.** With the hardened harness: `takeoff` ->
  `search_ok` (target found in ~1.4s) -> `APPROACH` -> `approach_lost_failed` (target lost mid-
  flight, a genuine new failure, first live observation of this) -> model's next plan was `land` ->
  `land_ok`, mission halted cleanly (`Mission complete after LAND; VLM planning halted.`). One VLM
  response mid-flight still failed to parse (`plan JSON parse failed`), but this time the FMU
  recovered on its very next wake cycle instead of getting stuck -- proof the plan-parsing fix works
  under real conditions, not just in the unit test. SLAM stayed healthy throughout
  (`tracking_frac=1.00`, `note=ok`, no collapse). Open, unresolved question: after the APPROACH
  failure, the model chose to land rather than retry -- permitted under DECISION RULE 9 ("adjust or
  safe-land"), but whether it was genuine reasoning or just defaulting to the easy way out can't be
  confirmed, since the raw model text for that specific plan wasn't captured verbatim (fixed for
  future runs, see below).

- **Better fix for the plan-parsing problem: stop extracting, force the format instead.** Challenged
  directly on why `extractJsonArray` manually hunts for JSON instead of just using the JSON library
  already in the codebase -- correct challenge. `nlohmann::json::parse()` can't solve "find JSON
  embedded in a larger non-JSON string" because that's not a parsing problem, it's a text-search
  problem no JSON library attempts. But the real fix is removing the need for that search entirely:
  this exact vendored `llama-server` build (confirmed by reading `server-common.cpp`) supports
  OpenAI-style `response_format: {"type": "json_schema", ...}` on `/v1/chat/completions` --
  internally converted to a grammar that constrains what tokens the model can even sample. Verified
  empirically before touching any code: a standalone request against this exact model + mmproj, with
  a real generated JPEG (not a stub), came back as pure JSON with zero prose and zero markdown
  fences, in under a second. Wired into `llamaclient.hpp`'s request template with a deliberately
  loose schema (`array of objects`, not exact per-action-field shapes) so it can't reject a valid
  variation it wasn't told about. `extractJsonArray` (the fix from earlier tonight) is now
  defense-in-depth, not the primary mechanism. **Not yet live-flight-verified** -- built and unit-
  buildable, but the one successful live flight above ran on the binary from *before* this change.

- **Raw VLM response text is now logged.** Previously only a character count
  (`VLM plan received (N chars)`) was logged, which made every parse failure undebuggable after the
  fact without re-running and adding prints by hand. `callLlamaServer()` now logs the actual text
  (bounded to 2000 chars) whenever a response is successfully extracted from the HTTP body.

## ASR status check (2026-08-09)

Asked directly whether ASR (voice override) had been forgotten. It has not: the ASR publisher node
already exists and works standalone (`source/llm_to_action/asr/asr_node.hpp`, push-to-talk on key
`H`, publishes to `/asr_server/transcribe`), and a full, detailed implementation spec already exists
at `docs/scheduled/sitl-2026-08-10-spec-A3-voice-interrupt-and-termination.md` (status: scheduled,
not started). `fmu_node.hpp` has zero references to the ASR topic today -- the wiring is genuinely
unbuilt, not forgotten. Worth flagging: that spec cites specific `fmu_node.hpp` line numbers for
where to hook in; those are now stale after tonight's edits (the file has grown), so whoever picks
up A3 will need to re-locate the relevant functions rather than trust the spec's line numbers
verbatim. Confirmed no conflict with tonight's `response_format` schema change -- it's deliberately
loose (any object shape) and A3's planned `objective_complete`/`reason` fields on the first array
element fit within it fine.

## feature-calibrate-slam branch: merge assessment (2026-08-09)

Reviewed (read-only: `git log`/`git diff` against `origin/feature-calibrate-slam`, no checkout, no
merge performed) ahead of merging into the next commit on this branch. Two commits on top of our
shared history at `be3db5d` (the OpenMP commit) -- `42c5b36` and `afe189b`, the latter looking like
a fixup of the former (near-identical messages).

- **Clean divergence.** 13 files changed, 500 insertions / 136 deletions. Only one file overlaps
  with tonight's own changes on this branch: `docs/NOTES.md` -- both branches append after the same
  anchor line, so this will show as a merge conflict, but it is a **pure append/append conflict**,
  not a logical one. Resolution is "keep both blocks," nothing to reconcile.
- **Real, well-documented debugging work, not half-finished junk despite the branch name.** Content:
  a provisional (explicitly marked "NOT calibrated for our airframe") community camera-intrinsics
  yaml for stella_vslam on the Tello (`dependencies/stella_config_tello.yaml`), a checkerboard
  generator, and substantial fixes to the calibration capture tooling: a missing SDK keepalive that
  was timing out real hardware, an OpenCV-GStreamer-vs-FFMPEG hang risk when no video is present,
  a recurrence of an earlier firewall-drop bug now with a real root cause (container launched
  without `devenv.sh`'s startup sequence, so its `iptables` rules were simply never inserted), and a
  genuine performance bug (`cv2.findChessboardCorners` costing ~50s/call on a boardless frame,
  freezing the capture preview; switched to `findChessboardCornersSB`, ~600x faster). All of this
  is already written up in that branch's own `docs/NOTES.md` additions in the same evidence-based
  style as this file.
- **Safe cleanup included:** two accidentally-tracked `__pycache__/*.pyc` files are deleted, and
  `source/llm_to_action/gstreamer_tello_udp_tx/CMakeLists.txt` is removed as dead code (the
  Tello-specific camera plugin, made unnecessary once `rx_node.cpp` got its `--tello` runtime flag).
  Confirmed safe: this subdirectory is already commented out of the build on `feature-llm-driver`
  (`source/llm_to_action/CMakeLists.txt:93`), so nothing references the file being deleted.
- **Recommendation:** merge is low-risk and should happen before the next real work session. Order:
  merge `origin/feature-calibrate-slam` into this branch first (while today's other changes are
  still fresh and the NOTES.md conflict is easy to reason about), resolve the one NOTES.md conflict
  by keeping both additions, then continue. The camera intrinsics it adds are still explicitly
  provisional -- a real checkerboard capture against the actual airframe is still open work, not
  closed by this branch.

- **Tello SDK mode has a 15s inactivity timeout.** The drone exits SDK mode, beeps, goes red, and
  lands if airborne when it hears no command for 15 seconds. Every tool that holds a Tello session
  needs its own keepalive. `tello_backend.cpp` already does this via `streamLoop()`'s `rc` heartbeat.
  `scripts/tello/capture_calibration_frames.py` was missing one and timed out on first real hardware
  contact; it now runs a background thread re-sending `command` every 5s. The same script also now
  binds local UDP 8889 and checks the replies, so a failed handshake reports itself instead of
  looking like a dead video stream.

- **Opening the Tello video stream: probe the port before opening a decoder.** `streamon` returning
  ok does not mean packets are flowing. Measured against a Tello-like raw H.264 UDP source: with data
  present, OpenCV's GStreamer backend opens in ~0.1s and decodes clean, and FFMPEG takes ~1.7s and
  logs `non-existing PPS 0` before settling. With no data present, FFMPEG returns `isOpened()==False`
  after ~4s but **GStreamer blocks forever** with no output. That hang is the worst failure mode, so
  `capture_calibration_frames.py` waits for a real datagram on UDP 11111 first, then opens GStreamer
  with FFMPEG as fallback. The pipeline matches `rx_node.cpp`'s `--tello` source stage: plain
  `udpsrc port=11111 ! h264parse`, no explicit caps needed.

- **The 2026-08-06 firewall drop recurred on 2026-08-09, this time on video (UDP 11111).** Same
  mechanism as the 8890 telemetry case above, same fix. The cause of the recurrence is new: the
  container was launched without `devenv.sh`'s startup command, so its two `iptables -I INPUT`
  rules were simply absent (`iptables -C` confirmed both missing while `ufw` sat active with
  `INPUT policy DROP`). Measured 2977 packets landing in `ufw-reject-input` in ~12s while the
  `command`/`streamon` replies passed normally. Note that `tello_teleop` cannot detect this: its
  camera is best-effort and it continues without video, so a healthy teleop session proves only the
  command socket. `capture_calibration_frames.py` now checks the two rules with `iptables -C` and
  prints the missing ones, rather than trusting `ufw`.

- **`cv2.findChessboardCorners` is unusable on live video; use `findChessboardCornersSB`.** Measured
  on this box at 960x720: with a clean board in view the classic detector costs ~4ms, but on a
  textured frame with no clean board it costs **~50 seconds per call**, and `CALIB_CB_FAST_CHECK`
  changes nothing (50.4s with it, 50.6s without). Since the no-board case is most of a capture
  session, the preview was effectively frozen. `findChessboardCornersSB` costs ~84ms on that same
  frame, a 600x improvement, and ~16ms at half resolution. `capture_calibration_frames.py` now runs
  SB on a half-size gray frame and scales the corners back up for the overlay, holding 29.1 fps
  against a 30 fps source. `calibrate_camera.py` uses SB at full resolution and drops its
  `cornerSubPix` pass, since SB returns subpixel corners already.
  Consequence worth knowing: before this, the "measured stream fps" the capture script printed was
  bounded by the detector, not the stream, so it would have written a badly wrong `fps` into
  `stella_config_tello.yaml`.

- **`devenv.sh`'s Tello firewall rules could be skipped silently, and were.** They were written as
  `iptables -C ... || iptables -I ...` hung off the startup `&&` chain. Two silent failure paths:
  any earlier command returning non-zero skipped them, and a `-C` match against rules left from a
  previous session skipped the insert even though ufw later rebuilt `INPUT` and wiped them. On
  2026-08-09 the rules were absent in a container launched through `devenv.sh`; the live rule order
  proved the working rules had been typed by hand, not inserted by the script. Now an unconditional
  delete-then-insert loop, detached from the `&&` chain, printing the chain head at launch.

## Lightweight color-discrimination SITL showcase (2026-08-09)

Built in response to a real field-showcase constraint: the existing full `rubicon_targets` scene
(2 cars + 2 people) measures ~12GiB VRAM (ROADMAP 9.15), which limits what can be demoed outside a
machine with a big GPU. New world `dependencies/rubicon_colors.sdf` (source of truth;
`scripts/test/lib/sim_core.sh` symlinks whatever `WORLD_NAME` resolves to from `dependencies/` into
the PX4-Autopilot worlds directory fresh on every run, so the world file must live there, not be
dropped directly into the PX4-Autopilot tree). Trimmed from `rubicon_targets.sdf`: kept the Rubicon
terrain (SLAM needs its texture -- "empty"/`default_car` are too feature-poor per earlier session
findings) and both existing hatchback models (`hatchback_blue` and the plain `hatchback`, already
present in `rubicon_targets.sdf` at different poses), dropped both person models entirely to cut
object count and perception load. Use `WORLD_NAME=rubicon_colors` in place of `rubicon_targets` in
any of tonight's run commands. Purpose: an objective like *"find the BLUE car, not the other one"*
tests whether the VLM discriminates by a real visual attribute instead of just detecting "a car" --
a meaningfully different and harder capability than object presence alone.

**Update 2026-08-10: run, and it surfaced a real bug -- the drone never took off.** Checked
`scripts/test/colors/captured_panes_log.txt` directly (`altENU`, `arm=`, the raw VLM plan), not just
the diagnostic lines that looked like normal flight at a glance:
- `altENU` never exceeds 0.06 m across the entire 278-sample log. The vehicle armed once (~t=492s)
  and stayed armed, but never climbed.
- The VLM's own plan: `thought` correctly reasoned *"The drone is currently not airborne and needs
  to take off first"* -- then the action array was `search`, `approach`, `takeoff`, in that literal
  order. `takeoff` was queued third, behind two actions that don't request altitude, and per the log
  was never reached.
- `search`/`approach` ran for real, on the ground, near the rocky outcrop the model's own `thought`
  mentions -- almost certainly the "hugging the rocks" behavior observed live.
- `scripts/test/colors/slam_check.log` shows `spread_ratio` 0.04-0.05 (`note=collapsed-fit`) for
  215/287 samples, 0 healthy -- consistent with a vehicle that never actually moved, not a SLAM/world
  problem in its own right.

Root cause is a plan-validation gap, not a colors-world or SLAM problem: nothing rejects a plan whose
first real action isn't `takeoff` while `!airborne`. Fix already scoped (not yet built): reject the
whole plan on that condition, same path as a JSON-parse failure -- discard, let queue-empty
immediately re-wake the VLM. Re-run this world once that lands before drawing any conclusion about
whether stella_vslam tracks in it.

## Honest capacity/risk assessment for the final 3 days (2026-08-10) -- written down per explicit request

This was given verbally in-session first and not persisted, which was a real gap given how much
weighs on it -- written here now so it survives context loss, not just chat history.

**On the 8-item plan (finish tonight's work, message-injection, ASR wiring, fix SEARCH, hardware
E2E, a real SLAM answer capped at 6h, Tello-specific tuning, plus two contest demos by Thursday
2026-08-13, one physical-with-localization preferred): not comfortably achievable as literally
scoped in ~40 working hours.** Basis for that read, not a guess: tonight alone, testing a system
believed largely finished, found six distinct real bugs in one evening -- a build flag, a
plan-parsing failure, three separate SEARCH gaps, a hardcoded objective silently eating every
override, an unexplained 20+ minute hang, and a command-ordering bug that kept a plan from ever
taking off. That is the real discovery rate this system produces under actual testing, not a
fluke to discount. SLAM has zero integration into flight control -- none, at any point tonight or
before. Wiring it into real hardware for the first time, under deadline pressure, at the same
discovery rate, risks the whole contest slot, not just one demo.

**Agreed mitigation:** SITL is the guaranteed deliverable (closest to solid, real positive
evidence already). Physical-with-localization is a stretch goal with an explicit checkpoint --
if the SLAM fallback gate (see item F below) is not cleanly working in SITL by Wednesday evening,
2026-08-12, do not attempt it live for the contest; fall back to the physical *non-localized* demo
(takeoff/rotate/describe/land, no position dependency) instead. That is still a real, honest,
working physical demonstration.

**Per-item read:**
- Finishing tonight's loose ends: essentially done as of this entry (merge landed, docs current).
  One new item added by tonight's own testing: a plan that puts `takeoff` after a movement command
  can leave the drone stuck forever, ungrounded, never airborne (see "SEARCH ordering bug" below)
  -- worth fixing before anything else, since it can silently eat a demo attempt.
- Message injection + ASR: correctly scoped as nearly one task -- the ASR spec's `[USER]`
  interrupt-injection mechanism doesn't care whether the text comes from a microphone or a typed
  string. Build the generic injection path first; real ASR becomes "subscribe to the existing topic
  and call the same function," not a second implementation.
- SEARCH: the return-to-start gap closed tonight; the size-preset request closed same night (see
  below). The harder gap (auto-measuring the room) remains open and was not attempted -- correctly
  out of scope for this window.
- Hardware E2E: the one item genuinely bound by calendar time (battery swaps, physical iteration),
  not by effort -- cannot be compressed by working harder. Should start early and run in parallel
  with everything else, not last.
- SLAM, capped at 6h: right instinct on the cap. Spend it on scale calibration + a staleness/
  fallback gate (never trust pose that hasn't updated recently), not on chasing a replacement
  library -- every alternative already evaluated has the same or worse fundamental limits for
  monocular SLAM at this budget. "Fully solve catastrophic tracking-loss recovery" is not
  achievable in 6h and should not quietly become the goal.
- Tello-specific tuning: flows directly out of hardware E2E time; cannot proceed independently of it.

## Two field-showcase fixes (2026-08-10)

- **rubicon_colors' two cars were not actually different colors.** Confirmed live: `hatchback` (no
  suffix) is ALSO blue, same as `hatchback_blue` -- the world was not a valid color-discrimination
  test as originally built. Replaced with OpenRobotics' real "Hatchback red" model (confirmed to
  exist via the Fuel API: same publisher, same weight class, 671KB), wired in via the explicit Fuel
  HTTPS URI (`.../OpenRobotics/models/Hatchback%20red`) rather than the `model://` shorthand --
  matches the pattern the Rubicon terrain include already uses reliably in this environment; the
  shorthand's exact resolution mechanism was never confirmed. **Not yet live-verified** -- a
  standalone `gz sim` sanity check was invalid (it failed on the pre-existing `hatchback_blue` line
  too, because it doesn't replicate the GZ_SIM_RESOURCE_PATH setup `sim_core.sh` normally provides),
  so this needs a real `scripts/test/colors/run.sh` run to confirm.
- **VLM context size is now overridable** (`VLM_CTX_SIZE`, `scripts/test/lib/sim_core.sh`),
  defaulting to 4096 for `scripts/test/colors/run.sh` specifically (was a hardcoded 65536
  everywhere). Could not verify the resulting VRAM figure -- this sandbox has no
  `nvidia-smi`/`rocm-smi`, and `vulkaninfo` does not report live heap usage here. Real number needs
  checking with whatever GPU tool exists on the actual demo machine before trusting it for a field
  demo with a real VRAM ceiling.

## SEARCH size presets (2026-08-10)

Replaced the single fixed lawnmower grid with three presets (small/medium/large), selectable per-
search by the VLM via a new optional `search_size` field, defaulting to medium (byte-identical to
the old flat constants, so an unspecified/old-format plan is unaffected). `fmu_node_base.hpp`:
`SearchSizeParams` struct + `kSearchSizePresets[3]` table (laneLengthM/laneSpacingM/maxLanes/
legTimeoutMs each). Important detail that would have been a real bug if missed: the per-leg timeout
had to become part of the per-size table, not stay a single flat constant -- LARGE's longer lane
takes longer to traverse at the same cruise speed, and the old flat 20s timeout would have cut a
large-preset lane short before it ever reached its own intended length, silently shrinking "large"
back down to whatever the timeout allowed. `kSearchReturnTimeoutMs` (the return-to-start bound)
stays one flat, generously-sized constant (70s) covering even LARGE's worst-case diagonal, rather
than adding a third per-size timeout to track. System prompt (`llm_base.hpp`) documents the new
parameter with guidance on when to use which size. Builds clean.

## SEARCH-then-APPROACH-before-TAKEOFF bug, found live (2026-08-10)

`scripts/test/colors/run.sh`'s first real trial produced a plan whose own `thought` field correctly
said *"The drone is currently not airborne and needs to take off first"* -- then emitted the action
array `search, approach, takeoff, orbit, stop, land`, with `takeoff` third, not first. Nothing
enforces the model's own stated reasoning against its actual output order. Result: SEARCH ran its
full 60s sweep while grounded and disarmed (never moved, matches `search_exhausted`'s own correct
timeout behavior -- that part worked), then APPROACH activated next and never resolved -- no
timeout fires because it kept flickering between "lost" and "reacquired" rather than staying
continuously lost long enough to trip its own failure timer, so `takeoff` (queued third) was never
reached. Confirmed via the unbounded FMU log (`scripts/test/colors/captured_panes_log.txt`), not
the scrollback-limited pane capture -- `arm=2` (armed) does not appear even once in the entire log.
**Fixed (2026-08-10, same session):** `translateToBaseCommands` now rejects the whole plan (same
path as a JSON-parse failure -- discard, let queue-empty immediately re-wake the VLM) if `!airborne`
and the first real action (skipping the leading `{"thought":...}` object) is not `takeoff`.
Deliberately NOT "last action must be land" -- see the design reasoning above, unchanged. Builds
clean. Also fixed the same night: the two `rubicon_colors` cars were both genuinely blue
(`hatchback` and `hatchback_blue` render identically) -- replaced with OpenRobotics' real
"Hatchback red" (confirmed to exist and resolve via the Fuel API and a manual HTTP GET before
wiring in; user separately downloaded/cached it locally). Re-verification of both fixes together
launched same session -- see the next entry once it lands.

## Colors POC re-verified: 2 fixes confirmed, 1 new fundamental problem found (2026-08-10)

Real takeoff-ordering gate and the red-car model both confirmed working. **New finding: the
color-discrimination premise itself doesn't work with the current matching mechanism, and a bad
APPROACH target produced dangerous flight, not a safe no-op.**

- **Takeoff-ordering gate: confirmed working, both directions.** Real `takeoff_ok` first this
  time. Later in the same flight, two more VLM plans that opened with `search` while not airborne
  were correctly rejected (`plan rejected: not airborne and first action is 'search'`) instead of
  executing.
- **Red car model: loads correctly.** No Fuel/model errors this run -- yesterday's loading problem
  is resolved.
- **New, more serious finding: `target_object: "blue_car"` never matches anything, because nothing
  in the perception pipeline emits color-qualified labels.** SEARCH/APPROACH match by exact string
  against the detector's own class labels (plain YOLO classes like `"car"`, not `"blue_car"`). The
  model can *see* the color and say so in its `thought` text, but has no way to make that survive
  into a `target_object` the matching logic can actually use. The whole premise of "ask it to tell
  two cars apart by color via target_object" cannot work as currently wired -- this needs a design
  fix (e.g. color as a separate field checked against the actual bounding-box crop, not folded into
  the label string), not a retry.
- **More urgent: chasing an unmatched APPROACH target produced a violent, erratic excursion, not a
  safe failure.** The instant `APPROACH activated target=blue_car` printed, position jumped from
  (2.6,-0.2) to (16.4,5.5) in about 1 second with `measVelENU` values over 9 m/s and wild yawrate
  swings -- then self-terminated as `noop_ok` rather than a controlled `approach_lost_failed`. Left
  the vehicle in a confused state afterward: PX4-level arm dropped to disarmed while the FMU's own
  flight-state tracking (`fs=2`) kept believing it was still flying, causing a real
  `TAKEOFF rejected (backend not STANDBY)` a few seconds later and a SEARCH command running at a
  physically nonsensical negative-then-noisy altitude. **This is a real safety-relevant gap**: an
  invalid/unmatched APPROACH target should fail safely (hover, or `approach_lost_failed`), not
  produce large uncommanded motion. Not investigated further tonight -- root cause of the wild
  velocity command itself (not just the missing-target symptom) is still open.
- The run's log was cut short mid-SEARCH by the harness's own cleanup before a natural end state
  was reached, so there's no clean final verdict line for this trial -- treat as a real, informative
  failure, not a clean pass or fail.

**Recommendation, not acted on tonight given the hour: do not re-attempt this specific test
unattended again until the APPROACH-on-bad-target behavior is understood.** It produced real,
uncommanded, several-meters-per-second motion in simulation from what should have been a benign
"target not found" case -- worth being cautious about on real hardware.

## TRL assessment (2026-08-10) -- given verbally in-session, not persisted at the time

Asked directly: given the agreed final-3-days goal (a solid SITL showcase, plus a physical
demonstration as a stretch), what's the current Technology Readiness Level, and the realistic
Thursday-morning TRL?

**Current: TRL 4 (technology validated in a lab/simulated environment).** The full VLM-plan ->
deterministic-execution loop runs end-to-end in SITL against real inference models (not mocked),
and tonight's testing found and fixed six real bugs through actual use, which is exactly what
TRL 4 validation looks like -- not a demo run once and left alone. It is not TRL 5 ("validated in
a *relevant* environment") yet, for two concrete reasons: a known, unresolved, safety-relevant
failure mode (the APPROACH excursion above) means the system cannot yet be called validated
against realistic failure conditions, only against the nominal path; and there has been zero
real-hardware flight this cycle, so nothing has moved from simulated to physical evidence. SLAM
sits lower on its own, around TRL 3 (proof of concept) -- it tracks in isolation but has never
been read by flight control, on sim or hardware.

**Realistic Thursday morning, if the agreed plan holds:** still TRL 4 overall, not higher --
one physical flight isn't enough repetition to claim "validated in a relevant environment" for
the full autonomy stack, and the plan deliberately keeps SLAM out of the critical path. What
changes is the *evidence mix*, which matters for a contest demo even without a TRL number moving:
a repeatable, clean SITL run (the guaranteed deliverable) plus one real physical flight of the
non-localized subset (takeoff/rotate/describe/land) would be genuine TRL 4 evidence for that
narrower flight-control slice, arguably touching TRL 5 for just that slice, while the full
color-discrimination/SLAM-assisted stack stays at TRL 3-4. Do not present it as more than that --
the honest story is "the core loop is validated and repeatable under real testing, with one
specific failure mode still open," not "flight-ready."
