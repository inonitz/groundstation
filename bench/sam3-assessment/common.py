"""Shared helpers for the SAM3 assessment scripts: the harden2 import path, the test
frames, percentiles, a pynvml GPU sampler and a bench Gemma.

The scripts measure the app's own modules in place (one home per component): SAM3 is
sam3.model.Sam3Backend, Gemma starts through the app's supervisor."""
import atexit
import contextlib
import glob
import json
import os
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
HARDEN = os.path.join(ROOT, "projects", "integration_harden2")
sys.path.insert(0, HARDEN)

import cv2                                   # noqa: E402
import numpy as np                           # noqa: E402
import pynvml                                # noqa: E402

from gemma import server as gemma_process   # noqa: E402
from gemma.client import Gemma               # noqa: E402
from runtime.fatal import die                 # noqa: E402
from runtime.supervisor import Supervisor     # noqa: E402

RESULTS = os.path.join(HERE, "results")
# The app's frame: the C920 webcam at 1280x720, BGR uint8 (2.64 MiB).
FRAME_W = 1280
FRAME_H = 720
# Real indoor frames (640x480), scaled up to the app's frame size.
DESK_FRAMES = "/root/models/vision/sam3-desk-frames"
# A port no other bench or the app uses (the app 8091, hebrew-command-bench 18091).
GEMMA_PORT = 18093
# The phrases as the app sends them after perception2.concept.phrase_concepts:
# "person" is one forward, "dresser" fans out to three.
PHRASE_ONE = "person"
PHRASE_THREE = "dresser, chest of drawers, cabinet"


def frames(n):
    """n real frames at the app's size, spread over the desk sequence."""
    paths = sorted(glob.glob(os.path.join(DESK_FRAMES, "*.jpg")))
    step = max(1, len(paths) // n)
    out = []

    for path in paths[::step][:n]:
        out.append(cv2.resize(cv2.imread(path), (FRAME_W, FRAME_H)))
    return out


def noise_frame():
    """The random frame the older benches used (contention.py, concurrency.py)."""
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, (FRAME_H, FRAME_W, 3), dtype=np.uint8)


def pct(values, q):
    """Nearest-rank percentile; nan for an empty list."""
    if not values:
        return float("nan")

    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(q / 100 * (len(ordered) - 1))))
    return ordered[index]


def stats(values):
    """n / p50 / p95 / min / max, rounded to 0.1."""
    if not values:
        return {"n": 0}

    return {
        "n": len(values),
        "p50": round(pct(values, 50), 1),
        "p95": round(pct(values, 95), 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
    }


def ms_since(t0):
    return (time.perf_counter() - t0) * 1000


class GpuSampler:
    """GPU load and memory every 0.1 s through pynvml (0.02 ms a read, HISTORY
    2026-09-27), on its own thread, between start() and stop()."""

    def __init__(self):
        pynvml.nvmlInit()
        self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        self._stop = threading.Event()
        self._thread = None
        self.load = []
        self.mem_mib = []
        return

    def name(self):
        return pynvml.nvmlDeviceGetName(self._handle)

    def start(self):
        self.load = []
        self.mem_mib = []
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return

    def stop(self):
        self._stop.set()
        self._thread.join()
        return {
            "load_p50": pct(self.load, 50),
            "load_max": max(self.load, default=0),
            "mem_max_mib": max(self.mem_mib, default=0),
        }

    def _run(self):
        while not self._stop.is_set():
            util = pynvml.nvmlDeviceGetUtilizationRates(self._handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            self.load.append(util.gpu)
            self.mem_mib.append(mem.used // (1024 * 1024))
            time.sleep(0.1)
        return


@contextlib.contextmanager
def gemma_server():
    """Gemma started the way the app starts it (the supervisor, gemma.server.process),
    on the bench port. atexit stops it even when a script dies, so no GPU process stays
    behind."""
    supervisor = Supervisor()
    atexit.register(supervisor.stop_all)
    log_dir = tempfile.mkdtemp(prefix="sam3-assessment-gemma-")
    handle = supervisor.start(gemma_process.process(log_dir, port=GEMMA_PORT))
    if not handle.wait_up(300):
        die(f"the bench Gemma was not ready after 300 s; log: {log_dir}")

    yield Gemma(GEMMA_PORT)

    supervisor.stop_all()
    return


def write_result(name, data):
    """results/<date>-<name>.json; returns the path."""
    day = time.strftime("%Y-%m-%d")
    path = os.path.join(RESULTS, f"{day}-{name}.json")
    with open(path, "w") as out:
        json.dump(data, out, indent=1, ensure_ascii=False)
    print("wrote", path, flush=True)
    return path
