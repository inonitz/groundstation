"""Tests for audio/: the mic ASR processes the app starts (the whisper ASR server + the keyboard hook).
No process is started here: the supervisor is a recorder."""
import http.server
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from audio import ros2_asr
from audio.phone_asr import PhoneEars
from system.status import BOARD, RECOVERING, UP


class RecordingSupervisor:
    def __init__(self):
        self.started = []

    def start(self, name, argv, env=None, ready=None, ready_timeout_s=0, log_path=None):
        self.started.append({"name": name, "argv": argv, "env": env, "log_path": log_path})


def test_asr_argv_is_built_from_config(monkeypatch):
    monkeypatch.setattr(config, "RECORD_SESSION", True)
    monkeypatch.setattr(config, "ASR_CAPTURE_DEVICE", None)
    argv = ros2_asr.asr_argv()
    assert argv[0] == os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_asr_server")
    assert f"--backend={config.ASR_BACKEND}" in argv and f"--model={config.ASR_MODEL_PATH}" in argv
    assert f"--language={config.ASR_LANGUAGE}" in argv
    assert "--record" in argv and f"--recordDir={config.CLIPS_DIR}" in argv
    assert not any(a.startswith("--captureid") for a in argv)


def test_capture_device_and_no_recording(monkeypatch):
    monkeypatch.setattr(config, "RECORD_SESSION", False)
    monkeypatch.setattr(config, "ASR_CAPTURE_DEVICE", "3")
    argv = ros2_asr.asr_argv()
    assert "--captureid=3" in argv and "--record" not in argv


def test_clips_land_where_the_session_log_reads_them():
    assert os.path.basename(config.CLIPS_DIR) == "asr_clips"


