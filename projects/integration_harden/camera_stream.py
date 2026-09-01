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
        try: self._spin.join(timeout=1.5)          # let the spin loop exit BEFORE destroying the node (was the core dump)
        except Exception: pass
        try: self._exec.remove_node(self._node)
        except Exception: pass
        try: self._node.destroy_node()
        except Exception: pass
