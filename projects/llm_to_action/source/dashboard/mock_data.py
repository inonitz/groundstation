#!/usr/bin/env python3
"""Publish synthetic A2 topics so the dashboard runs with no drone and no SITL.

It fires the four topics serve.py subscribes: two 320x240 BGR images (annotated and
depth) at ~10 Hz, a HUD line at 5 Hz, and a VLM reasoning line every few seconds.
Use it to check the bridge and the browser page end-to-end on a bench before you
spend SITL or flight time.

Run:  python3 scripts/dashboard/smoke.py      (Ctrl-C to stop)
Then: python3 scripts/dashboard/serve.py, and open http://localhost:8088
The image panels animate; the HUD tiles, detection list, and VLM log all update.
"""
import math

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


def frame(t, tag):
    img = np.zeros((240, 320, 3), np.uint8)
    x = int(140 + 90 * math.sin(t))          # a box that slides, so the stream visibly moves
    cv2.rectangle(img, (x, 70), (x + 60, 180), (80, 200, 90), 2)
    cv2.putText(img, tag, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    return img


class Smoke(Node):
    def __init__(self):
        super().__init__("dashboard_smoke")
        self.br = CvBridge()
        self.pa = self.create_publisher(Image, "/fmu/perception/annotated", 1)
        self.pd = self.create_publisher(Image, "/fmu/perception/depth", 1)
        self.ph = self.create_publisher(String, "/fmu/hud", 10)
        self.pv = self.create_publisher(String, "/fmu/vlm_text", 10)
        self.t = 0.0
        self.cyc = 0
        self.create_timer(0.1, self.on_img)   # 10 Hz images
        self.create_timer(0.2, self.on_hud)   # 5 Hz HUD
        self.create_timer(4.0, self.on_vlm)   # a VLM cycle every 4 s

    def on_img(self):
        self.t += 0.1
        self.pa.publish(self.br.cv2_to_imgmsg(frame(self.t, "annotated"), "bgr8"))
        depth = cv2.applyColorMap(frame(self.t * 0.7, "depth"), cv2.COLORMAP_TURBO)
        self.pd.publish(self.br.cv2_to_imgmsg(depth, "bgr8"))

    def on_hud(self):
        alt = 1.4 + 0.05 * math.sin(self.t)
        vel = 0.2 + 0.1 * abs(math.sin(self.t))
        busy = "busy" if int(self.t) % 6 < 2 else "idle"
        msg = String()
        msg.data = (f"STATE=FLIGHT ALT={alt:.2f}m TASK=follow(person) VLM={busy} "
                    f"DET=person@83%,chair@51% VEL={vel:.2f}m/s BATT=61%")
        self.ph.publish(msg)

    def on_vlm(self):
        self.cyc += 1
        msg = String()
        msg.data = (f"cycle {self.cyc}: two people in view; the masked one is the target. "
                    f"Lock it and follow, holding ~1.8 m.")
        self.pv.publish(msg)


def main():
    rclpy.init()
    node = Smoke()
    print("publishing synthetic A2 topics; Ctrl-C to stop")
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
