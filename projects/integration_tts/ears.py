"""Ears = your EXISTING ASR pipeline, reused whole. We do NOT capture audio or transcribe
here -- the ROS2 asr_node (miniaudio mic + push-to-talk on H + sttserv backend, all your
tuned work) already publishes transcripts on /asr_server/transcribe. This just subscribes
and hands each transcript to the brain. Run the asr_node alongside this demo; press H there
(its global key listener) to talk."""
import threading
import rclpy
from std_msgs.msg import String
import config

class Ears:
    def __init__(self, on_text):
        self._on_text = on_text
        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = rclpy.create_node("integration_ears")
        self._node.create_subscription(String, config.ASR_TOPIC, self._cb, 10)
        from rclpy.executors import SingleThreadedExecutor
        self._exec = SingleThreadedExecutor()          # OWN executor: never share the global one with CameraStream
        self._exec.add_node(self._node)
        threading.Thread(target=self._exec.spin, daemon=True).start()

    def _cb(self, msg):
        text = (msg.data or "").strip()
        if text:
            self._on_text(text)

    def shutdown(self):
        try:
            self._node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass
