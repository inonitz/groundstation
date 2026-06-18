# MAVSDK C++ API — Comprehensive Reference

> Generated from all 58 C++ example files in `dependencies/MAVSDK/examples/`

---

## Architecture Overview

MAVSDK is a **plugin-based** C++ library for communicating with UAVs (drones) over MAVLink. Each plugin operates on a `System` object, which represents a discovered MAVLink component. The typical pattern is:

```
Mavsdk::add_any_connection(url) → Mavsdk::poll() → Mavsdk::first_autopilot() → System → Plugin{system}
```

---

## 1. Action Plugin — High-Level Flight Commands

**Purpose:** Simple, high-level vehicle commands without manual mode management.

| Method | Description |
|--------|-------------|
| `arm()` | Arms the motors |
| `disarm()` | Disarms the motors |
| `takeoff_to_altitude_m(alt)` | Takes off to specified altitude |
| `land()` | Initiates landing |
| `return_to_launch()` | RTL |
| `hold()` / `hold_to_altitude_m()` | Loiter at current or specified altitude |
| `goto_location(lat, lon, alt_m)` | Fly to a specific GPS coordinate |
| `set_current_speed(kmh)` | Set cruise speed (used with `goto_location`) |
| `transition_to_fixedwing()` / `transition_to_multicopter()` | VTOL mode transitions |
| `reboot()` | Safely reboot autopilot |
| `terminate()` | Emergency motor stop + parachute deploy |
| `set_relay(index, On/Off)` | Toggle hardware relay |
| `set_actuator(index, value)` | Set servo position (0–1) |

**Examples:** `takeoff_and_land`, `set_gps_origin`, `fly_mission`, `vtol_transition`, `hold`, `goto_location`, `multiple_drones`, `fly_multiple_drones`, `reboot`, `terminate`, `set_relay`, `set_actuator`, `fly_qgc_mission`

---

## 2. Telemetry Plugin — Vehicle State

**Purpose:** Subscribe to and query real-time vehicle state data.

| Method / Callback | Description |
|-------------------|-------------|
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

**Used in:** Nearly every example — it's the primary telemetry subscription interface.

---

## 3. MissionRaw Plugin — QGroundControl Plan Import

**Purpose:** Import, upload, and fly `.plan` files from QGroundControl.

| Method | Description |
|--------|-------------|
| `import_qgroundcontrol_mission(path)` | Parse `.plan` → `MissionImportData` |
| `upload_mission(items)` | Upload parsed mission items |
| `start_mission()` | Begin execution |
| `pause_mission()` / `resume_mission()` | Pause/resume mid-flight |
| `clear_mission()` | Remove all mission items |
| `subscribe_mission_progress(cb)` | `(current_item, total_items)` callback |

**Examples:** `fly_mission`, `fly_qgc_mission`, `fly_multiple_drones`, `autopilot_server`

---

## 4. Camera Plugin — Camera Control

**Purpose:** Discover and control camera components on the vehicle.

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

**Examples:** `camera`, `camera_zoom`, `camera_settings`, `camera_server`, `camera_client`

---

## 5. Gimbal Plugin — Gimbal Control

**Purpose:** Control gimbal attitude, rates, and region-of-interest.

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

**Examples:** `gimbal`, `gimbal_device_tester`

---

## 6. Offboard Plugin — Low-Level Flight Control

**Purpose:** Direct vehicle control from external compute (companion computer).

| Method | Description |
|--------|-------------|
| `start()` | Enter offboard mode |
| `stop()` | Exit offboard mode |
| `set_velocity_ned(v_n, v_e, v_d)` | NED velocity setpoint |
| `set_position_global(lat, lon, alt, alt_type)` | Global position setpoint |
| `set_velocity_body(v_fwd, v_right, v_down)` | Body-frame velocity |
| `set_attitude(r, p, y, thrust)` | Attitude + thrust control |

**Coordinate systems:** NED (North-East-Down), Global (WGS84), Body frame, Attitude (roll/pitch/yaw)
**Altitude types:** `RelHome` (relative to home), `Amsl` (above mean sea level)

**Examples:** `offboard`, `set_gps_origin`

---

## 7. ManualControl Plugin — Joystick Control

**Purpose:** Fly the drone via joystick input (SDL2).

| Method | Description |
|--------|-------------|
| `start_position_control()` | Begin position control mode |
| `set_manual_control_input(input)` | Send joystick axes → pitch/roll/yaw/throttle |

**Examples:** `manual_control`, `joystick`

---

## 8. Geofence Plugin — No-Fly Zones

**Purpose:** Upload geofence polygons to the vehicle.

| Method | Description |
|--------|-------------|
| `upload_geofence(items)` | Upload fence items |

**Fence types:** `Inclusion` (stay inside), `Exclusion` (stay outside)
**Geometries:** Polygon (list of points), Circle (center + radius)

**Example:** `geofence`

---

## 9. MavlinkDirect Plugin — Raw MAVLink Messages

**Purpose:** Send and receive arbitrary MAVLink messages.

