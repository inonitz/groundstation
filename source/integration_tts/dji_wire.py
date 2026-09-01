"""Thin Python client for the recon-swarm ApiServer control wire.

Speaks the FROZEN protocol (docs/active/spec-dji-websocket-protocol.md):
  POST /c/takeoff, /c/land, /c/stop        discrete verbs
  WS   /c/ws/sticks  {vx,vy,vz,yaw}        body-frame m/s + yaw rate (deg/s), 18 Hz
  GET  /status/                            telemetry

SAFETY (CLAUDE.md): sending sticks/takeoff/land ARMS a real drone. This client defaults
to the mock at 127.0.0.1 and REFUSES any non-loopback host unless allow_real=True is
passed explicitly. The assistant only ever runs this against 127.0.0.1; the human runs
it against the phone. The surest kill is always the aircraft power button, not software.
"""
import asyncio
import ipaddress
import os
import json
import urllib.request
import urllib.error

# Conservative indoor envelope. Well under the app's kDjiMaxSpeedMps=2.0.
# NOTE: indoors the drone's VPS often refuses lateral/vertical sticks (see
# docs/NOTES / indoor-vps-denial); yaw + slow vertical are the reliable axes.
DEFAULT_SPEED_MPS = 0.5
DEFAULT_YAW_DEG_S = 45.0     # deg/s -- the app reads ANGULAR_VELOCITY in degrees, not rad
DEFAULT_NUDGE_S = 1.5        # bounded motion, then auto-hover
STREAM_HZ = 18


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

    def status(self) -> dict:
        with urllib.request.urlopen(
                f"http://{self.host}:{self.port}/status/", timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    # --- bounded velocity nudge --------------------------------------------------------
    async def _stream_sticks(self, vx, vy, vz, yaw, duration):
        import aiohttp  # lazy: only the WS nudge needs it
        url = f"ws://{self.host}:{self.port}/c/ws/sticks"
        period = 1.0 / STREAM_HZ
        async with aiohttp.ClientSession() as s:
            async with s.ws_connect(url) as ws:
                for _ in range(max(1, int(duration * STREAM_HZ))):
                    await ws.send_str(json.dumps({"vx": vx, "vy": vy, "vz": vz, "yaw": yaw}))
                    await asyncio.sleep(period)
                # Always end on an explicit hover so a dropped verb never runs away.
                await ws.send_str(json.dumps({"vx": 0.0, "vy": 0.0, "vz": 0.0, "yaw": 0.0}))

    def nudge(self, vx=0.0, vy=0.0, vz=0.0, yaw=0.0, duration=DEFAULT_NUDGE_S):
        """Body-frame: vx fwd+, vy right+, vz up+, yaw CW+ (deg/s). Streams for `duration`
        then hovers. Synchronous wrapper so the ASR callback thread can call it directly."""
        asyncio.run(self._stream_sticks(vx, vy, vz, yaw, duration))

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

    def fly_to(self, lat, lng, alt, max_velocity=8.0) -> int:
        """fly_gps: go to an absolute GPS point (lat/lng/alt), <=10 m/s."""
        return self.fly_mission([{"type": "fly_gps", "target": self._loc3(lat, lng, alt),
                                  "maxVelocity": float(max_velocity)}])

    def fly_circle(self, radius, velocity, count=1.0, clockwise=True, facing="INWARDS") -> int:
        """Orbit: radius (m), 1..6 m/s, count laps, facing INWARDS|OUTWARDS."""
        return self.fly_mission([{"type": "fly_circle", "radius": float(radius),
                                  "velocity": float(velocity), "count": float(count),
                                  "clockwise": bool(clockwise), "facing": facing}])

    def fly_square(self, side, velocity, clockwise=True) -> int:
        """Fly a square: side (m), 1..6 m/s."""
        return self.fly_mission([{"type": "fly_square", "side": float(side),
                                  "velocity": float(velocity), "clockwise": bool(clockwise)}])

    def scan_ground(self, radius=3.0, velocity=4.0, height=None, facing="OUTWARDS", clockwise=True) -> int:
        """Gimbal down + orbit to scan the ground."""
        a = {"type": "scan_ground", "radius": float(radius), "velocity": float(velocity),
             "facing": facing, "clockwise": bool(clockwise)}
        if height is not None: a["height"] = float(height)
        return self.fly_mission([a])

    def look_at(self, lat, lng, height=None) -> int:
        """Aim the gimbal (with body spin) at a GPS point."""
        a = {"type": "look_at", "target": self._loc2(lat, lng)}
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

    def delay(self, seconds) -> int:
        """Insert a wait (only meaningful mid-mission via fly_mission)."""
        return self.fly_mission([{"type": "delay", "seconds": float(seconds)}])

    REPORT_METRICS = ("battery", "user_location", "aircraft_location", "speed", "distance")

    def report_status(self, of=()) -> int:
        """Speak status via the aircraft TTS. of=[] -> all metrics. Valid: REPORT_METRICS."""
        return self.fly_mission([{"type": "report_status", "of": list(of)}])

    # -- direct (non-mission) endpoints -------------------------------------------------
    def fly_to_gps(self, lat, lng, alt, max_velocity=8.0) -> int:
        """POST /c/flyTo (dedicated route; same as the fly_gps action)."""
        return self._post_json("/c/flyTo", {"target": self._loc3(lat, lng, alt),
                                            "maxVelocity": float(max_velocity)})

    def look_at_gps(self, lat, lng, height=None) -> int:
        """POST /c/lookAt (dedicated route)."""
        body = {"target": self._loc2(lat, lng)}
        if height is not None: body["height"] = float(height)
        return self._post_json("/c/lookAt", body)

    def tts(self, text, lang="en", country=None, rate=1.0) -> int:
        """POST /tts -- make the phone speak."""
        body = {"text": text, "lang": lang, "rate": float(rate)}
        if country is not None: body["country"] = country
        return self._post_json("/tts", body)

    def key(self, group, key, func="GET", args=None) -> dict:
        """POST /key -- generic DJI SDK key access. func: GET|SET|ACTION. group e.g.
        'FlightControllerKey'/'GimbalKey'/'CameraKey', key e.g. 'KeyGoHome'. Returns the JSON."""
        body = {"group": group, "key": key, "func": func}
        if args is not None: body["args"] = args
        req = urllib.request.Request(f"http://{self.host}:{self.port}/key", method="POST",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def status_sub(self, which="battery") -> dict:
        """GET /status/<which> -- 'battery' or 'gps' detail blocks."""
        with urllib.request.urlopen(
                f"http://{self.host}:{self.port}/status/{which}", timeout=self.timeout) as r:
            return json.loads(r.read().decode())
