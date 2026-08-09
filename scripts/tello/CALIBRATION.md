# Tello camera calibration (B2)

Calibrate the real Tello's monocular camera and write a stella_vslam config for it.
This is a two-step, standalone toolchain. No ROS2, no FMU build, no Gazebo. You run it
on the laptop, over the Tello's own WiFi, with a printed chessboard in hand.

The output is `dependencies/stella_config_tello.yaml`, the real-camera counterpart to the
sim config `dependencies/stella_config.yaml`.

## Prerequisites

Join the laptop to the Tello's WiFi AP (SSID `TELLO-XXXXXX`) first. The host then gets
`192.168.10.2` and the drone is `192.168.10.1`. Nothing works before that association.

Print a chessboard on flat, rigid card. Measure one square edge in metres. Count the
*inner* corners, not the squares: a board with 10x7 squares has a 9x6 inner-corner grid.
Pass those inner-corner counts as `cols` and `rows`.

Python needs `cv2`, `numpy`, and `yaml`. All three are present in this checkout's
environment.

## Run, in order

Capture frames. The drone does not fly; hold it and move the board.

```bash
python3 scripts/tello/capture_calibration_frames.py calib_frames 9 6
# SPACE saves a frame, ESC quits. Aim for 20-40 frames.
# Vary angle and distance -- tilt the board, fill different parts of the view.
```

Note two numbers the script prints: the CONFIRMED resolution and the measured stream fps.
Do not assume 960x720 or 30 fps. Use what the script reports.

Calibrate and write the config. Feed it your board's square size in metres and the fps the
capture script measured.

```bash
python3 scripts/tello/calibrate_camera.py calib_frames 9 6 0.025 <measured_fps>
# args: <frames_dir> <inner_cols> <inner_rows> <square_size_m> <measured_fps>
```

This writes `dependencies/stella_config_tello.yaml` with a `Camera:` block only.

## After it writes the config

The script writes the `Camera:` block alone. Copy `FeatureExtractor:` and any other
non-`Camera:` section from `dependencies/stella_config.yaml` into the new Tello file by
hand. Tuning those sections is B1's job, not this tool's.

## What a good result looks like

The reprojection RMS error is the score. Under ~1.0 px is good; the calibration is
trustworthy. At or above 1.0 px the script warns you. Recapture with more frames and
better variety: more tilt, more distances, the board reaching the frame edges and corners.
Blurry frames and a board that stays flat-on in the centre are the usual causes of a high
error.
