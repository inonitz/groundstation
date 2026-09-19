"""The vision-backend contract, and the registry the highlight engine picks from.

A vision backend answers two calls (below). The engine builds ONE backend at startup, chosen by
SCENE_SEG, then calls it directly -- the choice is one-time, not a per-frame dispatch. To add a
backend: write a class with these two methods, then add one line to BACKENDS.
"""
from typing import Protocol


class VisionBackend(Protocol):
    """What the highlight engine needs from a vision model. SAM3 is the one backend today."""
    def detect(self, frame_bgr, phrase, conf=0.30, topk=8):
        """BGR frame + English noun phrase -> up to topk hits: [{'label','conf','box'(x1,y1,x2,y2)}]."""
        ...
    def mask_for_box(self, frame_bgr, box):
        """The mask this backend cached for one box in the last detect(); None on a miss."""
        ...


def _sam3():
    from perception2.sam3_backend import Sam3Backend   # lazy: the heavy model deps load only when built
    return Sam3Backend()


BACKENDS = {"sam3": _sam3}      # SCENE_SEG name -> zero-arg factory. One line per new backend.
