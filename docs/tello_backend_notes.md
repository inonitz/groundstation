# TelloBackend — SDK 2.0 verified notes (Phase 2)

Verified against the Ryze Tello SDK 2.0 User Guide (2018.11). Source of truth for the
`TelloBackend` (DroneBackend impl) that pairs with `PX4Backend`.

## Ports / init (prototype correct)
- Command+response: UDP `192.168.10.1:8889`. State: local `0.0.0.0:8890`. Video: `0.0.0.0:11111` (H.264).
- Init: send `command` (enter SDK) → `streamon`. Auto-land after **15 s** with no command → must stream `rc` continuously (keepalive).

## Commands we use
- `takeoff` / `land` / `stop` (hover, any time) / `emergency` (instant motor kill).
- `rc a b c d`: a=L/R, b=F/B, c=U/D, d=yaw, each **−100..100 = STICK PERCENT (not a velocity)**.
  → `go_vel` needs a velocity(m/s) → stick(%) calibration curve.
- `go x y z speed`: x,y,z −500..500 cm, speed 10..100 cm/s. **±20 cm deadzone** (no sub-20 cm move).
  Frame ~FLU (x fwd, y left, z up) — verify y-left sign empirically. Use for coarse hops only.
- `cw x` / `ccw x`: 1..360°. `up/down/forward/back/left/right x`: 20..500 cm (min 20 cm).

## State string (parser in prototype is EXACT — 16 fields, no mission pad)
`pitch;roll;yaw (deg); vgx;vgy;vgz; templ;temph; tof; h; bat; baro; time; agx;agy;agz`
- **vgx/vgy/vgz = cm/s** → m/s = `/100`. (Gemini's `/10` "dm/s" was WRONG, 10× error.)
- tof, h, baro = **cm**. agx/agy/agz = **g** (×9.81 for m/s²). yaw/pitch/roll = deg. time = s.
- Enabling Mission Pad (`mon`) prepends `mid;x;y;z;mpry` → breaks the 16-field parser. Keep `mon` off.

## Odometry (better than full dead-reckoning)
- **z = h/100 (measured), yaw = state.yaw (measured)** → no drift on those.
- **x,y = integrate body vgx/vgy** (rotate by yaw to world), Simpson over 3 samples (§8). Only x,y drift.
- Publish as `nav_msgs/Odometry` (cross-hw abstraction; Tello does NOT publish px4 VehicleOdometry).

## Prototype fixes needed
- Manual `bind(8890)` may collide with `ctello`'s own state socket → use `ctello::GetState()` OR
  add `SO_REUSEADDR` + check `bind()` return. `while(!ReceiveResponse());` needs a timeout.
- **Video: Tello = raw H.264, not RTP.** `rx_node`'s pipeline (`rtph264depay`) is gazebo-RTP only.
  Tello needs `udpsrc port=11111 ! h264parse ! avdec_h264 ! videoconvert ! appsink` → the camera
  RX must be platform-aware.
- `KeyboardNode` sends `rc` only on keypress → 15 s auto-land. FMU's ~30 Hz stream fixes this.

## Phase-2 frame decision
FMU should keep ONE canonical world frame (FLU/ENU, matching the VLM). Backends convert:
PX4Backend FLU→NED; TelloBackend ≈ identity for `go`, + velocity→stick for `rc`. (Phase-1 code
currently does FLU→NED inline because it's PX4-only — move that into PX4Backend.)
