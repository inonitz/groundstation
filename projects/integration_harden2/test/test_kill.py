import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from control.kill import KillSwitch


class FakeWire:
    def __init__(self): self.calls = []
    def stop(self): self.calls.append("stop"); return 200
    def halt(self): self.calls.append("halt"); return 200
    def takeoff(self): self.calls.append("takeoff"); return 200
    def land(self): self.calls.append("land"); return 200
    def fly_mission(self, actions): self.calls.append(("fly", list(actions))); return 200
    def fly_by(self, dx=0.0, dy=0.0, dz=0.0, velocity=4.0): self.calls.append("fly_by"); return 200


def test_kill_stops_and_latches_every_motion_verb():
    w = FakeWire(); said = []; ks = KillSwitch(w, say=said.append)
    assert w.fly_mission([{"type": "fly_by", "dx": 1}]) == 200
    assert ks.kill() == 200 and w.calls[-1] == "stop" and ks.killed
    assert w.fly_mission([{"type": "fly_by", "dx": 1}]) == KillSwitch.REFUSED
    assert w.takeoff() == KillSwitch.REFUSED and w.land() == KillSwitch.REFUSED and w.fly_by(dx=1) == KillSwitch.REFUSED
    assert "takeoff" not in w.calls and "land" not in w.calls and "fly_by" not in w.calls and ks.refused == 4
    assert w.halt() == 200                      # halt stays allowed while latched
    ks.rearm(); assert not ks.killed and w.fly_mission([]) == 200
    assert any("KILL" in m for m in said)


def test_kill_twice_resends_stop():
    w = FakeWire(); ks = KillSwitch(w, say=lambda m: None); ks.kill(); ks.kill()
    assert w.calls.count("stop") == 2 and ks.kills == 2


def test_m_key_toggle():
    w = FakeWire(); ks = KillSwitch(w, say=lambda m: None)
    assert ks.toggle() is True and ks.killed and w.calls[-1] == "stop"
    assert w.takeoff() == KillSwitch.REFUSED
    assert ks.toggle() is False and not ks.killed and w.takeoff() == 200
