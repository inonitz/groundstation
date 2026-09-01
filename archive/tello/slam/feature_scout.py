#!/usr/bin/env python3
"""
Venue pre-screen: will stella_vslam / the Tello VPS track on this surface?

Two modes:

  --live   Walk around HANDHELD with the Tello and watch it in real time. Connects to
           the Tello camera, runs stella's OWN ORB detector on every frame, and overlays
           the feature points + a live coverage%/verdict. Point it at glass, white walls,
           the stage screen, the mats -- and SEE where SLAM will choke, before you fly.

  (images) Give it photos and it prints a per-image report + a go/no-go. The floor shot
           decides it -- that is what the VPS sees and the surface that co-fails both
           the VPS and SLAM.

The honest caveat either way: what you see is an OPTIMISTIC ceiling. The Tello stream is
960x720 with motion blur; a marginal read here is a "no" in flight.

Usage:
    ./feature_scout.py --live                         # handheld, live overlay
    ./feature_scout.py --floor floor.jpg --forward *.jpg   # from photos
"""
import argparse
import glob
import os
import re
import socket
import sys
import time

import cv2
import numpy as np


DEFAULT_NUM_KEYPOINTS = 2500
DEFAULT_FAST_THRESHOLD = 10
CONFIG_PATH = os.environ.get(
    "STELLA_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "stella_config_tello.yaml"),
)

GRID = 8
CELL_MIN_FEATURES = 5
GOOD_COVERAGE = 0.75
MARGINAL_COVERAGE = 0.55
MIN_LAPLACIAN = 200.0
MAX_GLARE_FRAC = 0.12

TELLO_IP = "192.168.10.1"
TELLO_CMD_PORT = 8889
TELLO_VIDEO_URL = "udp://0.0.0.0:11111"


def load_detector_params():
    """Read num_keypoints + FAST threshold from the stella config; fall back to defaults."""
    nkp, fast = DEFAULT_NUM_KEYPOINTS, DEFAULT_FAST_THRESHOLD
    try:
        with open(CONFIG_PATH) as fh:
            text = fh.read()
        m = re.search(r"num_keypoints:\s*(\d+)", text)
        if m:
            nkp = int(m.group(1))
        m = re.search(r"ini_fast_threshold:\s*(\d+)", text)
        if m:
            fast = int(m.group(1))
    except OSError:
        pass
    return nkp, fast


def orb_grid(gray, orb):
    """Detect ORB and bin into an 8x8 coverage grid. Returns (keypoints, grid, coverage)."""
    h, w = gray.shape[:2]
    kp = orb.detect(gray, None)
    grid = np.zeros((GRID, GRID), dtype=int)
    for k in kp:
        gx = min(GRID - 1, int(k.pt[0] / w * GRID))
        gy = min(GRID - 1, int(k.pt[1] / h * GRID))
        grid[gy, gx] += 1
    coverage = int((grid >= CELL_MIN_FEATURES).sum()) / (GRID * GRID)
    return kp, grid, coverage


def verdict_from(coverage, laplacian, glare):
    reasons = []
    if coverage < MARGINAL_COVERAGE:
        reasons.append(f"coverage {coverage*100:.0f}%")
    if laplacian < MIN_LAPLACIAN:
        reasons.append(f"low texture (lap {laplacian:.0f})")
    if glare > MAX_GLARE_FRAC:
        reasons.append(f"glare {glare*100:.0f}%")
    if reasons:
        return "POOR", reasons
    if coverage < GOOD_COVERAGE:
        return "MARGINAL", [f"coverage {coverage*100:.0f}%"]
    return "GOOD", []


# ----------------------------- live handheld mode -----------------------------

