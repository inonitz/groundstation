[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![MIT][license-shield]][license-url]

<!-- PROJECT LOGO -->
<div align="center">
<h3 align="center">Groundstation</h3>
  <p align="center">
    Off-Board, VLM-Driven Autonomous Drone Control
  </p>
</div>

## NOTE

**This `README.md` requires cleanup since it doesn't address the DJI Mobile SDK Support, The new Perception Engine developed, and so much more. The current Documentation is generally correct but requires fine-tuning for proper build & usage.**

## About The Project

Groundstation is a C++17 / ROS 2 off-board autonomous flight stack for small drones (primary
target: DJI Tello; PX4 software-in-the-loop in Gazebo as the simulation fallback). The aircraft is
a dumb peripheral — it only streams H.264 video and telemetry over the local network. All
perception, planning, and control run on a ground-station computer.

The control philosophy is **"the VLM plans, deterministic math executes."** A local
Vision-Language Model (Qwen3-VL, served by `llama-server`) acts as a high-level, event-driven
planner: when the task queue drains it is shown the current camera frame, vehicle state, a YOLO
perception JSON (detections + metric depth), and the executed-command history, and it returns a
plan — a JSON array of discrete verbs (`takeoff`, `go`, `land`, `stop`, `approach`, plus
`rotate`/`orbit`/`search` still specced-only). A deterministic **20 Hz control loop** consumes
that plan one task at a time, owns the flight state machine, and streams setpoints to the flight
controller.

The two flight controllers are hidden behind a compile-time backend interface (CRTP,
`GenericBackend<Derived>`) so the same FMU logic drives either PX4 (SITL) or a real Tello. See
[docs/project_overview.md](docs/project_overview.md) for the full architectural framing and
[docs/ROADMAP.md](docs/ROADMAP.md) for current status of every objective.

<br></br>

### Project Structure

The project is structured around ROS 2 nodes that communicate via standard topics, under
`source/llm_to_action/`:

* `fmu/`: The Flight Management Unit — the VLM planner + 20 Hz deterministic control loop and
  flight state machine. The core of the system.
* `generic_backend/`, `px4_backend/`, `tello_backend/`: The compile-time backend abstraction and
  its two concrete implementations (PX4 SITL, DJI Tello).
* `perception/`: YOLO segmentation + metric depth integration (`PerceptionRuntime`), feeding the
  VLM's prompt and the `approach` servo.
* `asr/`: Whisper/Sherpa speech-to-text server node (retained as a component; not the primary
  demonstrated pipeline — see below).
* `keyboard/`: X11 push-to-talk / manual-override keyboard hook.
* `frame/`, `offboard_ctrl/`, `gstreamer_gz_udp_tx/`, `gstreamer_tello_udp_tx/`,
  `gstreamer_udp_cam_rx/`, `util/`: camera transport, offboard streaming, and shared utilities.

Outside `llm_to_action/`:

* `source/slam/`: work-in-progress monocular VSLAM/VIO (Stella-VSLAM / OpenVINS) and OctoMap
  scaffolding for the longer-horizon SLAM + A* navigation plan ("Being B" in
  [docs/project_overview.md](docs/project_overview.md)).
* `scripts/` & `cmake/`: build utilities, CMake configurations, and CPM dependency management.

> This branch (`feature-llm-driver`) is intentionally self-contained: the earlier
> `speech_to_action`/`nav` pipeline has been removed from it to keep scope focused on the
> VLM-driven `llm_to_action` stack described above.

<br></br>

## Getting Started

### Prerequisites

* ROS 2 (Humble recommended)
* CMake 3.16 or higher
* A working C++17 compiler toolchain (e.g., Clang or GCC)
* Core dependencies: Eigen3, OpenCV, GStreamer, ONNX Runtime, X11 (if building in a WSL
  environment)
* PX4-Autopilot + Gazebo (for SITL) and/or a DJI Tello on the same network (for real hardware)

### Downloading the Source

```sh
git clone https://github.com/inonitz/groundstation.git
cd groundstation
```

### Configuring & Building

`build.sh` (Linux/WSL) / `build.ps1` (Windows) abstract the CMake configure + Ninja build steps.

```sh
./build.sh <build_type> <library_type> <action>
```

- `build_type`: `debug`, `release`, `release_dbginfo`, `debug_perf`, `release_perf`
- `library_type`: `shared`, `static`
- `action`: `configure`, `build`, `cleanbuild`, `rungs`, `runsim`

```sh
./build.sh release static configure
./build.sh release static build
```

Backend selection (PX4, Tello, or both) is a CMake option
(`GROUNDSTATION_BUILD_BACKEND_PX4` / `_TELLO` / `_ALL`); see `CMakeLists.txt`.

<br></br>

## Usage

The fastest way to see the stack fly is the PX4 SITL rig:

```sh
./scripts/simenv_llm.sh              # canned plan: takeoff -> forward 1m -> land, no VLM
./scripts/simenv_llm.sh cross        # per-axis FLU sanity check
./scripts/simenv_llm.sh approach     # closed-loop APPROACH against a synthesized detection
./scripts/simenv_llm.sh approach-real # APPROACH against real YOLO seg+depth in-sim
./scripts/simenv_llm.sh vlm          # full stack: Qwen3-VL plans, no canned commands
```

Each mode launches PX4 + Gazebo + the FMU (and, for `vlm`, `llama-server`) in a tmux session; tear
it down with `Ctrl+B` then `:kill-session`. See the script header for full details and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for what each FMU verb actually does.

For real-hardware (Tello) bring-up notes, see
[docs/tello_backend_notes.md](docs/tello_backend_notes.md).

<br></br>

## Documentation

Start in [docs/README.md](docs/README.md) — it indexes the roadmap, architecture spec,
development log, and task docs.

<br></br>

## License

Distributed under the GNU GPLv3 License. See `LICENSE` file for more information.

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/inonitz/groundstation?style=for-the-badge&color=blue
[contributors-url]: https://github.com/inonitz/groundstation/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/inonitz/groundstation?style=for-the-badge&color=blue
[forks-url]: https://github.com/inonitz/groundstation/network/members
[stars-shield]: https://img.shields.io/github/stars/inonitz/groundstation?style=for-the-badge&color=blue
[stars-url]: https://github.com/inonitz/groundstation/stargazers
[license-shield]: https://img.shields.io/github/license/inonitz/groundstation?style=for-the-badge
[license-url]: https://github.com/inonitz/groundstation/blob/main/LICENSE
