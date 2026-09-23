"""camera_stream.py -- the video path, one job.

`llm_to_action_gstreamer_rx --dji|--tello|px4` takes the raw H.264 from the phone/drone,
decodes it, and PUBLISHES it on the ROS2 topic `camera/stream` (sensor_msgs/Image, bgr8).
We SUBSCRIBE to that topic here. Source-agnostic: the node decides the source, we just read.

CameraStream mimics the slice of cv2.VideoCapture that mvd uses:
    isOpened() / read() -> (ok, bgr_frame) / release().
So `open_capture("ros")` returns one of these and the perception loop is unchanged.
"""
import importlib.util
import os
import sys
import threading
import time

import cv2
import numpy as np

import config
from system.status import RECOVERING, UP
from system.supervisor import native_env

# ROS2 is optional at import time (a webcam run needs none). Check without importing, so there is
# no try on the import; the die() below fires only if a ROS source is actually opened.
_HAVE_ROS = (importlib.util.find_spec("rclpy") is not None
             and importlib.util.find_spec("sensor_msgs") is not None)
if _HAVE_ROS:
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from sensor_msgs.msg import Image

TOPIC = "camera/stream"          # == gstreamer_udp_cam_rx kOutCameraPipelineRawFrameTopic
ROS_SOURCES = ("ros", "camera_stream", TOPIC)   # source strings that mean "subscribe to the topic"


from fatal import die

def _teardown(spin, executor, node):
    """Shut a spin thread + node down in the ONE order that does not core-dump on exit: JOIN the
    spin loop first, then remove and destroy the node. Destroying a node while its executor is
    still spinning is what dumped core."""
    try:
        spin.join(timeout=1.5)
    except Exception as e:                 # rclpy teardown can throw during shutdown; report, keep going
        print(f"[camera_stream] teardown join: {e}", flush=True)
    try:
        executor.remove_node(node)
    except Exception as e:
        print(f"[camera_stream] teardown remove_node: {e}", flush=True)
    try:
        node.destroy_node()
    except Exception as e:
        print(f"[camera_stream] teardown destroy_node: {e}", flush=True)


class CameraStream:
    def __init__(self, topic=TOPIC, first_frame_timeout=15.0):
        if not _HAVE_ROS:
            die("ROS2 (rclpy) not available for camera_stream; source the ROS2 environment")
        if not rclpy.ok():
            rclpy.init()
        self._node = rclpy.create_node("scene_camera_stream_sub")
        self._sub  = self._node.create_subscription(Image, topic, self._cb, 10)
        self._exec = SingleThreadedExecutor()          # OWN executor: never share the global one with Ears
        self._exec.add_node(self._node)
        self._frame = None
        self.frames = 0                   # new frames received; the stall guard watches this count
        self._lock  = threading.Lock()
        self._stop  = False
        self._t0    = time.time()
        self._timeout = first_frame_timeout
        self._spin  = threading.Thread(target=self._spin_loop, daemon=True)
        self._spin.start()
        print(f"[camera_stream] subscribed to '{topic}' (waiting for gstreamer_rx frames)", flush=True)

    def _spin_loop(self):
        try:
            while not self._stop and rclpy.ok():
                self._exec.spin_once(timeout_sec=0.1)   # spin OUR executor only — cancellable, no global-executor contention
        except Exception as e:   # a spin error kills this thread; leave a trace, do not vanish
            print(f"[camera_stream] camera spin stopped: {e}", flush=True)

    def _cb(self, msg):
        h, w = msg.height, msg.width
        try:
            arr = np.frombuffer(msg.data, dtype=np.uint8).reshape(h, msg.step)   # a view: no extra copy
            img = arr[:, : w * 3].reshape(h, w, 3)      # bgr8, stride-safe
        except (ValueError, TypeError) as e:            # a malformed frame -> drop it, keep the callback alive
            print(f"[camera_stream] bad frame dropped: {e}", flush=True)
            return
        with self._lock:
            self._frame = img
            self.frames += 1

    # --- cv2.VideoCapture-compatible surface ---------------------------------------
    def isOpened(self):
        # "open" once frames flow, or until the first-frame timeout elapses (then let caller error)
        with self._lock:
            if self._frame is not None:
                return True
        return (time.time() - self._t0) < self._timeout

    def read(self):
        with self._lock:
            f = self._frame
        if f is None:
            return False, None
        return True, f.copy()

    def release(self):
        self._stop = True
        _teardown(self._spin, self._exec, self._node)   # join-before-destroy: the core-dump fix


