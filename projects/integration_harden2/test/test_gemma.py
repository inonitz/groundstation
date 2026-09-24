"""Tests for gemma/: the server's command line and start-up, and the ONE client.
The client is tested against a real local HTTP server that speaks the
chat-completions shape; no model is loaded."""
import http.server
import json
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from gemma import client, server


# ==================== server ====================
def test_argv_is_built_from_config():
    args = server.argv(config.LLAMA_SERVER_PORT, False)
    assert args[args.index("-m") + 1] == config.GEMMA_MODEL_PATH
    assert args[args.index("--mmproj") + 1] == config.GEMMA_MMPROJ_PATH
    assert args[args.index("--port") + 1] == str(config.LLAMA_SERVER_PORT)
    assert args[args.index("-np") + 1] == "1" and args[args.index("--temp") + 1] == "0.0"


def test_thinking_off_needs_both_flags():
    off = server.thinking_flags(False)
    assert '{"enable_thinking":false}' in off and "--reasoning-budget" in off
    assert '{"enable_thinking":true}' in server.thinking_flags(True)
    assert all(flag in server.argv(1, True) for flag in server.thinking_flags(True))


def test_port_up_is_false_on_a_closed_port():
    assert server.port_up(1) is False


def test_the_process_is_one_spec_for_the_app_and_the_benches(tmp_path):
    spec = server.process(str(tmp_path))
    assert spec.name == "gemma" and spec.argv == server.argv(
        config.LLAMA_SERVER_PORT, config.GEMMA_THINKING_ENABLED)
    assert spec.ready_timeout_s >= 60
    assert spec.log_path == str(tmp_path / "proc-gemma.log")
    assert spec.required                   # a laptop part: past the budget the app dies
    bench = server.process(str(tmp_path), port=18091, thinking=True)
    assert "18091" in bench.argv
    assert '{"enable_thinking":true}' in bench.argv


# ==================== client ====================
class _Chat(http.server.BaseHTTPRequestHandler):
    """A stand-in llama-server. `reply` sets what the next POST answers: a body (bytes)
    and a status, or "short" = promise more bytes than it sends (a short read)."""
    seen = []
    reply = (
        json.dumps({"choices": [{"message": {"content": "  hello  "}}]}).encode(),
        200,
    )

    def do_POST(self):
        _Chat.seen.append(
            json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        )
        if _Chat.reply == "short":
            self.send_response(200)
            self.send_header("Content-Length", "1000")
            self.end_headers()
            self.wfile.write(b'{"choices":')
            return
        body, code = _Chat.reply
        if self.path.startswith("/fail"):
            code = 500
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


def _serve():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Chat)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_request_returns_true_and_the_text():
    srv = _serve()
    ok, text = client.Gemma(srv.server_port).request(
        [{"role": "user", "content": "hi"}],
        grammar="root ::= x",
        max_tokens=7
    )
    srv.shutdown()
    assert ok and text == "hello"
    sent = _Chat.seen[-1]
    assert (
        sent["grammar"] == "root ::= x"
        and sent["max_tokens"] == 7
        and sent["temperature"] == 0.0
    )


def test_request_returns_false_when_nothing_listens():
    assert client.Gemma(1).request([{"role": "user", "content": "hi"}]) == (False, "")


def test_request_returns_false_on_an_http_error():
    good = _Chat.reply
    _Chat.reply = (good[0], 500)              # the server answers HTTP 500
    srv = _serve()
    ok, text = client.Gemma(srv.server_port).request([{"role": "user", "content": "hi"}])
    srv.shutdown()
    _Chat.reply = good
    assert (ok, text) == (False, "")


def test_a_malformed_reply_is_a_failed_request_not_an_exception():
    good = _Chat.reply
    bad_replies = [
        (b"<html>oops</html>", 200),
        (b"{}", 200),
        (b'{"choices": []}', 200),
        (json.dumps({"choices": [{"message": {"content": None}}]}).encode(), 200),
        "short",
    ]
    for bad in bad_replies:
        _Chat.reply = bad
        srv = _serve()
        result = client.Gemma(srv.server_port).request(
            [{"role": "user", "content": "hi"}], timeout_s=3
        )
        srv.shutdown()
        assert result == (False, ""), bad
    _Chat.reply = good
