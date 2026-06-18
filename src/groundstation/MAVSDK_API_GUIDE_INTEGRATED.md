# MAVSDK C++ API — Integrated Guide & Examples Reference

> **Sources:**
> - Official MAVSDK C++ Guide: https://mavsdk.mavlink.io/main/en/cpp/guide
> - 58 C++ example files: `dependencies/MAVSDK/examples/`
>
> This document cross-references the official guide with real-world example code to provide a complete picture of the API.

---

## 1. Architecture & Usage Paradigms

### Official Guide Insights

| Concept | Detail |
|---------|--------|
| **`Mavsdk` is the root singleton** | One instance per application, kept alive for the entire lifetime of any connected systems. Typically a stack variable, but `new`/`delete` is also supported. |
| **Plugin architecture** | All drone access is through plugins. Each plugin is instantiated per system: `auto action = Action{system};`. Plugins are `shared_ptr`-managed and cleaned up when `Mavsdk` is destroyed. |
| **No exceptions** | MAVSDK C++ API **never throws exceptions**. Every method that can fail returns a `Result` enum (e.g., `Result::Success`, `Result::ErrorNext`). Stream operators (`<<`) are provided for human-readable output. |
| **Callbacks** | Async operations and subscriptions use callbacks. All callbacks fire on a **single shared thread**. **Never do blocking/IO work inside a callback** — it will stall all subsequent callbacks. |
| **Compatibility modes** | `Mavsdk::Configuration` supports `Auto` (default — auto-detects PX4 vs ArduPilot), `Pure` (standard MAVLink only), `Px4`, and `ArduPilot`. Set via `config.set_compatibility_mode()`. |
| **Connection timeout** | A system is considered disconnected if no heartbeat is received within **3 seconds**. |

### Example Code Correlation

The examples consistently follow the guide's paradigm:

```cpp
// From takeoff_and_land.cpp — canonical usage pattern
int main(int argc, char** argv) {
    Mavsdk mavsdk;
    auto system = mavsdk.first_autopilot();  // Wait for first system
    Action action{system};                   // Instantiate plugin
    Telemetry telemetry{system};             // Another plugin for same system
    
    // ... use action and telemetry ...
}
```

### Key Takeaway

The guide's paradigm section is **authoritative** and **matches the examples exactly**. No discrepancies found.

---

## 2. Connecting to Systems

### Official Guide Insights

| Transport | Inbound (server) | Outbound (client) |
|-----------|------------------|-------------------|
| UDP | `udpin://0.0.0.0:14540` | `udpout://192.168.1.12:14550` |
| TCP | `tcpin://0.0.0.0:14550` | `tcpout://192.168.1.12:14550` |
| Serial | `serial:///dev/serial/by-id/...:57600` | Same format |

**Important notes from the guide:**
- `add_any_connection()` returns `ConnectionResult` immediately (synchronous)
- Standard PX4 port: `udpin://0.0.0.0:14540` is the standard PX4 offboard API port (SITL). Ground stations listen on port 14550.
- **Bidirectional forwarding**: Multiple connections can forward MAVLink messages using `ForwardingOption::ForwardingOn/Off`. Default is `ForwardingOff`.
- For one-directional forwarding, set `ForwardingOn` only on the **destination** connection. For bidirectional, set it on **both**.

### Example Code Correlation

| Example | Connection Pattern |
|---------|-------------------|
| `takeoff_and_land` | `Mavsdk mavsdk; mavsdk.add_any_connection("udpin://0.0.0.0:14540");` |
| `multiple_drones` | Multiple `add_any_connection()` calls for different ports |
| `mavlink_forwarding` | `add_any_connection(url, ForwardingOption::ForwardingOn)` |
| `reconnect` | `subscribe_connection_errors()` + `add_any_connection_with_handle()` |
| `disconnect` | Destruct/reconstruct `Mavsdk` on disconnect |

### Cross-Reference

The guide's connection string formats **match the examples exactly**. The guide adds the important detail about **forwarding options** which is demonstrated in `mavlink_forwarding.cpp` but not explicitly explained in the examples themselves.

---

## 3. Action Plugin — High-Level Flight Commands

### Official Guide Insights

