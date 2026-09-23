## Camera UDP port split: SITL vs Tello (2026-08-11, agent1)
- **Problem:** SITL image-in and real-Tello video-in both bound UDP **11111** (one hardcoded
  `kUdpHostPortAddress` in the gstreamer TX base), so a SITL run and a Tello calibration could not
  share a host -- blocked parallel work (Agent 1 FOLLOW SITL vs Agent 4 Tello calib).
- **Ownership (the point):** ports belong to the backend that owns the transport, not to a gstreamer
  catch-all constant. The Tello video port already existed as `kTelloVideoPort` (tello_backend_base.hpp,
  ROS-free) -- reuse it, do not duplicate. The SITL camera has no ROS backend that owns it: it comes
  from Gazebo via the gz TX plugin, so its port lives with that transport module as a single
  `kSitlUdpCamPort = 11112` (gstreamer_gz_udp_tx/gazebo_cam_plugin_base.hpp). It is NOT put in
  px4_backend_base.hpp, which is the DDS/px4_msgs contract -- the shared, backend-neutral RX is built
  once for both backends and must not pull px4_msgs (see rx_node.cpp main comment).
- **Wiring:** the RX picks the port by its `bUseTelloPipeline` flag -- `kTelloVideoPort` (pulled from
  the Tello backend) for the real drone, `kSitlUdpCamPort` for the sim. The gz TX plugin (sim-only)
  uses `kSitlUdpCamPort`. Compile-time, no env var (monolithic single-build constraint). Real-Tello
  path is byte-unchanged (still 11111).
- **Effect:** a SITL run (11112) and a Tello video stream (11111) now coexist on one host.
- **Caveat:** a sim started BEFORE this build still runs the old 11111 binary (old inode); it must be
  torn down before it stops squatting 11111.

# Architectural Notes

## ⚠ RUN QGROUNDCONTROL BEFORE ANY SITL SIM (2026-08-11) -- HARD REQUIREMENT

PX4 will NOT arm without a ground-control-station link. With no GCS connected the pxh
console prints `Preflight Fail: No connection to the GCS` then `Arming denied: Resolve
system health failures first`, and the drone sits disarmed forever: FMU streams the climb
setpoint, `nav=14` (OFFBOARD accepted), `arm` stays disarmed, altitude pinned at ~0. It
looks like a stuck takeoff; it is a refused arm.

The check is `rcAndDataLinkCheck.cpp`: arming needs a GCS or RC link when `NAV_DLL_ACT > 0`
(this build's default). QGroundControl supplies that link -- so **open QGroundControl before
launching any SITL scenario that must fly.** This is why the whole green SITL matrix was
operator-attended.

- **You (running a SITL sim): open QGroundControl first.** If you are an automated agent
  that cannot open a GUI, STOP and tell the human to open QGroundControl.
- Headless alternative (no GUI): export `PX4_PARAM_NAV_DLL_ACT=0` to waive the data-link
  check so a run can arm with no GCS. QGC is the intended path; the waiver is the fallback.
- Root-caused during the P1 disarm verify -- see
  `docs/active/sitl-agent3-qa-cleanups-spec.md` Report section 2.


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


## Tello manual-control reality check + run.sh canned knob (2026-08-10)

Re-checked the real Tello control path before handing off a physical dry-test runbook, because the
existing docs assume a manual keyboard takeoff/land that the code does not implement. Findings,
all read from source, not assumed:

- **The keyboard gives no takeoff/land/arm.** `keyboard_node.hpp` publishes only raw `[keycode,
  action]` events. The FMU's `keyCallback` (`fmu_node.hpp`) ignores every key unless manual-override
  is engaged, and even then maps only movement: WASD = horizontal body-FLU velocity, up/down arrows
  = altitude, left/right arrows = yaw, Space = hover. H and Enter are bound in the keyboard node but
  the FMU does nothing with them. There is no key that enqueues TAKEOFF or LAND.
- **Manual override itself can't be engaged from the Tello rig.** Override is a `std_msgs/Bool` on
  `/fmu/in/override`, toggled only by a manual `ros2 topic pub` (see `scripts/test/override/run.sh`).
  `scripts/tello/run.sh` launches only RX + FMU + keyboard, so nothing publishes that topic. Even if
  engaged, override is velocity-only and still cannot take off or land.
- **So takeoff/land come only from a plan** -- either the VLM (needs `llama-server` in a 4th pane),
  or a canned-plan flag on the FMU binary (argv[2], parsed in `fmu_node.cpp`). The stale header
  comment in `run.sh` ("manual arm / takeoff / interrupt / land") predates this and is wrong.
- **`--canned-rotate` is the position-free no-VLM airframe test.** It injects takeoff -> rotate 90 cw
  -> rotate 200 ccw -> land, yaw-only, no position source needed -- correct for a real Tello, which
  has no X/Y source wired. It also exercises the ROTATE-hang risk directly.
- **Real in-flight abort = Ctrl-C the FMU pane.** run.sh's cleanup `pkill`s the FMU, which stops the
  ~20 Hz rc keepalive; the Tello then auto-lands on its own ~15 s keepalive-loss timer. The docs'
  "land manually via keyboard" abort (`scripts/tello/README.md`, the tello physical handoff) does not
  exist and must not be relied on. The ~15 s auto-land is the actual safety net for a hung ROTATE.

Change made: added an optional `FMU_FLAG` env knob to `scripts/tello/run.sh` (default empty =
unchanged VLM-driven behavior), so the no-VLM canned test is reachable as
`FMU_FLAG=--canned-rotate ./run.sh` without editing the launcher or hand-rolling the FMU invocation.
Still open (doc debt, not fixed here): `run.sh`'s stale header comment and the keyboard-land claims
in `scripts/tello/README.md` and the tello physical handoff.


## P1 fix: FMU/backend flight-state desync on unexpected disarm (2026-08-10)

Root-caused the APPROACH "excursion" from the colors re-verify run. The guidance law is not the
culprit: every APPROACH velocity is clamped to `speedCeil` (~kApproachSpeedDefault) and the
unmatched-target paths command zero (hover/acquire) or a small `kApproachCoastSpeedMps` coast, so
the ~9 m/s / ~14 m jump in the log was *measured* state, not a *commanded* runaway -- a SITL
backend/estimator blowup. The real, fixable bug is what followed: the FMU never reconciles its own
`FlightState` against the backend once airborne. `FlightState`->`STANDBY` happened in only two
places (TAKEOFF seeing `IOState::FAULT`, LANDING touchdown); the `FLIGHT` branch logged
`m_backend->state()` but never acted on it. And the PX4 backend only moved `m_ioState` out of
`FLIGHT` on a *commanded* disarm (`disarm_impl`/`force_disarm_impl`) -- an unexpected PX4-side
disarm (failsafe/kill/crash) left `m_ioState=FLIGHT` even though `m_armingState` telemetry showed
disarmed. So the FMU kept streaming velocity to a disarmed vehicle and stayed `fs=FLIGHT`, which is
the desync seen live (later `TAKEOFF rejected (backend not STANDBY)`, SEARCH at nonsensical
altitude). The `noop_ok` was a *later* command falling through the "not movement -> auto-complete"
branch once state was corrupted, not APPROACH itself.

Two-part fix (syntax-verified via compile_commands `-fsyntax-only`; not yet full-built or
flight-tested):
- `px4_backend.cpp`: in the periodic tick, if `m_ioState==FLIGHT` and arming telemetry != ARMED,
  store `IOState::FAULT`. FAULT (not STANDBY) is deliberate -- it blocks an automatic re-takeoff
  after a failsafe until the operator restarts.
- `fmu_node.hpp` control loop: when `FlightState==FLIGHT` and `m_backend->state() != IOState::FLIGHT`,
  zero velocity, reconcile `FlightState`->`STANDBY`, `completeCurrent("backend_lost_flight")` if a
  task is active, and halt the mission. Placed after the LANDING/TAKEOFF early-returns so a normal
  land (FMU in LANDING at touchdown) can't false-trip it. Tello never reports FAULT, so it cannot
  false-trip there either; the Tello's own ~15 s keepalive auto-land remains its net.

Still open: the *measured* excursion's own trigger (why the SITL estimator/backend produced the
9 m/s state) is not root-caused -- needs a reproducing run with the FMU log retained. The guard
above makes the aftermath safe regardless. The single-detection APPROACH fallback (locks onto
whatever one object is in frame, ignoring the label) is a separate hazard, folded into the P2
discussion, not fixed here.

## VLM VRAM on the 4 GiB laptop (GTX 1050 Ti): current SITL config does NOT fit (2026-08-10)

Measured on the actual GPU (NVIDIA GTX 1050 Ti Max-Q, 4096 MiB). Tool: `nvidia-smi`. Gotcha worth
recording: the VLM runs on **Vulkan**, and Vulkan VRAM does **not** appear in
`nvidia-smi --query-compute-apps` (that lists CUDA contexts only) -- measure total
`--query-gpu=memory.used` instead, or the per-process read is a misleading 0.

- **Only the VLM uses the GPU during flight.** onnxruntime in this build is CPU-only (no
  `libonnxruntime_providers_cuda.so`), so YOLO seg + depth run on CPU (0 VRAM). GStreamer uses
  `avdec_h264` (software decode, 0 VRAM). Desktop/display baseline ~440 MiB.
- **The SITL `CMD_VLM` config OOMs at load on 4 GiB.** `-ngl 99 -c 65536` and `-ngl 99 -c 32768`
  both fail: `ggml_vulkan: Device memory allocation of size 1073741824 failed ... failed to
  allocate buffer for kv cache`. Root: `-ngl 99` forces all layers onto the GPU
  (`common_fit_params: failed to fit params to free device memory: n_gpu_layers set to 99, abort`)
  alongside Q4_K_M weights (1.11 GB) + mmproj BF16 (0.82 GB) + vision graph, leaving no room for KV.
- **Working config found:** drop `-ngl 99` (let llama.cpp auto-fit layers across GPU/CPU) with
  `-c 8192`. Loads clean; total GPU use ~3252 MiB (VLM delta ~2813 MiB), ~844 MiB free. That ~844
  MiB is the headroom for the vision-encoder transient during a real image inference -- Qwen3-VL
  wants >=1024 image tokens, so a full-res frame may spike into it; not yet measured live.
- Worst-case method: sample `nvidia-smi --query-gpu=memory.used --format=csv -lms 250` during an
  actual multimodal inference at the target `-c`, take the peak. Levers to free VRAM if the vision
  spike is too tight: quantized KV (`--cache-type-k/-v q8_0`), smaller `-c`, downscale camera frames
  before send, or a lower `-ngl`.


## Full VLM-driven SITL mission PASSES on the 4 GiB laptop + QGC-arming gotcha (2026-08-10)

End-to-end `scripts/test/vlm` run (objective "Take off, find the car, approach it, then land")
verified live on the GTX 1050 Ti (4 GiB). Clean pass: `takeoff_ok` -> `search_ok` ->
`APPROACH reached target=car range=1.94` -> `approach_ok` -> `land_ok`, `[SUCCESS] Clean`. No
excursion, no boundary interrupt, no lost-flight guard trip; max measured velocity ~0.09 m/s. This
is the nominal path -- one `car`, exact label match -- distinct from the 2-car unmatched `colors`
case (P2).

Two things made it work:
- **VRAM:** the default `sim_core.sh` `CMD_VLM` (`-ngl 99 -c 65536`) OOMs on 4 GiB. Ran with the lean
  config via the new knobs: `VLM_NGL_ARG="" VLM_CTX_SIZE=8192 VLM_KV_ARG="--cache-type-k q8_0
  --cache-type-v q8_0"`. Full stack (PX4 + Gazebo render + VLM) sat at ~3.45 GiB, ~580 MiB free.
- **Arming gotcha:** PX4 SITL refused to arm with `Arming denied: Resolve system health failures
  first` until **QGroundControl was running**. The GCS heartbeat/health link is a de-facto arming
  prerequisite for this SITL setup -- no QGC, no arm, drone never leaves the ground. Not a code
  bug. Start QGC before an armed SITL run.

Repro command (from `scripts/test/vlm/`, with QGC running):
`HEADLESS=1 HEADLESS_TIMEOUT_SECONDS=240 VLM_NGL_ARG="" VLM_CTX_SIZE=8192 VLM_KV_ARG="--cache-type-k q8_0 --cache-type-v q8_0" ./run.sh`
Drop HEADLESS for the attended/visual version for a live demo.


## Tello network verified + VLM speed levers in SITL (2026-08-10)

**Tello connectivity is correctly configured -- no change needed.** Runs directly on the laptop
(`wlp59s0`), not a container, so no container-routing issue. Firewall is `ufw` (INPUT policy DROP):
port 8889 (Tello command + response) is host-initiated so it rides the `ufw-before-input`
`ctstate RELATED,ESTABLISHED ACCEPT` rule; 8890 (state) and 11111 (video) are unsolicited pushes
from the drone and have explicit top-level ACCEPT rules. Route to 192.168.10.1 currently goes via
the default gateway only because the host isn't on the `TELLO-XXXX` AP yet; joining it gives
192.168.10.2 and a direct 192.168.10.0/24 route. All three ports covered.

**VLM speed in `scripts/test/vlm` -- the real levers (12-core laptop, GTX 1050 Ti):**
- Root cause of slowness: the 4 GiB VRAM cap forces the lean auto-fit config to offload some VLM
  layers to CPU, and `sim_core.sh` hardcoded `--threads 1`. Single-threaded CPU layers = slow.
- Fix (added, no rebuild): `VLM_THREADS` knob on `CMD_VLM` (default 1 = unchanged). Set
  `VLM_THREADS=6` (leave cores for Gazebo/PX4/FMU/YOLO-on-CPU). Biggest win.
- `kPlanCooldownMs = 2000` (`fmu_node_base.hpp`) is the *replan cadence* constant, not inference
  speed -- it throttles how often the FMU wakes the VLM. Compiled; lowering makes replanning
  snappier but doesn't speed a single inference.
- `max_tokens = 256` (`llamaclient.hpp`) caps plan length; compiled.
- Prompting "go faster" does NOT speed inference (compute is fixed). It CAN speed the *mission*:
  the plan schema has `speed` on go/approach/rotate and `search_size` on search, so nudging the
  objective toward higher speeds / smaller search makes the VLM emit larger speed values and the
  drone finish sooner. `llm_base.hpp` warns "keep speed low" for real hardware (transport latency);
  fine to push in SITL.


## A2 observability: annotated frame, depth colormap, VLM prompt log, HUD (2026-08-10)

Additive demo tooling. Nothing here feeds control; it is pure inspection. No existing
log line, topic, or behavior changed, so all SITL scenarios re-run as-is.

New topics the FMU node publishes:
- `/fmu/perception/annotated` (`sensor_msgs/Image`): camera frame with YOLO boxes + `class@conf`
  labels, at the seg loop rate.
- `/fmu/perception/depth` (`sensor_msgs/Image`): depth colormap (normalize -> 8-bit -> TURBO),
  at the depth loop rate.
- `/fmu/hud` (`std_msgs/String`): one human-readable status line, ~5 Hz. Also logged as `[FMU_HUD]`.
  Format: `STATE=... ALT=..m TASK=... VLM=idle|busy DET=label@NN%,... VEL=..m/s BATT=..%`.

Design decision: `PerceptionRuntime` gained two default-empty `std::function<void(cv::Mat const&)>`
callbacks (`onAnnotatedFrame`, `onDepthColormap`), so existing callers/tests still compile and just
skip publishing. The FMU owns the ROS publishers. The fixed `void(cv::Mat const&)` signature cannot
carry detections, so the boxes are drawn in `segLoop()` (where the detections are in scope) on a
clone of the frame; the FMU only wraps and publishes. The depth callback passes the raw metric mat
and the FMU applies the colormap.

Per-run VLM prompt/response log: `callLlamaServer()` writes one JSONL record per call to
`vlm_prompts_<YYYYMMDD_HHMMSS>.jsonl` under `kVlmPromptLogDir = /root/groundstation/vlm_logs`. The
filename is computed once at construction (no clobber across runs, same idiom as `sim_core.sh`'s
BAG_DIR). Record = `{timestamp_us, image_attached, image_b64_bytes, prompt, response}` -- the base64
image bytes are NOT inlined (they are live on the annotated topic), keeping a long run small. Written
on EVERY exit path, including HTTP/parse failures (empty `response` is itself the signal).

New constants (`fmu_node_base.hpp`): `kVlmViewTopic`, `kDepthColormapTopic`, `kFmuHudTopic`,
`kVlmPromptLogDir`, `kHudThrottleMs`/`kHudThrottleUs`.

New files: `scripts/test/lib/vlm_log_tool.sh` (no-arg lists files+records+sizes+total; `--clean`
wipes the dir), `dependencies/foxglove_layout.json` (primary), `dependencies/a2_observability.rviz`
(fallback -- Foxglove availability unverified; rviz2 ships with Jazzy).

## Runtime drone-config loader: per-drone tuning without a rebuild (2026-08-10)

The FMU flight constants were compile-time `constexpr` sized for PX4 Gazebo SITL. A real
Tello flown on those numbers climbed into an apartment ceiling. The loader fixes this. It
tunes the constants per drone and per environment from a text file at startup. No rebuild.

New file `source/llm_to_action/fmu/drone_config.hpp`. It holds a `DroneConfig` struct plus a
`loadDroneConfig(path, ok)` parser. The struct has one field per tunable. Every field DEFAULTS
to the exact compiled `constexpr k*` value in `fmu_node_base.hpp`. So with no profile loaded the
FMU reads the same numbers as before. No-profile behavior is byte-identical to the old binary.
The `constexpr` constants stay put as the documented default and the fallback. They were not
deleted.

Selection is the `DRONE_CONFIG` env var, read once in the FMU constructor. This getenv is the
one sanctioned runtime-config hook. The codebase's usual zero-getenv rule does not apply to this
selector. Unset means the all-defaults struct (SITL scale). Set-but-missing, unreadable, or
unparsable is `RCLCPP_FATAL` then `std::abort()`. An explicitly selected profile must never
silently fall back to the wrong-scale defaults. That silent fallback is the crash this prevents.
The config loads once and is then read-only. There is no hot-reload.

Parser: a flat `key: value` text file, hand-rolled, no YAML library. One pair per line. `#`
starts a comment. Whitespace is tolerated. An unknown key warns and is skipped, so a newer
profile still loads on an older binary. A malformed line or a bad numeric value sets `ok=false`,
which aborts a selected profile. No exceptions anywhere; parse uses `strtof`/`strtol`.

Wired fields (`fmu_node.hpp` now reads `m_cfg.*`, not `k*`): takeoff target/climb, land descend
plus the full flare taper, ground contact, GO cruise + position/cross-track gains, ROTATE yaw
gain + clamp (the SEARCH heading control reuses the same yaw gain), APPROACH standoff + speed,
SEARCH sweep speed and lane geometry, ORBIT speed, the emergency boundary base + velocity scale,
the two battery failsafe thresholds, and manual teleop speed.

SEARCH lane geometry is the one non-scalar wire. Lane length, spacing, and leg timeout come from
the VLM-chosen size preset (`kSearchSizePresets`). A loaded profile overlays those three with its
own tuned values via an `mb_cfgActive` gate; `maxLanes` stays from the preset. With no profile the
gate is false and the preset is used verbatim, so SITL is unchanged. This overlay is the only place
a loaded profile changes preset-selection behavior, and only for a real configured drone.

Profiles: `config/tello.yaml` is apartment scale and fixes the crash (0.8 m climb at 0.5 m/s, 1 m
standoff, 0.25 m/s search, short lanes). `config/px4_sitl.yaml` spells out today's SITL defaults;
loading it is identical to loading nothing, and it documents the format. `scripts/tello/run.sh`
defaults `DRONE_CONFIG` to `config/tello.yaml`, so `./run.sh` flies indoor-safe with no rebuild.
`scripts/test/lib/sim_core.sh` leaves it unset, so SITL keeps the compiled defaults; it only
passes a profile through if one is explicitly set.

Re-tune loop: edit `config/tello.yaml`, then `./run.sh`. No recompile. Blast radius: additive; the
only behavior change is opt-in, guarded by `DRONE_CONFIG` being set.


## VLM plan grammar: use raw GBNF, not json_schema (2026-08-10)
- The VLM kept stranding the drone on the ground. Every grounded plan was discarded:
  the first action was not `takeoff`, or the JSON truncated mid-array. 9 requests, 9 rejects,
  never airborne.
- Root cause 1: our llama-server build does NOT enforce json_schema `const`/`prefixItems`
  for this model. Verified adversarially -- with a takeoff `const` and a prompt demanding
  "do NOT take off", the model still planned `go` first. The schema shaped nothing; the
  takeoff-first we saw earlier was just the model's own choice.
- Root cause 2: the mandated first `{"thought":...}` object is a verbose 3-part analysis.
  A long thought ate `max_tokens` before the array closed -> truncated -> parse failed.
- Fix: hand-write a GBNF grammar and pass it via the `grammar` field (which IS enforced
  token-by-token). Built per-send in `llamaClientConnection::buildPlanGrammar`. Grounded
  (`requireTakeoffFirst`) pins the SECOND array element to the literal `{"action":"takeoff"}`.
  The `action` value is constrained to the verb enum, so the model cannot emit a sentence
  where a verb belongs. Every string and the action count are length-bounded (`{0,N}`
  repetition) so a runaway thought cannot truncate the array.
- `maxLength` on a schema string BREAKS this build's grammar (it injects junk `{" ":", "}`
  objects). Do not use it. Bound strings with `{0,N}` char repetition instead.
- The grounded flag is `m_flightState == STANDBY`, not an odometry-z threshold -- odometry
  can read stale/garbage in the first cycle before the EKF settles, which let one non-takeoff
  plan slip through. `STANDBY` is glitch-free.
- Verified in SITL: 3 requests, 0 grounded rejects, 0 parse fails, takeoff in ~30 s. Post-takeoff
  actions are clean verbs (go, search, orbit, stop). `max_tokens` raised 512 -> 768 for headroom.

## VLM llama-server config: fits the 4 GB GPU (2026-08-10)
- `-ngl 99 -c 8192 --cache-type-k q4_0 --cache-type-v q4_0 --threads 1` runs Qwen3-VL-2B
  FULLY on the 4 GB GTX 1050 Ti (~3.1 GiB VRAM with Gazebo), ~40 tok/s. App-stack RAM 1.9 GiB,
  well under the 8 GiB budget.
- The old default `-c 65536` OOMs. `--threads 1` is correct -- llama-server never needed more;
  throwing CPU threads at it starved the GPU path and made plans crawl.
