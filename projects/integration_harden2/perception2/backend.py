"""The vision-backend contract, and the registry the highlight engine picks from.

A vision backend answers two calls (below). The engine builds ONE backend at startup,
chosen by SCENE_SEG, then calls it directly -- the choice is one-time, not a per-frame
dispatch. To add a backend: write a class with these two methods, then add one line to
BACKENDS.
"""
import threading
from typing import Protocol

import config
from system.fatal import die
from system.status import UP, Status

# detect status codes. A status is a code the caller reads; detect never throws.
DETECT_OK = 0              # the call ran; hits may be empty (nothing matched)
DETECT_NOT_READY = 1       # the backend is still loading


class VisionBackend(Protocol):
    """What the highlight engine needs from a vision model. SAM3 is the one backend
    today."""
    def detect(self, frame_bgr, phrase, conf=0.30, topk=8):
        """BGR frame + English noun phrase -> (status, hits). status is a DETECT_* code
        above. hits: up to topk [{'label','conf','box'(x1,y1,x2,y2)}], empty unless
        status == DETECT_OK."""
        ...

    def mask_for_box(self, frame_bgr, box):
        """The mask this backend cached for one box in the last detect(); None on a
        miss."""
        ...


def _sam3():
    # lazy: the heavy model deps load only when built
    from perception2.sam3_backend import Sam3Backend
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
        self._backend = self._make()
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