| Method | Description |
|--------|-------------|
| `arm()` | Arms the motors. Returns `Action::Result::Success` if armed. |
| `disarm()` | Disarms the motors. |
| `takeoff()` | Sets vehicle to Takeoff mode; hovers at takeoff altitude. |
| `land()` | Switches to Land mode; auto-disarms after landing. |
| `return_to_launch()` | RTL |
| `hold()` / `hold_to_altitude_m()` | Loiter at current or specified altitude |
| `goto_location(lat, lon, alt_m)` | Fly to a specific GPS coordinate |
| `set_current_speed(kmh)` | Set cruise speed (used with `goto_location`) |
| `transition_to_fixedwing()` / `transition_to_multicopter()` | VTOL mode transitions |
| `reboot()` | Safely reboot autopilot |
| `terminate()` | Emergency motor stop + parachute deploy |
| `set_relay(index, On/Off)` | Toggle hardware relay |
| `set_actuator(index, value)` | Set servo position (0–1) |
| `get_takeoff_altitude()` / `set_takeoff_altitude(float)` | Get/set takeoff altitude |
| `get_maximum_speed()` / `set_maximum_speed(float)` | Get/set maximum cruise speed |

### Critical Warning from the Guide

> **"Action methods are fire-and-forget":** `Action::land()` returns as soon as the vehicle acknowledges the command, not when the action completes. You must separately monitor completion (e.g., via `subscribe_flight_mode()`).

> **Vehicle must be "healthy"** (calibrated, GPS lock, home position set) before arming. After takeoff, monitor altitude (`telemetry.position().relative_altitude_m`) to detect completion. After landing, poll `telemetry.armed()` to detect disarm completion.

### Example Code Correlation

| Example | How It Handles Completion |
|---------|--------------------------|
| `takeoff_and_land` | Uses `telemetry.health_all_ok()` before arming, `telemetry.in_air()` to detect takeoff completion, `telemetry.armed()` to detect landing |
| `vtol_transition` | Monitors `telemetry.position().relative_altitude_m` and `telemetry.armed()` during VTOL flight |
| `hold` | Uses `telemetry.subscribe_flight_mode()` to detect mode changes during RTL/Hold |
| `goto_location` | Monitors `telemetry.in_air()` and altitude |

### Cross-Reference

The guide's warning about **fire-and-forget** behavior is **crucial** and is correctly handled in the examples. The examples demonstrate the **required pattern**: always pair Action commands with Telemetry state monitoring.

---

## 4. Telemetry Plugin — Vehicle State

### Official Guide Insights

| Method | Description |
|--------|-------------|
| `subscribe_position(cb)` | `(lat, lon, rel_alt, abs_alt)` |
| `subscribe_battery(cb)` | `(voltage, current, temp, remaining%)` |
| `subscribe_armed(cb)` | Armed/disarmed state |
| `subscribe_in_air(cb)` | In-air state |
| `subscribe_landed_state(cb)` | `OnGround` / `Airborne` |
| `subscribe_health_all_ok(cb)` | Full health status |
| `subscribe_distance_sensor(cb)` | Distance in meters + orientation |
| `subscribe_wind(cb)` | NED wind velocity + variability |
| `subscribe_gps_global_origin(cb)` | GPS reference point |
| `subscribe_gimbal_list(cb)` | Available gimbal components |
| `get_gps_global_origin()` | One-shot GPS origin query |
| `set_rate_position(float)` | Set update rate for position (Hz) |
| `set_rate_battery(float)` | Set update rate for battery (Hz) |

**Important notes from the guide:**
- Update rates can be set per-telemetry-type using `set_rate_*()` methods (e.g., `set_rate_position(1.0)` for 1 Hz)
- **Asynchronous callbacks are the recommended way** to get regular, non-blocking updates
- For state-dependent sequencing, synchronous polling or `subscribe_*` with a `std::promise`/`std::future` blocking pattern is recommended
- `prom->set_value()` must only be called once; unsubscribe after use to avoid double-firing
- Default update rates depend on the autopilot (PX4 defaults set in `mavlink_main.cpp`)
- For "change only" semantics, implement a local `oldValue` comparison in the callback

### Data Types Defined by Telemetry

`Position`, `VelocityNED`, `VelocityBody`, `Altitude`, `Battery`, `Health`, `HomePosition`, `GpsInfo`, `EulerAngle`, `Quaternion`, `Covariance`, `DistanceSensor`, `FixedwingMetrics`, `Odometry`, `StatusText`, `RcStatus`

### Example Code Correlation

