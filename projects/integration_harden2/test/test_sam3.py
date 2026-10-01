"""Tests for sam3/: the loader service (its "sam3" row, not ready until loaded, an
unknown backend dies) and the real SAM3 model (GPU, opt-in). Moved unchanged from
test_perception2.py and test_app.py with the module (owner D2, 2026-09-29)."""
import os
import subprocess
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sam3.contract import DETECT_NOT_READY, DETECT_OK
from sam3.loader import BackendLoader
from support import CAR, state_of


def test_the_backend_loader_is_not_ready_until_loaded():
    from sam3.loader import BackendLoader
    release = threading.Event()

    def slow_model():
        release.wait(2)
        return type("M", (), {"detect": lambda self, f, p, conf, topk: (DETECT_OK, CAR),
                              "mask_for_box": lambda self, f, b: "mask"})()

    loader = BackendLoader("sam3", loader=slow_model)
    assert loader.detect(None, "car", 0.1) == (DETECT_NOT_READY, [])
    assert state_of(loader) == "STARTING"
    release.set()
    loader.thread.join(2)
    assert state_of(loader) == "UP" and loader.detect(None, "car", 0.1)[1] == CAR
    assert loader.mask_for_box(None, (1, 2, 3, 4)) == "mask"


def test_the_loader_warms_the_model_up_before_its_row_is_up():
    """Owner L1: one pass on a blank camera-size frame after the load; the "sam3" row
    turns UP only after it, and detect() answers NOT_READY until then."""
    import config
    release = threading.Event()
    calls = []

    class Model:
        def detect(self, frame, phrase, conf, topk):
            calls.append((frame.shape, phrase))
            release.wait(2)
            return DETECT_OK, CAR

        def mask_for_box(self, frame, box):
            return None

    loader = BackendLoader("sam3", loader=Model)
    assert _wait_for_calls(calls)
    assert calls[0] == ((config.CAM_H, config.CAM_W, 3), config.SAM3_WARM_UP_PHRASE)
    assert state_of(loader) == "STARTING"
    assert loader.detect(None, "car", 0.1) == (DETECT_NOT_READY, [])
    release.set()
    loader.thread.join(2)
    assert state_of(loader) == "UP"


def _wait_for_calls(calls):
    end = time.monotonic() + 2
    while not calls and time.monotonic() < end:
        time.sleep(0.01)
    return bool(calls)


def test_an_unknown_vision_backend_dies():
    """An unknown SCENE_SEG -> die() (a hard crash, not an exception), in a child."""
    here = os.path.dirname(__file__)
    code = ("import sys, os;"
            "sys.path.insert(0, os.path.join(%r, '..'));"
            "from sam3.loader import BackendLoader;"
            "BackendLoader('yoloe')" % (here,))
    r = subprocess.run([sys.executable, "-c", code],
                       env={**os.environ, "MVD_HOME": "integration_harden2"},
                       capture_output=True, text=True)
    assert r.returncode != 0, "unknown SCENE_SEG must crash"
    assert "no vision backend" in r.stderr, r.stderr


# ==================== the real SAM3 (GPU; opt-in) ====================
@pytest.mark.skipif(
    os.environ.get("HARDEN2_GPU_TESTS") != "1",
    reason="loads the real SAM3 model on the GPU: set HARDEN2_GPU_TESTS=1"
)
def test_real_sam3_detects_and_masks_a_window():
    """The real backend on a real picture: detect finds windows, and mask_for_box
    returns the frame-sized mask it cached. (Moved here from sam3_backend._smoke
    2026-09-24.)"""
    import cv2
    from sam3.model import Sam3Backend

    frame = cv2.imread(
        "/root/groundstation/bench/perception/dataset/images/img0.png"
    )
    assert frame is not None
    backend = Sam3Backend()
    status, dets = backend.detect(frame, "window", conf=0.30)
    assert status == DETECT_OK and dets

    mask = backend.mask_for_box(frame, dets[0]["box"])
    assert mask is not None and mask.shape[:2] == frame.shape[:2]


