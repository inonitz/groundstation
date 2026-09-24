"""Tests for video/: the source classifier, the gstreamer process, Video over a REAL
video file (written with OpenCV), and the ROS stream + stall guard over a REAL ROS2
topic."""
import os
import subprocess
import sys
import textwrap
import time

import cv2
import numpy as np
import rclpy
from sensor_msgs.msg import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from system.status import RECOVERING, UP
from video import ros_stream
from video.video import Video, source_kind

from support import wait_for

HARDEN2 = os.path.join(os.path.dirname(__file__), "..")


def _wait_for(pred, timeout=5.0):
    return wait_for(pred, timeout)


# ==================== the source ====================
def test_source_kind_names_every_source():
    assert source_kind("ros") == "ros" and source_kind("camera/stream") == "ros"
    assert source_kind("0") == "webcam" and source_kind(2) == "webcam"
    assert source_kind("videotestsrc ! appsink") == "gstreamer"
    assert source_kind("rtsp://10.0.0.1:8554/live") == "stream"
    assert source_kind("/data/clip.mp4") == "file"


def test_the_gstreamer_process_waits_instead_of_dying(tmp_path):
    spec = ros_stream.process(str(tmp_path), "10.0.0.7")
    receiver = os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_gstreamer_rx")
    assert spec.argv == [receiver, "--dji", "10.0.0.7"]
    assert spec.required is False           # it depends on the phone app: it WAITS
    assert spec.log_path == str(tmp_path / "proc-gstreamer.log")


# ==================== Video over a real file ====================
def _clip(path, frames=5):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (64, 48))
    for i in range(frames):
        writer.write(np.full((48, 64, 3), i * 40, np.uint8))
    writer.release()
    return str(path)


def test_a_file_opens_reads_and_hands_out_copies(tmp_path):
    video = Video(_clip(tmp_path / "clip.avi"))
    assert video.status()[0][1] == UP and not video.live
    ok, frame = video.read()
    assert ok and frame.shape == (48, 64, 3)
    copy = video.snapshot()
    copy[:] = 255                    # a private copy: the latest frame is untouched
    assert not np.array_equal(copy, video.snapshot())
    video.close()


def test_a_source_that_never_opens_dies_with_the_reason():
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {HARDEN2!r})
        import config
        config.OPEN_TIMEOUT = 0.0
        from video.video import Video
        Video("/nonexistent/clip.mp4")
        print("STILL RUNNING", flush=True)
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode != 0 and "STILL RUNNING" not in r.stdout
    assert "cannot open the video source" in r.stderr


# ============== the ROS stream and the stall guard, over real ROS2 ==============
class RecordingGstreamer:
    """Stands in for the gstreamer Process handle: records each restart request."""

    def __init__(self):
        self.restarts = []

    def restart(self, reason):
        self.restarts.append(reason)
        return True


def _publish_frame():
    node = rclpy.create_node("test_camera_publisher")
    pub = node.create_publisher(Image, ros_stream.TOPIC, 10)
    _wait_for(lambda: pub.get_subscription_count() > 0)
    msg = Image(height=4, width=6, encoding="bgr8", step=6 * 3)
    msg.data = bytes(range(4 * 6 * 3))
    pub.publish(msg)
    return node


def test_ros_frames_arrive_and_the_row_goes_up(monkeypatch):
    video = Video("ros", RecordingGstreamer())
    assert video.live and not video.read()[0]      # no frame yet: the UI shows "waiting"
    node = _publish_frame()
    assert _wait_for(lambda: video.read()[0])
    ok, frame = video.read()
    assert frame.shape == (4, 6, 3) and video.status()[0][1] == UP
    node.destroy_node()
    video.close()


def test_a_stalled_stream_restarts_gstreamer(monkeypatch):
    monkeypatch.setattr(config, "WATCHDOG_STALL_SEC", 0.1)
    monkeypatch.setattr(config, "WATCHDOG_RETRY_SEC", 60.0)
    gstreamer = RecordingGstreamer()
    video = Video("ros", gstreamer)
    time.sleep(0.2)
    video.read()                                   # no NEW frame for 0.2 s: stalled
    assert video.status()[0][1] == RECOVERING
    assert gstreamer.restarts and "stalled" in gstreamer.restarts[0]
    video.read()                                   # within the retry window: no repeat
    assert len(gstreamer.restarts) == 1
    video.close()
