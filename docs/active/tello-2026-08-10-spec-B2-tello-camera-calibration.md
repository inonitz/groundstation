# B2 — Tello camera calibration (operator, ground)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Revised:** 2026-08-09 (session review —
see Revision log). **Branch:** none needed — see B4's "Where this runs" note; same reasoning applies
here (no file-scope collision with A-track). **Depends:** none (parallel, no flight, and — corrected
this revision — does NOT depend on B4's `rx_node` fix either; see Scope). **ROADMAP:** 7.1 support.
**Owner:** operator. **Lock:** none — nothing else touches `dependencies/stella_config_tello.yaml` or a
new capture script.

## Objective
Give stella a real-Tello camera model. Calibrate on the ground so B1's tracking transfers to hardware.

## Grounding (verified against this checkout, 2026-08-09)
- `dependencies/stella_config.yaml` (the sim config) shows the exact schema stella_vslam expects for
  `Camera:` — `fx, fy, cx, cy, k1, k2, p1, p2, k3, fps, cols, rows, color_order`. This maps directly
  from OpenCV's `cv2.calibrateCamera` output: `cameraMatrix` gives `fx, fy, cx, cy`; `distCoeffs` gives
  `k1, k2, p1, p2, k3` in that exact order for the standard 5-parameter model. No translation layer
  needed — the script below writes the YAML in this shape directly.
- **The "~960x720" real-Tello resolution in the original spec is an estimate, not a verified fact** —
  grepped the whole codebase for a hardcoded Tello frame size and found none. Don't calibrate against
  an assumed resolution: capture one frame first and read its actual `.shape` before running the
  checkerboard capture, and use that confirmed size for both the capture and the final YAML's
  `cols`/`rows`.
- **Corrected dependency (this revision):** the original spec's implicit path through B4's `rx_node`
  fix isn't needed. `tello_backend/test/tello_teleop.cpp`'s own header comment documents a working
  capture path already: `cv2`/OpenCV `VideoCapture` over FFMPEG directly on the raw H.264 UDP stream
  (port 11111) — no ROS2, no ctello backend, no FMU build required. B2 can use that same technique
  standalone and start **immediately**, fully in parallel with B4, not gated on it.

## Scope
- **In:**
  1. A small standalone Python capture script (below) using `cv2.VideoCapture` against the Tello's raw
     H.264 stream — confirms actual resolution, then saves 20-40 checkerboard frames varied in
     angle/distance/position in frame.
  2. A calibration script (below) running `cv2.calibrateCamera` over those frames, reporting
     reprojection error, and writing `dependencies/stella_config_tello.yaml` in the schema above.
  3. `fps` in the output YAML: measure it, don't assume 30 — read the Tello video stream's actual
     delivered frame rate during capture (count frames over a timed window) since real WiFi
     video throughput on this hardware may not hit nominal.
- **Out:** anything requiring flight. Anything touching `rx_node.cpp` or the FMU build (that's B4).

## Capture script (new — none of this tooling exists yet)
`scripts/tello/capture_calibration_frames.py`:
```python
#!/usr/bin/env python3
"""Grab checkerboard frames from a real Tello for B2 camera calibration.
Standalone -- no ROS2/FMU build needed. Connect to the Tello's WiFi first,
then: python3 capture_calibration_frames.py [out_dir] [board_cols] [board_rows]
Press SPACE to save a frame, ESC to quit. Aim for 20-40 frames, varied angle/distance."""
import sys, os, time
import cv2

TELLO_CMD_ADDR = ("192.168.10.1", 8889)
STREAM_URL = "udp://0.0.0.0:11111"

def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "calib_frames"
    board_cols = int(sys.argv[2]) if len(sys.argv) > 2 else 9
    board_rows = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    os.makedirs(out_dir, exist_ok=True)

    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(b"command", TELLO_CMD_ADDR)
    time.sleep(0.5)
    sock.sendto(b"streamon", TELLO_CMD_ADDR)
    time.sleep(2.0)

    cap = cv2.VideoCapture(STREAM_URL, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("ERROR: could not open Tello video stream -- check WiFi connection.")
        sys.exit(1)

    ok, frame = cap.read()
    if not ok:
        print("ERROR: stream opened but no frame read.")
        sys.exit(1)
    h, w = frame.shape[:2]
    print(f"CONFIRMED resolution: {w}x{h} -- use this for cols/rows below, not an assumed value.")

    saved = 0
    t_start = time.time()
    frame_count = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        frame_count += 1
        found, corners = cv2.findChessboardCorners(frame, (board_cols, board_rows))
        disp = frame.copy()
        if found:
            cv2.drawChessboardCorners(disp, (board_cols, board_rows), corners, found)
        cv2.putText(disp, f"saved={saved}  SPACE=save  ESC=quit", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Tello calibration capture", disp)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        if key == 32:
            path = os.path.join(out_dir, f"frame_{saved:03d}.png")
            cv2.imwrite(path, frame)
            print(f"saved {path} (checkerboard {'found' if found else 'NOT found'})")
            saved += 1

    elapsed = time.time() - t_start
    print(f"measured stream fps ~= {frame_count / elapsed:.1f} over {elapsed:.1f}s -- use this in the YAML, not an assumed 30.0")
    print(f"saved {saved} frames to {out_dir}/ (target 20-40)")
    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
```

## Calibration script (new)
`scripts/tello/calibrate_camera.py`:
```python
#!/usr/bin/env python3
"""Run OpenCV calibrateCamera over captured checkerboard frames and write
dependencies/stella_config_tello.yaml in the schema stella_vslam expects.
Usage: python3 calibrate_camera.py <frames_dir> <board_cols> <board_rows> <square_size_m> <measured_fps>"""
import sys, glob
import cv2
import numpy as np
import yaml

def main():
    frames_dir, board_cols, board_rows, square_size, fps = (
        sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
    )
    objp = np.zeros((board_rows * board_cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:board_cols, 0:board_rows].T.reshape(-1, 2) * square_size

    objpoints, imgpoints = [], []
    img_size = None
    files = sorted(glob.glob(f"{frames_dir}/*.png"))
    if len(files) < 10:
        print(f"WARNING: only {len(files)} frames -- 20-40 recommended for a stable calibration.")

    for f in files:
        img = cv2.imread(f)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_size = gray.shape[::-1]
        found, corners = cv2.findChessboardCorners(gray, (board_cols, board_rows))
        if not found:
            print(f"skip {f}: checkerboard not found")
            continue
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1),
            (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
        objpoints.append(objp)
        imgpoints.append(corners)

    print(f"using {len(objpoints)}/{len(files)} frames with a detected checkerboard")
    rms, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
        objpoints, imgpoints, img_size, None, None)

    print(f"reprojection RMS error: {rms:.4f} px (target < ~1.0 px)")
    fx, fy = camera_matrix[0, 0], camera_matrix[1, 1]
    cx, cy = camera_matrix[0, 2], camera_matrix[1, 2]
    k1, k2, p1, p2, k3 = dist_coeffs.ravel()[:5]

    out = {
        "Camera": {
            "name": "Tello_Real_Camera",
            "setup": "monocular",
            "model": "perspective",
            "fx": float(fx), "fy": float(fy), "cx": float(cx), "cy": float(cy),
            "k1": float(k1), "k2": float(k2), "p1": float(p1), "p2": float(p2), "k3": float(k3),
            "fps": fps,
            "cols": img_size[0], "rows": img_size[1],
            "color_order": "RGB",
        }
    }
    out_path = "dependencies/stella_config_tello.yaml"
    with open(out_path, "w") as fh:
        yaml.safe_dump(out, fh, default_flow_style=False, sort_keys=False)
    print(f"wrote {out_path}")
    if rms >= 1.0:
        print("WARNING: reprojection error >= 1.0 px -- recapture with more/better-varied frames before trusting this.")

if __name__ == "__main__":
    main()
```
(`FeatureExtractor:` and any other non-`Camera:` sections in `dependencies/stella_config.yaml` are
unrelated to calibration and should be copied over unchanged into the Tello variant by hand after this
script writes the `Camera:` block — B1 owns tuning those, not B2.)

## Tests to create
- **[AUTO]** assert reprojection error < ~1 px from the calibration script's own output (the script
  already warns above threshold; a test just asserts the script's exit/warning behavior on a known-bad
  fixture and known-good fixture).
- **[AUTO]** assert the written YAML parses and contains all required `Camera:` keys.
- **[HUMAN]** the capture itself is manual (checkerboard photography).

## Acceptance
A Tello-resolution (measured, not assumed) calibrated config with sub-pixel reprojection error,
loadable by stella, with `fps` set from a measured value.

## Change-impact (per `docs/code-guidelines.md`)
- **What this changes:** purely additive — new standalone scripts, one new config file. Nothing in the
  build or runtime path changes.
- **Breaks existing behavior:** no.
- **Tests that re-run as-is:** none affected (B1's sim config, `stella_config.yaml`, is untouched).
- **Tests that are new:** the two listed above.

## Agent notes
Operator ground task, ~30-60 min with tooling ready — the two scripts above are that tooling. Runs
fully in parallel with everything else, including B4 (corrected this revision — no longer gated on
`rx_node`'s fix).

## Revision log
- 2026-08-09: removed the false dependency on B4's `rx_node` fix (a standalone `cv2.VideoCapture`/FFMPEG
  path already exists as precedent in `tello_teleop.cpp` and needs no FMU/ROS2 build); flagged the
  ~960x720 resolution as an unverified estimate and added a measure-first step; measured `fps` instead
  of an assumed 30.0; wrote the two scripts that didn't exist before (capture + calibrate), matching the
  exact `Camera:` YAML schema confirmed from `dependencies/stella_config.yaml`; added change-impact
  section.
