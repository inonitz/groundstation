#!/usr/bin/env python3
"""The scripted end-to-end run (owner rulings 2026-09-25 and Q4, 2026-09-28): publish a
fixed list of sentences on the ASR topic, as if spoken, so every run gets the same load
and runs compare fairly. The app reads each one as a mic transcript with no push-to-talk,
so it has no ASR time. The whole-app test publishes its sentences through
publish_transcript() below.

Script file: one sentence per line; "wait N" pauses N seconds; "#" starts a comment.
    python3 test/scripted_e2e_run.py [script]
    (run.sh up webcam mock with SCRIPT=<file>; SCRIPT=default = DEFAULT_SCRIPT below)

SAFETY: the sentences become commands, so it refuses unless control is the mock."""
import os
import sys
import time

import rclpy
from std_msgs.msg import String

# run as a script by run.sh: the harden2 root must be importable
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config  # noqa: E402
from gemma.server import port_up  # noqa: E402
from runtime import ros  # noqa: E402
from runtime.fatal import die  # noqa: E402

SETTLE_SECONDS = 20.0      # after Gemma is up: SAM3 and the rest finish loading
DISCOVERY_SECONDS = 2.0    # a new ROS2 publisher is not heard at once

# The default script: one of each request kind, the same every run. A "wait" after a
# request gives it time to finish before the next one.
DEFAULT_SCRIPT = """
מה אתה רואה?
wait 10
תסמן את הכוס
wait 15
תפסיק לסמן
wait 3
כמה אנשים יש פה?
wait 12
טוס קדימה חמישה מטרים
wait 6
עלה שלושה מטרים ואז הסתובב תשעים מעלות עם כיוון השעון
wait 8
מה אתה רואה?
wait 10
"""


def parse_script(text):
    """-> [("say", text) | ("wait", seconds)], in the order of the lines."""
    steps = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("wait "):
            steps.append(("wait", float(line.split()[1])))
            continue
        steps.append(("say", line))
    return steps


def read_script(path):
    """parse_script of a script file."""
    with open(path, encoding="utf-8") as fh:
        return parse_script(fh.read())


def speech_publisher(node):
    """A publisher on the ASR topic, where the ASR server publishes its transcripts."""
    return node.create_publisher(String, config.ASR_TOPIC, 10)


def publish_transcript(publisher, text):
    """Publish one transcript, as the ASR server does."""
    msg = String()
    msg.data = text
    publisher.publish(msg)
    return


def main():
    steps = []
    if config.DJI_REAL:
        die("the scripted run drives commands: it runs only with CONTROL=mock")

    if len(sys.argv) > 1:
        steps = read_script(sys.argv[1])
    else:
        steps = parse_script(DEFAULT_SCRIPT)

    print(f"[feed] waiting for Gemma on :{config.LLAMA_SERVER_PORT}", flush=True)
    while not port_up(config.LLAMA_SERVER_PORT):
        time.sleep(1.0)
    time.sleep(SETTLE_SECONDS)

    ros.start()
    node = rclpy.create_node("integration_feed")
    publisher = speech_publisher(node)
    time.sleep(DISCOVERY_SECONDS)

    for kind, value in steps:
        if kind == "wait":
            time.sleep(value)
            continue
        publish_transcript(publisher, value)
        print(f"[feed] said: {value}", flush=True)

    print("[feed] script done", flush=True)
    node.destroy_node()
    ros.stop()
    return


if __name__ == "__main__":
    main()