- Baked as the defaults in `scripts/test/lib/sim_core.sh` (still overridable via VLM_* env).
- Plan latency: the FIRST plan is prefill-bound (~27 s -- the 8241-char system prompt + image,
  prefilled once). Steady-state reuses the KV cache (~8 s prefill) and is decode-bound, so it
  swings with output length, not the image. Trimming the system prompt mainly speeds the first
  plan. The image is already ~460 tokens (below Qwen-VL's 1024 floor), so shrinking it does not help.

## FMU thread/observability trims (2026-08-10)
- `MultiThreadedExecutor` capped 12 -> 3 (`fmu_node.cpp`) to cut ROS thread contention.
- `FMU_OBSERVABILITY` (env, default OFF) gates the A2 image publishers, HUD, and VLM-JSONL log.
  OFF is takeoff-safe: the always-on 1280x720 image encode+publish was saturating the 12 cores and
  starving the VLM. ON is for the dashboard: resize to 320x240 + ~10 Hz throttle before publish
  (done, agent2 2026-08-11 -- see the A2 dashboard note below).

## A2 dashboard: lean bridge + 320x240 downscale + headless self-test (agent2, 2026-08-11)

Completes the A2 path from topics to a browser, and lands the leanness fix. All FMU-side work stays
under the `FMU_OBSERVABILITY` gate, so OFF is unchanged and takeoff-safe.
- FMU (`fmu_node.hpp`): `publishAnnotatedFrame` + `publishDepthColormap` now `cv::resize` to 320x240
  (`INTER_AREA`) and throttle to ~10 Hz (`m_lastAnnUs`/`m_lastDepthUs`, mirroring `kHudThrottleUs`)
  before publishing. This is the fix for the 1280x720 encode+publish that starved the VLM. Depth
  throttles BEFORE the colormap so the CPU is skipped, not just the publish. New `/fmu/vlm_text`
  (`std_msgs/String`) carries the VLM reasoning text, set in `callLlamaServer` (the HUD only had
  busy/idle). New constants (`fmu_node_base.hpp`): `kVlmTextTopic`, `kA2ImgW`/`kA2ImgH`,
  `kImgThrottleMs`/`kImgThrottleUs`.
- Browser dashboard (`scripts/dashboard/`, zero pip deps): `serve.py` is one `rclpy` node + a stdlib
  `ThreadingHTTPServer` (MJPEG per image, one SSE for HUD+VLM). `dashboard.html` renders it. No
  websockets/rosbridge/foxglove (not installed). `serve.py` has file logging (`--log`/`--verbose`);
  `smoke.py` publishes fake topics for a no-drone bench test; `assess.py` writes a PASS/FAIL verdict.
- Self-assessing headless test (`scripts/test/SITL/dashboard/run.sh`): brings up the moving_person
  FOLLOW demo with Gazebo HEADLESS + observability, runs the bridge + assessor. Verified on a full
  run: real Gazebo camera -> perception -> 320x240 at ~7.5 Hz, live HUD/detections/VLM on the page,
  total RSS ~2.4 GiB (well under the 8 GiB budget), no leak, no dup publishers.
- `/fmu/vlm_context` (`std_msgs/String` JSON: objective + executed-command history with status) lets
  the dashboard show what the VLM was told, not just its reply -- the SAME context `buildDynamicPrompt`
  feeds the model. Obs-gated, event-driven (mission start + each completion). The VLM pane renders the
  objective, a numbered executed-command list, and the reasoning log; the log is an out-of-flow scroll
  box so it cannot resize the grid.
- Pipeline rates: `/fmu/rates` (obs-gated `std_msgs/String` JSON, ~1 Hz) reports the FMU's OWN
  perception-refresh Hz (seg/depth loop iteration deltas via `PerceptionRuntime::segIters/depthIters`)
  and publish Hz. The bridge measures its receive Hz separately; the dashboard shows all three per
  stream (`seg | pub | rx`). Publish Hz reads 0 when unwatched (subscriber-gate) while perception Hz
  keeps ticking -- so you see the throttle/gate juggling at a glance. Publish rate must come from the
  FMU: a dropped frame is invisible to the bridge (ROS2 Images carry no sequence number).
- Debug image quality: `FMU_A2_IMG_W`/`FMU_A2_IMG_H` (FMU env) override the 320x240 A2 publish size,
  clamped to the source frame; the bridge `--quality` sets JPEG quality. Both throttled. The image
  sinks now skip entirely when `get_subscription_count()==0`, so with the bridge's on-demand subs the
  FMU does image work ONLY while a browser is watching -- a high debug resolution is free when unwatched.
- Bridge threading/CPU: ROS callbacks on a single-threaded spin (A/B: a 2-thread MultiThreadedExecutor
  ~2x'd watched CPU for this light workload, so single-threaded is leaner);
  HTTP on a bounded daemon-thread pool (not thread-per-connection); image topics subscribed ONLY while
  a browser streams them, so the bridge is near-idle when unwatched (most of a SITL run).
- `sim_core.sh` passes `FMU_OBSERVABILITY` (into `CMD_FMU`) and `HEADLESS` (into `CMD_PX4`) through to
  the tmux panes; both default off/0, so attended runs are unchanged. HEADLESS gives a gz server with
  no GUI, so the dashboard is the observation surface.

## Keyboard override toggle + input-hook robustness (agent0, 2026-08-11)
- Enter now toggles manual override in `keyCallback`, handled before the `m_manualOverride` gate.
- Nothing publishes `/fmu/in/override` in the running rig, so a gated toggle could never fire.
- The key synthesises a Bool and calls `overrideCallback`, so key and topic share one engage path.
- Press-only: the matching key release would otherwise undo the toggle milliseconds later.
- The keyboard has no arm/takeoff/land key; those reach the backend only as VLM plan commands.
- `tello_teleop` (`tello_backend/test/`) is the manual takeoff-to-landing path, not `run.sh`.
- `AsyncKeyHook` aborted the whole hook on the first failed device open, discarding nine good ones.
- It now skips unopenable devices, drops `/proc` paths with no node, and is fatal only when none open.
- It also leaked a descriptor for every non-keyboard it opened; those are closed now.
- Container gotcha: `/dev` is a tmpfs snapshot taken at creation, `/proc/bus/input/devices` is host-live.
- So a keyboard plugged in after container start is listed in `/proc` with no node to open.
- `scripts/devenv.sh` now bind-mounts `/dev/input` (not `--device`, which snapshots the same way).
- Immediate workaround without a restart: `mknod /dev/input/eventN c 13 $((64+N))`.
- `${VLM_KV_ARG--cache-type-k ...}` in `sim_core.sh` spent its first dash on the `-` default operator.
- llama-server therefore saw `-cache-type-k` and refused to start, leaving the FMU with 0-char plans.
- Both that and `${VLM_NGL_ARG--ngl 99}` now carry a space; the latter survived only by luck.

## Tello drift is a surface problem, not an airframe problem (agent0, 2026-08-11)
- Measured on the real drone across four logged flights; this overturns "the Tello drifts badly".
- The Tello holds position with its Vision Positioning System: a downward camera plus an IR ranger.
- Blind VPS means no station-keeping at all, so the airframe wanders off on any air current.
- On the original uniform reflective floor it could not hold a 3 s hover and flew into a wall.
- Over hard flat chair mats it held a **38 s hands-off hover**, drifting only +0.20 m in altitude.
- Same drone, same room, same binary. Only the surface under it changed.
- The rule is flat, hard, matte and high-contrast -- NOT merely "textured".
- A floral bed FAILED (1/123 samples) while plain chair mats WORKED (72/118). Soft, non-planar
  surfaces deform under the drone's own downwash and give the VPS nothing stable to lock onto.
- Demo consequence: cover the flight area. See the coverage correction below -- a patch is not enough.
- **CORRECTION (same day, after the translation test).** The 38 s hover and the drift figures below
  were flown over roughly 1 m2 of chair mats in a 3-3.5 m x 6-7 m room: about 5% floor coverage.
  Across a 49 s translation flight the drone reported velocity for only 28% of airborne time. The
  other 72% produced NO measurement, and the operator reports it was drifting quickly during those
  stretches. A blind VPS reports zero, and integrating zero reads as "not moving", so the measured
  drift of 0.2 cm/s describes only the locked 28% -- it is drift WHILE HELD, not drift.
- A 1 m2 patch is a weak visual anchor. The drone leaves it in under a second of commanded motion,
  and the surrounding uniform reflective floor gives the camera nothing to fall back on.
- Sizing the real thing: a 3.5 x 7 m room is ~24 m2, so full coverage is ~100 tiles of 50 cm. That
  is a genuine logistics cost for the demo, not an afternoon of taping mats down.
- `vgx`/`vgy` are useless as a drift instrument: they read 0 when the VPS is blind AND when the
  drone is genuinely still. Do not build dead reckoning on them.
- `vgz` and `tof` stay live throughout, which is how we proved the state parse was never at fault.
- `tof` (downward IR, cm) is now stored in `TelloBackend` (`m_tofCm` / `tof_cm()`) and logged by
  `tello_teleop`. A tof that tracks altitude with dead `vgx`/`vgy` means the camera half is blind.
- For an actual drift figure in cm, use `scripts/tello/measure_drift.py` against a phone video.
- `tello_teleop` teleop speed was 0.4 m/s = stick 40/100, too little authority to fight drift.
  Default is now 0.8 m/s, tunable live via `TELLO_MOVE_MPS` / `TELLO_YAW_RADPS`.

## Tello demo: what the environment must provide (agent0, 2026-08-11)
- Written down because it currently exists only in one conversation, and the demo depends on it.
- **Floor**: hard, flat, matte, high-contrast, covering the WHOLE flight envelope plus a margin.
- Interlocking EVA foam tiles are the cheap answer; their seams give the camera free contrast lines.
- Tape every edge and seam. The drone's own downwash lifts loose material, and a flapping corner is
  a moving feature, which is worse for the VPS than no feature at all.
- Rubber-backed patterned rugs or a taped-flat matte dropcloth also work. They must not ripple.
- Avoid glossy tile, glass, polished concrete, uniform low-pile carpet.
- **Partial coverage is worse than none**: the drone gets a lock, holds, then loses it mid-transit.
- **Air**: no fans, no HVAC vents, no open windows. A household fan beats this airframe outright.
- **Light**: even indoor lighting. No direct sun -- the camera needs light, the IR ranger hates sun.
- **Altitude**: fly 0.5-2 m. VPS is out of range below 0.3 m.
- Do not test outdoors: wind dominates an 80 g airframe and sun washes out the IR ranger, so an
  outdoor result would tell you nothing about an indoor demo.
- WiFi degrades badly through walls; keep the laptop line-of-sight to the drone.
- **If the venue floor cannot be covered, do not fly the Tello.** SITL hat-follow was always the
  reliable headline and the Tello the stretch; that is now a hardware fact, not caution.

## Agent 5 C3: dead reckoning is unimplementable on this airframe (agent0, 2026-08-11)
- C3 in `sitl-agent5-slam-stabilization-spec.md` says to Simpson-integrate `vgx/vgy/vgz` into a DR
  XY pose, and to free-run on DR whenever SLAM tracking pauses. Neither is possible.
- `vgx`/`vgy` are 0 for the entire airborne phase: 411 samples in one log, 606 in another,
  max|vel| 0.00, while `vgz` and `tof` stay live in the same 16-field parse. Integrating zeros
  yields zero, so there is no DR pose and no DR fallback.
- Recovery must instead be: on tracking loss command zero velocity at once, let the Tello's own VPS
  station-keep, relocalize against the in-RAM map, re-anchor, resume.
- That fallback only holds while the surface underneath is VPS-readable, which makes the floor
  itself part of the recovery design, not just a comfort.
- The tracking-state topic C3 asks for is still needed, and now matters more: it gates a hard stop
  rather than a handover to dead reckoning.

## tmux capture loses data by default; use pipe-pane (agent0, 2026-08-11)
- Cost us a real diagnosis: an FMU pane held ~1900 lines and the `MANUAL OVERRIDE` line we needed
  had scrolled off 0.6 s before the capture window began. It read as "the override never fired".
- `run.sh:82` and `sim_core.sh:172` both set `-g history-limit 200000`, but the live server was at
  the 2000 default. The set is swallowed by `2>/dev/null || true`, so the failure is silent.
- 2000 lines of a 20 Hz FMU is well under a minute of flight.
- Fix for a running session: `tmux set-option -t <session> history-limit 200000` (future lines only).
- Real fix, independent of buffer size -- stream every line as it is produced:
  `for p in $(tmux list-panes -s -t <session> -F '#{pane_id}'); do
     tmux pipe-pane -t "$p" -o "cat >> logs/pane${p#%}.log"; done`
- When capturing scrollback instead, `capture-pane` needs `-J` as well as `-S -`. Without `-J` tmux
  breaks long lines at the pane width, which silently defeats greps: `yawRate=` lands on a different
  line from `ORBIT target=car`.

## Tello teleop telemetry: 10 Hz and timestamped (agent0, 2026-08-11)
- `tello_teleop` printed telemetry at 2 Hz with no timestamp, and its key-event print fires only on
  press/release -- exactly the moments when velocity is near zero by construction.
- Reading only the key-event print led me to conclude the drone reported no horizontal velocity at
  all. It was the wrong print. Use the `[tele]` lines, not `telemetry(`.
- Now samples at 10 Hz, matching the Tello's state broadcast rate so no update is missed, and each
  line carries `t=<ms>` from the first sample. Override with `TELLO_TELE_MS`.
- This is what made the surface comparison and the drift integration possible at all.
- Latent, wider than teleop: `kTelloMaxSpeedMps = 1.0` (tello_backend_base.hpp) is the constant that
  turns m/s into a [-100,100] stick, and its own comment admits it is a first estimate pending
  hardware calibration. EVERY velocity the FMU commands is scaled by it, not just teleop, so if the
  Tello's true full-stick speed is several m/s then every autonomous speed is wrong by that factor.
  Not measured here; flagged so it is not mistaken for a calibrated value.

## ORBIT geometry defect handed to agent 1 (agent0, 2026-08-11)
- Found in a live SITL log: the VLM planned `orbit ... "speed":1`, read as cm/s, so 0.01 m/s. A 360
  orbit at R=4 m became a ~42 minute task that looked like hovering.
- `radius_cm` is parsed and never used; the radius is whatever distance the drone sits at on lock.
- Completion is angle-only, so there is no duration bound and a slow speed stalls the task forever.
- The VLM is not at fault: the orbit schema gives `"speed": <int>` with no units, and the prompt
  says "Keep speed low". Units appear once in the whole prompt, for `go`.
- Full write-up with the four defaulting cases: `docs/active/sitl-agent1-orbit-geometry-spec.md`.

## HOVER verb + FOLLOW hold-on-loss + typed-member grammar (agent1, 2026-08-12)
- Diagnosed from live SITL logs: the VLM kept losing the target, failing FOLLOW, then flailing on
  re-plan -- emitting `go 0,0,0` to "hold", re-issuing `takeoff` every cycle, and rebuilding the whole
  mission from scratch. Root causes were all upstream of the flight code.
- Cause 1: no persistent hold. `stop` sets zero velocity for one tick, then auto-completes (`noop_ok`),
  which empties the queue and re-wakes the VLM. Only FOLLOW/SEARCH/ORBIT persist. So the model had no
  clean "hold station, don't ask me again" token and abused `go`. Fix: new `CommandID::HOVER` verb --
  zero velocity, never completes, never wakes the VLM. Exits only on interrupt / re-assess / new command.
  The station hold itself is the backend position controller (PX4 EKF / Tello VPS), which already exists.
- Cause 2: FOLLOW failing on brief loss. On sustained loss FOLLOW called `completeCurrent("follow_lost")`,
  handing a flailing VLM control. Reworked: if FOLLOW was EVER locked, on loss it HOLDS station and keeps
  re-acquiring by label indefinitely (no wake, no fail); the tr.found branch re-locks automatically when
  the target returns. Only a follow that NEVER locked within the acquire window fails, as
  `follow_no_target`, so the VLM learns the named target is not there. FOLLOW never self-completes (spec).
- Cause 3: loose GBNF let the model emit `{"parameters":"x: 0, ..."}` as a free-form string, so the
  parser read every field as its default (track_id -> 0, breaking the bind). Fix: members are now TYPED
  per key -- coordinate/id/speed keys take a number, only target_object/direction/search_size/reason take
  a string. An unknown key like "parameters" is rejected token-by-token. Also, when airborne the verb list
  DROPS `takeoff`, so the model cannot re-launch mid-flight and rebuild the mission from the ground up.
- Parser also routes a zero-vector `go` (x=y=z=0) to HOVER -- the model's real intent was to hold.
- Tracker coast bumped from 5 to 15 frames (perception_runtime.hpp m_trackerParams). Live actor detection
  flickers, and the short window retired+re-minted ids constantly (observed track_id 13 -> 50 -> 86 for a
  single actor). Longer coast keeps the id stable across blinks. Association still gates on label+geometry,
  so a genuinely new person does not inherit a coasting id.
- Prompt (llm_base.hpp) gained: hover doc, "hold with hover NEVER a zero go", "go/approach MOVE the drone
  so never use them to follow/maintain", "target already visible -> go straight to follow, do not search",
  and "plan only what REMAINS; takeoff_ok in history means you are airborne, never takeoff again".


## C1 SLAM go/no-go + hover-hold node (agent5, 2026-08-12)
- C1 flown handheld on chair mats (axistest_20260812): stella held a CLEAN continuous lock --
  100% tracking uptime, 0 BLIND, 0 NO-VIDEO, ~27 Hz over 45 s. On a textured floor stella tracks
  fine; the venue's glass/concrete is the open risk, screened before flight by feature_scout.py.
- Frame decoded from the raw slam/pose trace against a scripted motion (forward, right, up): stella's
  map is the CAMERA-OPTICAL frame -- +x = right, +y = down, +z = forward. So a level forward-facing
  Tello's horizontal ground plane is map (x, z) and vertical is -y. This is the one mapping the
  hover-hold node needed and was refusing to guess; it is now validated on hardware.
- Rough scale from that run: ~1 m real ~= 0.6 map units. Monocular is up-to-scale, so the node
  resolves live scale per-frame as tof_height / (-y) (median-smoothed) rather than trusting any fixed
  constant.
- Built tello_slam_hold (source/llm_to_action/tello_backend/test/tello_slam_hold.cpp): owns a
  TelloBackend, subscribes slam/pose + slam/tracking_state, runs the offline-tested bridge + PID +
  recovery FSM, holds station via set_body_velocity, lands on sustained loss. Frame mapping above;
  ENU->body uses the engage heading (yaw0=0), exact only while the drone holds heading (the hold case).
  Rotating by a live SLAM heading is deferred behind a single seam (worldErrToBody) because C1 logged
  position only, not the quaternion -- do NOT engage a hold after a large yaw until that is validated.
- Builds only under a Tello backend config (-D GROUNDSTATION_BUILD_BACKEND_TELLO=ON), guarded on the
  rclcpp/geometry_msgs targets. Pure CMake, no ament. Compiles clean against real ROS headers.


## ASR noise robustness + demo decision (2026-08-12, Insurance Agent)

- SNR robustness benchmark: `snr_mix_core.h` (header-only, zero-dep) mixes gunfire/explosion beds into
  clean clips at a controlled SNR; wired in-process into `sttserv/test/asr_test.cpp` as a sweep that
  prints an accuracy-vs-SNR table. Parakeet-q4 holds 92% intent @ 0 dB (38/38 pass), ~80% @ -4 dB, on raw audio.
  Confirms "ship raw" — every denoiser (GTCRN/SpeexDSP/classical) was net-negative. Beds live in
  `dependencies/noise_beds/`. Full method + reproduce steps: `docs/active/asr-noise-robustness.md`.
- "Explosion/noise proof" is a robustness spec, not a denoiser task. The real mitigations are model
  robustness (curve above), capture-side hardening (push-to-talk + close mic; a blast that clips the
  ADC is unrecoverable in software), and operator read-back for residual errors. Denoising was tested
  and dropped.
- Demo decision for Demo Day: pure-SITL voice-driven mission on the dashboard is the headline; Tello
  hardware is not bet on. The mission chains perception-conditioned verbs live — "take off and find
  the hatted man" -> approach/hold -> "now follow him" (sequential context) -> "orbit him" (re-task)
  -> one improvised Q&A command (proves not-canned). Hebrew handled as English-live + one canned
  Hebrew clip + roadmap. Must-do: pre-warm the VLM (cold 27s), record a backup video, deterministic
  world/seed, speak on the ground.
- Pre-existing fix while building: `asr_test.cpp` still included `util2/C/print.h`; the util2 swap
  renamed it to `util2/C/print2.h`. Only file left on the old path.


## ASR -> FMU voice integration + demo-1 world (2026-08-12, Manager)

- The ASR node was already built and publishing transcripts on `/asr_server/transcribe`
  (`std_msgs/String`); nothing consumed them. Closed the seam in `fmu_node.hpp`: a new subscription
  (`m_subAsr`) whose `asrCallback` logs a read-back (`[ASR] heard: "..."`) then, if `STANDBY`, calls
  `start(text)` to launch the mission from the spoken objective; if already flying, it re-tasks the
  VLM by mirroring the override-handback path (drain queue, clear cooldown, re-arm `m_missionActive`).
  Read-back is the safety net, NOT a confidence gate -- token-probability confidence was tested and
  does not track correctness.
- Voice-first launch: `fmu_node.cpp main()` now skips the boot `start()` when the objective is an
  explicit empty string and no `--canned` flag is present -- the drone idles in `STANDBY` until the
  first spoken transcript. Any typed objective (incl. the argc<=1 "Hold position." default) or any
  canned flag auto-starts as before, so every existing test script is unaffected.
- VLM prewarm: `sim_core.sh` fires one throwaway `/v1/chat/completions` after the llama-server pane is
  listening (backgrounded, self-timing out). This burns the one-time Vulkan shader/graph compile so
  the FIRST operator plan is warm (~9s vs ~27s cold). CAVEAT: a text-only warmup does NOT compile the
  vision projector (mmproj compiles on the first IMAGE request), so the first real image-plan may still
  pay a small residual -- measure it and, if it bites, warm with a tiny image instead.
- `sim_core.sh` gained a `LAUNCH_ASR` knob + `CMD_ASR` pane (mirrors `simenv.sh`) so one launcher brings
  up the full voice stack: PX4+Gazebo+RX+FMU+VLM+ASR. `scripts/test/SITL/rubicon/run.sh` is now Demo 1:
  `WORLD_NAME=rubicon_tree`, `LAUNCH_VLM=1`, `LAUNCH_ASR=1`, typed objective by default (blank it for
  voice-only).
- Demo-1 world `dependencies/rubicon_tree.sdf`: Rubicon map + three `person_walking` actors, centre one
  recoloured RED via a diffuse override (proven in `three_people.sdf`). Still the person mesh -> YOLO
  labels each "person"; the VLM disambiguates by colour. Actor poses are placeholders for the standard
  spawn -- the human supplies the final tree-cluster coordinates to hardcode.


## Gazebo GUI window never opened — HEADLESS=0 regression (2026-08-12, Manager)

- Symptom: no Gazebo GUI window at all via the SITL harness, but the dashboard (camera) still
  worked. Worked ~20 commits ago. glxgears fine, DISPLAY/GPU healthy — so not an env/GL problem.
- Root cause: PX4's `ROMFS/px4fmu_common/init.d-posix/px4-rc.gzsim` starts the gz **server**
  unconditionally (`gz sim -r -s world.sdf`) but the **GUI** only `if [ -z "${HEADLESS}" ]` — i.e.
  when HEADLESS is EMPTY. `sim_core.sh` exported `HEADLESS=${HEADLESS:-0}`, so HEADLESS="0", a
  non-empty string -> `[ -z "0" ]` is false -> GUI never launched. The server kept rendering the
  camera, so the dashboard masked the failure. Introduced in commit `54b8a6a` (~20 commits back),
  which added that `export HEADLESS=...` line.
- Fix (`sim_core.sh` CMD_PX4): `export HEADLESS="$([ "${HEADLESS:-0}" = "1" ] && echo 1)"` — export
  "1" only for a real headless run, otherwise export EMPTY so PX4's `[ -z ]` gate opens the GUI. The
  internal `${HEADLESS:-0}` attach/bag checks still treat unset/empty as attended. Verified the gate
  logic against old vs new export with a standalone shell test.
- Watch (separate from the above): the first GUI bring-up on `rubicon*.sdf` is slow because the
  Rubicon model streams from Fuel online + Ogre2 compiles shaders on first render. That is load
  latency, not the HEADLESS bug.
- Housekeeping: commit `55dc70c` relocated the test scenarios under `scripts/test/SITL/` but left the
  old top-level copies, so `scripts/test/<scenario>` and `scripts/test/SITL/<scenario>` are now
  duplicated. Needs a dedupe (human runs the git rm).

## Voice mode drone auto-armed — `:=` clobbered the empty objective (2026-08-12, Manager)

- Symptom: in voice mode (`FMU_OBJECTIVE=""`, expecting the drone to idle until spoken to), the FMU
  started a mission and armed on its own. FMU log showed `Mission started ... objective: Canned SITL
  test.` — the empty objective never reached the binary.
- Root cause: `sim_core.sh` had `: "${FMU_OBJECTIVE:=Canned SITL test.}"`. The `:=` form substitutes
  when the var is unset OR EMPTY, so an explicit `FMU_OBJECTIVE=""` was overwritten with the canned
  default before launch. The FMU's idle-on-empty guard then saw a non-empty objective and ran start().
- Fix: drop the colon -> `: "${FMU_OBJECTIVE=Canned SITL test.}"`. `=` defaults only when UNSET and
  preserves an explicit empty. Verified: empty->stays empty (voice idles), unset->canned default,
  typed->unchanged. No rebuild needed; the binary already carries the guard.

## Keyboard pane silently missing — tmux pane overflow (2026-08-13, Manager)

- Symptom: the keyboard-hook pane never opened, so the ASR push-to-talk key (H) was never captured
  and voice recording could not start. No error was obvious.
- Root cause: `sim_core.sh` split every node into panes of window 0. With LAUNCH_VLM=1 plus the new
  LAUNCH_ASR pane, the pane count exceeded tmux's minimum pane size and `split-window` for CMD_KEYBOARD
  (launched after the ASR pane) failed with "no space for new pane" -- silently. Pre-existing fragility
  (the wave1 runbook already flagged LAUNCH_VLM=1 as near the limit); adding the ASR pane tipped it over.
- Fix: give each secondary node its own tmux WINDOW (`new-window -n vlm|asr|keys|bag`) instead of a
  split pane. Window 0 keeps the 4 core panes (agent/px4/rx/fmu). Windows have no space limit and are
  full-size. `select-window -t :0` lands the user on the sim view. Switch with Ctrl-B w / Ctrl-B <n>.
  H is captured globally via evdev, so it works from any window. Shell-only fix, no rebuild.

## 2026-08-13 — VLM-bbox drives APPROACH/ORBIT (non-COCO targets: house/window) [agent1]

Problem: YOLO only knows COCO classes, so "house"/"window" get no detection box, and the
APPROACH/ORBIT servos (which lock a detection centroid+depth) have nothing to drive toward.

Decision: drive both servos off a VLM-emitted bbox instead of a YOLO label. Key enabler is that
depth is dense and YOLO-independent (`YoloDepthEngine::estimate` returns CV_32FC1 metres over the
whole frame). Flow at activation only:
- The plan carries `"bbox":[xmin,ymin,xmax,ymax]` in the 640x640 image the VLM sees (grammar gains an
  `arrmember`/`arrkey "bbox"`; parser reads it into `CmdApproach::bbox` / `CmdOrbit::bbox`, i16[4]).
- `bboxToEnuAnchor()` scales the bbox to native camera px (kVlmImageSide 640 -> 1280x720), takes the
  median dense depth over it (`PerceptionRuntime::medianDepthCmInRect`), pinhole back-projects through
  the live pose (exact inverse of `updateCannedApproachRig`), and freezes a world ENU anchor.
- APPROACH reuses the synthetic-injection rig (`m_approachBboxRig`, reset per activation) so the
  existing label servo consumes the frozen anchor -- no YOLO. ORBIT latches `m_orbitCenterEnu`
  directly and skips the YOLO seed. house/window are static, so a one-shot bbox anchor is enough.

Why safe: geometry is the algebraic inverse of the already-SITL-verified canned-approach projection;
the bbox is optional (omitted -> unchanged label/track_id path); `static_assert`s guard the command
union payload (CmdOrbit 53B, CmdApproach 48B, budget 56B). Risk: VLM bbox accuracy on the 2B, and
SITL close-range monocular-depth over-read. Full visual proof needs the rubicon world; px4 links clean.

## Voice emergency fastpath + A3 interrupt/termination -- IMPLEMENTED (2026-08-13, Manager)

- Built spec A3 (docs/scheduled/sitl-2026-08-10-spec-A3-voice-interrupt-and-termination.md) plus a
  deterministic emergency fastpath. The ASR callback now only trims + POSTS the transcript
  (m_asrPending); controlLoop drains it and runs handleAsrCommand() on the control thread, so
  raiseInterrupt()/flight-state mutation stays control-thread-only (fixes the "control-thread only"
  contract that the earlier ad-hoc re-task violated).
- Three routes in handleAsrCommand: (1) EMERGENCY LAND -- short imperatives land/abort/emergency/
  mayday/etc. -> deterministic FlightState::LANDING, VLM bypassed (same primitive as the battery
  failsafe); (2) EMERGENCY STOP -- stop/halt/hold/etc. -> deterministic hover, VLM bypassed;
  (3) everything else -> grounded launches start(), airborne raises raiseInterrupt("user_command")
  which hovers instantly and surfaces the words in a new [USER] prompt block for the VLM to reassess.
  A full sentence ("find the house and land near it") is NOT an emergency -- only short callouts are.
- Completion verdict: the VLM may set objective_complete=true (+reason) on the first plan object;
  translateToBaseCommands reads plan[0] and stands the drone down (land if airborne, else stop) with
  m_missionActive=false. Defaulted false via .value() so every existing response is unaffected.
- GBNF grammar (llamaclient.hpp) extended: the thought object may now optionally carry
  objective_complete + reason (backward-compatible superset -- the thought-only form still parses).
  Without this the grammar-constrained VLM could not emit the verdict.
- Tests (canned, run against the real binary): --canned-complete -> "verdict objective_complete=true
  -> stand down (stop)"; --canned-voice -> "INTERRUPT (reason=user_command)"; regression --canned-cross
  -> normal start, NO verdict (default-false safety holds). All pass.
- Touches Agent 1's llm_base.hpp (OUTPUT FORMAT doc) + llamaclient.hpp (grammar) -- coordinate.

## SEARCH rewritten: lawnmower -> advance-and-scan (2026-08-13, Manager)

- Old SEARCH was a lawnmower (fly lane / step sideways / flip 180). It marched off to one side, faced
  BACKWARD on flipped lanes, and drifted into obstacles over many legs -- and the VLM often chose a
  sideways start_heading_deg, so it never searched the front where the target was.
- New primitive: at a checkpoint, rotate a full 360 IN PLACE (no translation) checking perception every
  tick; if not found, advance step_m forward along the search heading, scan again; repeat until found,
  max reach, or timeout, then return to origin. Starts by scanning at the takeoff spot (look before
  moving). fmu_node.hpp SEARCH dispatch + activation; new m_searchScanning/ScanRemainingRad/ScanPrevYaw/
  TotalDistM/StepM/MaxDistM state.
- Direction: reuses start_heading_deg as the ADVANCE heading, default 0 = forward (this is the fix). The
  360 scan sees every direction at each stop, so a wrong advance heading still scans everything -- it only
  controls where you progress. No new grammar key.
- step/maxDist by size: small 3/9 m, medium (default) 4/16 m, large 5/30 m. Reuses the 360-spin math from
  ROTATE (rotateMaxYawRate) and the existing return-to-origin-on-exhaust.
- Prompt (llm_base.hpp) updated to describe advance-and-scan and tell the VLM to advance AHEAD by default.
- Compiles + links; A3 voice unit tests still 3/3; live "find the red human" is the real test. Agent 1's
  SEARCH lane -- coordinate (touched fmu_node.hpp SEARCH + llm_base.hpp).


## 2026-08-13 -- Demo-1 crash post-mortem: empty search -> hallucinated approach -> underground sink

Rubicon voice run died mid-mission. Trace (captured_panes_log.txt): takeoff OK -> SEARCH (VLM picked
SMALL) -> person never detected -> search exhausted, returned to origin -> VLM re-planned, hallucinated
"the human in red is visible" with NO detection, emitted APPROACH with a fabricated bbox -> bboxToEnuAnchor
projected that low bbox through depth to an ENU anchor at z=-1.87 (UNDERGROUND) -> go-to servo flew the
drone into the ground -> PX4 ground-contact disarm -> FMU FLIGHT->FAULT, abort to STANDBY. The HUD's
`DET=person@100%` was misleading (track_id=-1, no YOLO lock).

Root causes + fixes (all in fmu_node.hpp / fmu_node_base.hpp):
- REACH: search reach = step x maxLegs -> small 0.5x4=2m, medium 1.5x6=9m, large 3.0x8=24m. People sit
  12-16m out, so a small search can NEVER reach them, and YOLO can't resolve a person that far anyway.
  Fix: when perception is EMPTY at SEARCH activation (drone blind), promote size to LARGE (reach ~24m).
  Once anything is in view the VLM's size is respected. Forward advance already aims at the cluster.
- SINK (the killer): bboxToEnuAnchor had no altitude floor. Fix: new kApproachMinAnchorAltEnu=0.8m; clamp
  the bbox anchor Z up to it, AND guard the visual-servo descent (vUp>=0 once at/below the floor). SITL
  ground is ENU 0.
- Hallucination gate (VLM approaching a target it can't see) is NOT yet fixed -- Agent 1's prompt/grammar
  lane. With the reach fix the demo path now gets a REAL detection, so the approach anchors on truth.

Test hygiene: sim_core.sh now `rm -f "$LOG_FILE"` before launch, so a run that dies before tee opens can't
leave the previous run's log reading as the current one (this exact staleness misled the first diagnosis).


## 2026-08-13 -- CRITICAL: red person showed BLUE (R/B swap in the gz camera tx plugin)

Symptom: the RED person rendered correct in the Gazebo GUI but appeared BLUE in the dashboard, and the
VLM could not lock "the person in red" -- because it was seeing blue too.

Root cause: our gz->udp camera plugin (source/llm_to_action/gstreamer_gz_udp_tx/gazebo_cam_plugin.cpp)
declared its appsrc caps as `format=BGR` and memcpy'd the Gazebo camera buffer straight in. But the gimbal
camera sensor emits R8G8B8 (RGB, gimbal model.sdf). So RGB bytes were fed to gstreamer AS BGR -> R and B
swapped, baked into the H.264 stream. Every consumer (rx -> perception/YOLO, the VLM b64 image, the
dashboard MJPEG) saw the swap, since they all read one stream. PX4's own GstCameraSystem.cpp declares
"RGB" correctly; ours was the odd one out. Fix: appsrc caps BGR -> RGB (one line). Rebuilt libGazeboGst
CameraPlugin.so. Requires a FULL sim restart (the plugin loads into the gz server; restarting only the
dashboard does nothing).

Implication: this likely sabotaged Demo 1 at the root -- "find the person in RED" cannot work when the
VLM sees the target as blue. Re-test colour disambiguation after the restart.


## 2026-08-13 -- SEARCH could not recognise "human in red" -> searched past it into the rocks

Symptom: drone saw the red person, planned a SEARCH anyway, and flew into terrain (rocks) during the
low-altitude advance.

Root cause: the SEARCH found-check matched by EXACT label -- strcmp(det.label, srch.target). The VLM names
the target in natural language ("human in red"); YOLO emits COCO "person". strcmp never matched, so the
search never registered the person right in front of it, ignored it, and kept advancing until it hit the
rocks (the search holds a FIXED low ENU altitude with zero terrain clearance).

Fix (fmu_node.hpp + fmu_node_base.hpp):
- New labelMatchesTarget(): a person detection matches whenever the requested target names a human
  (human/person/people/man/woman/...). Colour disambiguation stays the VLM's job via the image + bbox.
- kSearchMinConfidence 0.35 -> 0.25: a person at ~10m only scores 25-53%; 0.35 dropped real red hits.
Effect: the moment red is in view (at the start point or anywhere in the opening 360 scan), the search
completes as FOUND with zero velocity and hands to approach -- it no longer advances, so it no longer
crashes into terrain when the target is already visible. This is the deterministic version of "don't
search when it's right in front"; stopping the VLM from PLANNING a search at all is Agent 1's prompt lane.

RESIDUAL: a genuine search (target truly not visible) still advances at a fixed low ENU altitude with no
terrain clearance -- rock-collision hazard remains for that case. Separate fix (terrain-relative search
altitude / obstacle backstop) still owed.

## fmu_node canned-plan removal: A1/A2/B tiering (2026-08-16, agent1)
- **Decision:** the `--canned-*` scaffolding in fmu_node.hpp is bring-up/SITL regression test code,
  never on the live VLM demo path (`cannedRun` is false in a real run). SITL is a no-go, so it is
  being removed. Split by *coupling*, not by count, so each cut is verifiable and safe:
- **A1 (DONE, build-verified):** the 10 self-contained plans -- voice, complete, plan, rotate,
  land-flare, terrain-land, orbit, search, patrol, speed. Pure JSON -> translateToBaseCommands; touch
  no live state, no controlLoop, no LOCKED APPROACH. Removed from fmu_node.hpp (defs + start() params
  + dispatch + log) and fmu_node.cpp (decls + CLI parse + start() call). px4 build links clean.
- **A2 (PENDING, coordinate):** cross, flood, cross-flood, outbound, battery-rth/landnow, boundary,
  storm. These arm members the CONTROL LOOP reads (m_floodArmed @ the flood async, m_obstacleArmed
  inside the emergency-boundary SAFETY block, m_batForce* in the battery inject). Production-dead, but
  removing them edits inside controlLoop (LOCKED SEARCH/APPROACH region) -- do it with the owner.
- **Bucket B (with the perception replacement):** approach / approach-real / approach-impact + the
  no-YOLO rig (m_useCannedApproachRig, updateCannedApproachRig), the HARDCODED SAFE ORBIT (~L1334),
  and the auto-land-the-instant-APPROACH-finishes (~L2273). These ARE the working demo and sit in the
  LOCKED path -- they get *replaced* by the modular vision-servo, not blind-deleted.
- **Dead now:** scripts/test/SITL/{forward,speed,rotate-land,land-flare,terrain-land,orbit,search} +
  voice_unit.sh reference removed flags. Archive with the SITL harness.

## fmu test harness rewrite: canned plans -> TestPlan enum + pure command map (2026-08-16, agent1)
- **What:** the "--canned-*" scaffolding is no longer 20 bools threaded through start() + ~20 inject
  methods inside FmuNode. Now: one `enum class TestPlan : i8` (None=-1=no test) in
  test/fmu_test_plans.hpp, `parseTestPlan(argv)` there (lifted out of main), a single private
  `runTestPlan(TestPlan)` switch in the node that arms the node-owned members (flood/obstacle/battery/
  rig) + feeds the scripted JSON, and the scenario JSON as free functions in that same test header.
  start() now takes ONE TestPlan argument.
- **#5:** translateToBaseCommands no longer string-compares down an if/else chain. It calls the pure
  `commandIdFromAction()` (command_id.hpp -- CommandID moved out of fmu_node.hpp) then switches on the
  returned CommandID. Behaviour identical; px4 build compiles + links clean.
- **Diagnosis (the point):** the canned plans were NEVER unit tests. Each needs the whole node + a
  SITL sim to mean anything and asserts nothing in-process -- they are end-to-end scenario DATA. The
  rewrite extracts the two genuinely pure pieces (commandIdFromAction, parseTestPlan) and puts a REAL
  ROS-free unit test on them (test/fmu_translate_test.cpp, ALL PASS). The guidance/servo laws are
  still welded to controlLoop with no unit coverage -- that is the next extraction, not done here.
- **Archived (referenced removed flags):** scripts/archive/SITL/{forward,speed,rotate-land,land-flare,
  terrain-land,orbit,search,battery,disarm-verify} + scripts/archive/voice_unit.sh.


## DjiBackend: Linux backend for the DJI-over-Android-LAN app (2026-08-17, agent)
- **What:** new CRTP sibling of PX4Backend/TelloBackend under source/llm_to_action/dji_backend/.
  Talks to the recon-swarm Android app (or scripts/test/dji_mock/mock_apiserver.py) over the LAN:
  WS /c/ws/sticks streams FlightParam{vx,vy,vz,yaw} (body m/s + yaw rate) at ~18 Hz (also the
  keepalive); httplib GET /status/ @15 Hz -> Odometry; POST /c/takeoff|/c/land. ROS-free, two
  std::thread loops, atomic telemetry -- same shape as TelloBackend.
- **Files:** dji_backend_base.hpp (PURE: endpoints/rates/clamp + ENU->FlightParam map + serialise,
  NO json so the FMU TU stays clean of nlohmann's -Werror noise), dji_status_parse.hpp (the nlohmann
  /status parse, included ONLY by the .cpp + tests), dji_ws.hpp (opaque WS client API), dji_ws_raw.cpp,
  dji_ws_wspp.cpp, dji_backend.hpp/.cpp. Wired: root CMake option GROUNDSTATION_BUILD_BACKEND_DJI
  (mutual-exclusion now count-based over PX4/TELLO/DJI/ALL), fmu selection + link, active_backend.hpp
  DJI arm, build.sh `dji`.
- **TWO WS clients, both tested (user request):** RawWsClient (hand-rolled RFC6455 over a raw POSIX
  socket -- DEFAULT, zero deps) and WsppWsClient (websocketpp + standalone Asio, opt-in via
  -DGROUNDSTATION_DJI_WS_WEBSOCKETPP). Selected by a compile-time typedef (no virtual). Raw client:
  handshake accept-key validation (inline SHA-1+base64), non-blocking connect+select timeout,
  TCP_NODELAY, SO_SND/RCVTIMEO, alloc-free masked-frame hot path, inbound pump (auto-PONG, honours
  CLOSE/EOF), clean reconnect. websocketpp offloads send to its io-thread (lower measured enqueue
  latency) but allocates per message and reuses the endpoint poorly across reconnects.
- **Verified against the live mock (standalone g++, no full CMake configure):** dji_convert_test OK;
  head-to-head dji_ws_test raw+websocketpp both PASS (connect, stream 90 frames, mock position
  advances ~4.9 m); dji_backend_mock_test PASS on BOTH WS configs (takeoff->FLIGHT, streamed +East
  1 m/s -> odometry vel=(1,0,0) + dead-reckoned pos, land->STANDBY).
- **UNCONFIRMED (isolated to one constant/spot each; flip after the app author/AircraftController.kt):**
  (1) yaw-rate sign kDjiYawRateSign in dji_backend_base.hpp -- CW+ vs CCW+; the mock cannot confirm it
  (its integrator ignores yaw). (2) velocity3D frame -- treated as ENU. (3) velocity envelope
  kDjiMaxSpeedMps/kDjiMaxYawRateRadps -- conservative until the author gives the virtual-stick limits.
- **Note vs stale docs:** mission-brief-2026-08-15 still says Agent-Backend is BENCHED and the platform
  is an emulated-Android-in-Docker bridge; superseded by spec-dji-backend + dji-apiserver-review (the
  teammate's Ktor app), which is what this backend targets. Video (H.264 over TCP) is still an
  app-author dependency, not consumed here yet.


## DjiBackend: recon-swarm source review vs the new camera commits (2026-08-17, agent)
Cloned ExoSkeletons/DJI-android-sdk-v5-recon-swarm and read ApiServer.kt / AircraftController.kt /
DJICamera.kt / SerializerUtils.kt directly. Findings:
- **VIDEO = RTMP PUSH, not raw frames.** The only streaming route is `POST /c/stream/start`
  {"rtmpUrl": "..."} + `/c/stream/stop` + `GET /c/stream/status`. DJICamera.startStream() builds
  LiveStreamSettings(LiveStreamType.RTMP, StreamQuality.SD, bitrate AUTO) and calls
  MediaDataCenter.liveStreamManager.startStream(). H.264 in RTMP/FLV, ~1-5 s latency, needs an ingest
  server WE run. This is exactly the transport dji-apiserver-review.md Q1 said to AVOID (breaks the
  <1 s see->act loop). The requested raw-H264-NAL-over-TCP frame path (ICameraStreamManager frame
  listener -> socket) was NOT implemented. cameraStreamManager is used only for local surface render.
  => decision for the manager before building a consumer: push the author for the TCP frame path, or
  accept RTMP + ingest + latency. NOT building an RTMP mock/consumer speculatively.
- **takeoff/land response bodies: STILL MISSING on the POST verbs.** `POST /c/takeoff` and
  `POST /c/land` call controller.fly{takeoff()/land()} with NO call.respond(). Only the top-level
  `GET /(fly|takeoff)` and `GET /land` (quickActionsRoute) respond ok(). Our DjiBackend POSTs
  /c/takeoff|/c/land and checks status==200 -> against the REAL app that will not confirm. Fix: app
  author adds call.respond(ok()) to the two POST handlers (1 line each), OR our client switches to the
  responding GET /takeoff + GET /land. Manager's call (contract).
- **No stick clamp app-side.** sendFlightParam buffers and flushes combined params at 18 Hz
  (TRANSMISSION_FREQUENCY_HZ) straight to vSticks.sendStickParam -- no coerceIn on the raw path (the
  coerceIn/maxVelocity clamps are only in the autonomous flyToSticks/lookAt/smoothVelocity helpers).
  So OUR client-side clamp (kDjiMaxSpeedMps / kDjiMaxYawRateRadps) is load-bearing. Real envelope still
  unknown (Q5 open).
- **/status matches the protocol (confirmed from SerializerUtils.kt):** velocity3D={x,y,z};
  attitude={pitch,roll,yaw}; position3D={latitude,longitude,altitude} (GPS -> invalid indoors, we
  dead-reckon). Our parser + mock use velocity3D{x,y,z}+attitude.yaw correctly. The mock simplifies
  position3D to {x,y,z}; real is lat/lon/alt -- harmless since we ignore GPS pos. FlightParam wire
  fields {vx,vy,vz,yaw} confirmed against AircraftController.FlightParam(vy,vx,yaw,vz) kotlinx decode.
- **NEW telemetry PUSH option:** `/c/ws/telemetry` WS streams {location,battery,velocity} (a different
  shape, no attitude). Lower-latency alternative to polling /status/; not consumed yet.
- **Tests hardened per manager:** dji_convert_test now covers real+mock+fuzz /status shapes, a
  rotation-norm frame invariant, clamp boundaries, and the wire field contract. dji_backend_mock_test
  is now a soak: 30 s / ~540 WS frames / ~450 polls, invariants checked every 500 ms -> 0 send-fail,
  0 poll-miss, telemetry fresh 59/59 (max 66 ms), dead-reckon 29.96 m. All PASS vs the mock.


## DjiBackend: telemetry-confirmed takeoff/land (2026-08-17, agent)
- **Why:** the app's POST /c/takeoff|/c/land send no response body (author omitted call.respond()), so
  trusting the HTTP ACK would misreport verbs against the real drone. Fix: takeoff/land now FIRE the
  POST (ACK is a best-effort fast path) then confirm the physical state from telemetry
  `aircraft.isFlying` (new atomic m_isFlying + confirmFlying(want,timeoutMs)). Drone state is the
  authority, not an HTTP reply -- the correct pattern regardless of the missing body.
- **Proof:** mock gained MOCK_SILENT_VERBS mode (POST verbs -> 204, no body = faithful to the app).
  10 s soak PASSES in BOTH modes: normal (ACK) and silent (204) -> takeoff OK/FLIGHT, land OK/STANDBY,
  0 send-fail, 0 poll-miss, telemetry fresh, dead-reckon 10 m. Manager feedback logged in
  dji-apiserver-review.md: POST verbs must respond; the GET /takeoff|/land verbs should be removed
  (GET fetches state, never performs an action). Video decision: SHIP CONTROL-ONLY now; video parked
  pending the raw-H.264-over-TCP path from the author (RTMP is unusable for the <1 s loop).


## DjiBackend: video transport CONFIRMED + Linux consumer proven (2026-08-18, agent)
The app dev pushed the raw-frame path we asked for (commits e92cf56 response, 2669183 tcp frame
stream, 95b7db3 update client, eff6ab6 tts route). Reviewed the actual Kotlin:
- **Video transport (frozen):** raw TCP. The phone LISTENS on DEFAULT_STREAM_PORT = **5600**
  (ApiServerService.kt), auto-started with the service (no start/stop route). Linux connects IN and
  reads a **raw H.264/H.265 Annex-B elementary stream**, written verbatim by VideoTcpServer.kt
  (`out.write(data, offset, length)` in the ICameraStreamManager.ReceiveStreamListener) -- NO framing,
  NO length prefix. Codec is logged once via `info.mimeType` (Mini 4 Pro likely H.265). ONE client at
  a time; TCP_NODELAY + keepAlive.
- **takeoff/land now RESPOND** (e92cf56): `call.respond(status{"taking off"/"landing"})` ->
  {ok:true,status:...} 200. Our telemetry-confirm (isFlying) is now a safety net; the fast ACK path
  works too. /c/stop also responds.
- **/tts route is intentional** (per manager): perception feeds "what it sees/understands" to the
  phone's TTS so the drone speaks it in the demo. Future Linux->phone integration: POST /tts.
- **Video mock added:** scripts/test/dji_mock/video_tcp_mock.py -- mirrors VideoTcpServer (TCP server
  on 5600, one client, streams a looped raw Annex-B clip, real-time paced). Make clips with gst:
  `videotestsrc ! x264enc ! video/x-h264,stream-format=byte-stream ! filesink` (x265enc for H.265).
- **Consumer proven end-to-end (Linux):** `gst tcpclientsrc host=<ip> port=5600 ! decodebin !
  videoconvert ! appsink`. decodebin is codec-agnostic -> decoded BOTH H.264 (227 frames) and H.265
  (224 frames) over TCP from the mock, same pipeline. GStreamer 1.24 + libav decoders present; gst +
  gst-app dev libs present (a C++ appsink consumer can be built standalone). Key gotcha: DJI emits
  Annex-B byte-stream; a clip must be byte-stream (not AVC) or h264parse says "no valid frames".
- **Next:** ROS-free C++ gst appsink receiver (model source/llm_to_action/gstreamer_udp_cam_rx/
  rx_node.cpp, but tcpclientsrc + decodebin, no ROS) that hands perception BGR frames.


## Camera receiver: one node, backend-selected pipeline + DJI TCP path (2026-08-18, agent)
Per manager (KISS/DRY, don't duplicate): extended the existing receiver
(source/llm_to_action/gstreamer_udp_cam_rx/rx_node.cpp) instead of forking a new one.
- **bool -> enum:** `GstReceiverNode(bool bUseTelloPipeline)` is now
  `GstReceiverNode(BackendType backend, std::string djiHost)`; the canonical `enum class
  BackendType { PX4, TELLO, DJI }` lives in generic_backend_types.hpp (the shared backend-types
  header, next to IOState/BackendStatus/Odometry -- NOT a camera-local header). main() parses `--tello` / `--dji [host]` / default PX4.
- **DRY:** only the SOURCE+DECODE prefix differs by backend (a one-time init switch); the
  `videoconvert ! BGR ! appsink` tail, the appsink->sensor_msgs/Image poll (PollSampleCb), and the
  bus poll are shared. DJI prefix = `tcpclientsrc host=<ip> port=kDjiVideoPort(5600) ! decodebin`
  (decodebin auto-selects H.264 vs H.265, so the node needn't be told the codec).
- **Perception untouched:** it already subscribes to the `camera/stream` Image topic and knows
  nothing of gst internals (fmu_node.hpp / perception_runtime.hpp use only rx_node_base.hpp types).
- **No templates:** the backend only picks the prefix STRING at init; the per-frame path is identical
  and gst_parse_launch builds the graph from a string at runtime anyway -- a compile-time
  specialisation would remove one init switch for zero runtime gain. Documented in-code.
- **kDjiVideoPort = 5600** added to dji_backend_base.hpp (the DJI wire source of truth, mirroring
  kTelloVideoPort). Header-only; no new link deps for the rx target.
- **Verified:** the exact DJI pipeline (tcpclientsrc ! decodebin ! videoconvert ! video/x-raw,
  format=BGR) decoded 197 BGR frames over TCP from scripts/test/dji_mock/video_tcp_mock.py. The ROS
  node compiles under the full ROS build (not runnable standalone here).
- **RENAME PENDING (coordinate):** manager wants gstreamer_udp_cam_rx -> gstreamer_cam_rx. Deferred:
  it edits fmu_node.hpp:28 + perception_runtime.hpp:43 (include paths) AND the UDP-prefixed shared
  names (UDPCamMsgType / kOutUDPCameraRawFrameTopic) the FMU uses -- collides with the in-flight
  fmu_node refactor. Do it once that lands.


## HANDOFF to the fmu-refactor (manager) agent (2026-08-18)
Renamed the shared camera-frame names across the receiver AND the two FMU files you own, as
directed. Pure token substitution -- no logic touched. RECONCILE with your in-flight fmu_node work:
- **New names** (rx_node_base.hpp): UDPCamMsgType -> **CameraPipelineMsgType** (+ h/kh variants);
  kOutUDPCameraRawFrameTopic -> **kOutCameraPipelineRawFrameTopic**; kOutUDPCameraGstSinkName ->
  **kOutCameraPipelineGstSinkName**; kOutUDPCameraRawFrameID -> **kOutCameraPipelineRawFrameID**.
  Topic string value is unchanged ("camera/stream").
- **Files I edited that are yours:** fmu_node.hpp (lines ~28, 256-257, 369, 1496, 2407, 2659, 2696 --
  8 type + 1 const token) and perception_runtime.hpp (~43, 52, 188, 212, 350 -- 5 type tokens). If you
  have uncommitted fmu_node changes, the tokens may have moved; the rename is mechanical, re-apply the
  two substitutions after your merge.
- **Also this session (mine, no overlap with fmu logic):** DJI backend complete (control + telemetry,
  two WS clients, telemetry-confirmed takeoff/land); video path proven (dev shipped raw H.264/H.265
  over TCP:5600; Linux decodes via tcpclientsrc!decodebin); the camera receiver now takes
  `enum class BackendType` (in generic_backend_types.hpp; was a bool) and gained the DJI TCP pipeline.
- **STILL PENDING (needs us to coordinate):** the directory rename gstreamer_udp_cam_rx ->
  gstreamer_cam_rx. It changes the #include path in fmu_node.hpp:28 + perception_runtime.hpp:43. Do it
  once your fmu refactor lands so we don't clobber each other.

- 2026-08-18 -- Thursday gate demo = new standalone module `source/llm_cv_scene/` (Python +
  OpenCV, isolated from the C++ `llm_to_action` tree on purpose). Architecture: fast eyes +
  slow brain. YOLOE (real-time, per-frame) draws always-on background detections and, on
  demand, highlights a phrase; SAM2 optionally turns that box into a tracked mask. Qwen3-VL-4B
  (GGUF on the repo's llama-server) is the on-demand brain: sees frame + detections + the
  spoken question, answers in natural language, and names what to highlight. faster-whisper
  push-to-talk. Four colour-coded overlays (grey background / green YOLOE / magenta SAM2 /
  amber VLM box) so detector-grounding vs VLM-grounding is visible side by side. Depth is NOT
  used here (metric depth is a flight-pipeline concern; its SITL flip-flop is structural --
  per-frame + per-frame normalization -- fix later with temporal consistency + a metric model).

- 2026-08-18 -- DJI end-to-end bring-up PREP (spec-dji-endtoend-bringup.md, Tasks A/B/C). Hardware
  not on the bench yet, so I built the parts that make bench time fast, all validated against the mock:
  - **Latency probe** `dji_backend/test/dji_latency_probe.cpp` (CMake target `dji_latency_probe`).
    Drives the REAL DjiBackend against any host:port; measures **command->action** (t0 = step
    setpoint emitted; t1 = velocity3D crosses a threshold in the next fresh telemetry sample -- both
    Linux steady_clock, single clock, no cross-machine sync). Steps in BODY forward and watches the
    velocity MAGNITUDE, so it's frame-agnostic (survives the unconfirmed velocity3D frame). Also
    reports telemetry GET round-trip. Retargets to the phone by changing host:port.
  - **Telemetry RTT timer** added to the backend: `m_statusRttUs` set in statusLoop around the GET,
    read via `statusRttUs()`. Diagnostics only, off the control path.
  - **Runbook** `docs/active/dji-bringup-runbook.md`: ordered A/B/C bench procedure, exact commands
    (phone build + tunnel-off grep, curl /status, standalone g++ line, probe, ws_latency.py, video
    decode line), and the empty latency table to fill.
  - Mock floor (localhost, no drone dynamics): command->action ~67 ms (= the 15 Hz poll granularity),
    telemetry RTT ~1 ms. The real link adds WiFi + rotor spin-up.
  - The three latency legs already had tooling: WiFi baseline = `ws_latency.py` (WS echo at command
    cadence); video glass->Linux = film a ms clock. Only command->action was missing a harness -- now built.
  - Verified via standalone g++ (full tree needs ROS/PX4); clean compile, probe OK against the mock.
    No git writes -- suggest a commit to the human.

## 2026-08-19 — llm_cv_scene highlight rebuild: YOLOE -> LLMDet open-vocab grounder
- Highlight backend swapped from YOLOE-26 (bounded-vocab, MobileCLIP text encoder) to an open-vocab
  PHRASE grounder: **LLMDet-tiny**, loaded via the transformers **MM-Grounding-DINO** implementation.
  Both `iSEE-Laboratory/llmdet_*` and `openmmlab-community/mm_grounding_dino_*` checkpoints report
  `model_type=mm-grounding-dino`, so `AutoModelForZeroShotObjectDetection` loads LLMDet on stable
  transformers >=5.15 — no git-main, no dedicated `llmdet` module needed.
- Why LLMDet: on-box benchmark (8 images, 27 esoteric/small/referring prompts, AMD ROCm) hard-hit
  rate **LLMDet 96% vs MM-GDINO 89% vs YOLOE 41%**; LLMDet uniquely found `backpack` + `ear cushion`.
  Matches published LVIS rare-class AP (APr): LLMDet 44.7 > MM-GDINO 34.2 > orig GDINO ~low-20s.
- Vendor-neutral: the grounder's multi-scale deformable attention uses transformers' pure-PyTorch
  fallback (no CUDA-only custom op), so the SAME code runs on ROCm/CUDA/CPU. Verified on ROCm 6.4.
- DINO-X / Grounding DINO 1.6 Pro rejected: cloud-API-only, would need internet at show time.
- Highlight now routes through Qwen3-VL: `vlm.py` resolves the referent to a groundable noun phrase;
  `app.py` lets that refine the deterministic regex target. Background stays fast YOLO26-seg; SAM2
  mask retained. Thresholds box=0.25/text=0.25, HIGHLIGHT_HZ=2 (grounder ~438 ms warm on ROCm).
- Cold-start: first ROCm/MIOpen kernel compile is slow; front-loaded by a startup warmup +
  `MIOPEN_FIND_MODE=2`. LLMDet weights pre-baked into the Docker image for a fully OFFLINE demo.

## 2026-08-20 — llm_cv_track: voice-driven tracked highlighting (follow.py)
- **follow.py** fuses VLM referent-resolution + BoT-SORT: voice/command -> Qwen3-VL resolves the
  referent ONCE on a frozen snapshot -> IoU-match to a track ID on that same frame -> BoT-SORT follows
  the ID live. Reuses llm_cv_scene vlm.py/ears.py (frozen). track.py stays as the pure-tracker playground.
- **Re-ID is a color histogram, NOT OSNet (the OSNet problem).** Ultralytics BoT-SORT Re-ID is
  proximity-gated (`emb_dists[iou_dist > 1-proximity_thresh] = 1.0` in bot_sort.py get_dists): appearance
  only rescues spatially-overlapping boxes, so a target that leaves frame + returns elsewhere gets a NEW
  id (Kalman box drifts off-screen -> ~0 IoU -> appearance never consulted). Bumping track_buffer /
  with_reid does NOT fix this. Our fix: an HSV hue-sat histogram fingerprint + re-acquisition ABOVE the
  tracker (follow.py `_hist`/`_reacquire`), independent of the tracker's re-id.
  - **Limitation:** distinguishes by clothing COLOUR only -> two people in similar colours can be
    swapped. Fine for single-subject / distinctive clothing; weak in a same-colour crowd.
  - **Upgrade path (post-gate):** OSNet appearance embedding (~2.2M params, pure-torch/ROCm-safe) as the
    fingerprint instead of the colour hist, or a proper re-id model wired into the tracker. Adds a dep +
    a small per-crop inference. Do this only if same-colour confusion shows up live.
- **Phase 2 detector feel-test (2026-08-20).** Apache open-vocab **OmDet-Turbo** (transformers, needs
  timm) finds the esoteric/referring objects YOLOE(AGPL) missed (mic 0.61, headphones 0.67, guitar case
  0.31, "the man on the left" 0.76), ~115ms/ROCm, no hallucination -> the YOLOE replacement. **D-FINE**
  (Apache, transformers) = fast closed-set COCO/person (~60ms) -> YOLO26 replacement. The human's named
  models **OV-DEIM** and **D-FINE-seg** are real+Apache but standalone repo clones -> deferred (OmDet
  covers open-vocab already). Full AGPL escape still needs a permissive TRACKER (ultralytics .track is
  AGPL). See docs/active/2026-08-20-phase2-detector-feeltest.md.
- **llm_cv_track re-oriented (2026-08-20).** Its PURPOSE = llm_cv_scene's voice loop with the highlight
  swapped to a proper real-time open-vocab detector -> clean SAM2.1 masks (fixing YOLOE/LLMDet's esoteric
  failures + bad masks). Priority #1 = detection+seg+masking; specific-object TRACKING is priority #2.
  - **highlight_seg.py (NEW) = priority #1.** Voice "highlight the guitar case" -> OmDet-Turbo (open-vocab,
    ~150ms) detects it every frame (box follows) -> SAM2.1 masks it. "what do you see" -> Qwen3-VL. Reuses
    frozen vlm.py/ears.py/eyes.py. Tracking-by-detection gives a following highlight WITHOUT a re-id tracker.
  - **follow.py = priority #2, PARKED.** BoT-SORT + colour-hist re-id: fragile (locks onto the wrong person
    when 2 are in FOV; IDs churn on exit/entry). Not gate-ready; needs OSNet for real person re-id. Revisit
    after detect+seg+mask is solid.
- **Gate passed (2026-08-20) -> Demo Day next.** The star (scene_omdet, OmDet->SAM2) + backup
  (llm_cv_scene, VLM->SAM2) both work. See source/llm_cv_track/README.md and docs/active/2026-08-20-*.
- **OmDet offline load FIXED (was hanging on HF).** OmDet-Turbo resolved its Swin backbone from the HF
  Hub every load -> hung under rate-limiting; pure offline failed because transformers resolves the null
  `backbone_config` via an HF API call. Fix: vendored /root/models/omdet-turbo-swin-tiny (copied
  checkpoint + a config.json with backbone_config baked in via OmDetTurboConfig.save_pretrained,
  use_pretrained_backbone=False); highlight_seg.OmDet loads it with HF_HUB_OFFLINE=1 + local_files_only
  + monkeypatched timm.create_model(pretrained=False). Result: ~1s load, zero network. Rebuild steps in
  the README. Also fixed this session: VLM off the ASR thread (no voice bottleneck), vlm.ask not
  vlm.analyze for Q&A (no JSON repetition garbage), os._exit(0) clean exit (no core dump/exit-144),
  tmux teardown on quit, ASR_CAPTUREID=5 (dead MOTU default mic).

## 2026-08-21 — DjiBackend yaw units/sign confirmed + fixed (risk #2 closed)
- Confirmed against ExoSkeletons `DJIVirtualStick.build()`: FlightParam.yaw feeds
  `VirtualStickFlightControlParam.yaw` under `YawControlMode.ANGULAR_VELOCITY` = **deg/s**
  (SDK `VirtualStickRange.YAW_CONTROL_MAX_ANGULAR_VELOCITY = ±100`). vx/vy/vz stay m/s (VELOCITY/BODY).
- Sign: DJI positive yaw = **CW** (heading increases) — from `AircraftController.spinBy/flyCircle`
  (`yaw = vel * clockwiseSign`, loop converges as `attitude.yaw` rises). Our interface is ENU **CCW+**.
- Fix in `dji_backend_base.hpp`: interface stays rad/s; at the wire boundary multiply by `kRadToDeg`,
  negate (`kDjiYawRateSign = -1.0`), clamp to `kDjiMaxYawRateDegps = 100`. Old `kDjiMaxYawRateRadps` gone.
- `dji_convert_test` updated to the deg/s+sign truth; still bench-verify the physical turn direction
  props-off once before trusting in-flight yaw. Mock floor unchanged: cmd→action ~66ms, telem RTT ~0.4ms.

## 2026-08-21 — drone bootstrapped; container-adb + isolated-server gotchas
- Full stack live: DJI drone flies, MSDK Aircraft app built from source + installed on GrapheneOS.
  Start the API server from the standalone **"API Server"** list entry, NOT "Recon Swarm (Fragmented)"
  (the latter bundles TTS+Qwen which crash and block server start).
- Container adb: `/dev/bus/usb` is a static snapshot; phone re-enumeration orphans the node. Fix with
  `exoskeletons/tools/adbfix.sh` (recreate node + restart adb). See 2026-08-21-drone-bringup-status-and-next.md.

## 2026-08-22 — real-drone field behavior + comms assessment (indoor/outdoor)
- **Indoor (uniform house, no GPS, weak VPS):** auto-takeoff tops out ~0.3 m (not the ~1.2 m
  default); FC REFUSES horizontal + vertical stick motion because VPS can't lock features.
  Yaw/rotate always works; vertical only creeps ~0.5 cm/s. This is DJI VPS-denial safety, NOT a
  comms fault — the commands arrive, the FC declines to move.
- **Outdoor (SLAM features present):** all sticks nominal, no drift, responsive.
- **Comms VERIFIED:** workstation->drone command channel + discrete verbs (/c/takeoff, /c/land,
  /c/stop) round-trip on the real link; transport latency p95 24 ms (WS) / 47 ms (telemetry) at
  1.5 m point-blank (docs/active/latency-2026-08-22).
- **Comms DEFERRED / UNVERIFIED:** continuous velocity control via /c/ws/sticks @18 Hz end-to-end
  through OUR software, and command->action latency (leg 4). Need an OUTDOOR session with the field
  unit (new laptop). Do NOT mark comms "fully validated".
- **Decision:** proceed on the workstation with feature-total-integration simple mode against the
  mock; the only change when the field unit returns is pointing at the phone IP.
- **API gap noted:** /status/ has NO height/altitude field and position3D is null indoors, so the
  workstation cannot observe altitude over HTTP; any closed-loop height control must use on-phone
  ac.height (e.g. AircraftController.ascendTo).

- Perception voice-out = the PHONE owns TTS. `llm_cv_scene` POSTs the VLM answer to the app's
  `POST /tts` ({text, lang, rate}); the phone speaks via Android TextToSpeech (TTSManager). The
  workstation never synthesizes -- espeak/piper in `voice.py` is desk-debug only. TTS host is the
  SAME phone as the video (derived from `host=` in `SCENE_INPUT`). Keeps LLM/perception fully out
  of the flight-control path.

## MVD integration — voice → 4-tier router → drone + perception on live video (2026-08-24)

The committed MVD (per `docs/integration-mvd-2026-08-24.md` + `demo-roadmap-2026-08-28.md`).
All code now consolidated in **`source/integration/`** (was scattered across `llm_cv_track`,
`llm_cv_scene`, `integration`). Python talks straight to the frozen ApiServer wire — the C++ FMU
engine is NOT in the loop.

### Architecture (the destination vs the MVD)
- **`fmu_node` (C++ llm_to_action) is the DESTINATION product, NOT the MVD.** The MVD router is
  thin Python hitting the ApiServer directly. Do not try to run/build the FMU for the MVD.
- Data flow:
  ```
  H key (keyboard_hook) · asr_server (Parakeet → /asr_server/transcribe)
      └ ears.py → router.py (4-tier) → dji_wire.py → phone ApiServer :8080
                       └ COMPLEX → scene_omdet (OmDet+SAM2+Qwen VLM) → answer/highlight
  video: llm_to_action_gstreamer_rx --dji → ROS2 topic camera/stream → camera_stream.py → scene_omdet
  ```
- 4 tiers, fixed order: EMERGENCY > OVERRIDE/RESUME > BASIC(regex verb) > COMPLEX(perception).
  Regex ported verbatim from the Android app `strings.xml`. LLM never drives motion.

### TESTED / successful
- **Router → wire → mock: GREEN.** All basic verbs, emergency (`stop/halt/abort/...`), override→manual
  (basic verbs swallowed), resume→auto, WS `/c/ws/sticks` dispatch — all verified against
  `scripts/test/dji_mock/mock_apiserver.py`.
- Consolidation into `integration/` compiles; router uses dual-mode imports (works as a package and
  flat via `python3 scene_omdet.py`).
- Transport latency (2026-08-22): WS p95 24 ms, telemetry p95 47 ms, zero loss.

### NOT tested / open (do not claim these work)
- **`camera_stream.py` compiles but is NOT runtime-tested** against a live `gstreamer_rx` + drone.
  bgr8 stride reshape matches rx_node's output encoding but needs one real-frame smoke test.
- **Never run end-to-end on the real drone.** Deferred (drone was indoors; VPS refuses lateral/vertical).
- Video into perception on the real link (roadmap open-question #2): now wired, not proven live.

### Key findings verified this session (avoid re-litigating)
- **`POST /c/stop` = `FlightControllerKey.KeyEmergencyStop`** (via `controller.stop(emergency=true)`,
  `DJIAircraft.stop`), NOT a hover-brake. It is the SDK motor-kill. In-air outcome is gated by the
  aircraft's `FCUrgentStopMotorMode` (IN_OUT_ALWAYS → motors cut, drone falls; NEVER → refused in air).
  `.action()` is fire-and-forget (no ack). The `dji_wire.py` docstring calling it "relinquish/hover"
  is WRONG. Our voice "stop" AND "manual" both fire it — a soft-handoff for "manual" is a real bug.
  Surest kill remains the phone API-server toggle + power button (CLAUDE.md).
- **Phone `VideoTcpServer` serves exactly ONE TCP client** — a new connection closes the previous
  ("Replace and close any previous client"). Two consumers on `:5600` (e.g. `gstreamer_rx` +
  scene_omdet's own `tcpclientsrc`) thrash and starve each other. Fix: rx_node is the SOLE `:5600`
  client → publishes `camera/stream`; perception subscribes (`SCENE_INPUT=ros`). This was the cause
  of the "waiting for tcpclientsrc" hang.
- **Phone IP = WiFi default gateway** (hotspot). A second default route (ethernet) shadows the
  `ip route` auto-fetch; pass explicit `PHONE_IP=` when both are up. IP changes per phone (was
  10.222.215.92, was 10.200.2.63 on a different handset).
- **Yaw units = deg/s** (app `DJIVirtualStick`); the C++ backend's rad/s was ~57× too slow. Sign
  (CW+/CCW+) still unconfirmed — never command real yaw until settled.

### Lessons for the next agent (unsuccessful attempts, so you skip them)
- Do NOT chase `fmu_node`/`llm_to_action` C++ for the MVD — it's the destination, not the demo.
- Do NOT propose webcam when the ask is drone footage; the MVD shows the DRONE camera.
- READ `docs/integration-mvd-2026-08-24.md` + `final-objective-context.md` FIRST; they answer the
  architecture unambiguously.

### 2026-08-25 — MVD integration COMPLETE (voice -> router -> DJI + smart CV)
Full detail + command table + backend tasks: `docs/active/2026-08-25-mvd-integration-handoff.md`.
The `source/integration/` MVD is DONE and considered effective. It is SELF-CONTAINED (no
llm_cv_scene/llm_cv_track traces). Shipped this session:
- 4-tier deterministic router (EMERGENCY>OVERRIDE/RESUME>BASIC>COMPLEX); expanded verbs — spin, scan
  (orbit OUTWARDS) / search (INWARDS), track/follow/come_home (phone-GPS), gimbal look forward/down/up
  (0/-60/+30), wave (hello/how-are-you), directionals -> native `fly_by` (POST /c/fly), a `go <unknown>`
  no-op guard. Full `dji_wire.py` REST client (all `/c/fly` actions, /key, /tts, /status).
- Phone ASR channel `phone_ears.py` matched to the app's real contract (POST /input + raw-TCP JSON on
  laptop :8080, dedupe, receipt logging). TTS `voice.py` -> phone /tts + laptop espeak (LONG/SHORT split;
  screen shows Scene:+Spoken:; speaks only SHORT). Verbose `[dji]`/`[phone_ears]`/`[voice]` logging.

### Key findings verified this session (avoid re-litigating)
- **`controller.fly{}` cancels the previous flight job AND `takeControl()`s.** So a new `/c/fly` mission
  preempts the running one -> our **`stop` = `POST /c/fly [{delay:0}]` (`halt()`)** stops motion AND keeps
  our stick control. `stop` no longer fires `/c/stop` and no longer latches manual (that latch was the
  "can't control after stop" bug). `manual` = RC handoff (`/c/stop`), `resume` = pop.
- **Gimbal sign:** `pitchCamera(-90)`=ground -> negative=down, 0=forward, +=up. Our `gimbal_pitch` JSON
  matches the DTO, but **gimbal is broken BACKEND-SIDE** (no angle responds except "look forward" from a
  fully-down gimbal). `fly_by` works.
- **`CircleFaceMode`** serializes by name: `"INWARDS"|"OUTWARDS"|"TANGENT"` (lenient JSON).
- **VLM port moved `:8090` -> `:18090`** — VS Code holds `:8090`; the earlier "GPU-wedged, reboot"
  conclusion was WRONG (plain port collision, diagnosed from container-side `ss` which showed no owner).
- **OmDet offline:** transformers 5.15 `backbone_utils` -> `HfApi.repo_exists(swin...)` hits the hub;
  no internet on the hotspot -> reset/raise uncaught -> OmDet dies. Fix: `highlight_seg.py` wraps
  `repo_exists` fail-safe to False -> timm builds the backbone offline; `run_mvd.sh` exports
  `HF_HUB_OFFLINE=1`.
- **Executor starvation:** `Ears` (`rclpy.spin`) and `CameraStream` (`spin_once`) fought the global
  rclpy executor; with ASR on, CameraStream starved -> "waiting for video" despite a live topic. Each
  now owns a `SingleThreadedExecutor`. (`--no-ears` masked it.)
- **VLM `-np 1`** — concurrent `/c/fly` VLM images overflowed the unified KV pool and segfaulted the
  mtmd decode. asusctl Quiet was only the trigger (GPU throttle -> requests overlapped).

### Lessons for the next agent (so you skip them)
- **CONTAINER ISOLATION:** the assistant's `pgrep`/`ss`/`tmux` view can be ISOLATED from the host's
  running processes. Do NOT conclude "app not running / port dead" from container-side checks — verify
  on the host. This burned a whole diagnosis ("phone_ears down" was false; the app was up on the host).
- Single `:5600` client on the phone `VideoTcpServer` — gst_rx must be the SOLE consumer; two thrash.
- Phone target for ASR must be the laptop's gateway IP (the app's `// fixme "0.0.0.0"`), or nothing arrives.

## 2026-08-26 — desk session: FMU build fix, hardware reality, doc corrections (manager agent)
Measured this session; corrections + new facts for the record. Demo is **Thu 2026-08-27 16:00**
(on-site 10:00-12:00), NOT 2026-08-28 — every doc + the filename `demo-roadmap-2026-08-28.md` say
28th; that is wrong. Filenames left as-is (human owns git); dates corrected in-content where load-bearing.

- **FMU (`llm_to_action`) was never broken — it just never built.** `fmu/CMakeLists.txt` backend
  selector had branches for PX4 and TELLO and NONE for DJI, so `FMU_SELECTED_BACKENDS` came back empty
  and the executable target was never created (`./build.sh release shared dji build` exits 0 having built
  nothing). +2 lines (a `dji` elseif) -> `llm_to_action_fmu_dji` links in 38s, 0 errors. It RUNS: 20 Hz
  loop, loads yolo26n seg+depth ONNX, attempts `ws://.../c/ws/sticks`, blocks at "waiting for first camera
  frame" (correct with no camera fed). Runtime needs `LD_LIBRARY_PATH=.../_deps/onnxruntime/.../lib`.
  SAFETY: this binary holds virtual-stick authority -> human-only vs any real phone IP.
- **C++ `dji_backend` is BEHIND the Python `dji_wire.py`:** it implements only takeoff/land/stop/sticks
  (+ "safe stop = land", no motor-kill). It has NONE of the 10 `/c/fly` mission verbs the Python wire has
  (fly_by, spin_by, scan_ground, track_me, follow_me, home, gimbal_pitch, wave, look_at, delay). The two
  control paths are NOT equivalent today.
- **Hardware: this machine is NVIDIA RTX 5070 Laptop, torch 2.11.0+cu128, CUDA 12.8** (NOT ROCm). The
  `config.py:22` "NO NVIDIA / ROCm" comment was stale -> corrected. FMU ONNX seg+depth run on **CPU by
  design** (keep them off the GPU so they don't starve the VLM) -- do not "fix" to GPU without proving it
  doesn't cut VLM inference.
- **Drone is a DJI Mini 4 Pro.** Indoor flight IS possible where there is enough space AND VPS locks
  (flown inside a classroom successfully); it degrades only when VPS can't lock (uniform/low-feature/low-light).
  So the demo verb set depends on VPS lock at the venue, not on indoor-vs-outdoor per se.
- **Phone ASR runs an ON-DEVICE model** (the app downloads the ASR model; transcription is LOCAL, not
  cloud). This SATISFIES the challenge's local/no-cloud constraint. The only residual is Android/Google
  telemetry (a privacy concern for the operator), NOT the ASR path itself. Laptop Parakeet is likewise
  local. [Correction: an earlier note in this block called the phone path "cloud ASR" -- that was wrong.]
- **Router test count is 7, not 11** (`test_router.py`: 7 functions, all pass). Corrected in handoff + ROADMAP.
- **`SCENE_HL_BACKEND` defaults to `vlm`** (Qwen3-VL grounds referent + SAM2 mask), not omdet, despite the
  handoff calling scene_omdet+OmDet "THE app."
- **RoboMaster S1: SDK ships DISABLED**; needs community unlock (firmware-gated). Field kit written to
  `source/robomaster/` (probe/text/video scripts + runbook + pre-purchase checklist). Acquisition PAUSED
  (seller asked to hold). EP/EP Core have the SDK out of the box.
- Handoff §12 "uncommitted files" list is now STALE — that tree is clean; all committed in fdbea61 + 1a972b2.
- **The MVD is ROS2-NATIVE -> the demo machine MUST have ROS2 (`/opt/ros/jazzy`).** Verified 2026-08-26:
  `integration/{camera_stream,ears,video_doctor,video_watchdog}.py` call rclpy directly; `scene_omdet.py`
  imports `ears`; `run_mvd.sh` sources ROS + runs 3 compiled ROS2 nodes (asr_server, keyboard_hook,
  gstreamer_rx); the drone video path is `SCENE_INPUT=ros` (gstreamer_rx -> `camera/stream` -> CameraStream).
  **The DEMO-DAY LAPTOP (this machine: RTX 5070, `/opt/ros/jazzy` present) runs the MVD** and is the box
  going to the venue -- ROS2 is there, so this is settled (no venue-machine risk). A separate Linux Mint box
  lacks ROS2 and is NOT the demo machine; irrelevant.

- 2026-08-27: Laptop TTS for final demo lives in `source/integration_tts/` (fork of integration/, original untouched). Voice-out was already built (voice.py speaks the VLM short answer via phone /tts); the fork adds a working laptop engine: piper (en_US-lessac-medium, /root/models/tts/) preferred, espeak-ng fallback. `SCENE_TTS=both` (default) = phone + laptop; `piper`/`espeak` force laptop-only. Engines installed machine-wide (apt espeak-ng, piper bin+voice downloaded).

- 2026-08-30: Full cleanup/takeover audit performed (5 parallel archeology sweeps: docs, C++, Python forks, scripts, transcripts). All open points aggregated with evidence into docs/active/2026-08-30-cleanup-takeover-audit.md (ID-tagged for priority markup). Headline ground truths: runtime drone-config EXISTS (scheduled doc stale); drone_config.hpp approach-speed default diverges from constexpr (80 vs 120 — real bug); CURVE/re-assess taught to LLM but silently dropped; repo backup from Aug-28 never completed; fresh clone non-functional (*.pt ignored, TTS unscripted, README quickstart dead).

- 2026-09-01: **Skill-stack ruling (owner ratified).**
  - KEEP: ponytail (on probation — judged on the next 2 MVD Python diffs; demoted to review-only if it ever cuts safety-relevant robustness).
  - KEEP: official /code-review (correctness lane), clangd-lsp, caveman, skill-creator.
  - KEEP: thermo-nuclear-code-quality-review (vendored from cursor/plugins, MIT, into repo .claude/skills so it travels) — rare, opt-in, findings-only scorched-earth pass.
  - DROP: code-simplifier plugin (duplicated by ponytail-review + built-in /simplify).
  - DROP: claude-md-management plugin (owner disabled it in .claude/settings.json 2026-09-01).
  - DROP: feature-dev plugin (duplicates built-in Explore/Plan agents and /code-review).
  - SKIP: mattpocock skills stack (improve-codebase-architecture + 3 dependencies) — its CONTEXT.md/ADR machinery conflicts with our docs structure; the useful rubric was extracted instead.
  - NEW: .claude/skills/architecture-survey/ — house skill with the deletion test, recent-change bias, Strong/Worth-exploring/Speculative labels; survey-only, reports to docs/research/, honest "codebase is fine" allowed.
  - Superpowers: untouched during the sprint; post-sprint, fold the systematic-debugging habit into CLAUDE.md and drop the plugin.
  - Review lanes: correctness bugs -> /code-review; over-engineering -> /ponytail-review or /ponytail-audit; whole-repo architecture -> /architecture-survey; pre-merge harsh audit -> /thermo-nuclear-code-quality-review.
  - Infra fact: devenv.sh bind-mounts $HOME/.claude into the container, so skills/plugins SURVIVE rebuilds — no install-script entry needed for them.

## The Recognizer + perception engine become components (2026-09-02, agent)
- **Recognizer** = the named pipeline for Hebrew input, single home `projects/integration_harden/recognizer/`:
  stage 0 emergency (greedy by ruling: עצור always stops; wait-intent stays expressible via חכה) ->
  bypass (full-match sentences -> mission, no model, 79/189 std coverage) -> Hebrew rewrites
  (number-words->digits; measured trouble words inlined as English, DictaLM passes Latin through;
  verb insertion; glossary) -> DictaLM translate (injected callable; CPU p50 199 ms) -> output
  guards (copy-echo retry; number check -> retry -> digit patch -> REJECT and read back to the
  user, per ruling) -> English rewrites -> route() (deterministic; movement verb beats perception
  clause; 100/100 + 240/243 offline).
- Measured, complete pipeline, 370 sentences: emergency 6/6, std 98% (planner ceiling), verbose
  85% (ceiling), perception 58% (DictaLM), military 55%; ALL 301/364. Bench: bench/hebrew-command-bench.
- **Perception engine** extracted to `projects/integration_harden/perception/`: engine.py = pure
  logic w/ injected models (relative-confidence gate, mask hygiene, VLM-box fallback, VLM presence
  gate); detectors.py = OmDet + Eyes moved verbatim; vlm_client.py = vlm.py + testable parse_reply.
  scene_omdet.py stays the glue. highlight_seg/eyes/vlm deleted (moved, git history keeps them).
- **Dedup ruling:** components live ONLY in integration_harden; the bench imports and measures
  them in place. No second copies.
- **Deployment topology (measured):** GPU = Qwen3-VL 3.8 GiB + OmDet 0.9 + SAM2.1 0.7 + ASR 0.1
  = 5.5 of 8 GiB; CPU = translators. Model split (tgemma) deferred to the future E2E ASR system;
  direct-Hebrew planning parked (the VLM must be resident for flight anyway).
- Tests: 26/26 (router 13, recognizer wiring 7, perception 6), all model calls faked.
  Trace recorder: traces/*.jsonl per utterance, gitignored.
- **Module clustering executed (2026-09-02, later):** integration_harden top level -> `control/`
  (commands, router, dji_wire: transcript->verb, deterministic, emergency-regex source of truth),
  `audio/` (ears, phone_ears, voice: the transcript inlets + the TTS outlet; ASR itself stays
  EXTERNAL in asr_node/sttserv), `video/` (camera_stream + doctor + watchdog). Glue stays top:
  scene_omdet.py, config.py, run scripts. Files moved verbatim, imports updated; camera_stream
  gained a self-contained webcam self-test (`python3 video/camera_stream.py 0`).
- **Verified after the move:** 26/26 tests, bench audit CLEAN, recognizer + perception self-tests
  CLEAN, scene_omdet imports OK, webcam self-test 18 frames/3 s, live_mock_smoke PASSED (all 4
  router tiers over real HTTP vs the mock). integration_harden README rewritten to match (it
  still described deleted files).
- **DEVNULL trap again:** live_mock_smoke spawned the mock with stderr=DEVNULL, which hid a
  missing-aiohttp error after a container rebuild. Mock output now goes to a log. Missing deps
  fix = tools/devenv/install-runtime-deps.sh (already scripted); tools/preflight.sh checks it.
- **Rulings 2026-09-02 (later), all executed:** (a) audio modules renamed to say what they are:
  ears.py -> ros2_asr.py, phone_ears.py -> phone_asr.py, voice.py -> tts_io.py (class names
  unchanged). (b) Emergency vocabulary single-homed: the Recognizer's stage 0 EMERGENCY_RE is
  the source of truth; control/commands.py now imports it instead of keeping a copy (direction
  FLIPPED from the old comment, which said commands.py was the source). (c) Top-level
  integration_harden/__init__.py deleted -- the top level is glue, not a module; tests run on
  the namespace package. (d) Runtime pip deps (aiohttp, sentencepiece) baked into
  tools/devenv/Dockerfile; install-runtime-deps.sh stays as the stopgap for running containers.
- **E2E Hebrew text-path verified live (2026-09-02, later):** full go-live wiring (Router ->
  Pipeline -> dicta CPU + Qwen3-VL GPU -> mock wire over real HTTP; VLM leg on a live webcam
  frame). 19 bench sentences, all four outcomes correct except the two KNOWN residues, both
  reproduced live: chain-initial takeoff planned as land; DictaLM answered a see-question
  instead of translating it. ASR session brief: docs/active/2026-09-02-asr-session-brief.md.
- **LLMDet bake removed from tools/devenv/Dockerfile (ruled 2026-09-02):** the model was
  demoted from the live system; pre-baking its weights only inflated every image build.
- **Ruling 2026-09-02 (late): the router-level emergency check STAYS.** The rule (EMERGENCY_RE)
  lives once, in the Recognizer; the router's one-line check is position, not duplication --
  it alone runs before the basic-verb matcher. Measured without it: "stop going forward" flies
  forward, "stop the spin" spins, "kill/abort landing" lands; in manual mode those stops are
  dropped with no halt at all. Recognizer stage 0 remains the net for COMPLEX text and for
  consumers that use Pipeline without the router (the bench). Follow-up (OPEN, ROADMAP item 7):
  single command catalogue post-sprint.
- **Residue rules measured (2026-09-02, latest): 301 -> 306/364.** takeoff-verb/noun-inline
  (chain-initial המראה/תמריא carried through as inline Latin "take off"; המראה homograph guarded
  against the-mirror readings) and stay-there-strip (duration-less closing "stay there" no longer
  becomes a planner {"delay":1}). std 184/185, verbose 50/53. Military -1 = probe artifact
  (open owner call); found a ±1-2 cross-run noise band on model-dependent sets — dicta restarts
  flip identical translations english<->reject; determinism is per-server-session only.
- **Routing is first-class (2026-09-03, review Tier-2 fix):** recognize() kinds are now
  emergency|mission|reject|command|perception; pipeline dispatches on kind and an unknown kind
  never reaches the flight path. Bench gates widened to the two new kinds (same behavior).
  Equivalence proven by full re-measure: 306/364, zero payload diffs vs the prior run.
- **Tier-1 dead-code purge landed (2026-09-03, subagent, verified by the manager):** +31/-374
  across 7 files (detectors 268->124, dji_wire 246->157, vlm_client 200->116, config 116->88);
  four real bugs fixed (TTS "both" double-speak default -> phone, watchdog --dji None guard,
  VLM-box fallback now mask-checked like the primary path, docstring path). Two documented
  skips: DjiWire.status() (typed home for a 3x hand-rolled SAFE endpoint) and DEFAULT_*
  (live caller router.py:44). Full report: docs/active/2026-09-03-deadcode-purge-report.md.
  NOTE for the desk test: the engine fallback-mask change alters live highlight behavior.
- **Review items 7-15 done (2026-09-03): Recognizer guard unified + structure pass.** One
  Hebrew number composer for stage 2 and the guard (hundreds compose; מטר אחד no longer
  double-counts) with symmetric and-a-half on the English side — full recheck 308/366, the
  +2 are two false rejects that became correct missions, zero other diffs. he_word() is the
  one home for the Hebrew boundary idiom; route regexes carry self-test evidence. Structure:
  on_text dispatch, sectioned config, one default_gateway(), shared FrameCounter, dead import
  fallback gone. Deliberate skips + reasons: the two 2026-09-03 reports in docs/active/.
- **ASR ruling (2026-09-03, owner):** ivrit-ai whisper-large-v3-turbo, Q5 quant, is the ASR
  choice for now — fast enough, among the most accurate measured. In-domain validation
  (team recordings -> transfer metric) stays open and is owner-paced; the pick may be
  revisited when that data exists.
- **Go-live wiring landed in production (2026-09-03, agent):** scene_omdet.py now runs the
  Recognizer on COMPLEX text -- Pipeline is the Router's on_complex, vlm_query=TextHandler.perceive
  (the live-frame perception path), say=voice/print. Hebrew commands become missions on the wire;
  see-questions route back to perception (UX unchanged, English-keyed); rejects are spoken. run_mvd.sh
  gained a DictaLM CPU pane (:18091, log ${TMPDIR:-/tmp}/mvd_dicta.log). Tests 26 -> 32 (added
  test/test_scene_wiring.py: 6 scene-level wiring cases, models faked). Gates green: pytest 32,
  import, live_mock_smoke, one real DictaLM translate ("Ascend ten meters"), parse_highlight
  English-safe. HONEST SCOPE: the wiring PATTERN was already E2E-proven via a harness (the
  2026-09-02 entry above); what is NOT yet booted is the production scene_omdet.py app end-to-end --
  deferred to the live-test session, runbook in docs/active/2026-09-03-golive-wiring-report.md sec 6b.
- **SAM verdict (2026-09-03/04, owner-ruled): adopt SAM3 int4-nf4 as ONE model replacing OmDet +
  SAM2.1.** Measured: nf4 886 MiB < the current pair 1273 MiB; 3.3x detections (332 vs 101 on 17
  images); masks on par (IoU 0.862); on-demand p50 366 ms. SAM3 is a CONCEPT segmenter (bare nouns,
  not instructions; no car->van generalization -> synonym fan-out). SAM3.1 video tracking SHELVED
  (activation-bound peak, infeasible on the 8 GiB RTX 5070). Follow-on: integrate nf4 + build the
  VLM->concept front-end. Evidence + load recipe: bench/sam3-mask-bench/INTEGRATION-HANDOFF.md.
- **Go-live fragilities flagged at close (2026-09-04, d4, read-verified not measured):** COMPLEX
  now runs SYNCHRONOUSLY on the ASR callback thread (translate + Qwen plan + fly_mission block it);
  the real-model command chain (DictaLM->Qwen->mission) has ZERO automated coverage (fakes only) --
  the desk test must exercise it; real DictaLM says "Ascend ten meters" not "go up 10 meters"
  (planner mapping untested); a reject TTS error shows as "[drone unreachable]". Detail: the
  go-live section of the 2026-09-03 manager handoff.
- **SAM3 integration module perception2/ committed (2026-09-04):** Sam3Backend (nf4|bf16|fp8 +
  torch.compile) + VLM->concept front-end + chain_demo, not yet wired into scene_omdet. Key finding:
  torch.compile is the speed lever, not the weight format (SAM3 is compute-bound). SAM3.1 tracking
  shelved (activation-bound ~7 GiB peak, infeasible on the 8 GiB RTX 5070).
- **SAM3.1 is a PRIORITIZED future task, NOT abandoned (2026-09-04, owner ruling — supersedes the
  "SAM3.1 SHELVED" framing in the two entries above):** SAM3.1 (video multi-object tracking) is the
  better production model and IS wanted; the open problem is quantizing it to fit the 8 GiB RTX 5070.
  The owner will spawn a dedicated session (~2026-09-05) to crack it. Starting point, measured this
  session: weight quantization does NOT lower the ~7 GiB tracking peak (activation/state-bound); the
  fix is true int4/fp8 COMPUTE (gemlite/marlin, blocked by the repo's mixed-precision forward + a
  direct .weight transpose) OR the AOTInductor route (compile off-box, specialize the spatial_shapes
  grid symint), OR a Hopper-class GPU. A custom llama.cpp fork can also run BASE SAM3 (one of several
  alt methods), but SAM3.1 is preferred. Detail: bench/sam3-mask-bench/results/sam3-quantization.md
  and INTEGRATION-HANDOFF.md; memory sam3-quantization-insights.
- **Desk test defined and staged (2026-09-04, owner-ruled):** the live desk test bootstraps
  integration_harden into a real runnable system. Step 1 = the owner's desk: his microphone ->
  Hebrew Whisper ASR -> Recognizer -> command/perception -> JSON on the REST wire -> MOCK server,
  WITH the real drone camera feed via gstreamer_rx from the phone MSDK server (video is one-way,
  so a powered drone on the desk is safe). Step 2 = outdoors, same chain, REAL control, run by the
  human. Step 3 = latency and per-component performance, deliberately NOT defined yet (see below).
- **Roles on the desk test (2026-09-04, owner ruling):** the live-test AGENT writes and adapts the
  scripts; the OWNER runs them. The agent never boots the stack and never speaks into the mic. All
  logs collect to files so the agent can diagnose mid-session on request.
- **New desk-test scripts live in tools/desk-test/, NOT in integration_harden (2026-09-04, owner
  ruling):** production files are fixed in place, but new test-harness scripts must not clutter
  integration_harden.
- **Two gaps block the desk test, both found 2026-09-04 by the manager:** (a) the mock discards
  what it receives -- mock_apiserver.py fly() reads the /c/fly body and returns only a step count,
  and takeoff/land/stop print nothing, so the mock cannot show what the system sent; (b) run_mvd.sh
  line 162 hardcodes --backend=whisper-parakeet --language=en, which cannot transcribe Hebrew.
  Both are ruled FIXED before step 1.
- **ASR for the desk test: quantize ivrit whisper-large-v3-turbo to q5_k_m (2026-09-04, owner
  ruling):** the owner chose q5_k_m over the existing q5_1. On-disk sizes for comparison: q4_0
  452.0 MB, q5_1 595.2 MB, q8_0 833.7 MB, fp16 1549.3 MB, all under
  /root/models/asr/ivrit_ai/whisper-large-v3-turbo/. Whether whisper.cpp's quantize tool accepts a
  q5_k_m type for Whisper models is UNVERIFIED and is the first thing the live agent must check; a
  q4_k Whisper GGUF does exist on disk (xviers-whisper-large-v3-turbo-gguf), so k-quants exist for
  Whisper, but the tool's accepted type list is not confirmed.
- **Hebrew ASR changes which path a command takes (2026-09-04, measured from the code, behavioural
  not a bug):** the router's basic-verb table in control/commands.py is ENGLISH-keyed, so with
  Hebrew ASR those verbs never fire and every non-emergency utterance goes COMPLEX into the
  Recognizer. That is the intended architecture -- the Recognizer owns the Hebrew sieve. EMERGENCY_RE
  (recognizer.py:43) is BILINGUAL (stop/halt/abort + עצור/תעצור/סטופ/חירום), so the emergency stop
  survives the language switch. Consequence for the desk test: a model (DictaLM + Qwen) writes the
  flight plan for most Hebrew commands, which is why the mission JSON must be read before any real
  flight.
- **Step 3 (end-to-end latency + per-component performance) is DEFERRED, undefined by ruling
  (2026-09-04):** the owner ruled it is not defined enough to plan and will be scoped when reached.
  What exists today: recognizer/trace.py writes one JSONL line per utterance and pipeline.py:83
  records a single total `ms` plus kind/flags/action/payload. That covers the Recognizer only as one
  number -- it does not split translate, plan, wire or perception time, and records nothing for ASR.
  Per-component latency therefore needs new instrumentation before step 3 can run.
- **`q5_k_m` is NOT a whisper.cpp quantize type (2026-09-04, verified by the live-test agent):**
  the owner-ruled ASR quant `q5_k_m` does not exist in whisper.cpp's quantize tool. Accepted types
  are q2_k q3_k q4_0 q4_1 q4_k q5_0 q5_1 q5_k q6_k q8_0; the 5-bit k-quant is `q5_k` (ftype 13).
  `q5_k_m`/`q5_k_s` are llama.cpp mixture policies with no whisper.cpp equivalent. Passing `q5_k_m`
  fails ("unknown ftype" -> "invalid model type -1", exit 1) and leaves a corrupt ~596 KB partial
  file. OWNER RULED 2026-09-04: produce q5_k + q4_k + q4_0 (all three now on disk under
  /root/models/asr/ivrit_ai/whisper-large-v3-turbo/; sizes q5_k 547.4 MB, q4_k 452.0 MB, q4_0 452.0 MB
  -- q4_k and q4_0 tie at 4.5 bpw). Desk-test default = ggml-model-q5_k.bin. Inference-time + accuracy
  benchmark (perhaps FLEURS) deferred. Script: tools/desk-test/quantize_hebrew_asr.sh.
- **llm_to_action "presentable for the judges" scoped (2026-09-05, owner ruling):** DEMO POLISH is
  primary; code-quality cleanup is secondary and BOUNDED -- the owner's words were "I lean towards
  option 2 more than 3" and "don't be so sure we're going to perform the QC cleanup to the degree
  that you expect". A separate "repo hygiene / CMake tidy" scope was proposed by the manager,
  questioned by the owner, and WITHDRAWN. The fmu_node.hpp refactor is NOT in scope for this
  session; it keeps its own tasklist. Brief: docs/active/2026-09-05-llm-to-action-presentable-brief.md.
- **Gazebo is CHEAP, correcting a manager assumption (2026-09-05, owner):** a Gazebo/SITL run takes
  "a couple of minutes not an hour". The manager had argued against behaviour-sensitive work on the
  premise that per-slice Gazebo verification was expensive; that premise was wrong and the argument
  is withdrawn. Behaviour-touching changes are verified in Gazebo per slice, as the fmu tasklist
  already required.
- **Judge-facing surface is the A2 dashboard (2026-09-05, manager finding):** source/dashboard/
  serves annotated camera + depth colormap + flight HUD + VLM reasoning log to a browser. Two
  verified defects that would break a live demo: (a) its README's run command points at
  `scripts/dashboard/serve.py`, a path that DOES NOT EXIST -- the real file is
  projects/llm_to_action/source/dashboard/serve.py; (b) every dashboard topic publishes only when
  the FMU runs with FMU_OBSERVABILITY=1, so with the gate off the dashboard shows a silent blank
  with no error. Also: llm_to_action has NO top-level README at all.
- **Hebrew ASR quantization settled (2026-09-05):** q5_k_m is NOT a whisper.cpp ftype (verified by
  running whisper-quantize; accepted types are q2_k q3_k q4_0 q4_1 q4_k q5_0 q5_1 q5_k q6_k q8_0,
  and the 5-bit k-quant is spelled q5_k = ftype 13; the M/S mixture suffixes are llama.cpp-only).
  Owner ruled q5_k plus q4_k and q4_0; all three produced. Sizes: q5_k 547.4 MB, q4_k 452.0 MB,
  q4_0 452.0 MB. NOTE: q4_k and q4_0 are byte-identical in SIZE (473,992,235) but differ in content,
  so q4_k bought no size saving on this model. FLEURS accuracy bench for the new quants is DEFERRED.
- **REST API resync to the recon-swarm ApiServer (2026-09-05, owner-directed):** the Kotlin app
  (/root/DJI-android-sdk-v5-recon-swarm, author ExoSkeleton, last 5 days) changed `POST /c/fly` to a
  BARE JSON array of Actions (was `{"mission":[...]}`), added new endpoints (/tts, /key, /c/flyTo,
  /c/lookAt, /c/(wave|hi|hey|hello), /c/stream/*, quick GET /takeoff|/fly|/land, WS
  /c/ws/echo|gimbal|telemetry), and discrete verbs now return `{ok,status}` bodies.
- **All four dji_wire clients synced to the bare-array /c/fly (2026-09-05):** integration_harden,
  integration_notify, integration_tts, AND integration. Action `type`/field schema verified unchanged
  against dto/actions/*.kt; only the array wrapper changed.
- **FREEZE EXCEPTION, owner-authorized 2026-09-05:** projects/integration/ (the frozen demo fallback)
  WAS edited for API compatibility, because it must still work if integration_harden is not ready.
  This is a one-line compat fix, not a feature change; the freeze otherwise stands.
- **tools/dji_mock/mock_apiserver.py rewritten to mirror the current ApiServer.kt (2026-09-05):** all
  endpoints + response shapes, command logging preserved, smoke-tested.
- **DEFERRED: the C++ DjiBackend REST/telemetry sync (owner-ruled 2026-09-05):** dji_backend does not
  POST /c/fly (sticks-velocity track), so the mission change does not break it now; its /status
  telemetry parsing must be resynced to the new Velocity3D/LocationCoordinate serializers WHEN
  llm_to_action is integrated. Tracked, not done.
- **Overlay Hebrew went blank = python-bidi missing in the APP's ROS python (2026-09-05):** the
  scene_omdet overlay falls back to ASCII (strips Hebrew -> blank) when `import bidi` fails. It logs
  `[scene_omdet] Hebrew overlay off (PIL/bidi/font missing)`. A container rebuild wipes ad-hoc pip
  installs, so after a rebuild run tools/devenv/install-runtime-deps.sh (has python-bidi), or
  `source /opt/ros/jazzy/setup.bash && python3 -m pip install python-bidi`. The render code is fine;
  it is purely the missing dep. Check that log line before diagnosing "blank Hebrew".
- **Qwen3-VL-4B adopted for the FMU loop (owner-decided 2026-09-05/06):** move to Qwen3-VL-4B
  Q4_K_M, fix its issues, and ship IF the UI "looks sensible and describes what is impressive".
  Applied in sim_core.sh (env-overridable back to 2B). 4B verified standalone on the RTX 5070
  Laptop: 4097/8151 MiB VRAM with mmproj, text 0.078 s, vision 1.06 s per 320x240 frame.
- **fmu_node.hpp is intentionally throwaway ("vibecoded") code (owner ruling 2026-09-05):** its
  cleanliness is a NON-goal; do not spend effort refactoring it. The control-loop smell catalog
  (docs/active/2026-09-05-fmu-control-loop-smell-catalog.md) documents the test hooks and the
  real-flight hardcodes (APPROACH bbox-anchor, ORBIT fixed circle, auto-land gate) for the record.
- **Auto-land-after-APPROACH ended every multi-step mission (measured 2026-09-06) — guard applied:**
  the vlm pre-flight (takeoff, approach car, move back, orbit, land) collapsed to approach->auto-land->
  "mission complete"; move-back + orbit were skipped. Guard at fmu_node.hpp:2244 now fires auto-land
  only when the task queue is empty. Compiles; NOT yet SITL-verified end-to-end — the owner runs
  rubicon_orbit to confirm. Log: projects/llm_to_action/test/sitl/runs/vlm/captured_panes_log.txt.
- **Depth-model study COMPLETE; the perception fork is OPEN (2026-09-06, post-meeting decision):**
  master table bench/depth-sota-bench/DEPTH-BENCHMARKS.md. Path A = depth-anything.cpp ggml
  in-process (same stack family as llama.cpp/whisper.cpp; DA3 metric-large q8_0 176 ms Vulkan,
  bit-exact vs PyTorch) vs Path B = Python torch service (DA3-small GPU 38.5 ms). Root-caused: DA3
  RELATIVE models segfault on Vulkan (metric + DA2 fine). Current prod yolo26n-depth-384 ONNX
  CPU-2t = 44 ms / 22.5 Hz and is the "schizo" depth to replace. Quality (AbsRel) is UNMEASURED —
  needs ground truth (Gazebo GT depth). Fixing depth removes the APPROACH/ORBIT/auto-land hacks
  (same root cause); real target-centered orbit is impossible without reliable metric depth.
- **Global-doc merge of the 2026-09-05/06 lane work done by the manager (2026-09-06):**
  ARCHITECTURE.md gained the §15 "Reconciliation (2026-09-06)" block (real-flight hacks vs spec,
  depth fork, 4B swap) + a dated status update in the Voice-pipeline section (desk-verified chain,
  mock resync, desk-test harness, dataset recorder, overlay); the stale ~13 Hz depth-thread figure
  is corrected in §2. Judge diagrams: docs/active/2026-09-06-architecture-diagrams.md.
- **Whisper VRAM estimate heuristic (owner ruling 2026-09-06):** until a census rerun, a whisper
  GGML model's resident VRAM is estimated at about its FILE SIZE, give or take a few MiB. So
  q5_k (547.4 MB file) is carried as ~550 MiB, labeled estimate. The earlier "ASR 0.1 GiB" figure
  was the MEASURED wav2vec2-300M (104 MiB, census 2026-09-02) and must not be carried onto whisper.
- **Judge diagrams doc rewritten after the owner's line-by-line review (2026-09-06):** the current
  MVD is integration/* (FROZEN, English by design; phone-Hebrew out of scope there) and gets its
  own diagram; integration_harden is the successor and is drawn separately; the two stacks share
  only three llm_to_action utility binaries + the ApiServer wire protocol (the "same VLM" and
  "video integration point" cross-links were wrong and are removed -- the FMU runs its own
  llama-server); the wire is drawn as ONE endpoint chosen at boot (mock 8079 | phone 8080), not
  two runtime paths; router tiers + the full basic-verb dispatch table added from control/router.py;
  Recognizer stages use the code's own names (0 emergency filter, 1 bypass, 2 Hebrew rewrites,
  3 injected translate, 4 output guards, 5 English rewrites, 6 routing) and the Qwen planner is
  correctly placed in pipeline.py, NOT as stages 4-6; perception + perception2 get staged diagrams
  (presence gate -> OmDet low floor -> relative-confidence gate -> SAM2.1 -> mask hygiene -> VLM-box
  fallback; concept extraction -> synonym fan-out -> one SAM3 forward); the desk test is a numbered
  sequence diagram; the resource table cites the census per row and marks the whisper row estimate.
- **Judge diagrams doc, second revision to mechanism depth (2026-09-06):** after the owner's
  second review round, every section now carries its control flow in prose (thread, order, rate,
  destination, and the WHY of each choice) with file:line witnesses; validated twice — a scripted
  witness pass (37/37 citations match the code, one drifted line fixed) and a mermaid lint
  (10 blocks, 0 issues). New code-verified facts folded in: the FMU voice inlet
  (fmu_node.hpp:405 — deterministic emergency land/hold, grounded start, airborne user_command
  interrupt), maybePlan's trigger conditions + first-frame/first-detection warmups
  (fmu_node.hpp:1496), the 30 Hz offboard rationale (px4_backend_base.hpp:41-46 — PX4 needs ~1 s
  of streamed setpoints before OFFBOARD; 40 @ 30 Hz warmup), the post-backend chain
  (px4_backend.cpp:97-131 — sole 30 Hz publisher, ENU->NED, arm->OFFBOARD retried to confirm),
  the two-rate vision loops (33 ms seg / 80 ms depth, fmu_node_base.hpp:87-88; depth input = the
  same camera frameSource), the snapshot consumer split (VLM at plan time; control loop only in
  APPROACH/FOLLOW/ORBIT/SEARCH; GO is odometry-only), and the frozen MVD's on_text fall-through
  verified in its own code (integration/scene_omdet.py:195-215).
- **Overlay Hebrew double-bidi (2026-09-06, root-caused live):** the app's PIL is built WITH Raqm
  (features.check("raqm")=True), which applies the bidi algorithm natively in ImageDraw.text(); our
  get_display() pre-reversal therefore DOUBLE-reversed -> Hebrew shown backwards. Fix in scene_omdet:
  when Raqm is present pass the raw logical string; get_display only as the no-Raqm fallback. Overlay
  block reformatted to an aligned label column (En/Kind/Cmds/Action, mono font DejaVuSansMono).
- **Phone TTS dies with the drone link (2026-09-06, measured):** the recon-swarm app gates ALL routes
  (incl /tts) behind the RC/aircraft/product connection check -> when the drone sleeps (eco), /tts
  returns 503 and nothing is spoken (observed: early posts HTTP 200, later all 503). Options: exempt
  /tts from the gate (app-side, dev), or a local espeak/piper fallback on phone-503 (tts_io supports
  backends). OPEN - owner to rule.
- **"complex->perception" was a recorder artifact (2026-09-06):** the Router labels every COMPLEX
  res.action "complex->perception"; the SessionLog recorded that constant instead of the pipeline's
  real outcome. Fixed: pipe.handle is wrapped to record the true action (mission/reject/perception);
  the router label is only a fallback. The TTS "narration" heard on some commands was the REJECT
  path speaking "לא הבנתי, שמעתי: ..." (guard rejects: DictaLM answered instead of translating, or
  ASR-garbled numbers) -- by design, not a routing bug.
- **EMERGENCY_RE coverage gap (2026-09-06, live):** "תפסיק הכל"/"תפסיק שליטה" are NOT caught by the
  emergency regex (עצור/תעצור/חירום/סטופ only) -> went COMPLEX, no halt. Adding תפסיק is a
  Recognizer change: bench-gated (recognizer-bench skill, measured, zero-false-fire). OPEN.
- Overlay font gotcha (2026-09-06): DejaVuSansMono has NO Hebrew glyphs (boxes). Fix: fonts-freefont-ttf
  FreeMono = the only installed mono font with Hebrew; config.py now resolves SCENE_HE_FONT -> FreeMono ->
  DejaVuSans (fallback, alignment lost). Install scripted in install-runtime-deps.sh + Dockerfile.
- Live-50 run (2026-09-06): report + raw at projects/integration_harden/sessions/session-20260906-231140-rog/
  (REPORT.md). 33/48 full pass; 0 unintended flight on traps/negations; 3 wrong-motion missions, all
  ASR-garble->LLM-confabulation or a one-off spin+0.5 magnitude flub.
- DictaLM hallucination root (measured, same run): instruct-tuned translator flips to ASSISTANT mode when
  the content is a question or "you"-addressed — answers instead of translating (10/14 questions; 0/30
  imperatives). Fix candidates (bench-gated, OPEN): few-shot question exemplars, forced "English:" prefix,
  interrogative-strict prompt.
- Router gaps (same run, OPEN): presence/attribute questions (יש מישהו / מה הצבע) end planner-empty, VLM
  never queried; mixed move+see drops the see-half; תפסיק gap reproduced (standing, bench-gated).
- ASR he-forced residuals (same run): אחורה->סחורה persists; הדגש את ה->הדגשת ה prefix-merge; ארובה->ערובה.
- Bench grew 370->388 (2026-09-07, owner-ordered live-run additions): 18 cases from the 2026-09-06 desk
  session; full re-run 323/382 (85%), zero regressions, scorecard updated in place, old table archived.
  NEW catch: l_land_going (האם אתה הולך לנחות בקרוב) makes the planner LAND; מתכוון phrasing passes.
- Rethought open decisions (owner review pending, details in session REPORT.md): (1) SUPERSEDED — Qwen-as-Hebrew-front-end was already measured and REJECTED
  (results/HISTORY.md rounds 5-6: 42% / 38% perception, unreliable Hebrew noun lexicon, "the VLM path
  requires a translator in front of it"); remaining levers: DictaLM forced-prefix or revisit the
  TranslateGemma deferral; (2) PERCEPTION_RE extension
  proposal with positives/negatives, flips v_q2's file; (3) תפסיק->EMERGENCY yes / פוס-משחק no;
  (4) interrogative-forces-empty planner guard, blocked on the polite-request-question spec.
- Half-turn 0.5 root cause (2026-09-07): NOT the planner. Number guard patched DictaLM's correct
  "Turn right 180 degrees" to "Turn right 0.5 degrees" (Hebrew extractor read חצי=0.5; unit idiom
  חצי סיבוב=180 crossed). Fix direction: Hebrew-side חצי+סיבוב composition or no-patch-on-unit-words.
  Bench l_half_cw covers only the benign path. Evidence: traces/session-20260906-231146.jsonl utt 30.
- DictaLM temp-0 divergence within a session = llama.cpp KV-cache split nondeterminism (single slot,
  n_past 85-95 varies with the shared prefix of the PREVIOUS request); same class as the bench README
  ±1-2 noise band. Greedy decoding is only as deterministic as the logits.
- Interrogative-guard proposal WITHDRAWN (owner): l_land_going is plain answer-mode (raw JSON shows the
  hallucinated answer Qwen landed on); polite-question spec already ruled by r_pol_* cases (fly).
  q_land_trap's bench pass is luck — it hallucinates too.
- tgemma VRAM demystified (2026-09-07, measured): census 3,035 MiB was 4-slot x 4096-ctx f16-KV server
  DEFAULTS; at -c 512 / 1 slot it is 2,552 MiB (q8 KV: 2,521), identical output, 50-token worst-case
  prompt. Lean config fits the SAM3-nf4 end stack with ~370 MiB spare (mmproj/YOLO/fragmentation
  unmeasured); Q3_K_M requant = the comfort lever, quality gate pending. Table in
  bench/model-cpu-or-gpu/README.md addendum.
- Full VRAM census (2026-09-07, measured, supersedes yesterday's arithmetic AND the ~550 whisper
  estimate): whisper q4_k 743 / q5_k 838 / fp16 1841; dicta lean 1187; tgemma lean 2552; qwen prod
  3821 (lean 3738); yolo 286. Real free ceiling 7598 (440 driver carve-out). All-on-GPU at Q4 does
  NOT fit (over by ~600); fits = tgemma-Q3+whisper-CPU (+638) or tgemma-CPU (+1850). Full scenario
  table: bench/model-cpu-or-gpu/README.md addendum. OPEN owner ruling: which component leaves
  the GPU (tgemma vs whisper) or tgemma Q3 requant (quality gate needed).
- REAL co-resident VRAM (2026-09-07 night): full owner stack loaded together = 7,505 MiB, 93 free of
  8,151. SAM3-nf4 (886) does NOT fit -> over by ~793. ASR measured via the real asr_server node
  (q4_k 734, q5_k 829), NOT whisper-server. Qwen image ask (1280x720 q80) = 1,236 prompt tokens,
  +89 MiB transient, e2e 2,911 ms -> image path is not a residency risk. tgemma sys-prompt 74 tok,
  worst perception input 115 tok -> -c 256 is plenty. tgemma CPU p50 1,599 ms (was quoted 624 for
  short commands; perception is 2.6x longer). DictaLM on CPU confirmed fine. Table: census README.
  OWNER RULING NEEDED: which model leaves the GPU so SAM3 fits (tgemma frees 2,479 / whisper 829).
- SAM3 + Hy-MT2 wired behind FLAGS, defaults unchanged (2026-09-07 late, agent call -- OWNER to rule):
  `SCENE_SEG=omdet|sam3` picks the highlight backend (scene_omdet `build_highlight()`; sam3 = one
  perception2.Sam3Backend, OmDet+SAM2.1 never load) and `MVD_TRANSLATOR=dicta|hymt2` picks the
  stage-3 server on :18091 (recognizer/run_hymt2_server.sh, -c 512 -np 1, Vulkan). Defaults stay
  on the proven demo path (omdet + dicta) until the live test passes; the next stack boots with
  `SCENE_SEG=sam3 MVD_TRANSLATOR=hymt2 bash tools/desk-test/up.sh`. preflight checks the pairing
  (hymt2 on the GPU requires sam3) and the SAM3 deps. tmux window `dicta` is now `xlate`
  (log mvd_xlate.log). Deps scripted: bitsandbytes 0.50.2 + accelerate 1.14.0 in
  install-runtime-deps.sh + Dockerfile (they were wiped by a rebuild; SAM3-nf4 needs both).
- SAM3 live-path concepts KEEP attributes (agent call, OPEN): `perception2.phrase_concepts` strips
  only the article and fans out bare categories; the VLM concept front-end (drops colours by its
  prompt) is off the live path -- "the white car" must not highlight every vehicle. Evidence that
  SAM3 discriminates attributes: sam3-mask-bench RESULTS.md Web candidates finding 2. SAM3 forwards
  are rate-limited to one per SCENE_SAM3_PERIOD (1.0 s) per phrase because the highlight worker runs
  every frame and a ~0.45 s forward would hog the GPU shared with Qwen and whisper.
- Step 6 number guard fixed the SMART way (2026-09-07, gated): `חצי סיבוב`/`חצי הקפה` compose to
  180 on the Hebrew side and "half a turn|rotation|revolution|circle|spin" to 180 on the English
  side, so a correct "180 degrees" AND a correct "half a turn" pass unpatched; `חצי מטר` stays 0.5.
  patch_number now matches decimal tokens (0.5) bounded so it never edits inside 10.5. Full 413-case
  re-run vs the same-day baseline: 339/407 -> 339/407, ZERO Recognizer output diffs (the bench's
  DictaLM never emits the 180 phrasing; the positives live in the self-test + test_recognizer.py
  `test_half_turn_keeps_a_correct_180`). compare_runs.py = the per-case diff tool.
- bench.py grew `--translator dicta|hymt2` and `--tag` (raw JSON name suffix). Hy-MT2-Q4 through
  the FULL Recognizer + planner: 342/410 (std 193/201, verbose 43/54, perception 90/128, military
  9/20) -- reproduces the campaign's lost-harness row (345/410) within the noise band. The +3 net
  hides a swap: +14 perception, -4 std, -7 verbose. Hy-MT2 failure classes (OPEN, bench-gated):
  (a) "עם כיוון השעון" rendered COUNTER-clockwise = sign flip (combo3, combo5, v_finish3_g3) ->
  fixed by the clockwise-inline / counterclockwise-inline HE rules (Latin token pass-through,
  re-measured below); (b) literal register: "Wait, make sure you are ready" makes the planner add
  a wait step, "שנייה אחרי זה" becomes "a second after that" -> delay 1 (v_first3_g0/g2,
  v_ready3_g0/g3); (c) possibility/past phrasing the planner refuses: "It is possible to take off",
  "Let's fly", "Climbed to a height of 10 meters" -> [] (r_takeoff2/3, r_land4, r_alt10). Candidate
  lever for (b)+(c): few-shot CONTENT (imperative register exemplars), count stays 2 -- owner call.
- census.py `--sam3-stack` measures the ruled topology co-resident (Qwen prod script + Hy-MT2
  server + REAL asr node + YOLO + SAM3-nf4 + one image ask). Its import path was stale (llama.py
  moved to recognizer/) -- fixed. Servers are killed by process group, never `pkill -f llama-server`.
- Step 5 (whisper k-quants) is the OWNER's to run: the agent's `rm manifests/*.json` and
  `run.sh --step prep` were blocked by the permission classifier. Command in the campaign doc §8.
- RULED TOPOLOGY FITS, at Q4 only (2026-09-07 late, measured together, `census.py --sam3-stack`):
  Qwen 3,821 + Hy-MT2-Q4 1,187 + whisper q5_k node 827 + YOLO 282 + SAM3-nf4 1,074 + image transient
  94 -> used 7,396 / 8,151, 313 MiB free. SAM3-nf4 costs 1,074 in-process, NOT the 886 isolated peak
  the campaign budgeted, so the paper margin (~600) is really ~313 and Hy-MT2-Q6 (+326) is out.
- Clockwise/counterclockwise inline rules SHIPPED with the flip disclosed (2026-09-07 late): Hy-MT2
  verdict gate vs an in-memory rules-off control = 5 flips: combo3, combo5, v_finish3_g3 (rotation
  SIGN fixed), v_ready3_g0 fixed; v_note3_g3 pass->fail (Hy-MT2 splits the sentence at "Note:" and
  the planner drops the last step; the English is correct). Zero false fires. DictaLM: counts
  identical. bench.py now persists per-case planner verdicts ("verdicts") so compare_runs.py can
  list flips; runs before this session lack them. Owner may veto the rules (handoff §11.5 item 3).
- down.sh could not free :18091 (2026-09-08 00:3x, owner-reported): the listener belonged to uid 1000
  and was INVISIBLE in this container (host networking shares the port space; the process lived on
  the host or in another container). It accepted TCP but never answered HTTP (a wedged or half-dead
  server), with ~50 live + ~1,400 TIME_WAIT root-owned client connections churning at it from
  outside too. Nothing inside the container can kill such a process. Fixes: (1) preflight.sh and
  down.sh now say "held by a process OUTSIDE this container (uid N)" and print the host command
  (`sudo ss -tlnp | grep :PORT`); (2) the translator port is overridable end to end with
  `MVD_XLATE_PORT=18092 bash up.sh` (run_mvd -> server script -> pipeline.py). The foreign
  listener was VS CODE PORT FORWARDING (owner, 2026-09-08): VS Code had forwarded :18091 and its
  forwarder holds the port from the host side. Stop the forward in the VS Code Ports panel before
  booting, or boot with MVD_XLATE_PORT=18092.
- LIVE Step 1 (2026-09-08 00:37, DictaLM stack, live-test-50): 38/50. Causes: ASR 6 (אחורה->סחור,
  זוז->זו, עשרים->עשרה, הדגש את->הדגשת x2, ארובה->ערובה), DictaLM answer-mode 3, router see-question
  gap 2 (יש מישהו, מה הצבע), תפסיק emergency gap 1. SAFETY: the land-trap question (#28) made
  DictaLM reply "To land, please say Land" and the planner SENT LAND (it did not on 2026-09-06 --
  DictaLM is unstable run to run); ad-hoc "תחזור הביתה" -> "Return home" -> planner sent LAND;
  ASR garble flew wrong spins (#5, #8) that the number guard cannot see. Report:
  sessions/session-20260908-003702-rog/REPORT.md.
- NO answer-mode guard exists in the Recognizer (only the few-shot copy guard and the number guard);
  the interrogative guard was withdrawn 2026-09-07 and the remedy chosen was Hy-MT2 (answer-mode 0
  on the bench). Proposed stage-4 guard (OPEN, owner deferred to after Step 3): reject an English
  line that reads as a reply ("No,", "Yes,", "I am", "I see", "I can", "please say ..."): strict
  retry first, then REJECT + read back. Evidence: 4 live utterances 2026-09-08. Gate: full 413 run,
  both translators, zero flips on correct cases.
- LIVE Step 3 (2026-09-08 01:02, Hy-MT2 + SAM3 stack, live-test-75): 41/69 scored. Report:
  sessions/session-20260908-010129-rog/REPORT.md. Causes: Hy-MT2 register 6 (past tense /
  possibility -> planner refuses), Hy-MT2 wording 3, Hy-MT2 numbers 3 (bare מטר -> "six meters" x2,
  caught; סיבוב וחצי -> 180 flew for 540), MY guard bugs 3 (punctuation glued to tokens, ש clitic on
  שחצי -> false rejects), ASR 6, planner 3, router 2, emergency 2. Land trap HELD on Hy-MT2.
- HIGHLIGHT PATH NEVER REACHED for "Follow" / "Focus on" / "Emphasize" (2026-09-08): engine FIND_RE
  knows highlight/locate/track/mark/find/show me/point at/where is only; both translators use the
  other three for עקוב/התמקד/הדגש -> every such request became a VLM question in BOTH live runs.
  Fix = extend FIND_RE + LEAD_VERB_RE (perception/engine.py). check_colors() is dead code (never
  called in recognize()) and COLORS lacks סגול.
- PLANNER FEW-SHOT ECHO (safety, 2026-09-08 u74): "Do it!" made Qwen emit its own example mission
  (takeoff, dz+4, spin 90, dx+6, land). The copy guard covers translator shots only. Candidate
  guard: refuse a mission identical to a PLANNER_SHOTS_D mission.
- Post-Step-3 fixes (2026-09-08 ~02:00, owner approved items 1, 2, 3, 6; items 4 and 5 held):
  (1) perception/engine.py FIND_RE + LEAD_VERB_RE now accept follow / focus on / emphasize (+ "stop
  following" clears) -- the highlight path is reachable for עקוב/התמקד/הדגש at last; (2) number guard
  tokenizer strips ASR-glued punctuation ("חמישה...", "מטר.") and reads a clitic on חצי (שחצי);
  (3) סיבוב וחצי = 540 on both sides (HE_TURN_HALF_RE / EN_TURN_HALF_RE) so "a half turn" for a turn
  and a half is caught; (6) stage-4b answer-mode guard: a first-person reply ("I am", "I see",
  "please say", "my primary function") is retried with strict=True ("Translate ONLY ... Do not answer
  it"), then REJECTED + read back. translate() contract grew `strict` (pipeline, bench, app wrapper,
  test fakes). Self-test positives/negatives for every rule; 38 tests green. Bench gate: see the
  next entry.
- First gate of the answer-mode guard (2026-09-08 ~02:30, DictaLM, items 1+2+3+6): the wide pattern
  caught every trap but also rejected three CORRECT translations -- "I can fly up five meters"
  (r_pol_up5, polite request the planner flies), "I will fly up 20 meters and describe..." (v_mix1),
  "I have visual contact with the command post" (s_cp_visual, a correct report). Narrowed to the
  measured shapes: "I am / I'm / I see / I cannot / I can't" (sentence-initial, optional No,/Yes,),
  "please say", "my (primary) function", "as a drone/AI". Hy-MT2 on the same gate: 2 outputs
  changed, 0 flips (j_pin_halfgate now passes; s_cp_visual was the false fire, fixed by narrowing).
- Bench scoring of REJECTS changed (2026-09-08): a reject on a must-not-fly case (expected []) is
  CORRECT-reject (nothing flew, the user heard the read-back); a reject on a real command is REJECT
  and counts as a fail. Before, both were "routed" and dropped from n, which hid rejected commands.
  Baselines re-scored offline under the new rule: DictaLM std 201/203, verbose 50/54; Hy-MT2 std
  197/203, verbose 44/54.
- Items 4 and 5 applied (owner: "apply those fixes too", 2026-09-08 ~02:20): (4) stage-2
  `explicit_one_meter`: a bare מטר with no number on either side -> מטר אחד (15 מטר, מטר וחצי, מטר
  אחד, מטרים untouched); (5) pipeline `is_shot_echo`: a planned mission identical to one of the
  planner's six few-shot missions, from English carrying none of that example's numbers, is
  refused and read back (action "reject-planner-echo"). recognizer/__init__ now exports _nums_en.
  bench/whole-system/run_list.py = text-mode run of a live-test list through the
  real translator + planner (no mic), judged against the list's expected notation.
- Gate of all six 2026-09-08 fixes (both translators, 413, per-case flips): DictaLM 339 -> 346 (5 flips,
  all safe: four traps now CORRECT-reject, l_land_going planner-LANDED -> reject); Hy-MT2 345 -> 348, 0
  flips against. Text-mode 75 list: DictaLM 45/7/23, Hy-MT2 36/16/23 -- Hy-MT2's past-tense/possibility
  register costs it 8 lines (planner refuses statements). DANGER (DictaLM): "יאללה נחת" -> "Take off".
  Tables: sessions/text-runs/2026-09-08-live-test-75-{hymt2,dicta}.md.
- RULING (owner, 2026-09-08): retests, including the retest of any new translator prompt, run on the
  WEBCAM (`VIDEO=webcam SCENE_TTS=off bash /root/groundstation/tools/desk-test/up.sh`), never on the drone + phone. Webcam mode mocks the
  whole system with nothing connected; the phone/drone are for final demo footage only. The mode has
  existed in run_mvd.sh/up.sh (VIDEO=webcam) throughout -- the runbook wrongly steered to the hotspot,
  which cost the owner ~12 hours over two days. Phone TTS is absent in webcam mode: SCENE_TTS=off.
- DAY-2 RERUN (2026-09-08 morning): all suites green (39 tests, 3 self-tests, bench audit); bench 413
  reproduced last night EXACTLY on both translators (0 of 413 outputs changed, 0 flips): DictaLM
  346/412, Hy-MT2 348/412. Raw: results/2026-09-08-recognizer-{dicta,hymt2}-day2.json.
- live-test-75 REBUILT as v2, ALL 75 NEW (owner: unique sentences only; v1's Set 1 had been drawn
  from the dataset by my misreading). Set 1 = dataset-style fresh sentences. Text-mode results:
  Hy-MT2 42 pass / 10 fail / 23 review; DictaLM 44 / 8 / 23. Set 1 alone: Hy-MT2 23/25, DictaLM
  21/25. Tables: sessions/text-runs/2026-09-08-live-test-75v2-{hymt2,dicta}.md. Filing after the
  owner rules: commands std 50, perception 10, verbose 9, emergency 5, military 1.
- New guard findings from v2 (candidates, not applied): (a) "סיבוב שלם" -> DictaLM "one full
  revolution" -> the number guard reads "one" as 1 vs nothing in Hebrew -> FALSE reject (1 measured;
  the symmetric fix is סיבוב שלם = 360 on both sides, like the 180/540 idioms); (b) DictaLM
  answer shapes the answer-mode guard does not know: "There are five people standing near the
  entrance." (caught by the number guard, safe) and "To the right, there's a large tree..." (NOT
  caught, sent to the VLM as the question); (c) "תן לי תצפית על הצומת ודווח" routes to the planner
  (PERCEPTION_RE lacks תצפית/דווח) -> EMPTY on both.
- PERFECT-ENGLISH CONTROL rerun on the current dataset (2026-09-08, `bench.py --perfect-en`, the
  hand-written reference English straight to Qwen3-VL): std 201/204, verbose 45/54 = 246/258. The
  PLANNER alone loses 12: r_mis5 (return-leg sign), l_postpone + l_pause_idiom (a "hold off two
  minutes" becomes a delay), and NINE verbose chains where the literal reference ("a second after
  that", "Wait, make sure you are ready", "and also") makes the planner add a delay/wait step or merge
  axes. Hy-MT2 (197 + 44) translates faithfully and inherits those planner faults; DictaLM (202 + 50)
  paraphrases them away and beats the "perfect" reference on verbose. Consequence: the "שנייה" and
  preamble losses are PLANNER issues (prompt or a Hebrew rewrite before translation), and Hy-MT2's
  own gap is the statement register only (4 std + 1 verbose). Raw: results/2026-09-08-perfect-en.json.
- V2 translator prompt SIZE (2026-09-08, measured on the live Hy-MT2 server's /tokenize): system + 2
  shots + a long input = ~516 tokens (V1: ~107). The live server ran -c 512 -> raised to -c 1024 in
  run_hymt2_server.sh (KV cost is a few MiB; the co-resident margin was 313). The bench serves -c 4096.
- Self-kill gotcha, second form: `pgrep -f '<model name>' | xargs kill` inside a long bash -c chain
  matches the CHAIN'S OWN command line (the pattern is in it) and kills the chain. Never match process
  names from inside a script whose text contains them; kill by saved PID only.
- V2 TRANSLATOR PROMPT MEASURED AND REJECTED (2026-09-08, Hy-MT2, 413 cases, `--prompt v2`):
  341/412 vs 348 with V1. It fixed the register class (verbose 44 -> 51: every planner-inherited
  filler/statement loss; std: r_takeoff2/3, r_land4, r_alt10, combo4 now CORRECT) but broke ten std
  cases, three of them in the UNSAFE direction: r_pol_spin (90 -> -90), r_low (dz +2 -> -2), r_neg4
  (a negation now FLIES 4 steps); five became number-guard rejects (r_bit_left/up, r_quart_r,
  r_wait1, r_ord4); perception dropped 91 -> 83; 273 of 413 outputs changed. On the 75 list the total
  stayed 42/10/23 but line 6 flipped sign (+20 -> -20) and line 11 lost its land. A 1.8B translator
  does not absorb a six-rule prompt; it trades one error class for sign errors. V1 stays the default
  (MVD_TRANSLATE_PROMPT=v1). Untested option: V3 = V1 prompt + rule 1 (register) + the two new shots
  only, one gate. Raw: results/2026-09-08-recognizer-hymt2-v2.json, sessions/text-runs/…-hymt2-p2.md.
- WHISPER ON THE CPU MEASURED (2026-09-08, `bench/hebrew_asr/cpu_latency.py`, 20 real push-to-talk
  clips from the 2026-09-08 session, p50 2.4 s of audio, large-v3-turbo q5_k, beam 4, same build as the
  node): latency p50 = 10.2 s at 4 threads, 6.9 s at 6, 5.5 s at 8 (RTF 2.5-4.6; the cost is the fixed
  30-second encoder window, so short clips do not help). GPU Vulkan = 0.29 s p50 (0.51 p95). Verdict:
  whisper stays on the GPU; the "whisper to CPU frees 827 MiB for TranslateGemma" option is DEAD on this
  laptop. Remaining ways to seat TranslateGemma (needs ~750 MiB): drop the YOLO background (282) +
  tgemma Q3_K_M requant (~500, quality gate unrun) = borderline; tgemma on the CPU (measured p50 1.6 s
  perception / 0.6 s commands); or the 16 GB desktop.
- GEMMA 4 E4B PROBED (2026-09-08, llama-server Vulkan, gemma-4-E4B-it-qat-UD-Q4_K_XL + mmproj-BF16):
  resident 3,950 MiB WITH its 1 GB vision projector (Qwen3-VL-4B: 3,821) -> replacing Qwen AND the
  translator (1,188) would free ~1,060 MiB. DIRECT-HEBREW PLANNING (no translator; the bench's revised
  prompt + Hebrew sign addendum + Hebrew shots + JSON grammar): 8/10 on a probe -- the 3-step chain,
  "שנייה אחרי זה" with NO delay, יאללה נחת -> land, negation, אל תנחת+תעלה, חצי סיבוב שמאלה, the
  land-trap question -> [] (safe); misses: אפשר להמריא -> [] and סיבוב וחצי -> 180. p50 351 ms.
  VISION: understands the image and Hebrew questions natively (people, parked sedan, distant white
  car, motorcycles, shop fronts), 5.5 s per 1280x720 ask vs Qwen ~3 s, but it NARRATES a "thinking
  process" as plain content even with --reasoning-budget 0 / enable_thinking=false, so free-text
  answers exhaust max_tokens before the LONG/SHORT lines -> vlm_client parse fails. Fix path: a GBNF
  grammar for the LONG/SHORT/HIGHLIGHT format (as the planner does). Server gotchas: --image-min-tokens
  1024 breaks its CLIP load (image_max_pixels < image_min_pixels); KV q4_0 + flash-attn gave empty
  output; `setsid llama-server` forks, so the saved PID is the parent -- stop it via
  `ss -tlnpH 'sport = :18090'`. Gemma-4-12B (7.1 GB Q4) cannot fit next to anything on 8 GB.
  Web (2026-09): Gemma 4 12B MMMU-Pro 69.1; Qwen3-VL-4B DocVQA 95.3 vs Gemma 4 26B 94.9 -> Qwen3-VL
  stays at least as strong per parameter on vision benchmarks; no E4B vision numbers or vision
  fine-tunes found; Gemma 4 = 140+ languages incl. Hebrew, audio input on E2B/E4B/12B.
  OPEN owner idea: Gemma 4 E4B as ONE model for Hebrew planning + VLM (drop the translator), with
  whisper + SAM3. Untested at scale: the 413-case direct-Hebrew run and a grammar-forced VLM format.
- VISION COMPARISON Qwen3-VL-4B vs Gemma 4 E4B (2026-09-08, whole-system/vlm_compare.py, SAM3 as the
  reference, 26 images): gate agreement 88/104 vs 91/104; "boiler" false-present 0/26 both; box IoU
  median 0.47 vs 0.02 (Gemma cannot localize); people count exact 11/26 vs 2/26; format 104/104 both
  with the grammar (Gemma needs it); latency p50 2.2 s vs 1.6 s. Verdict: Gemma gates as well and
  faster, boxes useless (we use SAM3's anyway), counting much worse. No labels exist: agreement, not truth.
- GEMMA 4 E4B AS PLANNER (2026-09-08): perfect-English ceiling std 195/204, verbose 51/54 (Qwen: 201/204,
  45/54). DIRECT HEBREW, no translator (bench --planner gemma4 --direct-he): std 195/203, verbose 52/54 =
  247/257 -- at Qwen's perfect-English ceiling (246/258) and above the current Hy-MT2 pipeline (241) with
  NO translation stage; fails: אפשר להמריא/לנחות -> [], r_higher, r_mis5, r_mis8, r_wait1, l_postpone,
  l_pause_idiom, v_start4_g3, v_mix1. Qwen direct Hebrew (reference): 187/203, 35/54. The lanes crashed on
  a scorecard division by zero (perception skipped) before writing JSON -> fixed, rerun for the raw files.
- WHOLE-SYSTEM OFFLINE TEST (2026-09-08, owner: "make it self-contained inside bench"):
  bench/whole-system/{run_all.sh, README.md, results/<date>/}. Lanes: 1 audio replay (session
  clips -> whisper-cli -> Recognizer -> planner, `run_list.py --from-clips`, clips matched to list lines
  by token overlap), 2 bench 413 (+ --direct-he, --planner gemma4), planner ceiling (--perfect-en),
  3 vision (whole-system/vlm_compare.py), 4 live mic on the webcam. Decision rule: a candidate stack
  must match or beat the current one on lanes 1-3 with zero unsafe flips before lane 4. Lane tools
  stay in their own homes; the runner only sequences them.
- AUDIO REPLAY LANE first run (2026-09-08, after the six fixes, the live sessions' own clips ->
  whisper-cli q5_k beam 4 -> Recognizer -> planner): Step-1 session vs live-test-50: Hy-MT2 35 pass /
  2 fail / 20 review, DictaLM 34/3/20 (57 clips matched by overlap, 8 ad-hoc/repeats unmatched); Step-3
  session vs the v2 list: Hy-MT2 18/14/21, DictaLM 23/9/21 (35 unmatched = v1's Set 1). The live runs
  on the same audio before the fixes scored 38/50 and 41/69. Reports: bench/whole-system/results/2026-09-08/.
- HIGHLIGHT CHAIN + PLANNING PER CASE (2026-09-08, whole-system/results/2026-09-08/vision-sam3-chain.md,
  planning-per-case.md): with the object present (42), Qwen says present 28 and SAM3 hits from its phrase
  22; Gemma says present 35, SAM3 hits 28 -> Gemma delivers MORE correct highlights; its VLM-box
  fallback is unusable (3/35 vs Qwen 13/28). Planning: Gemma direct 247/258, Hy-MT2 241, DictaLM 252;
  Gemma's misses carry no wrong direction/sign (two EMPTY idioms flown as delays, אפשר ל -> []).
- RELOCATION (owner: "keep the features self contained", 2026-09-08): everything whole-system-specific
  now lives in bench/whole-system: run_list.py (text + audio replay), vlm_compare.py (VLM vs SAM3),
  vision_chain.py (SAM3 from each VLM's phrase), planning_table.py (per-case planning table), run_all.sh,
  results/<date>/. sam3-mask-bench keeps only the images; hebrew-command-bench keeps bench.py and its raw
  JSON. Earlier paths in NOTES/handoffs were rewritten to the new home.
- OVERLAYS (2026-09-08, owner: "I want to see what Qwen3-VL and Gemma 4 highlighted with their boxes and how
  they work with SAM3 against the ground truth"): whole-system/overlays.py draws, per image and phrase, a
  three-panel jpg (VLM box yellow, SAM3-from-VLM-phrase green, SAM3-on-concept magenta = reference) ->
  results/<date>/overlays/index.md. vlm_compare.py now keeps the FULL reply and the parsed box per row
  (the first run truncated replies at 300 chars and lost some VLM_BOX lines). There is no human ground
  truth for these images; the reference is SAM3 on the asked concept.
- Vision rerun with full replies (2026-09-08 late): identical numbers; 104 overlays drawn -> bench/whole-system/results/2026-09-08/overlays/index.md.
- OWNER IDEA (2026-09-08, open): SAM3 as a standalone tool the LLM calls, dropping the Qwen3-VL presence
  gate for highlight requests (saves one ~2-3 s VLM call). Measured today from vlm-compare.json: SAM3 alone
  at score >= 0.5 said "present" for the absent phrase "boiler" on 0/26 images (the VLM gate: 0/26).
  The VLM stays needed for questions, descriptions and counts. Missing number: SAM3's false-present rate
  against real labels (the 20 desk frames) and the score threshold that zeroes it.
- 2026-09-08 (owner instruction, scheduled AFTER the judge meetings): consolidate the repo documentation.
  Owner + agent go through every document one by one, build a map (what connects to what, stale vs current),
  then write 2-3 cohesive documents that describe everything in the repo. NOTES.md is exempt (dumping ground).
  The documents aggregate performance metrics over history, what was measured, why, the design consideration
  behind it, and the other technical decisions. Full note: docs/active/2026-09-08-session-handoff.md §16.
- 2026-09-08 15:10 MEASURED (lane 3c, bench/whole-system/sam3_alone.py -> results/2026-09-08/sam3-alone.md):
  SAM3 alone as the presence gate, scored against the CONSENSUS of the Qwen3-VL and Gemma 4 gates (not human
  truth; 89/104 asks, 15 disputed omitted): max score >= 0.5 -> 82/89 (6 false presents / 61 absent, 1 miss / 28
  present, desk frames 28/28); >= 0.7 -> 83/89; >= 0.8 starts missing (6/28). "boiler" (absent by construction)
  got zero detections on all 26 images even at a 0.05 floor. SAM3 detect p50 451 ms vs Qwen gate 2150 ms.
  Of the 7 disagreements at 0.5, at least 4 look like VLM-consensus errors (windows/cars in street scenes; a truck
  called a car). Nobody in this session can view images (no Read tool) -> the owner settles 22 asks by eye in
  side-by-side.md or fills labels/presence-2026-09-08.template.json and reruns --score. Ruling still OPEN.
- 2026-09-08 15:40 OWNER PROPOSAL (open): replace the whole stack with whisper q5_k + Gemma 4 E4B Q4 + SAM3 (+ YOLO).
  Evidence per claim with verdicts, numbers copied from the raw files: bench/whole-system/results/2026-09-08/
  stack-swap-evidence.md. Supported: Hebrew planning 247/258 with no translator (no wrong direction/sign in the 11
  misses), highlight chain 28/42 vs Qwen 22/42, vision asks 1520 vs 2150 ms, Q4 file. Not supported: counts 2/26,
  own boxes IoU 0.02, no Hebrew router/number guard/live grammar, no audio replay or live run. VRAM: the saving is
  the translator (~1,100), Gemma itself is +90 vs Qwen in the same harness; new stack ~6,300 derived, unmeasured.
- 2026-09-08 15:55 OWNER RULINGS: (a) the v2 75-list will not be spoken live; (b) TranslateGemma will NOT be used
  (open decision 1 closed); (c) the remaining §12 not-done items are low priority; (d) measure Gemma 4 E4B as the
  TRANSLATOR on the 413 bench, before (v1 prompt, 2 shots) and after (TranslateGemma's instruction, zero-shot):
  bench.py --translator gemma4 [--prompt tgemma]; (e) the 75 v2 sentences must be filed into the dataset by their
  `file:` set (agent deferred it by mistake). OPEN QUESTION: freeze integration_harden for real-drone testing and
  fork integration_harden2 on the new stack. Agent view: the SAM3 + Hy-MT2 switches already prove the runtime-switch
  route (one home, zero duplication); a copy doubles every fix and breaks the bench import path (it imports
  projects/integration_harden/recognizer). Frozen fallback precedent: projects/integration/.
- 2026-09-08 16:10 RULINGS: FORK DECIDED -> projects/integration_harden2 (copy) hosts the Gemma 4 stack; harden stays
  clean for tomorrow; copy after the harden go-live commit. Emergency words הפסק/תפסיק/די ADDED + gated (0 new
  fires on 413; +תפסיק/+הפסק הכל on the live lists, intended; 42 tests). Keyboard KILL SWITCH built: SPACE = /c/stop
  (stop + RC control) + latch refusing every motion verb, R = re-arm (control/kill.py, fake-wire tested, not yet
  pressed live). TTS/eco: tools/dji_mock/watch_503.sh (SAFE) finds the eco timeout; keep-alive effect unverified.
- 2026-09-08 16:15 MEASURED: Gemma 4 E4B as the TRANSLATOR (v1 prompt, 2 shots) -> Qwen planner = 359/412
  (+11 vs Hy-MT2: perception 116/128 (+25), verbose 26/54 (-18), std 198/203, military 12/20). 57/413 outputs
  NARRATE ("The user wants to translate...") -> 23 answer-mode rejects; ONE UNSAFE flip (r_neg4 negation flown).
  WON back the four Hy-MT2 register cases (r_takeoff2/3, r_land4, r_alt10). TranslateGemma's zero-shot
  instruction on Gemma 4 = 171/412 (narrates everywhere) -> few-shots are mandatory for Gemma 4 too. Next lever
  (not ruled): a grammar that forbids the narration opening, or the strict retry. Raw:
  bench/hebrew-command-bench/results/2026-09-08-recognizer-gemma4-xlate-{v1,tgemma}.json.
- 2026-09-08 16:30 RULINGS APPLIED: (1) the 503 watcher is built into the desk-test: `status.sh` prints the phone gate
  code each run and `status.sh --watch` streams changes; preflight prints the watcher command. (2) Manual override =
  the M key toggle (kill / re-arm), replacing SPACE/R. (3) LIVE DEFAULTS FLIPPED: Hy-MT2 + SAM3 + Qwen3-VL
  (run_mvd.sh, scene_omdet.py, preflight.sh, up.sh); omdet/dicta remain switches. (4) integration_harden2 is to be
  built NOW after a short planning round with the owner (Gemma 4 stack). (5) Gemma 4 grammar restriction: research
  existing solutions on the web first (owner ask).
- 2026-09-08 16:35 GEMMA 4 NARRATION FIXED: the cause is the thinking channel; `--reasoning-budget 0` is ignored by
  Gemma 4 (same finding as llama.cpp discussion #21338). `--jinja --chat-template-kwargs '{"enable_thinking":false}'`
  (or `--reasoning off` on build b8738+) stops it: our 12 narrating translator cases -> 0/12, 120-700 ms. Flag is now
  in GEMMA4_EXTRA (recognizer/llama.py) for every Gemma server the bench starts; the harden2 VLM/planner server must
  carry it too. Sources: github.com/ggml-org/llama.cpp/discussions/21338, unsloth.ai/docs/models/gemma-4.
- 2026-09-08 16:40 MEASURED: Gemma 4 E4B translator with enable_thinking=false -> Qwen planner = 389/412 (std 202/203, verbose 51/54, perception 117/128, military 12/20); narrations 0/413 (was 57); vs Hy-MT2 348: lost 1 ['v_ready3_g2'], won 13; unsafe 0 []. Raw: bench/hebrew-command-bench/results/2026-09-08-recognizer-gemma4-xlate-v1-nothink.json.
- 2026-09-08 17:20 OWNER RULINGS + ACTIONS: harden2 created (projects/integration_harden2, copy of the working tree
  minus sessions/). Design rulings: Gemma routes via grammar; translator switch kept; YOLO off by default, switchable;
  whisper stays (TODO: measure Gemma 4 as ASR on the ~125 recorded clips); Hebrew answers straight to the phone TTS
  (SCENE_TTS_LANG=he, no VRAM). The 75 v2 sentences FILED into the bench (488 cases: cmd 254, verbose 63, emergency
  12, perception 138, slang 21; audit CLEAN). Register phrasings HARDWIRED (stage-2 register_imperative: אפשר ל-/
  יש אפשרות ל- + infinitive -> imperative, בוא נ- -> ת-, עלה לגובה N -> עלה N; questions untouched). די/מספיק
  emergency fix. Running: Hy-MT2 488 gate, then Gemma 4 ALONE direct-Hebrew with thinking off and on.
- 2026-09-08 17:30 MEASURED (488-case dataset): Hy-MT2 488 gate 420/487, register rewrites LOST 0 / WON 4 on the
  413 common cases. GEMMA 4 ALONE (direct Hebrew, one model, no translator): thinking OFF 318/328 commands (std
  245/253, verbose 61/63) vs the deployed Hy-MT2->Qwen 310/328 on the same cases; thinking ON 314/328 (loses 4,
  wins 0) -> thinking OFF. Perception for Gemma alone: n/a until the target_en scoring lands.
- 2026-09-08 17:30 HARDEN2 BUILT (projects/integration_harden2): one Gemma server (planner + VLM + Hebrew answers,
  thinking off), direct-Hebrew pipeline with a unified grammar {kind, target_en, mission}, number guard on the
  mission, YOLO off by default, Hebrew TTS, home switch MVD_HOME for desk-test/bench/tests. Live smoke: 10/10.
  Boot (owner): MVD_HOME=integration_harden2 VIDEO=webcam SCENE_TTS=off bash tools/desk-test/up.sh
- 2026-09-08 17:30 GEMMA 4 AS ASR (owner note D): our /root/models/vlm/Gemma-4-E4B/mmproj-BF16.gguf CARRIES the audio
  encoder (has_audio_encoder=true in the GGUF). llama.cpp has the Gemma 4 audio conformer in mtmd (PR #21421) and it
  works through llama-mtmd-cli, but the HTTP server has no input_audio route yet (issue #21868) and the encoder needs
  BF16 (quantised mmproj drifts past its clamps). So the measurement runs clip-by-clip through the CLI, not the server.
- 2026-09-08 17:33 GEMMA-AS-ASR RUN started (background, ~9 min): bench/hebrew_asr/gemma_asr.py, 153 clips of
  the two live sessions through llama-mtmd-cli with the audio mmproj, Hebrew-only GBNF grammar (the CLI has no
  thinking switch; without the grammar it narrates "**Analyze the Request**"). Scored CER/WER vs the matched
  live-test line next to whisper q5_k on the same clip. Result table: bench_out/gemma-asr-2026-09-08.md (gitignored)
  + the summary goes into bench/hebrew_asr/README.md when done.
- 2026-09-08 GOTCHA (again): `pkill -f`/`pgrep -f <pattern>` from a Bash call whose own text contains the pattern kills
  the call (exit 144). Use `ps -eo pid,args | awk '/pattern/ && !/awk/ {print $1}'`.
- 2026-09-08 17:45 MEASURED Gemma 4 E4B as ASR on the 107 matched live clips: CER 35.8 % / WER 71.8 % vs whisper q5_k CER 8.4 % / WER 10.3 %; exact clips 7 vs 69; head-to-head Gemma better on 1, whisper on 96; p50 3542 ms per clip (CLI, model reload each). WHISPER STAYS. Table: bench/hebrew_asr/README.md; per-clip: bench_out/gemma-asr-2026-09-08.md (gitignored).
- 2026-09-08 18:05 MEASURED harden2 END TO END on the 488 bench (unified_bench.py): Gemma 4 alone = 415/487 (perception 108/138, commands 295/316) vs harden Hy-MT2->Qwen 420/487 (perception 100/138, commands 298/316); military not comparable (translation-only set). p50 475 ms per utterance. Parity on the bench, one model, no translator. Raw: bench/hebrew-command-bench/results/2026-09-08-unified-gemma4.json.
- 2026-09-08 19:20 .gitignore: projects/integration_harden2/sessions/ added (the fork records clips + transcripts the same way; private).
- 2026-09-08 19:40 WEBCAM GOTCHA: `VIDEO=webcam` opens index 0 = the laptop's built-in ASUS lid camera, which is
  black with the lid shut. The desk camera is a Logitech C920 = host /dev/video2+3; the dev container only carries
  the /dev/video nodes that existed at container start, so a camera plugged later has NO node inside (mknod
  /dev/video2 c 81 2 + video3 minor 3 fixes it until the container restarts). New switch: WEBCAM_DEV=2 (run_mvd.sh
  webcam mode in both trees; up.sh passes it). C920 measured from the container: 1280x720, 30/30 frames.
- 2026-09-08 19:43 up.sh now creates any missing /dev/videoN node from /sys/class/video4linux at boot (privileged container), so a camera plugged after container start works without a restart.
- 2026-09-08 19:50 tools/desk-test/list_cams.py lists every host camera with index, name, whether the container can open it, frame size/fps and brightness (BLACK flag); preflight (VIDEO=webcam) and status.sh print it; the lid camera is tagged.
- 2026-09-08 20:30 LIVE END-TO-END, harden2 on the C920 + mock (session-20260908-170015-rog, REPORT.md there): 62
  utterances vs the 50-line uniform sample -> PASS 42, FAIL 17, REVIEW 1, unmatched 2. The 17: 8 ASR/speaker (7 of them
  safely rejected by the number guard or fixed on the owner's retry), 4 by ruling/known (greedy עצור halt on r_wait4;
  the 3 military idioms -> reject), 4 planner (extra 0-degree spin on "סיבוב קטן"; a DOUBLE NEGATION flew two spins
  once and was empty on the retry -> UNSAFE, shot added; dz vs dy axis on one chain; return-trip sign dx=-10), 1
  routing ("יש אפשרות לנחות עכשיו?" with an ASR question mark -> reject). Perception: all 14 lines routed right; gate
  absent on 12 desk-less scenes, present on the owner (line 21) and ONE FALSE PRESENT with a zero box (line 34).
  Peak VRAM ~6.5 GiB (owner-observed). SAM3 jitter explained: one SAM3 forward per second (SCENE_SAM3_PERIOD=1.0);
  the compound phrase scored 0.21-0.49 around the 0.30 floor -> mask on/off each second; below the floor the VLM box
  (IoU 0.02) was drawn as the fallback = the "chest rectangle". FIXED in harden2: Gemma boxes never used as a
  fallback, a degenerate gate box = absent, SAM3 gets the head object with its own attributes only
  (phrase_concepts drops relational clauses), a highlight nobody finds for SCENE_HL_GIVEUP=8 s is dropped with a
  Hebrew "לא מצאתי". Tests 49 green. Not fixed: SAM3 counting; the double-negation guard is a shot, not a rule.
- 2026-09-08 21:10 GITIGNORE (owner: "make gitignores", diff was 326 files -> 217): *.done markers, the whole-system
  overlay jpgs (regenerated by overlays.py), whole-system run logs and replay .jsonl rows (clip transcripts = private),
  bench/hebrew_asr/bench_out/ (transcripts), projects/integration_harden2/sessions/. Kept on purpose: the
  bench raw .json results and the .md reports (the READMEs cite them as evidence). A gitignore pattern must not
  carry a trailing "# comment" on the same line -- it becomes part of the pattern.
- 2026-09-08 21:10 harden2 architecture diagram (mermaid + measured numbers per box + switches):
  docs/active/2026-09-08-harden2-architecture.md. To be aligned with the owner's demo-day diagram.
- 2026-09-08 22:40 docs/active/2026-09-06-architecture-diagrams.md refreshed by the live-test lane at the manager's request: §3 (defaults, kill switch, line cites), NEW §3b harden2 (links the 09-08 doc), §5 (stage 0/2/4 changes, 488-case table), §6 (SAM3 backend, rate limit, live flicker finding), §7 (WIRED, the six open items resolved/updated). Every mermaid block re-rendered via mermaid.ink.
- **Defaults flipped to SAM3 + Hy-MT2 (owner ruling 2026-09-08; recorded here by the manager
  2026-09-08 late, since the 2026-09-07 entry above still says "defaults unchanged, OWNER to rule"):**
  `SCENE_SEG=sam3` and `MVD_TRANSLATOR=hymt2` are the run_mvd.sh defaults (run_mvd.sh:36-40,
  tools/desk-test/preflight.sh:56); `omdet` + `dicta` remain the switches for the old pair. The
  translator pane is now named `xlate` (log mvd_xlate.log), port MVD_XLATE_PORT default 18091.
  Measured fit of the deployed five-model stack (census.py --sam3-stack, 2026-09-07): Qwen 3,821 +
  Hy-MT2-Q4 1,187 + whisper q5_k 827 + YOLO 282 + SAM3-nf4 1,074 + transient 94 = 7,396 / 8,151 MiB,
  313 free. whisper q5_k MEASURED at 827 MiB supersedes the file-size estimate (~550).
- **Judge diagrams doc consistency pass after the lane refresh (manager, 2026-09-08 late):** §1
  high-level view now shows the three Python forks (frozen, harden, harden2), the GPU model servers
  per fork and SAM3 as the default highlighter; §9 renamed dicta->xlate and the new preflight model
  checks; §12 marks the SAM3 lane WIRED and adds the harden2 flight gate; §13 replaces the 09-02
  census table with the measured 09-07 five-model stack. The lane's edits (§3, §3b, §5, §6, §7)
  were verified against run_mvd.sh, preflight.sh, the bench README and the tree before acceptance.
  Its report of 404/503 on the FMU-lane blocks was mermaid.ink rate limiting: all render 200 with backoff.
- 2026-09-09 00:45 OWNER RULING applied: COUNTING IS SAM3's JOB in harden2 (Gemma 2/26 on the bench). kind=count ->
  "count the <target>" -> TextHandler._handle_count -> SAM3 alone at score 0.5 on phrase_concepts(target) (no VLM
  gate), the counted objects stay highlighted, chat "ספרתי N: <target>", TTS "יש N" / "לא מצאתי". parse_count in
  perception/engine.py; tests 51 green. Not yet exercised live.
- 2026-09-09 00:45 OWNER RULING: a root `runs/`-style folder for every log / trace / session / overlay / replay row,
  gitignored as one line, scripts write there; committed evidence (.md reports + cited raw .json) stays next to each
  bench. Scheduled for the day after the judges ("we'll do the data folder tomorrow"); ~8 scripts touch their paths.
- 2026-09-09 01:30 harden2 slide diagrams redone as graphviz DOT (docs/active/assets/harden2-*.dot -> .png/.svg, dpi 192) per the llm_to_action lane's recipe; mermaid.ink dropped for slides (Hebrew/'&'/'direction' parse failures; banner aspect ratios).
- 2026-09-09 02:15 DJI API server diagrams + route doc written by a headless Opus job (docs/active/assets/dji-apiserver-{simplified,detailed}.{dot,png,svg}, docs/active/2026-09-09-dji-apiserver-architecture.md). It corrected four ground-station-side assumptions: /input is the PHONE posting to the ground station; the H.264 video is TCP :5600 with the phone as the server; the recognizer is Google SpeechRecognizer (Vosk is dead code); /c/ws/sticks has no keepalive. harden2 diagram labels fixed accordingly.
- 2026-09-09 02:20 DIAGRAM SVG BUG FIXED: graphviz's default SVG keeps text as <text> with fontname Helvetica; slide tools without that font substitute a wider one and labels overflow. All diagram SVGs (harden2-*, dji-apiserver-*) are now rendered with `dot -Tsvg:cairo`, which outlines every glyph into paths (0 <text> elements, verified). Labels narrowed (line breaks instead of dot separators). draw.io files regenerated from the DOT layouts.
- 2026-09-09 02:30 tools/diagrams/dot2drawio.py: graphviz DOT -> native editable draw.io (keeps the dot layout). Slide recipe: dot -Tpng, dot -Tsvg:cairo (outlined glyphs), dot2drawio for hand edits.
- 2026-09-09 05:40 CONTEXT SWEEP before compaction: handoff §17 (the night's work) + §18 (where to look next); the judge/team objective brief is docs/private/2026-09-09-team-summary-objective.md (gitignored). Next agent: read §18 first.
- 2026-09-09 05:45 tools/desk-test/score_session.py: the live-session scorer (overlap alignment + expected-notation judge) saved as a script; it reproduces the 42/17/1/2 review of session-20260908-170015-rog.
- 2026-09-09 06:05 block A (webcam + mock, harden2) result: 7/7 sentences routed right; 2 missions flew on the mock with the exact steps; highlight chair stable (SAM3 0.93-0.95); describe answered in Hebrew; both rejects clean; M killed (POST /c/stop 200) and refused the next 3 missions until re-armed; "עצור ל-10 שניות" halts by design. ONE bug: "ספור את הכיסאות" 4 times -> 2, 5, 4, 6 (one frame, no dedup; SAM3 returns part-inside-whole instances). Fix: perception2/counting.py (conf >= 0.5, drop boxes 70 % contained in a stronger box) + median over 3 frames 0.3 s apart (SCENE_COUNT_FRAMES/SCENE_COUNT_GAP); test/test_count.py. Live stability of the fix is UNVERIFIED until block B.
- 2026-09-09 06:05 evidence gaps closed: _say now always prints to app.log (the KILL / refused lines were chat-only, so the session log could not show the kill); pipeline names a 409 refusal "REFUSED-kill-latch mission(...)" instead of "mission(..., planned)".
- 2026-09-09 06:00 team summary document produced by a headless agent into docs/private/ (gitignored): team-summary-2026-09-09.{md,pdf} (7 pages), competitors-validation.md (12 blocks, 2 sources each), render_team_summary.py, team-summary-STATUS.md. Findings the owner must read before the meeting: ThirdEye had a MAFAT Hebrew voice interface (20 commands) in 2022; XTEND markets XOS as hardware-agnostic; "Kronos Group" was not found (likely Kratos); LINE5 product claims unverifiable; every "they lack X" claim is unverified by construction.
- 2026-09-09 06:40 block B (phone video + mock + Hebrew TTS, harden2) worked: mark chair + count chairs (5,5,5 after the median fix) from the phone, the phone spoke. Vision misses, root causes from /tmp/desk-test/20260909-031808/app.log + traces: (1) Gemma's target_en mistranslated furniture nouns: מגירות -> "cabin", שידות -> "desks" -> SAM3 counted 0 (Gemma is not the vision here, its English WORD was wrong); (2) SAM3 scores "screens" 0.25 and "window panes" 0.26 while "monitor"/"window" score ~0.9; (3) "top left window": SAM3 cannot use positional words -> NOTHING; (4) the Gemma presence gate said absent once for "all screens" (then present on retry); Gemma describe answers were pedantic ("no traditional kitchen cabinets... there is a wooden hutch"). Windows highlight actually worked (2 windows at 0.88-0.91).
- 2026-09-09 06:40 fixes: perception2/lexicon.py HE->EN noun table (about 120 nouns) applied under Gemma for highlight/count only when Gemma's target has none of the noun's aliases (flag "lexicon:'cabin'->'drawer'" in the trace); SAM3 synonyms screen->monitor/television/screen, cabinet->cabinet/cupboard/wardrobe, drawer->drawer/dresser, "window pane"->window; positional words (top/left/upper/... , "on the left") stripped from the SAM3 concept; SCENE_GATE=vlm|either|sam3 switch in scene_omdet (default vlm = unchanged; "either" = Gemma no + SAM3 hit >= 0.5 counts as present). 60 tests pass. OPEN ruling: the SCENE_GATE default for the demo (agent recommends "either").
- 2026-09-09 06:46 RULING (owner): block C and the demo run with SCENE_GATE=either (Gemma "absent" is overruled by a SAM3 hit >= 0.5). The code default stays vlm until C confirms it; if C is clean, flip the default in scene_omdet.py so the demo cannot forget the env.
- 2026-09-09 07:19 laptop restart wiped bitsandbytes + accelerate from the container (SAM3 nf4 would not load). Restored with tools/devenv/install-runtime-deps.sh (exit 0). Rule for the morning: after ANY restart run that script, then preflight. The C920 was not on USB and the laptop was on a non-hotspot network (gw 10.160.188.132) at the time.
- 2026-09-09 07:28 real-run blocker: run_mvd.sh line 173 exported a bare $MVD_SESSION_DIR under set -u; only up.sh set it, so `run_mvd.sh dji real` aborted "unbound variable" (blocks A/B went through up.sh and never hit it). Fix: run_mvd.sh now defaults MVD_SESSION_DIR to sessions/session-<stamp>-<host> and records clips (ASR_RECORD=1) so a direct real run leaves the same evidence as up.sh.
- 2026-09-09 07:28 real-run blocker 2: the phone's hotspot IP CHANGED (10.222.215.92 -> 10.160.188.132). The run was launched with the old IP: gstreamer video flowed (derived gateway) but the app's router said "-> 10.222.215.92 (real)" and every POST /c/fly timed out UNREACHABLE while the aircraft was airborne on the RC. Rule: never hardcode PHONE_IP; use $(ip route | awk '/^default/{print $3}') and confirm GET http://<gw>:8080/status = 200 before boot. Run sheet + run_mvd.sh header fixed; memory updated.
- 2026-09-09 07:35 RULING (owner): "Gemma 4 is the planner, SAM3 is the eyes." SCENE_GATE default flipped vlm -> sam3 in harden2 scene_omdet.py: a highlight no longer asks Gemma whether the object is visible; SAM3 at score >= 0.5 (deduplicated) decides. Count was already SAM3-only. Describe questions still go to Gemma because SAM3 cannot describe a scene (the only VLM on the box). SCENE_GATE=vlm|either remain as switches.
- 2026-09-09 07:45 FIRST REAL harden2 FLIGHT (Gemma 4 planner, SAM3 eyes) — session projects/integration_harden2/sessions/session-20260909-042949-rog, log /tmp/mvd_app.log: 6 missions reached the aircraft with HTTP 200 (dz 2; spin -90 + dx 1; spin 180 + dx 5; three "square" requests). Planner finding: "square" is phrasing-dependent at temp 0 — "תבצע תנועה של ריבוע בגודל של מטר אחד" -> the correct 4 legs; "תטוס בריבוע של מטר" -> ONE diagonal leg (dx 1, dy 1); "תעלה עוד שני מטרים ... ריבוע בגודל שני מטרים" -> dz 2 then a diagonal first leg. Not a vision issue; a UNIFIED_SHOTS square example is the fix but needs the 488 bench rerun -> after the judges. Do NOT say "ריבוע" in the demo. Vision finding: "סמן את כל הכיסאות" in an open field -> Gemma gate present=True AND SAM3 "chairs" 0.60-0.86 on boxes under 0.5 % of the frame = speck false positives. Fix: SCENE_MIN_BOX_FRAC=0.001 (about 30x30 px at 720p) applied to the gate, the count and the drawn highlight; test added; 61 tests pass. ASR note: "תספורת מיכלי הגז" (haircut) for "תספור את" still routed to count by Gemma.
- 2026-09-09 08:05 "can't see" diagnosis (session-20260909-044803-rog, /tmp/mvd_app.log; SCENE_GATE=sam3 default confirmed via /proc environ, process started 04:48 > code mtime 04:42 so the new code IS live). Pattern, by noun: cars/vehicles/person -> SAM3 0.86-0.97 on real boxes (3-17% of frame), highlighted fine. windows 17x "found NOTHING", blinds 4-5x NOTHING, and several drops-after-8s. Root cause: SAM3-nf4 is UNSTABLE on glass/architecture (windows, blinds) and tiny boxes -- it returns a box on the gate snapshot (present=True) then loses it on the next frames, so after SCENE_HL_GIVEUP (8s) the chat says "לא מצאתי" = the "can't see" the owner heard. NOT a Gemma fault (gate is SAM3 now) and NOT the speck floor (no person/car/chair was dropped by it). Demo rule: highlight/count PEOPLE, CARS, CHAIRS -- never windows, blinds, glass, screens-at-distance. Post-judges fix: seed the worker with the gate's own SAM3 box so an unstable object is not lost (gate and worker both run SAM3 now but independently), and/or raise SCENE_HL_GIVEUP.
- 2026-09-09 08:20 "only 3 of 12 cars highlighted" root cause + fix (live block C). The offline sam3-mask-bench fed images straight to the backend; the LIVE highlighter wraps SAM3 in PerceptionEngine with three limits the bench never had: (a) mask_k=3 -> at most 3 detections drawn per frame [THE cap: the log showed 8/8 cars passed the gate, only 3 drawn]; (b) SAM3 detect topk=8 -> cars 9-12 never entered; (c) relative gate rel=0.65 -> anything below 0.65*best dropped. So live recall = SAM3 raw minus three gates, on a moving drone -- not a SAM3 regression. Fix (scene_omdet.py, 61 tests pass): SCENE_HL_TOPK default 8->24 (detect + count), SCENE_HL_MAX default 3->15 (engine mask_k, passed at construction; constructor default stays 3 so the engine selftest is unchanged). SAM3 masks are cached from detect so drawing 15 costs almost nothing. Simulation (12 real car boxes conf 0.97..0.55): before=3 drawn; after rel=0.65=9 drawn; rel=0.45=12 drawn. Remaining lever for crowded scenes: SCENE_HL_REL=0.45 (default 0.65 kept -- it protects single-object highlights, e.g. the engine selftest's 0.48 window dying next to a 0.90). Windows/blinds are still the SAM3-can't-segment-glass problem (separate, 08:05).
- 2026-09-09 08:25 WHY the highlight cap existed (for the record, owner asked). The PerceptionEngine (mask_k=3, rel=0.65, presence gate) was written for the OmDet-Turbo + SAM2.1 pipeline: each kept box needed a SEPARATE, expensive SAM2.1 mask forward, so mask_k=3 capped cost for the live loop, and the relative/presence gates existed because OmDet returns a confident box on absent objects. SAM3 returns boxes AND masks in ONE cached forward, so the per-box mask cost that justified mask_k=3 is gone -- but the cap was inherited at the SAM3 swap and never lifted (integration oversight). That is the entire bench-vs-live gap: sam3-mask-bench (2026-09-03) called the backend DIRECTLY (run_suite/run_indepth) and saw 26-47 windows, 30 people, 8 cars; the live app ran the SAME SAM3 through the OmDet-era throttle -> 3 draws max. Fixed 08:20 (HL_MAX 15, HL_TOPK 24). Note the split: cars = the cap (fixed); windows live = SAM3 returned ZERO at floor 0.12 from the moving drone (the bench stills gave 47) = scene/motion, NOT the cap. compare_engines.py is the one bench path that DID drive the full PerceptionEngine, so the gating was visible there, just not in the headline raw-detect numbers.
- 2026-09-09 08:55 team doc section ד rewritten from verdict-log bullets (אמיתי/סותר/אין ראיה) to Gemini-style prose, one paragraph per company, in order 1-12, no internal jargon; dropped the "Gemini logic vs findings / don't tell the judge" meta-subsection; kept the three differentiation blocks + the numbers/form table. The firm per-claim verdicts + 16-39 sources each stay in competitors-validation.md (evidence file for owner only). PDF re-rendered: 6 pages. Backup at team-summary-2026-09-09.md.bak.
- 2026-09-09 18:45 judge meeting CANCELLED (the business meeting was enough for them). Reorienting to the challenge form only. Full high+low state written to docs/active/2026-09-09-project-state-and-reorientation.md: scorecard (done/WIP/not-met/not-measured) with WHY each was worked, all measured numbers, today's work, and the ranked backlog led by 3.1 vision-conditioned action.
- 2026-09-09 19:20 SAM3 caps were arbitrary and wrong (owner called it). The 3-draw / 8-detect caps were inherited from the OmDet+SAM2.1 era where each box cost a separate SAM2.1 mask forward; SAM3 returns boxes+masks in one cached pass so there is NO per-box cost to cap. My 15/24 "fix" this morning was still an arbitrary number and it silently clipped COUNT at 24 (a real bug: >24 objects would undercount). Corrected: HL_TOPK and HL_MAX default 128, above SAM3's own object-query budget (bench saw 47 windows, 51 in market-2; exact budget UNMEASURED = a research point). They are now a latency safety-valve, not a product limit; count is effectively uncapped. Open: measure SAM3's true per-pass instance ceiling.
- 2026-09-09 19:50 challenge form saved canonical: docs/active/challenge-form.md (from Build Challenge Doc.pdf, Ground Forces Innovation Lab). All status docs map to its section numbers.
- 2026-09-09 19:50 ASR noise numbers FOUND (owner pointed to the noise filter; they live in the ASR side, not the vision repo): docs/research/asr-noise-robustness.md + the sttserv harness (BUILD_noisefilter/snr_mix_core.h, sttserv/test/asr_test.cpp, dependencies/noise_beds/battle_{0..3}.wav). Result, Parakeet-TDT-0.6B q4, ENGLISH, raw audio, real gunfire/explosion beds mixed at controlled SNR: 92% intent at 0 dB (38/38 pass), ~87%+ from +20 to 0 dB, ~80% at -4 dB, collapse by -10 dB. Denoisers ALL net-negative end to end: raw 37/44 vs classical DSP 33, SpeexDSP 30, GTCRN neural 27 -> decision "ship raw, no front-end filter" (the ASR is trained on noisy speech). Confidence gating dead (failing transcripts averaged higher confidence than passing). GAP vs the challenge: this is Parakeet/English; the challenge is whisper/Hebrew. Remaining work = replicate the SNR sweep with whisper on Hebrew clips + the same beds (infra reusable), and build the LOW-LIGHT image equivalent for SAM3. Do NOT re-research denoisers; that question is answered.
- 2026-09-09 21:00 negation demo (offline, deterministic): ALL negation sentences pass through recognize_direct as "direct" -> reach Gemma. Safety on negations currently rests on Gemma classifying them as reject; it worked for "אל תנחת" (block A) but FAILED live for r_neg4 "בלי להסתובב בבקשה" (flew two spins). Demonstrates the need for a deterministic action-negation guard BEFORE the model. Demo script in scratchpad.
- 2026-09-09 21:00 SAM3 cap state: code corrected (HL_TOPK/HL_MAX=128, count uncapped, comment cleaned), compiles, 61 tests pass, but UNTRACKED in git and NOT verified live. Not shipped.
- 2026-09-09 21:00 repo cleanup DRAFT written: docs/active/2026-09-09-repo-cleanup-draft.md. Key risk flagged: integration_harden2 is entirely UNTRACKED; a git mishap would delete the fork. Commit it first.
- 2026-09-09 21:30 owner replan approvals: (B) negation guard+test APPROVED; (C) operator-mission context = its own project (the drone's context != the operator's field context; model mission/phase so the system assumes correctly instead of guessing); (D) tracker back ON, NOT Plane (owner dislikes their pricing) — agent recommends OpenProject (GPL, free, hierarchy + wiki, ~4GB, Docker) hosted on the workstation not the 8GB laptop, Huly as the modern-feel alternative (8-16GB); noise = a real whisper-Hebrew e2e benchmark, no denoiser research (answered). New ordered plan in docs/active/2026-09-09-project-state-and-reorientation.md §7 (two tracks: organization + technical).
- 2026-09-10 owner: each track gets its own subagent. Track 2 (the system) = owner + this session. Track 1 (self-hosted tracker) = a separate subagent, seeded by docs/active/2026-09-10-track1-tracker-handoff.md (written in the house handoff style; cross-checked against the 09-05/-07/-08 handoffs + the 08-26 manager brief). Tracker recommendation OpenProject (Huly alt), host on the workstation not the 8GB demo laptop, NOT Plane.
- 2026-09-10 "routing verification" pinned = harden2's single Gemma call choosing action+plan, checked by bench/hebrew-command-bench/unified_bench.py over 488 cases (last 415/466) + a live pass; it is Track 2 (owner's point 2). Today's changes were vision-only, so routing should be unchanged. Track 2 execution draft written: docs/active/2026-09-10-track2-execution-draft.md (steps 1-5 with definition-of-done + who-runs-what).
- 2026-09-10 Track2 draft rev2 (owner corrections): (1) the negation guard is a harden2 FEATURE and must land BEFORE the commit/freeze, not after — folded into step 2 (2b) and made part of routing verification (a negation that flies is a routing failure); clarified we FREEZE harden (old fallback), NOT harden2 (active). (2) noise+low-light benchmarks DEFERRED to after the repo cleanup, which is now step 3. New order: 1 webcam verify, 2 harden2 save+guard+verify+commit(+freeze harden), 3 cleanup, 4 benchmarks, 5 big builds.
- 2026-09-10 Track2 draft rev3 (owner): harden is ABANDONED as the dev target but KEPT as fallback; FREEZE it only AFTER harden2 proves it works well OUTSIDE (real outdoor drone session) — freeze moved to step 5, gated on outdoor validation, not on the bench+webcam. Added the abandonment-reasons list (4->1 models, lossy translation hop dropped, VRAM, 415 vs 410, less to tune, Hebrew answers free, iteration speed). Added step 7: eventually FUSE the C++ llm_to_action engine with integration_harden2 (the destination product). New order: 1 webcam verify, 2 harden2 save+guard+verify+commit, 3 cleanup, 4 benchmarks, 5 outside-validation->freeze harden, 6 features, 7 llm_to_action fusion.
- 2026-09-10 CORRECTION (owner was right): integration_harden is NOT the fallback and is half-baked. Evidence: CLAUDE.md names projects/integration/ (English, frozen) as THE proven fallback; integration_harden is 100% uncommitted (22 modified + 3 untracked), and lacks every 2026-09-09 harden2 fix (no perception2/counting.py, no lexicon.py, no HL_TOPK/HL_MAX cap fix, no SCENE_GATE) so it still has the count jitter + 3-draw cap + "cabin" mistranslation. Its 44 tests pass (code coherent) but it is stale/buggy as a system. Ruling: drop "freeze harden" from the plan entirely; harden is a dead intermediate; owner later discards its uncommitted diff or leaves it as history; harden2 is the Hebrew system; the only real fallback is projects/integration/ (English). No second Hebrew tree maintained. Track2 draft -> rev4.
- 2026-09-10 Track2 rev5 (owner): the outdoor test validates the FINAL system (harden2 + today's perception fixes + the negation guard), so it comes BEFORE the cleanup, not after; passing it freezes THAT exact commit as the validated baseline (tag). Cleanup must be behaviour-preserving for harden2 (moves/commits/docs OK); any change to harden2's runtime behaviour invalidates the frozen validation -> RETEST outdoors and re-freeze. New order: 1 webcam verify, 2 harden2 save+guard+verify+commit, 3 outdoor validation -> freeze baseline, 4 cleanup (behaviour-preserving), 5 benchmarks, 6 features off the baseline, 7 llm_to_action fusion.
- 2026-09-10 clarified (owner asked "why hymt2 as translator?"): harden2 does NOT run a translator. run_mvd.sh defaults MVD_TRANSLATOR=none (Gemma reads Hebrew directly); no xlate tmux window starts (block A/B had windows vlm/keys/asr/gst/dog/app, no xlate). The "hymt2" the owner saw was a COSMETIC LIE in up.sh's status echo and preflight.sh's default (hardcoded :-hymt2 from harden's era). Fixed both to be MVD_HOME-aware: default none for integration_harden2, hymt2 otherwise. Display/preflight-only change; no runtime behaviour change to harden2.
- 2026-09-10 GOTCHA found while listing run args: SCENE_TTS is NOT read anywhere; "SCENE_TTS=off" (used in earlier retest commands + up.sh comment) is a NO-OP. The real TTS switch is MVD_TTS=0. On webcam-only boots TTS was off because the phone voice backend fails to attach, not because of the flag. Full arg reference: docs/active/2026-09-10-harden2-run-arguments.md.
- 2026-09-10 owner rulings on harden2 args + a 2-file config draft. DELETE: MVD_HOME, MVD_TRANSLATOR, MVD_XLATE_PORT, GEMMA4_THINK, MVD_TRANSLATE_PROMPT, MVD_PLANNER(qwen3vl path), SCENE_SEG(omdet path)+SCENE_SAM2, SCENE_TTS(no-op). BAKE constants: gemma4+thinking-off, ports, SEG=sam3, BG off, HL_TOPK/HL_MAX/HL_CONF/DETECT_FLOOR/MIN_BOX_FRAC/COUNT_FRAMES/COUNT_GAP/HL_GIVEUP/SAM3_PERIOD, TTS_LANG=he, PHONE_ASR on, PHONE_ASR_PORT, offline flags, TMUX_SESSION, DISPLAY, PULSE_SERVER, DRONE_ROUTER on. KEEP as overridable-with-default: VIDEO(webcam|dji), CONTROL(mock|real), WEBCAM_DEV, PHONE_IP(ALWAYS derived from default route, override to force), SCENE_HL_REL, SCENE_GATE(kept "at bay", default sam3), MVD_TTS, all ASR_* escape hatches, RECORD(default on, drives clips), SESSIONS_ROOT/SESSION_DIR(one root; CLIPS_DIR+LOG_DIR derived). Draft files: projects/integration_harden2/config_constants.py + config_defaults.py (NOT yet wired; behaviour-preserving until the cleanup wires them and deletes the dead code paths + moves config out of the scripts). run_mvd stays only as a thin process launcher (llama-server, whisper ASR node, keyboard hook, gstreamer node, app, tmux); config leaves it.
- 2026-09-10 config draft rev2 (owner): MVD_DRONE removed ENTIRELY (not even baked) — routing is unconditional, CONTROL alone decides the wire target; no "enable router" flag. Perception constants renamed to intent-describing names (SAM3_MAX_BOXES_PER_QUERY, MAX_HIGHLIGHTS_DRAWN_PER_FRAME, MIN_DRAW_CONFIDENCE, DETECTOR_QUERY_THRESHOLD, MIN_BOX_FRACTION_OF_FRAME, COUNT_MEDIAN_FRAMES, COUNT_FRAME_GAP_SECONDS, HIGHLIGHT_GIVEUP_SECONDS, SAM3_MIN_SECONDS_BETWEEN_FORWARDS). SCENE_GATE stays in config_defaults.py as HIGHLIGHT_PRESENCE_GATE (default sam3, env-overridable). Confirmed: Gemma has ONE runtime prompt (UNIFIED_PROMPT = REVISED_PROMPT + routing, with UNIFIED_GRAMMAR + UNIFIED_SHOTS); the other prompt strings are the dead translator. run_mvd stays only as the process launcher post-cleanup.
- 2026-09-10 22:47 negation-guard BASELINE finding: at temp 0 the 488-case bench shows Gemma ALREADY rejects EVERY negation correctly (r_neg1-5, neg_trap, l_dbl_neg, l75_neg_emphatic all CORRECT-reject; the negation+order cases CORRECT). Zero measured failures. The UNIFIED_SHOTS negation reject examples already handle it. So the deterministic guard is DEFENSE-IN-DEPTH vs the LIVE non-determinism (r_neg4 flew two spins once), NOT a bench fix; it does not meet the skill's >=2-failures bar, and its only real risk is regressing a currently-correct case. PAUSED for owner go/no-go. Current bench total = 410/487 (the older "415/466" is stale).
- 2026-09-11 (morning) persisted the assurance math (binomial/Clopper-Pearson/Wilson/rule-of-three + implications) to the guard workplan appendix; added a consolidated session index + resume pointer to the reorientation doc section 8. Everything non-private is in purpose-specific files, not chat. Resume = workplan "STATUS at stop" -> A5.

- 2026-09-11 negation guard HARDENED + config merge DESIGNED (harden2). (1) recognizer.negation_only
  rewritten from a positional heuristic ("positive before negation") to a SUBTRACT rule: split the
  utterance on , . ; ואז אבל ורק אולם, then per clause remove the verb the negation trigger governs
  (אל ת.../בלי ל.../לא ל...); an imperative that SURVIVES the removal is a separate real order, so the
  clause passes. A bare number+unit is an order only when the clause has no negation. This fixed a real
  false fire — a leading manner-negation before an order ("בלי לעצור תמשיך ישר", continue straight
  without stopping) — that the positional rule wrongly refused. Added continue/slow/speed verbs
  (תמשיך/המשך, תאט/האט, תאיץ/האץ) to the positive-imperative list. Dataset grown to 24 must-refuse +
  25 must-pass (test_negation_guard.py). Full bench re-run (tag negation-guard-a7): 410/487, 0 changed
  cases vs baseline, 0 false fires. Guard is defense-in-depth (Gemma already rejects these at temp 0);
  the win is determinism for the safety-critical negation class. UNCOMMITTED (human owns git).
- 2026-09-11 config merge (harden2) design + golden-master, behaviour-preserving. Captured the current
  config surface (~47 keys across config.py + scattered getenv in scene_omdet.py/pipeline.py/watchdog)
  per launch scenario -> test/golden_config.json (capture_golden_config.py). Completed config_constants.py
  (baked) + config_defaults.py (overridable + video_input()/wire_target() derivers) as a full superset of
  the ACTIVE keys; test_config_golden.py proves they reproduce the golden for webcam_mock/dji_mock/dji_real
  (2 tests green, 66 total offline). The merge DROPS the omdet/sam2/yolo + translator keys with their dead
  code. It bakes the launcher's active values (TTS he, background off, router unconditional) as constants,
  dropping config.py's stale yolo/English naked defaults (the bench does not read them -> no behaviour
  change). B2 (rewire app imports + delete dead code + strip run_mvd.sh exports) is STAGED, gated on an
  owner live webcam run because the bench exercises only the recognizer, not perception/camera/TTS.

- 2026-09-11 perception capture ADDED (harden2, cleanup-audit B1 half 1). scene_omdet SessionLog gains
  capture_perception(); the count/highlight/ask threads each call it after detection. Per query it saves
  the frame (<session>/perception/NNNN-<kind>.jpg) + raw and kept SAM3 detections (conf+box) + the result
  + the params (gate/seg/thr/min_box_frac/topk) as one JSONL line in <session>/perception/perception.jsonl.
  Self-contained in the session dir, SEPARATE from the ASR clips/ and utterances.jsonl (owner requirement,
  "dont mix the data"). Behaviour-preserving (additive I/O on the existing background threads). This closes
  the gap that made the indoor "12 cars, 3 highlighted" miss un-debuggable, and feeds the B1 replay harness.
  test_perception_capture.py 3/3; full harden2 suite green. UNCOMMITTED (human owns git).

- 2026-09-11 config merge WIRED (harden2) + session-folder symmetry + a static-analysis pass on all
  session features. (a) config.py is now a thin ADAPTER: every value is sourced from config_constants.py
  (baked) + config_defaults.py (overridable + the host resolvers resolve_device/torch/default_gateway/
  resolve_he_font + overlay colours), with each env override preserved. scene_omdet's scattered perception
  knobs (SEG/GATE/HL_TOPK/HL_MAX/COUNT_*/MIN_BOX_FRAC/HL_GIVEUP/SAM3_PERIOD/DETECT_FLOOR/HL_CONF/HL_REL) now
  take their DEFAULTS from the two files. Behaviour-preserving: golden-master 2/2, scene_omdet imports with
  every knob value identical, 70 offline tests green, the guard bench unaffected (410/487). (b) session
  folder is now symmetric: asr/ (utterances.jsonl + .log + clips/*.wav) and perception/ (frames + jsonl),
  meta.json at the root; SessionLog + run_mvd.sh write there, and the 5 reader tools (show_session, score_*,
  gemma_asr, run_list) fall back to the legacy top-level so old sessions still read. (c) static analysis /
  dry run of every feature: recognize_direct crashed on a None transcript (pre-existing stage-0 regex;
  unreachable live because the text handler does (text or "").strip()) -> hardened with `he = he or ""`;
  the negation guard is fail-safe (reject only, never motion) and survives empty/emoji/5000-char/null-byte
  input; the perception threads were driven synchronously with fakes and do not crash (None frame -> image
  null); perception2/detectors.Eyes does an UNGUARDED YOLO(config.BG_SEG_MODEL) that would raise on BG=off,
  but it is DEAD (scene_omdet uses the guarded perception/detectors.Eyes) -> delete it in the B2 dead-code
  pass, no live risk. REMAINING (B2 cleanup, not blocking): delete the omdet/translator dead code and strip
  the now-redundant config exports from run_mvd.sh. All UNCOMMITTED (human owns git).

- 2026-09-11 harden2 dead-code PURGE (owner ruling: keep YOLO26 background, delete the rest of the old
  4-model stack; harden2 only). Removed OmDet, SAM2.1, the DictaLM/Hy-MT2 translators, and the Qwen3-VL
  planner from pipeline.py (-> direct path only), llama.MODELS, perception/detectors.py (Eyes=YOLO only),
  scene_omdet (import + build_highlight omdet branch + _translate wrap), config.SAM2_WEIGHTS, perception2/
  __init__, run_mvd.sh (translator/xlate/qwen/omdet). Behaviour-preserving: bench 410/487 with 0 changed
  cases; 60 offline tests; golden-master 2/2; all modules import. Owner to git rm 6 orphaned files
  (2 translator servers + perception2/{detectors,engine,vlm_client,chain_demo}.py). Deferred to the nuclear
  review: prompts.py dead strings + recognizer.recognize(). Plan: docs/active/2026-09-11-harden2-deadcode-purge.md.

- 2026-09-12 up.sh completeness fix for the asr/ folder change. The session-folder move to asr/ had only
  touched run_mvd.sh; but tools/desk-test/up.sh (the launcher the owner drives) OVERRIDES ASR_RECORD_DIR,
  so clips would have landed in flat clips/ while utterances went to asr/ -- a split. Fixed: up.sh now sets
  CLIPS_SUB=asr/clips for MVD_HOME=integration_harden2, flat clips/ otherwise. run_mvd.sh push-to-talk
  banner corrected H->F5 (the keyboard hook binds F5; run_mvd echoed a stale H). Desk-test launch method of
  record = the 4 scripts (up/preflight/status/down), NOT raw run_mvd.sh.

- 2026-09-12 MVD_HOME DELETED (honoring the 2026-09-10 ruling I had missed). It was the up.sh/preflight
  fork-selector and, worse, defaulted to the DEAD integration_harden. harden2 is the only system, so the
  desk-test launchers now hardcode projects/integration_harden2: up.sh RUNMVD + SESSIONS_ROOT + CLIPS_SUB
  (=asr/clips), preflight TRANSLATOR=none. No MVD_HOME anywhere in tools/desk-test/*.sh. Desk-test launch
  is now just: VIDEO=webcam MVD_TTS=0 bash tools/desk-test/up.sh. config_constants docstring updated to list
  MVD_HOME among the deleted knobs.

- 2026-09-12 webcam-test fixes (owner complaints 1/3/4). (1) Rejections now show WHY in the overlay:
  _reject_why() maps the action to a plain reason (neg-guard / number-mismatch / planner-echo / model
  could-not-route). (3) The highlight-absent message was ungrammatical ("a all guitars") AND opaque: it
  used the raw target and gave no reason. Now it uses the stripped concept and reports SAM3's best score
  -- "I don't see \"guitars\" in view (SAM3 best 0.42 < 0.50 gate)" vs "(SAM3 found nothing)". The gate now
  detects at a 0.1 floor so near-misses are visible (still gates at 0.50). (4) Container is UTC (TZ unset,
  /etc/localtime->Etc/UTC); session dirs + asr clip names (localtime_r) were stamped UTC. up.sh now exports
  TZ=${TZ:-Asia/Jerusalem} so both stamp local time. PENDING (big): (5) full start-to-finish per-utterance
  trace with before/after frames; (2) UI redo for Hebrew overflow (HTML draft -> opencv).

- 2026-09-12 full start-to-finish trace + session replayer built (owner point 5 + 2b). trace.jsonl is now
  THE per-utterance log (retires utterances.jsonl): transcript, he2, flags, kind, target, vision_query,
  mission, verdict, spoken, action+reject_reason, timings, and audio_clip. Audio linked causally (no C++
  change, no timestamp math): on transcript arrival Python claims the newest unclaimed asr_clips/*.wav and
  renames it utt_<seq>.wav. Vision captured per REQUEST under perception/<seq>-<kind>-<target>/ with one RAW
  frame + json per SAM3 forward / Gemma VLM call (model-agnostic, no burned boxes). he2/kind/target flow via
  a new optional Pipeline.observe() callback (off the bench path). Replayer: tools/session-replayer/replayer.html
  (local directory picker, draws boxes from JSON, audio, per-pass scrub, annotated export). 62 offline tests;
  bench unaffected. PENDING: opencv pane redesign (2a); browser + webcam smoke of the replayer/capture.

- 2026-09-12 live opencv pane reproduced from the approved mockup (tools/ui-mockups/live-pane.html).
  render_chat: width-aware wrapping via _wrap_px (measures _HE_FONT.getlength; the old fixed char-count
  overflowed — long Hebrew now wraps inside CHAT_W, verified 388<426px), RTL right-align for Hebrew in
  _draw_conv, and the session DUMP PATH shown in the header ("dump: sessions/session-..."). reject-reason +
  SAM3 best-score lines already land from the earlier fixes. Not yet reproduced: the mockup's left tag-column
  (kept the inline You:/Scene:/Kind labels) -- iterate after a live look. Can't render the window headless;
  verified wrap logic + compile + 62 tests. Replayer nits fixed same day: canvas full-width, utterance
  timings populated (recognizer/plan/e2e ms), box-label top-clamp pile-up fixed.

## scene_omdet split + recording crash-safety (2026-09-12)
- scene_omdet.py did four jobs in 899 lines. Split into three files, no behaviour change (66 tests pass):
  - overlay.py (213) -- pure chat-pane renderer. render_chat(height, chat, thinking, killed, session_dir, om_name) takes a SNAPSHOT; the caller holds S.lock. No shared state, no threads. Owns the 3-font stack + draw_box + FONT.
  - session_log.py (178) -- SessionLog + reject_why. The telemetry/capture layer.
  - scene_omdet.py (548) -- engine wiring + command dispatch + main loop (its real job).
- Recording crash-safety: a hard interrupt outdoors (Ctrl-C / power loss / force-quit) must never corrupt the recording.
  - trace.jsonl: one complete JSON line per utterance, append + flush + os.fsync on commit -> every committed utterance is durable.
  - meta.json / request.json / pass_*.json / pass_*.jpg: written atomically (temp file + fsync + os.replace) -> never a truncated mix.
  - Contract: at worst the in-flight utterance is lost; everything committed survives. Proven by test/test_crash_safety.py (incl. a real SIGKILL mid-session).

## Field power/energy is a first-class constraint (owner, 2026-09-12)
- The deployment target is a backpack box, not a 5070-Mobile laptop. Power draw, heat, and battery life gate it.
- Derived from the owner's data: <3x 20-min flights on the pack => >~90 W average SYSTEM draw. Laptop-class.
- We have measured SAM3 VRAM/latency/accuracy but NEVER watts. That is the gap. SAM3 1008->672 ~halves a
  forward's GPU energy, but SAM3 is on-demand (per highlight, ~0.4 s, 1/s cap) so its share of the sustained
  draw is small. The continuous baseline (GPU holding Gemma, video) + the platform choice dominate.
- SAM3 input is a fixed 1008x1008x3 square (patch 14 x window 24 = 336; 1008 = 3x336). Valid clean sizes are
  multiples of 336 (672, 1008, 1344); 960 is NOT valid. Lowering it is an accuracy risk (small/distant objects)
  -> benchmark, do not assume.
- Tool: tools/desk-test/power_profile.py -- detects the GPU (nvidia-smi/rocm-smi) and the battery from /sys
  (nothing hardcoded), samples live power, integrates to Wh, and estimates flights/charge from the DETECTED pack.
  Run it UNPLUGGED (battery discharging) for the true total-system number; on AC it measures only the GPU.

## HUD model line + power profiler, properly (owner push 2026-09-12)
- HUD header: the single appended "planner · SAM3 · whisper-ivrit" line is split into one line per subsystem,
  each READ from env/config (overlay._model_lines): brain=MVD_PLANNER, eyes=SCENE_SEG+SCENE_SAM3_PRECISION,
  ears=ASR_MODEL_PATH. It follows the env, so it never lies. NOTE: harden2 is single-stack -- qwen3vl was purged
  from llama.MODELS, so MVD_PLANNER=qwen3vl would change the LABEL but NOT load Qwen3-VL; the backend must exist.
- power_profile.py now works plugged-in: adds CPU package power via RAPL (/sys/class/powercap/intel-rapl:*,
  package domains, wrap-handled). Reports CPU(RAPL) + GPU(smi) = "compute draw" (a LOWER bound, excludes
  RAM/board/PSU) when no battery discharges; prefers the full-system battery number when it does. Fixed a first-
  sample div-by-tiny-dt that showed 30 kW; dt is now stamped at the RAPL read. Idle on this rig: CPU ~55 W,
  GPU ~22 W, compute ~77 W -> ~3.5 flights/90 Wh at idle (drops under load).
- Wh = watts x hours (energy). watts = Wh / hours. 90 Wh pack = 90 W for 1 h, or 30 W for 3 h.

- 2026-09-13 repo restructure: `bench/` is now top-level (was `tools/bench`); dead forks (integration, integration_harden, integration_notify) + slam moved to `archive/` (purged at freeze); harden2 runtime output consolidated under `logs/{sessions,traces,runs}`; `integration_tts` is the frozen demo fallback (was `integration/`); `.gitignore` slimmed. Recognizer bench unchanged at 410/487 (verified 2026-09-13, wall 237s).


## Extracted rulings preserved during the 2026-09-15 doc flatten

These were pulled from docs now retired to stale, so the binding content survives the flatten.

### Objective + proven/not-proven (from the 2026-08-27 "compass")
- Objective: a drone commanded by voice that understands the scene and acts. Human-in-the-loop, safety-gated.
  Camera drone, no weaponization/targeting/payload. "Kill switch" = flight-safety motor cut.
- Hardware bet: DJI Mini 4 Pro flown from a phone (ExoSkeletons MSDK app); the Linux laptop is the brain over
  WiFi -- control/telemetry on 8080, raw H.264 video on 5600. Tello/SITL era retired (recoverable from git).
- PROVEN (2026-08-25/26): MVD end-to-end voice->verb->drone + smart-CV answers, field-tested >3 h incl. a
  classroom flight; app builds/installs; discrete verbs round-trip on the real link; transport latency
  WS p95 24 ms / telemetry p95 47 ms, zero loss; REST mission actions drive the aircraft.
- NOT PROVEN (do not claim): end-to-end command->action latency < 1 s on the real link; video glass->Linux
  latency number; gimbal control (broken backend-side); the C++ llm_to_action engine flying end-to-end.
- Operational facts: phone IP = the WiFi hotspot gateway (changes per phone; derive from the default route);
  indoors the drone refuses horizontal/vertical sticks unless VPS locks (yaw + slow vertical otherwise);
  /status/ exposes no altitude, position3D null indoors; ONNX seg/depth on CPU keeps the 8 GB GPU free for the VLM.

### VRAM + perception campaign rulings (2026-09-07)
- tgemma + few-shots is the most accurate (90%) but VRAM-blocked (~2,478 MiB) -- not deployable on the 8 GB host.
- DictaLM stays the command path on CPU (99% commands) if a split is chosen; weak perception, CPU latency tail.
- Direction: everything-on-GPU at Q4 does not fit; one of tgemma/whisper moves to CPU, or tgemma drops to Q3.
  (Superseded later by the harden2 single-Gemma-direct-Hebrew planner; kept here as the measured record.)


## 2026-09-19 -- harden2 pre-freeze hardening: Gemma routing, crash-not-raise, swappable vision, doc pass

- Config knobs collapsed to SCENE_TTS / CONTROL / VIDEO / RECORD; the rest are baked constants.
- Command routing moved to the one Gemma call. The deterministic English BASIC verb tier was deleted;
  classify() now returns EMERGENCY / OVERRIDE / RESUME / COMPLEX only. Gemma emits takeoff, land, fly_by,
  spin_by, delay, gimbal_pitch, home, wave; a greeting becomes wave; follow/track/mark stay a camera
  highlight. Manual mode refuses flight (Pipeline.flight_allowed) while perception still answers.
  unified_bench held at 412/487 (was 410); zero false-fire on a non-command.
- No exceptions in our own code: fatal.py::die prints a loud reason and crashes (os._exit). Our raises in
  mvd/sam3_backend/llama/tts_io/camera_stream became die(); TTSConfigError was removed. Third-party errors
  we must catch (aplay, model HTTP retries) stay caught.
- The vision backend sits behind a contract (perception2/backend.py: VisionBackend Protocol + BACKENDS
  registry). build_highlight picks the backend once from SCENE_SEG; an unknown name crashes. SAM3 is the
  one backend today; another drops in without touching the engine.
- SAM3 highlight over-detected: it emitted several nested boxes per object. detect() now merges overlaps
  (IoU>0.5 or >70% containment), so one object draws one box. Caught by the webcam test.
- run_llama_server.sh pinned to gemma4 (qwen3vl alternate removed). Translator servers + the census bench
  removed; the live path has no translator.
- Full documentation staleness audit + fixes: specs, harden2 and bench READMEs repointed to the live
  system; CLAUDE.md links -> guidelines.md; 8 finished task docs archived to stale/.
