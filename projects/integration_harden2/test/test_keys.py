"""Tests for keys/: the global keys over a REAL ROS2 topic (keys.py). Moved unchanged
from test_app.py with the module (owner R3 a, 2026-09-28)."""
import os
import sys
import time

import rclpy
from std_msgs.msg import Int32MultiArray

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from keys.keys import Keys


# ==================== keys.py: the global kill key ====================
def _publish(events):
    """Publish each [code, action] pair from a separate node, as
    the keyboard hook does."""
    node = rclpy.create_node("test_keyboard_hook")
    pub = node.create_publisher(Int32MultiArray, config.KEYBOARD_RAW_TOPIC, 10)
    deadline = time.time() + 5.0
    while pub.get_subscription_count() == 0 and time.time() < deadline:
        time.sleep(0.05)
    for data in events:
        msg = Int32MultiArray()
        msg.data = list(data)
        pub.publish(msg)
    time.sleep(0.5)
    node.destroy_node()
    return


def _run(events):
    """-> the key codes Keys reported for these key events."""
    codes = []
    keys = Keys(on_key=codes.append)
    _publish(events)
    keys.close()
    return codes


def test_a_press_is_reported_once():
    press = [config.KILL_KEY_CODE, config.KEY_ACTION_PRESSED]
    assert _run([press]) == [config.KILL_KEY_CODE]


def test_release_and_repeat_are_not_reported():
    # holding F4: press, auto-repeat x2, release -> exactly one report
    events = [
        [config.KILL_KEY_CODE, 1],
        [config.KILL_KEY_CODE, 2],
        [config.KILL_KEY_CODE, 2],
        [config.KILL_KEY_CODE, 0],
    ]
    assert _run(events) == [config.KILL_KEY_CODE]


def test_keys_reports_every_key_and_knows_nothing_about_the_drone():
    # evdev KEY_M = 50, KEY_Q = 16, KEY_C = 46
    assert _run([[50, 1], [16, 1], [46, 1]]) == [50, 16, 46]


def test_short_message_is_ignored():
    assert _run([[config.KILL_KEY_CODE]]) == []