def source_kind(src):
    """ros | webcam | gstreamer | stream | file: the ONE place that classifies a video source string."""
    s = str(src)
    if s in ROS_SOURCES:
        return "ros"
    if s.isdigit():
        return "webcam"
    if "!" in s:
        return "gstreamer"
    if "://" in s:
        return "stream"
    return "file"


def open_capture(src):
    """One opener for every source kind: ROS topic, webcam index, GStreamer pipe, or URL/file.
    Moved from highlight_seg.py on 2026-09-02."""
    kind = source_kind(src)
    src = str(src)
    if kind == "ros":
        return CameraStream()
    if kind == "webcam":
        cap = cv2.VideoCapture(int(src))
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))   # 2026-09-08: UVC cams (C920) give 720p at 10 fps in YUYV, 30 fps in MJPG
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_H)
        return cap
    if kind == "gstreamer":
        return cv2.VideoCapture(src, cv2.CAP_GSTREAMER)
    return cv2.VideoCapture(src)



def gstreamer_argv(phone_ip):
    """The gstreamer receiver's command line (was run.sh's gst pane): the phone's H.264 -> camera/stream."""
    return [os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_gstreamer_rx"), "--dji", phone_ip]


def start_services(supervisor, log_dir, source):
    """Start the video processes a source needs. Only a ROS source (dji) needs one: the gstreamer
    receiver. The phone is the WiFi gateway; no gateway at start-up is fatal (the source is required)."""
    if source_kind(source) != "ros":
        return
    if not config.PHONE_IP:
        die("VIDEO=dji but no phone IP: connect to the phone hotspot, or export PHONE_IP")
    supervisor.start("gstreamer", gstreamer_argv(config.PHONE_IP), env=native_env(),
                     log_path=os.path.join(log_dir, "proc-gstreamer.log"))
    return


class StallGuard:
    """Replaces the old video_watchdog process. The display loop calls tick() once per loop with
    whether a new frame arrived. No frame for STALL seconds -> report `video` RECOVERING and ask the
    supervisor for a deliberate gstreamer restart, again every RETRY seconds, forever (a stalled phone
    stream must not crash the app). Frames again -> `video` UP.
    @m_lastFrame: monotonic time of the last new frame. @m_lastRetry: of the last restart request."""

    def __init__(self, supervisor, board, stall_s=config.WATCHDOG_STALL_SEC, retry_s=config.WATCHDOG_RETRY_SEC):
        self.supervisor = supervisor
        self.board = board
        self.mk_stallS = stall_s
        self.mk_retryS = retry_s
        self.m_lastFrame = time.monotonic()
        self.m_lastRetry = 0.0

    def tick(self, got_frame, now=None):
        now = time.monotonic() if now is None else now
        if got_frame:
            self.m_lastFrame = now
            self.board.report("video", UP)            # the board records (and logs) only a change
            return
        gap = now - self.m_lastFrame
        if gap <= self.mk_stallS:
            return
        if now - self.m_lastRetry < self.mk_retryS:
            return
        self.m_lastRetry = now
        self.board.report("video", RECOVERING, f"no frames for {gap:.0f}s; restarting gstreamer")
        self.supervisor.restart("gstreamer", f"video stalled {gap:.0f}s")
        return

if __name__ == "__main__":
    # Self-contained smoke: read frames from any source for 3 s and report. No ROS needed for
    # webcam/file sources. Run as a MODULE from the integration_harden2 root, which puts that root
    # on sys.path for free -- no path shim:
    #     cd /root/groundstation/projects/integration_harden2 && python3 -m video.camera_stream 0
    src = sys.argv[1] if len(sys.argv) > 1 else "0"
    cap = open_capture(src)
    frames, shape, t0 = 0, None, time.time()
    while time.time() - t0 < 3.0:
        ok, frame = cap.read()
        if ok:
            frames += 1
            shape = frame.shape
    cap.release()
    print(f"[camera_stream selftest] source={src} frames_in_3s={frames} shape={shape}")
    sys.exit(0 if frames > 0 else 1)
