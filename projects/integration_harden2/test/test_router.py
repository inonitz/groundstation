"""Router/classifier tests (harden2 2026-09-19: BASIC retired; Gemma routes non-safety commands).
Pins the deterministic safety tiers (emergency / override / resume, EN + HE) and that everything
else falls through to COMPLEX (the Gemma recognizer). Flight-gating in manual mode is tested at
the pipeline (test_pipeline_direct.py): only the recognizer knows a command is a flight."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from control.commands import classify, Tier
from control.router import Router

def _c(t): return classify(t)


def test_safety_tiers_english():
    for w in ("stop", "abort", "freeze", "kill"):
        assert _c(w).tier is Tier.EMERGENCY, w
    assert _c("manual").tier is Tier.OVERRIDE
    assert _c("resume").tier is Tier.RESUME


def test_everything_else_is_complex():
    for t in ("what do you see", "how many people are in the room",
              "is the drone going to land soon",          # a QUESTION with 'land' must NOT be emergency
              "fly forward five meters", "look down", "scan the area", "come home", "hello"):
        assert _c(t).tier is Tier.COMPLEX, t
    assert _c("").tier is Tier.COMPLEX                      # empty -> complex, never a flight


class _StubWire:
    def __init__(s): s.log = []
    def halt(s): s.log.append("halt"); return 200
    def stop(s): s.log.append("stop"); return 200


def _rec():
    seen = []
    return seen, seen.append


def test_dispatch_emergency_override_resume():
    seen, on_complex = _rec()
    r = Router(_StubWire(), on_complex=on_complex)
    assert r.handle("stop").tier is Tier.EMERGENCY and "halt" in r.wire.log
    assert r.handle("manual").tier is Tier.OVERRIDE and r.mode == "manual" and "stop" in r.wire.log
    assert r.handle("resume").tier is Tier.RESUME and r.mode == "auto"


def test_complex_forwarded_to_recognizer():
    seen, on_complex = _rec()
    r = Router(_StubWire(), on_complex=on_complex)
    res = r.handle("טוס קדימה שני מטרים")
    assert res.tier is Tier.COMPLEX and res.dispatched and seen == ["טוס קדימה שני מטרים"]


def test_emergency_beats_manual():
    r = Router(_StubWire()); r.handle("manual")
    assert r.handle("stop").tier is Tier.EMERGENCY and "halt" in r.wire.log   # e-stop works in manual


def test_stop_is_one_shot_no_mode_change():
    r = Router(_StubWire())
    assert r.handle("stop").tier is Tier.EMERGENCY and r.mode == "auto"


def test_complex_forwarded_even_in_manual():
    # the router does NOT gate; the pipeline refuses flight in manual, perception still answers
    seen, on_complex = _rec()
    r = Router(_StubWire(), on_complex=on_complex); r.handle("manual")
    assert r.handle("מה אתה רואה").tier is Tier.COMPLEX and seen == ["מה אתה רואה"]


def test_hebrew_emergency_tiers():
    for w in ("עצור", "עצרי", "עצרו", "תעצור", "סטופ", "חירום", "עצור עכשיו"):
        assert _c(w).tier is Tier.EMERGENCY, w
    assert _c("שליטה ידנית").tier is Tier.OVERRIDE
    assert _c("ידני").tier is Tier.OVERRIDE
    assert _c("אני בשליטה").tier is Tier.OVERRIDE
    assert _c("המשך").tier is Tier.RESUME
    assert _c("אוטומטי").tier is Tier.RESUME
    assert _c("רחפן תעצור מיד בבקשה").tier is Tier.EMERGENCY   # emergency embedded in a longer sentence


def test_hebrew_emergency_dispatch():
    r = Router(_StubWire())
    assert r.handle("עצור").tier is Tier.EMERGENCY and "halt" in r.wire.log
    assert _c("מה אתה רואה עכשיו").tier is Tier.COMPLEX


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    fails = 0
    for fn in fns:
        try: fn(); print(f"PASS {fn.__name__}")
        except AssertionError as e: fails += 1; print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns)-fails}/{len(fns)} passed")
    sys.exit(1 if fails else 0)
