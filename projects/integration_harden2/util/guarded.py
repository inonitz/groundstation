"""The ONE home of the try/except blocks around third-party calls that report failure
only by a throw (house rule: no exceptions in our code; a try exists only at a
third-party boundary with no non-throwing API). Each helper turns the throw into a
return value, and every caller reads a status instead.

One try per failure domain (the audit:
docs/audit-harden2-try-except-necessity-2026-09-23.md):
    http_request  http.client: a refused connection, a timeout, a broken reply
    parse_json    json: text that is not JSON
    file_op       the filesystem: open / write / fsync / rename / replace
    stream_call   asyncio streams: the peer left, a line over the stream limit
"""
import asyncio
import http.client
import json
import os


# ======================================== HTTP ========================================
def http_request(host, port, method, path, body=None, headers=None, timeout=3.0):
    """One HTTP request. -> (code, reply_body, error). code is the int status of ANY
    reply (an error status is a reply, not a failure); None when no usable reply came
    back, and then error says why."""
    code = None
    reply = b""
    conn = http.client.HTTPConnection(host, port, timeout=timeout)

    try:
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        reply = response.read()
        code = response.status
    # refused, reset, timed out (all OSError), or a malformed / short reply
    except (OSError, http.client.HTTPException) as e:
        conn.close()
        return None, b"", repr(e)

    conn.close()
    return code, reply, ""


# ======================================== JSON ========================================
def parse_json(text):
    """-> (True, value), or (False, the reason) when the text is not JSON."""
    try:
        return True, json.loads(text)
    # json reports bad input only by a throw
    except json.JSONDecodeError as e:
        return False, str(e)


# ===================================== filesystem =====================================
def file_op(what, fn, *args):
    """Run one filesystem step fn(*args). -> True when it worked. A failure prints
    `what` and the reason, and returns False: the caller decides what it means."""
    try:
        fn(*args)
    # the filesystem reports a failed step only by a throw
    except OSError as e:
        print(f"[fs] {what} failed: {e}", flush=True)
        return False
    return True


def _write_synced(path, data, mode):
    with open(path, mode) as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    return


def atomic_write(path, data):
    """Write bytes so a crash leaves the old file or the new one, never a truncated
    mix: a temp file, fsync, then a rename over the target (atomic on one
    filesystem). -> True when written."""
    tmp = path + ".tmp"
    if not file_op(f"write {tmp}", _write_synced, tmp, data, "wb"):
        return False
    return file_op(f"rename {tmp} -> {path}", os.replace, tmp, path)


def append_line(path, line):
    """Append one text line and fsync it. -> True when written."""
    return file_op(f"append to {path}", _write_synced, path, line, "a")


def rename(src, dst):
    """-> True when src now lives at dst."""
    return file_op(f"rename {src} -> {dst}", os.rename, src, dst)


# =================================== asyncio streams ===================================
async def stream_call(awaitable):
    """Await one asyncio stream call (readline, readexactly, drain). -> (True, result),
    or (False, the reason) when the peer left (ConnectionError, a short read) or a line
    passed the stream limit (ValueError). Untrusted network input never reaches the
    crash handler."""
    try:
        return True, await awaitable
    except (ConnectionError, asyncio.IncompleteReadError, ValueError) as e:
        return False, repr(e)
