"""Tests for system/: the status board and the generic process supervisor."""
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from system import status
from system.status import DOWN, FAILED, RECOVERING, STARTING, UP, StatusBoard
from system.supervisor import Supervisor

HARDEN2 = os.path.join(os.path.dirname(__file__), "..")


# ==================== status ====================
def test_report_then_snapshot_keeps_first_report_order():
    b = StatusBoard()
    b.report("gemma", STARTING)
    b.report("sam3", UP)
    b.report("gemma", UP)
    assert b.snapshot() == [("gemma", UP, ""), ("sam3", UP, "")]


def test_state_of_an_unknown_system_is_none():
    assert StatusBoard().state("nothing") is None


def test_detail_is_kept_with_a_red_state():
    b = StatusBoard()
    b.report("asr", RECOVERING, "exit code 139, restart 1/3")
    assert b.snapshot() == [("asr", RECOVERING, "exit code 139, restart 1/3")]
    assert b.state("asr") == RECOVERING


def test_reports_from_many_threads_are_all_kept():
    b = StatusBoard()
    ths = [threading.Thread(target=b.report, args=(f"s{i}", UP)) for i in range(50)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert len(b.snapshot()) == 50


def test_app_board_exists_and_states_are_distinct():
    assert isinstance(status.BOARD, StatusBoard)
    assert len({STARTING, UP, RECOVERING, FAILED, DOWN}) == 5


def test_die_runs_cleanups_before_exit():
    code = textwrap.dedent(f'''
        import sys; sys.path.insert(0, {HARDEN2!r})
        from fatal import die, on_die
        on_die(lambda: print("CLEANUP RAN", flush=True))
        die("boom")
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 1 and "CLEANUP RAN" in r.stdout and "FATAL: boom" in r.stderr


# ==================== supervisor ====================


def _wait_for(pred, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def _py(code):
    return [sys.executable, "-c", code]


def test_a_healthy_process_goes_up_and_stops_down():
    b = StatusBoard()
    sup = Supervisor(board=b, max_restarts=3, stable_s=60)
    sup.start("sleeper", _py("import time; time.sleep(60)"))
    assert _wait_for(lambda: b.state("sleeper") == UP)
    sup.stop_all()
    assert b.state("sleeper") == DOWN


def test_ready_probe_holds_starting_until_ready():
    b = StatusBoard()
    flag = os.path.join(tempfile.mkdtemp(), "ready")
    sup = Supervisor(board=b, max_restarts=3, stable_s=60)
    sup.start("slow", _py(f"import time; time.sleep(0.6); open({flag!r}, 'w').close(); time.sleep(60)"),
              ready=lambda: os.path.exists(flag))
    assert _wait_for(lambda: b.state("slow") == STARTING, 2)
    assert _wait_for(lambda: b.state("slow") == UP)
    sup.stop_all()


def test_a_dead_process_is_restarted_and_recovers():
    b = StatusBoard()
    marker = os.path.join(tempfile.mkdtemp(), "crashed-once")
    seen = []
    b.report = (lambda orig: (lambda s, st, d="": (seen.append((st, d)), orig(s, st, d))))(b.report)
    code = (f"import os, sys, time\n"
            f"if not os.path.exists({marker!r}):\n    open({marker!r}, 'w').close(); sys.exit(3)\n"
            f"time.sleep(60)")
    sup = Supervisor(board=b, max_restarts=3, stable_s=60)
    sup.start("flaky", _py(code))
    assert _wait_for(lambda: b.state("flaky") == UP and any(st == RECOVERING for st, _ in seen))
    assert (RECOVERING, "exited with code 3; restart 1/3") in seen
    sup.stop_all()


def test_never_ready_counts_as_a_failure():
    b = StatusBoard()
    seen = []
    b.report = (lambda orig: (lambda s, st, d="": (seen.append((st, d)), orig(s, st, d))))(b.report)
    sup = Supervisor(board=b, max_restarts=3, stable_s=60)
    sup.start("mute", _py("import time; time.sleep(60)"), ready=lambda: False, ready_timeout_s=0.3)
    assert _wait_for(lambda: any(st == RECOVERING and "not ready after" in d for st, d in seen))
    sup.stop_all()


def test_gives_up_after_max_restarts_and_dies_with_the_reason():
    code = textwrap.dedent(f'''
        import sys, time; sys.path.insert(0, {HARDEN2!r})
        from system.supervisor import Supervisor
        sup = Supervisor(max_restarts=2, stable_s=60)
        sup.start("doomed", [sys.executable, "-c", "import sys; sys.exit(7)"])
        time.sleep(20)
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 1
    assert "[status] doomed: FAILED -- exited with code 7" in r.stdout
    assert "FATAL: doomed failed: exited with code 7. 2 restarts did not recover it." in r.stderr


def test_die_stops_the_children_first():
    code = textwrap.dedent(f'''
        import sys, time; sys.path.insert(0, {HARDEN2!r})
        from system.supervisor import Supervisor
        from system.status import BOARD
        from fatal import die
        sup = Supervisor(max_restarts=3, stable_s=60)
        sup.start("child", [sys.executable, "-c", "import time; time.sleep(60)"])
        while BOARD.state("child") != "UP": time.sleep(0.05)
        pid = sup._procs["child"].pid
        print("PID", pid, flush=True)
        die("test")
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    pid = int(r.stdout.split("PID ")[1].split()[0])
    assert r.returncode == 1 and "[status] child: DOWN" in r.stdout
    assert not os.path.exists(f"/proc/{pid}") or open(f"/proc/{pid}/stat").read().split()[2] == "Z"


def test_a_deliberate_restart_does_not_spend_the_crash_budget():
    b = StatusBoard()
    seen = []
    b.report = (lambda orig: (lambda s, st, d="": (seen.append((st, d)), orig(s, st, d))))(b.report)
    sup = Supervisor(board=b, max_restarts=1, stable_s=60)
    sup.start("cam", _py("import time; time.sleep(60)"))
    assert _wait_for(lambda: b.state("cam") == UP)
    for i in range(3):                                   # three planned restarts with a budget of one
        assert sup.restart("cam", f"video stalled {i}s")
        assert _wait_for(lambda: (RECOVERING, f"video stalled {i}s; restarting") in seen)
        assert _wait_for(lambda: b.state("cam") == UP)
    assert not any("restart 1/1" in d for _, d in seen)  # none of them counted as a crash
    sup.stop_all()


def test_restart_of_an_unknown_process_is_false():
    assert Supervisor(board=StatusBoard()).restart("nothing", "x") is False


def test_native_env_adds_the_native_library_folder():
    import config
    from system.supervisor import native_env
    env = native_env(PULSE_SERVER="unix:/x")
    assert env["LD_LIBRARY_PATH"].split(":")[0] == config.NATIVE_BIN_DIR and env["PULSE_SERVER"] == "unix:/x"


def test_an_uncaught_thread_exception_dies_loudly_and_cleans_up():
    code = textwrap.dedent(f'''
        import sys, threading, time; sys.path.insert(0, {HARDEN2!r})
        from fatal import install_crash_hooks, on_die
        install_crash_hooks()
        on_die(lambda: print("CLEANUP RAN", flush=True))
        def boom():
            raise ValueError("a bug in a worker")
        threading.Thread(target=boom, name="sam3-worker").start()
        time.sleep(5)
        print("STILL RUNNING", flush=True)
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 1 and "CLEANUP RAN" in r.stdout and "STILL RUNNING" not in r.stdout
    assert "uncaught ValueError in thread sam3-worker: a bug in a worker" in r.stderr
    assert "Traceback" in r.stderr



def test_no_launch_after_stop_all():
    """R16: once stopping, _launch starts nothing, so stop_all can never miss a child."""
    sup = Supervisor(board=StatusBoard())
    sup.stop_all()
    assert sup._launch("late", _py("import time; time.sleep(60)"), None, os.devnull) is None


def test_die_reaches_exit_even_when_a_cleanup_fails_and_runs_once():
    """R17: a failing cleanup is reported and the rest still run; two threads dying exit once."""
    code = textwrap.dedent(f'''
        import sys, threading, time; sys.path.insert(0, {HARDEN2!r})
        from fatal import die, on_die
        def bad():
            raise OSError("wait failed")
        on_die(bad)
        on_die(lambda: print("SECOND CLEANUP RAN", flush=True))
        for i in range(2):
            threading.Thread(target=die, args=(f"boom {{i}}",)).start()
        time.sleep(5)
        print("STILL RUNNING", flush=True)
    ''')
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert r.returncode == 1 and "STILL RUNNING" not in r.stdout
    assert r.stdout.count("SECOND CLEANUP RAN") == 1
    assert "a cleanup failed during die(): OSError('wait failed')" in r.stderr
