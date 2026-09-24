"""Speech in from the laptop mic, through our C++ ASR server (whisper). The server
records on push-to-talk and publishes each transcript on config.ASR_TOPIC; this
subscribes and hands each transcript on. The app starts the server (process() below) when
"ros" is one of the ASR sources."""
import os

from std_msgs.msg import String

import config
from system.ros import Subscription
from system.supervisor import ProcessSpec
from util.process import native_env


class RosAsr:
    """@on_heard(text, source): called once per transcript, source "ros"."""

    def __init__(self, on_heard):
        self._on_heard = on_heard
        self._sub = Subscription(
            "integration_asr_ros",
            String,
            config.ASR_TOPIC,
            self._on_message
        )
        return

    def status(self):
        """No row of its own: this source's health is its ASR server's process row."""
        return []

    def close(self):
        self._sub.close()
        return

    def _on_message(self, msg):
        text = (msg.data or "").strip()
        if not text:
            return
        self._on_heard(text, "ros")
        return


def argv():
    """The C++ ASR server's command line, from config."""
    args = [
        os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_asr_server"),
        f"--backend={config.ASR_BACKEND}",
        f"--model={config.ASR_MODEL_PATH}",
        "--fa",
        f"--language={config.ASR_LANGUAGE}",
        "--threads=1",
        "--gid=0",
    ]
    if config.ASR_CAPTURE_DEVICE:
        args.append(f"--captureid={config.ASR_CAPTURE_DEVICE}")

    if config.RECORD_SESSION:
        args += ["--record", f"--recordDir={config.CLIPS_DIR}"]

    return args


def process(log_dir):
    """The ASR server for the supervisor. A laptop part: past the budget, the app
    dies."""
    os.makedirs(config.CLIPS_DIR, exist_ok=True)
    return ProcessSpec(
        name="asr",
        argv=argv(),
        env=native_env(PULSE_SERVER=config.PULSE_SERVER),
        log_path=os.path.join(log_dir, "proc-asr.log"),
    )
