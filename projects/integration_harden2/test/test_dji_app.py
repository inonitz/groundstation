"""Tests for dji_app/: the phone-app client (status codes, the mock-only guard, every
request's path and body, a malformed reply) and the mock under the supervisor. Real
HTTP servers, no fakes of the client itself."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time
from http import HTTPStatus

import config
import dji_app.client
from system.status import UP
from system.supervisor import Supervisor
from support import RecordingPhone, dead_port, state_of


def test_the_mock_process_waits_instead_of_dying(tmp_path):
    spec = dji_app.client.mock_process(str(tmp_path))
    assert spec.name == "mock" and spec.argv[1:] == [
        config.MOCK_APISERVER_PATH, "127.0.0.1", str(config.MOCK_DJI_PORT)
    ]
    assert spec.ready is dji_app.client.mock_ready
    assert spec.required is False      # the mock stands in for the phone app: it WAITS


def test_a_status_is_the_standard_library_s_http_status():
    assert dji_app.client._status(200) is HTTPStatus.OK
    assert dji_app.client._status(409) is HTTPStatus.CONFLICT
    assert dji_app.client._status(599) is HTTPStatus.BAD_GATEWAY   # non-standard code


def test_the_real_mock_starts_under_the_supervisor_and_answers(tmp_path, monkeypatch):
    """REAL path, mock only (127.0.0.1): the supervisor starts the
    real mock, the phone app talks HTTP to it."""
    import socket
    # a port nothing else holds (a stray mock may own 8079)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    monkeypatch.setattr(config, "MOCK_DJI_PORT", free_port)
    monkeypatch.setattr(config, "DJI_REAL", False)
    sup = Supervisor(max_restarts=1, stable_s=60)
    mock = sup.start(dji_app.client.mock_process(str(tmp_path)))
    end = time.monotonic() + 30
    while state_of(mock) != UP and time.monotonic() < end:
        time.sleep(0.1)
    assert state_of(mock) == UP
    dji = dji_app.client.DjiApp("127.0.0.1", config.MOCK_DJI_PORT)
    end = time.monotonic() + 10
    # the probe: GET /status/
    while state_of(dji) != UP and time.monotonic() < end:
        time.sleep(0.05)
    assert state_of(dji) == UP
    assert dji.halt() == 200
    dji.close()
    sup.stop_all()
    assert not dji_app.client.mock_ready()


def test_loopback_guard_accepts_only_real_loopback_addresses():
    for host in ("localhost", "::1", "127.0.0.1", "127.1.2.3"):
        assert dji_app.client._is_loopback(host), host
    for host in (
        "127.drone.lan",
        "127.0.0.1.nip.io",
        "127.0.0",
        "127.0.0.256",
        "10.0.0.1",
        "",
        "127.a.b.c",
    ):
        assert not dji_app.client._is_loopback(host), host


def test_a_malformed_phone_reply_is_a_status_not_an_exception():
    """R11: a reply that is not valid HTTP (a garbage status
    line) returns None (no answer); it never throws."""
    import socketserver
    import threading

    class Garbage(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(4096)
            self.request.sendall(b"NOT-HTTP garbage\r\n\r\n")

    srv = socketserver.TCPServer(("127.0.0.1", 0), Garbage)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    dji = dji_app.client.DjiApp("127.0.0.1", srv.server_address[1], timeout=0.5)
    assert dji.stop() is None
    end = time.monotonic() + 5
    while state_of(dji) != "WAITING" and time.monotonic() < end:
        time.sleep(0.05)
    # orange: the user must fix it; the app lives on
    assert state_of(dji) == "WAITING"
    dji.close()
    srv.shutdown()
    srv.server_close()


def test_every_request_posts_its_path_and_body():
    phone = RecordingPhone()
    d = phone.dji
    mission = [{"type": "spin_by", "degrees": 90.0}]
    calls = [(d.takeoff, (), "/c/takeoff", None), (d.land, (), "/c/land", None),
             (d.stop, (), "/c/stop", None),
             (d.halt, (), "/c/fly", [{"type": "delay", "seconds": 0.0}]),
             (d.fly_mission, (mission,), "/c/fly", mission)]
    for fn, args, path, body in calls:
        assert fn(*args) == 200
        assert phone.seen[-1] == (path, body), fn.__name__
    phone.close()


def test_transmit_off_blocks_motion_but_never_the_stop():
    phone = RecordingPhone()
    phone.dji.set_transmit(False)
    assert not phone.dji.transmitting()
    for fn, args in [(phone.dji.takeoff, ()), (phone.dji.land, ()), (phone.dji.halt, ()),
                     (phone.dji.fly_mission, ([{"type": "wave"}],))]:
        assert fn(*args) == HTTPStatus.CONFLICT, fn.__name__
    assert phone.seen == []                                  # nothing left the laptop
    assert phone.dji.stop() == 200 and phone.paths() == ["/c/stop"]
    phone.dji.set_transmit(True)
    assert phone.dji.takeoff() == 200
    phone.close()


def test_from_env_uses_the_config_target(monkeypatch):
    monkeypatch.setattr(config, "DJI_HOST", "127.0.0.1")
    monkeypatch.setattr(config, "DJI_PORT", 8079)
    monkeypatch.setattr(config, "DJI_REAL", False)
    w = dji_app.client.DjiApp.from_env()
    assert (w.host, w.port) == ("127.0.0.1", 8079)


def test_a_real_host_without_allow_real_dies():
    import subprocess
    import sys as _sys
    here = os.path.dirname(__file__)
    code = (
        f"import sys; sys.path.insert(0, {os.path.join(here, '..')!r}); "
        "from dji_app.client import DjiApp; DjiApp('10.0.0.5')"
    )
    r = subprocess.run(
        [_sys.executable, "-c", code], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 1 and "refusing non-loopback host '10.0.0.5'" in r.stderr


def test_the_phone_app_row_goes_up_again_when_the_app_answers(monkeypatch):
    """WAITING while nothing answers; UP once a phone app answers GET /status/ again."""
    monkeypatch.setattr(config, "WAITING_RETRY_SECONDS", 0.1)
    port = dead_port()
    dji = dji_app.client.DjiApp("127.0.0.1", port, timeout=0.3)
    end = time.monotonic() + 5
    while state_of(dji) != "WAITING" and time.monotonic() < end:
        time.sleep(0.02)
    assert state_of(dji) == "WAITING"
    phone = RecordingPhone(port=port)                 # the user fixed the phone app
    end = time.monotonic() + 5
    while state_of(dji) != UP and time.monotonic() < end:
        time.sleep(0.02)
    assert state_of(dji) == UP
    dji.close()
    phone.close()
