"""The client for the DJI phone app (the recon-swarm ApiServer), or the mock that stands
in for it.

Speaks the FROZEN protocol (docs/specs/spec-dji-websocket-protocol.md):
    POST /c/takeoff, /c/land, /c/stop    discrete verbs
    POST /c/fly [Action...]              native flight actions (a bare JSON array)

Telemetry (GET /status/) is read here only as the health probe (below); its other
consumers (tools/dji_mock/*) call it directly over urllib/curl. This client is the
command path.

SAFETY (CLAUDE.md): sending takeoff/land/fly ARMS a real drone. This client defaults to
the mock at 127.0.0.1 and REFUSES any non-loopback host unless allow_real=True is passed
explicitly. The assistant only ever runs this against 127.0.0.1; the human runs it
against the phone. The surest kill is always the aircraft power button, not software.

Every request returns an http.HTTPStatus (the standard library's), or None when the phone
app did not answer at all.

STATUS ("dji app" row): UP while the app answers. When a request gets no answer, the row
goes WAITING (orange): the laptop cannot restart the phone app, the user must fix it. A
probe then checks the port every config.WAITING_RETRY_SECONDS and turns the row UP when
the app answers again. The app never dies because of the phone (owner ruling 2026-09-23).
/tts is served by the same app on the same port, so text-to-speech is one more request
here (speak()).

The TRANSMIT SWITCH: when it is off, every motion request (takeoff, land, /c/fly) returns
HTTPStatus.CONFLICT (409) and nothing leaves the laptop. /c/stop is never blocked.
Control is the switch's only user (owner ruling 2026-09-23): the F4 key and the spoken
manual/auto both go through control.
"""
import json
import os
import sys
import threading
from http import HTTPStatus

import config
from system.fatal import die
from system.status import STARTING, UP, WAITING, Status
from system.supervisor import ProcessSpec
from util.guarded import http_request
from util.net import JSON_HEADERS, port_open

_KNOWN_CODES = {int(status) for status in HTTPStatus}
# a halt: a new mission pre-empts the running one, and delay:0 waits 0 s
HALT_MISSION = [{"type": "delay", "seconds": 0.0}]


def _status(code):
    """An HTTP code as an HTTPStatus. The phone app only sends standard codes; anything
    else is reported and read as BAD_GATEWAY (HTTPStatus() throws on an unknown code)."""
    if code in _KNOWN_CODES:
        return HTTPStatus(code)

    print(f"[dji] the phone app sent a non-standard HTTP code {code}", flush=True)
    return HTTPStatus.BAD_GATEWAY


def _is_loopback(host):
    """True ONLY for localhost, ::1, or a dotted IPv4 address 127.a.b.c (each part
    0-255). A hostname that merely starts with "127." (e.g. "127.drone.lan") is NOT
    loopback: it can resolve to a real phone.
    Plain string checks, no throw (the drone-safety guard, review finding R2)."""
    if host in ("localhost", "::1"):
        return True

    parts = str(host).split(".")
    if len(parts) != 4 or parts[0] != "127":
        return False
    return all(p.isdigit() and int(p) <= 255 for p in parts)