| Example | Telemetry Pattern |
|---------|------------------|
| `takeoff_and_land` | `telemetry.health_all_ok()`, `telemetry.in_air()`, `telemetry.armed()` |
| `battery/subscribe_battery` | `telemetry.subscribe_battery(cb)` |
| `wind` | `telemetry.subscribe_wind(cb)` |
| `distance_sensor` | `telemetry.subscribe_distance_sensor(cb)` |
| `vtol_transition` | `telemetry.set_rate_position(1.0)`, `telemetry.subscribe_position(cb)` |
| `multiple_drones` | `telemetry.set_rate_position(1.0)`, `telemetry.subscribe_position(cb)` |
| `callback_executor` | `telemetry.set_callback_executor()` for custom threading |

### Cross-Reference

The guide's information on **update rates** and **callback patterns** is **not fully covered in the examples**. The examples show basic subscriptions but don't demonstrate `set_rate_*()` or the `std::promise`/`std::future` blocking pattern. The guide adds significant value here.

---

## 5. MissionRaw Plugin — QGroundControl Plan Import

### Official Guide Insights

| Method | Description |
|--------|-------------|
| `import_qgroundcontrol_mission(path)` | Parse `.plan` → `MissionImportData` |
| `upload_mission(items)` | Upload parsed mission items |
| `start_mission()` | Begin execution |
| `pause_mission()` / `resume_mission()` | Pause/resume mid-flight |
| `clear_mission()` | Remove all mission items |
| `subscribe_mission_progress(cb)` | `(current_item, total_items)` callback |
| `is_mission_finished()` | Sync check for mission completion |
| `download_mission()` | Returns `std::pair<Result, Mission::MissionPlan>` |
| `make_mission_item()` | Helper function to create mission items |

**MissionItem fields:** `latitude_deg`, `longitude_deg`, `relative_altitude_m`, `speed_m_s`, `is_fly_through`, `gimbal_pitch_deg`, `gimbal_yaw_deg`, `camera_action`, `loiter_time_s`, `camera_photo_interval_s`

**Supported Mission Commands:**
- `MAV_CMD_NAV_WAYPOINT`, `MAV_CMD_DO_CHANGE_SPEED`, `MAV_CMD_DO_MOUNT_CONTROL`, `MAV_CMD_IMAGE_START/STOP_CAPTURE`, `MAV_CMD_VIDEO_START/STOP_CAPTURE`, `MAV_CMD_NAV_LOITER_TIME`
- Import-only: `MAV_CMD_NAV_LAND`, `MAV_CMD_NAV_TAKEOFF`

**Important notes from the guide:**
- The standard `Mission` plugin is a **simplified subset**. For full MAVLink mission commands, use `MissionRaw`.
- Default attribute values are `NaN` (ignored/not sent); setting a value persists for the remainder of the mission.
- Missions with unsupported commands will fail to download.
- Takeoff/land/RTL are handled by the `Action` API, **not** mission items.

### Example Code Correlation

| Example | Mission Pattern |
|---------|----------------|
| `fly_mission` | Full waypoint mission with 6 items including camera actions, gimbal angles, pause/resume |
| `fly_qgc_mission` | `import_qgroundcontrol_mission(path)` → `upload_mission()` → `start_mission()` |
| `fly_multiple_drones` | Multi-drone QGC mission import |
| `autopilot_server` | `mission.upload_mission_async()`, `mission.clear_mission_async()`, `mission.subscribe_mission_progress()` |

### Cross-Reference

The guide's distinction between **Mission** (simplified) and **MissionRaw** (full MAVLink) is **critical** and is demonstrated in the examples but not explicitly explained. The guide adds the important note that **takeoff/land/RTL are handled by Action, not mission items**.

---

## 6. Camera Plugin — Camera Control

### Official Guide Insights

The official guide does not have a dedicated Camera page, but the API is well-documented in the examples and the API Reference.

| Method | Description |
|--------|-------------|
| `camera_list()` | Discover available camera components |
| `set_mode(Photo/Video)` | Switch capture mode |
| `take_photo()` | Capture a single photo |
| `start_video()` / `stop_video()` | Record video |
| `start_video_streaming()` / `stop_video_streaming()` | Start/stop video stream |
| `zoom_in_start()` / `zoom_out_start()` / `zoom_stop()` | Continuous zoom |
| `zoom_range()` / `zoom_set(value)` | Get/set zoom level |
| `set_setting(option, value)` | Configure camera settings |
| `get_possible_setting_options()` | List available settings |
| `format_storage()` / `reset_settings()` | Storage and config management |
| `subscribe_capture_info(cb)` | Photo capture notifications (file URL) |
| `subscribe_storage(cb)` | Storage status (free/used space) |
| `subscribe_camera_list(cb)` | Camera connection events |
| `subscribe_current_settings(cb)` | Live camera settings |

