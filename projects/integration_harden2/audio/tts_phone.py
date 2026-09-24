"""Speech out on the PHONE: POST /tts through the phone-app client; Android TextToSpeech
speaks it (Hebrew). /tts is served by the same phone app as the drone commands, so its
health IS the "dji app" row: no row and no retry of its own (owner ruling 2026-09-23). In
mock mode the mock stands in for the phone and logs the text."""
from system.fatal import die


class PhoneTts:
    """@dji: the phone-app client (dji_app.client.DjiApp)."""

    def __init__(self, dji):
        if dji is None:
            die("the phone voice needs the phone-app client")

        self._dji = dji
        return

    def close(self):
        return

    def say(self, text):
        """-> True when the phone app answered 2xx."""
        status = self._dji.speak(text)
        print(f"[tts_phone] -> /tts {status}: {text[:50]!r}", flush=True)
        return status is not None and status.is_success

    def stop_current(self):
        """The phone speaks on its own; a newer answer simply follows."""
        return
