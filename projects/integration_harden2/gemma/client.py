"""The ONE interface to Gemma, for the recognizer and perception2 alike: the Gemma
service object. The app builds one Gemma(port) and hands it to both.

Gemma.request(messages, ...) sends one chat completion and returns (True, text) or
(False, ""). The caller builds its own messages and parses its own reply. A failure
is a False the caller reads; the server's health is on the status panel (the
supervisor reports it). Temperature is always 0.
A reply that is not the chat-completions shape (bad JSON, a short read, a missing
key, null content) is a failed request too, never an exception (review finding R6).
"""
import json
import time

import config
from log.perf import NO_PERF
from util.guarded import http_request, parse_json
from util.net import JSON_HEADERS


def _content(body):
    """body["choices"][0]["message"]["content"] when every level has the right type,
    else None. No throw."""
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices:
        return None
    if not isinstance(choices[0], dict):
        return None

    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None

    content = message.get("content")
    if not isinstance(content, str):
        return None
    return content


class Gemma:
    """One Gemma server, reached on 127.0.0.1:port."""

    def __init__(self, port=config.LLAMA_SERVER_PORT, perf=NO_PERF):
        self.port = port
        self._perf = perf
        return

    def close(self):
        """Nothing to release: every request is its own connection."""
        return

    def request(
        self,
        messages,
        grammar=None,
        max_tokens=256,
        timeout_s=config.VLM_TIMEOUT,
        label="request"
    ):
        """POST one chat completion. @label names the caller in the perf record (plan,
        vision). -> (True, reply_text) on success, (False, "") on any failure."""
        t0 = time.monotonic()
        ok, text = self._request(messages, grammar, max_tokens, timeout_s)
        self._perf.record("gemma", (time.monotonic() - t0) * 1000, label=label, ok=ok)
        return ok, text

    def _request(self, messages, grammar, max_tokens, timeout_s):
        payload = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.0}
        if grammar:
            payload["grammar"] = grammar

        code, raw, error = http_request(
            "127.0.0.1",
            self.port,
            "POST",
            "/v1/chat/completions",
            body=json.dumps(payload).encode(),
            headers=JSON_HEADERS,
            timeout=timeout_s
        )
        if code is None:
            print(f"[gemma] request failed: {error}", flush=True)
            return False, ""
        if code != 200:
            print(f"[gemma] request failed: HTTP {code}", flush=True)
            return False, ""

        ok, body = parse_json(raw)
        if not ok:
            print(f"[gemma] reply is not JSON: {body}", flush=True)
            return False, ""

        text = _content(body)
        if text is None:
            print(
                f"[gemma] reply has no choices[0].message.content: {str(body)[:120]}",
                flush=True
            )
            return False, ""
        return True, text.strip()
