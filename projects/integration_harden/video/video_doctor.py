#!/usr/bin/env python3
"""video_doctor -- when the app says "waiting for video", run this. It walks the video path
layer by layer and names the ONE that's broken, so "waiting for video" is never a mystery again.
Layers: phone IP -> control reachable -> gst node running -> gst connected to :5600 ->
phone actually sending frames -> ROS topic publishing.

Run as a MODULE from the integration_harden root (that root is then on sys.path, so `import config`
and `from video.camera_stream import ...` both resolve with no path shim):
    cd /root/groundstation/projects/integration_harden && python3 -m video.video_doctor
"""
import glob, os, subprocess, time

import config
from video.camera_stream import FrameCounter, TOPIC   # one home for the topic + the teardown fix

def gst_pids():
    out=[]
    for c in glob.glob("/proc/[0-9]*/comm"):
        try:
            if open(c).read().strip().startswith("llm_to_action_g"): out.append(c.split("/")[2])
        except Exception: pass
    return out

def estab_5600(ip):
    try:
        r=subprocess.run(["ss","-tnp"],capture_output=True,text=True,timeout=4).stdout
        return [l for l in r.splitlines() if f"{ip}:5600" in l and "ESTAB" in l]
    except Exception: return []

def topic_hz(secs=3):
    """Frames seen on TOPIC in `secs`. FrameCounter owns the node, its own executor, and the
    join-before-destroy teardown, so the doctor no longer hand-rolls a subscription."""
    try:
        with FrameCounter(node_name="video_doctor") as fc:
            t=time.time()
            while time.time()-t<secs: time.sleep(0.1)
            return fc.frames
    except Exception as e: return f"ERR:{e}"

ip=config.default_gateway(); print(f"[1] phone IP (gateway): {ip}")
ctl="?"
if not ip: ctl="NO DEFAULT ROUTE"
else:
  try:
    subprocess.run(["curl","-s","-o","/dev/null","--max-time","3",f"http://{ip}:8080/status/"],check=True); ctl="reachable"
  except Exception: ctl="UNREACHABLE"
print(f"[2] control :8080     : {ctl}")
g=gst_pids(); print(f"[3] gst node running  : {g or 'NO'}")
e=estab_5600(ip); print(f"[4] gst<->phone :5600 : {'ESTABLISHED' if e else 'NOT CONNECTED'}")
frames=topic_hz(); print(f"[5] {TOPIC} in 3s  : {frames}")

print("\n>>> VERDICT:")
if ctl=="NO DEFAULT ROUTE": print("    NO DEFAULT ROUTE. The workstation is not on the phone's Wi-Fi at all.")
elif ctl=="UNREACHABLE": print("    PHONE UNREACHABLE. Wrong Wi-Fi / phone IP changed / API Server OFF.")
elif not g: print("    NO GST NODE. Start it (run_mvd relaunch or respawn the gst pane).")
elif not e: print("    GST NOT CONNECTED to phone:5600. Phone app/API-Server video port not listening.")
elif isinstance(frames,int) and frames==0:
    print("    PHONE CONNECTED BUT SENDING 0 FRAMES -> PHONE-SIDE video source stopped.")
    print("    Fix on the PHONE: foreground the control app; confirm the drone's live camera")
    print("    feed is visible in-app; API Server toggle ON; check RC/drone link + power-save.")
elif isinstance(frames,int): print(f"    VIDEO OK ({frames} frames/3s). If app still waits, the APP instance is stale -> restart it.")
else: print(f"    ROS check failed: {frames}")
