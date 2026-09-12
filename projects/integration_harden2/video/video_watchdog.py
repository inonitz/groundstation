#!/usr/bin/env python3
"""video_watchdog -- video stalls now NOTIFY and AUTO-RECOVER instead of silently hanging.
Subscribes to camera_stream.TOPIC via the shared FrameCounter. If frames stop for STALL_SEC, it prints a loud banner and respawns the
gst tmux pane (fresh tcpclientsrc connect to the phone), retrying every RETRY_SEC until video returns,
then announces RECOVERED. Meant to run as its own window alongside the app.

Run as a MODULE from the integration_harden root:
    cd /root/groundstation/projects/integration_harden && python3 -m video.video_watchdog
"""
import os, time, subprocess

import config
from video.camera_stream import FrameCounter, TOPIC   # one home for the topic + the teardown fix

STALL_SEC = float(os.environ.get("WATCHDOG_STALL_SEC", "6"))
RETRY_SEC = float(os.environ.get("WATCHDOG_RETRY_SEC", "15"))
SESSION   = os.environ.get("SCENE_TMUX_SESSION", "mvd")
BIN       = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "build", "release", "shared", "dji", "bin"))

def respawn_gst():
    ip = config.default_gateway()
    if not ip:                       # no default route -> "--dji None" would spawn a broken pane
        print("[watchdog] ===== NO WIFI GATEWAY: cannot resolve the phone IP, SKIPPING respawn. "
              "Reconnect the workstation to the phone hotspot. =====", flush=True)
        return None
    cmd = (f"source /opt/ros/jazzy/setup.bash && export LD_LIBRARY_PATH={BIN}:$LD_LIBRARY_PATH && "
           f"{BIN}/llm_to_action_gstreamer_rx --dji {ip}; echo [gst exited]; exec bash")
    subprocess.run(["tmux", "respawn-pane", "-k", "-t", f"{SESSION}:gst", "bash", "-c", cmd],
                   stderr=subprocess.DEVNULL)
    return ip

with FrameCounter(node_name="video_watchdog") as fc:
    print(f"[watchdog] monitoring {TOPIC} | stall>{STALL_SEC}s -> reconnect | retry every {RETRY_SEC}s", flush=True)
    stalled = False
    last_respawn = 0.0
    last_beat = 0.0
    while fc.alive:
        time.sleep(0.2)
        now = time.time()
        gap = fc.gap
        if gap > STALL_SEC:
            if not stalled:
                stalled = True
                print(f"\n[watchdog] ===== VIDEO STALLED: no frames for {gap:.0f}s =====", flush=True)
            if now - last_respawn >= RETRY_SEC:
                ip = respawn_gst()
                last_respawn = now
                if ip:
                    print(f"[watchdog] reconnecting gst --dji {ip} (retry). If this repeats, the PHONE stopped "
                          f"streaming -> foreground the app / check the drone camera feed.", flush=True)
        else:
            if stalled:
                stalled = False
                print(f"[watchdog] ===== VIDEO RECOVERED ({fc.frames} frames total) =====", flush=True)
        if now - last_beat >= 10:
            last_beat = now
            print(f"[watchdog] {'STALLED' if stalled else 'OK'} | {fc.frames} frames | last {gap:.1f}s ago", flush=True)
