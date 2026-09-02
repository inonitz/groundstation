"""Model serving for the bench. This file, and only this file, starts llama-server.

Two models exist in the system: DictaLM (the Recognizer's translator) and Qwen3-VL (the
planner). Both run through the LlamaServer context manager below: one model resident at a
time, loaded on enter, verified dead on exit. Server stderr goes to LOG_PATH, and a startup
failure raises with the log tail, never silently.
"""
import json
import os
import subprocess
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BIN = os.path.join(ROOT, "build", "release", "shared", "dji", "bin")
LOG_PATH = "/tmp/llama-server-bench.log"
PORT = 18091

MODELS = {
    "dicta": "/root/models/asr/dictalm-3-1.7b/dictalm-3.0-1.7b-instruct-q4_k_m.gguf",
    "qwen3vl": "/root/models/vlm/Qwen3-VL-4B-Instruct/Qwen3-VL-4B-Instruct-Q4_K_M.gguf",
}
QWEN3VL_EXTRA = ("--mmproj", "/root/models/vlm/Qwen3-VL-4B-Instruct/mmproj-BF16.gguf",
                 "--flash-attn", "on", "--cache-type-k", "q4_0", "--cache-type-v", "q4_0")


def port_up(port):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
        return True
    except Exception:
        return False


class LlamaServer:
    """One llama-server process, GPU-resident, alive only inside the with-block."""

    def __init__(self, model, port=PORT, extra=()):
        self.port = port
        self.proc = None
        self.args = [os.path.join(BIN, "llama-server"), "-m", model,
                     "-dev", "Vulkan0", "-ngl", "99", "-c", "4096", "--temp", "0.0",
                     "--host", "127.0.0.1", "--port", str(port), "--threads", "1", *extra]

    def __enter__(self):
        env = dict(os.environ, LD_LIBRARY_PATH=BIN + ":" + os.environ.get("LD_LIBRARY_PATH", ""))
        log = open(LOG_PATH, "ab", buffering=0)
        self.proc = subprocess.Popen(self.args, env=env, stdout=log, stderr=log)
        for _ in range(120):
            if port_up(self.port):
                return self
            if self.proc.poll() is not None:
                tail = open(LOG_PATH, "rb").read()[-500:].decode(errors="replace")
                raise RuntimeError(f"llama-server died on startup (rc={self.proc.returncode}):\n{tail}")
            time.sleep(1)
        raise RuntimeError(f"llama-server not healthy after 120s (port {self.port})")

    def __exit__(self, *exc):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except Exception:
            self.proc.kill()
            self.proc.wait()
        for _ in range(20):                     # the port must actually be free for the next model
            if not port_up(self.port):
                break
            time.sleep(0.5)
        time.sleep(1)


def chat(port, system, user, max_tokens=300, grammar=None, shots=(), retries=90):
    """One chat completion. Retries on 503 while the model is still loading."""
    msgs = [{"role": "system", "content": system}]
    for u, a in shots:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    msgs.append({"role": "user", "content": user})
    payload = {"messages": msgs, "max_tokens": max_tokens, "temperature": 0.0}
    if grammar:
        payload["grammar"] = grammar
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",
                                 json.dumps(payload).encode(), {"Content-Type": "application/json"})
    for attempt in range(retries):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)["choices"][0]["message"]["content"], time.time() - t0
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt < retries - 1:
                time.sleep(1)
                continue
            raise
    raise RuntimeError("server never became ready")