### Server-Side (CameraServer)

| Method | Description |
|--------|-------------|
| `set_information()` | Define camera capabilities |
| `respond_take_photo()` | Respond to photo requests |
| `respond_start_video()` / `respond_stop_video()` | Respond to video requests |
| `respond_set_mode()` | Respond to mode changes |
| `respond_storage_information()` | Respond to storage queries |
| `respond_capture_status()` | Respond to capture status |
| `respond_format_storage()` | Respond to format requests |
| `respond_reset_settings()` | Respond to reset requests |

### Example Code Correlation

| Example | Camera Pattern |
|---------|---------------|
| `camera` | Discover camera, switch to photo mode, subscribe to capture info, take photo |
| `camera_zoom` | Zoom in/out with step and continuous zoom controls |
| `camera_settings` | Interactive CLI for changing camera mode and settings |
| `camera_server` | Server-side camera implementation with all respond handlers |
| `camera_client` | Client-side camera operations (photo, video, streaming, storage) |

### Cross-Reference

The examples **fully cover** the Camera API. The guide doesn't add much beyond what the examples show, but the examples are comprehensive and well-structured.

---

## 7. Gimbal Plugin — Gimbal Control

### Official Guide Insights

The guide doesn't have a dedicated Gimbal page, but the API is well-documented in the examples.

| Method | Description |
|--------|-------------|
| `take_control()` / `release_control()` | Exclusive gimbal control |
| `set_angles(pitch, yaw, mode, send_mode)` | Set absolute angles |
| `set_angular_rates(pitch, yaw, send_mode)` | Set angular velocities |
| `set_roi_location(lat, lon, alt)` | Region of Interest targeting |
| `get_attitude()` | One-shot attitude query |
| `subscribe_attitude(cb)` | Gimbal attitude subscription |
| `subscribe_gimbal_list(cb)` | Gimbal component discovery |

**Yaw modes:** `YawLock` (absolute), `YawFollow` (follow vehicle heading)
**Send modes:** `Once` (single), `OnChangeOfYaw` (rate-limited)

### Example Code Correlation

| Example | Gimbal Pattern |
|---------|---------------|
| `gimbal` | Full gimbal control: take/release control, set angles, angular rates, ROI |
| `gimbal_device_tester` | Comprehensive gimbal device tester using MavlinkPassthrough |

### Cross-Reference

The examples **fully cover** the Gimbal API. The guide doesn't add much beyond what the examples show.

---

## 8. Offboard Plugin — Low-Level Flight Control

### Official Guide Insights

| Method | Description |
|--------|-------------|
| `start()` | Enter offboard mode |
| `stop()` | Exit offboard mode |
| `set_velocity_ned(VelocityNEDYaw)` | NED frame (absolute North/East/Down) |
| `set_velocity_body(VelocityBodyYawspeed)` | Body frame (forward/right/down) |

**Coordinate Frame Differences:**
- **NED frame:** First 3 values = North, East, Down velocity (m/s); 4th value = yaw (degrees clockwise from North)
- **Body frame:** First 3 values = forward, right, down velocity (m/s); 4th value = yaw rate (deg/s, positive=clockwise)

**Important notes from the guide:**
- Only works with **copter and VTOL** vehicles (PX4 limitation — no fixed wing)
- SDK auto-resends setpoints at 20 Hz (PX4 requires minimum 2 Hz)
- **Must set a setpoint before calling `start()`**
- Setpoints are cleared on last call; vehicle obeys the most recent setpoint
- If vehicle leaves offboard mode externally, SDK stops sending setpoints — `is_active()` becomes false
- No position or thrust setpoint support (at time of writing)

### Example Code Correlation

| Example | Offboard Pattern |
|---------|----------------|
| `offboard` | NED velocity, global position, body velocity, attitude modes |
| `set_gps_origin` | Offboard velocity control + GPS origin re-baselining |

### Cross-Reference

