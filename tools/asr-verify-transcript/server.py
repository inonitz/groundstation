#!/usr/bin/env python3
"""The labelling page for the 139 recordings (owner UI1, 2026-09-29).

A local web server on Python's standard library, bound to 127.0.0.1: it serves the page
(index.html), each clip's audio, and a small JSON API over labels.Recordings. Every save
rewrites datasets/asr/recordings.json at once (atomically), so the owner can stop at any
clip and resume later.

Run:
    python3 /root/groundstation/tools/asr-verify-transcript/server.py [--port 8766]
        [--out PATH]
Never run it while another tool writes the same recordings file.
"""
import http.server
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import labels                                                 # noqa: E402
from util.guarded import parse_json                           # noqa: E402

PORT = 8766
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
}


def option(argv, flag, default):
    """The value after a flag, or the default."""
    if flag not in argv:
        return default
    return argv[argv.index(flag) + 1]


def make_handler(recordings):
    """A request handler class bound to one Recordings."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def reply(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        def reply_json(self, code, value):
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.reply(code, body, "application/json; charset=utf-8")
            return

        def clip_index(self, text):
            """A clip number from the path -> its index, or None when out of range."""
            if not text.isdigit():
                return None
            index = int(text)
            if index >= recordings.total():
                return None
            return index

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            parts = path.strip("/").split("/")
            index = None

            if path in STATIC:
                name, content_type = STATIC[path]
                with open(os.path.join(HERE, name), "rb") as src:
                    self.reply(200, src.read(), content_type)
                return
            if path == "/api/state":
                self.reply_json(200, {
                    "total": recordings.total(),
                    "saved": recordings.saved_count(),
                    "first_unsaved": recordings.first_unsaved(),
                    "out": recordings.path,
                })
                return
            if len(parts) == 3 and parts[:2] == ["api", "clip"]:
                index = self.clip_index(parts[2])
                if index is None:
                    self.reply_json(404, {"error": "no such clip"})
                    return
                self.reply_json(200, recordings.clip(index))
                return
            if len(parts) == 2 and parts[0] == "audio":
                index = self.clip_index(parts[1])
                if index is None:
                    self.reply_json(404, {"error": "no such clip"})
                    return
                wav = os.path.join(labels.ROOT, labels.wav_of(recordings.rows[index]))
                with open(wav, "rb") as src:
                    self.reply(200, src.read(), "audio/wav")
                return
            self.reply_json(404, {"error": "not found"})
            return

        def read_body(self):
            """-> (value, error): the request's JSON object."""
            size = int(self.headers.get("Content-Length") or 0)
            ok, value = parse_json(self.rfile.read(size).decode("utf-8"))
            if not ok or not isinstance(value, dict):
                return None, "the request is not a JSON object"
            return value, None

        def do_POST(self):
            body, error = self.read_body()
            expect = None
            index = None
            if error is not None:
                self.reply_json(400, {"error": error})
                return

            if self.path == "/api/parse":
                expect, error = labels.read_expect(body.get("text", ""))
                if error is not None:
                    self.reply_json(200, {"ok": False, "error": error})
                    return
                self.reply_json(200, {
                    "ok": True,
                    "expect": expect,
                    "plan": labels.plan_words(expect),
                    "rows": labels.rows_of(expect),
                    "vision": labels.vision_of(expect),
                })
                return
            if self.path == "/api/nearest":
                index = self.clip_index(str(body.get("index", "")))
                text = body.get("text")
                if index is None or not isinstance(text, str):
                    self.reply_json(400, {"error": "nearest needs index and text"})
                    return
                self.reply_json(200, {"options": recordings.rerank(index, text)})
                return
            if self.path == "/api/vision":
                expect, error = labels.vision_expect(
                    body.get("kind", "any"),
                    body.get("words", "")
                )
                if error is not None:
                    self.reply_json(200, {"ok": False, "error": error})
                    return
                self.reply_json(200, {
                    "ok": True,
                    "expect": expect,
                    "plan": labels.plan_words(expect),
                })
                return
            if self.path == "/api/rows":
                expect, error = labels.expect_from_rows(body.get("rows") or [])
                if error is not None:
                    self.reply_json(200, {"ok": False, "error": error})
                    return
                self.reply_json(200, {
                    "ok": True,
                    "expect": expect,
                    "plan": labels.plan_words(expect),
                })
                return
            if self.path == "/api/save":
                index = self.clip_index(str(body.get("index", "")))
                expect = body.get("expect")
                he = body.get("he")
                # an empty sentence is valid: nothing was said (owner B4 (7))
                if (
                    index is None
                    or not isinstance(expect, dict)
                    or not isinstance(he, str)
                ):
                    self.reply_json(400, {"error": "a save needs index, he and expect"})
                    return
                removed = body.get("removed")
                if removed is not None and not str(removed).strip():
                    self.reply_json(400, {"error": "a removal needs its reason"})
                    return
                count = recordings.save(
                    index,
                    he,
                    expect,
                    int(body.get("option", 0)),
                    removed=str(removed).strip() if removed is not None else None
                )
                self.reply_json(200, {
                    "ok": True,
                    "saved": count,
                    "first_unsaved": recordings.first_unsaved(),
                })
                return
            self.reply_json(404, {"error": "not found"})
            return

    return Handler


def serve(recordings, port):
    """Build the server (not started). port 0 picks a free port."""
    return http.server.ThreadingHTTPServer(
        ("127.0.0.1", port),
        make_handler(recordings)
    )


def main():
    argv = sys.argv[1:]
    out = option(argv, "--out", labels.OUT)
    port = int(option(argv, "--port", PORT))
    recordings = labels.Recordings(out)
    server = serve(recordings, port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"{recordings.saved_count()}/{recordings.total()} clips saved in {out}")
    print(f"open {url}  (Ctrl+C stops it)", flush=True)
    server.serve_forever()
    return


if __name__ == "__main__":
    main()
