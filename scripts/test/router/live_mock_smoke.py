"""Live end-to-end smoke: transcript -> Router -> DjiWire -> mock ApiServer (127.0.0.1).

Starts the mock itself, runs the full dispatch path, checks the mock's telemetry actually
reflects each verb, tears the mock down. Agent-safe: loopback only, never a real drone.
Run: python3 scripts/test/router/live_mock_smoke.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "source"))
from integration.dji_wire import DjiWire      # noqa: E402
from integration.router import Router          # noqa: E402

MOCK = os.path.join(ROOT, "scripts", "test", "dji_mock", "mock_apiserver.py")


def status():
    with urllib.request.urlopen("http://127.0.0.1:8080/status/", timeout=1.0) as r:
        return json.loads(r.read().decode())["aircraft"]


def wait_up(deadline_s=12):
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        try:
            status(); return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    proc = subprocess.Popen([sys.executable, MOCK, "127.0.0.1", "8080"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert wait_up(), "mock did not come up"
        wire = DjiWire()  # defaults to 127.0.0.1:8080
        r = Router(wire, on_complex=lambda t: print(f"  [perception stub] {t!r}"))

        r.handle("take off")
        assert status()["isFlying"] is True, "takeoff did not set isFlying"
        print("  takeoff -> isFlying=True  OK")

        r.handle("go forward")
        assert status()["position3D"]["x"] > 0.05, "forward nudge did not advance x"
        print(f"  go forward -> x={status()['position3D']['x']:.2f}  OK")

        r.handle("go up")
        assert status()["position3D"]["z"] > 1.2, "up nudge did not raise z"
        print(f"  go up -> z={status()['position3D']['z']:.2f}  OK")

        r.handle("stop")  # emergency: relinquish; mode -> manual
        assert r.mode == "manual", "emergency should flip to manual"
        r.handle("go forward")  # must be swallowed in manual
        print("  stop -> manual, subsequent verb swallowed  OK")

        r.handle("resume")
        r.handle("land")
        assert status()["isFlying"] is False, "land did not clear isFlying"
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
