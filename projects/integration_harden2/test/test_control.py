"""Tests for control/: control executes flight through the REAL phone-app client against
a REAL local HTTP server (test/support.py). It owns the one transmit switch."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from control.flight import Control, outcome_text
from http import HTTPStatus

from dji_app.client import DjiApp
from support import RecordingPhone, dead_port

FLY_BY = [{"type": "fly_by", "dx": 1}]


def test_manual_stops_then_refuses_every_mission_without_sending_it():
    phone = RecordingPhone()
    assert phone.control.manual() == HTTPStatus.OK and phone.paths() == ["/c/stop"]
    assert phone.control.manual_on()
    assert phone.control.fly(FLY_BY) == HTTPStatus.CONFLICT
    assert phone.dji.takeoff() == HTTPStatus.CONFLICT
    assert phone.dji.land() == HTTPStatus.CONFLICT
    # nothing else left the laptop
    assert phone.paths() == ["/c/stop"]
    phone.close()


def test_auto_allows_missions_again():
    phone = RecordingPhone()
    phone.control.manual()
    phone.control.auto()
    assert not phone.control.manual_on()
    assert phone.control.fly(FLY_BY) == 200 and phone.seen[-1] == ("/c/fly", FLY_BY)
    phone.close()


def test_the_kill_key_toggles_manual_and_auto():
    phone = RecordingPhone()
    assert phone.control.toggle_manual() == ("manual", HTTPStatus.OK)
    assert phone.control.toggle_manual() == ("auto", None)
    assert phone.paths() == ["/c/stop"]
    phone.close()


def test_emergency_halts_in_auto_and_stops_in_manual():
    phone = RecordingPhone()
    assert phone.control.emergency_halt() == 200
    # keeps stick control
    assert phone.seen[-1] == ("/c/fly", [{"type": "delay", "seconds": 0.0}])
    phone.control.manual()
    assert phone.control.emergency_halt() == 200
    # never a halt that takes control back from the RC
    assert phone.paths()[-1] == "/c/stop"
    phone.close()


def test_manual_refuses_missions_even_when_the_stop_did_not_arrive():
    control = Control(DjiApp("127.0.0.1", dead_port(), timeout=0.5))
    assert control.manual() is None
    assert control.manual_on() and control.fly(FLY_BY) == HTTPStatus.CONFLICT


def test_outcome_text_says_what_really_happened():
    key = config.KILL_KEY_NAME
    manual = outcome_text("manual", HTTPStatus.OK)
    assert "the RC has control" in manual and key in manual
    assert outcome_text("mission", HTTPStatus.OK) == "mission: sent (HTTP 200)."
    assert "refused: manual mode is on" in outcome_text("mission", HTTPStatus.CONFLICT)
    lost = outcome_text("manual", None)
    assert "did NOT reach the aircraft" in lost and "power button" in lost
    assert "stay refused" in lost
    assert "HTTP 500" in outcome_text("mission", HTTPStatus.INTERNAL_SERVER_ERROR)
    assert outcome_text("auto", None) == "auto: missions are allowed again."
