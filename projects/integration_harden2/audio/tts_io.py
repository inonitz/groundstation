"""Voice = the demo's mouth. Speaks the VLM's answer so the loop is voice-in -> voice-out.

The PHONE app (DJI backend) OWNS TTS: it exposes POST /tts and speaks through Android
TextToSpeech (TTSManager). This module is a thin client -- it POSTs the answer text to the
SAME phone that serves the video (IP pulled from the video pipeline). The phone flushes its
speech queue per request, so the latest answer wins. Never raises into the caller.

Local backends exist for desk debugging with no phone attached. phonikud is the offline
Hebrew voice (G2P adds niqqud+stress -> IPA -> Piper onnx); espeak is a last-resort fallback.

Select:  SCENE_TTS = phone | phonikud | espeak | piper | both | off      (default: phone)
         "both" = phone AND laptop, i.e. every answer spoken twice -- opt in on purpose.
Phone:   SCENE_TTS_HOST=<ip>  (default: host= from the video SCENE_INPUT, else WiFi gateway)
         SCENE_TTS_PORT=8080  SCENE_TTS_LANG=en  SCENE_TTS_RATE=1.0
"""
import os, re, shutil, subprocess, threading, queue
import numpy as np
import config
try:
    import requests
except Exception:
    requests = None


def _resolve_phone_host():
    """Same phone as the video: explicit override -> host= in SCENE_INPUT -> WiFi default gateway."""
    if config.TTS_HOST:
        return config.TTS_HOST
    m = re.search(r"host=(\S+)", str(config.INPUT))
    if m:
        return m.group(1)
    return config.default_gateway() or ""


