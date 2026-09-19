"""Voice = the demo's mouth. Speaks the VLM's answer so the loop is voice-in -> voice-out.

Hebrew only. Two backends:
  phone    -- POST /tts to the DJI phone app; it speaks via Android TextToSpeech (Google he-IL).
              Needs the phone reachable and on data. say() never raises into the caller.
  phonikud -- OFFLINE Hebrew on the laptop: phonikud G2P (niqqud+stress -> IPA) -> Piper onnx
              voice -> aplay. If the model/deps are missing, construction die()s (a loud crash)
              (fail LOUD -- never run the demo with no voice; owner ruling 2026-09-17).
English/espeak/piper backends were removed: we only speak Hebrew. If English TTS is ever needed,
add a SOTA model back -- do not resurrect espeak.

Select:  SCENE_TTS = phone | phonikud | off      (the ONLY TTS knob; default: phone)
Everything else -- phone host (derived from the video host), port, language, rate, timeout, and the
phonikud model paths -- is a fixed constant in config, not env-tunable.
"""
import os, re, shutil, subprocess, threading, queue
import numpy as np
import config
try:
    import requests
except Exception:
    requests = None


from fatal import die

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
        b = (config.TTS_BACKEND or "phone").lower()
        _valid = ("phone", "phonikud", "off")
        if b not in _valid:
            print(f"[voice] SCENE_TTS={b!r} not recognized (use {'|'.join(_valid)}) -> OFF", flush=True)
            b = "off"
        self._phone = b == "phone"
        self._pk = self._pk_voice = self._pk_phonemize = None

        if b == "phonikud":
            if not shutil.which("aplay"):
                die("phonikud TTS needs aplay (alsa-utils); it is not installed")
            for pth in (config.PHONIKUD_G2P, config.PHONIKUD_VOICE, config.PHONIKUD_CONFIG):
                if not os.path.exists(pth):
                    die(f"phonikud model file missing: {pth} (run tools/devenv/install-runtime-deps.sh)")
            try:
                from phonikud_onnx import Phonikud
                from phonikud import phonemize as _pk_phonemize
                from phonikud_tts import Piper as _PkPiper
            except Exception as e:
                die(f"phonikud packages not importable: {e} (pip install phonikud phonikud-onnx phonikud-tts)")
            self._pk = Phonikud(config.PHONIKUD_G2P)
            self._pk_voice = _PkPiper(config.PHONIKUD_VOICE, config.PHONIKUD_CONFIG)
            self._pk_phonemize = _pk_phonemize

        self.host = _resolve_phone_host() if self._phone else ""
        if self._phone and (requests is None or not self.host):
            print(f"[voice] phone TTS unavailable (requests={requests is not None} host={self.host!r})", flush=True)
            self._phone = False

        self.backend = b if (self._phone or self._pk_voice) else "off"
        self._q, self._cur, self._lock, self._run = queue.Queue(), None, threading.Lock(), True
        if self.backend != "off":
            threading.Thread(target=self._worker, daemon=True).start()
        where = (f"phone http://{self.host}:{config.TTS_PORT}/tts" if self._phone
                 else "laptop phonikud" if self._pk_voice else "OFF")
        print(f"[voice] speaking on: {where}", flush=True)

    def say(self, text):
        """Queue an answer; drops anything stale so the latest question's answer wins."""
        text = (text or "").strip()
        if not text or self.backend == "off":
            return
        try:
            while True: self._q.get_nowait()
        except queue.Empty:
            pass
        self._stop_current()
        self._q.put(text)

    def _stop_current(self):
        with self._lock:
            p = self._cur
        if p is not None and hasattr(p, "poll") and p.poll() is None:
            try: p.terminate()
            except Exception: pass

    def _worker(self):
        while self._run:
            try:
                text = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._phone:
                try: self._say_phone(text)
                except Exception as e: print(f"[voice] phone tts: {e}", flush=True)
            elif self._pk_voice:
                try: self._say_phonikud(text)
                except Exception as e: print(f"[voice] phonikud tts: {e}", flush=True)

    def _say_phone(self, text):
        body = {"text": text, "lang": config.TTS_LANG, "rate": config.TTS_RATE}
        r = requests.post(f"http://{self.host}:{config.TTS_PORT}/tts", json=body, timeout=config.TTS_TIMEOUT)
        print(f"[voice] -> phone /tts HTTP {r.status_code}: {text[:50]!r}", flush=True)

    def _say_phonikud(self, text):
        """Offline Hebrew: phonikud adds niqqud+stress -> IPA phonemes -> Piper onnx voice -> aplay."""
        vocalized = self._pk.add_diacritics(text)
        phonemes  = self._pk_phonemize(vocalized)
        samples, sr = self._pk_voice.create(phonemes, is_phonemes=True)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        play = subprocess.Popen(["aplay", "-q", "-r", str(sr), "-f", "S16_LE", "-t", "raw", "-"],
                                stdin=subprocess.PIPE)
        with self._lock: self._cur = play
        play.stdin.write(pcm); play.stdin.close(); play.wait()
        if play.returncode not in (0, None):
            raise RuntimeError(f"aplay rc={play.returncode}")

    def shutdown(self):
        self._run = False
        self._stop_current()
