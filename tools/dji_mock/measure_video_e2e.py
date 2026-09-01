#!/usr/bin/env python3
"""True end-to-end video latency (glass -> Linux), automatic — no eyeballing a clock.
Flashes a window black<->white, records the flash time, and detects when that brightness
step arrives in the decoded drone frames. latency = arrival - flash.

Measures the FULL path: monitor -> drone camera -> RC -> WiFi -> phone -> rx_node decode -> ROS -> here.

SETUP (two terminals, both: source /opt/ros/jazzy/setup.bash):
  1)  GW=$(ip route show dev wlp2s0 | awk '/^default/{print $3}')
      build/release/shared/dji/bin/llm_to_action_gstreamer_rx --dji "$GW"
  2)  python3 tools/dji_mock/measure_video_e2e.py
Then AIM THE DRONE CAMERA AT THE 'FLASH' WINDOW so it fills most of the view.
Latency prints per flash. ESC or Ctrl-C -> prints full distribution + writes CSV."""
import time, os
import numpy as np, cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

INTERVAL = 1.5      # seconds between flips
THRESH   = 15.0     # mean-brightness jump (0-255) that counts as the flash arriving
CSV      = "tools/dji_mock/out/video_e2e.csv"

class E2E(Node):
    def __init__(self):
        super().__init__("video_e2e")
        self.create_subscription(Image, "camera/stream", self.cb, 10)
        self.state = 0; self.last = time.monotonic(); self.flash_t = self.last
        self.pending = True; self.prev = None; self.lat = []
        cv2.namedWindow("FLASH", cv2.WINDOW_NORMAL); cv2.resizeWindow("FLASH", 1000, 800)
        self.render()
        self.create_timer(0.01, self.tick)
        print("Aim the drone camera at the FLASH window (fill the view). ESC to stop + summarize.\n", flush=True)
    def render(self):
        img = np.zeros((800,1000,3),np.uint8) if self.state==0 else np.full((800,1000,3),255,np.uint8)
        cv2.imshow("FLASH", img); cv2.waitKey(1)
    def tick(self):
        now = time.monotonic()
        if now - self.last >= INTERVAL:
            self.state ^= 1; self.last = now; self.flash_t = now; self.pending = True; self.render()
        if (cv2.waitKey(1) & 0xFF) == 27: rclpy.shutdown()
    def cb(self, msg):
        tcap = time.monotonic()
        h, w = msg.height, msg.width
        try:
            a = np.frombuffer(bytes(msg.data), np.uint8).reshape(h, msg.step)[:, :w*3].reshape(h,w,3)
        except Exception:
            return
        b = float(a.mean())
        if self.prev is not None and self.pending:
            j = b - self.prev
            if (self.state==1 and j>THRESH) or (self.state==0 and j<-THRESH):
                l = (tcap - self.flash_t) * 1000.0
                if 0 < l < 3000:
                    self.lat.append(l); self.pending = False
                    A = np.array(self.lat)
                    print(f"e2e latency = {l:6.0f} ms   | n={len(A):3d}  mean={A.mean():.0f}  "
                          f"p50={np.median(A):.0f}  min={A.min():.0f}  max={A.max():.0f}", flush=True)
        self.prev = b
    def summary(self):
        if not self.lat:
            print("\nno samples gathered."); return
        a = np.array(sorted(self.lat)); n = len(a)
        pct = lambda q: a[min(n-1, int(round(q/100*(n-1))))]
        # robust view: drop clear artifacts (<50ms false matches, and the top 5% jitter tail)
        core = a[(a >= 50)]
        os.makedirs(os.path.dirname(CSV), exist_ok=True)
        with open(CSV, "w") as f:
            f.write("idx,latency_ms\n")
            for i, v in enumerate(self.lat): f.write(f"{i},{v:.1f}\n")
        print(f"\n=== e2e video latency summary (n={n}) ===")
        print(f"  ALL:  min={a[0]:.0f}  p50={pct(50):.0f}  p90={pct(90):.0f}  p95={pct(95):.0f}  "
              f"p99={pct(99):.0f}  max={a[-1]:.0f}  mean={a.mean():.0f} ms")
        if len(core):
            c = np.sort(core); m = len(c); cp = lambda q: c[min(m-1,int(round(q/100*(m-1))))]
            print(f"  >=50ms (drop false matches, n={m}): p50={cp(50):.0f}  p90={cp(90):.0f}  "
                  f"p95={cp(95):.0f}  mean={c.mean():.0f} ms")
        print(f"  raw samples -> {CSV}")

def main():
    rclpy.init()
    node = E2E()
    try: rclpy.spin(node)
    except KeyboardInterrupt: pass
    finally:
        node.summary()
        cv2.destroyAllWindows()
        if rclpy.ok(): rclpy.shutdown()
if __name__ == "__main__": main()