| Method | Description |
|--------|-------------|
| `subscribe_message(name_or_id, cb)` | Subscribe to specific or all (empty string) messages |
| `send_message(name, data)` | Send a single message |
| `load_custom_xml(path)` | Load custom XML dialect for non-standard messages |

**Examples:** `subscribe_gps`, `mavlink_stats`, `sender`, `sender_custom`

---

## 10. MavlinkPassthrough Plugin — MAVLink Packet Manipulation

**Purpose:** Queue and send raw MAVLink packets (for simulating components).

| Method | Description |
|--------|-------------|
| `queue_message(packet)` | Queue a raw MAVLink packet |
| `subscribe_message(msg_id, cb)` | Subscribe by numeric MAVLink ID |
| `send_command_long(cmd, param1..7)` | Send MAV_CMD_* commands |

**Examples:** `parachute`, `publish_battery`, `gimbal_device_tester`

---

## 11. MavlinkForwarding Plugin — Traffic Forwarding

**Purpose:** Forward MAVLink traffic between connections.

| Method | Description |
|--------|-------------|
| `add_any_connection(url, ForwardingOption)` | Add connection with forwarding enabled |

**Example:** `mavlink_forwarding`

---

## 12. LogStreaming Plugin — Live Log Stream

**Purpose:** Stream raw log data from the vehicle in real-time.

| Method | Description |
|--------|-------------|
| `subscribe_log_streaming_raw(cb)` | Receive log data chunks |
| `start_log_streaming()` | Begin streaming |
| `stop_log_streaming()` | Stop streaming |

**Formats:** `.ulg` (PX4), `.bin` (ArduPilot)

**Examples:** `log_streaming`, `log_callback`

---

## 13. LogFiles Plugin — Log File Download

**Purpose:** Download stored log files from the vehicle.

| Method | Description |
|--------|-------------|
| `get_entries()` | List log file entries |
| `download_log_file_async(id, progress_cb)` | Download with progress tracking |
| `erase_all_log_files()` | Clear all logs |

**Progress callback:** `(percentage, downloaded_bytes, speed_kib_s)`

**Example:** `logfile_download`

---

## 14. Ftp Plugin — File Transfer (Client)

**Purpose:** Upload/download files to/from the vehicle.

| Method | Description |
|--------|-------------|
| `upload_async(path, progress_cb)` | Upload file |
| `download_async(path, progress_cb)` | Download file |
| `remove_file_async(path)` | Delete file |
| `rename_async(old, new)` | Rename |
| `create_directory_async(path)` | Create directory |
| `remove_directory_async(path)` | Remove directory (recursive) |
| `list_directory_async(path)` | List directory contents |
| `are_files_identical_async(path_a, path_b)` | Compare files |

**Example:** `ftp_client`

---

## 15. FtpServer Plugin — File Transfer (Server)

**Purpose:** Expose a local directory as an MAVLink FTP server.

| Method | Description |
|--------|-------------|
| `set_root_dir(path)` | Set the exposed directory |

**Example:** `ftp_server`

---

## 16. Param Plugin — Parameter Management

**Purpose:** Read and write vehicle parameters.

| Method | Description |
|--------|-------------|
| `get_all_params()` | Get all parameters at once |
| `get_param_float(name)` | Query float parameter |
| `get_param_int(name)` | Query int parameter |
| `set_param_float(name, value)` | Set float parameter |
| `set_param_int(name, value)` | Set int parameter |

**Error handling:** `WrongType` errors trigger type fallback (float ↔ int)

**Examples:** `params`, `autopilot_server`, `log_streaming`

---

## 17. ParamServer Plugin — Parameter Server

**Purpose:** Act as a parameter server (simulating an autopilot).

| Method | Description |
|--------|-------------|
| `provide_param_float(name, value)` | Serve float parameter |
| `provide_param_int(name, value)` | Serve int parameter |

**Example:** `autopilot_server`

---

## 18. ComponentMetadata Plugin — Component Info

**Purpose:** Request and receive component metadata (parameters, events, actuators) as JSON.

| Method | Description |
|--------|-------------|
| `request_autopilot_component(comp_id)` | Request metadata for a component |
| `subscribe_metadata_available(cb)` | Get notified when metadata is available |

**Metadata types:** `Parameters`, `Events`, `Actuators`, `AllCompleted`

**Example:** `component_metadata`

---

## 19. Events Plugin — MAVLink Events

**Purpose:** Subscribe to MAVLink event logs and health checks.

| Method | Description |
|--------|-------------|
| `subscribe_events(cb)` | Receive log-level events with namespace |
| `subscribe_health_and_arming_checks(cb)` | Receive arming check results |

**Example:** `events`

---

## 20. Transponder Plugin — ADS-B

**Purpose:** Subscribe to ADS-B transponder reports from other aircraft.

| Method | Description |
|--------|-------------|
| `set_rate_transponder(hz)` | Set update rate |
| `subscribe_transponder(cb)` | Receive ICAO address, lat/lon, altitude, heading, velocity, callsign, emitter type, squawk |

**Example:** `transponder`

---

## 21. Wind Plugin — Wind Telemetry

