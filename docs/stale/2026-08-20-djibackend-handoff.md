# HANDOFF — DjiBackend <-> Exoskeletons app: test-now plan + in-depth rundown (2026-08-20)
For a new manager agent. Goal the human set: **prove `llm_to_action` + `DjiBackend` drives the REAL drone
with dumb velocity/takeoff/land commands (NO VLM, NO perception), measure command->action latency, then
pick milestones.** The workstation now has a WiFi card (the laptop died) so it can join the drone's WiFi.

## 0. TL;DR — is our backend still valid against the app? MOSTLY YES.
The app's **core control wire is intact**: `WS /c/ws/sticks` (decodes our `{vx,vy,vz,yaw}` JSON straight
into `AircraftController.FlightParam` -> `sendFlightParam`), `GET /status/` (isFlying, battery,
velocity3D, attitude, gimbalAttitude), `POST /c/takeoff` + `/c/land`. So `DjiBackend` should fly the
drone for simple commands **today**. Two real gaps + several UNCONFIRMED constants below.

## 1. OUR side — C++ DjiBackend (source/llm_to_action/dji_backend/)  [in-depth]
Files: `dji_backend.{hpp,cpp}`, `dji_backend_base.hpp` (pure wire math), `dji_status_parse.hpp` (/status
JSON), `dji_ws.hpp` + `dji_ws_raw.cpp` / `dji_ws_wspp.cpp` (WS client, two impls), plus `test/`:
`dji_backend_mock_test.cpp` (soak: arm/stream/hold/land), `dji_convert_test.cpp` (frame map + parse),
`dji_latency_probe.cpp` (command->action + telemetry RTT), `dji_ws_test.cpp`.
- CRTP `GenericBackend<DjiBackend>` sibling of PX4/Tello; ROS-free; own threads + atomics.
- Wire constants (dji_backend_base.hpp): host/port (default 127.0.0.1:8080), `/c/ws/sticks`, `/status/`,
  `/c/takeoff`, `/c/land`, video TCP `kDjiVideoPort=5600`. Stream 18 Hz, poll 15 Hz.
