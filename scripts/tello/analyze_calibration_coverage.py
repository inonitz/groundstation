#!/usr/bin/env python3
"""Diagnose what a set of captured checkerboard frames is missing.

Low reprojection RMS does not prove a good calibration -- the distortion estimate comes
from the image edges, so a board kept near the centre scores well yet calibrates badly.
This reports where the board actually landed (image regions, edge reach) and how it was
posed (tilt, distance), then names the gaps to fill on the next capture burst.

Usage: python3 analyze_calibration_coverage.py <frames_dir> <board_cols> <board_rows> <square_m>"""
import sys, glob, math
import cv2, numpy as np

def main():
    d, cols, rows, sq = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
    objp = np.zeros((rows*cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * sq

    files = sorted(glob.glob(f"{d}/*.png"))
    imgpoints, size = [], None
    for f in files:
        g = cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2GRAY)
        size = g.shape[::-1]
        ok, c = cv2.findChessboardCornersSB(g, (cols, rows))
        if ok:
            imgpoints.append(c)
    W, H = size
    n = len(imgpoints)
    print(f"{n}/{len(files)} frames with a detected board, image {W}x{H}\n")

    _, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        [objp]*n, imgpoints, size, None, None)

    # Image-space coverage on a 4x3 grid + outer-edge reach.
    GX, GY = 4, 3
    grid = np.zeros((GY, GX), int)
    edges = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    EDGE = 0.08  # within 8% of a border counts as reaching that edge
    tilts, dists = [], []
    for c, rvec, tvec in zip(imgpoints, rvecs, tvecs):
        p = c.reshape(-1, 2)
        xs, ys = p[:, 0]/W, p[:, 1]/H
        # mark every grid cell the board's bbox spans
        cx0, cx1 = int(xs.min()*GX), int(min(xs.max()*GX, GX-1e-9))
        cy0, cy1 = int(ys.min()*GY), int(min(ys.max()*GY, GY-1e-9))
        grid[cy0:cy1+1, cx0:cx1+1] += 1
        if xs.min() < EDGE: edges["left"] += 1
        if xs.max() > 1-EDGE: edges["right"] += 1
        if ys.min() < EDGE: edges["top"] += 1
        if ys.max() > 1-EDGE: edges["bottom"] += 1
        R, _ = cv2.Rodrigues(rvec)
        n_cam = R @ np.array([0, 0, 1.0])
        tilts.append(math.degrees(math.acos(min(1.0, abs(n_cam[2])))))
        dists.append(float(np.linalg.norm(tvec)))

    print("image coverage (frames whose board touches each cell, 4x3 over the frame):")
    for r in range(GY):
        print("  " + " ".join(f"{grid[r,c]:3d}" for c in range(GX)))
    empty = [(r, c) for r in range(GY) for c in range(GX) if grid[r, c] == 0]
    print(f"  empty cells: {empty if empty else 'none'}\n")

    print(f"outer-edge reach (board within {int(EDGE*100)}% of that border):")
    for k, v in edges.items():
        flag = "  <-- THIN" if v < 3 else ""
        print(f"  {k:6s}: {v} frames{flag}")
    print()

    t = np.array(tilts)
    print("board tilt vs frontal (deg):")
    print(f"  <15 (too flat): {(t<15).sum()}   15-40 (good): {((t>=15)&(t<=40)).sum()}   >40: {(t>40).sum()}")
    print(f"  range {t.min():.0f}-{t.max():.0f}, mean {t.mean():.0f}\n")
    ds = np.array(dists)
    print(f"board distance (m): range {ds.min():.2f}-{ds.max():.2f}, mean {ds.mean():.2f}\n")

    print("VERDICT / what to add:")
    if empty:
        print(f"  - fill empty image regions {empty} -- push the board into those cells.")
    for k, v in edges.items():
        if v < 3:
            print(f"  - more frames reaching the {k} edge (only {v}); distortion lives there.")
    if (t < 15).sum() > n*0.4:
        print("  - too many near-flat frames; tilt the board 20-40 deg on most shots.")
    if (t >= 15).sum() < 6:
        print("  - not enough tilted frames; add strong-tilt shots for the focal estimate.")
    if ds.max()-ds.min() < 0.4:
        print("  - distance range narrow; add both close and far frames.")
    if not empty and all(v >= 3 for v in edges.values()) and (t >= 15).sum() >= 6:
        print("  - coverage is solid; current calibration is well-supported.")

if __name__ == "__main__":
    main()
