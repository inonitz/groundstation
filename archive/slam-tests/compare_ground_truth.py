#!/usr/bin/env python3
"""
Score stella_vslam's pose against PX4 EKF2 ground truth during a SITL flight.

Spec B1 asks for a number, not a screenshot. This node subscribes to the SLAM
pose and to PX4's odometry, pairs them in time, and prints one tagged line per
second that a human or a filter.sh can grep:

    [SLAM_CHECK] rate=29.80hz tracking_frac=0.99 drift_m=0.14 ...

Four things make the comparison non-trivial, and each is handled explicitly:

1. Monocular SLAM has no metric scale, and its world frame starts wherever
   tracking initialised. Subtracting the two positions directly would report
   garbage. So the two trajectories are aligned with a Umeyama similarity fit
   (scale + rotation + translation) over the whole run, and drift is the
   residual left after that best-case alignment. That is the honest number: it
   asks "is the SLAM trajectory the same SHAPE as the true one", which is what
   monocular tracking can actually promise.

2. That fit has a failure mode worth naming. When the SLAM track is mostly
   noise, the cheapest similarity fit is to shrink the scale toward zero and
   park every point on the centroid. Drift then saturates at the size of the
   flight path instead of growing without bound, so a small drift number alone
   does NOT prove tracking worked. spread_ratio catches this. It compares the
   RMS spread of the aligned SLAM track against the RMS spread of the true
   track, so honest tracking sits near 1.0 and a collapsed fit sits near 0.
   Spread is used rather than path length on purpose: at 30 Hz, per-sample
   jitter dominates arc length and would make even a good track look inflated,
   whereas spread only degrades in quadrature.

3. PX4 reports position in NED. slam/pose is published in a right-handed frame
   that rviz reads as ENU-ish. The odometry is converted NED -> ENU before use.

4. The two message stamps come from different clocks. VehicleOdometry.timestamp
   is PX4 boot time in microseconds; slam/pose is stamped with the SLAM node's
   ROS clock. They are not comparable, so both samples are timestamped on
   arrival with this node's clock instead. At 30 Hz the receipt jitter is far
   below the drift scale being measured.

Usage:
    python3 compare_ground_truth.py [--window 5.0] [--max-drift-m 1.0]
                                    [--min-tracking-frac 0.5]
Ctrl-C prints a final [SLAM_CHECK_SUMMARY] verdict line and exits non-zero on FAIL.
"""

import argparse
import math
import sys
from collections import deque

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped
from px4_msgs.msg import VehicleOdometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

SLAM_POSE_TOPIC = "slam/pose"
PX4_ODOM_TOPIC = "/fmu/out/vehicle_odometry"
CAMERA_TOPIC = "camera/stream"

# A pair is only usable if the two samples landed within this much of each other.
MAX_PAIR_DT_S = 0.05
# Below this much true motion the similarity fit is degenerate (a hover gives a
# scale of roughly 0/0), so drift is reported as nan rather than as a fake number.
MIN_PATH_LENGTH_M = 1.0
# Umeyama needs a handful of well-spread points to mean anything.
MIN_PAIRS = 20
# Acceptable band for the aligned-vs-true spread ratio. Outside it the fit has
# either collapsed onto a point or blown up, and the drift number is meaningless.
SPREAD_RATIO_MIN = 0.5
SPREAD_RATIO_MAX = 2.0


def umeyama_similarity(src, dst):
    """
    Least-squares similarity transform mapping src onto dst (Umeyama 1991).

    src, dst: (N, 3) arrays of corresponding points.
    Returns (scale, rotation 3x3, translation 3) minimising
    ||dst - (scale * R @ src + t)||.
    """
    n = src.shape[0]
    mu_src = src.mean(axis=0)
    mu_dst = dst.mean(axis=0)
    src_c = src - mu_src
    dst_c = dst - mu_dst

    cov = (dst_c.T @ src_c) / n
    u_mat, singular, vt_mat = np.linalg.svd(cov)

    # Guard against the fit choosing a reflection instead of a rotation.
    correction = np.eye(3)
    if np.linalg.det(u_mat) * np.linalg.det(vt_mat) < 0:
        correction[2, 2] = -1.0

    rotation = u_mat @ correction @ vt_mat
    var_src = (src_c ** 2).sum() / n
    if var_src < 1e-12:
        return float("nan"), rotation, np.zeros(3)

    scale = float(np.trace(np.diag(singular) @ correction) / var_src)
    translation = mu_dst - scale * (rotation @ mu_src)
    return scale, rotation, translation


