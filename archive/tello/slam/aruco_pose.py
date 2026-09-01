#!/usr/bin/env python3
"""
ArUco pose source for the Tello hover-hold -- a drift-free, metric position anchor
that does NOT depend on stella's map or the venue floor.

The forward camera sees ONE matte-printed marker (on a wall/stand where the drone
hovers). This node detects it and publishes the marker pose in the CAMERA frame on
`aruco/pose`, which the hover-hold PID holds a setpoint against. stella is not in the
loop -- a glass room that breaks SLAM does not break a fiducial the camera can see.

Why this design survives the venue (see the venue analysis):
  - Marker is PHYSICAL + MATTE, never on the emissive screen -- a rolling-shutter
    camera beats against a display's refresh and bands the marker. Matt paper: no
    refresh, no backlight, no glare.
  - Pose via solvePnP on the four corners -- portable across OpenCV versions (no
    deprecated estimatePoseSingleMarkers), and a single planar marker gives usable
    POSITION (what the PID needs) even when orientation is ambiguous at oblique angles.

Sizing (fx ~ 915, reliable at ~50 px of marker): an A4 (~0.18 m) marker holds to ~3 m;
print A3/A2 for longer range. See README.

Usage:
    ./aruco_pose.py --selftest              # no ROS: generate a marker, detect, verify
    ./aruco_pose.py                         # ROS node: camera/stream -> aruco/pose
    ./aruco_pose.py --dict DICT_5X5_100 --marker-len 0.18
"""
import argparse
import os
import re
import sys

import numpy as np
import cv2


DEFAULT_DICT = "DICT_5X5_100"
DEFAULT_MARKER_LEN_M = 0.18          # A4 usable square
CONFIG_PATH = os.environ.get(
    "STELLA_CONFIG_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "stella_config_tello.yaml"),
)
# Calibrated Tello intrinsics (config/stella_config_tello.yaml); used if the file is absent.
FALLBACK_K = dict(fx=914.980, fy=914.705, cx=486.094, cy=362.422)
FALLBACK_DIST = [-0.025176, -0.004571, 0.000329, 0.001766, 0.107302]  # k1 k2 p1 p2 k3


def load_intrinsics():
    """K (3x3) + dist (5,) from the stella config, falling back to the measured values."""
    k = dict(FALLBACK_K)
    dist = list(FALLBACK_DIST)
    try:
        with open(CONFIG_PATH) as fh:
            text = fh.read()
        for key in ("fx", "fy", "cx", "cy"):
            m = re.search(rf"\b{key}:\s*([-\d.]+)", text)
            if m:
                k[key] = float(m.group(1))
        got = {}
        for key in ("k1", "k2", "p1", "p2", "k3"):
            m = re.search(rf"\b{key}:\s*([-\d.]+)", text)
            if m:
                got[key] = float(m.group(1))
        if len(got) == 5:
            dist = [got["k1"], got["k2"], got["p1"], got["p2"], got["k3"]]
    except OSError:
        pass
    K = np.array([[k["fx"], 0.0, k["cx"]],
                  [0.0, k["fy"], k["cy"]],
                  [0.0, 0.0, 1.0]], dtype=np.float64)
    return K, np.array(dist, dtype=np.float64)


def get_dictionary(name):
    dict_id = getattr(cv2.aruco, name)
    if hasattr(cv2.aruco, "getPredefinedDictionary"):
        return cv2.aruco.getPredefinedDictionary(dict_id)
    return cv2.aruco.Dictionary_get(dict_id)                  # very old OpenCV


def get_detector_params():
    if hasattr(cv2.aruco, "DetectorParameters_create"):
        return cv2.aruco.DetectorParameters_create()         # 4.6
    return cv2.aruco.DetectorParameters()                    # 4.7+


def draw_marker(dictionary, marker_id, px):
    if hasattr(cv2.aruco, "generateImageMarker"):
        return cv2.aruco.generateImageMarker(dictionary, marker_id, px)   # 4.7+
    return cv2.aruco.drawMarker(dictionary, marker_id, px)                # 4.6


def marker_object_points(marker_len):
    """The four marker corners in the marker frame, in detectMarkers order
    (top-left, top-right, bottom-right, bottom-left), z = 0 (planar)."""
    h = marker_len / 2.0
    return np.array([[-h,  h, 0.0],
                     [ h,  h, 0.0],
                     [ h, -h, 0.0],
                     [-h, -h, 0.0]], dtype=np.float64)


