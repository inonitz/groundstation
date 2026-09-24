"""Speech out on the LAPTOP, offline Hebrew: phonikud G2P (niqqud + stress -> IPA) ->
Piper onnx voice -> sounddevice. The models are cc-nc (demo / competition use only);
fetched by tools/devenv/install-runtime-deps.sh.

A missing model or package dies at start (never run with no voice; owner 2026-09-17). A
playback error dies at once with the reason: it only happens when the laptop sound system
itself breaks, and no retry fixes that (owner ruling 9a-1, 2026-09-23). sounddevice
reports it only by a throw (PortAudioError); nothing catches it, so the crash hook
(system/fatal.py) dies with the error and its traceback."""
import importlib.util
import os

import numpy as np

import config
from system.fatal import die

# phonikud is OPTIONAL: checked without importing it, so no import can throw.
_PACKAGES = ("phonikud_onnx", "phonikud", "phonikud_tts", "sounddevice")
_HAVE_PHONIKUD = all(importlib.util.find_spec(pkg) is not None for pkg in _PACKAGES)
if _HAVE_PHONIKUD:
    import sounddevice
    from phonikud import phonemize
    from phonikud_onnx import Phonikud
    from phonikud_tts import Piper


class LaptopTts:
    def __init__(self, dji=None):
        """@dji is unused: every output takes the same arguments."""
        for path in (config.PHONIKUD_G2P, config.PHONIKUD_VOICE, config.PHONIKUD_CONFIG):
            if not os.path.exists(path):
                die(
                    f"phonikud model file missing: {path} "
                    "(run tools/devenv/install-runtime-deps.sh)"
                )

        if not _HAVE_PHONIKUD:
            die(
                "the laptop voice needs phonikud (pip install phonikud phonikud-onnx "
                "phonikud-tts sounddevice)"
            )

        self._g2p = Phonikud(config.PHONIKUD_G2P)
        self._voice = Piper(config.PHONIKUD_VOICE, config.PHONIKUD_CONFIG)
        return

    def close(self):
        self.stop_current()
        return

    def say(self, text):
        """Blocks until the sentence ends, or until stop_current() cuts it."""
        phonemes = phonemize(self._g2p.add_diacritics(text))
        samples, sample_rate = self._voice.create(phonemes, is_phonemes=True)
        samples = np.clip(samples, -1.0, 1.0).astype(np.float32)

        # a PortAudioError here (the laptop sound system broke) reaches the crash hook
        sounddevice.play(samples, sample_rate)
        sounddevice.wait()
        return True

    def stop_current(self):
        sounddevice.stop()
        return
