# A2 live dashboard

A lean browser dashboard for the off-board VLM autonomy stack. It shows the annotated camera, the depth
colormap, the flight HUD, and the VLM reasoning log, live. It is a demo view and a debug tool.

It must not hurt system performance. The transport stays lean by design. The FMU downscales the two
image streams to 320x240 and caps them near 10 fps. This bridge only re-encodes what arrives. It never
requests full frames. This is the fix for the earlier regression where full 1280x720 publishing starved
the VLM and pushed RSS over budget.

## Parts

- `serve.py` — the bridge. One `rclpy` node plus one stdlib `ThreadingHTTPServer`. It subscribes the ROS
  topics and serves them to the browser.
- `dashboard.html` — the page. Two MJPEG image panels and one SSE stream. No build step, no framework.

## Dependencies

Only the ROS runtime already on a sourced workspace: `rclpy`, `cv_bridge`, `cv2`. Everything else is the
Python standard library. There are no pip installs. Websockets, rosbridge, and foxglove are not used and
must not be added.

## Topics

| Topic | Type | Panel |
|-------|------|-------|
| `/fmu/perception/annotated` | `sensor_msgs/Image` | camera (boxes are baked in) |
| `/fmu/perception/depth` | `sensor_msgs/Image` | depth colormap |
| `/fmu/hud` | `std_msgs/String` | HUD tiles + detection list |
| `/fmu/vlm_text` | `std_msgs/String` | VLM reasoning log |
| `/fmu/vlm_context` | `std_msgs/String` (JSON) | objective + executed-command history (with status) |

All four are published only when the FMU runs with `FMU_OBSERVABILITY=1`. With the gate off, the FMU
publishes nothing and this dashboard sees no data.

## Run

Source the workspace, start a SITL run with observability on, then start the bridge:

```bash
FMU_OBSERVABILITY=1   # set for the SITL/FMU run
python3 scripts/dashboard/serve.py                      # default port 8088
python3 scripts/dashboard/serve.py 9000                 # or pick a port
python3 scripts/dashboard/serve.py 8088 --log dash.log  # also write a log file
python3 scripts/dashboard/serve.py 8088 --log dash.log --verbose   # + per-request DEBUG
python3 scripts/dashboard/serve.py 8088 --workers 6                # HTTP worker-pool size
```

Open `http://localhost:8088`. The camera and depth panels stream over MJPEG. The HUD and VLM log update
over SSE. The page reconnects on its own if the bridge restarts.

## Logs

The bridge logs to stderr, and to a file when `--log <path>` (or `DASH_LOG=<path>`) is given. Each
subscription logs its first message and a rate summary every 5 s, so the log shows whether frames are
arriving from the FMU and how fast. Every HTTP request is logged, and each stream logs open/close with
the frame or event count. `--verbose` (or `DASH_VERBOSE=1`) adds per-request DEBUG detail. A blank page
with no `first message on 'annotated'` line means the FMU is not publishing -- check `FMU_OBSERVABILITY`.

## Resource use

The bridge is built to stay light, especially while nobody is watching it during a SITL run:
- **ROS callbacks** run on a single-threaded spin. A/B testing showed rclpy's `MultiThreadedExecutor`
  roughly doubled watched CPU for this light workload (two 10 Hz encodes), so single-threaded is leaner.
- **HTTP** is served from a **bounded daemon-thread pool** (`--workers`, default 6), not a thread per
  connection. Long-lived MJPEG/SSE streams each hold one worker, so keep it `>= 3` per open tab.
- **Image topics are subscribed on demand.** The heavy `/fmu/perception/*` topics (230 KB/frame at
  10 Hz each) are subscribed only while a browser is actively streaming them, and dropped when the last
  viewer leaves. With no one watching, the bridge receives and encodes nothing -- it is near-idle. The
  cheap text topics stay subscribed so the HUD/VLM panes are ready the moment a tab opens.

## Endpoints

- `/` — the page.
- `/stream/annotated`, `/stream/depth` — `multipart/x-mixed-replace` MJPEG, one per image.
- `/events` — Server-Sent Events carrying the latest HUD line and VLM text as JSON.

## Notes

- Image subscriptions use queue depth 1. A slow encoder drops stale frames instead of backing up.
- The MJPEG loop sleeps 0.1s, so each stream is capped near 10 fps.
- The SSE stream blocks until the HUD or VLM text actually changes, with a 15s keep-alive tick. It does
  not busy-poll.
- VLM text is written into the log with `textContent`, so model output cannot inject HTML.
