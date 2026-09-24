"""Tests for system/: the status board and the generic process supervisor."""
import os
import subprocess
import sys
import tempfile
import textwrap
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from system import status
from system import supervisor as supervisor_module
from system.status import (
    DOWN,
    FAILED,
    RECOVERING,
    STARTING,
    UP,
    WAITING,
    Status,
    StatusBoard,
)
from system.supervisor import ProcessSpec, Supervisor

from support import wait_for

HARDEN2 = os.path.join(os.path.dirname(__file__), "..")


# ==================== status ====================
class _Source:
    """A part with status rows, as the board sees it."""

    def __init__(self, *statuses):
        self.statuses = statuses

    def status(self):
        return [s.row() for s in self.statuses]


def test_the_board_asks_each_source_in_source_order():
    gemma = Status("gemma")
    sam3 = Status("sam3", UP)
    board = StatusBoard([_Source(gemma), _Source(sam3), _Source()])
    gemma.set(UP)
    assert board.snapshot() == [("gemma", UP, ""), ("sam3", UP, "")]


def test_a_status_starts_starting_and_keeps_its_detail():
    asr = Status("asr")
    assert asr.state() == STARTING
    asr.set(RECOVERING, "exit code 139, restart 1/3")
    assert asr.row() == ("asr", RECOVERING, "exit code 139, restart 1/3")