The guide's information on **NED vs Body frame** differences and the **20 Hz auto-resend** behavior is **not covered in the examples**. The guide adds significant value here. The critical note about **must set a setpoint before calling `start()`** is also not explicitly stated in the examples.

---

## 9. FollowMe Plugin — Autonomous Following

### Official Guide Insights

| Method | Description |
|--------|-------------|
| `set_config(Config)` | Configure follow behavior |
| `start()` / `stop()` | Start/stop following |
| `set_target_location(lat, lon, alt, relative_alt, speed, heading)` | Set target position |
| `get_last_location()` | Get last known target location |

**Config struct:** `min_height_m`, `follow_distance_m`, `responsiveness`, `follow_direction` (FRONT/LEFT/RIGHT/BEHIND/CENTRE)

**Default Configuration:** Height: 8 m, Distance: 8 m, Behind target.

**Important notes from the guide:**
- ⚠️ **QGroundControl conflict:** Running QGC simultaneously causes unpredictable behavior. Must disable "Stream GCS Position" (Application Settings > General > Miscellaneous > Stream GCS Position = Never)
- If `start()` called without a target location, vehicle climbs to minimum altitude and waits
- If connection breaks, vehicle stays in mode waiting for messages

### Example Code Correlation

| Example | FollowMe Pattern |
|---------|----------------|
| `follow_me` | Full workflow: arm, takeoff, configure follow height/angle, start FollowMe, feed simulated location updates, stop, land |
| `fake_location_provider` | Mock location provider generating a square path |

### Cross-Reference

The guide's **QGroundControl conflict warning** is **not mentioned in the examples**. This is a critical piece of information that the guide provides but the examples omit.

---

## 10. VTOL Support

### Official Guide Insights

| Feature | Status |
|---------|--------|
| Take off and land in multicopter mode | ✅ Supported |
| Fly in multicopter mode and transition to fixed wing | ✅ Supported |
| Camera/gimbal and other generic features | ✅ Supported |
| VTOL transitions via `Action` API | ✅ Supported |
| VTOL waypoint missions | ⚠️ Requires `MissionRaw` plugin (not standard `Mission`) |
| VTOL takeoff in fixed wing mode | ❌ Not supported |

**Important notes from the guide:**
- MAVSDK has **basic** VTOL support. Most design/test effort went into multicopter.
- VTOL waypoint missions require the `MissionRaw` plugin (not the standard `Mission` plugin).
- Can't include VTOL transitions in the mission itself — must use `Action` transitions.

### Example Code Correlation

| Example | VTOL Pattern |
|---------|-------------|
| `vtol_transition` | VTOL takeoff → fixedwing transition → loiter → transition back → land |

### Cross-Reference

The guide's distinction between **Mission** and **MissionRaw** for VTOL missions is **critical** and is demonstrated in the examples but not explicitly explained. The guide adds the important note about **VTOL takeoff in fixed wing mode not being supported**.

---

## 11. MavlinkDirect Plugin — Raw MAVLink Messages

### Official Guide Insights

| Method | Description |
|--------|-------------|
| `load_custom_xml(std::string xml)` | Load custom XML dialect for non-standard messages |
| `send_message(MavlinkMessage)` | Send a single message |
| `subscribe_message(message_name, callback)` | Subscribe to specific or all (empty string) messages |
| `unsubscribe_message(handle)` | Unsubscribe using handle returned from `subscribe_message()` |

**MavlinkMessage Structure:**
```cpp
MavlinkDirect::MavlinkMessage {
    std::string message_name;  // e.g., "OBSTACLE_DISTANCE"
    uint8_t system_id;
    uint8_t component_id;
    uint8_t target_system_id;
    uint8_t target_component_id;
    std::string fields_json;   // JSON object with field names/values
}
```

**Important notes from the guide:**
- It is the **recommended replacement** for `MavlinkPassthrough` (which will become compile-time-only in MAVSDK v4)
- ⚠️ **API is not yet stabilized** — specifics/types may change before MAVSDK v4
- Runtime approach means no auto-complete; users must look up MAVLink message definitions manually
- Enum values/flags must be assembled manually
- Performance may be slower than compile-time, but negligible unless at very high rates
- Environment variable `MAVSDK_MAVLINK_DIRECT_DEBUGGING=1` for debug output

### Example Code Correlation

