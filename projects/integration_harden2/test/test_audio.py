"""Tests for audio/: speech in (the ROS mic source's process, the phone source over REAL
sockets, SpeechIn) and speech out (the phone voice over a REAL local HTTP server, the
laptop voice, SpeechOut)."""
import os
import socket
import subprocess
import sys
import textwrap
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from audio import asr_ros, tts_laptop
from audio.asr_phone import PhoneAsr
from audio.speech_in import SpeechIn
from audio.speech_out import SpeechOut
from audio.tts_phone import PhoneTts
from system.status import UP
from support import RecordingPhone, dead_port, state_of, wait_for


def test_asr_argv_is_built_from_config(monkeypatch):
    monkeypatch.setattr(config, "RECORD_SESSION", True)
    monkeypatch.setattr(config, "ASR_CAPTURE_DEVICE", None)
    argv = asr_ros.argv()
    assert argv[0] == os.path.join(config.NATIVE_BIN_DIR, "llm_to_action_asr_server")
    assert (
        f"--backend={config.ASR_BACKEND}" in argv
        and f"--model={config.ASR_MODEL_PATH}" in argv
    )
    assert f"--language={config.ASR_LANGUAGE}" in argv
    assert "--record" in argv and f"--recordDir={config.CLIPS_DIR}" in argv
    assert not any(a.startswith("--captureid") for a in argv)


def test_capture_device_and_no_recording(monkeypatch):
    monkeypatch.setattr(config, "RECORD_SESSION", False)
    monkeypatch.setattr(config, "ASR_CAPTURE_DEVICE", "3")
    argv = asr_ros.argv()
    assert "--captureid=3" in argv and "--record" not in argv


def test_clips_land_where_the_session_log_reads_them():
    assert os.path.basename(config.CLIPS_DIR) == "asr_clips"


# ==================== phone speech channel (review R7) ====================


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for(pred, timeout=5.0):
    return wait_for(pred, timeout)


def _listening(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def test_extract_drops_a_malformed_line_and_keeps_good_ones():
    ears = PhoneAsr.__new__(PhoneAsr)                 # the parser only; no server
    assert ears._extract('{"text": " hello "}') == "hello"
    assert ears._extract("plain words") == "plain words"
    assert ears._extract('{"text": "cut off') == ""
    assert ears._extract("[1, 2]") == "[1, 2]" and ears._extract('{"no_text": 1}') == ""


def test_real_listener_survives_garbage_drops_and_short_bodies():
    heard = []
    port = _free_port()
    listener = PhoneAsr(
        lambda text, source: heard.append(text),
        host="127.0.0.1",
        port=port
    )
    assert _wait_for(lambda: _listening(port))
    assert _wait_for(lambda: state_of(listener) == UP)
    # TCP: garbage, then a good line on the SAME socket
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall(b'{"text": "broken\n{"text": "take off"}\n')
        assert _wait_for(lambda: heard == ["take off"])
    # HTTP body shorter than its Content-Length
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall(
            b"POST /input HTTP/1.1\r\nContent-Length: 500\r\n\r\n{\"text\": \"x\"}"
        )
        s.shutdown(socket.SHUT_WR)
    # a bad Content-Length header
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall(b"POST /input HTTP/1.1\r\nContent-Length: abc\r\n\r\n")
        s.shutdown(socket.SHUT_WR)
    # the listener still serves a good request
    with socket.create_connection(("127.0.0.1", port)) as s:
        body = b'{"text": "land"}'
        s.sendall(
            b"POST /input HTTP/1.1\r\nContent-Length: "
            + str(len(body)).encode()
            + b"\r\n\r\n"
            + body
        )
        assert _wait_for(lambda: heard == ["take off", "land"])


def test_an_over_long_line_ends_only_that_connection():
    """R12: a line over asyncio's 64 KiB limit ends that
    connection; the listener keeps serving."""
    heard = []
    port = _free_port()
    PhoneAsr(
        lambda text, source: heard.append(text),
        host="127.0.0.1",
        port=port
    )
    assert _wait_for(lambda: _listening(port))
    with socket.create_connection(("127.0.0.1", port)) as s:
        # no newline, over the limit
        s.sendall(b"x" * 70000)
        s.shutdown(socket.SHUT_WR)
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall(b'{"text": "hover"}\n')
        assert _wait_for(lambda: heard == ["hover"])


HARDEN2 = os.path.join(os.path.dirname(__file__), "..")


def test_a_slow_command_does_not_let_the_duplicate_copy_through():
    """R21 SAFETY: the phone sends each command over REST AND TCP. A slow first
    command (Gemma planning) must not block the loop so long that the second copy
    misses the dedup window and flies twice."""
    heard = []

    def slow(text, source):
        heard.append(text)
        # longer than the 1.5 s dedup window
        time.sleep(2.5)
    port = _free_port()
    PhoneAsr(slow, host="127.0.0.1", port=port)
    assert _wait_for(lambda: _listening(port))
    body = b'{"text": "fly forward 3 meters"}'
    rest = socket.create_connection(("127.0.0.1", port))
    rest.sendall(
        b"POST /input HTTP/1.1\r\nContent-Length: "
        + str(len(body)).encode()
        + b"\r\n\r\n"
        + body
    )
    # the TCP copy lands while command 1 is planning
    time.sleep(0.3)
    with socket.create_connection(("127.0.0.1", port)) as tcp:
        tcp.sendall(body + b"\n")
        time.sleep(3.5)
    rest.close()
    assert heard == ["fly forward 3 meters"]                 # delivered ONCE


def test_the_asr_server_process_is_a_laptop_part(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CLIPS_DIR", str(tmp_path / "asr_clips"))
    spec = asr_ros.process(str(tmp_path))
    assert spec.name == "asr" and spec.argv == asr_ros.argv()
    assert "PULSE_SERVER" in spec.env and spec.log_path == str(tmp_path / "proc-asr.log")
    assert os.path.isdir(tmp_path / "asr_clips")
    assert spec.required                     # a laptop part: 3 restarts, then die


# ==================== speech in ====================
def test_speech_in_runs_every_source_and_names_it(monkeypatch):
    port = _free_port()
    heard = []
    monkeypatch.setattr(config, "PHONE_ASR_PORT", port)
    speech_in = SpeechIn(
        ["phone"],
        lambda text, source: heard.append((text, source))
    )
    assert _wait_for(lambda: _listening(port))
    with socket.create_connection(("127.0.0.1", port)) as s:
        s.sendall(b'{"text": "take off"}\n')
        assert _wait_for(lambda: heard == [("take off", "phone")])
    speech_in.close()


def test_an_unknown_speech_source_dies():
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {HARDEN2!r})
        from audio.speech_in import SpeechIn
        SpeechIn(["telepathy"], print)
        print("STILL RUNNING", flush=True)
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode != 0 and "STILL RUNNING" not in r.stdout
    assert "unknown sources ['telepathy']" in r.stderr


# ==================== speech out ====================
def test_the_phone_voice_is_a_request_to_the_phone_app():
    phone = RecordingPhone()
    assert PhoneTts(phone.dji).say("שלום") is True
    body = {"text": "שלום", "lang": config.TTS_LANG, "rate": config.TTS_RATE}
    assert phone.seen[-1] == ("/tts", body)
    phone.close()


def test_the_phone_voice_speaks_even_in_manual_mode():
    phone = RecordingPhone()
    phone.control.manual()           # transmit off: motion refused, speech is not
    assert PhoneTts(phone.dji).say("עצרתי") is True and phone.paths()[-1] == "/tts"
    phone.close()


def test_a_dead_phone_app_is_waiting_and_never_kills_the_app():
    """No answer: the speech fails, the "dji app" row goes WAITING (orange), the app
    lives."""
    from dji_app.client import DjiApp
    dji = DjiApp("127.0.0.1", dead_port(), timeout=0.3)
    assert PhoneTts(dji).say("שלום") is False
    assert _wait_for(lambda: state_of(dji) == "WAITING")
    dji.close()


def test_speech_out_sends_every_sentence_to_each_output():
    phone = RecordingPhone()
    speech_out = SpeechOut(["phone"], phone.dji)
    speech_out.say("שלום")
    assert _wait_for(lambda: phone.paths() == ["/tts"])
    speech_out.close()
    phone.close()


def test_an_unknown_speech_output_dies():
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {HARDEN2!r})
        from audio.speech_out import SpeechOut
        SpeechOut(["smoke signals"], None)
        print("STILL RUNNING", flush=True)
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode != 0 and "STILL RUNNING" not in r.stdout
    assert "unknown outputs" in r.stderr


