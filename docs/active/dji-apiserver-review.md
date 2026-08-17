# Code review — recon-swarm `ApiServer` (integration + demo hardening)

Nice work getting this flying solo. We're going to use your app as a **backend service only** —
our Linux stack (perception + planning) talks to it over the LAN, streams stick velocities, and
reads telemetry, exactly like our existing PX4 and Tello backends. This is about making that
integration solid and the app **demo-safe**; the design is good.

Reviewed the actual code (`ApiServer.kt`, `Tunneling.kt`, `AircraftController.kt`,
`SerializerUtils.kt`, `dto/Responses.kt`, 2026-08-15). We've frozen the wire contract on our side
and built a **mock of your ApiServer**, so we can finish the Linux backend before integrating.

---

## What we already read (FYI — correct us only if we got it wrong)

- **`FlightParam` = `{ vx, vy, vz, yaw }`** (nullable doubles): **body-frame velocities in m/s**
  (vx forward, vy right, vz up) + yaw rate. Your app buffers and flushes these to the drone at
  **~18 Hz**. So we stream velocity setpoints directly — no stick-% curve needed.
- **`velocity3D` = `{ x, y, z }`.**
- **Init:** `init(takeStickControl=true)` runs `ac.init()` -> `rc.listen()` -> `vSticks.takeControl()`
  -> transmission; takeoff via `ac.takeoff()`. So **virtual stick is enabled by your init** — we
  don't POST anything to arm it.
- **Responses:** `{ok:true,…}` / `{ok:false,error}` / `{ok:false,djiError{…}}` / `{ok:true,status}`.
- **Endpoints:** `GET /status[/battery|/gps|/signal]`, `WS /c/ws/sticks`, `POST /c/takeoff|land|fly`,
  `POST /key`.

---

## Blocking — must fix for the demo

1. **`Tunneling.kt` routes through the cloud.** It sets up a Cloudflare/Pinggy relay
   (`trycloudflare.com`, `argotunnel.com`). The challenge is **local, no cloud** — and a relay
   round-trip kills our <1 s budget. **Bind LAN only; never start the tunnel.** Confirm nothing
   auto-starts it.
2. **`takeoff` / `land` send no response body** — add an `ok { status = … }` so we can confirm
   the command was accepted.

---

## Critical integration questions (what we need from your API to wire our features)

These are the ones we actually need answered — they decide whether your API supports our system.

1. **Video to the client — the #1 gap.** `ApiServer` exposes no video, and our perception
   (voice -> see -> act) runs on **Linux**, so we need the MSDK camera feed off the drone.
   **Preferred: forward the raw H.264 stream** from `ICameraStreamManager` — register a stream
   listener and ship the NAL units over a plain TCP socket; we decode on Linux (~150-300 ms, no
   media server). **Acceptable: MJPEG-over-WebSocket** at 5-10 fps (reuses your Ktor server).
   **Avoid RTMP** — DJI's `LiveStreamManager` makes it a one-liner, but it needs an ingest server
   and lands at ~1-5 s latency, which breaks our closed see->act loop. Whatever you pick, tell us
   resolution / fps / latency. **This blocks the entire perception half of the demo.**
2. **Indoor position.** `position3D` looks like it serializes `LocationCoordinate3D`
   (lat/lon/alt = **GPS**), which is invalid indoors. Does MSDK give you a **fused / VPS local
   pose** indoors that you can surface in `/status`, or should we **dead-reckon from `velocity3D`**?
   This decides our whole indoor control approach.
3. **Gimbal control.** You have `IGimbal` (`angleCamera`, `lookTo`) internally, but it isn't on the
   API. We want to **aim the camera at the target** for tracking, without yawing the airframe.
   Please expose gimbal pitch/yaw over the API.
4. **Mid-flight re-tasking (sequential commands).** Can we **interrupt a running `/c/fly` mission**
   by sending `/c/ws/sticks` (or a stop), so we can chain commands ("find X … now follow … now
   land")? Or is it one-mission-at-a-time? This is a scored criterion for us.
5. **Velocity envelope.** Max magnitude / clamping on `vx/vy/vz` (m/s) and `yaw` (rad/s or deg/s)?
   So our servo gains are sane.

---

## What our backend does (the contract you're holding)

- Stream `{ vx, vy, vz, yaw }` on `WS /c/ws/sticks` at ~10–20 Hz (this is also our keepalive).
- Poll `GET /status/` at ~10–20 Hz -> odometry (`velocity3D` + `attitude`; position via Q2).
- `POST /c/takeoff | /c/land | /c/fly` for discrete verbs; consume the video stream once it exists.
- Direct LAN, tunnel off.

Let's pair over the code. The three that unblock the most for us, in order: **video (Q1), indoor
position (Q2), gimbal (Q3).**
