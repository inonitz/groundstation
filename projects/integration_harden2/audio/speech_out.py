"""Speech out: ONE interface over a LIST of outputs (owner ruling 2026-09-23). The config
option TTS_OUTPUTS picks them (phone, laptop); every sentence goes to each one. A new
output is one class plus one line in OUTPUTS.

Latest answer wins: say() overwrites a one-slot mailbox, cuts what is playing, and wakes
the worker; the worker sleeps on an event at zero CPU until then. No queue, no
polling."""
import threading

from audio.tts_laptop import LaptopTts
from audio.tts_phone import PhoneTts
from system.fatal import die

OUTPUTS = {"phone": PhoneTts, "laptop": LaptopTts}


class SpeechOut:
    """@outputs: names from OUTPUTS (config.TTS_OUTPUTS). @dji: the phone-app client."""

    def __init__(self, outputs, dji):
        unknown = [name for name in outputs if name not in OUTPUTS]
        if unknown:
            die(f"TTS_OUTPUTS has unknown outputs {unknown} (known: {sorted(OUTPUTS)})")

        self._outputs = [OUTPUTS[name](dji) for name in outputs]
        self._pending = None
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._running = True
        self._worker = threading.Thread(target=self._run, name="speech-out", daemon=True)
        self._worker.start()
        print(f"[speech_out] outputs: {list(outputs)}", flush=True)
        return

    def close(self):
        self._running = False
        self._wake.set()                    # the worker sees _running is False and exits
        self._worker.join()
        for output in reversed(self._outputs):
            output.close()
        return

    def say(self, text):
        """Hand the worker the latest answer; any unspoken one is dropped. Never
        blocks."""
        text = (text or "").strip()
        if not text:
            return

        with self._lock:
            self._pending = text
        for output in self._outputs:
            output.stop_current()           # a newer answer starts now
        self._wake.set()
        return

    def _run(self):
        text = None

        while self._running:
            self._wake.wait()
            self._wake.clear()
            with self._lock:
                text = self._pending
                self._pending = None

            if text is None:                # a shutdown wake, or an already-taken slot
                continue

            for output in self._outputs:
                output.say(text)
        return
