#!/usr/bin/env python3
"""video_watchdog -- camera/stream stalls now NOTIFY and AUTO-RECOVER instead of silently hanging.
Subscribes to camera/stream. If frames stop for STALL_SEC, it prints a loud banner and respawns the
gst tmux pane (fresh tcpclientsrc connect to the phone), retrying every RETRY_SEC until video returns,
then announces RECOVERED. Meant to run as its own window alongside the app."""
import os, time, subprocess
import rclpy
from sensor_msgs.msg import Image

STALL_SEC = float(os.environ.get("WATCHDOG_STALL_SEC", "6"))
RETRY_SEC = float(os.environ.get("WATCHDOG_RETRY_SEC", "15"))
SESSION   = os.environ.get("SCENE_TMUX_SESSION", "mvd")
BIN       = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "build", "release", "shared", "dji", "bin"))

def gateway():
    try:
        for l in open("/proc/net/route").readlines()[1:]:
            p = l.split()
            if p[1] == "00000000":
                return ".".join(str(int(p[2][i:i+2], 16)) for i in (6, 4, 2, 0))
    except Exception:
        pass
    return None

def respawn_gst():
    ip = gateway()
    cmd = (f"source /opt/ros/jazzy/setup.bash && export LD_LIBRARY_PATH={BIN}:$LD_LIBRARY_PATH && "
           f"{BIN}/llm_to_action_gstreamer_rx --dji {ip}; echo [gst exited]; exec bash")
    subprocess.run(["tmux", "respawn-pane", "-k", "-t", f"{SESSION}:gst", "bash", "-c", cmd],
                   stderr=subprocess.DEVNULL)
    return ip

rclpy.init()
node = rclpy.create_node("video_watchdog")
S = {"last": time.time(), "frames": 0}
node.create_subscription(Image, "camera/stream", lambda m: S.update(last=time.time(), frames=S["frames"] + 1), 10)

print(f"[watchdog] monitoring camera/stream | stall>{STALL_SEC}s -> reconnect | retry every {RETRY_SEC}s", flush=True)
stalled = False
last_respawn = 0.0
last_beat = 0.0
while rclpy.ok():
    rclpy.spin_once(node, timeout_sec=0.2)
    now = time.time()
    gap = now - S["last"]
    if gap > STALL_SEC:
        if not stalled:
            stalled = True
            print(f"\n[watchdog] ===== VIDEO STALLED: no frames for {gap:.0f}s =====", flush=True)
        if now - last_respawn >= RETRY_SEC:
            ip = respawn_gst()
            last_respawn = now
            print(f"[watchdog] reconnecting gst --dji {ip} (retry). If this repeats, the PHONE stopped "
                  f"streaming -> foreground the app / check the drone camera feed.", flush=True)
    else:
        if stalled:
            stalled = False
            print(f"[watchdog] ===== VIDEO RECOVERED ({S['frames']} frames total) =====", flush=True)
    if now - last_beat >= 10:
        last_beat = now
        print(f"[watchdog] {'STALLED' if stalled else 'OK'} | {S['frames']} frames | last {gap:.1f}s ago", flush=True)
