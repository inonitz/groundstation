"""Gemma's process: its command line and its readiness check, as ONE ProcessSpec.

The app and the benches start Gemma the SAME way (owner ruling 2026-09-23): through the
supervisor, from process(). The app uses the app port; a bench passes its own port, so a
bench server never collides with the app's.
"""
import os
from functools import partial

import config
from system.supervisor import ProcessSpec
from util.guarded import http_request
from util.process import native_env


def thinking_flags(enabled):
    """Gemma thinking on or off, through the jinja template. OFF needs both flags:
    --reasoning-budget 0 alone still narrated on 57/413 translations;
    enable_thinking=false stopped 12/12 (2026-09-08, llama.cpp discussion 21338)."""
    if enabled:
        return ["--jinja", "--chat-template-kwargs", '{"enable_thinking":true}']

    return [
        "--jinja",
        "--chat-template-kwargs",
        '{"enable_thinking":false}',
        "--reasoning-budget",
        "0",
    ]


def port_up(port):
    """True when a llama-server on this port answers /health with 200 (loaded and
    ready). It answers 503 while the model still loads."""
    code, _reply, _error = http_request("127.0.0.1", port, "GET", "/health", timeout=1)
    return code == 200


def argv(port, thinking):
    """Gemma's command line, from config. Gemma gotchas (2026-09-08): NO
    --image-min-tokens (breaks its CLIP load), NO q4_0 KV + flash-attn (empty output)."""
    return [
        os.path.join(config.NATIVE_BIN_DIR, "llama-server"),
        "-m", config.GEMMA_MODEL_PATH,
        "--mmproj", config.GEMMA_MMPROJ_PATH,
        "-dev", "Vulkan0",
        "-ngl", "99",
        "-c", "4096",
        "-np", "1",
        "--temp", "0.0",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--threads", "1",
        *thinking_flags(thinking),
    ]


def process(
    log_dir,
    port=config.LLAMA_SERVER_PORT,
    thinking=config.GEMMA_THINKING_ENABLED
):
    """The Gemma process for the supervisor: STARTING -> UP once /health answers. The
    model loads in ~15-60 s, so it gets a long start-up window. A laptop part: past the
    restart budget the app dies."""
    return ProcessSpec(
        name="gemma",
        argv=argv(port, thinking),
        env=native_env(),
        ready=partial(port_up, port),
        ready_timeout_s=240.0,
        log_path=os.path.join(log_dir, "proc-gemma.log"),
    )
