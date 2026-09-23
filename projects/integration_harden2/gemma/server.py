"""Keep Gemma alive: its command line, its readiness check, and its start through the supervisor.

The app: start_services(supervisor, log_dir) launches Gemma from config (model, vision projector, port, thinking off)
under the generic supervisor, which restarts it if it dies and die()s after the restart budget.
The benches: LlamaServer(MODELS["gemma4"], extra=GEMMA4_EXTRA) as a context manager on the bench PORT,
so a bench server never collides with the app's. One model resident at a time.
Moved from recognizer/llama.py on 2026-09-22.
"""
import os
import subprocess
import time
import urllib.error
import urllib.request

import config
from fatal import die
from system.supervisor import native_env

BIN = config.NATIVE_BIN_DIR
LOG_PATH = "/tmp/llama-server-bench.log"      # bench servers
PORT = 18091                                  # the BENCH port; the app uses config.LLAMA_SERVER_PORT

MODELS = {"gemma4": config.GEMMA_MODEL_PATH}


def thinking_flags(enabled):
    """Gemma thinking on or off, through the jinja template. OFF needs both flags: --reasoning-budget 0
    alone still narrated on 57/413 translations; enable_thinking=false stopped 12/12 (2026-09-08,
    llama.cpp discussion 21338)."""
    if enabled:
        return ("--jinja", "--chat-template-kwargs", '{"enable_thinking":true}')
    return ("--jinja", "--chat-template-kwargs", '{"enable_thinking":false}', "--reasoning-budget", "0")


GEMMA4_EXTRA = thinking_flags(os.environ.get("GEMMA4_THINK") == "1")   # bench A/B arm: GEMMA4_THINK=1 = on


def port_up(port):
    """True when a llama-server on this port answers /health with 200 (loaded and ready)."""
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
        return True
    except (urllib.error.URLError, OSError):   # urllib reports "not up" or "still loading" only by a throw
        return False


class LlamaServer:
    """One llama-server process. The benches use it as a context manager: alive only inside the
    with-block (the app runs Gemma through the supervisor instead)."""

    def __init__(self, model, port=PORT, extra=()):
        self.port = port
        self.proc = None
        self._log = None
        self.args = [os.path.join(BIN, "llama-server"), "-m", model,
                     "-dev", "Vulkan0", "-ngl", "99", "-c", "4096", "--temp", "0.0",
                     "--host", "127.0.0.1", "--port", str(port), "--threads", "1", *extra]

    def start(self):
        self._log = open(LOG_PATH, "ab", buffering=0)
        self.proc = subprocess.Popen(self.args, env=native_env(), stdout=self._log, stderr=self._log)
        return

    def wait_ready(self, timeout_s=120):
        """Block until /health answers. die() with the log tail if the process exits or never gets ready."""
        for _ in range(timeout_s):
            if port_up(self.port):
                return
            if self.proc.poll() is not None:
                die(f"llama-server died on startup (rc={self.proc.returncode}):\n{self._tail()}")
            time.sleep(1)
        die(f"llama-server not healthy after {timeout_s}s (port {self.port}):\n{self._tail()}")

    def _tail(self):
        with open(LOG_PATH, "rb") as f:
            return f.read()[-500:].decode(errors="replace")

    def stop(self):
        """Terminate the server and wait until its port is free for the next model."""
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:       # subprocess reports a timeout only by a throw
                self.proc.kill()
                self.proc.wait()
            for _ in range(20):
                if not port_up(self.port):
                    break
                time.sleep(0.5)
            time.sleep(1)
        if self._log is not None:
            self._log.close()
            self._log = None
        return

    def __enter__(self):
        self.start()
        self.wait_ready()
        return self

    def __exit__(self, *exc):
        self.stop()
        return False


def app_argv():
    """The app's Gemma command line, built from config. Gemma gotchas (2026-09-08): NO
    --image-min-tokens (breaks its CLIP load), NO q4_0 KV + flash-attn (empty output)."""
    return [os.path.join(BIN, "llama-server"), "-m", config.GEMMA_MODEL_PATH,
            "--mmproj", config.GEMMA_MMPROJ_PATH,
            "-dev", "Vulkan0", "-ngl", "99", "-c", "4096", "-np", "1", "--temp", "0.0",
            "--host", "127.0.0.1", "--port", str(config.LLAMA_SERVER_PORT), "--threads", "1",
            *thinking_flags(config.GEMMA_THINKING_ENABLED)]


def ready():
    return port_up(config.LLAMA_SERVER_PORT)


def start_services(supervisor, log_dir):
    """Start the app's Gemma under the supervisor: STARTING -> UP once /health answers. Model load is
    ~15-60 s, so it gets a long start-up window."""
    supervisor.start("gemma", app_argv(), env=native_env(), ready=ready, ready_timeout_s=240.0,
                     log_path=os.path.join(log_dir, "proc-gemma.log"))
    return