**Purpose:** Subscribe to wind data from the vehicle.

| Method | Description |
|--------|-------------|
| `subscribe_wind(cb)` | Receive NED wind velocity, variability, and altitude |

**Example:** `wind`

---

## 22. Tune Plugin — Audio Feedback

**Purpose:** Play tunes on the vehicle's buzzer/beeper.

| Method | Description |
|--------|-------------|
| `play_tune(tune_string)` | Send a tune description (notes, durations, tempo) |

**Example:** `tune`

---

## 23. Winch Plugin — Winch Control

**Purpose:** Control a winch/tether system.

| Method | Description |
|--------|-------------|
| `lock(tension)` | Lock winch at tension level |

**Example:** `winch`

---

## 24. Calibration Plugin — Sensor Calibration

**Purpose:** Run sensor calibration routines.

| Method | Description |
|--------|-------------|
| `calibrate_accelerometer_async(progress_cb)` | Accelerometer calibration |
| `calibrate_gyro_async(progress_cb)` | Gyro calibration |
| `calibrate_magnetometer_async(progress_cb)` | Magnetometer calibration |

**Progress callback:** `(status_text, percentage)`

**Example:** `calibrate`

---

## 25. Shell Plugin — Interactive Shell

**Purpose:** Send commands to the vehicle and receive output.

| Method | Description |
|--------|-------------|
| `send(command)` | Send a shell command |
| `subscribe_receive(cb)` | Receive command output |

**Example:** `mavshell`

---

## 26. Info Plugin — Vehicle Information

**Purpose:** Query vehicle firmware and product info.

| Method | Description |
|--------|-------------|
| `get_version()` | Firmware version |
| `get_product()` | Product info |
| `get_identification()` | Vehicle identification |

**Example:** `system_info`

---

## 27. Mavsdk Core — Lifecycle & Connection Management

**Purpose:** The top-level `Mavsdk` class manages connections, system discovery, and plugin lifecycle.

| Method | Description |
|--------|-------------|
| `add_any_connection(url)` | Add UDP/TCP/serial/UNIX connection |
| `add_udp_connection(port, server_mode)` | UDP connection |
| `add_tcp_connection(server_url)` | TCP connection |
| `add_serial_connection(port, baud)` | Serial connection |
| `add_unix_socket_connection(path)` | Unix socket |
| `remove_connection(url)` | Remove a connection |
| `subscribe_on_new_system(cb)` | Callback when a new system is discovered |
| `subscribe_is_connected(cb)` | Connection state changes |
| `subscribe_connection_errors(cb)` | Connection error notifications |
| `subscribe_incoming_messages_json(cb)` | Raw MAVLink message inspection |
| `poll()` / `poll_for(next_system)` | Blocking system discovery |
| `first_autopilot(timeout)` | Get first autopilot system |
| `systems()` / `all_systems()` | Query discovered systems |
| `set_callback_executor(executor)` | Custom callback threading |
| `log::subscribe(cb)` | Custom logging |
| `server_init()` / `server_run()` / `server_stop()` / `server_destroy()` | C API daemon lifecycle |

**Examples:** `disconnect`, `reconnect`, `callback_executor`, `mavlink_forwarding`, `log_callback`, `start_stop_server`

---

## 28. Server-Side Plugins (Simulating Vehicle Components)

These plugins let the ground station act as a vehicle component:

| Plugin | Methods |
|--------|---------|
| **ActionServer** | `set_allow_takeoff()`, `set_allow_arm()` |
| **MissionRawServer** | `subscribe_incoming_mission()`, `set_current_item()` |
| **ParamServer** | `provide_param_float()`, `provide_param_int()` |
| **TelemetryServer** | `publish_position()`, `publish_health_all_ok()` |
| **CameraServer** | `set_information()`, `respond_*()` handlers |
| **ArmAuthorizerServer** | `subscribe_arm_authorization()`, `accept/reject_arm_authorization()` |

**Examples:** `autopilot_server`, `camera_server`, `arm_authorizer_server`

---

## 29. FollowMe Plugin — Autonomous Following

**Purpose:** Autonomous drone following of a moving target.

| Method | Description |
|--------|-------------|
| `set_config(height_m, angle_rad, follows_joystick)` | Configure follow behavior |
| `start()` / `stop()` | Start/stop following |
| `set_target_location(lat, lon, alt)` | Set target position |
| `get_last_location()` | Get last known target location |

**Examples:** `follow_me`, `fake_location_provider`

---

## Key Design Patterns Observed

1. **Async-first:** Most operations return `Result` objects or use callbacks; blocking calls use `poll_for()` or `std::future`
2. **Plugin per subsystem:** Each capability is a separate plugin class instantiated from a `System`
3. **Subscription model:** Telemetry, events, and state use `subscribe_*()` callbacks rather than polling
4. **Component-based:** `System` can have multiple components (autopilot, camera, gimbal, battery)
5. **Connection abstraction:** UDP, TCP, serial, and Unix sockets all use the same `add_*_connection()` API
6. **Error handling:** `Result` objects with `success()` / `error_string()` for every operation