| Example | MavlinkDirect Pattern |
|---------|----------------------|
| `subscribe_gps` | `subscribe_message("GPS_RAW_INT", callback)` |
| `mavlink_stats` | `subscribe_message("", callback)` to subscribe to ALL messages |
| `sender` | `send_message()` for OBSTACLE_DISTANCE |
| `sender_custom` | `load_custom_xml()` for AIRSPEED message |

### Cross-Reference

The guide's information about **MavlinkDirect being the recommended replacement for MavlinkPassthrough** and the **API not yet stabilized** is **not mentioned in the examples**. This is critical forward-looking information that the guide provides.

---

## 12. System Information Plugin

### Official Guide Insights

| Method | Description |
|--------|-------------|
| `hardware_uid()` | Returns `char[18]` hardware unique ID (replaced old `uint64_t` UUID) |
| `get_version()` | Returns `pair<Result, Info::Version>` — version info |
| `get_product()` | Returns `pair<Result, Info::Product>` — product info |
| `get_identification()` | Returns `pair<Result, Info::Identification>` |
| `is_complete()` | Check if version/product data is fully received |

**Info::Version struct:** Contains `flight_sw_*`, `os_sw_*`, `flight_sw_git_hash`, etc.
**Info::Product struct:** Contains `vendor_id`, `vendor_name`, `product_id`, `product_name`

**Result States for Info Queries:**
- `INFORMATION_NOT_RECEIVED_YET` — data hasn't arrived yet; poll/wait
- Other `Result` values indicate success or specific errors

**Important notes from the guide:**
- Data is cached: Since this information doesn't change, it's accurate whenever read (once populated)
- Asynchronous population: Version/product data arrives from the vehicle over time. You must poll or wait until data is received before reading.
- ⚠️ **Garbage values possible:** Not all vehicles report all version fields. Simulators, for example, return garbage for vendor firmware semantic version.
- **hardware_uid replaced UUID:** The old `uint64_t` UUID was replaced by `char[18] hardware_uid` (inherited from MAVLink to prevent ID conflicts)

### Example Code Correlation

| Example | System Info Pattern |
|---------|-------------------|
| `system_info` | `info.get_version()`, `info.get_product()`, `info.get_identification()` |

### Cross-Reference

The guide's information about **garbage values in simulators** and the **hardware_uid replacing UUID** is **not mentioned in the examples**. The guide adds significant value here.

---

## 13. MavlinkPassthrough Plugin — MAVLink Packet Manipulation

### Official Guide Insights

The guide indicates that `MavlinkPassthrough` will become **compile-time-only** in MAVSDK v4, with `MavlinkDirect` being the recommended replacement for runtime message handling.

| Method | Description |
|--------|-------------|
| `queue_message(packet)` | Queue a raw MAVLink packet |
| `subscribe_message(msg_id, cb)` | Subscribe by numeric MAVLink ID |
| `send_command_long(cmd, param1..7)` | Send MAV_CMD_* commands |

### Example Code Correlation

| Example | MavlinkPassthrough Pattern |
|---------|--------------------------|
| `parachute` | `subscribe_message(MAVLINK_MSG_ID_COMMAND_LONG, callback)` |
| `publish_battery` | `queue_message(mavlink_msg_battery_status_pack_chan(...))` |
| `gimbal_device_tester` | `queue_message()`, `subscribe_message()`, `send_command_long()` for gimbal protocol testing |

### Cross-Reference

The guide's information about **MavlinkPassthrough becoming compile-time-only in v4** is **not mentioned in the examples**. This is important migration information.

---

## 14. Server-Side Plugins (Simulating Vehicle Components)

### Official Guide Insights

These plugins let the ground station act as a vehicle component:

| Plugin | Methods |
|--------|---------|
| **ActionServer** | `set_allow_takeoff()`, `set_allow_arm()` |
| **MissionRawServer** | `subscribe_incoming_mission()`, `set_current_item()` |
| **ParamServer** | `provide_param_float()`, `provide_param_int()` |
| **TelemetryServer** | `publish_position()`, `publish_health_all_ok()` |
| **CameraServer** | `set_information()`, `respond_*()` handlers |
| **ArmAuthorizerServer** | `subscribe_arm_authorization()`, `accept/reject_arm_authorization()` |

### Example Code Correlation

