#!/usr/bin/env python3
"""
Measure Tello positional drift from a fixed-camera video.

The Tello reports vgx=vgy=0 always -- it has no horizontal velocity feedback -- so drift
cannot be read from telemetry. This recovers it from video instead.

Method: track the drone, then use its known real width as the scale reference. For a pinhole
camera, apparent width in pixels falls off as 1/range, so a single tracked box gives full 3D:

    f = (frame_width / 2) / tan(hfov / 2)      focal length in pixels
    Z = f * W_real / w_px                      range from camera
    X = (u - cx) * Z / f                       lateral   (+ right)
    Y = -(v - cy) * Z / f                      vertical  (+ up)

Only the camera's horizontal FOV is needed. No ruler in shot, no calibration target.

Usage:
    ./measure_drift.py flight.mp4                      # drag a box round the drone, press ENTER
    ./measure_drift.py flight.mp4 --roi 640,360,80,40  # skip the GUI
    ./measure_drift.py flight.mp4 --hfov 78 --width-m 0.18 --csv drift.csv

Accuracy: X and Y are good. Z is the weak axis -- it depends on box width, which spinning props
smear. Treat Z as indicative. Mount the camera so the drift you care about runs ACROSS frame.
"""
import argparse
import math
import sys

import cv2
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Measure Tello drift from a fixed-camera video.")
    p.add_argument("video")
    p.add_argument("--hfov", type=float, default=65.0,
                   help="camera horizontal field of view, degrees (phones are ~65-78)")
    p.add_argument("--width-m", type=float, default=0.18,
                   help="drone width as seen by the camera, metres (0.18 = prop tip to prop tip)")
    p.add_argument("--roi", type=str, default=None, help="x,y,w,h of the drone in frame 1")
    p.add_argument("--csv", type=str, default=None, help="write per-frame track here")
    p.add_argument("--smooth", type=int, default=5, help="median window on box width, frames")
    p.add_argument("--use-depth", action="store_true",
                   help="include the depth axis in the headline number (noisy; off by default)")
    return p.parse_args()


def pick_roi(frame):
    """Let the operator drag a box round the drone. ENTER accepts, c cancels."""
    box = cv2.selectROI("drag a box round the drone, then ENTER", frame, showCrosshair=True)
    cv2.destroyAllWindows()
    if box[2] == 0 or box[3] == 0:
        sys.exit("no box selected")
    return box


def track(video, roi, smooth):
    """Run CSRT over the clip. Returns (times_s, centres_px, widths_px, frame_size)."""
    cap = cv2.VideoCapture(video)
    if not cap.isOpened():
        sys.exit(f"cannot open {video}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    ok, frame = cap.read()
    if not ok:
        sys.exit("empty video")
    h, w = frame.shape[:2]

    if roi is None:
        roi = pick_roi(frame)
    tracker = cv2.TrackerCSRT_create()
    tracker.init(frame, tuple(roi))

    times, centres, widths = [], [], []
    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        idx += 1
        found, box = tracker.update(frame)
        if not found:
            print(f"[warn] track lost at frame {idx} ({idx / fps:.1f}s) -- truncating here",
                  file=sys.stderr)
            break
        x, y, bw, bh = box
        times.append(idx / fps)
        centres.append((x + bw / 2.0, y + bh / 2.0))
        widths.append(bw)
    cap.release()

    if len(widths) < 2:
        sys.exit("track too short to measure anything")
    # Median-filter the width: spinning props make it jitter, and it feeds the range estimate.
    wid = np.asarray(widths, dtype=float)
    if smooth > 1:
        pad = smooth // 2
        padded = np.pad(wid, pad, mode="edge")
        wid = np.asarray([np.median(padded[i:i + smooth]) for i in range(len(wid))])
    return np.asarray(times), np.asarray(centres), wid, (w, h)


def to_metres(centres, widths, frame_size, hfov_deg, width_m):
    """Pinhole back-projection to camera-frame XYZ in metres.

    X and Y are scaled by a FIXED reference range taken from the opening frames, not by the
    per-frame range. Range comes from box width, and a tracker's box width jitters by a few
    percent even on a stationary target; feeding that into X and Y would inject noise into the
    two axes that are otherwise measured well. The cost is a small scale error if the drone
    changes range a lot, which is the trade we want -- see --use-depth."""
    fw, fh = frame_size
    f = (fw / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    cx, cy = fw / 2.0, fh / 2.0
    z    = f * width_m / widths
    zref = float(np.median(z[:min(10, len(z))]))
    x = (centres[:, 0] - cx) * zref / f
    y = -(centres[:, 1] - cy) * zref / f
    return np.column_stack([x, y, z]), f, zref


def report(times, pos, f, zref, use_depth, csv_path):
    rel = pos - pos[0]
    # Default headline is the image plane (X,Y): both are measured well. Depth rides on box
    # width and is an order of magnitude noisier, so it is opt-in.
    axes  = [0, 1, 2] if use_depth else [0, 1]
    total = np.linalg.norm(rel[:, axes], axis=1)
    duration = times[-1] - times[0]

    zspread = float(np.percentile(pos[:, 2], 90) - np.percentile(pos[:, 2], 10))
    # Net bearing of the horizontal drift, degrees clockwise from "straight away from camera".
    bearing = math.degrees(math.atan2(rel[-1, 0], rel[-1, 2])) if use_depth else 0.0
    # Path length, so a drone that wanders and returns is not scored as stable.
    path = float(np.sum(np.linalg.norm(np.diff(rel[:, axes], axis=0), axis=1)))

    print(f"\n  duration            {duration:6.1f} s   ({len(times)} frames)")
    print(f"  focal length        {f:6.1f} px    reference range {zref:.2f} m")
    print(f"  measured over       {'X,Y,Z' if use_depth else 'X,Y (image plane)'}")
    print(f"\n  net displacement    {total[-1] * 100:6.1f} cm")
    print(f"    lateral  (X)      {rel[-1, 0] * 100:+6.1f} cm")
    print(f"    vertical (Y)      {rel[-1, 1] * 100:+6.1f} cm")
    print(f"    depth    (Z)      {rel[-1, 2] * 100:+6.1f} cm   "
          f"(weak axis, +/-{zspread * 100:.0f} cm spread{'' if use_depth else ', excluded'})")
    if use_depth:
        print(f"  horizontal bearing  {bearing:+6.1f} deg from camera axis")
    print(f"\n  peak displacement   {total.max() * 100:6.1f} cm")
    print(f"  path travelled      {path * 100:6.1f} cm")
    print(f"  mean drift rate     {total[-1] / duration * 100:6.1f} cm/s")
    print(f"  peak drift rate     {np.max(np.abs(np.gradient(total, times))) * 100:6.1f} cm/s")

    if path > 2.5 * max(total[-1], 1e-6):
        print("\n  NOTE: path is much longer than net displacement -- it wandered rather than")
        print("        sliding one way. Report the path length, not just the endpoint.")

    if csv_path:
        with open(csv_path, "w") as fh:
            fh.write("t_s,x_m,y_m,z_m,displacement_m\n")
            for t, (px, py, pz), d in zip(times, rel, total):
                fh.write(f"{t:.3f},{px:.4f},{py:.4f},{pz:.4f},{d:.4f}\n")
        print(f"\n  per-frame track -> {csv_path}")


def main():
    a = parse_args()
    roi = tuple(int(v) for v in a.roi.split(",")) if a.roi else None
    times, centres, widths, size = track(a.video, roi, a.smooth)
    pos, f, zref = to_metres(centres, widths, size, a.hfov, a.width_m)
    report(times, pos, f, zref, a.use_depth, a.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
