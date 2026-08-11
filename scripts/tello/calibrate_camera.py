#!/usr/bin/env python3
"""Run OpenCV calibrateCamera over captured checkerboard frames and write
config/stella_config_tello.yaml in the schema stella_vslam expects.
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
        # SB is the sector-based detector. It returns subpixel corners directly, so it needs
        # no cornerSubPix pass, and it does not blow up on frames where the board is absent
        # or partly occluded -- the classic detector took ~50s on such a frame at 960x720.
        found, corners = cv2.findChessboardCornersSB(gray, (board_cols, board_rows))
        if not found:
            print(f"skip {f}: checkerboard not found")
            continue
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
            # BGR, not RGB: rx_node's pipeline ends in `video/x-raw, format=BGR`, and the
            # sim config declares BGR for the same reason. The frames stella sees are BGR.
            "color_order": "BGR",
        }
    }
    out_path = "config/stella_config_tello.yaml"
    with open(out_path, "w") as fh:
        yaml.safe_dump(out, fh, default_flow_style=False, sort_keys=False)
    print(f"wrote {out_path}")
    if rms >= 1.0:
        print("WARNING: reprojection error >= 1.0 px -- recapture with more/better-varied frames before trusting this.")

if __name__ == "__main__":
    main()
