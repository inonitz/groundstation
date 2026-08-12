#!/usr/bin/env python3
"""Self-assessment for the A2 dashboard against a running FMU (SITL or real).

Subscribes the four observability topics for a few seconds, then exercises the
dashboard bridge over HTTP, and writes a PASS/FAIL verdict with the evidence it
saw. Designed to be run alongside a headless SITL stack: it waits for topics to
appear, so it can start before the FMU is up.

Checks:
  - annotated + depth frames arriving, width == 320 (FMU-side resize)
  - publish rate sane (>0 and not wildly above the ~10 Hz cap -- a rate far above
    that means duplicate/phantom publishers, not a working throttle)
  - /fmu/hud present and parseable (STATE=... field)
  - bridge serves the page, real JPEG frames on both MJPEG streams, and an SSE
    stream carrying the live HUD

Run:  python3 scripts/dashboard/assess.py --port 8088 --out verdict.txt
Exit code 0 = all PASS, 1 = something FAILED.
"""
import argparse
import sys
import socket
import time
import urllib.request

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String


def collect(duration, wait_topics):
    """Subscribe the four topics; return counts, last width, last hud/vlm."""
    rclpy.init()
    n = Node("dashboard_assessor")
    state = {"a": 0, "d": 0, "h": 0, "v": 0, "width": None, "hud": "", "vlm": ""}

    def on_ann(m):
        state["a"] += 1
        state["width"] = m.width

    n.create_subscription(Image, "/fmu/perception/annotated", on_ann, 1)
    n.create_subscription(Image, "/fmu/perception/depth", lambda m: state.__setitem__("d", state["d"] + 1), 1)
    n.create_subscription(String, "/fmu/hud", lambda m: (state.__setitem__("h", state["h"] + 1), state.__setitem__("hud", m.data)), 10)
    n.create_subscription(String, "/fmu/vlm_text", lambda m: (state.__setitem__("v", state["v"] + 1), state.__setitem__("vlm", m.data)), 10)

    # Wait (up to wait_topics s) for the first annotated frame, then measure duration s.
    t0 = time.monotonic()
    while time.monotonic() - t0 < wait_topics and state["a"] == 0:
        rclpy.spin_once(n, timeout_sec=0.2)
    measured_from = time.monotonic()
    for k in ("a", "d", "h", "v"):
        state[k] = 0
    while time.monotonic() - measured_from < duration:
        rclpy.spin_once(n, timeout_sec=0.1)
    dt = time.monotonic() - measured_from
    n.destroy_node()
    rclpy.shutdown()
    state["dt"] = dt
    return state


def http_get(url, timeout, maxbytes):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read(maxbytes)


def read_sse(url, timeout):
    """Read an SSE stream until one blank-line-delimited event or the deadline.

    A slow HUD stream will not deliver a fixed byte count in a fixed time, so we
    accumulate small reads and stop at the first complete event. Partial data on
    timeout is fine -- the caller just checks what arrived.
    """
    data = b""
    t0 = time.monotonic()
    resp = urllib.request.urlopen(url, timeout=timeout)
    try:
        while time.monotonic() - t0 < timeout and b"\n\n" not in data:
            try:
                chunk = resp.read(64)
            except (socket.timeout, TimeoutError):
                break
            if not chunk:
                break
            data += chunk
    finally:
        resp.close()
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8088)
    ap.add_argument("--out", default="verdict.txt")
    ap.add_argument("--wait", type=float, default=90.0, help="max seconds to wait for topics")
    ap.add_argument("--measure", type=float, default=6.0, help="seconds to measure rates")
    args = ap.parse_args()

    base = f"http://localhost:{args.port}"
    checks = []  # (name, ok, evidence)

    st = collect(args.measure, args.wait)
    dt = st["dt"] or 1.0
    ann_hz, dep_hz = st["a"] / dt, st["d"] / dt

    checks.append(("annotated frames arriving", st["a"] > 0, f"{st['a']} msgs, {ann_hz:.1f} Hz"))
    checks.append(("depth frames arriving", st["d"] > 0, f"{st['d']} msgs, {dep_hz:.1f} Hz"))
    checks.append(("annotated width == 320 (FMU resize)", st["width"] == 320, f"width={st['width']}"))
    checks.append(("annotated rate under cap (<=13 Hz => no dup publishers)",
                   0 < ann_hz <= 13.0, f"{ann_hz:.1f} Hz"))
    checks.append(("HUD present + parseable", st["h"] > 0 and "STATE=" in st["hud"],
                   st["hud"][:100] or "(none)"))

    # HTTP layer
    try:
        page = http_get(base + "/", 4, 4096)
        checks.append(("bridge serves page", b"A2 Live Diagnostics" in page, f"{len(page)} B"))
    except Exception as e:
        checks.append(("bridge serves page", False, f"error: {e}"))
    for name, path in (("annotated", "/stream/annotated"), ("depth", "/stream/depth")):
        try:
            blob = http_get(base + path, 3, 200000)
            ok = b"\xff\xd8\xff" in blob and b"--frame" in blob
            checks.append((f"MJPEG {name} real frames", ok, f"{len(blob)} B, jpeg={ok}"))
        except Exception as e:
            checks.append((f"MJPEG {name} real frames", False, f"error: {e}"))
    try:
        ev = read_sse(base + "/events", 8.0).decode("utf-8", "replace")
        first = next((ln for ln in ev.splitlines() if ln.startswith("data:")), "")
        checks.append(("SSE carries live HUD", '"hud"' in ev and "STATE=" in ev,
                       first[:100] or "(no data line)"))
    except Exception as e:
        checks.append(("SSE carries live HUD", False, f"error: {e}"))

    all_ok = all(ok for _, ok, _ in checks)
    lines = [f"DASHBOARD ASSESSMENT: {'PASS' if all_ok else 'FAIL'}",
             f"(measured {st['a']}/{st['d']} ann/depth frames over {dt:.1f}s; "
             f"HUD='{st['hud'][:80]}'; VLM='{st['vlm'][:60]}')", ""]
    for name, ok, ev in checks:
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {name}  --  {ev}")
    report = "\n".join(lines) + "\n"

    with open(args.out, "w") as f:
        f.write(report)
    print(report)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
