"""Wiring tests for the go-live assembly in scene_omdet.py. No GPU, no video, no real models:
the translator and planner are fakes and vlm_query/say are recorders. These lock the NEW
production wiring that the Recognizer's own tests (test_recognizer.py) do not exercise:

  - COMPLEX text is consumed by the router (TextHandler._handle_drone returns True) and routed
    through Pipeline as Router.on_complex -- it does NOT fall to perception directly.
  - A see-question reaches TextHandler.perceive (the Pipeline's vlm_query).
  - A Hebrew command becomes a mission on the wire; a reject is spoken; emergency halts via the
    router tier, not the Pipeline.
  - With no router, TextHandler.perceive runs directly (the no-drone path).

Run: python3 test_scene_wiring.py   (or: pytest -q test_scene_wiring.py)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "recognizer"))

import scene_omdet as scene
from scene_omdet import TextHandler
from control.router import Router
from recognizer import Pipeline
from recognizer.pipeline import REJECT_PREFIX


class FakeWire:
    def __init__(self):
        self.missions = []
        self.halts = 0

    def fly_mission(self, steps):
        self.missions.append(steps)

    def halt(self):
        self.halts += 1


def build(translate_returns=None, plan_returns=None, with_router=True):
    """Mirror scene_omdet.main()'s ruled wiring, with the models faked. seen[] records the
    Pipeline's vlm_query (= TextHandler.perceive), said[] records the Pipeline's say (= _say)."""
    scene.S.chat.clear()
    wire = FakeWire()
    seen, said = [], []
    on_text = TextHandler(None, voice=None)
    on_text.perceive = seen.append              # observe perception routing (patched before pipe)
    if not with_router:
        return on_text, wire, seen, said
    pipe = Pipeline(wire, vlm_query=on_text.perceive, say=said.append,
                    plan_fn=lambda en: plan_returns, trace_dir="/tmp/scene-wiring-traces")
    if translate_returns is not None:
        pipe._translate = lambda he, required_numbers=None: translate_returns
    else:                                       # no fake given -> any translate call is a bug (no network)
        def _no_model(he, required_numbers=None):
            raise AssertionError("translate called on a path that must not use a model")
        pipe._translate = _no_model
    on_text.router = Router(wire, on_complex=pipe.handle)
    return on_text, wire, seen, said


def test_complex_perception_routes_to_perceive():
    on_text, wire, seen, said = build(translate_returns="mark the white car by the tree")
    on_text("סמן את המכונית הלבנה ליד העץ")
    assert seen == ["mark the white car by the tree"]   # reached perceive exactly once
    assert wire.missions == [] and said == []


def test_hebrew_command_flies_via_pipeline():
    mission = [{"type": "fly_by", "dx": 5}]
    on_text, wire, seen, said = build(translate_returns="fly forward 5 meters please quickly",
                                      plan_returns=mission)
    on_text("טוס קדימה חמישה מטרים בזהירות רבה")
    assert wire.missions == [mission] and seen == []


def test_mission_bypass_flies_without_models():
    on_text, wire, seen, said = build()             # build() installs a raising translate: proves no model
    on_text("עלה עשרה מטרים")
    assert wire.missions == [[{"type": "fly_by", "dz": 10.0}]] and seen == []


def test_reject_is_spoken_not_perceived():
    on_text, wire, seen, said = build(translate_returns="climb sixty meters and turn ninety")
    on_text("תעלה לי בעדינות עשרים מעלות ועוד שלושים")
    assert said and said[0].startswith(REJECT_PREFIX)
    assert wire.missions == [] and seen == []


def test_emergency_halts_via_router_not_pipeline():
    on_text, wire, seen, said = build(translate_returns="unused")
    on_text("עצור")
    assert wire.halts == 1                              # router tier-4 halt, not the Pipeline backup
    assert seen == [] and wire.missions == []
    assert ("model", "[drone] stop") in list(scene.S.chat)


def test_no_router_falls_through_to_perceive():
    on_text, wire, seen, said = build(with_router=False)
    on_text("what do you see")
    assert seen == ["what do you see"]                  # no router -> perceive runs directly


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except AssertionError as e:
            fails += 1; print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - fails}/{len(fns)} passed")
    sys.exit(1 if fails else 0)
