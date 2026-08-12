#!/usr/bin/env python3
"""
C1 SLAM-quality readout for the Tello -- the vision-side half of the go/no-go.

No EKF2 ground truth on the Tello, so this does NOT score absolute drift. It measures
what stella exposes on ROS, ROBUSTLY (no fragile poses/frames ratio):

    rate        slam/pose publish rate (Hz)      -- near the 30 Hz camera is healthy
    uptime      fraction of seconds WITH a pose  -- 1.0 = stella never lost tracking
    blind       seconds with video but NO pose   -- tracker paused/lost
    no-video    seconds with no frames at all    -- RX not publishing (not stella's fault)
    return/peak end-offset over peak-excursion, in SLAM UNITS (monocular = up-to-scale):
                small ratio = returned near start; a large one = drift or imperfect return

    IMPORTANT: positions are UP-TO-SCALE (monocular). The numbers are stella map units,
    NOT metres. Only the return/peak RATIO is meaningful without a scale. For physical
    drift in metres, film the flight and run ../measure_drift.py.

One line/sec on [TELLO_SLAM]; Ctrl-C prints a [TELLO_SLAM_SUMMARY] verdict.
"""
import math
import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Image


POSE_TOPIC  = "slam/pose"
IMAGE_TOPIC = "camera/stream"

GOOD_UPTIME   = 0.80   # fraction of seconds tracking, for a PASS
MAX_NOVIDEO_S = 3      # a couple of startup seconds is fine; more means RX trouble


class TelloSlamCheck(Node):
    def __init__(self):
        super().__init__("tello_slam_check")
        img_qos = QoSProfile(depth=10)
        img_qos.reliability = ReliabilityPolicy.BEST_EFFORT
        img_qos.history = HistoryPolicy.KEEP_LAST

        self.create_subscription(PoseStamped, POSE_TOPIC, self.on_pose, 10)
        self.create_subscription(Image, IMAGE_TOPIC, self.on_image, img_qos)

        self.win_poses = 0
        self.win_frames = 0
        self.total_seconds = 0
        self.track_seconds = 0     # seconds with >=1 pose
        self.blind_seconds = 0     # frames>0 but poses==0
        self.novideo_seconds = 0   # frames==0
        self.total_poses = 0

        self.first_pos = None
        self.last_pos = None
        self.prev_pos = None
        self.path_len = 0.0
        self.peak_disp = 0.0
        self.jitter_acc = 0.0
        self.jitter_n = 0

        self.create_timer(1.0, self.tick)
        self.get_logger().info(
            f"[TELLO_SLAM] listening: pose='{POSE_TOPIC}' image='{IMAGE_TOPIC}'. "
            "Move the camera through the textured scene (translate to init).")

    def on_image(self, _msg):
        self.win_frames += 1     # lossy by QoS; used ONLY as a >0 'is there video' flag

    def on_pose(self, msg):
        self.win_poses += 1
        self.total_poses += 1
        p = msg.pose.position
        pos = (p.x, p.y, p.z)
        if self.first_pos is None:
            self.first_pos = pos
        if self.prev_pos is not None:
            d = _dist(pos, self.prev_pos)
            self.path_len += d
            if d < 0.05:
                self.jitter_acc += d
                self.jitter_n += 1
        self.prev_pos = pos
        self.last_pos = pos
        self.peak_disp = max(self.peak_disp, _dist(pos, self.first_pos))

    def tick(self):
        self.total_seconds += 1
        frames, poses = self.win_frames, self.win_poses
        self.win_frames = self.win_poses = 0

        if poses > 0:
            state = "TRACKING"; self.track_seconds += 1
        elif frames == 0:
            state = "NO-VIDEO"; self.novideo_seconds += 1
        else:
            state = "BLIND";    self.blind_seconds += 1

        ret  = _dist(self.last_pos, self.first_pos) if (self.last_pos and self.first_pos) else 0.0
        ratio = (ret / self.peak_disp) if self.peak_disp > 1e-6 else 0.0
        px, py, pz = self.last_pos if self.last_pos else (0.0, 0.0, 0.0)
        # raw map-frame position (up-to-scale). Correlate with a KNOWN move ("I went
        # forward 1 m") to pin which axis is which -- needed to write the hover-hold node.
        self.get_logger().info(
            f"[TELLO_SLAM] rate={poses:2d}hz state={state:8s} "
            f"pos=({px:+.2f},{py:+.2f},{pz:+.2f}) "
            f"return/peak={ratio:.2f} (ret={ret:.2f} peak={self.peak_disp:.2f} units) note={state}")

    def summary(self):
        secs = self.total_seconds or 1
        uptime = self.track_seconds / secs
        ret   = _dist(self.last_pos, self.first_pos) if (self.last_pos and self.first_pos) else 0.0
        ratio = (ret / self.peak_disp) if self.peak_disp > 1e-6 else 0.0
        rate  = self.total_poses / secs
        jitter = (self.jitter_acc / self.jitter_n) if self.jitter_n else 0.0

        reasons = []
        verdict = "PASS"
        if self.track_seconds == 0:
            verdict, reasons = "FAIL", ["stella never produced a pose -- did not track at all"]
        else:
            if uptime < GOOD_UPTIME:
                verdict = "FAIL"; reasons.append(f"uptime {uptime:.0%} < {GOOD_UPTIME:.0%}")
            if self.novideo_seconds > MAX_NOVIDEO_S:
                verdict = "FAIL"; reasons.append(f"no-video {self.novideo_seconds}s -- RX not publishing")

        print(f"\n[TELLO_SLAM_SUMMARY] {verdict}  seconds={self.total_seconds} "
              f"uptime={uptime:.0%} blind={self.blind_seconds}s novideo={self.novideo_seconds}s "
              f"pose_rate={rate:.0f}hz return_over_peak={ratio:.2f} "
              f"(ret={ret:.2f} peak={self.peak_disp:.2f} SLAM-units) jitter={jitter*1000:.0f}mu")
        if reasons:
            print("[TELLO_SLAM_SUMMARY] why: " + "; ".join(reasons))
        print("[TELLO_SLAM_SUMMARY] units are UP-TO-SCALE (monocular). For drift in METRES: "
              "film the flight + run ../measure_drift.py.")
        return verdict == "PASS"


def _dist(a, b):
    if a is None or b is None:
        return 0.0
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def main():
    rclpy.init()
    node = TelloSlamCheck()
    ok = False
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        ok = node.summary()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