| Example | Server Pattern |
|---------|---------------|
| `autopilot_server` | Two-thread example: main thread acts as GCS client, background thread runs server plugins simulating an autopilot |
| `camera_server` | Server-side camera implementation with all respond handlers |
| `arm_authorizer_server` | Authorization server for arming — accepts or rejects arm requests |

### Cross-Reference

The guide's documentation of server plugins is **complementary** to the examples. The examples demonstrate usage but the guide provides the complete API surface.

---

## 15. Additional Plugins (Not Covered in Guide)

The following plugins are **well-covered in examples** but have **minimal guide documentation**:

| Plugin | Examples | Key Methods |
|--------|----------|-------------|
| **LogStreaming** | `log_streaming`, `log_callback` | `subscribe_log_streaming_raw()`, `start_log_streaming()`, `stop_log_streaming()` |
| **LogFiles** | `logfile_download` | `get_entries()`, `download_log_file_async()`, `erase_all_log_files()` |
| **Ftp** | `ftp_client` | `upload_async()`, `download_async()`, `remove_file_async()`, `rename_async()`, `create_directory_async()`, `remove_directory_async()`, `list_directory_async()`, `are_files_identical_async()` |
| **FtpServer** | `ftp_server` | `set_root_dir()` |
| **Param** | `params`, `autopilot_server`, `log_streaming` | `get_all_params()`, `get_param_float()`, `get_param_int()`, `set_param_float()`, `set_param_int()` |
| **ComponentMetadata** | `component_metadata` | `request_autopilot_component()`, `subscribe_metadata_available()` |
| **Events** | `events` | `subscribe_events()`, `subscribe_health_and_arming_checks()` |
| **Transponder** | `transponder` | `set_rate_transponder()`, `subscribe_transponder()` |
| **Wind** | `wind` | `subscribe_wind()` |
| **Tune** | `tune` | `play_tune()` |
| **Winch** | `winch` | `lock()` |
| **Calibration** | `calibrate` | `calibrate_accelerometer_async()`, `calibrate_gyro_async()`, `calibrate_magnetometer_async()` |
| **Shell** | `mavshell` | `send()`, `subscribe_receive()` |
| **Geofence** | `geofence` | `upload_geofence()` |
| **ManualControl** | `manual_control`, `joystick` | `start_position_control()`, `set_manual_control_input()` |

---

## 16. Cross-Reference Summary

### Where Guide Adds Value Beyond Examples

| Topic | Guide Contribution |
|-------|-------------------|
| **Usage Paradigms** | Explains no-exceptions policy, callback threading model, compatibility modes |
| **Connection Forwarding** | Explains `ForwardingOption` in detail |
| **Action Completion** | Critical warning about fire-and-forget behavior |
| **Telemetry Update Rates** | `set_rate_*()` methods and callback patterns |
| **Mission vs MissionRaw** | Clear distinction between simplified and full MAVLink mission support |
| **Offboard Coordinate Frames** | NED vs Body frame differences, 20 Hz auto-resend |
| **QGroundControl Conflict** | Critical warning about FollowMe + QGC conflict |
| **VTOL Limitations** | VTOL takeoff in fixed wing mode not supported |
| **MavlinkDirect vs MavlinkPassthrough** | MavlinkDirect is the future; Passthrough becomes compile-time-only in v4 |
| **System Info Garbage Values** | Simulators return garbage for vendor firmware |
| **hardware_uid Replacement** | Old UUID replaced by `char[18] hardware_uid` |

### Where Examples Add Value Beyond Guide

| Topic | Examples Contribution |
|-------|---------------------|
| **Real-world error handling** | Shows how to handle `Result` failures in practice |
| **Multi-drone patterns** | `multiple_drones`, `fly_multiple_drones` show parallel drone control |
| **Server-side implementation** | `autopilot_server`, `camera_server` show complete server implementations |
| **Interactive CLI patterns** | `params`, `camera_settings` show full CLI implementations |
| **Custom MAVLink messages** | `sender_custom` shows custom XML loading |
| **Gimbal protocol testing** | `gimbal_device_tester` shows comprehensive protocol testing |
| **Connection retry logic** | `reconnect` shows auto-reconnect management |
| **Log streaming with stats** | `log_streaming` shows throughput monitoring |
| **FTP with progress callbacks** | `ftp_client` shows progress tracking |
| **Battery simulation** | `publish_battery` shows smart battery component simulation |

---

## 17. Design Patterns Summary

### Canonical Usage Flow

