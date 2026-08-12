# Tello + SLAM (Agent 5, C1)

Tools for the Tello SLAM go/no-go. The point of C1 is one decision: **is this venue's
surface good enough to fly stella_vslam on the Tello, or do we run SITL instead?**

The order below is the demo-day workflow: screen the surface from photos, then confirm
live, then read the verdict.

## 1. Screen the surface from photos (no drone)

```bash
./feature_scout.py --floor floor.jpg --forward *.jpg
```

Runs stella's OWN ORB detector over each photo and reports feature count, an 8x8
coverage grid, dead cells, and glare. The floor shot decides the verdict -- it is what
the VPS sees and the surface that co-fails both the VPS and SLAM.

Caveat baked into the tool: a phone still is an optimistic ceiling. The Tello streams
960x720 with motion blur, so real yield is lower. A "MARGINAL" here means "no" live.

## 2. Confirm live on the real Tello

Join the Tello WiFi, build the Tello tree and the SLAM tree, then:

```bash
cd scripts/tello/slam && ./run.sh
```

Four tmux panes: RX (`--tello`, decodes video to `camera/stream`), stella
(`stella_vslam_monocular`, calibrated `config/stella_config_tello.yaml`), `tello_teleop`
(manual flight), and the measurement. Fly a path, then a return-to-start loop.

Controls (teleop pane): `T` takeoff, `L` land, `WASD` move, `RF` up/down, `QE` yaw,
`Space` hover, `Esc` land+quit.

## 3. Read the verdict

`measure_tello_slam.py` prints one `[TELLO_SLAM]` line/sec and a
`[TELLO_SLAM_SUMMARY]` on Ctrl-C: pose rate, tracking_frac, blind_frac, return-error.

**Go/no-go:** if tracking_frac is low or blind_frac is high, or the drone visibly drifts
the instant SLAM drops -> STOP, run SITL. SITL is the reliable headline; the Tello is the
stretch.

Two numbers this pane deliberately does NOT give:
- **Physical drift in metres** -> run `../measure_drift.py` on a fixed-camera clip. That
  external camera is the only ground truth that sees the drone when the VPS/SLAM cannot;
  telemetry reads a false zero while blind.
- **Scale consistency** -> compare the SLAM z-delta against the known metric flight height.

## Notes

- Agent 4 relocated the stella configs into `config/`, so `slam2.hpp`'s compiled default
  (`dependencies/stella_config.yaml`) is a dead path. `run.sh` sets `STELLA_CONFIG_PATH`
  explicitly to dodge it.
- SITL camera is UDP 11112, real Tello video is 11111 (split by the RX `--tello` flag), so
  a SITL run and this Tello session can share a host.
