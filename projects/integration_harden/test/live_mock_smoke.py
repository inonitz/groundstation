"""Live end-to-end smoke: transcript -> Router -> DjiWire -> mock ApiServer (127.0.0.1).

Starts the mock itself, runs the full dispatch path over real HTTP, tears the mock down.
Agent-safe: loopback only, never a real drone.

v3 router semantics: directionals go out as /c/fly missions (not stick nudges) and the mock
ACKs missions WITHOUT integrating motion, so position is not asserted here -- takeoff/land
telemetry, dispatch results, and mode gating are. (If the mock ever integrates fly_by
missions into position3D, add position asserts back.)

Run: python3 projects/integration_harden/test/live_mock_smoke.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "projects"))
from integration_harden.dji_wire import DjiWire      # noqa: E402
from integration_harden.router import Router          # noqa: E402

MOCK = os.path.join(ROOT, "tools", "dji_mock", "mock_apiserver.py")


def status():
    with urllib.request.urlopen("http://127.0.0.1:8080/status/", timeout=2) as r:
        return json.load(r)


def wait_up(deadline_s=12):
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            status()
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    proc = subprocess.Popen([sys.executable, MOCK, "127.0.0.1", "8080"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_up(), "mock did not come up"
        wire = DjiWire()  # defaults to 127.0.0.1:8080
        r = Router(wire, on_complex=lambda t: print(f"  [perception stub] {t!r}"))

        res = r.handle("take off")
        assert res.dispatched, "takeoff not dispatched"
        assert status()["aircraft"]["isFlying"] is True, "takeoff did not set isFlying"
        print("  takeoff -> isFlying=True  OK")

        assert r.handle("go forward").dispatched, "forward mission not dispatched"
        assert r.handle("go up").dispatched, "up mission not dispatched"
        print("  forward + up -> /c/fly missions dispatched over live HTTP  OK")

        assert r.handle("manual").tier.name == "OVERRIDE" and r.mode == "manual"
        assert r.handle("go forward").dispatched is False, "manual must swallow verbs"
        print("  manual -> verbs swallowed  OK")

        assert r.handle("stop").tier.name == "EMERGENCY", "e-stop must fire in manual"
        print("  emergency stop fires in manual  OK")

        r.handle("resume")
        assert r.mode == "auto", "resume did not restore auto"
        res = r.handle("land")
        assert res.dispatched, "land not dispatched"
        assert status()["aircraft"]["isFlying"] is False, "land did not clear isFlying"
        print("  resume + land -> isFlying=False  OK")

        r.handle("how many people do you see")  # complex -> perception stub
        print("LIVE MOCK SMOKE PASSED")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
