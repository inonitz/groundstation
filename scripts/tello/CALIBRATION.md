# Tello camera calibration

Measure the real Tello's camera and write `dependencies/stella_config_tello.yaml`, the
real-camera counterpart to the sim config `dependencies/stella_config.yaml`.

Two scripts, run in order. No ROS2, no FMU build, no Gazebo. The drone never flies.

A provisional config already sits at that path, built from community-measured intrinsics so
SLAM can run before you calibrate. It is not measured from our drone. Running step 2
overwrites it.

## 1. Print the board

Print `checkerboard_a4_9x6_20mm.pdf` on A4 landscape at **100% scale**, with fit-to-page
off.

Then check the print did not get rescaled. Measure the 100 mm bar under the board, or
measure the board itself across all 10 squares, which is 200 mm. Either one will tell you.
If the number is wrong, reprint, because a rescaled board makes every distance wrong.

`python3 scripts/tello/make_checkerboard.py 13` regenerates it at any square size.

Back it with something flat and rigid. A hardcover notebook works. The backing has to be at
least as big as the board, which is 200x140 mm. If yours is smaller, print the 13 mm version
instead, which is 130x91 mm and fits an A5 cover.

Press the sheet flat first. Leave it under the notebook with a weight on top for ten minutes,
because a fresh print curls. Then wrap the paper margins around the cover and hold them at
the back, or slide the top margin inside the front cover and close it. Both grip the margin
only, so no squares get covered. A hand-held loose sheet curls, and that is the usual cause
of a bad result.

Then measure your squares. Measure across eight of them and divide by eight. Keep that
number in metres for step 2.

## 2. Capture frames

Join the laptop to the Tello's WiFi AP first. Nothing works before that.

```bash
cd ~/groundstation
python3 scripts/tello/capture_calibration_frames.py calib_frames 9 6
```

SPACE saves a frame, ESC quits. Aim for 20 to 40.

Put the drone on a table and move the board in front of it. The one rule that matters: keep
the board moving around the frame. Push it into all four corners and out to the edges, not
just the middle, and tilt it 30 to 45 degrees most of the time. The distortion numbers come
from the edges of the image, so a board that stays flat-on in the centre gives a bad result
no matter how many frames you take.

Save a frame only when the corner overlay is drawn. Hold still for a moment first, since
motion blurs the corners.

Note the two numbers it prints at the end: the confirmed resolution, and the measured fps.

## 3. Calibrate

Run from the repo root. The output path is relative to your working directory.

```bash
python3 scripts/tello/calibrate_camera.py calib_frames 9 6 <square_size_m> <measured_fps>
```

Use your measured square size, in metres, and the fps the capture script reported.

## Was it any good?

The reprojection RMS error is the score. Under 1.0 px is good. The script warns above that.

Also glance at the numbers it wrote. `cx` and `cy` should sit near the image centre, so near
480 and 360 at 960x720. `fx` and `fy` should be within a few percent of each other. If they
are not, your board coverage was too thin, whatever the RMS says. Recapture with more tilt
and more edge coverage.

The script writes the `Camera:` block only. Copy `FeatureExtractor:` over from
`dependencies/stella_config.yaml` by hand. Tuning it is B1's job.

## If something breaks

**Drone beeps and goes red.** That is the SDK-mode timeout, not a video fault. The capture
script holds the session open, so this means it exited early. Read its last printed line.

**"no video packets on UDP 11111".** The host firewall is dropping them. The script prints
the exact `iptables` rules to add. Do not use `ufw` here, it reports success without
applying anything. Background in `docs/ARCHITECTURE.md` section 17.

**Preview is slow.** It should hold near 30 fps, shown on the overlay. If it does not, the
measured fps at the end is wrong and must not go into the config.

Note that a working `tello_teleop` session does not prove video works. Its camera is
best-effort and it carries on without one.
