# llm_to_action

An off-board autonomy stack for a camera drone. It turns a spoken or typed objective into flight.
A vision-language model (VLM) plans; a C++ flight management unit (FMU) flies; a browser dashboard
shows what the drone sees and does, live.

The stack runs off the aircraft. It talks to the flight controller over a backend (PX4, DJI, or
Tello). Exactly one backend is compiled per build. Simulation uses the PX4 backend with Gazebo.

| Section | What it covers |
|---|---|
| [Architecture](#architecture) | The ROS2 nodes and how data flows between them |
| [Build](#build) | Compiling the stack for one backend |
| [Run the SITL demo](#run-the-sitl-demo) | The headless Gazebo demo, watched in the browser |
| [Open the dashboard](#open-the-dashboard) | The judge-facing live view |
| [Repository layout](#repository-layout) | Where each part lives |
| [Safety](#safety) | Rules for a real aircraft |

## Architecture

The stack is a set of ROS2 nodes. The FMU is the center. It reads the camera, runs perception,
asks the VLM for a plan, and drives the flight backend. Data flows like this:

```
 microphone ─▶ asr ──/asr_server/transcribe──▶ ┌───────────────┐
 keyboard  ─▶ keyboard ──/keyboard/in/raw────▶ │      FMU      │──▶ backend (PX4 / DJI / Tello)
 camera (sim/drone) ─▶ gstreamer_rx ──/image─▶ │ (fmu_<backend>)│
                        VLM (llama-server) ◀──▶ └──────┬────────┘
                          HTTP /v1/chat/completions    │ observability topics (FMU_OBSERVABILITY=1)
                                                        ▼
                                    /fmu/hud  /fmu/vlm_text  /fmu/vlm_context  /fmu/rates
                                    /fmu/perception/annotated  /fmu/perception/depth
                                                        │
                                                        ▼
                                              dashboard bridge ──▶ browser (port 8088)
```

| Node (executable) | Language | Role |
|---|---|---|
| `fmu` (`llm_to_action_fmu_<backend>`) | C++ | The flight management unit. Runs the 20 Hz control loop, the seg and depth perception, the VLM planning, and the safety laws. Publishes the observability topics the dashboard reads. |
| `asr` (`llm_to_action_asr_server`) | C++ | Speech-to-text. Publishes each transcript on `/asr_server/transcribe`. The FMU takes it as a voice objective. |
| `gstreamer_udp_cam_rx` (`llm_to_action_gstreamer_rx`) | C++ | Receives the camera stream over UDP with GStreamer. Publishes it on `/image`. |
| `gstreamer_gz_udp_tx` (`libGazeboGstCameraPlugin.so`) | C++ | The Gazebo camera plugin. Sends the simulated camera over UDP to the receiver. PX4/SITL builds only. |
| `keyboard` (`llm_to_action_keyboard_hook`) | C++ | A global key grabber for manual override. Publishes keys on `/keyboard/in/raw`. |
| `offboard_ctrl` (`llm_to_action_offboard_mode`) | C++ | A PX4 offboard setpoint helper. PX4 builds only. |
| `px4_backend` / `dji_backend` / `tello_backend` / `generic_backend` | C++ | The flight backend. One is linked into the FMU per build. It converts FMU commands to the aircraft's protocol. |
| `perception`, `frame`, `util` | C++ | Support libraries linked into the FMU. Perception runs the ONNX models; frame does coordinate conversions. |
| `dashboard` (`serve.py`) | Python | A bridge. It subscribes the FMU observability topics and serves the browser dashboard. See [source/dashboard/README.md](source/dashboard/README.md). |

The FMU publishes the observability topics only when it starts with `FMU_OBSERVABILITY=1`. With the
gate off, the dashboard shows no data. The SITL demo launcher sets the gate for you.

## Build

The stack builds out of source into `build/<type>/<lib>/<backend>/`. Build one backend at a time.
Run these from the repository root (`/root/groundstation`):

```bash
./build.sh release shared px4 configure   # once, or after a CMake change
./build.sh release shared px4 build        # compile
```

This produces the node executables under `build/release/shared/px4/bin/`, including
`llm_to_action_fmu_px4` and `llm_to_action_gstreamer_rx`. A fresh checkout has no binaries, so you
must build before you run. See [../../build.sh](../../build.sh) `--help` for other backends and
build types.

## Run the SITL demo

The demo flies a "follow the person" scenario in Gazebo, with no GUI window. You watch it in the
browser, not in a Gazebo window. It needs the PX4 build above, `gz`, `MicroXRCEAgent`, and the ONNX
vision models under `/root/models/vision/`.

```bash
cd projects/llm_to_action/source/dashboard
./run_sitl_demo.sh                                # holds ~30 min, self-assesses once
HEADLESS_TIMEOUT_SECONDS=150 ./run_sitl_demo.sh   # short self-test
```

The launcher brings up PX4 SITL, Gazebo, and the FMU with observability on. It starts the dashboard
bridge and an assessor. The assessor checks the whole pipeline and writes a PASS/FAIL verdict. The
stack tears itself down after the timeout. Logs land in `logs_<timestamp>/`; the FMU's own log lands
in `test/sitl/runs/follow/captured_panes_log.txt`.

Other scenarios live in the SITL harness. List them with:

```bash
cd projects/llm_to_action/test/sitl
./run.sh --list
```

## Open the dashboard

While the demo runs, open `http://localhost:8088`. The page shows four panels:

- the annotated camera stream, with detection boxes baked in;
- the depth colormap;
- the flight HUD, with the detection list;
- the VLM reasoning log, with the objective and the executed-command history.

The `follow` demo runs without the VLM, so the VLM panel stays idle. To see the VLM panel fill, run
a scenario that starts the VLM (see `run.sh --list`).

## Repository layout

| Path | What it holds |
|---|---|
| `source/` | The ROS2 nodes, one folder each, plus the dashboard bridge |
| `source/dashboard/` | The browser dashboard and its SITL demo launcher |
| `test/sitl/` | The SITL harness, scenario table, and per-scenario verdicts |
| `test/lib/sim_core.sh` | The shared launch engine that brings up PX4, Gazebo, and the FMU |

## Safety

This project can fly a real aircraft. Read the safety rules in the repository root `CLAUDE.md`
before you command real hardware. Simulation (PX4 SITL and Gazebo) is safe. A real aircraft must be
physically secured before any command that can spin its motors.
