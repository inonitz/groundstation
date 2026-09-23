"""The system status board: every subsystem reports its state here; the overlay draws it.

Internals only. A subsystem calls report(); the display loop calls snapshot() once per frame and
draws each entry as a green (UP) or red (anything else) row. A failure changes a colour and a state
on the panel. It is not a chat message (owner ruling 2026-09-22).
"""
import threading
import time

from fatal import die

STARTING = "STARTING"       # launched, not ready yet
UP = "UP"                   # running and ready: the only green state
RECOVERING = "RECOVERING"   # died, being restarted
FAILED = "FAILED"           # not working and not being recovered (a supervised process: about to die())
DOWN = "DOWN"               # stopped on purpose (shutdown)


class StatusBoard:
    """@_entries: system name -> (state, detail, since). Insertion order = panel row order."""

    def __init__(self):
        self._lock = threading.Lock()
        self._entries = {}

    def report(self, system, state, detail=""):
        """Set a system's state. Logs the line only when the state or detail changed."""
        with self._lock:
            old = self._entries.get(system)
            changed = old is None or old[0] != state or old[1] != detail
            if changed:
                self._entries[system] = (state, detail, time.time())
        if changed:
            suffix = f" -- {detail}" if detail else ""
            print(f"[status] {system}: {state}{suffix}", flush=True)
        return

    def snapshot(self):
        """[(system, state, detail), ...] in first-report order. Safe to call from any thread."""
        with self._lock:
            rows = [(name, entry[0], entry[1]) for name, entry in self._entries.items()]
        return rows

    def state(self, system):
        with self._lock:
            entry = self._entries.get(system)
        return entry[0] if entry else None


BOARD = StatusBoard()       # the app's one board


def fail(system, detail, message, board=BOARD):
    """Show `system` FAILED with `detail`, then die(message). One call, so the pane is never green while
    the app crashes."""
    board.report(system, FAILED, detail)
    die(message)