class DjiApp:
    """Owns the "dji app" status row (status())."""

    def __init__(
        self,
        host="127.0.0.1",
        port=8080,
        allow_real=False,
        timeout=3.0
    ):
        if not _is_loopback(host) and not allow_real:
            die(
                f"refusing non-loopback host {host!r} without allow_real=True. "
                "Real-drone commands are HUMAN-run only (CLAUDE.md drone-safety rules)."
            )

        self.host = host
        self.port = port
        self.timeout = timeout
        self._transmit = True
        self._probe_lock = threading.Lock()
        self._probing = False
        self._closed = threading.Event()

        self._status = Status("dji app", STARTING, f"{host}:{port}")
        self._start_probe()                 # UP once the app answers, WAITING until then
        return

    @classmethod
    def from_env(cls):
        """Build from config.DJI_* (derived from CONTROL=mock|real): mock ->
        127.0.0.1:8079, not real; real -> PHONE_IP:8080, real (HUMAN-run only). CONTROL
        is the one decision; config derives the rest."""
        return cls(
            host=config.DJI_HOST,
            port=config.DJI_PORT,
            allow_real=config.DJI_REAL
        )

    def close(self):
        """Stop the probe (shutdown, tests)."""
        self._closed.set()
        return

    def status(self):
        """[(name, state, detail)]: the "dji app" row."""
        return [self._status.row()]

    def _http(self, method, path, data=None, headers=None, quiet=False):
        """One HTTP request. -> an HTTPStatus, or None when there is no usable reply.
        An error status is a reply (it is returned); only no reply at all is None."""
        note = f"{path}  {data.decode()}" if data else path
        code, _reply, error = http_request(
            self.host,
            self.port,
            method,
            path,
            body=data,
            headers=headers,
            timeout=self.timeout
        )
        if code is None:
            if not quiet:
                print(f"[dji] {method} {note} -> no answer: {error}", flush=True)
            return None

        if not quiet:
            print(f"[dji] {method} {note} -> HTTP {code}", flush=True)
        return _status(code)

    def _request(self, path, data=None, headers=None):
        """POST to path. -> an HTTPStatus, or None. Any answer means the app is there
        (UP); no answer starts the probe (WAITING)."""
        status = self._http("POST", path, data or b"", headers)
        if status is None:
            self._start_probe()
            return None

        self._status.set(UP)
        return status

    # --- status: the probe that waits for the user to fix the phone app ------------
    def _start_probe(self):
        """Start the one probe thread, unless it already runs."""
        with self._probe_lock:
            if self._probing:
                return
            self._probing = True

        threading.Thread(
            target=self._probe,
            name="dji-app-probe",
            daemon=True
        ).start()
        return

    def _probe(self):
        """WAITING until GET /status/ (read-only telemetry) answers 2xx, then UP. The
        phone is outside the laptop, so this checks on a timer: there is no event to wait
        on."""
        status = None

        while True:
            status = self._http("GET", "/status/", quiet=True)
            if status is not None and status.is_success:
                self._status.set(UP)
                break
            self._status.set(
                WAITING,
                f"no answer from {self.host}:{self.port}: the user "
                f"must fix the phone app. Retry every "
                f"{config.WAITING_RETRY_SECONDS:.0f}s"
            )
            if self._closed.wait(config.WAITING_RETRY_SECONDS):
                break                                  # closed: stop checking

        with self._probe_lock:
            self._probing = False
        return

    # --- the transmit switch -------------------------------------------------------
    def set_transmit(self, enabled):
        """On: motion requests are sent. Off: they return HTTPStatus.CONFLICT. A plain
        bool: control is the one caller and holds its own lock around every change."""
        self._transmit = bool(enabled)
        return

    def transmitting(self):
        return self._transmit

    def _motion(self, path, data=None, headers=None):
        """Send a motion request, or return CONFLICT when the transmit switch is off."""
        if not self._transmit:
            print(f"[dji] blocked {path}: the transmit switch is off", flush=True)
            return HTTPStatus.CONFLICT     # blocked: nothing left the laptop
        return self._request(path, data, headers)

    # --- requests ------------------------------------------------------------------
    def takeoff(self):
        return self._motion("/c/takeoff")

    def land(self):
        return self._motion("/c/land")

    def stop(self):
        """POST /c/stop = controller.stop(emergency=true): stops the aircraft and
        relinquishes our virtual-stick control (hands authority back to the RC). Per the
        app dev this does NOT crash the aircraft: it is the app's defined STOP. NEVER
        blocked by the transmit switch."""
        return self._request("/c/stop")

    def fly_mission(self, actions):
        """POST /c/fly -- run native flight Actions in order on the aircraft. Returns at
        once (the app runs the mission async). Each action is a dict with a 'type'
        discriminator, e.g. {'type': 'spin_by', 'degrees': 360}. Grammar: the app's
        dto/actions/*."""
        body = json.dumps(list(actions)).encode()
        return self._motion("/c/fly", data=body, headers=JSON_HEADERS)

    def speak(self, text):
        """POST /tts: the phone app speaks the text (Android TextToSpeech, Hebrew). Never
        blocked by the transmit switch. A failure shows on the "dji app" row; it never
        kills the app."""
        body = {"text": text, "lang": config.TTS_LANG, "rate": config.TTS_RATE}
        data = json.dumps(body).encode()
        return self._request("/tts", data=data, headers=JSON_HEADERS)

    def halt(self):
        """Stop current motion WITHOUT /c/stop: a new mission pre-empts the running one
        and delay:0 waits 0 s. KEEPS our virtual-stick control. Blocked when transmit is
        off."""
        return self.fly_mission(HALT_MISSION)


def mock_ready():
    """True once the mock phone app accepts a TCP connection on its port."""
    return port_open("127.0.0.1", config.MOCK_DJI_PORT)


def mock_process(log_dir):
    """The mock phone app for the supervisor (only when CONTROL=mock). It stands in for
    the phone app, so past its restart budget it WAITS for the user instead of killing
    the app."""
    env = dict(os.environ, MOCK_CMD_LOG=os.path.join(log_dir, "mock_commands.log"))
    return ProcessSpec(
        name="mock",
        argv=[
            sys.executable,
            config.MOCK_APISERVER_PATH,
            "127.0.0.1",
            str(config.MOCK_DJI_PORT),
        ],
        env=env,
        ready=mock_ready,
        ready_timeout_s=25.0,
        log_path=os.path.join(log_dir, "proc-mock.log"),
        required=False,
    )