def tello_stream_on():
    """Best-effort: put the Tello in SDK mode and start its video. Raw UDP so this tool
    needs no ctello. Returns the socket (kept open) or None if the send failed."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        sock.bind(("", 0))
        for cmd in ("command", "streamon"):
            sock.sendto(cmd.encode(), (TELLO_IP, TELLO_CMD_PORT))
            try:
                sock.recvfrom(1024)   # drain the "ok"; ignore if none
            except socket.timeout:
                pass
            time.sleep(0.5)
        return sock
    except OSError as e:
        print(f"[warn] could not send streamon ({e}); is the Tello WiFi joined?", file=sys.stderr)
        return None


def draw_overlay(frame, kp, grid, coverage, lap, glare):
    h, w = frame.shape[:2]
    cv2.drawKeypoints(frame, kp, frame, color=(0, 255, 0), flags=0)
    # shade the feature-starved cells so choke zones are obvious
    cw, ch = w // GRID, h // GRID
    for gy in range(GRID):
        for gx in range(GRID):
            if grid[gy, gx] < CELL_MIN_FEATURES:
                x0, y0 = gx * cw, gy * ch
                sub = frame[y0:y0 + ch, x0:x0 + cw]
                sub[:] = (sub * 0.45).astype(np.uint8)   # darken dead cells
    v, _ = verdict_from(coverage, lap, glare)
    color = {"GOOD": (0, 220, 0), "MARGINAL": (0, 200, 220), "POOR": (0, 0, 230)}[v]
    cv2.rectangle(frame, (0, 0), (w, 34), (0, 0, 0), -1)
    cv2.putText(frame, f"{v}  coverage {coverage*100:2.0f}%  feats {len(kp)}  "
                       f"lap {lap:4.0f}  glare {glare*100:2.0f}%",
                (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return frame


def live_screen(args):
    nkp, fast = load_detector_params()
    orb = cv2.ORB_create(nfeatures=nkp, fastThreshold=fast)
    print(f"stella detector: {nkp} keypoints, FAST {fast}")
    print("Connecting to the Tello camera (join its WiFi first)...")
    sock = tello_stream_on()
    cap = cv2.VideoCapture(TELLO_VIDEO_URL, cv2.CAP_FFMPEG)
    t0 = time.time()
    while not cap.isOpened() and time.time() - t0 < 8.0:
        time.sleep(0.3)
        cap.open(TELLO_VIDEO_URL, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("[ERROR] no video from the Tello. WiFi joined? streamon acked?", file=sys.stderr)
        return 1
    print("Live. Point it at surfaces; darkened cells = SLAM choke zones. 'q' or Esc to quit.")
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        kp, grid, coverage = orb_grid(gray, orb)
        lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        glare = float((gray > 245).mean())
        cv2.imshow("venue pre-screen (live)", draw_overlay(frame, kp, grid, coverage, lap, glare))
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
            break
    cap.release()
    cv2.destroyAllWindows()
    if sock:
        try:
            sock.sendto(b"streamoff", (TELLO_IP, TELLO_CMD_PORT))
        except OSError:
            pass
        sock.close()
    return 0


# ------------------------------- image mode -----------------------------------

def analyse(path, orb):
    img = cv2.imread(path)
    if img is None:
        print(f"[warn] cannot decode {path}", file=sys.stderr)
        return None
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    kp, grid, coverage = orb_grid(gray, orb)
    return {
        "path": path, "w": w, "h": h,
        "features": len(kp), "coverage": coverage,
        "dead_cells": GRID * GRID - int((grid >= CELL_MIN_FEATURES).sum()),
        "grid": grid,
        "laplacian": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "glare": float((gray > 245).mean()),
        "brightness": float(gray.mean()),
        "contrast": float(gray.std()),
    }


def print_report(m):
    v, reasons = verdict_from(m["coverage"], m["laplacian"], m["glare"])
    print(f"\n=== {os.path.basename(m['path'])} ===  [{v}]")
    print(f"  resolution   {m['w']}x{m['h']}  (a still over-reports vs the 960x720 stream)")
    print(f"  ORB features {m['features']}   coverage {m['coverage']*100:.0f}%  ({m['dead_cells']} dead cells)")
    print(f"  texture      laplacian {m['laplacian']:.0f}   glare {m['glare']*100:.1f}%")
    if reasons:
        print(f"  why          {'; '.join(reasons)}")
    print("  feature map  (. = starved cell -> VPS/SLAM blind spot):")
    for row in m["grid"]:
        print("    " + " ".join(f"{c:3d}" if c >= CELL_MIN_FEATURES else "  ." for c in row))
    return v


def is_floor(path):
    n = os.path.basename(path).lower()
    return "floor" in n or "down" in n


def image_mode(paths, floor_hint):
    nkp, fast = load_detector_params()
    orb = cv2.ORB_create(nfeatures=nkp, fastThreshold=fast)
    print(f"stella detector: {nkp} keypoints, FAST {fast}  (from {os.path.basename(CONFIG_PATH)})")
    floor_paths = set(floor_hint) | {p for p in paths if is_floor(p)}
    verdicts = []
    for p in paths:
        m = analyse(p, orb)
        if m is None:
            continue
        verdicts.append((p, print_report(m), p in floor_paths))

    print("\n=== SUMMARY ===")
    for p, v, isf in verdicts:
        print(f"  {'[floor] ' if isf else '        '}{v:8s} {os.path.basename(p)}")
    floor_v = [v for _, v, isf in verdicts if isf]
    if not floor_v:
        print("\n  NO FLOOR SHOT. Screen a straight-down floor photo -- that is what the VPS sees.")
    elif "POOR" in floor_v or "MARGINAL" in floor_v:
        print("\n  VERDICT: floor not clearly good -> do NOT bet the live demo on the Tello; run SITL.")
    else:
        print("\n  VERDICT: floor GOOD -> a Tello attempt is reasonable; confirm live with C1.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Pre-screen a venue surface for stella/VPS trackability.")
    ap.add_argument("images", nargs="*", help="image paths or globs (image mode)")
    ap.add_argument("--floor", action="append", default=[], help="a downward/floor shot")
    ap.add_argument("--forward", action="append", default=[], help="a forward shot")
    ap.add_argument("--live", action="store_true", help="handheld live overlay off the Tello camera")
    args = ap.parse_args()

    if args.live:
        return live_screen(args)

    paths = []
    for pat in args.images + args.floor + args.forward:
        paths.extend(sorted(glob.glob(pat)) or [pat])
    if not paths:
        sys.exit("give images, or use --live. e.g. ./feature_scout.py --live")
    return image_mode(paths, args.floor)


if __name__ == "__main__":
    sys.exit(main())
