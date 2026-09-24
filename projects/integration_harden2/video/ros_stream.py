"""Video from the DJI phone app: `llm_to_action_gstreamer_rx --dji <phone ip>` decodes
the phone's H.264 and publishes it on the ROS2 topic camera/stream (sensor_msgs/Image,
bgr8). RosStream subscribes to that topic. process() describes the gstreamer receiver for
the supervisor."""
import os
import threading

import numpy as np
from sensor_msgs.msg import Image

import config
from system.ros import Subscription
from system.supervisor import ProcessSpec
from util.process import native_env

TOPIC = "camera/stream"      # == gstreamer_udp_cam_rx kOutCameraPipelineRawFrameTopic


class RosStream:
    """The latest frame on camera/stream. read() -> (ok, frame); frames counts NEW frames
    (a stalled stream still returns its last frame)."""

    def __init__(self, topic=TOPIC):
        self._frame = None
        self.frames = 0
        self._lock = threading.Lock()
        self._sub = Subscription("integration_video_ros", Image, topic, self._on_image)
        print(f"[video] subscribed to '{topic}': waiting for frames", flush=True)
        return

    def close(self):
        self._sub.close()
        return

    def read(self):
        with self._lock:
            frame = self._frame
        if frame is None:
            return False, None

        return True, frame.copy()

    def _on_image(self, msg):
        height = msg.height
        width = msg.width

        # A malformed frame is dropped. After these checks the reshapes cannot fail.
        if msg.encoding != "bgr8":
            print(f"[video] frame dropped: {msg.encoding}, not bgr8", flush=True)
            return
        if msg.step < width * 3 or len(msg.data) != height * msg.step:
            print(
                f"[video] frame dropped: {len(msg.data)} bytes for "
                f"{height} rows x {msg.step} (width {width})",
                flush=True
            )
            return

        rows = np.frombuffer(msg.data, dtype=np.uint8).reshape(height, msg.step)
        image = rows[:, : width * 3].reshape(height, width, 3)   # stride-safe
        with self._lock:
            self._frame = image
            self.frames += 1
        return


def process(log_dir, phone_ip):
    """The gstreamer receiver for the supervisor. It depends on the phone app, so past
    its restart budget it WAITS for the user (orange) instead of killing the app."""
    return ProcessSpec(
        name="gstreamer",
        argv=[
            os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_gstreamer_rx"),
            "--dji",
            phone_ip,
        ],
        env=native_env(),
        log_path=os.path.join(log_dir, "proc-gstreamer.log"),
        required=False,
    )
