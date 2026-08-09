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
