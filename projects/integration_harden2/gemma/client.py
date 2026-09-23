"""The ONE interface to Gemma, for the recognizer and perception2 alike.

request(messages, ...) sends one chat completion and returns (True, text) or (False, ""). The caller
builds its own messages and parses its own reply. A failure is a False the caller reads; the server's
health is on the status panel (the supervisor reports it). Temperature is always 0.
A reply that is not the chat-completions shape (bad JSON, a short read, a missing key, null content)
is a failed request too, never an exception (review finding R6).
"""
import http.client
import json
import urllib.error
import urllib.request

import config


def _content(body):
    """body["choices"][0]["message"]["content"] when every level has the right type, else None. No throw."""
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    return content if isinstance(content, str) else None


def request(messages, grammar=None, max_tokens=256, timeout_s=config.VLM_TIMEOUT, port=config.LLAMA_SERVER_PORT):
    """POST one chat completion. -> (True, reply_text) on success, (False, "") on any failure."""
    payload = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.0}
    if grammar:
        payload["grammar"] = grammar
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 json.dumps(payload).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            raw = r.read()
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:   # refused, HTTP error, timeout, short read
        print(f"[gemma] request failed: {e!r}", flush=True)
        return False, ""
    try:
        body = json.loads(raw)
    except json.JSONDecodeError as e:                 # json reports a malformed body only by a throw
        print(f"[gemma] reply is not JSON: {e}", flush=True)
        return False, ""
    text = _content(body)
    if text is None:
        print(f"[gemma] reply has no choices[0].message.content: {str(body)[:120]}", flush=True)
        return False, ""
    return True, text.strip()