def path_length(points):
    """Total distance travelled along the sample sequence."""
    if points.shape[0] < 2:
        return 0.0
    return float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())


def spread(points):
    """RMS distance of the samples from their centroid."""
    if points.shape[0] < 2:
        return 0.0
    centred = points - points.mean(axis=0)
    return float(np.sqrt((centred ** 2).sum(axis=1).mean()))


class DriftResult:
    """One drift measurement, or an explained absence of one."""

    def __init__(self, rmse, max_resid, scale, spread_ratio, pairs, note):
        self.rmse = rmse
        self.max_resid = max_resid
        self.scale = scale
        self.spread_ratio = spread_ratio
        self.pairs = pairs
        self.note = note

    @classmethod
    def unavailable(cls, pairs, note):
        nan = float("nan")
        return cls(nan, nan, nan, nan, pairs, note)

    @property
    def usable(self):
        return math.isfinite(self.rmse)


class SlamGroundTruthComparator(Node):
    def __init__(self, args):
        super().__init__("slam_ground_truth_comparator")
        self.args = args

        # Full-run buffers, used for the similarity fit.
        self.slam_samples = []   # (t, np.array([x, y, z]))
        self.odom_samples = []
        # Rolling windows, used for rate and tracking fraction.
        self.slam_recent = deque()
        self.image_recent = deque()

        self.create_subscription(PoseStamped, SLAM_POSE_TOPIC, self.on_slam_pose, 50)
        self.create_subscription(
            VehicleOdometry, PX4_ODOM_TOPIC, self.on_odometry, qos_profile_sensor_data
        )
        self.create_subscription(Image, CAMERA_TOPIC, self.on_image, qos_profile_sensor_data)
        self.create_timer(1.0, self.on_report)

        self.reports = 0
        self.last_tracking_frac = 0.0
        self.get_logger().info(
            "comparing %s against %s (window=%.1fs)"
            % (SLAM_POSE_TOPIC, PX4_ODOM_TOPIC, args.window)
        )

    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_slam_pose(self, msg):
        t = self.now_s()
        p = msg.pose.position
        self.slam_samples.append((t, np.array([p.x, p.y, p.z], dtype=float)))
        self.slam_recent.append(t)

    def on_odometry(self, msg):
        t = self.now_s()
        # PX4 NED -> ENU: east = pos[1], north = pos[0], up = -pos[2].
        pos = msg.position
        if any(math.isnan(v) for v in (pos[0], pos[1], pos[2])):
            return
        enu = np.array([pos[1], pos[0], -pos[2]], dtype=float)
        self.odom_samples.append((t, enu))

    def on_image(self, _msg):
        self.image_recent.append(self.now_s())

    def prune(self, window_start):
        while self.slam_recent and self.slam_recent[0] < window_start:
            self.slam_recent.popleft()
        while self.image_recent and self.image_recent[0] < window_start:
            self.image_recent.popleft()

    def pair_samples(self):
        """Nearest-in-time odometry sample for each SLAM sample."""
        if not self.slam_samples or not self.odom_samples:
            return np.empty((0, 3)), np.empty((0, 3))

        odom_t = np.array([t for t, _ in self.odom_samples])
        odom_p = np.stack([p for _, p in self.odom_samples])

        src, dst = [], []
        for t, slam_p in self.slam_samples:
            idx = int(np.argmin(np.abs(odom_t - t)))
            if abs(odom_t[idx] - t) > MAX_PAIR_DT_S:
                continue
            src.append(slam_p)
            dst.append(odom_p[idx])

        if not src:
            return np.empty((0, 3)), np.empty((0, 3))
        return np.stack(src), np.stack(dst)

    def compute_drift(self):
        """
        Drift is the horizontal (XY) residual after the best similarity
        alignment. Vertical is excluded because the spec's acceptance criterion
        is horizontal drift, and monocular altitude is the weakest axis.
        """
        src, dst = self.pair_samples()
        n = src.shape[0]
        if n < MIN_PAIRS:
            return DriftResult.unavailable(n, "too-few-pairs")
        if path_length(dst) < MIN_PATH_LENGTH_M:
            return DriftResult.unavailable(n, "not-enough-motion")

        scale, rotation, translation = umeyama_similarity(src, dst)
        if not math.isfinite(scale):
            return DriftResult.unavailable(n, "degenerate-fit")

        aligned = (scale * (rotation @ src.T)).T + translation
        residual_xy = np.linalg.norm(aligned[:, :2] - dst[:, :2], axis=1)
        rmse = float(np.sqrt((residual_xy ** 2).mean()))

        truth_spread = spread(dst)
        if truth_spread < 1e-6:
            return DriftResult.unavailable(n, "not-enough-motion")
        ratio = spread(aligned) / truth_spread

        note = "ok"
        if ratio < SPREAD_RATIO_MIN:
            # The fit shrank the SLAM track onto the centroid: the pose is not
            # tracking, and the small drift number would be an artefact.
            note = "collapsed-fit"
        elif ratio > SPREAD_RATIO_MAX:
            note = "inflated-fit"
        return DriftResult(rmse, float(residual_xy.max()), scale, ratio, n, note)

    def on_report(self):
        now = self.now_s()
        self.prune(now - self.args.window)

        rate = len(self.slam_recent) / self.args.window
        frames = len(self.image_recent)
        # publish_rviz_pose() is skipped while the tracker is paused, so poses
        # per camera frame is the available proxy for "is it tracking".
        tracking_frac = min(1.0, len(self.slam_recent) / frames) if frames else 0.0
        self.last_tracking_frac = tracking_frac

        d = self.compute_drift()
        self.reports += 1
        print(
            "[SLAM_CHECK] rate=%.2fhz tracking_frac=%.2f drift_m=%.2f drift_max_m=%.2f "
            "spread_ratio=%.2f pairs=%d scale=%.3f frames=%d note=%s"
            % (rate, tracking_frac, d.rmse, d.max_resid, d.spread_ratio, d.pairs,
               d.scale, frames, d.note),
            flush=True,
        )

    def summarise(self):
        d = self.compute_drift()
        failures = []
        if self.last_tracking_frac < self.args.min_tracking_frac:
            failures.append(
                "tracking_frac %.2f < %.2f" % (self.last_tracking_frac, self.args.min_tracking_frac)
            )
        if not d.usable:
            failures.append("no usable drift measurement (%s)" % d.note)
        else:
            if d.note != "ok":
                failures.append(
                    "alignment %s (spread_ratio %.2f outside %.1f-%.1f), drift number not trustworthy"
                    % (d.note, d.spread_ratio, SPREAD_RATIO_MIN, SPREAD_RATIO_MAX)
                )
            if d.rmse > self.args.max_drift_m:
                failures.append("drift_m %.2f > %.2f" % (d.rmse, self.args.max_drift_m))

        verdict = "PASS" if not failures else "FAIL"
        print(
            "[SLAM_CHECK_SUMMARY] verdict=%s drift_m=%.2f drift_max_m=%.2f spread_ratio=%.2f "
            "scale=%.3f pairs=%d tracking_frac=%.2f reports=%d reason=%s"
            % (
                verdict,
                d.rmse,
                d.max_resid,
                d.spread_ratio,
                d.scale,
                d.pairs,
                self.last_tracking_frac,
                self.reports,
                "; ".join(failures) if failures else "none",
            ),
            flush=True,
        )
        return verdict == "PASS"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--window", type=float, default=5.0, help="rolling window, seconds")
    parser.add_argument("--max-drift-m", type=float, default=1.0, help="drift RMSE tolerance")
    parser.add_argument("--min-tracking-frac", type=float, default=0.5, help="tracking floor")
    args, ros_args = parser.parse_known_args()

    rclpy.init(args=ros_args)
    node = SlamGroundTruthComparator(args)
    passed = False
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        passed = node.summarise()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
