"""The generic process supervisor: the app starts EVERY external process through it
(owner 2026-09-22).

For each process it: launches it, waits until it is ready, reports UP, then blocks
on the process exit on its own thread (no polling while it runs). When the process
dies it reports RECOVERING and starts it again. After config.SUPERVISOR_MAX_RESTARTS
failed restarts:
  - a REQUIRED process (a laptop process: Gemma, ASR, keys) reports FAILED and
    die()s with the reason;
  - a process that is NOT required (it depends on the phone app: the mock,
    gstreamer) reports WAITING (orange: the user must fix it) and is retried every
    config.WAITING_RETRY_SECONDS until it runs.
A process that stays up SUPERVISOR_STABLE_SECONDS earns its restart count back, so
one crash an hour never adds up to a shutdown.

The only wait that polls is the readiness probe at start (a bounded check, e.g. an
HTTP /health). die() anywhere in the app stops every child first (fatal.on_die), so
nothing is left orphaned.
"""
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import config
from system.fatal import on_die
from system.status import DOWN, RECOVERING, UP, WAITING, Status, fail
from util.process import wait_exit

READY_PROBE_SECONDS = 0.5     # how often a readiness probe runs during start-up
STOP_GRACE_SECONDS = 10.0     # terminate, then kill after this long


@dataclass
class ProcessSpec:
    """What a module needs started. The module describes it; the app starts it.
    @ready: a no-argument callable, True once the process can serve
        (None = ready as soon as it is launched).
    @log_path: where stdout + stderr go (None = /tmp/harden2-<name>.log).
    @required: False = past the restart budget, WAIT for the user instead of dying."""
    name: str
    argv: list
    env: Optional[dict] = None
    ready: Optional[Callable] = None
    ready_timeout_s: float = 120.0
    log_path: Optional[str] = None
    required: bool = True


class Process:
    """The handle Supervisor.start() returns. It owns the process's status row (the
    board reads it through status()). A module that must restart its process (the video
    stall guard) holds this, never the supervisor itself."""

    def __init__(self, supervisor, name, status):
        self._supervisor = supervisor
        self.name = name
        self._status = status
        return

    def status(self):
        """[(name, state, detail)]: this process's one row."""
        return [self._status.row()]

    def restart(self, reason):
        """A deliberate restart: not counted against the crash budget. -> False when it
        is not running."""
        return self._supervisor.restart(self.name, reason)

    def wait_up(self, timeout_s):
        """Block until the process is UP (ready) the first time. -> False on timeout.
        A bench uses this; the app watches the status board instead."""
        return self._supervisor.up_event(self.name).wait(timeout_s)


