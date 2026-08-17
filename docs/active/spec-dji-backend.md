# Spec — Linux `DjiBackend` (talks to the Android recon-swarm app over LAN)

**Owner:** UNASSIGNED (this or a parallel agent). **Status:** ready to start against the mock.
**Runs parallel to** `spec-fmu-cleanup.md` — entirely new files, no collision.

---

## Context — read these first (a cold agent MUST load these)
- **`docs/active/mission-brief-2026-08-15.md`** — the project. Voice-commanded drone demo, Israeli
  MOD contest (~2026-08-28). Linux does perception + planning; a drone backend does I/O. Platform is
  a **DJI Mini via an Android phone bridge** (MSDK v5 is Android-only; there is no Linux DJI SDK).
- **`docs/active/dji-apiserver-review.md`** — what the Android app (a teammate's Kotlin Ktor server,
  `ExoSkeletons/DJI-android-sdk-v5-recon-swarm`) exposes, the 3 fixes we asked for, and the open
  integration questions. This is the punch list for the app author.
- **`docs/active/spec-dji-websocket-protocol.md`** — the FROZEN wire contract this backend targets.
- **`scripts/test/dji_mock/mock_apiserver.py`** — a faithful mock of the app's API. **Build and test
  the whole backend against this**, with no drone and no phone. Run:
  `pip install aiohttp && python3 scripts/test/dji_mock/mock_apiserver.py 0.0.0.0 8080`.
- **`docs/code-guidelines.md`** — **no virtual dispatch, no exceptions** (CRTP + tagged dispatch),
  guard clauses, WHY-comments, ~150-400 LOC files.
- **`CLAUDE.md`** — **reads/greps via `rtk`; run NO git writes** (human owns git; suggest house-style
  commits). The **`Edit` tool is blocked** — edit via `python3` string-replace or full-file `Write`.

## Why against a mock
The teammate who wrote the app is only available Tuesday, and the drone is co-located with him. The
mock lets the entire Linux backend + its servo loop be built and tested NOW; real integration then
becomes "point it at the phone's IP." (Also pending: fetch the Kotlin source from GitHub once GitHub is
back up, and a phone-side WiFi test — laptop<->phone round-trip already measured good, p95 ~12 ms on
2.4 GHz over a sustained stream.)

## Build / verify command
```
cmake --build build/release/shared/px4 -- -j4     # existing; add a "dji" backend + a convert test
```
Model the CMake + test on `source/llm_to_action/tello_backend/` (which fetches `ctello` DOWNLOAD_ONLY
and compiles its one TU directly, and has a hardware-free `test/tello_convert_test.cpp`).

---

## The interface to implement (CRTP — no virtuals)
`DjiBackend` is a sibling of `PX4Backend` / `TelloBackend`. It derives
`GenericBackend<DjiBackend>` (`source/llm_to_action/generic_backend/generic_backend.hpp`) and supplies
these `*_impl` methods (compile-time dispatch, force-inlined):

```
bool          start_impl();                 void stop_impl();
BackendStatus takeoff_impl();               BackendStatus land_impl();
void          set_velocity_impl(Vec3 worldVelEnu, f32 yawspeed);   // ENU world vel + yaw rate rad/s CCW+
void          disarm_impl();                void force_disarm_impl();
Odometry      odometry_impl() const;        IOState state_impl() const;   i32 battery_pct_impl() const;
```
Types are in `generic_backend/generic_backend_types.hpp` (`Odometry` = ENU meters, `IOState`,
`BackendStatus`). **Study `tello_backend/tello_backend.hpp` + `.cpp` + `tello_backend_base.hpp`** —
`DjiBackend` mirrors them: ROS-free, own `std::thread` loops, `std::atomic` telemetry, opaque client
type forward-declared in the header.

## The wire (from spec-dji-websocket-protocol.md, confirmed against the app source)
- **Control:** `WS /c/ws/sticks`, client streams `FlightParam = { vx, vy, vz, yaw }` — **body-frame
  m/s** (vx fwd, vy **right**, vz up) + yaw rate — the app flushes to the drone at ~18 Hz. The stream
  is also the keepalive.
