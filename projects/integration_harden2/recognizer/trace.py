"""The per-utterance flight recorder (the owner's database, 2026-09-02).

One JSONL line per utterance: what was heard, what every stage did, what came out, how long
it took. One file per session under <repo>/logs/traces/ (outside the frozen harden2 tree; logs/ is
gitignored, so transcripts and audio never enter git).
"""
import json
import os
import time


class Trace:

    def __init__(self, directory=None):
        # Default OUTSIDE the frozen harden2 tree: <repo>/logs/traces (logs/ is gitignored).
        directory = directory or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "logs", "traces")
        os.makedirs(directory, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(directory, f"session-{stamp}.jsonl")
        self._n = 0

    def record(self, **fields):
        """Append one line. -> True when written. A failed write is logged and never crashes a session
        (the same policy as session_log: status, not an exception)."""
        self._n += 1
        fields["utterance"] = self._n
        fields["ts"] = round(time.time(), 3)
        try:
            with open(self.path, "a") as f:
                f.write(json.dumps(fields, ensure_ascii=False) + "\n")
        except OSError as e:                      # the filesystem reports a failed write only by a throw
            print(f"[trace] write failed: {self.path}: {e}", flush=True)
            return False
        return True