- **Frame math:** interface takes ENU-world velocity; `enu_vel_to_flightparam()` -> body FlightParam
  (`vy = -left` since DJI is forward-RIGHT-up). Velocity clamp `kDjiMaxSpeedMps=2.0`, yaw clamp
  `M_PI` (~180 deg/s IF the app reads rad/s -- SEE risk #2). Serialiser: snprintf `{"vx"..,"vy"..,"vz"..,"yaw"..}`.
- **Verified this session:** the standalone (no-ROS) `dji_latency_probe` COMPILES clean via the runbook's
  g++ line. Deps present (util2, cpp-httplib, nlohmann under build/release/shared/px4/_deps).
- **UNCONFIRMED constants (flagged in the header itself):** `kDjiYawRateSign` (CW+ vs CCW+),
  velocity envelope, yaw UNITS (see risk #2).

## 2. THE APP side — Exoskeletons Kotlin server  [in-depth rundown]
Repo: `ExoSkeletons/DJI-android-sdk-v5-recon-swarm` (PUBLIC, main, ~438 commits). Ktor server under
`SampleCode-V5/.../com/kcg/dr/api/`. Files: `ApiServer.kt` (535 lines, all routes), `VideoTcpServer.kt`
(79), `SerializerUtils.kt`, `Tunneling.kt` (cloud relay — MUST stay off), `dto/*` (Responses, FlyRequest,
StreamRequest, KeyRequest, TTSRequest, actions/*), `flight/AircraftController.kt` (1371), `flight/dji/DJICamera.kt`.

**Full route surface (ApiServer.kt):**
- `GET /` -> handshake (rc/aircraft/product availability).
- `GET /status/` (+ `/status/battery`, `/status/gps`, `/status/signal`) -> isFlying, battery, **velocity3D**,
  location3D (GPS -- invalid indoors), attitude, gimbalAttitude, firmware, connection. **<- our telemetry source.**
- `WS /c/ws/echo`, `WS /c/ws/sticks` (**our control**: decodes `FlightParam` -> `sendFlightParam`),
  `WS /c/ws/telemetry` (**NEW: telemetry PUSH stream** -- we don't use it; a latency win over 15 Hz polling).
- `POST /c/takeoff`, `POST /c/land`, `POST /c/stop`, `POST /c/flyTo`, `POST /c/lookAt`, `POST /c/fly`
  (mission actions), and legacy `GET /(fly|takeoff)` / `GET /land` (semantically wrong, still present).
- `POST /tts` (text-to-speech on the aircraft speaker). `POST /key`. Regex quick-actions (wave/hi/...).
- `route("/c/stream")`: `POST /start {rtmpUrl}` -> `cam.startStream(url)` (**RTMP**), `POST /stop`, `GET /status`.
- Rich `dto/actions/`: Circle, Square, FlyBy, SpinBy, FlyTo, FlyToMe, FollowMe, TrackMe, ScanGround,
  GimbalPitch, LookAt, Wave, Delay, ReportStatus, Takeoff, Land. (App-author mission verbs -- we don't need them.)
- `AircraftController.FlightParam { var vx,vy,vz,yaw: Double? }` -- nullable, field names MATCH ours. The
  sticks WS does `Json.decodeFromString<FlightParam>(text)` then `sendFlightParam` -> `sendStickParam` ->
  DJI virtual stick. `takeControl()` grabs virtual stick on init.

## 3. DRIFT ANALYSIS — our backend vs the CURRENT app
MATCHES (works today): `/c/ws/sticks` + `{vx,vy,vz,yaw}` field names; `/status/` shape (velocity3D/attitude/
isFlying/battery); `POST /c/takeoff`,`/c/land`. **-> DjiBackend can drive simple velocity + takeoff/land now.**
GAPS / RISKS:
1. **VIDEO (real gap).** `VideoTcpServer.kt` (raw H.264/H.265 NAL over a TCP `ServerSocket`, via
   `ICameraStreamManager.ReceiveStreamListener`) EXISTS, but **it is NOT referenced anywhere in
   `ApiServer.kt`** -- the only route, `POST /c/stream/start`, still starts **RTMP** (`cam.startStream(rtmpUrl)`).
   So the raw-TCP video our `kDjiVideoPort=5600` expects has **no server-side trigger in ApiServer**. ACTION:
   confirm whether `VideoTcpServer.start(port)` is invoked elsewhere (`ApiServerService.kt`/`DJICamera.kt`);
   if not, either (a) ask the app author to wire it into a route + confirm the port, or (b) fall back to the
   RTMP->MediaMTX->RTSP path (the Python prototype already uses this) until the TCP streamer is wired.
2. **YAW UNITS + SIGN (HIGH-RISK unconfirmed).** Our serialiser sends `yaw` in **radians/s** (clamped to
   pi ~= 3.14). DJI virtual stick yaw is conventionally **deg/s**, and `AircraftController.yaw(degrees:...)`
   takes degrees. If `sendFlightParam` passes `FlightParam.yaw` straight to the DJI virtual stick expecting
   deg/s, our pi rad/s reads as ~3 deg/s (~57x too slow), and the SIGN (CW+/CCW+) is also unconfirmed.
   ACTION: read `VirtualStickVM.sendStickParam` / the DJI param mapping; fix `dji_backend_base.hpp` yaw
   units + `kDjiYawRateSign`. (vx/vy/vz m/s likely fine; yaw is the risk.)
3. **Velocity envelope** `kDjiMaxSpeedMps=2.0` still a guess -- confirm the drone's virtual-stick max.
4. **NOT-used-but-available:** `WS /c/ws/telemetry` (push telemetry, lower latency than our poll),
   `POST /tts`, the mission actions. Optional; the telemetry WS is worth adopting for the <1 s budget.

## 4. TEST PLAN — RIGHT NOW (no VLM, no perception)  [from dji-bringup-runbook.md]
Pre-flight (no drone, proves the backend): `pip install aiohttp`; run the mock
`python3 scripts/test/dji_mock/mock_apiserver.py 0.0.0.0 8080`; standalone-compile + run the soak test and
the latency probe against `127.0.0.1:8080` (mock floor: command->action ~67 ms, telemetry RTT ~1 ms).
Compile (verified): the g++ line in the runbook (Task B) -> `/tmp/dji_latency_probe`.
Real drone (Tasks A/B/C, dji-bringup-runbook.md): install the app on the phone via the RC-N3; confirm
`Tunneling.kt` does NOT start a tunnel; `curl http://<PHONE_IP>:<PORT>/status/`; run
`./dji_backend_mock_test <PHONE_IP> <PORT> 60` (props off/tethered, confirm stick-loss hover-brake);
then `/tmp/dji_latency_probe <PHONE_IP> <PORT> 30 8` -> fill the latency table (command->action p50/p95).

## 5. NEXT MILESTONES (orient from the latency number)
- If command->action p95 < 1 s on the real link -> the control spine is DEMO-VALID. Proceed to
  `feature-total-integration` **simple mode** (voice->intent->deterministic verb->DjiBackend).
- Fix yaw units/sign (risk #2) BEFORE any yaw command in flight.
- Decide video: wire VideoTcpServer (author) vs RTMP fallback (us) -- gates the perception-on-drone half.
- Adopt `WS /c/ws/telemetry` if polling latency hurts the budget.

## 6. CONTEXT (what this whole session was)
Global objective + how this session drifted: `docs/active/2026-08-20-project-context-recovery.md` (READ FIRST).
The Python perception prototype (source/llm_cv_track + llm_cv_scene) passed the 2026-08-20 gate; it is a
component to fold into the C++ system, NOT the destination. DJI specs: spec-dji-backend.md,
spec-dji-websocket-protocol.md, dji-apiserver-review.md, spec-dji-endtoend-bringup.md, this runbook.
