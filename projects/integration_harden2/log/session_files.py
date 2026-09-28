"""Finds a recorded session's files for the read-only tools (show.py, score.py,
perf_report.py): the newest session folder and its per-utterance log."""
import glob
import os

import config
from system.fatal import die


def latest_session():
    """The newest session folder under config.SESSIONS_ROOT; die when there is none. The
    read-only tools (show.py, score.py) use this."""
    found = sorted(glob.glob(os.path.join(config.SESSIONS_ROOT, "session-*")))
    if not found:
        die(f"no session folder under {config.SESSIONS_ROOT}")
    return found[-1]


def trace_file(root):
    """A session's per-utterance log: trace.jsonl (since 2026-09-12), else an older
    utterances.jsonl layout. The read-only tools (show.py, score.py) use this."""
    for name in ("trace.jsonl", "asr/utterances.jsonl", "utterances.jsonl"):
        path = os.path.join(root, *name.split("/"))
        if os.path.exists(path):
            return path
    return os.path.join(root, "trace.jsonl")
