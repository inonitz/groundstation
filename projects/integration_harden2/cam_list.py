#!/usr/bin/env python3
"""List the cameras the host has, whether this container can open each, and what they deliver.
Used by preflight.sh and status.sh so the right WEBCAM_DEV index is a read, not a guess (2026-09-08).
Each UVC camera shows two nodes; only the capture one opens and gives frames. Brightness < 8 = black (lid shut / covered)."""
import glob
import os
import stat

import cv2


def _camera_name(sys_path):
    """Read the v4l2 device name. `with` closes the handle, so it never leaks."""
    with open(f"{sys_path}/name") as f:
        return f.read().strip()


def _probe(index):
    """Open the camera and describe what it delivers, or why it does not open."""
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        return "cannot open (metadata node, or another process holds it)"
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(3, 1280)
    cap.set(4, 720)
    ok, frame = cap.read()
    if not ok:
        cap.release()
        return "opens, no frames (metadata node or busy)"
    brightness = float(frame.mean())
    fps = cap.get(5)
    cap.release()
    black = "  <-- BLACK" if brightness < 8 else ""
    return f"CAPTURE {frame.shape[1]}x{frame.shape[0]} @ {fps:.0f} fps, brightness {brightness:.0f}{black}"


def main():
    cv2.setLogLevel(0)
    chosen = os.environ.get("WEBCAM_DEV", "0")
    rows = []
    for sys_path in sorted(glob.glob("/sys/class/video4linux/video*"),
                           key=lambda p: int(p.rsplit("video", 1)[1])):
        index = int(sys_path.rsplit("video", 1)[1])
        name = _camera_name(sys_path)
        node = f"/dev/video{index}"
        has_node = os.path.exists(node) and stat.S_ISCHR(os.stat(node).st_mode)
        state = _probe(index) if has_node else "no /dev node in the container (up.sh creates it)"
        rows.append((index, name, state))
    for index, name, state in rows:
        tag = " (laptop lid camera)" if "ASUS" in name else ""
        selected = "   <== selected" if str(index) == chosen else ""
        print(f"  WEBCAM_DEV={index}  {name}{tag}: {state}{selected}")
    if not rows:
        print("  no video4linux devices on the host")


if __name__ == "__main__":
    main()
