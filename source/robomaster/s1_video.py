#!/usr/bin/env python3
"""
S1 VIDEO-IN PROBE -- the demo-relevant path: get the S1 camera into our stack.

Enters SDK mode on 40923, sends `stream on;`, then reads the raw H.264 elementary
stream off TCP 40921 and writes it to a file. Confirms bytes/frames actually flow.
This is what integration/scene_omdet.py would consume (same role as the drone's feed).

Stdlib only. Play the result with:  ffplay -f h264 out.h264
Or feed live into GStreamer:  gst-launch-1.0 tcpclientsrc host=192.168.2.1 port=40921 ! h264parse ! ...

Usage:
  python3 s1_video.py                 # 8 s capture to out.h264 from 192.168.2.1
  python3 s1_video.py <ip> <seconds> <outfile>
"""
import socket, sys, time

CTRL_PORT, VIDEO_PORT = 40923, 40921
ip   = sys.argv[1] if len(sys.argv) > 1 else "192.168.2.1"
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
out  = sys.argv[3] if len(sys.argv) > 3 else "out.h264"

def cmd(sock, c, t=3.0):
    sock.settimeout(t); sock.sendall((c.strip()+";").encode())
    try: return sock.recv(1024).decode(errors="replace").strip()
    except socket.timeout: return "<timeout>"

print(f"[video] control connect {ip}:{CTRL_PORT}")
ctrl = socket.create_connection((ip, CTRL_PORT), timeout=5)
if not cmd(ctrl, "command").startswith("ok"):
    print("[video] SDK refused -> locked/busy. Stop."); sys.exit(2)
print(f"[video] stream on; -> {cmd(ctrl, 'stream on')!r}")

print(f"[video] pulling H.264 from {ip}:{VIDEO_PORT} for {secs:.0f}s -> {out}")
total = 0
try:
    vid = socket.create_connection((ip, VIDEO_PORT), timeout=5)
except Exception as e:
    print(f"[video] VIDEO PORT CONNECT FAILED: {e} -> stream port not open."); cmd(ctrl,"stream off"); cmd(ctrl,"quit"); sys.exit(3)

vid.settimeout(2.0)
t0 = time.time()
with open(out, "wb") as f:
    while time.time() - t0 < secs:
        try:
            b = vid.recv(65536)
        except socket.timeout:
            print("[video] (no bytes in 2s window)"); continue
        if not b:
            print("[video] stream closed by robot"); break
        f.write(b); total += len(b)
vid.close()
cmd(ctrl, "stream off"); cmd(ctrl, "quit"); ctrl.close()

print(f"[video] wrote {total/1024:.0f} KiB to {out}")
print("[video] VERDICT:", "*** VIDEO FLOWS ***  play: ffplay -f h264 " + out if total > 0
      else "NO DATA -> stream port open but empty; check `stream on;` reply + firmware.")