class Voice:
    def __init__(self):
        b = (config.TTS_BACKEND or "phone").lower()
        _valid = ("phone", "phonikud", "espeak", "piper", "both", "off")
        if b not in _valid:
            print(f"[voice] SCENE_TTS={b!r} not recognized (use {'|'.join(_valid)}) -> OFF", flush=True)
            b = "off"
        self._phone = b in ("phone", "both")
        # laptop engine: prefer piper (natural voice) when bin+model are ready, else espeak fallback.
        self._piper_bin = config.TTS_PIPER_BIN if os.path.exists(config.TTS_PIPER_BIN) else (shutil.which("piper") or "")
        piper_ready  = bool(config.TTS_MODEL and os.path.exists(config.TTS_MODEL) and self._piper_bin and shutil.which("aplay"))
        espeak_ready = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
        phonikud_ready = bool(shutil.which("aplay")
                              and os.path.exists(config.PHONIKUD_G2P)
                              and os.path.exists(config.PHONIKUD_VOICE)
                              and os.path.exists(config.PHONIKUD_CONFIG))
        if b == "phonikud":
            self._local_kind = "phonikud" if phonikud_ready else ("espeak" if espeak_ready else None)
        elif b == "espeak":
            self._local_kind = "espeak" if espeak_ready else None
        elif b in ("both", "piper"):
            self._local_kind = "piper" if piper_ready else ("espeak" if espeak_ready else None)
        else:
            self._local_kind = None
        self.host = _resolve_phone_host() if self._phone else ""
        if self._phone and (requests is None or not self.host):
            print(f"[voice] phone TTS unavailable (requests={requests is not None} host={self.host!r})", flush=True)
            self._phone = False
        if self._local_kind == "espeak" and not (shutil.which("espeak-ng") or shutil.which("espeak")):
            print("[voice] espeak not installed -> laptop TTS off (apt install espeak-ng)", flush=True)
            self._local_kind = None
        if b == "phonikud" and not phonikud_ready:
            print("[voice] phonikud models/aplay missing -> run "
                  "tools/devenv/install-runtime-deps.sh (falling back to espeak)", flush=True)
        self._pk = self._pk_voice = self._pk_phonemize = None
        if self._local_kind == "phonikud":
            try:
                from phonikud_onnx import Phonikud
                from phonikud import phonemize as _pk_phonemize
                from phonikud_tts import Piper as _PkPiper
                self._pk = Phonikud(config.PHONIKUD_G2P)
                self._pk_voice = _PkPiper(config.PHONIKUD_VOICE, config.PHONIKUD_CONFIG)
                self._pk_phonemize = _pk_phonemize
            except Exception as e:
                print(f"[voice] phonikud load failed ({e}) -> espeak fallback", flush=True)
                self._local_kind = "espeak" if espeak_ready else None
        self.backend = "off" if (not self._phone and not self._local_kind) else b
        self._q, self._cur, self._lock, self._run = queue.Queue(), None, threading.Lock(), True
        if self.backend != "off":
            threading.Thread(target=self._worker, daemon=True).start()
        outs = ([f"phone http://{self.host}:{config.TTS_PORT}/tts"] if self._phone else []) + \
               ([f"laptop {self._local_kind}"] if self._local_kind else [])
        print(f"[voice] speaking on: {', '.join(outs) or 'OFF'}", flush=True)

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
            if self._local_kind:
                try: self._say_local(text)
                except Exception as e: print(f"[voice] laptop tts: {e}", flush=True)

    def _say_phone(self, text):
        body = {"text": text, "lang": config.TTS_LANG, "rate": config.TTS_RATE}
        r = requests.post(f"http://{self.host}:{config.TTS_PORT}/tts", json=body, timeout=config.TTS_TIMEOUT)
        print(f"[voice] -> phone /tts HTTP {r.status_code}: {text[:50]!r}", flush=True)

    def _say_local(self, text):
        """Speak on the laptop: phonikud/piper first, espeak as the fallback if it errs."""
        if self._local_kind == "phonikud":
            try:
                self._say_phonikud(text); return
            except Exception as e:
                print(f"[voice] phonikud failed -> espeak fallback: {e}", flush=True)
        if self._local_kind == "piper":
            try:
                self._say_piper(text); return
            except Exception as e:
                print(f"[voice] piper failed -> espeak fallback: {e}", flush=True)
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe: return
        # -v <lang>: without a voice, espeak reads non-Latin text letter by letter ("Letter LAMED" ...).
        p = subprocess.Popen([exe, "-v", config.TTS_LANG, text])
        with self._lock: self._cur = p
        p.wait()

    def _say_piper(self, text):
        aplay = shutil.which("aplay")
        if not (self._piper_bin and config.TTS_MODEL and aplay):
            raise RuntimeError("piper not ready")
        piper = subprocess.Popen([self._piper_bin, "--model", config.TTS_MODEL, "--output-raw"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        play  = subprocess.Popen([aplay, "-q", "-r", str(config.TTS_SR),
                                  "-f", "S16_LE", "-t", "raw", "-"], stdin=piper.stdout)
        piper.stdout.close()
        with self._lock: self._cur = play
        piper.stdin.write(text.encode()); piper.stdin.close()
        play.wait()
        if play.returncode not in (0, None):
            raise RuntimeError(f"aplay rc={play.returncode}")

    def _say_phonikud(self, text):
        """Offline Hebrew: phonikud adds niqqud+stress -> IPA phonemes -> Piper onnx voice -> aplay."""
        aplay = shutil.which("aplay")
        if not (aplay and self._pk and self._pk_voice):
            raise RuntimeError("phonikud not ready")
        vocalized = self._pk.add_diacritics(text)
        phonemes  = self._pk_phonemize(vocalized)
        samples, sr = self._pk_voice.create(phonemes, is_phonemes=True)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
        play = subprocess.Popen([aplay, "-q", "-r", str(sr), "-f", "S16_LE", "-t", "raw", "-"],
                                stdin=subprocess.PIPE)
        with self._lock: self._cur = play
        play.stdin.write(pcm); play.stdin.close(); play.wait()
        if play.returncode not in (0, None):
            raise RuntimeError(f"aplay rc={play.returncode}")

    def shutdown(self):
        self._run = False
        self._stop_current()
