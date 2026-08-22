# DJI end-to-end bring-up runbook

Do this on the bench, in order, to take `DjiBackend` from the mock to the real drone over WiFi.
It executes `spec-dji-endtoend-bringup.md` (Tasks A/B/C). Every step is a copy-paste command.
Fill the latency table at the bottom as you go.

**Safety first.** The first arm is props-off or tethered, in open space, with a hand on the RC kill.
Confirm the stick-loss hover-brake before any untethered flight.

Placeholders: `<PHONE_IP>` = the phone's WiFi address, `<PORT>` = the app's ApiServer port.

---

## Task A — the app on the phone, LAN-only

1. **Build + install.** Clone `ExoSkeletons/DJI-android-sdk-v5-recon-swarm`. Build the
   `SampleCode-V5/android-sdk-v5-sample` module and install it:
   ```bash
   ./gradlew :android-sdk-v5-sample:assembleDebug
   adb install -r SampleCode-V5/android-sdk-v5-sample/build/outputs/apk/debug/*.apk
   ```
   The MSDK v5 app key must be registered for the app's package id.

2. **Kill the cloud tunnel.** Confirm `Tunneling.kt` never starts the Cloudflare/Pinggy relay.
   Grep the source for `trycloudflare`, `argotunnel`, `pinggy`. Nothing may auto-start it. The
   challenge is local. A relay round-trip blows the 1 s budget.

3. **Note the verb build.** Check whether `POST /c/takeoff` and `/c/land` reply with a body.
   Either build works — `DjiBackend` confirms takeoff/land from telemetry (`isFlying`), same as the
   mock's `MOCK_SILENT_VERBS` mode. Just record which build is on the phone.

4. **Reachability.** Phone and laptop on the same WiFi. From Linux:
   ```bash
   curl http://<PHONE_IP>:<PORT>/status/
   ```
   You want the aircraft JSON back. Record `<PHONE_IP>` and `<PORT>`.

---

## Task B — Linux ↔ phone ↔ drone

Build the backend tests. The full tree needs ROS/PX4, so the quick path is a standalone compile
of just the DjiBackend (no ROS). Both the soak test and the latency probe build this way:

```bash
UTIL2=build/release/shared/px4/_deps/sttserver-src/dependencies/util2/include
HTTPLIB=build/release/shared/px4/_deps/cpp-httplib-src
NLOHMANN=build/release/shared/px4/_deps/nlohmann_json-src/include
g++ -std=c++17 -O2 -pthread -Isource/llm_to_action -I"$UTIL2" -I"$HTTPLIB" -I"$NLOHMANN" \
  source/llm_to_action/dji_backend/dji_backend.cpp \
  source/llm_to_action/dji_backend/dji_ws_raw.cpp \
  source/llm_to_action/dji_backend/test/dji_latency_probe.cpp \
  -o /tmp/dji_latency_probe
```
(Inside the full CMake build the same target is `dji_latency_probe`; the standalone line is faster
on the bench.)

1. **Telemetry + verbs, tethered arm.** Point the soak test at the phone and hold a stream for a
   minute. It streams sticks at 18 Hz, polls `/status/`, arms, holds, and lands:
   ```bash
   # (compile dji_backend_mock_test the same way, swapping the last source file)
   ./dji_backend_mock_test <PHONE_IP> <PORT> 60
   ```
   Watch the drone arm, hold, and land. **Props off / tethered.** Confirm hover-brake: pull the WiFi
   for ~2 s mid-hold; the drone must brake to hover, not drift.

2. **Video.** If the app has the `VideoTcpStreamer` (`dji-video-h264-over-tcp.md`), start it, then
   eyeball the decode on Linux:
   ```bash
   curl -X POST http://<PHONE_IP>:<PORT>/c/video/start
   gst-launch-1.0 tcpclientsrc host=<PHONE_IP> port=5600 ! decodebin ! videoconvert ! autovideosink
   ```
   `decodebin` picks H.264 vs H.265 for you. Read the app's `video codec = ...` log line and
   **record the codec, resolution, and fps.** If the build is still RTMP-only, note it and fall back
   to `scripts/test/dji_mock/video_tcp_mock.py` until the app author adds the TCP streamer.

3. **Feed perception.** The real receiver is the DJI path in `gstreamer_udp_cam_rx/rx_node`
   (`--dji <PHONE_IP>`); it publishes `camera/stream`. Bring it up once the eyeball decode works.

---

## Task C — the latency table

Measure each leg on the real link. Log the WiFi band, distance, and that the tunnel is off.

1. **Command→action** (the scored < 1 s). This drives the real backend, steps the setpoint, and
   times how long until the drone's `velocity3D` responds in telemetry:
   ```bash
   /tmp/dji_latency_probe <PHONE_IP> <PORT> 30 8
   ```
   Take `command->action` median / p95 from its table. **Props off / tethered.**

2. **Telemetry round-trip.** The same probe prints `telemetry GET RTT` (median / p95). Use it.

3. **WiFi baseline.** Run the WS echo probe at command cadence. On the phone (Termux),
   then the laptop:
   ```bash
   # phone:   python3 ws_latency.py server 0.0.0.0 <PORT>
   python3 scripts/test/dji_mock/ws_latency.py client ws://<PHONE_IP>:<PORT> --hz 20 --secs 30
   ```
   Prefer 5 GHz. Record p50 / p95 / p99. One-way ≈ RTT/2.

4. **Video glass-to-Linux.** Point the camera at a phone stopwatch showing milliseconds. Freeze a
   decoded frame on Linux next to Linux wall-clock. The difference is the glass-to-Linux latency.
   Report median + p95 over several frames.

### Fill this in

| Leg                    | median | p95 | notes (band / distance / tunnel-off) |
|------------------------|--------|-----|--------------------------------------|
| command → action       |        |     |                                      |
| video glass → Linux     |        |     |                                      |
| telemetry GET round-trip| 35.6 ms| 46.8 ms | 5 GHz hotspot; 9867 samp/360 s, 0 loss; p99 62.5 / max 1064 (1 stall) |
| WiFi baseline (WS RTT)  | 16.4 ms| 23.6 ms | 5 GHz hotspot; 7157 samp/360 s, 0 loss; p99 36.1 / max 152; jitter 6.8 |

Mock floor for reference (localhost, no drone dynamics): command→action ≈ 67 ms (the 15 Hz poll
granularity), telemetry RTT ≈ 1 ms. The real link adds WiFi and rotor spin-up.

---

## Report back into the docs

- **Codec / resolution / fps** → `dji-video-h264-over-tcp.md` and `spec-dji-websocket-protocol.md`.
- **Open `dji-apiserver-review.md` answers** confirmed on hardware: velocity3D frame, indoor
  position (dead-reckon vs a fused pose), the velocity envelope, `kDjiYawRateSign`, gimbal,
  mid-flight re-tasking. Flip the `UNCONFIRMED` constants in `dji_backend_base.hpp` once measured.
- Suggest house-style commits; the human runs every git write.
