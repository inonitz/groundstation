"""Thin Python client for the recon-swarm ApiServer control wire.

Speaks the FROZEN protocol (docs/specs/spec-dji-websocket-protocol.md):
  POST /c/takeoff, /c/land, /c/stop        discrete verbs
  POST /c/fly [Action...]                  native flight actions (bare JSON array)

Telemetry (GET /status/) is NOT spoken here: it is read-only, and its consumers
(tools/dji_mock/*) call it directly over
urllib/curl. This client is the command path only.

SAFETY (CLAUDE.md): sending takeoff/land/fly ARMS a real drone. This client defaults
to the mock at 127.0.0.1 and REFUSES any non-loopback host unless allow_real=True is
passed explicitly. The assistant only ever runs this against 127.0.0.1; the human runs
it against the phone. The surest kill is always the aircraft power button, not software.

Every POST returns an HTTP-style status code. 0 means the server was unreachable.
"""
import http.client
import json
import os
import sys
import urllib.error
import urllib.request

import config
from fatal import die
from system.status import BOARD, FAILED, STARTING, UP
from system.supervisor import port_open

UNREACHABLE = 0   # the status _post returns when there is no HTTP response at all
LATCHED = 409     # KillSwitch refused the verb: the operator pressed M (not a transport failure)


def sent(code):
    """True only when the phone accepted the command (HTTP 2xx). 0 (unreachable) or an error status means
    the command did NOT reach the aircraft, and the caller must say so."""
    return code is not None and 200 <= code < 300


def _is_loopback(host):
    """True ONLY for localhost, ::1, or a dotted IPv4 address 127.a.b.c (each part 0-255). A hostname that
    merely starts with "127." (e.g. "127.drone.lan") is NOT loopback: it can resolve to a real phone.
    Plain string checks, no throw (the drone-safety guard, review finding R2)."""
    if host in ("localhost", "::1"):
        return True
    parts = str(host).split(".")
    if len(parts) != 4 or parts[0] != "127":
        return False
    return all(p.isdigit() and int(p) <= 255 for p in parts)


