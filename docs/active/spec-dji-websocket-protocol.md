> **STATUS 2026-08-26 — read first.** This is the low-level **wire contract**, kept for reference.
> The **MVD does NOT drive via `WS /c/ws/sticks`** — it uses **REST `POST /c/fly {mission:[…]}`
> mission actions** (see `mvd-voice-command-table.md`). The WS-sticks velocity stream below is the
> channel for the **C++ `llm_to_action` `DjiBackend`** track, not the Python MVD.
> Fix-status since this was frozen: **#2 video path is DONE** (raw H.264 over TCP `:5600`, auto-starts
> with the app). **Still open (dev-owned):** takeoff/land response bodies, **gimbal (broken
> backend-side)**, and dynamic groundstation-IP discovery. The `10.222.215.92` examples are **stale** —
> the phone IP is the WiFi gateway; derive it.

# FROZEN spec — DJI bridge websocket protocol (v1)

The contract between the **Linux `DjiBackend`** and the **Android `ApiServer.kt`** (recon-swarm
app). Freeze this; build `DjiBackend` against the mock (`scripts/test/dji_mock/mock_apiserver.py`),
swap the endpoint for the real app once integrated. Extracted from `com/kcg/dr/api/ApiServer.kt`
+ `AircraftController.kt` + `SerializerUtils.kt` (2026-08-15). Most fields are resolved from the
code; the open items are the feature-integration questions at the bottom.

## Transport

- **Ktor HTTP + WebSocket**, configurable `host:port`. Bind on the **LAN** (Android hotspot or a
  shared AP). Linux client hits `http://<android-ip>:<port>` + `ws://<android-ip>:<port>`.
- **DISABLE `Tunneling.kt`.** It routes through **Cloudflare/Pinggy cloud relays** -> violates the
  "no cloud" fixed requirement AND adds a relay round-trip that blows <1 s. **Direct LAN only.**

## Endpoints

**Telemetry (GET, poll ~10-20 Hz; MSDK updates ~10 Hz so faster polling just re-reads):**
- `GET /status/` ->
  ```json
  { "aircraft": { "isFlying": bool, "battery": number,
                  "velocity3D": {…}, "position3D": {…}, "attitude": {…}, "gimbalAttitude": {…} },
    "product":    { "version": str, "connection": bool },
    "controller": { "version": str, "connection": bool } }
  ```
  `velocity3D` = `{x,y,z}` (read from `SerializerUtils.kt`). `position3D` likely serializes
  `LocationCoordinate3D` = `{latitude,longitude,altitude}` (**GPS -> invalid indoors**); plan to
  dead-reckon from `velocity3D` unless the author surfaces a fused/VPS local pose. `attitude`: confirm.
- `GET /status/battery` -> `{ voltage, capacity, remaining, percent }`
- `GET /status/gps`     -> `{ satCount, signalLevel, valid, compass }`
- `GET /status/signal`  -> `{ connection, quality, frequency, range }`

**Control:**
- **`WS /c/ws/sticks`** — client streams `FlightParam` JSON; server echoes `{ "param": "…" }`.
  This stream is also the **keepalive** — stop sending and the drone times out.
  `FlightParam` = `{ vx, vy, vz, yaw }` (nullable doubles) — **body-frame velocities in m/s**
  (vx fwd, vy right, vz up) + yaw rate; the app flushes to the drone at ~18 Hz. (Read from `AircraftController.kt`.)
- `POST /c/takeoff`, `POST /c/land` — discrete. (Handlers currently send **no response body** — see fixes.)
- `POST /c/fly` — `{ "mission": [ Action… ] }`; responds `{ "ok": true, "status": "starting mission" }`.
- `POST /key` — MSDK key activation (the `KeyRequest` system). **CONFIRM** the boot sequence.

**Response wrapper (`dto/Responses.kt`):**
- ok: `{ "ok": true, … }` · status: `{ "ok": true, "status": "…" }`
- error: `{ "ok": false, "error": "…" }`
- DJI error: `{ "ok": false, "djiError": { errorType, errorCode, innerCode, description, hint } }`

## REQUIRED FIXES before it flies (app-side, for the author)

1. **Tunnel off** — never start `Tunneling.kt`; bind LAN only. (No-cloud + latency.)
2. **Video path** — `ApiServer` does **not** stream video. Linux perception needs frames.
   **Preferred:** forward raw H.264 NAL units from `ICameraStreamManager` over a TCP socket
   (~150-300 ms, no media server). **Acceptable:** MJPEG-over-WS at 5-10 fps. **Not RTMP** (needs
   an ingest server, ~1-5 s latency -> breaks the closed loop). **This is the critical-path gap.**
3. **Takeoff/land responses** — handlers call `controller.fly()` with no `call.respond()`; add one so
   the client can confirm the command landed.

## Linux `DjiBackend` (CRTP sibling of `PX4Backend`/`TelloBackend`)

- **Control:** open `WS /c/ws/sticks`; map FMU velocity setpoints -> `FlightParam`; stream 10-20 Hz.
- **Telemetry -> `Odometry`:** poll `GET /status/` at 10-20 Hz; parse `position3D`/`velocity3D`/
  `attitude` -> `nav_msgs/Odometry`. (Pull-based; if latency bites, ask the author to add a telemetry-push WS.)
- **Verbs:** `POST /c/takeoff|land|fly`.
- **Video:** consume the stream once fix #3 lands.

## Critical questions for the author (feature integration)

- **Video to the client** -- not exposed; Linux perception needs the MSDK feed. The #1 gap.
- **Indoor position** -- fused/VPS local pose available, or do we dead-reckon from `velocity3D`?
- **Gimbal** -- `IGimbal` exists internally but isn't on the API; expose pitch/yaw for target tracking.
- **Mid-flight re-tasking** -- can `/c/ws/sticks` interrupt a running `/c/fly` (sequential commands)?
- `/key` activation sequence + whether virtual-stick auto-holds when no `FlightParam` arrives.
