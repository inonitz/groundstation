"""Model serving for the bench. This file, and only this file, starts llama-server.

harden2 runs ONE model server: the planner (the vision-language model). The model is chosen in
run_llama_server.sh; there is no translator in the live path. It runs through the LlamaServer context
manager below: one model resident at a time, loaded on enter, verified dead on exit. Server stderr
goes to LOG_PATH, and a startup failure crashes (die) with the log tail, never silently.
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
    "gemma4": "/root/models/vlm/Gemma-4-E4B/gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf",   # candidate single-model Hebrew planner + VLM (2026-09-08)
}
GEMMA4_EXTRA = (("--jinja", "--chat-template-kwargs", '{"enable_thinking":true}') if os.environ.get("GEMMA4_THINK") == "1"
                else ("--jinja", "--chat-template-kwargs", '{"enable_thinking":false}', "--reasoning-budget", "0"))   # GEMMA4_THINK=1 = thinking ON (A/B arm)
# ^ thinking OFF for real (2026-09-08): --reasoning-budget 0 alone still narrated on 57/413 translations; enable_thinking=false
#   via the jinja template stopped 12/12 narrating cases (llama.cpp discussion 21338; --reasoning off needs build b8738+).
from fatal import die

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
                die(f"llama-server died on startup (rc={self.proc.returncode}):\n{tail}")
            time.sleep(1)
        die(f"llama-server not healthy after 120s (port {self.port})")

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
            die(f"model server HTTP {e.code} on port {port} (after {attempt+1} tries)")
    die(f"model server on port {port} never became ready after {retries} tries")
