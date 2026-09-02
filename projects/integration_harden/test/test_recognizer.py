"""Wiring tests for the Recognizer module. No GPU: the translator and planner are fakes.
One test per output kind, plus the component self-test and the router-compatibility check."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "recognizer"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import recognizer as R
from pipeline import Pipeline, REJECT_PREFIX


class FakeWire:
    def __init__(self):
        self.missions = []
        self.halts = 0

    def fly_mission(self, steps):
        self.missions.append(steps)

    def halt(self):
        self.halts += 1


def make(translate_returns=None, plan_returns=None):
    wire = FakeWire()
    said, seen = [], []
    pipe = Pipeline(wire,
                    vlm_query=seen.append,
                    say=said.append,
                    plan_fn=lambda en: plan_returns,
                    trace_dir="/tmp/recognizer-test-traces")
    if translate_returns is not None:
        pipe._translate = lambda he, required_numbers=None: translate_returns
    return pipe, wire, said, seen


def test_component_selftest_clean():
    assert R.selftest() == []


def test_bypass_flies_without_models():
    pipe, wire, said, seen = make()
    pipe._translate = None                      # any model call would crash the test
    action = pipe.handle("עלה עשרה מטרים")
    assert wire.missions == [[{"type": "fly_by", "dz": 10.0}]]
    assert "bypass" in action


def test_emergency_backup_net_halts():
    pipe, wire, said, seen = make()
    pipe.handle("עצור הכל מיד")
    assert wire.halts == 1 and wire.missions == []


def test_command_plans_then_flies():
    mission = [{"type": "fly_by", "dx": 5}]
    pipe, wire, said, seen = make(translate_returns="fly forward 5 meters please quickly",
                                  plan_returns=mission)
    action = pipe.handle("טוס קדימה חמישה מטרים בזהירות רבה")
    assert wire.missions == [mission] and "planned" in action


def test_perception_goes_to_vlm():
    pipe, wire, said, seen = make(translate_returns="mark the white car by the tree")
    pipe.handle("סמן את המכונית הלבנה ליד העץ")
    assert seen == ["mark the white car by the tree"] and wire.missions == []


def test_reject_reads_back_to_user():
    pipe, wire, said, seen = make(translate_returns="climb sixty meters")
    pipe.handle("תעלה לי בעדינות עשרים מטרים")     # 20 in, 60 out, twice -> unpatchable? no: 60->20 patches
    # patching succeeds here, so force a real mismatch: two numbers wrong
    pipe2, wire2, said2, seen2 = make(translate_returns="climb sixty meters and turn ninety")
    pipe2.handle("תעלה לי בעדינות עשרים מעלות ועוד שלושים")
    assert said2 and said2[0].startswith(REJECT_PREFIX)
    assert wire2.missions == []


def test_planned_empty_means_no_flight():
    pipe, wire, said, seen = make(translate_returns="what is your altitude today",
                                  plan_returns=[])
    action = pipe.handle("איזה גובה נחמד יש היום אה")
    assert wire.missions == [] and action == "planned-empty"
