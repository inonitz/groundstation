# Groundstation

**Voice-commanded autonomous camera drone: the VLM plans, deterministic verbs fly.**

All perception, planning, and control run on a ground-station computer. The aircraft is a dumb
peripheral streaming H.264 video and telemetry; a local Vision-Language Model (Qwen3-VL via
`llama-server`) answers scene questions and plans bounded verb sequences, and deterministic
code -- never the LLM -- produces every motor command.

Two living systems share this repo:

- **The MVD (Python, `projects/integration*`)** -- the field-tested demo: phone-connected DJI
  drone, push-to-talk ASR, a 4-tier command router (emergency regex -> override -> verbs ->
  VLM perception), YOLO26-seg + OmDet-Turbo + SAM2.1 + VLM-gated highlighting, spoken answers.
- **`projects/llm_to_action` (C++17 / ROS 2)** -- the real system being built: FMU with a 20 Hz
  control loop and flight state machine behind a compile-time backend (PX4 SITL in Gazebo / DJI),
  YOLO seg + metric depth perception, VLM objective planning. Owner-written.

## Layout

```
projects/
  integration/           frozen field-tested MVD fallback -- never edited
  integration_notify/    MVD fork: person-notify demo + dashboard
  integration_tts/       MVD fork: voice-out; the going-forward base
  integration_harden/    MVD fork: the current interview-sprint work (+ test/)
  llm_to_action/         C++ stack: source/ + test/sitl (consolidated SITL suite)
  slam/                  C++ VSLAM/VIO work (source/)
tools/       dji_mock (mock API server) · devenv (Dockerfile + installs) · preflight.sh
assets/      gazebo worlds/models, drone configs
docs/        active/ · runbooks/ · specs/ · research/ · stale/  -- start at docs/README.md
archive/     dead-but-revivable code (tello, cv prototypes)
```

## Quickstart

```bash
bash tools/preflight.sh              # checks every model/binary/tool, prints what's missing
bash tools/devenv/install-runtime-deps.sh   # after any container rebuild

# C++ build (backend: px4 | tello | dji | all):
./build.sh release shared dji build

# MVD desk test, no drone (mock control + webcam):
python3 tools/dji_mock/mock_apiserver.py 127.0.0.1 8079     # terminal 1
bash projects/integration/run_mvd.sh webcam mock            # terminal 2

# SITL (PX4 + Gazebo + FMU):
projects/llm_to_action/test/sitl/run.sh --list
projects/llm_to_action/test/sitl/run.sh hover
```

Real-drone runs are **human-only** with the aircraft secured -- read the safety rules in
[CLAUDE.md](CLAUDE.md) and [docs/runbooks/2026-08-27-run-guide.md](docs/runbooks/2026-08-27-run-guide.md)
first, and know the kill switch before arming.

Models live in `/root/models` (volume-mounted, travels between machines) -- `tools/preflight.sh`
tells you what belongs there.

## Documentation

[docs/README.md](docs/README.md) indexes everything: architecture, roadmap, runbooks, specs,
and the running development log.

## License

GNU GPLv3 -- see `LICENSE`.
