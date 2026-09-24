"""Process helpers shared by several modules."""
import os
import time

import config

STOP_POLL_SECONDS = 0.1     # how often stop_process checks a terminated child


def native_env(**extra):
    """The environment for one of our C++ programs: ours, plus the native library
    folder, plus `extra`."""
    library_path = config.NATIVE_BIN_DIR + ":" + os.environ.get("LD_LIBRARY_PATH", "")
    env = dict(os.environ, LD_LIBRARY_PATH=library_path)
    env.update(extra)
    return env


def wait_exit(proc, timeout_s):
    """Wait up to timeout_s for a child to exit. -> True when it exited. Popen.poll()
    never throws (Popen.wait(timeout) reports a timeout only by a throw)."""
    deadline = time.monotonic() + timeout_s
    while proc.poll() is None:
        if time.monotonic() >= deadline:
            return False
        time.sleep(STOP_POLL_SECONDS)
    return True
