"""The generic process supervisor: the app starts EVERY external process through it (owner 2026-09-22).

For each process it: launches it, waits until it is ready, reports UP, then blocks on the process exit
on its own thread (no polling while it runs). When the process dies it reports RECOVERING and starts
it again. After config.SUPERVISOR_MAX_RESTARTS failed restarts it reports FAILED and die()s with the
reason. A process that stays up SUPERVISOR_STABLE_SECONDS earns its restart count back, so one crash
an hour never adds up to a shutdown.

The only wait that polls is the readiness probe at start (a bounded check, e.g. an HTTP /health).
die() anywhere in the app stops every child first (fatal.on_die), so nothing is left orphaned.
"""
import os
import socket
import subprocess
import threading
import time

import config
from fatal import on_die
from system.status import BOARD, DOWN, RECOVERING, STARTING, UP, fail

def port_open(host, port, timeout=0.5):
    """True when something accepts a TCP connection on host:port. The ONE port probe in the app."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:                                 # socket reports "nothing listening" only by a throw
        return False


def native_env(**extra):
    """The environment for a C++ binary: ours, plus the native library folder, plus `extra`."""
    env = dict(os.environ, LD_LIBRARY_PATH=config.NATIVE_BIN_DIR + ":" + os.environ.get("LD_LIBRARY_PATH", ""))
    env.update(extra)
    return env


READY_PROBE_SECONDS = 0.5     # how often a readiness probe runs during start-up
STOP_GRACE_SECONDS = 10.0     # terminate, then kill after this long


class Supervisor:
    def __init__(self, board=BOARD, max_restarts=config.SUPERVISOR_MAX_RESTARTS,
                 stable_s=config.SUPERVISOR_STABLE_SECONDS):
        self.board = board
        self.mk_maxRestarts = max_restarts
        self.mk_stableS = stable_s
        self._lock = threading.Lock()
        self._procs = {}                  # name -> the live Popen
        self._planned = {}                # name -> reason, for a restart the app asked for
        self.mb_stopping = False
        on_die(self.stop_all)

    def start(self, name, argv, env=None, ready=None, ready_timeout_s=120.0, log_path=None):
        """Launch `argv` as `name` and supervise it on its own thread. Returns at once.
        @ready: a no-argument callable, True once the process can serve (None = ready when launched).
        @log_path: where stdout + stderr go (None = /tmp/harden2-<name>.log)."""
        log_path = log_path or f"/tmp/harden2-{name}.log"
        spec = (name, list(argv), env, ready, ready_timeout_s, log_path)
        threading.Thread(target=self._watch, args=spec, name=f"supervise-{name}", daemon=True).start()
        return

    def restart(self, name, reason):
        """A deliberate restart (e.g. the video stalled): terminate it; its watcher starts it again.
        It does NOT spend the crash budget. Returns False when no such process is running."""
        with self._lock:
            proc = self._procs.get(name)
            if proc is None or proc.poll() is not None:
                return False
            self._planned[name] = reason
        proc.terminate()
        return True

    def stop_all(self):
        """Stop every child: terminate, then kill after the grace period. Reports each as DOWN."""
        with self._lock:
            self.mb_stopping = True
            procs = list(self._procs.items())
        for _name, proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for name, proc in procs:
            try:
                proc.wait(timeout=STOP_GRACE_SECONDS)
            except subprocess.TimeoutExpired:      # subprocess reports a timeout only by a throw
                proc.kill()
                proc.wait()
            self.board.report(name, DOWN)
        return

    # --- one watcher thread per process -------------------------------------------------
    def _launch(self, name, argv, env, log_path):
        """Start the child and register it in ONE critical section with the stopping check, so stop_all
        can never miss a child launched during shutdown (review R16). None when stopping."""
        with self._lock:
            if self.mb_stopping:
                return None
            log = open(log_path, "ab", buffering=0)
            proc = subprocess.Popen(argv, env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            log.close()                   # the child holds its own copy of the file descriptor
            self._procs[name] = proc
        return proc

    def _wait_ready(self, proc, ready, timeout_s):
        """(True, "") once ready; (False, reason) if the process exits or never gets ready."""
        if ready is None:
            return True, ""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if ready():
                return True, ""
            if proc.poll() is not None:
                return False, f"exited during start-up (code {proc.returncode})"
            time.sleep(READY_PROBE_SECONDS)
        return False, f"not ready after {timeout_s:.0f}s"

    def _watch(self, name, argv, env, ready, ready_timeout_s, log_path):
        restarts = 0
        reason = ""
        while True:
            if restarts == 0 and not reason:
                self.board.report(name, STARTING)
            elif restarts > 0:
                self.board.report(name, RECOVERING, f"{reason}; restart {restarts}/{self.mk_maxRestarts}")
            proc = self._launch(name, argv, env, log_path)
            if proc is None:                          # the app is shutting down
                return
            ok, reason = self._wait_ready(proc, ready, ready_timeout_s)
            if ok:
                self.board.report(name, UP)
                t_up = time.monotonic()
                code = proc.wait()                    # blocks until the process exits; no polling
                if time.monotonic() - t_up >= self.mk_stableS:
                    restarts = 0
                reason = f"exited with code {code}"
            elif proc.poll() is None:
                proc.kill()                           # never ready: do not leave it half-started
                proc.wait()
            if self.mb_stopping:
                return
            with self._lock:
                planned = self._planned.pop(name, None)
            if planned is not None:
                self.board.report(name, RECOVERING, f"{planned}; restarting")
                continue                              # a deliberate restart: not a crash, not counted
            restarts += 1
            if restarts > self.mk_maxRestarts:
                fail(name, reason, f"{name} failed: {reason}. {self.mk_maxRestarts} restarts did not recover it. "
                     f"Log: {log_path}", board=self.board)