class DjiWire:
    def __init__(self, host="127.0.0.1", port=8080, allow_real=False, timeout=3.0):
        if not _is_loopback(host) and not allow_real:
            die(f"refusing non-loopback host {host!r} without allow_real=True. "
                "Real-drone commands are HUMAN-run only (CLAUDE.md drone-safety rules).")
        self.host = host
        self.port = port
        self.timeout = timeout
        BOARD.report("drone link", STARTING, f"{host}:{port}: no command sent yet")

    @classmethod
    def from_env(cls):
        """Build from config.WIRE_* (derived from CONTROL=mock|real): mock -> 127.0.0.1:8079 not real;
        real -> PHONE_IP:8080 real (HUMAN-run only). CONTROL is the one decision; config derives the rest."""
        return cls(host=config.WIRE_HOST, port=config.WIRE_PORT, allow_real=config.WIRE_REAL)

    def _request(self, path, data=None, headers=None):
        """POST to path. Returns the HTTP status, or UNREACHABLE (0) when there is no response.
        urllib is the throwing party: an error status and an unreachable host both convert to a code."""
        url = f"http://{self.host}:{self.port}{path}"
        req = urllib.request.Request(url, method="POST", data=data or b"", headers=headers or {})
        note = f"{path}  {data.decode()}" if data else path
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                print(f"[dji] POST {note} -> HTTP {r.status}", flush=True)
                code = r.status
        except urllib.error.HTTPError as e:                 # the server answered with an error status
            print(f"[dji] POST {note} -> HTTP {e.code} ERR: {e.reason}", flush=True)   # no e.read(): it can throw too
            code = e.code
        except (urllib.error.URLError, OSError, http.client.HTTPException) as e:   # no usable HTTP reply at all
            print(f"[dji] POST {note} -> UNREACHABLE: {e!r}", flush=True)
            BOARD.report("drone link", FAILED, f"{path} got no answer from {self.host}:{self.port} "
                         "(no auto-reconnect yet: the drone-link resilience task)")
            return UNREACHABLE
        BOARD.report("drone link", UP)                      # the ApiServer answered: the link works
        return code

    # --- discrete verbs ----------------------------------------------------------------
    # Motion verbs. The recognizer no longer calls these directly: Gemma sends each action as a mission
    # dict through fly_mission() -> POST /c/fly (2026-09-19). They are kept on purpose, NOT dead code --
    # control/kill.py guards each by name (KillSwitch.MOTION) as defence-in-depth, and test_kill.py checks it.
    def takeoff(self):
        return self._request("/c/takeoff")

    def land(self):
        return self._request("/c/land")

    def stop(self):
        """POST /c/stop = controller.stop(emergency=true): stops the aircraft and relinquishes our
        virtual-stick control (hands authority back to the RC). It fires KeyEmergencyStop under the
        hood, but per the app dev this does NOT crash the aircraft -- it is the app's defined STOP.
        This verb is ONLY the stop; it does not change our auto/manual mode. After a stop the next
        mission verb (/c/fly) re-takes stick control automatically (controller.fly -> takeControl)."""
        return self._request("/c/stop")

    # --- mission / action API (POST /c/fly [Action...]  -- bare JSON array) -------------
    def fly_mission(self, actions):
        """POST /c/fly -- run native flight Actions sequentially on the aircraft. Returns
        immediately (the app runs the mission async). Each action is a dict with a 'type'
        discriminator, e.g. {'type':'spin_by','degrees':360}. Grammar: app dto/actions/*."""
        return self._request("/c/fly", data=json.dumps(list(actions)).encode(),
                             headers={"Content-Type": "application/json"})

    def halt(self):
        """Stop current motion WITHOUT /c/stop: a new mission preempts the running one
        (controller.fly cancels the previous flight job) and delay:0 waits 0s. KEEPS our
        virtual-stick control (fly -> takeControl), so the user flies again immediately."""
        return self.fly_mission([{"type": "delay", "seconds": 0.0}])

    def spin_by(self, degrees=360.0):
        """Native precise-angle yaw via the app's SpinBy action -- turns EXACTLY `degrees`
        relative to current heading. Replaces the timed yaw-stick nudge (~67deg per 1.5s)."""
        return self.fly_mission([{"type": "spin_by", "degrees": float(degrees)}])

    def fly_by(self, dx=0.0, dy=0.0, dz=0.0, velocity=4.0):
        """Native relative move (metres, body-frame: x fwd+, y right+, z up+) via FlyBy."""
        return self.fly_mission([{"type": "fly_by", "dx": float(dx), "dy": float(dy),
                                  "dz": float(dz), "velocity": float(velocity)}])

    def gimbal_pitch(self, angle):
        """Native camera gimbal pitch (-90..60 deg) via GimbalPitch."""
        return self.fly_mission([{"type": "gimbal_pitch", "angle": float(angle)}])

    def scan_ground(self, radius=3.0, velocity=4.0, height=None, facing="OUTWARDS", clockwise=True):
        """Gimbal down + orbit to scan the ground."""
        action = {"type": "scan_ground", "radius": float(radius), "velocity": float(velocity),
                  "facing": facing, "clockwise": bool(clockwise)}
        if height is not None:
            action["height"] = float(height)
        return self.fly_mission([action])

    def go_home_to_user(self, max_velocity=4.0):
        """'home': fly back to the user's live phone location."""
        return self.fly_mission([{"type": "home", "maxVelocity": float(max_velocity)}])

    def follow_me(self, cruise_height=7.0, follow_distance=3.5, max_velocity=8.0):
        return self.fly_mission([{"type": "follow_me", "cruiseHeight": float(cruise_height),
                                  "followDistance": float(follow_distance),
                                  "maxVelocity": float(max_velocity)}])

    def track_me(self, fov_tolerance=17.0):
        """Camera-track the user (gimbal follows, no flight)."""
        return self.fly_mission([{"type": "track_me", "fovTolerance": float(fov_tolerance)}])

    def wave(self, count=2):
        """Greet the user by waving the camera."""
        return self.fly_mission([{"type": "wave", "count": int(count)}])


def mock_ready():
    """True once the mock ApiServer accepts a TCP connection on its port."""
    return port_open("127.0.0.1", config.MOCK_WIRE_PORT)


def start_services(supervisor, log_dir):
    """In mock control mode, start the DJI API test double (was run.sh's background mock). Real mode
    starts nothing: the phone runs the real ApiServer."""
    if config.WIRE_REAL:
        return
    env = dict(os.environ, MOCK_CMD_LOG=os.path.join(log_dir, "mock_commands.log"))
    argv = [sys.executable, config.MOCK_APISERVER_PATH, "127.0.0.1", str(config.MOCK_WIRE_PORT)]
    supervisor.start("mock", argv, env=env, ready=mock_ready, ready_timeout_s=25.0,
                     log_path=os.path.join(log_dir, "proc-mock.log"))
    return