def detect_poses(gray, dictionary, params, marker_len, K, dist):
    """Return a list of (id, tvec[3], rvec[3]) for every marker found. Pose via
    solvePnP on the corners -- portable, and position is robust even when a single
    planar marker's orientation is ambiguous."""
    corners, ids, _ = cv2.aruco.detectMarkers(gray, dictionary, parameters=params)
    out = []
    if ids is None:
        return out
    objp = marker_object_points(marker_len)
    for i, mid in enumerate(ids.flatten()):
        img_pts = corners[i].reshape(-1, 2).astype(np.float64)
        ok, rvec, tvec = cv2.solvePnP(objp, img_pts, K, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if ok:
            out.append((int(mid), tvec.flatten(), rvec.flatten()))
    return out


def selftest():
    """Generate a marker at a known pixel size, detect it, and check the recovered
    range against fx*markerLen/pixelSize. No ROS, no hardware."""
    K, dist = load_intrinsics()
    fx = K[0, 0]
    dictionary = get_dictionary(DEFAULT_DICT)
    params = get_detector_params()
    marker_len = DEFAULT_MARKER_LEN_M

    px = 200
    canvas = np.full((720, 960), 255, np.uint8)
    marker = draw_marker(dictionary, 0, px)
    y0 = (720 - px) // 2
    x0 = (960 - px) // 2
    canvas[y0:y0 + px, x0:x0 + px] = marker

    poses = detect_poses(canvas, dictionary, params, marker_len, K, dist)
    assert len(poses) == 1, f"expected 1 marker, got {len(poses)}"
    mid, tvec, _ = poses[0]
    assert mid == 0, f"wrong id {mid}"
    expected_z = fx * marker_len / px          # ~ 0.82 m for these numbers
    err = abs(tvec[2] - expected_z) / expected_z
    assert err < 0.15, f"range {tvec[2]:.3f} vs expected {expected_z:.3f} (err {err:.2f})"
    # frontal + centred marker -> lateral offset near zero
    assert abs(tvec[0]) < 0.05 and abs(tvec[1]) < 0.05, f"off-centre tvec {tvec}"
    print(f"aruco_pose selftest: PASS  (id={mid} range={tvec[2]:.3f}m expected={expected_z:.3f}m)")
    return True


def ros_main(args):
    """ROS node: camera/stream (Image) -> aruco/pose (PoseStamped, camera frame)."""
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    from sensor_msgs.msg import Image
    from geometry_msgs.msg import PoseStamped

    K, dist = load_intrinsics()
    dictionary = get_dictionary(args.dict)
    params = get_detector_params()

    class ArucoPoseNode(Node):
        def __init__(self):
            super().__init__("aruco_pose")
            qos = QoSProfile(depth=5)
            qos.reliability = ReliabilityPolicy.BEST_EFFORT
            self.create_subscription(Image, "camera/stream", self.on_image, qos)
            self.pub = self.create_publisher(PoseStamped, "aruco/pose", 10)
            self.get_logger().info(
                f"aruco_pose up: dict={args.dict} marker_len={args.marker_len}m "
                f"-> aruco/pose (target id={args.id})")

        def on_image(self, msg):
            # Manual BGR8/mono decode -- avoid a hard cv_bridge dependency.
            buf = np.frombuffer(msg.data, dtype=np.uint8)
            if msg.encoding in ("bgr8", "rgb8"):
                img = buf.reshape(msg.height, msg.width, 3)
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = buf.reshape(msg.height, msg.width)
            poses = detect_poses(gray, dictionary, params, args.marker_len, K, dist)
            hit = next((p for p in poses if p[0] == args.id), None)
            if hit is None:
                return
            _, tvec, rvec = hit
            out = PoseStamped()
            out.header = msg.header
            out.header.frame_id = "camera"
            out.pose.position.x = float(tvec[0])
            out.pose.position.y = float(tvec[1])
            out.pose.position.z = float(tvec[2])
            # rvec (Rodrigues) -> quaternion for the orientation half.
            R, _ = cv2.Rodrigues(rvec)
            q = _rot_to_quat(R)
            out.pose.orientation.x, out.pose.orientation.y = float(q[0]), float(q[1])
            out.pose.orientation.z, out.pose.orientation.w = float(q[2]), float(q[3])
            self.pub.publish(out)

    rclpy.init()
    node = ArucoPoseNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0


def _rot_to_quat(R):
    """3x3 rotation -> (x,y,z,w). Standard, numerically-stable branch form."""
    t = np.trace(R)
    if t > 0.0:
        s = np.sqrt(t + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    return (x, y, z, w)


def main():
    ap = argparse.ArgumentParser(description="ArUco pose source for the Tello hover-hold.")
    ap.add_argument("--selftest", action="store_true", help="no-ROS detection self-test")
    ap.add_argument("--dict", default=DEFAULT_DICT, help="ArUco dictionary name")
    ap.add_argument("--marker-len", type=float, default=DEFAULT_MARKER_LEN_M, help="marker side, metres")
    ap.add_argument("--id", type=int, default=0, help="marker id to track")
    args = ap.parse_args()

    if args.selftest:
        return 0 if selftest() else 1
    return ros_main(args)


if __name__ == "__main__":
    sys.exit(main())
