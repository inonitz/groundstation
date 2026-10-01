"""The SAM3 SERVICE: the registry of vision backends and BackendLoader, which loads the
chosen one on its own thread at start and answers for it meanwhile.

The app builds ONE backend at startup, chosen by SCENE_SEG, then calls it directly -- the
choice is one-time, not a per-frame dispatch. To add a backend: write a class with the
two methods of sam3/contract.py, then add one line to BACKENDS.
"""
import threading

import numpy as np

import config
from runtime.fatal import die
from runtime.status import UP, Status
from sam3.contract import DETECT_NOT_READY, DETECT_OK


def _sam3():
    # torch and transformers load here, on the loader's thread at start, never when
    # the app imports its modules (owner S3, 2026-09-29)
    from sam3.model import Sam3Backend
    return Sam3Backend()


# SCENE_SEG name -> zero-arg factory. One line per new backend.
BACKENDS = {"sam3": _sam3}


class BackendLoader:
    """Loads the chosen backend on its own thread (the model takes seconds to minutes)
    and answers for it meanwhile: detect() returns (DETECT_NOT_READY, []) until it is
    loaded. Owns the "sam3" status row (status()). A load failure reaches the crash
    hook: the app dies (a required model). Every detect() is a real forward: no
    cache."""

    def __init__(self, seg, loader=None):
        make = loader or BACKENDS.get(seg)
        if make is None:
            die(
                f"SCENE_SEG={seg!r} has no vision backend "
                f"(known: {', '.join(sorted(BACKENDS))})"
            )

        self._make = make
        self._backend = None
        self._status = Status("sam3")        # STARTING until the model is loaded
        self.thread = threading.Thread(
            target=self._load,
            name="vision-backend-load",
            daemon=True
        )
        self.thread.start()
        return

    def close(self):
        """Nothing to release: the model is freed when the app exits."""
        return

    def status(self):
        """[(name, state, detail)]: the "sam3" row."""
        return [self._status.row()]

    def _load(self):
        """Load, then one warm-up pass on a blank camera-size frame (owner L1): the
        first pass of a fresh model is 1.4-2.1 s against 0.5 s warm, and rule 3.3 keeps
        that out of the run. The row turns UP after it."""
        backend = self._make()
        frame = np.zeros((config.CAM_H, config.CAM_W, 3), np.uint8)
        backend.detect(frame, config.SAM3_WARM_UP_PHRASE, conf=0.5, topk=1)
        self._backend = backend
        self._status.set(UP)
        return

    def detect(self, frame, phrase, floor):
        backend = self._backend
        if backend is None:
            return DETECT_NOT_READY, []
        status, dets = backend.detect(frame, phrase, conf=floor, topk=config.HL_TOPK)
        if status != DETECT_OK:
            return status, []
        return status, dets

    def mask_for_box(self, frame, box):
        backend = self._backend
        if backend is None:
            return None
        return backend.mask_for_box(frame, box)
