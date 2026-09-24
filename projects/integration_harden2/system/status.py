"""System status: every part that has a status row OWNS it and reports it through its own
API (owner ruling 2026-09-24). The board owns nothing: it asks each source for its rows.

  Status       one row (name, state, detail), set only by the part it describes. It logs
               a line whenever the state or the detail changes.
  source       any object with status() -> [(name, state, detail), ...]: a supervised
               process handle, the phone-app client, the SAM3 loader, video, speech in.
  StatusBoard  the app builds it once from its sources; the screen calls snapshot()
               every frame. Row order = source order.

Colours on the pane: green when UP, orange when WAITING (the user must fix something
outside the laptop), red in every other state. A failure changes a colour and a state on
the panel. It is not a chat message (owner ruling 2026-09-22).
"""
import threading

from system.fatal import die

STARTING = "STARTING"       # launched, not ready yet
UP = "UP"                   # running and ready: the only green state
RECOVERING = "RECOVERING"   # died, being restarted
# outside the laptop and down (the phone app): waiting for the USER to fix it
WAITING = "WAITING"
# not working and not being recovered (a supervised process: about to die())
FAILED = "FAILED"
DOWN = "DOWN"               # stopped on purpose (shutdown)


class Status:
    """One status row. Its owner calls set(); anyone may read it (thread-safe)."""

    def __init__(self, name, state=STARTING, detail=""):
        self.name = name
        self._lock = threading.Lock()
        self._state = None
        self._detail = ""
        self.set(state, detail)
        return

    def set(self, state, detail=""):
        """Change the row. Logs the line only when the state or the detail changed."""
        suffix = f" -- {detail}" if detail else ""
        with self._lock:
            changed = state != self._state or detail != self._detail
            self._state = state
            self._detail = detail

        if not changed:
            return
        print(f"[status] {self.name}: {state}{suffix}", flush=True)
        return

    def state(self):
        with self._lock:
            return self._state

    def row(self):
        """(name, state, detail)."""
        with self._lock:
            return self.name, self._state, self._detail


class StatusBoard:
    """@sources: objects with status() -> [(name, state, detail), ...], in panel
    order."""

    def __init__(self, sources):
        self._sources = list(sources)
        return

    def snapshot(self):
        """Every source's rows, in source order. Safe to call from any thread."""
        rows = []
        for source in self._sources:
            rows.extend(source.status())
        return rows


def fail(status, detail, message):
    """Set `status` FAILED with `detail`, then die(message): the log line says FAILED
    before the reason, so a crash never reads as green."""
    status.set(FAILED, detail)
    die(message)
