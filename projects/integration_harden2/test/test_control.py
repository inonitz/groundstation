"""Tests for control/: the router tiers and the kill switch. The wire is a fake."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import time

import config
from control import dji_wire
from control.commands import Tier, classify
from control.kill import KillSwitch
from control.router import Router
from system.status import StatusBoard, UP
from system.supervisor import Supervisor


# ==================== router ====================
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


# ==================== kill ====================
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
    assert w.fly_mission([{"type": "fly_by", "dx": 1}]) == dji_wire.LATCHED
    assert w.takeoff() == dji_wire.LATCHED and w.land() == dji_wire.LATCHED and w.fly_by(dx=1) == dji_wire.LATCHED
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
    assert w.takeoff() == dji_wire.LATCHED
    assert ks.toggle() is False and not ks.killed and w.takeoff() == 200


# ==================== mock ApiServer start ====================
class RecordingSupervisor:
    def __init__(self):
        self.started = []

    def start(self, name, argv, env=None, ready=None, ready_timeout_s=0, log_path=None):
        self.started.append((name, argv, ready))


def test_mock_mode_starts_the_mock_and_real_mode_does_not(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WIRE_REAL", False)
    sup = RecordingSupervisor()
    dji_wire.start_services(sup, str(tmp_path))
    name, argv, ready = sup.started[0]
    assert name == "mock" and argv[1:] == [config.MOCK_APISERVER_PATH, "127.0.0.1", str(config.MOCK_WIRE_PORT)]
    assert ready is dji_wire.mock_ready
    monkeypatch.setattr(config, "WIRE_REAL", True)
    sup2 = RecordingSupervisor()
    dji_wire.start_services(sup2, str(tmp_path))
    assert sup2.started == []


def test_the_real_mock_starts_under_the_supervisor_and_answers(tmp_path, monkeypatch):
    """REAL path, mock only (127.0.0.1): the supervisor starts the real mock, the wire talks HTTP to it."""
    import socket
    with socket.socket() as probe:                     # a port nothing else holds (a stray mock may own 8079)
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    monkeypatch.setattr(config, "MOCK_WIRE_PORT", free_port)
    monkeypatch.setattr(config, "WIRE_REAL", False)
    board = StatusBoard()
    sup = Supervisor(board=board, max_restarts=1, stable_s=60)
    dji_wire.start_services(sup, str(tmp_path))
    end = time.monotonic() + 30
    while board.state("mock") != UP and time.monotonic() < end:
        time.sleep(0.1)
    assert board.state("mock") == UP
    wire = dji_wire.DjiWire("127.0.0.1", config.MOCK_WIRE_PORT)
    assert dji_wire.BOARD.state("drone link") == "STARTING"        # no command sent yet
    assert wire.halt() == 200
    assert dji_wire.BOARD.state("drone link") == UP
    sup.stop_all()
    assert not dji_wire.mock_ready()


# ==================== a stop must never read as done when it did not arrive (review R1) ====================
class DeadWire:
    """The phone is unreachable: every POST returns 0 (dji_wire.UNREACHABLE)."""
    def stop(self): return 0
    def halt(self): return 0


def test_kill_that_did_not_arrive_says_so():
    said = []
    ks = KillSwitch(DeadWire(), say=said.append)
    assert ks.kill() == 0 and ks.killed
    assert said[-1].startswith("KILL FAILED: /c/stop -> HTTP 0") and "RC" in said[-1]
    assert "Motion stopped" not in said[-1]


def test_router_stop_and_override_that_did_not_arrive_say_so():
    r = Router(DeadWire())
    assert "FAILED (HTTP 0)" in r.handle("עצור").action
    res = r.handle("שליטה ידנית")
    assert res.tier is Tier.OVERRIDE and r.mode == "manual"      # flight refused even though the stop failed
    assert "FAILED (HTTP 0)" in res.action


def test_sent_is_true_only_for_2xx():
    assert dji_wire.sent(200) and dji_wire.sent(204)
    assert not dji_wire.sent(0) and not dji_wire.sent(409) and not dji_wire.sent(500) and not dji_wire.sent(None)


def test_loopback_guard_accepts_only_real_loopback_addresses():
    for host in ("localhost", "::1", "127.0.0.1", "127.1.2.3"):
        assert dji_wire._is_loopback(host), host
    for host in ("127.drone.lan", "127.0.0.1.nip.io", "127.0.0", "127.0.0.256", "10.0.0.1", "", "127.a.b.c"):
        assert not dji_wire._is_loopback(host), host


def test_latch_refusal_is_not_reported_as_a_comms_failure():
    class LatchedWire:
        def halt(self): return dji_wire.LATCHED
    res = Router(LatchedWire()).handle("עצור")
    assert "kill latch is on" in res.action and "FAILED" not in res.action


def test_a_malformed_phone_reply_is_a_status_not_an_exception():
    """R11: a reply that is not valid HTTP (a garbage status line) returns UNREACHABLE; it never throws."""
    import socketserver
    import threading

    class Garbage(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(4096)
            self.request.sendall(b"NOT-HTTP garbage\r\n\r\n")

    srv = socketserver.TCPServer(("127.0.0.1", 0), Garbage)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    assert dji_wire.DjiWire("127.0.0.1", srv.server_address[1]).stop() == dji_wire.UNREACHABLE
    assert dji_wire.BOARD.state("drone link") == "FAILED"          # red on the panel; no die (drone ruling)
    srv.shutdown()
    srv.server_close()


# ==================== the wire's verbs (all cases) ====================
class _Recorder:
    """A stand-in ApiServer on 127.0.0.1 that records (path, json-body) and answers 200."""
    def __init__(self):
        import http.server
        import threading
        seen = self.seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n) if n else b""
                seen.append((self.path, json.loads(raw) if raw else None))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                return
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.wire = dji_wire.DjiWire("127.0.0.1", self.srv.server_address[1])

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def test_every_verb_posts_its_path_and_action():
    r = _Recorder()
    w = r.wire
    calls = [(w.takeoff, (), "/c/takeoff", None), (w.land, (), "/c/land", None), (w.stop, (), "/c/stop", None),
             (w.halt, (), "/c/fly", [{"type": "delay", "seconds": 0.0}]),
             (w.spin_by, (90,), "/c/fly", [{"type": "spin_by", "degrees": 90.0}]),
             (w.fly_by, (1, -2, 3), "/c/fly", [{"type": "fly_by", "dx": 1.0, "dy": -2.0, "dz": 3.0, "velocity": 4.0}]),
             (w.gimbal_pitch, (-45,), "/c/fly", [{"type": "gimbal_pitch", "angle": -45.0}]),
             (w.go_home_to_user, (), "/c/fly", [{"type": "home", "maxVelocity": 4.0}]),
             (w.follow_me, (), "/c/fly", [{"type": "follow_me", "cruiseHeight": 7.0, "followDistance": 3.5, "maxVelocity": 8.0}]),
             (w.track_me, (), "/c/fly", [{"type": "track_me", "fovTolerance": 17.0}]),
             (w.wave, (3,), "/c/fly", [{"type": "wave", "count": 3}])]
    for fn, args, path, body in calls:
        assert fn(*args) == 200
        assert r.seen[-1] == (path, body), fn.__name__
    w.scan_ground(radius=2, height=5)
    assert r.seen[-1][1][0]["type"] == "scan_ground" and r.seen[-1][1][0]["height"] == 5.0
    w.scan_ground()
    assert "height" not in r.seen[-1][1][0]                  # no height unless asked
    r.close()


def test_from_env_uses_the_config_target(monkeypatch):
    monkeypatch.setattr(config, "WIRE_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "WIRE_PORT", 8079)
    monkeypatch.setattr(config, "WIRE_REAL", False)
    w = dji_wire.DjiWire.from_env()
    assert (w.host, w.port) == ("127.0.0.1", 8079)


def test_a_real_host_without_allow_real_dies():
    import subprocess
    import sys as _sys
    here = os.path.dirname(__file__)
    code = f"import sys; sys.path.insert(0, {os.path.join(here, '..')!r}); from control.dji_wire import DjiWire; DjiWire('10.0.0.5')"
    r = subprocess.run([_sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 1 and "refusing non-loopback host '10.0.0.5'" in r.stderr