# ==================== _dedup_overlaps on REAL SAM3 boxes (CPU) ====================
# raw_dets copied from pass_*.json of past runs of today's code (2026-09-25). Each
# list is already deduplicated by detect(), so a second pass returns it unchanged
# (owner TR17).
REAL_PASSES = {
    # session-20260925-045109-rog/perception/0015-highlight-dresser/pass_00001.json
    "dresser": [
        {"conf": 0.7266, "box": (676, 219, 876, 462), "label": "dresser"},
        {"conf": 0.7148, "box": (680, 219, 872, 462), "label": "cabinet"},
        {"conf": 0.6328, "box": (676, 219, 876, 464), "label": "chest of drawers"},
        {"conf": 0.291, "box": (596, 219, 876, 568), "label": "cabinet"},
        {"conf": 0.2656, "box": (592, 219, 876, 568), "label": "chest of drawers"},
        {"conf": 0.2539, "box": (596, 219, 884, 568), "label": "dresser"},
        {"conf": 0.2354, "box": (1248, 286, 1272, 496), "label": "cabinet"},
        {"conf": 0.167, "box": (1248, 284, 1272, 498), "label": "dresser"},
        {"conf": 0.166, "box": (-13, 576, 251, 732), "label": "cabinet"},
        {"conf": 0.1523, "box": (-7, 704, 1272, 720), "label": "dresser"},
        {"conf": 0.1328, "box": (-15, 572, 249, 724), "label": "dresser"},
        {"conf": 0.127, "box": (-12, 231, 880, 732), "label": "dresser"},
        {"conf": 0.1216, "box": (1248, 286, 1272, 496), "label": "chest of drawers"},
    ],
    # session-20260925-045109-rog/perception/0002-highlight-my_dresser/pass_00004.json
    "my dresser": [
        {"conf": 0.6992, "box": (676, 233, 876, 532), "label": "dresser"},
        {"conf": 0.6953, "box": (680, 238, 880, 536), "label": "cabinet"},
        {"conf": 0.6484, "box": (676, 245, 876, 532), "label": "chest of drawers"},
        {"conf": 0.4043, "box": (528, 278, 688, 544), "label": "cabinet"},
        {"conf": 0.3516, "box": (528, 278, 688, 544), "label": "dresser"},
        {"conf": 0.2793, "box": (528, 278, 688, 544), "label": "chest of drawers"},
        {"conf": 0.2109, "box": (1248, 286, 1272, 500), "label": "cabinet"},
        {"conf": 0.1562, "box": (1248, 286, 1272, 500), "label": "dresser"},
        {"conf": 0.1494, "box": (-16, 442, 360, 732), "label": "cabinet"},
        {"conf": 0.1318, "box": (528, 284, 880, 476), "label": "chest of drawers"},
        {"conf": 0.1299, "box": (1248, 290, 1280, 504), "label": "chest of drawers"},
        {"conf": 0.1216, "box": (520, 296, 880, 452), "label": "cabinet"},
    ],
    # session-20260925-033523-rog/perception/0003-highlight-microphone/pass_00026.json
    "microphone": [
        {"conf": 0.7148, "box": (588, 292, 688, 394), "label": "microphone"},
        {"conf": 0.5703, "box": (900, 54, 1280, 276), "label": "microphone"},
        {"conf": 0.4707, "box": (720, 52, 1288, 360), "label": "microphone"},
        {"conf": 0.4023, "box": (588, 292, 768, 414), "label": "microphone"},
        {"conf": 0.3223, "box": (596, 292, 844, 536), "label": "microphone"},
        {"conf": 0.2949, "box": (580, 59, 1280, 544), "label": "microphone"},
        {"conf": 0.1621, "box": (572, 302, 760, 720), "label": "microphone"},
    ],
    # session-20260925-045109-rog/perception/0004-highlight-microphone/pass_00003.json
    "one microphone": [
        {"conf": 0.9492, "box": (498, 179, 780, 300), "label": "microphone"},
        {"conf": 0.1982, "box": (800, 3, 1280, 150), "label": "microphone"},
        {"conf": 0.1553, "box": (696, 74, 824, 157), "label": "microphone"},
    ],
}


def test_real_deduplicated_boxes_come_back_unchanged():
    """Owner TR17: a CPU test on real SAM3 boxes. Distinct objects survive, and so do
    boxes of other labels over the same object (the dedup is per label)."""
    from sam3.model import _dedup_overlaps
    for name, dets in REAL_PASSES.items():
        assert _dedup_overlaps([dict(d) for d in dets]) == dets, name


def test_a_real_box_and_a_copy_of_its_inner_part_become_one_box():
    """SAM3 emits nested boxes for one object: the inner part, scored lower, goes."""
    from sam3.model import _dedup_overlaps
    for name, dets in REAL_PASSES.items():
        outer = dets[0]
        x0, y0, x1, y1 = outer["box"]
        dx = (x1 - x0) // 5
        dy = (y1 - y0) // 5
        inner = {
            "conf": outer["conf"] - 0.01,
            "box": (x0 + dx, y0 + dy, x1 - dx, y1 - dy),
            "label": outer["label"],
        }
        assert _dedup_overlaps([dict(outer), inner]) == [outer], name
