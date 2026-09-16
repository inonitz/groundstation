#!/usr/bin/env python3
"""List the cameras the host has, whether this container can open each, and what they deliver.
Used by preflight.sh and status.sh so the right WEBCAM_DEV index is a read, not a guess (2026-09-08).
Each UVC camera shows two nodes; only the capture one opens and gives frames. Brightness < 8 = black (lid shut / covered)."""
import glob, os, stat, sys
def main():
    try:
        import cv2; cv2.setLogLevel(0)
    except Exception:
        cv2 = None
    chosen = os.environ.get("WEBCAM_DEV", "0"); rows = []
    for d in sorted(glob.glob("/sys/class/video4linux/video*"), key=lambda p: int(p.rsplit("video", 1)[1])):
        n = int(d.rsplit("video", 1)[1]); name = open(f"{d}/name").read().strip(); node = f"/dev/video{n}"
        has = os.path.exists(node) and stat.S_ISCHR(os.stat(node).st_mode)
        state = "no /dev node in the container (up.sh creates it)" if not has else "node present"
        if has and cv2 is not None:
            cap = cv2.VideoCapture(n)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")); cap.set(3, 1280); cap.set(4, 720)
                ok, fr = cap.read()
                if ok:
                    m = float(fr.mean())
                    state = f"CAPTURE {fr.shape[1]}x{fr.shape[0]} @ {cap.get(5):.0f} fps, brightness {m:.0f}" + ("  <-- BLACK" if m < 8 else "")
                else:
                    state = "opens, no frames (metadata node or busy)"
            else:
                state = "cannot open (metadata node, or another process holds it)"
            cap.release()
        rows.append((n, name, state))
    for n, name, state in rows:
        tag = " (laptop lid camera)" if "ASUS" in name else ""
        print(f"  WEBCAM_DEV={n}  {name}{tag}: {state}" + ("   <== selected" if str(n) == chosen else ""))
    if not rows: print("  no video4linux devices on the host")
if __name__ == "__main__":
    main()