- **Telemetry:** `GET /status/` -> `{ aircraft:{ isFlying, battery, velocity3D:{x,y,z}, position3D,
  attitude, gimbalAttitude }, ... }`. `velocity3D` is the trustworthy indoor signal.
- **Verbs:** `POST /c/takeoff`, `/c/land` (discrete). Ignore `/c/fly` (mission API — not used).
- **Responses:** `{ok:true,...}` / `{ok:false,error}` / `{ok:false,djiError{...}}`.

## Frames
`set_velocity_impl` gets **ENU world** velocity. DJI FlightParam is **body forward-right-up**. Reuse
`frame/frame_convert.hpp`: `enu_to_flu(worldVelEnu, yaw)` gives body forward-**left**-up, so
`FlightParam = { vx=fwd, vy=-left (=right), vz=up, yaw=yawspeed }`. **CONFIRM the yaw sign** (CW+ vs
CCW+) against `AircraftController.kt` and the mock before flight. Telemetry: `position3D` is GPS
(invalid indoors) — **dead-reckon position from `velocity3D`**; map `velocity3D` + `attitude` into
`Odometry` (ENU).

---

## Tasks
1. **Vendor the WebSocket client.** cpp-httplib (already in the tree, used by `llamaclient`) has NO WS
   client. Vendor **websocketpp + standalone Asio** (header-only), FetchContent like `ctello`,
   configured **exception-free**. Keep it opaque: forward-declare the client in `dji_backend.hpp`,
   include websocketpp only in `dji_backend.cpp`. (Alt considered + rejected: rbeeli/websocketclient-cpp
   is C++23; the tree is C++17 — don't force the bump. easywsclient is too old.)
2. **`dji_backend_base.hpp`** (pure, ROS-free, mirrors `tello_backend_base.hpp`): host/port, stream
   rate (~18-20 Hz), poll rate (~10-20 Hz), **velocity clamp** (max m/s + yaw rate), the ENU->body
   `FlightParam` map, and the `/status` JSON parse -> `Odometry`. All unit-testable.
3. **`dji_backend.hpp`**: `class DjiBackend : public GenericBackend<DjiBackend>` — opaque WS + HTTP
   clients, atomics for telemetry, two `std::thread` loops. ROS-free by construction.
4. **`dji_backend.cpp`**: stick-stream thread (serialize `FlightParam` JSON, send on the WS at
   ~18-20 Hz — this is also the keepalive); telemetry-poll thread (cpp-httplib `GET /status/` at
   ~10-20 Hz -> parse -> atomics); `takeoff`/`land` POST. Match Tello's no-mutex atomics model; one
   mutex only if a single socket is written from multiple threads.
5. **CMake + build wiring**: a `Drone::dji_backend` library + a `dji_convert_test` (hardware-free,
   tests the frame map + `/status` parse), and a `dji` option in `build.sh` alongside `px4`/`tello`.
6. **Test against the mock**: run `mock_apiserver.py`, point the backend at `ws://127.0.0.1:8080` /
   `http://127.0.0.1:8080`. The mock logs every stick message and integrates them into moving
   telemetry, so the whole servo loop can be brought up offline.

## Integration dependencies (owned by the app author — track, don't block on)
From `dji-apiserver-review.md`: **video** (raw H.264 over a TCP socket — being implemented, ~1.5 days;
consume it once it lands), **indoor position** (dead-reckon from `velocity3D`; confirm whether a fused
pose is available), **velocity envelope** (clamp values), **gimbal** (deferred). Disconnect is a
non-issue — the drone brakes to hover on stick-stream loss (DJI virtual-stick behavior; confirmed).

## Done means
`dji_convert_test` passes (frame map + parse), and `DjiBackend` drives the mock end to end — takeoff,
streamed velocity that moves the mock's telemetry, land — with the build compiling + linking. Then it
is ready to point at the real phone. Suggest house-style commits; do not stage/commit.
