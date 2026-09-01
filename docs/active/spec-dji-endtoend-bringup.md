# Spec — DJI end-to-end bring-up: real drone over WiFi + Android app on the phone

**Owner:** the **DjiBackend agent** (this is the continuation of `spec-dji-backend.md`, mock → real
hardware). **Status:** prep NOW; execute when the drone + phone are on the bench. Runs in parallel
with the Thursday `llm_cv_scene` demo — no file collision.

## Why this exists
`spec-dji-backend.md` built `DjiBackend` against the **mock** (`scripts/test/dji_mock/mock_apiserver.py`).
That is done / in progress. This spec takes it the last mile: **stand up the real Android app on the
phone, connect the Linux stack to the real drone over WiFi, decode the video, and measure the true
end-to-end latency.** Two concrete asks from the human:

- **A. Run the `.apk` server on the phone** — build + deploy the ExoSkeletons app
  (`ExoSkeletons/DJI-android-sdk-v5-recon-swarm`), configured demo-safe, and confirm the Linux box
  can reach its API over WiFi.
- **B. Real link + latency** — point `DjiBackend` at the phone's IP, fly takeoff/land, stream sticks,
  poll telemetry, pull the camera stream, and **measure end-to-end latency** on every leg.

## Read first (all already in the repo — do not re-derive)
- `docs/active/spec-dji-backend.md` — the backend contract, the CRTP interface, the mock.
- `docs/active/spec-dji-websocket-protocol.md` — the FROZEN wire contract.
- `docs/active/dji-apiserver-review.md` — what the app exposes, the **blocking demo fixes**, the open
  integration questions (video, indoor position, gimbal, re-tasking, velocity envelope).
- `docs/active/dji-video-h264-over-tcp.md` — the raw-H.264/H.265-over-one-TCP-socket design, the exact
  Kotlin `VideoTcpStreamer`, and the GStreamer decode line. **Video is the #1 unblocker.**
- `docs/active/mission-brief-2026-08-15.md` — platform decision (DJI Mini 4/5 Pro), the whole project.
- `CLAUDE.md` + `docs/code-guidelines.md` — no git writes (suggest house-style commits), `rtk` for
  reads/greps, `Edit` tool blocked (python/Write), no virtual dispatch / no exceptions, portable
  (no CUDA-only assumptions — the Linux side decodes with GStreamer, vendor-neutral).

---

## Task A — the Android `.apk` on the phone (demo-safe)
1. **Build + deploy.** Clone `ExoSkeletons/DJI-android-sdk-v5-recon-swarm`, build the
   `SampleCode-V5/android-sdk-v5-sample` module in Android Studio (or `./gradlew assembleDebug`),
   install on the phone. Needs the DJI MSDK v5 app key registered for the app's package id.
2. **Make it demo-safe (from `dji-apiserver-review.md`):**
   - **`Tunneling.kt` must NOT start the Cloudflare/Pinggy relay.** Bind LAN-only. The challenge is
     local, no cloud, and a relay round-trip blows the <1 s budget. Confirm nothing auto-starts it.
   - Verify **POST `/c/takeoff` and `/c/land` respond** (`ok { status }`). If the build still ships
     the silent verbs, that is fine — `DjiBackend` confirms via telemetry (`aircraft.isFlying`), same
     as the mock's `MOCK_SILENT_VERBS` (204) mode. Note which build you have.
3. **Reachability.** With phone + laptop on the same WiFi, confirm from Linux:
   `curl http://<phone-ip>:<port>/status/` returns the aircraft JSON. Record the phone IP + port.

## Task B — Linux ↔ phone ↔ drone link
1. **Telemetry + verbs.** Point `DjiBackend` at `http://<phone-ip>:<port>` and `ws://<phone-ip>:<port>`.
   Bring up: poll `GET /status/` → `Odometry` (velocity3D + attitude; position dead-reckoned per Q2);
   `POST /c/takeoff` then `/c/land`, confirming from `isFlying`. **Props off / drone tethered for the
   first arm.**
2. **Stick stream.** Stream `FlightParam {vx,vy,vz,yaw}` (body FLU→FRU per the protocol spec) on
   `WS /c/ws/sticks` at ~18 Hz. This is also the keepalive; loss → drone brakes to hover (confirmed).
3. **Video.** If the app has the `VideoTcpStreamer` (H.264/H.265 over TCP, `dji-video-h264-over-tcp.md`):
   `POST /c/video/start`, then on Linux eyeball it:
   `gst-launch-1.0 tcpclientsrc host=<phone-ip> port=5600 ! h265parse ! avdec_h265 ! videoconvert ! autovideosink`
   (swap `h265`→`h264` per the `video codec=` log). Then feed it to perception via `appsink`.
   **Record the codec, resolution, fps.** If the build still only does RTMP, log that and fall back to
   the mock video until the app author adds the TCP streamer.

## Task C — end-to-end latency (the number the human wants)
Measure each leg on the **real** link, phone + drone on WiFi, and report a table.
- **Command→action (the scored <1 s):** t0 = stick setpoint emitted on Linux; t1 = drone velocity
  responds in telemetry. Stamp on Linux; use `velocity3D` crossing a threshold as t1.
- **Video glass-to-Linux:** point the camera at a millisecond clock / phone stopwatch; compare the
  timestamp in the decoded frame to Linux wall-clock. Report median + p95.
- **Telemetry round-trip:** `GET /status/` request→response, median + p95.
- **WiFi baseline:** re-confirm the laptop↔phone ping (earlier p95 ~12 ms @ 2.4 GHz; prefer 5 GHz).
Log the WiFi band, distance, and whether the tunnel was (correctly) off.

## Safety
First real arm: props removed or drone tethered, open space, a hand on the RC kill. Verify the
stick-loss → hover brake before any untethered flight.

## Done means
The `.apk` runs on the phone LAN-only, Linux reaches `/status/` over WiFi, `DjiBackend` flies a
tethered takeoff→hover→land on the real drone via streamed sticks, the camera decodes on Linux, and
a latency table (command→action, video, telemetry, WiFi) is recorded. Suggest house-style commits;
do not stage/commit. Report the codec/res/fps + the open `dji-apiserver-review.md` answers back into
the docs.

---

## Where each phase runs (workstation vs laptop/field) — so the two tracks parallelize
This work splits into two tracks that proceed IN PARALLEL and only meet at Phase 6.

- **WORKSTATION track (the AMD RX 7900 GRE GPU box; no drone needed):** develop `DjiBackend`
  against the mock (`scripts/test/dji_mock/mock_apiserver.py`), build + test the GStreamer
  H.264/H.265 decode against a canned clip or the mock, and prep the drone-stream input swap for
  `source/llm_cv_scene/` (Phase 6). All doable now, no hardware. Runs alongside the Thursday
  perception demo, which is also workstation-only.
- **LAPTOP / FIELD track (portable unit, AT the drone + phone):** Phase 0-1 (build + run the
  `.apk` on the phone), Phase 4 (real tethered flight), Phase 5 (latency on the real link).
  Requires the physical hardware; goes where the drone is.
- **CONVERGENCE (Phase 6):** point the real drone stream into `llm_cv_scene`. Needs both tracks
  mature — do it last.

Rule of thumb: touches the mock / code / decode -> WORKSTATION, now. Touches the real
phone / drone / RC / WiFi -> LAPTOP/FIELD. Keep the FROZEN wire contract byte-identical on both
so "point it at the phone IP" is the ONLY change when the field unit is ready.
