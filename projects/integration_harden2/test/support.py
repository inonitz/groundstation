"""Shared test helpers (not a test file).
RecordingPhone: a REAL local HTTP server that stands in for the phone app, with the REAL
DjiApp client and the REAL Control in front of it. Loopback only (127.0.0.1). Each
client owns its "dji app" row, so no test sees another test's row.
state_of: the state on a part's first status row (a part owns its rows).
StandInBackend: answers the vision service's detect() calls (SAM3 itself is GPU-only)."""
import http.server
import json
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from control.flight import Control
from dji_app.client import DjiApp
from perception2.backend import DETECT_NOT_READY, DETECT_OK


def wait_for(pred, timeout):
    """Poll pred() until it is true or timeout seconds pass. -> whether it came true."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def state_of(source):
    """The state on the first row of a part's status() (every part owns its rows)."""
    return source.status()[0][1]


class RecordingPhone:
    """Records every POST as (path, json-body) and answers `code`. GET
    /status/ (the read-only telemetry the probe uses) answers 200 and is
    not recorded. .dji and .control talk to it."""

    def __init__(self, code=200, port=0):
        seen = self.seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                seen.append((self.path, json.loads(raw) if raw else None))
                self.send_response(code)
                self.end_headers()

            def do_GET(self):
                self.send_response(200 if self.path.startswith("/status") else 404)
                self.end_headers()

            def log_message(self, *args):
                return

        self.srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.dji = DjiApp("127.0.0.1", self.srv.server_address[1])
        self.control = Control(self.dji)

    def paths(self):
        return [path for path, _ in self.seen]

    def close(self):
        self.dji.close()
        self.srv.shutdown()
        self.srv.server_close()
        return


def dead_port():
    """A loopback port with nothing listening: every request to it is UNREACHABLE."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


CAR = [{"label": "car", "conf": 0.9, "box": (10, 10, 40, 40)},
       {"label": "car", "conf": 0.8, "box": (60, 60, 90, 90)}]


class StandInBackend:
    """Answers detect() from `hits[first concept]` (a list, or DETECT_NOT_READY) after
    `delay` s.
    Records each call's start time and the most forward passes that ever overlapped."""

    def __init__(self, hits, delay=0.0):
        self.hits, self.delay = hits, delay
        self.starts, self.inside, self.max_inside = [], 0, 0
        self._lock = threading.Lock()

    def detect(self, frame, phrase, floor):
        with self._lock:
            self.inside += 1
            self.max_inside = max(self.max_inside, self.inside)
            self.starts.append(time.monotonic())
        time.sleep(self.delay)
        with self._lock:
            self.inside -= 1
        # the service expands concepts ("car" -> "car, van, truck"): match the first one
        answer = self.hits.get(phrase.split(",")[0].strip(), [])
        if answer == DETECT_NOT_READY:
            return DETECT_NOT_READY, []
        return DETECT_OK, [dict(h) for h in answer]

    def mask_for_box(self, frame, box):
        return None


PLAN_FAILED = "failed"


class PlannerStub:
    """Stands in for gemma.client.Gemma as the recognizer's planner: answer(he2) returns
    the plan dict to reply with, None (a reply that is not a plan), or PLAN_FAILED (the
    request itself failed)."""

    def __init__(self, answer):
        self.answer = answer
        self.requests = []

    def request(self, messages, grammar=None, max_tokens=256, timeout_s=0, label=""):
        he2 = messages[-1]["content"]
        self.requests.append(he2)
        plan = self.answer(he2)
        if plan == PLAN_FAILED:
            return False, ""
        if plan is None:
            return True, "not a plan"
        return True, json.dumps(plan)

    def close(self):
        return


def no_plan():
    """A planner whose every reply is not a plan (a model call would not fly)."""
    return PlannerStub(lambda he: None)


class GemmaStub:
    """Stands in for gemma.client.Gemma (the model needs the GPU): every request answers
    `reply` (True, text), in the vision prompt's labelled format by default."""

    def __init__(
        self,
        reply="LONG RESPONSE: a room\nSHORT RESPONSE: room\nHIGHLIGHT: none"
    ):
        self.reply = reply
        self.requests = []

    def request(self, messages, grammar=None, max_tokens=256, timeout_s=0, label=""):
        self.requests.append(messages)
        return True, self.reply

    def close(self):
        return
