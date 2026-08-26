#!/usr/bin/env python3
"""
S1 TEXT-API CONTROL TEST -- exercises the plaintext SDK the way the demo would.

Enters SDK mode, prints version, reads battery/attitude, and (only with --move)
does ONE small, bounded gimbal nudge. Chassis motion is OFF unless you pass
--chassis, because a ground robot on a table will drive off it.

This is the "text API" path: raw TCP, ASCII commands ending in `;`. No pip package.
If this works, integration/ can drive the S1 the same way dji_wire.py drives the drone.

Usage:
  python3 s1_text.py                      # safe: SDK mode + queries only, no motion
  python3 s1_text.py --move               # + a tiny gimbal move (robot secured / off-table)
  python3 s1_text.py --chassis            # + a tiny chassis nudge (ONLY with wheels off ground)
  python3 s1_text.py <ip> [flags]
"""
import socket, sys, time

CTRL_PORT = 40923
args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}
ip = args[0] if args else "192.168.2.1"

def cmd(sock, c, t=3.0, quiet=False):
    sock.settimeout(t)
    sock.sendall((c.strip() + ";").encode())
    try:
        r = sock.recv(2048).decode(errors="replace").strip()
    except socket.timeout:
        r = "<timeout>"
    if not quiet:
        print(f"  {c:38s} -> {r!r}")
    return r

print(f"[text] connect {ip}:{CTRL_PORT}")
s = socket.create_connection((ip, CTRL_PORT), timeout=5)
with s:
    if not cmd(s, "command").startswith("ok"):
        print("[text] SDK mode refused -> robot is locked or busy. Stop here."); sys.exit(2)
    cmd(s, "version")
    cmd(s, "robot mode chassis_lead")          # gimbal follows chassis; standard demo mode
    cmd(s, "chassis push position on pfreq 1")  # start position telemetry (optional)
    cmd(s, "gimbal recenter")
    print("[text] queries:")
    cmd(s, "chassis position ?")
    cmd(s, "chassis attitude ?")
    cmd(s, "gimbal attitude ?")

    if "--move" in flags:
        print("[text] gimbal nudge (secured?):")
        cmd(s, "gimbal moveto p 15 y 0 vp 30 vy 30"); time.sleep(1.5)
        cmd(s, "gimbal moveto p 0 y 0 vp 30 vy 30");  time.sleep(1.5)

    if "--chassis" in flags:
        print("[text] chassis nudge -- WHEELS OFF GROUND ONLY:")
        cmd(s, "chassis move x 0.1 y 0 z 0");  time.sleep(2.0)
        cmd(s, "chassis move x -0.1 y 0 z 0"); time.sleep(2.0)

    cmd(s, "quit")
print("[text] done.")
