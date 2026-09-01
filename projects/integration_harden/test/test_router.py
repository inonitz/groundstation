"""Router/classifier tests. Run: python3 test_router.py   (or: pytest -q test_router.py)
Pins the ambiguous phrases that bit us: 'back up' != go_up, 'go down' != land,
long questions containing 'land' != land, and mode-gating under override."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from integration_harden.commands import classify, Tier
from integration_harden.router import Router

def _c(t): return classify(t)

def test_basic_verbs():
    assert _c("take off").name == "takeoff"
    assert _c("land").name == "land"
    assert _c("rise").name == "go_up"
    assert _c("go up").name == "go_up"
    assert _c("go down").name == "go_down"          # NOT land (ordering)
    assert _c("move forward").name == "go_forward"
    assert _c("turn right").name == "go_right"
    assert _c("go left").name == "go_left"
    assert _c("spin around").name == "spin"

def test_back_up_is_backward_not_up():             # the bug the harness caught
    assert _c("back up").name == "go_backward"
    assert _c("backward").name == "go_backward"

def test_tiers():
    for w in ("stop", "abort", "freeze", "kill"):
        assert _c(w).tier is Tier.EMERGENCY
    assert _c("manual").tier is Tier.OVERRIDE
    assert _c("resume").tier is Tier.RESUME

def test_complex_and_length_guard():
    assert _c("what do you see").tier is Tier.COMPLEX
    assert _c("how many people are in the room").tier is Tier.COMPLEX
    # a QUESTION containing 'land' must NOT land the drone:
    assert _c("is the drone going to land soon").tier is Tier.COMPLEX

class _StubWire:
    def __init__(s): s.log=[]
    def takeoff(s): s.log.append("takeoff")
    def land(s): s.log.append("land")
    def stop(s): s.log.append("stop")
    def nudge(s, **k): s.log.append(("nudge", k))
    def spin_by(s, *a, **k): s.log.append(("spin_by", a, k))
    def fly_mission(s, a): s.log.append(("fly_mission", a))
    def scan_ground(s, *a, **k): s.log.append(("scan_ground", a, k))
    def track_me(s, *a, **k): s.log.append(("track_me", a, k))
    def follow_me(s, *a, **k): s.log.append(("follow_me", a, k))
    def go_home_to_user(s, *a, **k): s.log.append(("go_home_to_user", a, k))
    def halt(s, *a, **k): s.log.append(("halt", a, k))
    def fly_by(s, *a, **k): s.log.append(("fly_by", a, k))
    def gimbal_pitch(s, *a, **k): s.log.append(("gimbal_pitch", a, k))
    def wave(s, *a, **k): s.log.append(("wave", a, k))

def test_override_mode_gating():
    r = Router(_StubWire())
    assert r.handle("manual").tier is Tier.OVERRIDE and r.mode == "manual"
    assert r.handle("go up").dispatched is False       # swallowed while manual
    assert r.handle("resume").tier is Tier.RESUME and r.mode == "auto"
    assert r.handle("go up").dispatched is True         # flies again

def test_emergency_beats_manual():
    r = Router(_StubWire()); r.handle("manual")
    assert r.handle("stop").tier is Tier.EMERGENCY      # e-stop works even in manual



def test_spin_uses_native_spinby():
    r = Router(_StubWire(), spin_deg=360.0)
    res = r.handle("spin around")
    assert res.action == "spin" and res.dispatched is True
    assert ("spin_by", (360.0,), {}) in r.wire.log      # native SpinBy(360), not a yaw nudge
    assert not any(e[0] == "nudge" for e in r.wire.log if isinstance(e, tuple))

if __name__ == "__main__":
    fns=[v for k,v in sorted(globals().items()) if k.startswith("test_")]
    fails=0
    for fn in fns:
        try: fn(); print(f"PASS {fn.__name__}")
        except AssertionError as e: fails+=1; print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns)-fails}/{len(fns)} passed")
    sys.exit(1 if fails else 0)


def test_expanded_verbs():
    def one(phrase, verb, method):
        r = Router(_StubWire())
        res = r.handle(phrase)
        assert res.action == verb, f"{phrase!r} -> {res.action}, want {verb}"
        assert any(e[0] == method for e in r.wire.log if isinstance(e, tuple)), f"{phrase!r} missed {method}"
    one("look at me", "track", "track_me")
    one("track me", "track", "track_me")
    one("follow me", "follow", "follow_me")
    one("scan the ground", "scan", "scan_ground")
    one("search", "search", "scan_ground")
    one("come back home", "come_home", "go_home_to_user")
    # come_home must win over go_backward on "come back"
    assert Router(_StubWire()).handle("come back").action == "come_home"


def test_stop_does_not_latch_manual():
    r = Router(_StubWire())
    assert r.handle("stop").tier is Tier.EMERGENCY
    assert r.mode == "auto"                        # one-shot; no mode change
    assert r.handle("spin").dispatched is True     # user still controls the drone after a stop


def test_v3_mappings():
    def verb(phrase): 
        r=Router(_StubWire()); res=r.handle(phrase); return res, r.wire.log
    # gimbal (distinct from drone up/down and from track "look at me")
    _,log=verb("look forward"); assert ("gimbal_pitch",(0.0,),{}) in log
    _,log=verb("look down");    assert ("gimbal_pitch",(-60.0,),{}) in log
    _,log=verb("look up");      assert ("gimbal_pitch",(30.0,),{}) in log
    res,log=verb("look at me"); assert res.action=="track" and any(e[0]=="track_me" for e in log)
    # wave greetings
    for g in ("hello","how are you","hey"):
        _,log=verb(g); assert any(e[0]=="wave" for e in log), g
    # scan modes
    _,log=verb("scan");   assert ("scan_ground",(),{"facing":"OUTWARDS"}) in log
    _,log=verb("search"); assert ("scan_ground",(),{"facing":"INWARDS"}) in log
    # directionals -> fly_by (not sticks)
    _,log=verb("forward"); assert any(e[0]=="fly_by" for e in log)
    _,log=verb("go up");   fb=[e for e in log if e[0]=="fly_by"][0]; assert fb[2].get("dz")==1.0
    # stop -> halt (delay:0), not /c/stop
    res,log=verb("stop"); assert res.tier is Tier.EMERGENCY and any(e[0]=="halt" for e in log)
    assert not any(e[0]=="stop" for e in log)   # NOT /c/stop


def test_unknown_move_guard():
    r = Router(_StubWire())
    res = r.handle("go dance")                 # movement intent, unknown direction
    assert res.action.startswith("didn't catch") and res.dispatched is False
    assert not r.wire.log                        # NOTHING sent to the drone
    assert r.handle("what do you see").tier is Tier.COMPLEX   # real questions still reach perception


def test_hebrew_emergency_tiers():
    # Hebrew must hit the emergency/override/resume tiers DIRECTLY (no translation hop).
    for w in ("עצור", "עצרי", "עצרו", "תעצור", "סטופ", "חירום", "עצור עכשיו"):
        assert _c(w).tier is Tier.EMERGENCY, w
    assert _c("שליטה ידנית").tier is Tier.OVERRIDE
    assert _c("ידני").tier is Tier.OVERRIDE
    assert _c("אני בשליטה").tier is Tier.OVERRIDE
    assert _c("המשך").tier is Tier.RESUME
    assert _c("אוטומטי").tier is Tier.RESUME
    # emergency embedded in a longer Hebrew sentence still fires (length-independent tier)
    assert _c("רחפן תעצור מיד בבקשה").tier is Tier.EMERGENCY


def test_hebrew_emergency_dispatch():
    r = Router(_StubWire())
    res = r.handle("עצור")
    assert res.tier is Tier.EMERGENCY
    assert any(e[0] == "halt" for e in r.wire.log), "Hebrew stop must halt on the wire"
    # Hebrew question does NOT trip emergency and reaches the complex tier
    assert _c("מה אתה רואה עכשיו").tier is Tier.COMPLEX
