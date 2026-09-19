"""Wiring tests for the go-live assembly in mvd.py (harden2 direct path). No GPU, no video, no
real models: the unified Gemma call is a plan2 fake; vlm_query/say are recorders. These lock the
assembly that the Pipeline's own tests do not exercise:

  - COMPLEX text is consumed by the router (TextHandler._handle_drone returns True) and routed through
    Pipeline as Router.on_complex -- it does NOT fall to perception directly.
  - A see-question reaches TextHandler.perceive (the Pipeline's vlm_query).
  - A Hebrew command becomes a mission on the wire; a reject is spoken; emergency halts via the router
    tier, not the Pipeline.
  - With no router, TextHandler.perceive runs directly (the no-drone path).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "recognizer"))

import mvd as scene
from mvd import TextHandler
from control.router import Router
from recognizer import Pipeline


class FakeWire:
    def __init__(self):
        self.missions = []
        self.halts = 0

    def fly_mission(self, steps):
        self.missions.append(steps)

    def halt(self):
        self.halts += 1


def build(plan2=None, with_router=True):
    """Mirror mvd.main()'s ruled wiring, with the Gemma call faked by plan2. seen[] records the
    Pipeline's vlm_query (= TextHandler.perceive); said[] records the Pipeline's say."""
    scene.S.chat.clear()
    wire = FakeWire()
    seen, said = [], []
    on_text = TextHandler(None, voice=None)
    on_text.perceive = seen.append              # observe perception routing (patched before pipe)
    if not with_router:
        return on_text, wire, seen, said
    pipe = Pipeline(wire, vlm_query=on_text.perceive, say=said.append,
                    plan2_fn=plan2 or (lambda he: None), trace_dir="/tmp/scene-wiring-traces")
    on_text.router = Router(wire, on_complex=pipe.handle)
    return on_text, wire, seen, said


def test_complex_perception_routes_to_perceive():
    on_text, wire, seen, said = build(plan2=lambda he: {"kind": "highlight", "target_en": "white car", "mission": []})
    on_text("סמן את המכונית הלבנה ליד העץ")
    assert len(seen) == 1 and seen[0].startswith("highlight the")   # reached perceive exactly once
    assert wire.missions == []


def test_hebrew_command_flies_via_pipeline():
    on_text, wire, seen, said = build(plan2=lambda he: {"kind": "mission", "target_en": "", "mission": [{"type": "fly_by", "dx": 5}]})
    on_text("טוס קדימה חמישה מטרים בזהירות רבה")
    assert wire.missions == [[{"type": "fly_by", "dx": 5}]] and seen == []


def test_mission_bypass_flies_without_models():
    on_text, wire, seen, said = build()             # plan2 returns None: a model call would show as no flight
    on_text("עלה עשרה מטרים")
    assert wire.missions == [[{"type": "fly_by", "dz": 10.0}]] and seen == []


def test_reject_is_spoken_not_perceived():
    on_text, wire, seen, said = build(plan2=lambda he: {"kind": "reject", "target_en": "", "mission": []})
    on_text("מה הגובה שלך עכשיו")
    assert said and said[0].startswith(Pipeline.REJECT_HE)
    assert wire.missions == [] and seen == []


def test_emergency_halts_via_router_not_pipeline():
    on_text, wire, seen, said = build()
    on_text("עצור")
    assert wire.halts == 1                              # router tier-4 halt, not the Pipeline backup
    assert seen == [] and wire.missions == []
    assert any(r[0] == "model" and r[1] == "[drone] stop" for r in scene.S.chat)


def test_no_router_falls_through_to_perceive():
    on_text, wire, seen, said = build(with_router=False)
    on_text("what do you see")
    assert seen == ["what do you see"]                  # no router -> perceive runs directly


class FakeBackend:
    """Stands in for the SAM3 backend: one detect, one cached mask."""
    def __init__(self):
        self.calls = 0

    def detect(self, frame, phrase, conf=0.3, topk=8):
        self.calls += 1
        return [{"label": phrase, "conf": 0.9, "box": (1, 2, 3, 4)}]

    def mask_for_box(self, frame, box):
        return "mask" if box == (1, 2, 3, 4) else None


def test_build_highlight_sam3_one_model_serves_both_callables():
    scene.OM["det"] = None
    fake = FakeBackend()
    detect, mask_for_box, th = scene.build_highlight("sam3", eyes=None, loader=lambda: fake)
    th.join(5)
    assert detect(None, "car", 0.12)[0]["box"] == (1, 2, 3, 4)
    assert mask_for_box(None, (1, 2, 3, 4)) == "mask"      # the mask comes from the SAME model
    detect(None, "car", 0.12)
    assert fake.calls == 1                                  # rate limit: one forward per period
    scene.OM["det"] = None


def test_build_highlight_rejects_unknown_backend():
    # unknown backend -> die() (a hard crash, not an exception). Check the child process crashes loudly.
    import subprocess
    here = os.path.dirname(__file__)
    code = ("import sys, os;"
            "sys.path.insert(0, os.path.join(%r, '..'));"
            "sys.path.insert(0, os.path.join(%r, '..', 'recognizer'));"
            "import mvd as scene;"
            "scene.build_highlight('yoloe', eyes=None)" % (here, here))
    r = subprocess.run([sys.executable, "-c", code],
                       env={**os.environ, "MVD_HOME": "integration_harden2", "MVD_TRANSLATOR": "none"},
                       capture_output=True, text=True)
    assert r.returncode != 0, "unknown SCENE_SEG must crash"
    assert "no vision backend" in r.stderr, r.stderr
