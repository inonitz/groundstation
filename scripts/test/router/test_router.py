"""Router unit tests: classification tiers + dispatch logic, with a fake wire (no network).

Run: python3 scripts/test/router/test_router.py
The KEY cases are the inherited regex collisions ("go down" must NOT become land, etc.)
and that manual mode swallows ASR verbs while emergency always fires.
"""
import os
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "source"))

from integration import commands              # noqa: E402
from integration.commands import Tier         # noqa: E402
from integration.router import Router          # noqa: E402


class FakeWire:
    """Records wire calls instead of hitting the network."""
    def __init__(self):
        self.calls = []
    def takeoff(self): self.calls.append(("takeoff",))
    def land(self): self.calls.append(("land",))
    def stop(self): self.calls.append(("stop",))
    def nudge(self, vx=0.0, vy=0.0, vz=0.0, yaw=0.0, duration=0.0):
        self.calls.append(("nudge", vx, vy, vz, yaw))


def _ce(text, tier, name=None):
    c = commands.classify(text)
    assert c.tier is tier, f"{text!r}: expected {tier}, got {c.tier} ({c.name})"
    if name is not None:
        assert c.name == name, f"{text!r}: expected verb {name}, got {c.name}"


def test_classification():
    _ce("stop", Tier.EMERGENCY)
    _ce("emergency land now", Tier.EMERGENCY)      # "stop"-class word wins over "land"
    _ce("take manual control", Tier.OVERRIDE)
    _ce("resume", Tier.RESUME)
    _ce("take off", Tier.BASIC, "takeoff")
    _ce("liftoff", Tier.BASIC, "takeoff")
    _ce("land", Tier.BASIC, "land")
    _ce("go forward", Tier.BASIC, "go_forward")
    _ce("go down", Tier.BASIC, "go_down")          # COLLISION: must be go_down, NOT land
    _ce("down", Tier.BASIC, "go_down")
    _ce("go up", Tier.BASIC, "go_up")
    _ce("spin around", Tier.BASIC, "spin")
    _ce("what do you see", Tier.COMPLEX)
    _ce("how many people are in the room", Tier.COMPLEX)
    _ce("follow the person in red", Tier.COMPLEX)   # mission/perception -> complex, no auto-fly
    _ce("is the drone going to land", Tier.COMPLEX)  # word-count guard: question, not a LAND cmd
    _ce("what is that thing on the floor", Tier.COMPLEX)  # "floor" in land regex, but long -> complex
    print("  classification: OK")


def test_dispatch_and_mode():
    w = FakeWire()
    complex_seen = []
    r = Router(w, on_complex=complex_seen.append)

    assert r.handle("take off").action == "takeoff"
    assert w.calls[-1] == ("takeoff",)

    r.handle("go forward")
    assert w.calls[-1][0] == "nudge" and w.calls[-1][1] > 0    # vx forward

    r.handle("go left")
    assert w.calls[-1][0] == "nudge" and w.calls[-1][2] < 0    # vy left is negative

    # Override -> manual: stop fires, subsequent verbs are swallowed.
    res = r.handle("switch to manual")
    assert res.tier is Tier.OVERRIDE and w.calls[-1] == ("stop",) and r.mode == "manual"
    n_before = len(w.calls)
    res = r.handle("go up")
    assert res.dispatched is False and len(w.calls) == n_before, "manual must swallow verbs"

    # Emergency fires even in manual mode.
    r.handle("stop")
    assert w.calls[-1] == ("stop",)

    # Resume -> auto, verbs fly again.
    r.handle("resume")
    assert r.mode == "auto"
    r.handle("land")
    assert w.calls[-1] == ("land",)

    # Complex reaches perception.
    r.handle("describe the scene")
    assert complex_seen and complex_seen[-1] == "describe the scene"
    print("  dispatch + mode: OK")


if __name__ == "__main__":
    test_classification()
    test_dispatch_and_mode()
    print("ALL ROUTER TESTS PASSED")
