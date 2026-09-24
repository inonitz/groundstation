"""Control: the way we interact with the drone, and ONLY that (owner ruling 2026-09-23).
It parses nothing: the recognizer understands the sentence and calls control; the app's
F4 key calls control. It is the ONLY module that sends flight requests to the phone app
and the ONLY user of the phone app's transmit switch.

  manual         -> POST /c/stop (the aircraft stops, the RC flies) + transmit OFF:
                    missions are refused.
  auto           -> transmit ON: missions are allowed again.
  emergency halt -> in auto, a delay:0 mission pre-empts motion and KEEPS our stick
                    control; in manual, /c/stop (a halt would take stick control back
                    from the RC).

Results are the standard library's http.HTTPStatus, or None when the phone app did not
answer. CONFLICT (409) means the transmit switch blocked the request.

Only a human presses F4 against a real aircraft: the assistant never sends /c/stop to a
real drone (CLAUDE.md drone-safety rules)."""
import threading
from http import HTTPStatus

import config
from dji_app.client import HALT_MISSION


def outcome_text(action, status):
    """The ONE wording of a flight result, for the chat, the speech output and the
    log."""
    key = config.KILL_KEY_NAME

    if action == "auto":
        return "auto: missions are allowed again."

    if status is not None and status.is_success:
        if action == "manual":
            return (f"manual: motion stopped, the RC has control. Missions are refused "
                    f"until {key} or 'auto'.")
        return f"{action}: sent (HTTP {int(status)})."

    if status == HTTPStatus.CONFLICT:
        return (f"{action} refused: manual mode is on. Press {key} or say 'auto' to "
                "allow missions.")

    if status is None:
        text = (f"{action} did NOT reach the aircraft: the phone app did not answer. "
                "Take over with the RC, or hold the aircraft power button.")
        if action == "manual":
            text += " Missions stay refused."
        return text

    return f"{action} FAILED: the phone app answered HTTP {int(status)}."


class Control:
    """@dji: the phone-app client (dji_app.client.DjiApp).
    @log: the session log, or None. Every mission control sends is recorded in the
    current turn, exactly as sent."""

    def __init__(self, dji, log=None):
        self._dji = dji
        self._log = log
        self._lock = threading.Lock()   # F4 (key thread) races voice (speech thread)
        return

    def close(self):
        return

    def manual_on(self):
        return not self._dji.transmitting()

    def manual(self):
        """Stop, then refuse missions. The switch goes off even when the stop did not
        arrive: our missions must never fly while the operator believes the RC has
        control."""
        with self._lock:
            self._dji.set_transmit(False)
            return self._dji.stop()

    def auto(self):
        with self._lock:
            self._dji.set_transmit(True)
        return

    def toggle_manual(self):
        """The F4 key. -> (action, status) for outcome_text; status is None for auto."""
        if self.manual_on():
            self.auto()
            return "auto", None

        return "manual", self.manual()

    def emergency_halt(self):
        """In manual mode a halt would take stick control back from the RC, so the
        emergency sends /c/stop instead (never blocked)."""
        if self.manual_on():
            return self._dji.stop()

        self._record(HALT_MISSION)
        return self._dji.halt()

    def fly(self, actions):
        """-> the phone app's status, or CONFLICT in manual mode."""
        self._record(actions)
        return self._dji.fly_mission(actions)

    def _record(self, mission):
        if self._log is None:
            return
        self._log.set(mission=mission)
        return
