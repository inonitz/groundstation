#!/usr/bin/env python3
"""List the cameras the host has, whether this container can open each, and what they
deliver, so the right WEBCAM_DEV index is a read, not a guess (2026-09-08). Each UVC
camera shows two nodes; only the capture one opens and gives frames. Brightness < 8 =
black (lid shut / covered).

    python3 video/cam_list.py              every camera (run.sh status)
    python3 video/cam_list.py --selected   only WEBCAM_DEV (run.sh preflight; owner P1 a:
                                           opening every camera took 2.1 s of 2.2 s)"""
import glob
import os
import stat
import sys
import time

import cv2

# run as a script by run.sh: the harden2 root must be importable for config
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config  # noqa: E402


# ---- read one camera ----

def _video_index(sys_path):
    """/sys/class/video4linux/video12 -> 12."""
    return int(sys_path.rsplit("video", 1)[1])


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
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_W)       # what the app asks for
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_H)
    ok, frame = cap.read()
    if not ok:
        cap.release()
        return "opens, no frames (metadata node or busy)"

    brightness = float(frame.mean())
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    black = "  <-- BLACK" if brightness < 8 else ""
    return (
        f"CAPTURE {frame.shape[1]}x{frame.shape[0]} @ {fps:.0f} fps, "
        f"brightness {brightness:.0f}{black}"
    )


def _describe(index):
    """The camera's state, or why this container cannot see it."""
    node = f"/dev/video{index}"
    has_node = os.path.exists(node) and stat.S_ISCHR(os.stat(node).st_mode)

    if not has_node:
        return "no /dev node in the container (run.sh creates it)"
    return _probe(index)


# ---- the selected camera, or every camera ----

def show_selected():
    """One line for WEBCAM_DEV: its state; "CAPTURE" in it means it gives frames. A
    camera that gives no frame is read once more after CAMERA_CHECK_RETRY_SECONDS: one
    just released by a stopped run can be busy for a moment (owner O3 a, 2026-09-29)."""
    index = config.WEBCAM_DEVICE_INDEX
    state = ""
    cv2.setLogLevel(0)

    state = _describe(index)
    if "CAPTURE" not in state:
        time.sleep(config.CAMERA_CHECK_RETRY_SECONDS)
        state = _describe(index)
    print(f"  WEBCAM_DEV={index}: {state}")
    return


def main():
    if sys.argv[1:] == ["--selected"]:
        show_selected()
        return
    show_all()
    return


def show_all():
    chosen = str(config.WEBCAM_DEVICE_INDEX)
    rows = []
    paths = []
    index = 0
    name = ""
    state = ""
    tag = ""
    selected = ""

    cv2.setLogLevel(0)
    paths = sorted(glob.glob("/sys/class/video4linux/video*"), key=_video_index)
    for sys_path in paths:
        index = _video_index(sys_path)
        name = _camera_name(sys_path)
        state = _describe(index)
        rows.append((index, name, state))

    for index, name, state in rows:
        tag = " (laptop lid camera)" if "ASUS" in name else ""
        selected = "   <== selected" if str(index) == chosen else ""
        print(f"  WEBCAM_DEV={index}  {name}{tag}: {state}{selected}")
    if not rows:
        print("  no video4linux devices on the host")
    return


if __name__ == "__main__":
    main()