```cpp
// 1. Create Mavsdk instance
Mavsdk mavsdk;

// 2. Add connection(s)
mavsdk.add_any_connection("udpin://0.0.0.0:14540");

// 3. Wait for system discovery
auto system = mavsdk.first_autopilot();

// 4. Instantiate plugins for the system
Action action{system};
Telemetry telemetry{system};
Mission mission{system};

// 5. Use plugins (sync or async)
auto result = action.arm();
if (result == Action::Result::Success) {
    // Monitor completion via telemetry
    telemetry.subscribe_armed([](Telemetry::Result result) {
        // Handle armed state
    });
}
```

### Key Patterns

1. **Plugin per subsystem:** Each capability is a separate plugin class instantiated from a `System`
2. **Subscription model:** Telemetry, events, and state use `subscribe_*()` callbacks rather than polling
3. **Component-based:** `System` can have multiple components (autopilot, camera, gimbal, battery)
4. **Connection abstraction:** UDP, TCP, serial, and Unix sockets all use the same `add_*_connection()` API
5. **Error handling:** `Result` objects with `success()` / `error_string()` for every operation
6. **Sync/async duality:** Every major method has both a synchronous and `*_async` variant
7. **Blocking pattern:** `std::promise`/`std::future` used with subscriptions for synchronous-waiting-on-async patterns

---

## 18. Known Limitations & Caveats

### From the Guide

- **Supported vehicles:** Designed primarily for PX4 multicopters. Fixed-wing/VTOL have basic support. Ground vehicles are untested. ArduPilot compatibility is added incrementally.
- **Offboard limitation:** Only works with copter and VTOL vehicles (PX4 limitation — no fixed wing)
- **VTOL limitations:** VTOL takeoff in fixed wing mode not supported; VTOL transitions must use Action API, not mission items
- **MavlinkDirect API:** Not yet stabilized; specifics/types may change before MAVSDK v4

### From the Examples

- **Gimbal device tester:** May fail against PX4 SITL with `payload_deliverer` if targeting the wrong component ID
- **Calibration:** Best tested on real hardware (Pixhawk), not simulation
- **FollowMe + QGC:** Running QGroundControl simultaneously causes unpredictable behavior

---

## 19. Quick Reference — Plugin Header Includes

```cpp
#include <mavsdk/plugins/action/action.h>
#include <mavsdk/plugins/telemetry/telemetry.h>
#include <mavsdk/plugins/mission/mission.h>
#include <mavsdk/plugins/mission_raw/mission_raw.h>
#include <mavsdk/plugins/camera/camera.h>
#include <mavsdk/plugins/camera_server/camera_server.h>
#include <mavsdk/plugins/gimbal/gimbal.h>
#include <mavsdk/plugins/offboard/offboard.h>
#include <mavsdk/plugins/manual_control/manual_control.h>
#include <mavsdk/plugins/geofence/geofence.h>
#include <mavsdk/plugins/mavlink_direct/mavlink_direct.h>
#include <mavsdk/plugins/mavlink_passthrough/mavlink_passthrough.h>
#include <mavsdk/plugins/mavlink_forwarding/mavlink_forwarding.h>
#include <mavsdk/plugins/log_streaming/log_streaming.h>
#include <mavsdk/plugins/log_files/log_files.h>
#include <mavsdk/plugins/ftp/ftp.h>
#include <mavsdk/plugins/ftp_server/ftp_server.h>
#include <mavsdk/plugins/param/param.h>
#include <mavsdk/plugins/param_server/param_server.h>
#include <mavsdk/plugins/component_metadata/component_metadata.h>
#include <mavsdk/plugins/events/events.h>
#include <mavsdk/plugins/transponder/transponder.h>
#include <mavsdk/plugins/wind/wind.h>
#include <mavsdk/plugins/tune/tune.h>
#include <mavsdk/plugins/winch/winch.h>
#include <mavsdk/plugins/calibration/calibration.h>
#include <mavsdk/plugins/shell/shell.h>
#include <mavsdk/plugins/info/info.h>
#include <mavsdk/plugins/follow_me/follow_me.h>
#include <mavsdk/plugins/arm_authorizer_server/arm_authorizer_server.h>
```

---

*Generated by integrating MAVSDK C++ Guide (https://mavsdk.mavlink.io/main/en/cpp/guide) with 58 C++ example files from `dependencies/MAVSDK/examples/`*