def test_sets_from_many_threads_leave_one_consistent_row():
    row = Status("s")
    ths = [threading.Thread(target=row.set, args=(UP, f"d{i}")) for i in range(50)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert row.state() == UP and row.row()[2].startswith("d")


def test_there_is_no_global_board_and_states_are_distinct():
    """Each part owns its row; the board only reads them (owner ruling 2026-09-24)."""
    assert not hasattr(status, "BOARD")
    assert len({STARTING, UP, RECOVERING, FAILED, DOWN}) == 5


def test_die_runs_cleanups_before_exit():
    code = textwrap.dedent(f'''
        import sys; sys.path.insert(0, {HARDEN2!r})
        from system.fatal import die, on_die
        on_die(lambda: print("CLEANUP RAN", flush=True))
        die("boom")
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 1 and "CLEANUP RAN" in r.stdout and "FATAL: boom" in r.stderr


# ==================== supervisor ====================


def _wait_for(pred, timeout=10.0):
    return wait_for(pred, timeout)


def _py(code):
    return [sys.executable, "-c", code]


def _state(process):
    """The state on a Process handle's own row."""
    return process.status()[0][1]


def _recording(monkeypatch):
    """Record every (state, detail) the supervisor sets on any process row."""
    seen = []

    class RecordingStatus(Status):
        def set(self, state, detail=""):
            seen.append((state, detail))
            return super().set(state, detail)

    monkeypatch.setattr(supervisor_module, "Status", RecordingStatus)
    return seen


def test_a_healthy_process_goes_up_and_stops_down():
    sup = Supervisor(max_restarts=3, stable_s=60)
    p = sup.start(ProcessSpec("sleeper", _py("import time; time.sleep(60)")))
    assert _wait_for(lambda: _state(p) == UP)
    sup.stop_all()
    assert _state(p) == DOWN


def test_ready_probe_holds_starting_until_ready():
    flag = os.path.join(tempfile.mkdtemp(), "ready")
    sup = Supervisor(max_restarts=3, stable_s=60)
    p = sup.start(ProcessSpec(
        "slow",
        _py(
            f"import time; time.sleep(0.6); "
            f"open({flag!r}, 'w').close(); time.sleep(60)"
        ),
        ready=lambda: os.path.exists(flag)
    ))
    assert _wait_for(lambda: _state(p) == STARTING, 2)
    assert _wait_for(lambda: _state(p) == UP)
    sup.stop_all()


def test_a_dead_process_is_restarted_and_recovers(monkeypatch):
    seen = _recording(monkeypatch)
    marker = os.path.join(tempfile.mkdtemp(), "crashed-once")
    code = (f"import os, sys, time\n"
            f"if not os.path.exists({marker!r}):\n"
            f"    open({marker!r}, 'w').close(); sys.exit(3)\n"
            f"time.sleep(60)")
    sup = Supervisor(max_restarts=3, stable_s=60)
    p = sup.start(ProcessSpec("flaky", _py(code)))
    assert _wait_for(
        lambda: _state(p) == UP and any(st == RECOVERING for st, _ in seen)
    )
    assert (RECOVERING, "exited with code 3; restart 1/3") in seen
    sup.stop_all()


def test_never_ready_counts_as_a_failure(monkeypatch):
    seen = _recording(monkeypatch)
    sup = Supervisor(max_restarts=3, stable_s=60)
    sup.start(ProcessSpec(
        "mute",
        _py("import time; time.sleep(60)"),
        ready=lambda: False,
        ready_timeout_s=0.3
    ))
    assert _wait_for(
        lambda: any(st == RECOVERING and "not ready after" in d for st, d in seen)
    )
    sup.stop_all()


def test_gives_up_after_max_restarts_and_dies_with_the_reason():
    code = textwrap.dedent(f'''
        import sys, time; sys.path.insert(0, {HARDEN2!r})
        from system.supervisor import ProcessSpec, Supervisor
        sup = Supervisor(max_restarts=2, stable_s=60)
        argv = [sys.executable, "-c", "import sys; sys.exit(7)"]
        sup.start(ProcessSpec("doomed", argv))
        time.sleep(20)
    ''')
    r = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert r.returncode == 1
    assert "[status] doomed: FAILED -- exited with code 7" in r.stdout
    assert (
        "FATAL: doomed failed: exited with code 7. 2 restarts did not recover it."
        in r.stderr
    )


def test_a_process_that_is_not_required_waits_instead_of_dying(monkeypatch):
    """Past the budget, a process that depends on the phone app goes WAITING (orange) and
    is retried; the app does NOT die. When it runs again, it goes UP."""
    monkeypatch.setattr(config, "WAITING_RETRY_SECONDS", 0.2)
    marker = os.path.join(tempfile.mkdtemp(), "fixed")
    code = (f"import os, sys, time\n"
            f"if not os.path.exists({marker!r}):\n    sys.exit(5)\n"
            f"time.sleep(60)")
    sup = Supervisor(max_restarts=1, stable_s=60)
    p = sup.start(ProcessSpec("phone-side", _py(code), required=False))
    assert _wait_for(lambda: _state(p) == WAITING)
    open(marker, "w").close()                 # the user fixed it
    assert _wait_for(lambda: _state(p) == UP)
    sup.stop_all()
    assert _state(p) == DOWN


def test_die_stops_the_children_first():
    code = textwrap.dedent(f'''
        import sys, time; sys.path.insert(0, {HARDEN2!r})
        from system.supervisor import ProcessSpec, Supervisor
        from system.fatal import die
        sup = Supervisor(max_restarts=3, stable_s=60)
        argv = [sys.executable, "-c", "import time; time.sleep(60)"]
        child = sup.start(ProcessSpec("child", argv))
        while child.status()[0][1] != "UP": time.sleep(0.05)
        pid = sup._procs["child"].pid
        print("PID", pid, flush=True)
        die("test")
    ''')
    r = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    pid = int(r.stdout.split("PID ")[1].split()[0])
    assert r.returncode == 1 and "[status] child: DOWN" in r.stdout
    assert (
        not os.path.exists(f"/proc/{pid}")
        or open(f"/proc/{pid}/stat").read().split()[2] == "Z"
    )


def test_a_deliberate_restart_does_not_spend_the_crash_budget(monkeypatch):
    seen = _recording(monkeypatch)
    sup = Supervisor(max_restarts=1, stable_s=60)
    p = sup.start(ProcessSpec("cam", _py("import time; time.sleep(60)")))
    assert _wait_for(lambda: _state(p) == UP)
    # three planned restarts with a budget of one
    for i in range(3):
        assert sup.restart("cam", f"video stalled {i}s")
        assert _wait_for(lambda: (RECOVERING, f"video stalled {i}s; restarting") in seen)
        assert _wait_for(lambda: _state(p) == UP)
    # none of them counted as a crash
    assert not any("restart 1/1" in d for _, d in seen)
    sup.stop_all()


def test_restart_of_an_unknown_process_is_false():
    assert Supervisor().restart("nothing", "x") is False


def test_an_uncaught_thread_exception_dies_loudly_and_cleans_up():
    code = textwrap.dedent(f'''
        import sys, threading, time; sys.path.insert(0, {HARDEN2!r})
        from system.fatal import install_crash_hooks, on_die
        install_crash_hooks()
        on_die(lambda: print("CLEANUP RAN", flush=True))
        def boom():
            raise ValueError("a bug in a worker")
        threading.Thread(target=boom, name="sam3-worker").start()
        time.sleep(5)
        print("STILL RUNNING", flush=True)
    ''')
    r = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert (
        r.returncode == 1
        and "CLEANUP RAN" in r.stdout
        and "STILL RUNNING" not in r.stdout
    )
    assert "uncaught ValueError in thread sam3-worker: a bug in a worker" in r.stderr
    assert "Traceback" in r.stderr


def test_no_launch_after_stop_all():
    """R16: once stopping, _launch starts nothing, so stop_all can never miss a child."""
    sup = Supervisor()
    sup.stop_all()
    assert sup._launch(
        "late", _py("import time; time.sleep(60)"), None, os.devnull
    ) is None


def test_die_reaches_exit_even_when_a_cleanup_fails_and_runs_once():
    """R17: a failing cleanup is reported and the rest still run;
    two threads dying exit once."""
    code = textwrap.dedent(f'''
        import sys, threading, time; sys.path.insert(0, {HARDEN2!r})
        from system.fatal import die, on_die
        def bad():
            raise OSError("wait failed")
        on_die(bad)
        on_die(lambda: print("SECOND CLEANUP RAN", flush=True))
        for i in range(2):
            threading.Thread(target=die, args=(f"boom {{i}}",)).start()
        time.sleep(5)
        print("STILL RUNNING", flush=True)
    ''')
    r = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert r.returncode == 1 and "STILL RUNNING" not in r.stdout
    assert r.stdout.count("SECOND CLEANUP RAN") == 1
    assert "a cleanup failed during die(): OSError('wait failed')" in r.stderr
