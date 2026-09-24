"""Speech in: ONE interface over a LIST of sources (owner ruling 2026-09-23). The config
option ASR_SOURCES picks them; every source feeds the same on_heard(text, source).
Several run at once on purpose: a remote source must never take away the ground-control
mic. A new source is one class plus one line in SOURCES."""
from audio.asr_phone import PhoneAsr
from audio.asr_ros import RosAsr
from system.fatal import die

SOURCES = {"ros": RosAsr, "phone": PhoneAsr}


class SpeechIn:
    """@sources: names from SOURCES (config.ASR_SOURCES). @on_heard(text, source).
    Every source takes (on_heard) and answers status()."""

    def __init__(self, sources, on_heard):
        unknown = [name for name in sources if name not in SOURCES]
        if unknown:
            die(f"ASR_SOURCES has unknown sources {unknown} (known: {sorted(SOURCES)})")

        self._sources = [SOURCES[name](on_heard) for name in sources]
        return

    def status(self):
        """Every source's rows (a source with no row of its own adds none)."""
        rows = []
        for source in self._sources:
            rows.extend(source.status())
        return rows

    def close(self):
        """Close every source, newest first."""
        for source in reversed(self._sources):
            source.close()
        return
