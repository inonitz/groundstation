"""Voice = the demo's mouth. Speaks the VLM's answer so the loop is voice-in -> voice-out.

Hebrew only. Two backends:
  phone    -- POST /tts to the DJI phone app; it speaks via Android TextToSpeech (Google he-IL).
              Needs the phone reachable and on data. say() never raises into the caller.
  phonikud -- OFFLINE Hebrew on the laptop: phonikud G2P (niqqud+stress -> IPA) -> Piper onnx
              voice -> sounddevice. If the model/deps are missing, construction die()s (a loud crash)
              (fail LOUD -- never run the demo with no voice; owner ruling 2026-09-17).
English/espeak/piper backends were removed: we only speak Hebrew. If English TTS is ever needed,
add a SOTA model back -- do not resurrect espeak.

Select:  SCENE_TTS = phone | phonikud | off      (the ONLY TTS knob; default: phone)
Everything else -- phone host (derived from the video host), port, language, rate, timeout, and the
phonikud model paths -- is a fixed constant in config, not env-tunable.

Threading: the worker holds ONE slot for the latest answer, guarded by a lock, woken by an event.
say() overwrites the slot, cuts current playback, and signals; the worker blocks on the event at zero
CPU until then. Latest answer wins; there is no queue and no polling.
"""
import importlib.util
import http.client
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import numpy as np

import config
from fatal import die
from system.status import BOARD, RECOVERING, UP, fail
from system.supervisor import port_open

# phonikud is an OPTIONAL offline-TTS dependency (SCENE_TTS=phonikud). Checked here at module level, so
# there is no import inside a function; _load_phonikud die()s if it is selected but missing.
_HAVE_PHONIKUD = all(importlib.util.find_spec(pkg) is not None
                     for pkg in ("phonikud_onnx", "phonikud", "phonikud_tts", "sounddevice"))
if _HAVE_PHONIKUD:
    from phonikud_onnx import Phonikud
    from phonikud import phonemize as _pk_phonemize
    from phonikud_tts import Piper


def _resolve_phone_host():
    """Same phone as the video: config.TTS_HOST (unset by default) -> host= in the source -> WiFi gateway."""
    if config.TTS_HOST:
        return config.TTS_HOST
    m = re.search(r"host=(\S+)", str(config.INPUT))
    if m:
        return m.group(1)
    return config.default_gateway() or ""


