"""Ears = your EXISTING ASR pipeline, reused whole. We do NOT capture audio or transcribe
here -- the ROS2 asr_node (miniaudio mic + push-to-talk on H + sttserv backend, all your
tuned work) already publishes transcripts on /asr_server/transcribe. This just subscribes
and hands each transcript to the brain. Run the asr_node alongside this demo; press H there
(its global key listener) to talk."""
import os
import threading

import rclpy
from rclpy.executors import SingleThreadedExecutor
from std_msgs.msg import String

import config
from system.supervisor import native_env

class Ears:
    def __init__(self, on_text):
        self._on_text = on_text
        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = rclpy.create_node("integration_ears")
        self._node.create_subscription(String, config.ASR_TOPIC, self._cb, 10)
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
        except Exception as e:   # rclpy teardown can throw during interpreter shutdown; report, do not swallow
            print(f"[ears] ROS2 shutdown error: {e}", flush=True)


def asr_argv():
    """The C++ ASR server's command line, from config (was run.sh's asr pane)."""
    argv = [os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_asr_server"),
            f"--backend={config.ASR_BACKEND}", f"--model={config.ASR_MODEL_PATH}", "--fa",
            f"--language={config.ASR_LANGUAGE}", "--threads=1", "--gid=0"]
    if config.ASR_CAPTURE_DEVICE:
        argv.append(f"--captureid={config.ASR_CAPTURE_DEVICE}")
    if config.RECORD_SESSION:
        argv += ["--record", f"--recordDir={config.CLIPS_DIR}"]
    return argv


def start_services(supervisor, log_dir):
    """Start the mic ASR under the supervisor: the whisper ASR server, and the push-to-talk keyboard
    hook that drives it. Both are ROS2 nodes: the app runs in a ROS-sourced shell, so they inherit it."""
    os.makedirs(config.CLIPS_DIR, exist_ok=True)
    supervisor.start("asr", asr_argv(), env=native_env(PULSE_SERVER=os.environ.get("PULSE_SERVER", config.PULSE_SERVER)),
                     log_path=os.path.join(log_dir, "proc-asr.log"))
    supervisor.start("keys", [os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_keyboard_hook")],
                     env=native_env(), log_path=os.path.join(log_dir, "proc-keys.log"))
    return
