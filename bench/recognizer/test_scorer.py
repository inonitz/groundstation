"""Tests for scorer.py, the recognizer benchmark's one scorer. Run:
python3 -m pytest -q /root/groundstation/bench/recognizer/test_scorer.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scorer import read_notation, score  # noqa: E402


class Decision:
    """What route() decided, as the scorer reads it."""

    def __init__(self, kind, target="", mission=None, action=""):
        self.kind = kind
        self.target = target
        self.mission = mission or []
        self.action = action


def test_a_vision_request_of_another_kind_fails():
    """SC1 (owner 2026-09-30): the kind is graded from its own field."""
    expect = {"kind": "perception", "vision": "count", "groups": [["chair"]]}
    assert score(expect, Decision("count", "chairs"))[0] == "PASS"
    verdict, reason = score(expect, Decision("highlight", "chairs"))
    assert verdict == "FAIL" and reason == "a highlight request, expected count"
    assert score(expect, Decision("count", "tables"))[0] == "FAIL"


def test_a_vision_request_with_no_kind_accepts_every_kind():
    expect = {"kind": "perception", "groups": [["chair"]]}
    for kind in ("highlight", "count", "describe"):
        assert score(expect, Decision(kind, "chair"))[0] == "PASS", kind
    assert score(expect, Decision("mission"))[0] == "FAIL"


def test_a_signed_turn_without_deg_is_read():
    """The notation that failed two right plans on 2026-09-26."""
    assert read_notation("dz+10, +90, dx+5")["steps"] == [
        ["fly_by", "dz", 10.0],
        ["spin_by", "degrees", 90.0],
        ["fly_by", "dx", 5.0],
    ]
    assert read_notation("180 deg (either way)")["steps"] == [
        ["spin_by", "degrees", ["abs", 180.0]]
    ]


def test_alternatives_and_a_halt():
    expect = {
        "kind": "mission",
        "alternatives": ["halt", [["delay", "seconds", None]]],
    }
    assert score(expect, Decision("emergency"))[0] == "PASS"
    wait = [{"type": "delay", "seconds": 3}]
    assert score(expect, Decision("mission", mission=wait))[0] == "PASS"
    fly = [{"type": "fly_by", "dx": 1}]
    assert score(expect, Decision("mission", mission=fly))[0] == "FAIL"