class Supervisor:
    """Starts, watches and restarts processes. Each process's state is set on its own
    Process handle's status row; the supervisor writes no other status."""

    def __init__(
        self,
        max_restarts=config.SUPERVISOR_MAX_RESTARTS,
        stable_s=config.SUPERVISOR_STABLE_SECONDS,
    ):
        self.mk_maxRestarts = max_restarts
        self.mk_stableS = stable_s
        self._lock = threading.Lock()
        self._procs = {}                    # name -> the live Popen
        self._statuses = {}                 # name -> the process's status row
        self._planned = {}                  # name -> reason, for a restart the app asked
        self._up = {}                       # name -> Event, set once the process is UP
        self.mb_stopping = False
        self._stopped = threading.Event()  # wakes a WAITING watcher at once on shutdown

        on_die(self.stop_all)
        return

    def start(self, spec):
        """Launch the process `spec` describes and supervise it on its own thread.
        Returns a Process handle at once (its row is STARTING)."""
        status = Status(spec.name)
        with self._lock:
            self._statuses[spec.name] = status

        threading.Thread(
            target=self._watch,
            args=(spec, status),
            name=f"supervise-{spec.name}",
            daemon=True,
        ).start()
        return Process(self, spec.name, status)

    def up_event(self, name):
        """The Event that is set once `name` is UP the first time."""
        with self._lock:
            return self._up.setdefault(name, threading.Event())

    def restart(self, name, reason):
        """A deliberate restart (e.g. the video stalled): terminate it; its watcher
        starts it again. It does NOT spend the crash budget. Returns False when no such
        process is running."""
        with self._lock:
            proc = self._procs.get(name)
            if proc is None or proc.poll() is not None:
                return False
            self._planned[name] = reason

        proc.terminate()
        return True

    def stop_all(self):
        """Stop every child: terminate them all, then kill any that has not exited
        after the grace period. Reports each as DOWN."""
        with self._lock:
            self.mb_stopping = True
            procs = list(self._procs.items())
            statuses = dict(self._statuses)
        self._stopped.set()

        for _name, proc in procs:
            if proc.poll() is None:
                proc.terminate()

        for name, proc in procs:
            if not wait_exit(proc, STOP_GRACE_SECONDS):
                proc.kill()
                proc.wait()
            statuses[name].set(DOWN)
        return

    # --- one watcher thread per process ---------------------------------------
    def _launch(self, name, argv, env, log_path):
        """Start the child and register it in ONE critical section with the stopping
        check, so stop_all can never miss a child launched during shutdown (review
        R16). None when stopping."""
        with self._lock:
            if self.mb_stopping:
                return None

            log = open(log_path, "ab", buffering=0)
            proc = subprocess.Popen(
                argv,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
            )
            # the child holds its own copy of the file descriptor
            log.close()
            self._procs[name] = proc
        return proc

    def _wait_ready(self, proc, ready, timeout_s):
        """(True, "") once ready; (False, reason) if the process exits or never gets
        ready."""
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

    def _run_once(self, proc, spec, status):
        """Wait until the process is ready, then until it exits. -> (ran, reason,
        stable): whether it got ready, why it ended, and whether it stayed up long
        enough to earn its restarts back."""
        t_up = 0.0
        code = 0

        ok, reason = self._wait_ready(proc, spec.ready, spec.ready_timeout_s)
        if not ok:
            # never ready: do not leave it half-started
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            return False, reason, False

        status.set(UP)
        self.up_event(spec.name).set()
        t_up = time.monotonic()
        code = proc.wait()                  # blocks until the process exits; no polling
        stable = time.monotonic() - t_up >= self.mk_stableS
        return True, f"exited with code {code}", stable

    def _watch(self, spec, status):
        name = spec.name
        log_path = spec.log_path or f"/tmp/harden2-{name}.log"
        restarts = 0
        reason = ""
        waiting = False
        proc = None
        ran = False
        stable = False
        planned = None

        while True:
            # the row before each launch: first start, a restart, or still waiting
            if restarts > 0 and not waiting:
                status.set(
                    RECOVERING,
                    f"{reason}; restart {restarts}/{self.mk_maxRestarts}",
                )

            proc = self._launch(name, list(spec.argv), spec.env, log_path)
            if proc is None:                          # the app is shutting down
                return

            ran, reason, stable = self._run_once(proc, spec, status)
            if ran:
                waiting = False
            if stable:
                restarts = 0
            if self.mb_stopping:
                return

            # a deliberate restart: not a crash, not counted
            with self._lock:
                planned = self._planned.pop(name, None)
            if planned is not None:
                status.set(RECOVERING, f"{planned}; restarting")
                continue

            restarts += 1
            if restarts <= self.mk_maxRestarts:
                continue

            # past the budget: a laptop part dies, a phone-side part waits for the user
            if spec.required:
                fail(
                    status,
                    reason,
                    f"{name} failed: {reason}. {self.mk_maxRestarts} restarts did not "
                    f"recover it. Log: {log_path}",
                )
            waiting = True
            status.set(
                WAITING,
                f"{reason}; the user must fix it. Retry every "
                f"{config.WAITING_RETRY_SECONDS:.0f}s",
            )
            if self._stopped.wait(config.WAITING_RETRY_SECONDS):
                return                                # shutting down
