# DJI bring-up & test toolkit

Everything here tests the DJI link (control, telemetry, video) from the workstation, with **no motors**.
Each tool below lists its purpose, usage, and a **manual fallback** — the raw command that does the same
thing if the script fails or you want to see it by hand.

## Golden rules (read first)
- **Never hardcode the phone IP.** It is the WiFi hotspot gateway and CHANGES on every phone reboot.
  Always derive it:
  ```bash
  GW=$(ip route show dev wlp2s0 | awk '/^default/{print $3}')
  ```
- **Verify 8080 first.** If `8080` itself times out, you are on the wrong IP (stale) — re-derive; it is
  NOT a firewall.
- **Safety:** the assistant never sends arm/takeoff/land/stick commands to a real drone. Read-only tools
  (status, telemetry, video receive) are safe. See `../../../CLAUDE.md` and
  `../../../docs/runbooks/kill-switch-verification.md`.
- Ports: **8080** = control + telemetry (HTTP + WS), **5600** = raw H.264 video (TCP).

---

## One-shot health check — `dji_check.sh`
Derives the live IP, shows the `/status` chain, and probes video. Run this first, always.
```bash
bash tools/dji_mock/dji_check.sh
```
Good output: `/status` returns aircraft JSON, video shows `VIDEO LIVE`.
**Manual fallback:**
```bash
GW=$(ip route show dev wlp2s0 | awk '/^default/{print $3}')
curl -s "http://$GW:8080/status/"; echo
python3 tools/dji_mock/probe_video.py "$GW" 5600 5
```
503 body meanings (the DJI chain is down): "No connection to Remote Controller" (phone↔RC USB),
"...Aircraft" (aircraft off/not linked), "Product not connected" (MSDK not activated — restart app).

---

## Telemetry latency — `measure_telemetry.py`
End-to-end round-trip: workstation → phone → drone → back (`GET /status/`). Read-only.
```bash
python3 tools/dji_mock/measure_telemetry.py <host:port> [secs=360] [csv_out]
# e.g.
python3 tools/dji_mock/measure_telemetry.py "$GW:8080" 360 out/tel.csv
```
Preflight aborts cleanly if the chain is down. Prints min/p50/p90/p95/p99/max/mean/jitter.
**Manual fallback (rough RTT):**
```bash
for i in $(seq 20); do curl -s -o /dev/null -w "%{time_total}\n" "http://$GW:8080/status/"; done
```

## Transport latency — `measure_ws_rtt.py`
Workstation → controller round-trip over WebSocket `/c/ws/echo` (no drone). Isolates WiFi+phone cost.
Zero-dependency raw RFC6455 client (skips control frames — do not "fix" that).
```bash
python3 tools/dji_mock/measure_ws_rtt.py <host:port> [secs=360] [hz=20] [csv_out]
python3 tools/dji_mock/measure_ws_rtt.py "$GW:8080" 360 20 out/ws.csv
```
Sanity: WS RTT must be LOWER than telemetry (it skips the drone read). If not, the numbers are wrong.
**Manual fallback:** none simple (needs a WS client); use the script.

## Latency plots — `plot_latency.py`
Turns the two CSVs into graphs (timeseries + histogram + overlay).
```bash
python3 tools/dji_mock/plot_latency.py <telemetry.csv> <wsrtt.csv> <out_dir>
```

## Video reachability — `probe_video.py`
Connects to the raw H.264 TCP port, reads bytes, reports codec (H.264 vs H.265) + bitrate. Receive-only,
sends nothing.
```bash
python3 tools/dji_mock/probe_video.py <host> [port=5600] [secs=5]
```
- `VIDEO LIVE` = frames flowing. `CONNECTED but NO DATA` = socket up but drone/camera not producing.
- `cannot connect ... timed out` = wrong IP (stale) or app server off.
**Manual fallback (does data arrive?):**
```bash
timeout 5 nc "$GW" 5600 | wc -c    # >0 bytes = video is flowing
```

---

## Offline testing (no drone) — mocks
- `mock_apiserver.py <host> <port>` — fake ApiServer (`/status/`, `/c/ws/echo`). Point the latency tools at it.
- `video_tcp_mock.py [port=5600] [clip.h264] [secs]` — fake raw-H.264 TCP server. Make a clip FIRST
  (byte-stream is REQUIRED, else the decoder hangs):
  ```bash
  gst-launch-1.0 videotestsrc num-buffers=150 ! video/x-raw,width=640,height=360,framerate=30/1 \
    ! x264enc tune=zerolatency key-int-max=30 ! h264parse \
    ! 'video/x-h264,stream-format=byte-stream,alignment=au' ! filesink location=clip.h264
  ```

---

## Live video into ROS + rviz2 (the real receiver: C++ rx_node)
`rx_node` (GStreamer) connects to `5600`, decodes low-latency H.264, publishes `sensor_msgs/Image` on
topic **`camera/stream`**. It stays connected and waits for the keyframe (unlike OpenCV).

Build ONLY the receiver (skips the heavy SLAM/llama/ASR tree):
```bash
source /opt/ros/jazzy/setup.bash
bash build.sh release shared dji configure          # once: fetches deps + generates Ninja
cmake --build build/release/shared/dji --target llm_to_action_gstreamer_rx -j$(nproc)
```
Run + view:
```bash
GW=$(ip route show dev wlp2s0 | awk '/^default/{print $3}')
build/release/shared/dji/bin/llm_to_action_gstreamer_rx --dji "$GW"
# then, in another shell:
source /opt/ros/jazzy/setup.bash
ros2 run rqt_image_view rqt_image_view      # pick /camera/stream   (lighter than rviz2)
```
First frame takes up to ~10 s (the drone's keyframe interval). Latency ~150 ms = the DJI stream floor.
**Manual fallback (view without ROS):** needs `gstreamer1.0-plugins-base` for an X sink
(`xvimagesink`); only `kmssink` is installed here and the compositor blocks it — so use rqt/rviz2.

`build.sh` gotchas: actions are mutually exclusive — `configure` fetches+generates, `build` compiles
(target `all` = the whole heavy tree), `cleanbuild` ONLY wipes the dir. Use `configure` then `build`.

---

## Android app build/install (on the workstation) — `../../../../exoskeletons/tools/`
- `adk.sh` — build/install the phone app without Android Studio: `doctor`, `setup`, `build`, `install`,
  `status <IP>`, `video <IP>`. See its `help`.
- `adbfix.sh` — recreate the phone's USB node in the container after re-enumeration, then restart adb.
  Run when `adb devices` goes empty after a reconnect. (Phone↔RC and phone↔workstation share ONE USB-C
  port — you cannot do both at once.)

## True e2e video latency — `measure_video_e2e.py`
Flashes the screen, detects the flash arriving in `camera/stream`, prints latency = arrival − flash.
Needs `rx_node` running + the drone camera aimed at the FLASH window.
```bash
# term1: rx_node --dji $GW    ;    term2:
python3 tools/dji_mock/measure_video_e2e.py
```
Measured baseline: **p50 ≈ 320 ms** (DJI air-link floor). Tune THRESH/INTERVAL in the file if no detections.
