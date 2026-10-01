"""The vision-backend contract: what the vision system needs from a vision model. SAM3
is the one backend today (sam3/model.py); perception2 and the loader import this file,
which imports no model code."""
from typing import Protocol

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
