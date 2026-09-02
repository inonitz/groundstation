"""The per-utterance flight recorder (the owner's database, 2026-09-02).

One JSONL line per utterance: what was heard, what every stage did, what came out, how long
it took. Files live under traces/ next to this package, one per session, and are gitignored --
transcripts and audio never enter git.
"""
import json
import os
import time


class Trace:

    def __init__(self, directory=None):
        directory = directory or os.path.join(os.path.dirname(__file__), "..", "traces")
        os.makedirs(directory, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.path = os.path.join(directory, f"session-{stamp}.jsonl")
        self._n = 0

    def record(self, **fields):
        self._n += 1
        fields["utterance"] = self._n
        fields["ts"] = round(time.time(), 3)
        with open(self.path, "a") as f:
            f.write(json.dumps(fields, ensure_ascii=False) + "\n")