class Voice:
    def __init__(self):
        """Only built when TTS is on (mvd.build_voice returns None for SCENE_TTS=off)."""
        backend = (config.TTS_BACKEND or "phone").lower()
        if backend not in ("phone", "phonikud"):
            die(f"SCENE_TTS={backend!r} is not a valid voice backend (use phone | phonikud; off builds no Voice)")
        self._phone = backend == "phone"
        self._pk = self._pk_voice = self._pk_phonemize = self._sd = None
        self.host = ""
        self._tts_url = ""
        self.backend = backend
        # Choose the speak function ONCE, so the worker loop has no per-iteration backend branch.
        if self._phone:
            self._setup_phone()
            self._say = self._say_phone
            where = f"phone {self._tts_url}"
        else:
            self._load_phonikud()
            self._say = self._say_phonikud
            where = "laptop phonikud"

        # One-slot mailbox: the latest text to speak, a lock, and a wake event.
        self._pending = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._run = True
        threading.Thread(target=self._worker, daemon=True).start()
        print(f"[voice] speaking on: {where}", flush=True)
        BOARD.report("tts", UP)

    def _setup_phone(self):
        """Resolve the phone host and verify it answers. A phone TTS with no connection is fatal (owner)."""
        self.host = _resolve_phone_host()
        if not self.host:
            die("SCENE_TTS=phone but no phone host resolved (check the WiFi hotspot or set PHONE_IP)")
        self._tts_url = f"http://{self.host}:{config.TTS_PORT}/tts"
        if not port_open(self.host, config.TTS_PORT, config.TTS_TIMEOUT):   # unreachable at start-up is fatal
            fail("tts", f"{self.host}:{config.TTS_PORT} unreachable at start-up",
                 f"SCENE_TTS=phone but {self.host}:{config.TTS_PORT} is unreachable")

    def _load_phonikud(self):
        """Load the offline Hebrew voice, or die() loudly with the fix. No silent fallback."""
        for path in (config.PHONIKUD_G2P, config.PHONIKUD_VOICE, config.PHONIKUD_CONFIG):
            if not os.path.exists(path):
                die(f"phonikud model file missing: {path} (run tools/devenv/install-runtime-deps.sh)")
        if not _HAVE_PHONIKUD:
            die("phonikud stack missing (pip install phonikud phonikud-onnx phonikud-tts sounddevice)")
        import sounddevice   # phonikud-only playback; needs native PortAudio, so it stays out of module scope
        self._sd = sounddevice
        self._pk = Phonikud(config.PHONIKUD_G2P)
        self._pk_voice = Piper(config.PHONIKUD_VOICE, config.PHONIKUD_CONFIG)
        self._pk_phonemize = _pk_phonemize

    def say(self, text):
        """Hand the worker the latest answer. Drops any unspoken text, so the newest wins. Never raises."""
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            self._pending = text        # overwrite: the latest answer is the only one that matters
        self._stop_current()            # cut the current playback so the new answer starts now
        self._wake.set()                # wake the worker

    def _stop_current(self):
        """Stop any playback in progress, so a newer answer starts at once."""
        if self._pk_voice:
            self._sd.stop()

    def _worker(self):
        """Block on the wake event, take the latest text, speak it. Zero CPU while idle."""
        while self._run:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                text = self._pending
                self._pending = None
            if text is not None:        # None = a shutdown wake, or an already-taken slot
                self._say(text)

    def _post(self, body):
        """One POST /tts. -> the HTTP status, or None when the phone did not answer at all (urllib, like every
        other HTTP call in the app; it reports an error status or no answer only by a throw)."""
        req = urllib.request.Request(self._tts_url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=config.TTS_TIMEOUT) as r:
                return r.status
        except urllib.error.HTTPError as e:           # the phone answered with an error status
            return e.code
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
            print(f"[voice] phone /tts did not answer: {e!r}", flush=True)
            return None

    def _say_phone(self, text):
        """POST the text to the phone. A phone that does not answer is RECOVERED like every supervised
        service (owner ruling 2026-09-22): report RECOVERING, try again up to SUPERVISOR_MAX_RESTARTS times,
        back to UP when it answers, else report FAILED and die() with the reason."""
        body = {"text": text, "lang": config.TTS_LANG, "rate": config.TTS_RATE}
        tries = config.SUPERVISOR_MAX_RESTARTS
        for attempt in range(tries + 1):
            code = self._post(body)
            if code is not None and 200 <= code < 300:        # a 4xx/5xx is a failed delivery too (R28)
                if attempt:
                    BOARD.report("tts", UP)
                print(f"[voice] -> phone /tts HTTP {code}: {text[:50]!r}", flush=True)
                return True
            if attempt == tries:
                break
            reason = "did not answer" if code is None else f"answered HTTP {code}"
            BOARD.report("tts", RECOVERING, f"phone /tts {reason}; retry {attempt + 1}/{tries}")
            time.sleep(config.SERVICE_RETRY_SECONDS)
            with self._lock:                                   # a newer answer arrived: speak that one
                if self._pending is not None:
                    text, self._pending = self._pending, None
                    body["text"] = text
        fail("tts", f"phone /tts failed {tries + 1} times",
             f"phone TTS at {self._tts_url} failed {tries + 1} times; {tries} recoveries failed")

    def _say_phonikud(self, text):
        """Offline Hebrew: phonikud niqqud+stress -> IPA -> Piper onnx voice -> sounddevice. Returns a status."""
        vocalized = self._pk.add_diacritics(text)
        phonemes = self._pk_phonemize(vocalized)
        samples, sample_rate = self._pk_voice.create(phonemes, is_phonemes=True)
        self._sd.play(np.clip(samples, -1.0, 1.0).astype(np.float32), sample_rate)
        self._sd.wait()   # blocks until playback ends, or until _stop_current() cuts it for a newer answer
        return True

    def shutdown(self):
        self._run = False
        self._wake.set()        # wake the worker so it sees _run is False and exits
        self._stop_current()
