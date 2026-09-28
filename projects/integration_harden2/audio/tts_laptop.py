"""Speech out on the LAPTOP, offline Hebrew: phonikud G2P (niqqud + stress -> IPA) ->
Piper onnx voice -> sounddevice. The models are cc-nc (demo / competition use only);
fetched by tools/devenv/install-runtime-deps.sh.

A missing model file or package dies at start (never run with no voice; owner
2026-09-17): system/deps.py checks them. A playback error dies at once with the reason:
it only happens when the laptop sound system itself breaks, and no retry fixes that
(owner ruling 9a-1, 2026-09-23). sounddevice reports it only by a throw
(PortAudioError); nothing catches it, so the crash hook (system/fatal.py) dies with the
error and its traceback."""
import numpy as np
import sounddevice
from phonikud import phonemize
from phonikud_onnx import Phonikud
from phonikud_tts import Piper

import config


class LaptopTts:
    def __init__(self, dji=None):
        """@dji is unused: every output takes the same arguments. The model files are
        checked at start-up (system/deps.py)."""
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
