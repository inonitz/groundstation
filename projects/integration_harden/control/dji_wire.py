"""Thin Python client for the recon-swarm ApiServer control wire.

Speaks the FROZEN protocol (docs/specs/spec-dji-websocket-protocol.md):
  POST /c/takeoff, /c/land, /c/stop        discrete verbs
  POST /c/fly {mission:[Action...]}        native flight actions

Telemetry (GET /status/) is NOT spoken here: it is read-only, and its consumers
(test/live_mock_smoke.py, video/video_doctor.py, tools/dji_mock/*) each call it directly over
urllib/curl. This client is the command path only.

SAFETY (CLAUDE.md): sending takeoff/land/fly ARMS a real drone. This client defaults
to the mock at 127.0.0.1 and REFUSES any non-loopback host unless allow_real=True is
passed explicitly. The assistant only ever runs this against 127.0.0.1; the human runs
it against the phone. The surest kill is always the aircraft power button, not software.
"""
import ipaddress
import os
import json
import urllib.request
import urllib.error

def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False

class DjiWire:
    def __init__(self, host="127.0.0.1", port=8080, allow_real=False, timeout=3.0):
        if not _is_loopback(host) and not allow_real:
            raise RuntimeError(
                f"refusing non-loopback host {host!r} without allow_real=True. "
                "Real-drone commands are HUMAN-run only (CLAUDE.md drone-safety rules)."
            )
        self.host = host
        self.port = port
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        """Build from MVD_WIRE_* env: host (default 127.0.0.1 mock), port (8080), REAL (off).
        Real-drone use = MVD_WIRE_HOST=<phone-ip> MVD_WIRE_REAL=1, and a HUMAN runs it."""
        host = os.environ.get("MVD_WIRE_HOST", "127.0.0.1")
        port = int(os.environ.get("MVD_WIRE_PORT", "8080"))
        real = os.environ.get("MVD_WIRE_REAL", "").lower() in ("1", "true", "yes")
        return cls(host=host, port=port, allow_real=real)

    # --- discrete verbs ----------------------------------------------------------------
    def _post(self, path: str) -> int:
        url = f"http://{self.host}:{self.port}{path}"
        req = urllib.request.Request(url, method="POST", data=b"")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                print(f"[dji] POST {path} -> HTTP {r.status}", flush=True)
                return r.status
        except urllib.error.HTTPError as e:
            print(f"[dji] POST {path} -> HTTP {e.code} ERR: {e.read()[:200]!r}", flush=True)
            return e.code
        except Exception as e:
            print(f"[dji] POST {path} -> UNREACHABLE: {e}", flush=True); raise

    def takeoff(self) -> int:
        return self._post("/c/takeoff")

    def land(self) -> int:
        return self._post("/c/land")

    def stop(self) -> int:
        """POST /c/stop = controller.stop(emergency=true): stops the aircraft and relinquishes our
        virtual-stick control (hands authority back to the RC). It fires KeyEmergencyStop under the
        hood, but per the app dev this does NOT crash the aircraft -- it is the app's defined STOP.
        This verb is ONLY the stop; it does not change our auto/manual mode. After a stop the next
        mission verb (/c/fly) re-takes stick control automatically (controller.fly -> takeControl)."""
        return self._post("/c/stop")

    # --- mission / action API (POST /c/fly {mission:[Action...]}) ----------------------
    def _post_json(self, path: str, obj) -> int:
        payload = json.dumps(obj)
        req = urllib.request.Request(
            f"http://{self.host}:{self.port}{path}", method="POST", data=payload.encode(),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                print(f"[dji] POST {path}  {payload}  -> HTTP {r.status}", flush=True)
                return r.status
        except urllib.error.HTTPError as e:
            print(f"[dji] POST {path}  {payload}  -> HTTP {e.code} ERR: {e.read()[:200]!r}", flush=True)
            return e.code
        except Exception as e:
            print(f"[dji] POST {path}  {payload}  -> UNREACHABLE: {e}", flush=True); raise

    def fly_mission(self, actions: list) -> int:
        """POST /c/fly -- run native flight Actions sequentially on the aircraft. Returns
        immediately (the app runs the mission async). Each action is a dict with a 'type'
        discriminator, e.g. {'type':'spin_by','degrees':360}. Grammar: app dto/actions/*."""
        return self._post_json("/c/fly", {"mission": list(actions)})

    def halt(self) -> int:
        """Stop current motion WITHOUT /c/stop: a new mission preempts the running one
        (controller.fly cancels the previous flight job) and delay:0 waits 0s. KEEPS our
        virtual-stick control (fly -> takeControl), so the user flies again immediately."""
        return self.fly_mission([{"type": "delay", "seconds": 0.0}])

    def spin_by(self, degrees: float = 360.0) -> int:
        """Native precise-angle yaw via the app's SpinBy action -- turns EXACTLY `degrees`
        relative to current heading. Replaces the timed yaw-stick nudge (~67deg per 1.5s)."""
        return self.fly_mission([{"type": "spin_by", "degrees": float(degrees)}])

    def fly_by(self, dx=0.0, dy=0.0, dz=0.0, velocity=4.0) -> int:
        """Native relative move (metres, body-frame: x fwd+, y right+, z up+) via FlyBy."""
        return self.fly_mission([{"type": "fly_by", "dx": float(dx), "dy": float(dy),
                                  "dz": float(dz), "velocity": float(velocity)}])

    def gimbal_pitch(self, angle: float) -> int:
        """Native camera gimbal pitch (-90..60 deg) via GimbalPitch."""
        return self.fly_mission([{"type": "gimbal_pitch", "angle": float(angle)}])

    # -- single-action convenience wrappers (each = one POST /c/fly mission) -------------
    @staticmethod
    def _loc3(lat, lng, alt): return {"latitude": lat, "longitude": lng, "altitude": alt}
    @staticmethod
    def _loc2(lat, lng):      return {"latitude": lat, "longitude": lng}

    def scan_ground(self, radius=3.0, velocity=4.0, height=None, facing="OUTWARDS", clockwise=True) -> int:
        """Gimbal down + orbit to scan the ground."""
        a = {"type": "scan_ground", "radius": float(radius), "velocity": float(velocity),
             "facing": facing, "clockwise": bool(clockwise)}
        if height is not None: a["height"] = float(height)
        return self.fly_mission([a])

    def go_home_to_user(self, max_velocity=4.0) -> int:
        """'home': fly back to the user's live phone location."""
        return self.fly_mission([{"type": "home", "maxVelocity": float(max_velocity)}])

    def follow_me(self, cruise_height=7.0, follow_distance=3.5, max_velocity=8.0) -> int:
        return self.fly_mission([{"type": "follow_me", "cruiseHeight": float(cruise_height),
                                  "followDistance": float(follow_distance),
                                  "maxVelocity": float(max_velocity)}])

    def track_me(self, fov_tolerance=17.0) -> int:
        """Camera-track the user (gimbal follows, no flight)."""
        return self.fly_mission([{"type": "track_me", "fovTolerance": float(fov_tolerance)}])

    def wave(self, count=2) -> int:
        """Greet the user by waving the camera."""
        return self.fly_mission([{"type": "wave", "count": int(count)}])
