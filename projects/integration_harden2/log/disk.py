"""The session record's disk writes: the start-up folder check and the atomic JSON and
JPEG writes. A failed write means the laptop's disk is broken: the app dies with the
reason (owner ruling 2026-09-23)."""
import json
import os

import cv2

from system.fatal import die
from util.guarded import atomic_write


def _written(ok, what):
    """A failed write means the laptop's disk is
    broken: die with the reason. Returns ok."""
    if not ok:
        die(
            f"the session record could not write {what}: "
            "the laptop disk refused a write"
        )
    return ok


def _writable_folder(path):
    """True when `path` exists and is writable, or its nearest existing parent is (so
    makedirs will succeed). A plain permission check: nothing throws."""
    probe = os.path.abspath(path)
    while not os.path.exists(probe):
        probe = os.path.dirname(probe)
    return os.path.isdir(probe) and os.access(probe, os.W_OK | os.X_OK)


def _atomic_json(path, obj, indent=1):
    """Write JSON atomically (util.guarded.atomic_write: the old file or the new one,
    never a truncated mix). A failed write dies (_written)."""
    data = json.dumps(obj, ensure_ascii=False, indent=indent).encode("utf-8")
    return _written(atomic_write(path, data), os.path.basename(path))


def _atomic_imwrite(path, frame):
    """The same guarantee for a JPEG frame: a kill mid-encode cannot leave a truncated
    image. cv2.imencode reports a failed encode as False, never a throw."""
    ok, jpeg = cv2.imencode(".jpg", frame)
    if not ok:
        print(f"[session] image encode failed: {path}", flush=True)
        return _written(False, os.path.basename(path))
    return _written(atomic_write(path, jpeg.tobytes()), os.path.basename(path))