class _StandInSoundDevice:
    """Stands in for sounddevice ONLY to inject a device error (a real device cannot fail
    on demand). `broken` = every play() throws."""
    class PortAudioError(Exception):
        pass

    def __init__(self, broken):
        self.broken = broken
        self.played = 0

    def play(self, samples, rate):
        if self.broken:
            raise self.PortAudioError("device unplugged")
        self.played += 1

    def wait(self):
        return

    def stop(self):
        return


def _laptop_voice():
    """A LaptopTts with the model calls stubbed (no model files needed)."""
    voice = tts_laptop.LaptopTts.__new__(tts_laptop.LaptopTts)
    voice._g2p = type("G2P", (), {"add_diacritics": lambda self, t: t})()
    voice._voice = type("Piper", (), {"create": lambda self, p, is_phonemes: (
        np.zeros(10), 16000)})()
    return voice


def test_the_laptop_voice_plays(monkeypatch):
    device = _StandInSoundDevice(broken=False)
    monkeypatch.setattr(tts_laptop, "sounddevice", device, raising=False)
    monkeypatch.setattr(tts_laptop, "phonemize", lambda text: text, raising=False)
    assert _laptop_voice().say("שלום") is True and device.played == 1


def test_the_laptop_voice_dies_at_once_on_a_playback_error():
    """Owner ruling 9a-1: no retry; the sound system itself broke."""
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {HARDEN2!r})
        sys.path.insert(0, {os.path.dirname(__file__)!r})
        from audio import tts_laptop
        from test_audio import _StandInSoundDevice, _laptop_voice
        tts_laptop.sounddevice = _StandInSoundDevice(broken=True)
        tts_laptop.phonemize = lambda text: text
        _laptop_voice().say("x")
        print("STILL RUNNING", flush=True)
    """)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=60, env={**os.environ, "MVD_HOME": "integration_harden2"})
    assert r.returncode != 0 and "STILL RUNNING" not in r.stdout
    # no catch: the crash hook dies with the device's own error
    assert "PortAudioError" in r.stderr and "device unplugged" in r.stderr

