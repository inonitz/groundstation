"""The scripted run (owner ruling 2026-09-25): publish a fixed list of sentences on the
ASR topic, as if spoken, so every run gets the same load and runs compare fairly. The app
reads each one as a mic transcript with no push-to-talk, so it has no ASR time.

Script file: one sentence per line; "wait N" pauses N seconds; "#" starts a comment.
    python3 -m app.feed [script]        (run.sh up webcam mock with SCRIPT=<file>)

SAFETY: the sentences become commands, so it refuses unless control is the mock."""
import os
import sys
import time

import rclpy
from std_msgs.msg import String

import config
from gemma.server import port_up
from system import ros
from system.fatal import die

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCRIPT = os.path.join(HERE, "perf_script.txt")
SETTLE_SECONDS = 20.0      # after Gemma is up: SAM3 and the rest finish loading
DISCOVERY_SECONDS = 2.0    # a new ROS2 publisher is not heard at once


def read_script(path):
    """-> [("say", text) | ("wait", seconds)], in file order."""
    steps = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("wait "):
                steps.append(("wait", float(line.split()[1])))
                continue
            steps.append(("say", line))
    return steps


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SCRIPT
    msg = String()

    if config.DJI_REAL:
        die("the scripted run drives commands: it runs only with CONTROL=mock")
    steps = read_script(path)

    print(f"[feed] waiting for Gemma on :{config.LLAMA_SERVER_PORT}", flush=True)
    while not port_up(config.LLAMA_SERVER_PORT):
        time.sleep(1.0)
    time.sleep(SETTLE_SECONDS)

    ros.start()
    node = rclpy.create_node("integration_feed")
    publisher = node.create_publisher(String, config.ASR_TOPIC, 10)
    time.sleep(DISCOVERY_SECONDS)

    for kind, value in steps:
        if kind == "wait":
            time.sleep(value)
            continue
        msg.data = value
        publisher.publish(msg)
        print(f"[feed] said: {value}", flush=True)

    print("[feed] script done", flush=True)
    node.destroy_node()
    ros.stop()
    return


if __name__ == "__main__":
    main()
