"""Tests for video/: the gstreamer receiver's start-up and the stall guard that replaced the watchdog
process. No process is started: the supervisor is a recorder; time is passed in."""
import os
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from system.status import RECOVERING, UP, StatusBoard
from video import camera_stream
from video.camera_stream import StallGuard

HARDEN2 = os.path.join(os.path.dirname(__file__), "..")


class RecordingSupervisor:
    def __init__(self):
        self.started = []
        self.restarts = []

    def start(self, name, argv, env=None, ready=None, ready_timeout_s=0, log_path=None):
        self.started.append((name, argv))

    def restart(self, name, reason):
        self.restarts.append((name, reason))
        return True


def test_gstreamer_argv():
    assert camera_stream.gstreamer_argv("10.0.0.1") == [
        os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_gstreamer_rx"), "--dji", "10.0.0.1"]


def test_webcam_starts_no_video_process(tmp_path):
    sup = RecordingSupervisor()
    camera_stream.start_services(sup, str(tmp_path), "0")
    assert sup.started == []


def test_dji_starts_gstreamer_to_the_phone(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PHONE_IP", "10.0.0.7")
    sup = RecordingSupervisor()
    camera_stream.start_services(sup, str(tmp_path), "ros")
    assert sup.started == [("gstreamer", camera_stream.gstreamer_argv("10.0.0.7"))]


def test_dji_without_a_phone_ip_dies():
    code = textwrap.dedent(f'''
        import sys; sys.path.insert(0, {HARDEN2!r})
        import config; config.PHONE_IP = None
        from video import camera_stream
        camera_stream.start_services(None, "/tmp", "ros")
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "no phone IP" in r.stderr


def test_stall_guard_restarts_on_a_stall_and_retries_on_its_period():
    board, sup = StatusBoard(), RecordingSupervisor()
    g = StallGuard(sup, board, stall_s=6.0, retry_s=15.0)
    g.tick(True, now=100.0)
    assert board.state("video") == UP
    g.tick(False, now=105.0)                          # 5 s: not a stall yet
    assert sup.restarts == []
    g.tick(False, now=107.0)                          # 7 s: stall -> restart once
    assert len(sup.restarts) == 1 and board.state("video") == RECOVERING
    g.tick(False, now=115.0)                          # inside the retry period: no second restart
    assert len(sup.restarts) == 1
    g.tick(False, now=122.5)                          # retry period passed: restart again
    assert len(sup.restarts) == 2 and sup.restarts[0][0] == "gstreamer"
    g.tick(True, now=123.0)                           # frames again
    assert board.state("video") == UP


# ==================== open_capture + CameraStream (all cases) ====================
import numpy as np


def test_open_capture_picks_the_reader_by_source_kind(monkeypatch):
    opened = []
    monkeypatch.setattr(camera_stream.cv2, "VideoCapture", lambda *a: (opened.append(a), _FakeCap())[1])
    monkeypatch.setattr(camera_stream, "CameraStream", lambda: "ros-stream")
    assert camera_stream.open_capture("ros") == "ros-stream"
    camera_stream.open_capture("2")
    assert opened[-1] == (2,)                                       # a webcam index
    camera_stream.open_capture("v4l2src ! videoconvert ! appsink")
    assert opened[-1][1] == camera_stream.cv2.CAP_GSTREAMER          # a gstreamer pipeline
    camera_stream.open_capture("/tmp/clip.mp4")
    assert opened[-1] == ("/tmp/clip.mp4",)                         # a file or URL


class _FakeCap:
    def set(self, *a):
        return True


class _Msg:
    def __init__(self, h, w, step, data):
        self.height, self.width, self.step, self.data = h, w, step, data


def _bare_stream():
    s = camera_stream.CameraStream.__new__(camera_stream.CameraStream)   # no ROS node: frame logic only
    import threading
    import time as _t
    s._lock, s._frame, s.frames, s._t0, s._timeout = threading.Lock(), None, 0, _t.time(), 60.0
    return s


def test_camera_stream_parses_a_stride_padded_frame_and_counts_it():
    s = _bare_stream()
    h, w, step = 2, 3, 12                                            # 9 bytes of pixels + 3 bytes of padding per row
    s._cb(_Msg(h, w, step, bytes(range(h * step))))
    ok, frame = s.read()
    assert ok and frame.shape == (2, 3, 3) and s.frames == 1
    assert frame[1, 0, 0] == 12                                      # row 2 starts after the padding


def test_camera_stream_drops_a_malformed_frame_and_keeps_going():
    s = _bare_stream()
    s._cb(_Msg(2, 3, 12, b"short"))
    assert s.read() == (False, None) and s.frames == 0
    assert s.isOpened()                                               # still inside the first-frame window


def test_camera_stream_read_returns_a_copy():
    s = _bare_stream()
    s._cb(_Msg(1, 1, 3, bytes([1, 2, 3])))
    _, a = s.read()
    a[:] = 0
    _, b = s.read()
    assert np.array_equal(b, np.array([[[1, 2, 3]]], np.uint8))
