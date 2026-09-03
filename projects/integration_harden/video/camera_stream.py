"""camera_stream.py -- the video path, one job.

`llm_to_action_gstreamer_rx --dji|--tello|px4` takes the raw H.264 from the phone/drone,
decodes it, and PUBLISHES it on the ROS2 topic `camera/stream` (sensor_msgs/Image, bgr8).
We SUBSCRIBE to that topic here. Source-agnostic: the node decides the source, we just read.

CameraStream mimics the slice of cv2.VideoCapture that scene_omdet uses:
    isOpened() / read() -> (ok, bgr_frame) / release().
So `open_capture("ros")` returns one of these and the perception loop is unchanged.
"""
import threading, time
import numpy as np

try:
    import rclpy
    from sensor_msgs.msg import Image
    _HAVE_ROS = True
except Exception as _e:          # ROS2 not sourced -> fail loudly only when actually used
    _HAVE_ROS = False
    _IMPORT_ERR = _e

TOPIC = "camera/stream"          # == gstreamer_udp_cam_rx kOutCameraPipelineRawFrameTopic
ROS_SOURCES = ("ros", "camera_stream", TOPIC)   # source strings that mean "subscribe to the topic"


def _teardown(spin, executor, node):
    """Shut a spin thread + node down in the ONE order that does not core-dump on exit: JOIN the
    spin loop first, then remove and destroy the node. Destroying a node while its executor is
    still spinning is what dumped core. Shared by CameraStream and FrameCounter so the fix cannot
    drift out of one of them again."""
    try: spin.join(timeout=1.5)
    except Exception: pass
    try: executor.remove_node(node)
    except Exception: pass
    try: node.destroy_node()
    except Exception: pass


class FrameCounter:
    """Counts frames arriving on a ROS2 topic, in its OWN SingleThreadedExecutor and spin thread
    (never the global executor -- that contends with Ears). Context manager, so teardown always
    goes through _teardown.

        with FrameCounter() as fc:
            time.sleep(3)
            print(fc.frames, fc.gap)

    video_doctor and video_watchdog each hand-rolled this subscription in a different lifecycle
    style; only one of them had the teardown fix. This is the single home."""

    def __init__(self, topic=TOPIC, node_name="frame_counter"):
        if not _HAVE_ROS:
            raise RuntimeError(f"ROS2 not available for camera_stream: {_IMPORT_ERR}")
        if not rclpy.ok():
            rclpy.init()
        self.frames = 0
        self.last = time.time()          # wall time of the most recent frame
        self.topic = topic
        self._node = rclpy.create_node(node_name)
        self._sub = self._node.create_subscription(Image, topic, self._cb, 10)
        from rclpy.executors import SingleThreadedExecutor
        self._exec = SingleThreadedExecutor()
        self._exec.add_node(self._node)
        self._stop = False
        self._spin = threading.Thread(target=self._spin_loop, daemon=True)
        self._spin.start()

    def _cb(self, _msg):
        self.frames += 1
        self.last = time.time()

    def _spin_loop(self):
        try:
            while not self._stop and rclpy.ok():
                self._exec.spin_once(timeout_sec=0.1)
        except Exception:
            pass

    @property
    def gap(self):
        """Seconds since the last frame arrived."""
        return time.time() - self.last

    @property
    def alive(self):
        """False once ROS shuts down or the counter is closed -- the loop condition for a monitor."""
        return (not self._stop) and rclpy.ok()

    def close(self):
        self._stop = True
        _teardown(self._spin, self._exec, self._node)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class CameraStream:
    def __init__(self, topic=TOPIC, first_frame_timeout=15.0):
        if not _HAVE_ROS:
            raise RuntimeError(f"ROS2 not available for camera_stream: {_IMPORT_ERR}")
        if not rclpy.ok():
            rclpy.init()
        self._node = rclpy.create_node("scene_camera_stream_sub")
        self._sub  = self._node.create_subscription(Image, topic, self._cb, 10)
        from rclpy.executors import SingleThreadedExecutor
        self._exec = SingleThreadedExecutor()          # OWN executor: never share the global one with Ears
        self._exec.add_node(self._node)
        self._frame = None
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
        except Exception:
            pass

    def _cb(self, msg):
        h, w = msg.height, msg.width
        try:
            arr = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(h, msg.step)
            img = arr[:, : w * 3].reshape(h, w, 3)      # bgr8, stride-safe
        except Exception:
            return
        with self._lock:
            self._frame = img

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


def open_capture(src):
    """One opener for every source kind: ROS topic, webcam index, GStreamer pipe, or URL/file.
    Moved from highlight_seg.py on 2026-09-02."""
    import cv2
    import config
    src = str(src)
    if src in ROS_SOURCES:
        return CameraStream()
    if src.isdigit():
        cap = cv2.VideoCapture(int(src))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_H)
        return cap
    if "!" in src:
        return cv2.VideoCapture(src, cv2.CAP_GSTREAMER)
    return cv2.VideoCapture(src)


if __name__ == "__main__":
    # Self-contained smoke: read frames from any source for 3 s and report. No ROS needed for
    # webcam/file sources. Run as a MODULE from the integration_harden root, which puts that root
    # on sys.path for free -- no path shim:
    #     cd /root/groundstation/projects/integration_harden && python3 -m video.camera_stream 0
    import sys
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
