"""The operator's global keys. The llm_to_action keyboard hook (process() below) reads
every key from /dev/input, whatever window has focus, and publishes [key code, action] on
/keyboard/in/raw. Keys subscribes to that topic and reports each key PRESS through
on_key; the app decides what a key does (F4 -> control). Keys knows nothing about the
drone (owner ruling 2026-09-23). Only function keys act in the app: letters are typed in
other windows."""
import os

from std_msgs.msg import Int32MultiArray

import config
from system.ros import Subscription

KEY_ACTION_RELEASED = 0          # evdev EV_KEY value: 0 release, 1 press, 2 auto-repeat
from system.supervisor import ProcessSpec
from util.process import native_env


class Keys:
    """@on_key(code): once per key PRESS (evdev key code). Release and auto-repeat are
    ignored, so holding a key reports it once."""

    def __init__(self, on_key, on_release=None):
        """@on_release(code): once per key RELEASE, or None."""
        self._on_key = on_key
        self._on_release = on_release
        self._sub = Subscription(
            "integration_keys",
            Int32MultiArray,
            config.KEYBOARD_RAW_TOPIC,
            self._on_message
        )
        return

    def close(self):
        self._sub.close()
        return

    def _on_message(self, msg):
        if len(msg.data) < 2:
            return
        if msg.data[1] == KEY_ACTION_RELEASED and self._on_release is not None:
            self._on_release(msg.data[0])
            return
        if msg.data[1] != config.KEY_ACTION_PRESSED:
            return

        self._on_key(msg.data[0])
        return


def process(log_dir):
    """The keyboard hook for the supervisor. ALWAYS started: F4 (the kill key) needs it,
    and so does push-to-talk. A laptop part: past the budget, the app dies."""
    return ProcessSpec(
        name="keys",
        argv=[os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_keyboard_hook")],
        env=native_env(),
        log_path=os.path.join(log_dir, "proc-keys.log"),
    )
