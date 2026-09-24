"""Video: ONE interface; the config option VIDEO picks its source (one choice). Video
opens the source, retries it, reports its own "video" status row, hands out the latest
frame and, for DJI video, restarts gstreamer when the frames stop.

  ros      -> RosStream: the phone's video through gstreamer and ROS2 (VIDEO=dji)
  webcam   -> OpenCV on a camera index
  gstreamer / stream / file -> OpenCV on a pipeline, a URL or a file"""
import threading
import time

import cv2

import config
from system.status import RECOVERING, STARTING, UP, Status, fail
from video.ros_stream import RosStream

ROS_SOURCES = ("ros", "camera_stream", "camera/stream")
OPEN_RETRY_SECONDS = 1.5      # a source that does not open is tried again after this


def source_kind(source):
    """ros | webcam | gstreamer | stream | file: the ONE place that classifies a
    source."""
    text = str(source)
    if text in ROS_SOURCES:
        return "ros"
    if text.isdigit():
        return "webcam"
    if "!" in text:
        return "gstreamer"
    if "://" in text:
        return "stream"
    return "file"


def _open(source, kind):
    """One capture for the source kind; every kind answers read() -> (ok, frame)."""
    if kind == "ros":
        return RosStream()

    if kind == "webcam":
        capture = cv2.VideoCapture(int(source))
        # UVC cams (C920) give 720p at 10 fps in YUYV, 30 fps in MJPG (2026-09-08)
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAM_W)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAM_H)
        return capture

    if kind == "gstreamer":
        return cv2.VideoCapture(str(source), cv2.CAP_GSTREAMER)

    return cv2.VideoCapture(str(source))


def _is_open(capture, kind):
    """An OpenCV capture knows at once. The ROS stream counts as open at once: the window
    shows "waiting for video" (with the status pane) until the first frame arrives."""
    if kind == "ros":
        return True
    return capture.isOpened()


class Video:
    """@source: config.INPUT. @gstreamer: the gstreamer Process handle (DJI video), or
             None. Video owns the "video" status row (status()).
    The source is required: never open within config.OPEN_TIMEOUT -> FAILED and die."""

    def __init__(self, source, gstreamer=None):
        self.source = source
        self.kind = source_kind(source)
        self.live = self.kind in ("ros", "stream", "gstreamer")   # never "ends"
        self._gstreamer = gstreamer
        self._latest = None
        self._lock = threading.Lock()
        self._seen_frames = 0
        self._last_frame = time.monotonic()
        self._last_restart = 0.0

        self._status = Status("video", STARTING, str(source))
        self._capture = self._open_with_retry()
        if self.kind != "ros":             # the ROS stream goes UP with its first frame
            self._status.set(UP)
        return

    def status(self):
        """[(name, state, detail)]: the "video" row."""
        return [self._status.row()]

    def close(self):
        if self.kind == "ros":
            self._capture.close()
            return

        self._capture.release()
        return

    def read(self):
        """The next frame. -> (ok, frame). The display loop calls this; the stall guard
        runs here."""
        ok, frame = self._capture.read()
        if self.kind == "ros":
            self._watch_stall()

        if not ok:
            return False, None

        with self._lock:
            self._latest = frame
        return True, frame

    def snapshot(self):
        """A private copy of the latest frame, or None (vision takes these)."""
        with self._lock:
            frame = self._latest
        if frame is None:
            return None
        return frame.copy()

    def _open_with_retry(self):
        started = time.monotonic()
        capture = _open(self.source, self.kind)

        while not _is_open(capture, self.kind):
            if time.monotonic() - started > config.OPEN_TIMEOUT:
                fail(
                    self._status,
                    f"cannot open {self.source}",
                    f"cannot open the video source {self.source!r} within "
                    f"{config.OPEN_TIMEOUT:.0f}s"
                )
            print("[video] waiting for", self.source, flush=True)
            time.sleep(OPEN_RETRY_SECONDS)
            capture.release()
            capture = _open(self.source, self.kind)
        return capture

    def _watch_stall(self):
        """No NEW frame for WATCHDOG_STALL_SEC -> RECOVERING and a planned gstreamer
        restart, again every WATCHDOG_RETRY_SEC (a stalled phone stream never crashes the
        app). Frames again -> UP."""
        now = time.monotonic()
        if self._capture.frames != self._seen_frames:
            self._seen_frames = self._capture.frames
            self._last_frame = now
            self._status.set(UP)
            return

        gap = now - self._last_frame
        if gap <= config.WATCHDOG_STALL_SEC:
            return
        if now - self._last_restart < config.WATCHDOG_RETRY_SEC:
            return

        self._last_restart = now
        self._status.set(
            RECOVERING,
            f"no frames for {gap:.0f}s; restarting gstreamer"
        )
        if self._gstreamer is not None:
            self._gstreamer.restart(f"video stalled {gap:.0f}s")
        return
