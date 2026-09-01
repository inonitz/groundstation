"""Voice = the demo's mouth. Speaks the VLM's answer so the loop is voice-in -> voice-out.

The PHONE app (DJI backend) OWNS TTS: it exposes POST /tts and speaks through Android
TextToSpeech (TTSManager). This module is a thin client -- it POSTs the answer text to the
SAME phone that serves the video (IP pulled from the video pipeline). The phone flushes its
speech queue per request, so the latest answer wins. Never raises into the caller.

Local espeak/piper backends exist ONLY for desk debugging with no phone attached.

Select:  SCENE_TTS = phone | espeak | piper | off             (default: phone)
Phone:   SCENE_TTS_HOST=<ip>  (default: host= from the video SCENE_INPUT, else WiFi gateway)
         SCENE_TTS_PORT=8080  SCENE_TTS_LANG=en  SCENE_TTS_RATE=1.0
"""
import os, re, shutil, subprocess, threading, queue
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
    try:
        for ln in subprocess.check_output(["ip", "route"], text=True).splitlines():
            if ln.startswith("default"):
                return ln.split()[2]
    except Exception:
        pass
    return ""


class Voice:
    def __init__(self):
        self.backend = (config.TTS_BACKEND or "phone").lower()
        self.host = _resolve_phone_host() if self.backend == "phone" else ""
        if self.backend == "phone" and (requests is None or not self.host):
            print(f"[voice] phone TTS unavailable (requests={requests is not None} host={self.host!r}) -> OFF",
                  flush=True)
            self.backend = "off"
        self._q, self._cur, self._lock, self._run = queue.Queue(), None, threading.Lock(), True
        if self.backend != "off":
            threading.Thread(target=self._worker, daemon=True).start()
        where = f"http://{self.host}:{config.TTS_PORT}/tts" if self.backend == "phone" else self.backend
        print(f"[voice] backend = {self.backend}  ({where})", flush=True)

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
            try:
                self._say_phone(text) if self.backend == "phone" else self._say_local(text)
            except Exception as e:
                print(f"[voice] speak failed: {e}", flush=True)

    def _say_phone(self, text):
        body = {"text": text, "lang": config.TTS_LANG, "rate": config.TTS_RATE}
        requests.post(f"http://{self.host}:{config.TTS_PORT}/tts", json=body, timeout=config.TTS_TIMEOUT)

    def _say_local(self, text):
        """Desk-debug only: speak on the workstation, no phone. Not the demo path."""
        if self.backend == "espeak":
            exe = shutil.which("espeak-ng") or shutil.which("espeak")
            if not exe: return
            p = subprocess.Popen([exe, text])
            with self._lock: self._cur = p
            p.wait(); return
        if self.backend == "piper":
            aplay = shutil.which("aplay")
            if not (config.TTS_MODEL and shutil.which("piper") and aplay): return
            piper = subprocess.Popen(["piper", "--model", config.TTS_MODEL, "--output-raw"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            play  = subprocess.Popen([aplay, "-q", "-r", str(config.TTS_SR),
                                      "-f", "S16_LE", "-t", "raw", "-"], stdin=piper.stdout)
            piper.stdout.close()
            with self._lock: self._cur = play
            piper.stdin.write(text.encode()); piper.stdin.close(); play.wait()

    def shutdown(self):
        self._run = False
        self._stop_current()