def test_start_services_starts_asr_and_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CLIPS_DIR", str(tmp_path / "asr_clips"))
    sup = RecordingSupervisor()
    ros2_asr.start_services(sup, str(tmp_path))
    names = [s["name"] for s in sup.started]
    assert names == ["asr", "keys"]
    asr, keys = sup.started
    assert "PULSE_SERVER" in asr["env"] and asr["log_path"] == str(tmp_path / "proc-asr.log")
    assert keys["argv"] == [os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_keyboard_hook")]
    assert os.path.isdir(tmp_path / "asr_clips")


# ==================== phone speech channel (review R7) ====================


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def _listening(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def test_extract_drops_a_malformed_line_and_keeps_good_ones():
    ears = PhoneEars.__new__(PhoneEars)                 # the parser only; no server
    assert ears._extract('{"text": " hello "}') == "hello"
    assert ears._extract("plain words") == "plain words"
    assert ears._extract('{"text": "cut off') == ""
    assert ears._extract("[1, 2]") == "[1, 2]" and ears._extract('{"no_text": 1}') == ""


def test_real_listener_survives_garbage_drops_and_short_bodies():
    heard = []
    port = _free_port()
    PhoneEars(heard.append, host="127.0.0.1", port=port)
    assert _wait_for(lambda: _listening(port))
    assert _wait_for(lambda: BOARD.state("phone speech") == UP)
    with socket.create_connection(("127.0.0.1", port)) as s:    # TCP: garbage, then a good line on the SAME socket
        s.sendall(b'{"text": "broken\n{"text": "take off"}\n')
        assert _wait_for(lambda: heard == ["take off"])
    with socket.create_connection(("127.0.0.1", port)) as s:    # HTTP body shorter than its Content-Length
        s.sendall(b"POST /input HTTP/1.1\r\nContent-Length: 500\r\n\r\n{\"text\": \"x\"}")
        s.shutdown(socket.SHUT_WR)
    with socket.create_connection(("127.0.0.1", port)) as s:    # a bad Content-Length header
        s.sendall(b"POST /input HTTP/1.1\r\nContent-Length: abc\r\n\r\n")
        s.shutdown(socket.SHUT_WR)
    with socket.create_connection(("127.0.0.1", port)) as s:    # the listener still serves a good request
        body = b'{"text": "land"}'
        s.sendall(b"POST /input HTTP/1.1\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
        assert _wait_for(lambda: heard == ["take off", "land"])



def test_an_over_long_line_ends_only_that_connection():
    """R12: a line over asyncio's 64 KiB limit ends that connection; the listener keeps serving."""
    heard = []
    port = _free_port()
    PhoneEars(heard.append, host="127.0.0.1", port=port)
    assert _wait_for(lambda: _listening(port))
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall(b"x" * 70000)                                  # no newline, over the limit
        s.shutdown(socket.SHUT_WR)
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall(b'{"text": "hover"}\n')
        assert _wait_for(lambda: heard == ["hover"])



# ==================== phone TTS recovery (owner ruling R10) ====================
HARDEN2 = os.path.join(os.path.dirname(__file__), "..")


class _FakePhone(http.server.BaseHTTPRequestHandler):
    """Stands in for the phone's POST /tts: answers 200."""
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        return


def _phone(port):
    srv = http.server.HTTPServer(("127.0.0.1", port), _FakePhone)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _phone_voice(monkeypatch, port):
    from audio import tts_io
    for key, value in (("TTS_BACKEND", "phone"), ("TTS_HOST", "127.0.0.1"), ("TTS_PORT", port),
                       ("TTS_TIMEOUT", 0.5), ("SERVICE_RETRY_SECONDS", 0.3), ("SUPERVISOR_MAX_RESTARTS", 3)):
        monkeypatch.setattr(config, key, value)
    return tts_io.Voice()


def test_tts_is_up_at_start_and_recovers_when_the_phone_comes_back(monkeypatch):
    port = _free_port()
    srv = _phone(port)
    voice = _phone_voice(monkeypatch, port)
    assert BOARD.state("tts") == UP
    srv.shutdown()
    srv.server_close()
    seen = []
    orig = BOARD.report
    monkeypatch.setattr(BOARD, "report", lambda s, st, d="": (seen.append((s, st)), orig(s, st, d))[1])
    back = threading.Timer(0.5, lambda: seen.append(("phone", _phone(port))))   # the phone returns mid-recovery
    back.start()
    assert voice._say_phone("שלום") is True
    assert ("tts", RECOVERING) in seen and BOARD.state("tts") == UP
    next(v for k, v in seen if k == "phone").shutdown()


def test_tts_gives_up_after_the_restart_budget_and_dies_with_the_reason():
    port = _free_port()
    code = textwrap.dedent(f'''
        import sys, threading, http.server; sys.path.insert(0, {HARDEN2!r})
        import config
        config.TTS_BACKEND, config.TTS_HOST, config.TTS_PORT = "phone", "127.0.0.1", {port}
        config.TTS_TIMEOUT, config.SERVICE_RETRY_SECONDS, config.SUPERVISOR_MAX_RESTARTS = 0.3, 0.1, 2
        class P(http.server.BaseHTTPRequestHandler):
            def do_POST(self): self.send_response(200); self.end_headers()
        srv = http.server.HTTPServer(("127.0.0.1", {port}), P)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        from audio import tts_io
        v = tts_io.Voice()
        srv.shutdown(); srv.server_close()
        v._say_phone("x")
        print("STILL RUNNING", flush=True)
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "STILL RUNNING" not in r.stdout
    assert "[status] tts: RECOVERING -- phone /tts did not answer; retry 2/2" in r.stdout
    assert "[status] tts: FAILED" in r.stdout and "failed 3 times; 2 recoveries failed" in r.stderr



def test_a_slow_command_does_not_let_the_duplicate_copy_through():
    """R21 SAFETY: the phone sends each command over REST AND TCP. A slow first command (Gemma planning)
    must not block the loop so long that the second copy misses the dedup window and flies twice."""
    heard = []

    def slow(text):
        heard.append(text)
        time.sleep(2.5)                                     # longer than the 1.5 s dedup window
    port = _free_port()
    PhoneEars(slow, host="127.0.0.1", port=port)
    assert _wait_for(lambda: _listening(port))
    body = b'{"text": "fly forward 3 meters"}'
    rest = socket.create_connection(("127.0.0.1", port))
    rest.sendall(b"POST /input HTTP/1.1\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    time.sleep(0.3)                                          # the TCP copy lands while command 1 is planning
    with socket.create_connection(("127.0.0.1", port)) as tcp:
        tcp.sendall(body + b"\n")
        time.sleep(3.5)
    rest.close()
    assert heard == ["fly forward 3 meters"]                 # delivered ONCE



def test_an_http_error_from_the_phone_is_a_failed_delivery_and_retries_speak_the_newest(monkeypatch):
    """R28: a 500 from /tts is not 'spoken'; while it recovers, a newer answer replaces the stale one."""
    port = _free_port()
    srv = _phone(port)
    voice = _phone_voice(monkeypatch, port)
    codes = iter([500, 200])
    sent = []

    def post(body):
        sent.append(body["text"])
        return next(codes)
    monkeypatch.setattr(voice, "_post", post)
    with voice._lock:
        voice._pending = "the newer answer"
    assert voice._say_phone("the old answer") is True
    assert sent == ["the old answer", "the newer answer"] and BOARD.state("tts") == UP
    srv.shutdown()
