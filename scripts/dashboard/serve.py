#!/usr/bin/env python3
"""Lean live-dashboard bridge: ROS topics to a browser over the Python stdlib.

One rclpy node subscribes the A2 observability topics. One ThreadingHTTPServer
serves the page, an MJPEG stream per image, and a single SSE stream for the HUD
and VLM text. The only non-stdlib imports are the ROS runtime that is already on
the path in a sourced workspace: rclpy, cv_bridge, cv2. No websockets, no
rosbridge, no foxglove -- none of those are installed and none are added here.

The FMU already downscales the annotated and depth frames to 320x240 and caps
them near 10 fps under the FMU_OBSERVABILITY gate, so this process only has to
JPEG-encode what arrives and fan it out. It never requests full frames.

Logging: everything goes to stderr, and also to a file when --log <path> is
given (or the DASH_LOG env var is set). Add --verbose (or DASH_VERBOSE=1) for
per-request DEBUG detail. The log records subscription rates, every HTTP
request, each stream's open/close with frames sent, and any encode error --
enough to diagnose "the page is blank" without guessing which layer failed.

Run:  python3 scripts/dashboard/serve.py [port] [--log FILE] [--verbose]
      (default port 8088)
"""

import argparse
import json
import logging
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

HTML_FILE = Path(__file__).with_name("dashboard.html")
JPEG_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, 70]   # reassigned from --quality in main()
RATE_LOG_PERIOD_S = 5.0   # how often each subscription logs a rate summary

LOG = logging.getLogger("dashboard")


def setup_logging(log_path, verbose):
    level = logging.DEBUG if verbose else logging.INFO
    LOG.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", "%H:%M:%S")
    stderr = logging.StreamHandler(sys.stderr)
    stderr.setFormatter(fmt)
    LOG.addHandler(stderr)
    if log_path:
        fh = logging.FileHandler(log_path)
        fh.setFormatter(fmt)
        LOG.addHandler(fh)
        LOG.info("logging to file: %s", log_path)


class Shared:
    """Latest frame per stream plus the latest HUD/VLM text, shared across threads.

    Frames use a plain lock: readers just want the newest bytes. HUD/VLM text uses
    a condition so an SSE reader can block until something actually changes instead
    of polling. seq bumps on every text change and is the version an SSE client
    waits on.
    """

    def __init__(self):
        self.frame_lock = threading.Lock()
        self.frames = {"annotated": None, "depth": None}
        self.text_cond = threading.Condition()
        self.hud = ""
        self.vlm = ""
        self.ctx = ""
        self.rates_pub = "{}"   # raw JSON from /fmu/rates: FMU's own perception + publish rates
        self.rx = {"annotated": 0, "depth": 0, "hud": 0}   # cumulative received counts
        self.rx_lock = threading.Lock()
        self.rates_rx = {"annotated": 0.0, "depth": 0.0, "hud": 0.0}   # bridge-measured receive Hz
        self.seq = 0

    def set_frame(self, key, jpeg):
        with self.frame_lock:
            self.frames[key] = jpeg

    def get_frame(self, key):
        with self.frame_lock:
            return self.frames[key]

    def set_text(self, hud=None, vlm=None, ctx=None):
        with self.text_cond:
            if hud is not None:
                self.hud = hud
            if vlm is not None:
                self.vlm = vlm
            if ctx is not None:
                self.ctx = ctx
            self.seq += 1
            self.text_cond.notify_all()

    def bump_rx(self, key):
        with self.rx_lock:
            if key in self.rx:
                self.rx[key] += 1

    def set_rates_pub(self, data):
        with self.text_cond:
            self.rates_pub = data
            self.seq += 1
            self.text_cond.notify_all()

    def set_rates_rx(self, rates):
        with self.text_cond:
            self.rates_rx = rates
            self.seq += 1
            self.text_cond.notify_all()

    def snapshot_text(self):
        return json.dumps({"hud": self.hud, "vlm": self.vlm, "ctx": self.ctx,
                           "rates_pub": self.rates_pub, "rates_rx": self.rates_rx})



SH = Shared()
NODE = None   # the Bridge node; set in main, used by the MJPEG handler


class Bridge(Node):
    """Subscribe the four A2 topics; JPEG-encode images, cache text.

    Every subscription keeps a running count and logs a rate summary every
    RATE_LOG_PERIOD_S so the log shows, at a glance, whether frames are actually
    arriving from the FMU and at what rate.
    """

    def __init__(self):
        super().__init__("dashboard_bridge")
        self.bridge = CvBridge()
        self.cb = ReentrantCallbackGroup()   # all subs share one group (mirrors the FMU node)
        self._stats_lock = threading.Lock()
        self._stats = {k: {"n": 0, "t0": time.monotonic(), "seen": False}
                       for k in ("annotated", "depth", "hud", "vlm", "ctx")}
        # depth 1 so a slow encoder drops stale frames instead of piling a backlog.
        self._img_subs = {"annotated": None, "depth": None}
        self._img_lock = threading.Lock()
        self._viewers = {"annotated": 0, "depth": 0}
        # Text topics are cheap -> always on. Image topics are heavy (230 KB/frame @ 10 Hz each),
        # so subscribe them only while a browser is streaming, and drop the subscription when the
        # last viewer leaves. With no one watching (most of a SITL run) the bridge receives no
        # images at all -> near-zero CPU.
        self.create_subscription(String, "/fmu/hud",
                                 lambda m: self._on_text("hud", m), 10, callback_group=self.cb)
        self.create_subscription(String, "/fmu/vlm_text",
                                 lambda m: self._on_text("vlm", m), 10, callback_group=self.cb)
        self.create_subscription(String, "/fmu/vlm_context",
                                 lambda m: self._on_text("ctx", m), 10, callback_group=self.cb)
        self.create_subscription(String, "/fmu/rates",
                                 lambda m: SH.set_rates_pub(m.data), 10, callback_group=self.cb)
        LOG.info("subscribed: /fmu/hud, /fmu/vlm_text, /fmu/vlm_context, /fmu/rates "
                 "(image topics subscribed on demand while viewed)")

    def stream_opened(self, key):
        with self._img_lock:
            self._viewers[key] += 1
            if self._img_subs[key] is None:
                topic = "/fmu/perception/" + key
                self._img_subs[key] = self.create_subscription(
                    Image, topic, lambda m, k=key: self._on_image(k, m), 1, callback_group=self.cb)
                LOG.info("subscribed %s (first viewer)", topic)

    def stream_closed(self, key):
        with self._img_lock:
            self._viewers[key] = max(0, self._viewers[key] - 1)
            if self._viewers[key] == 0 and self._img_subs[key] is not None:
                self.destroy_subscription(self._img_subs[key])
                self._img_subs[key] = None
                SH.set_frame(key, None)   # drop the stale cached frame
                LOG.info("unsubscribed /fmu/perception/%s (no viewers)", key)

    def _tick(self, key, extra=""):
        with self._stats_lock:
            st = self._stats[key]
            st["n"] += 1
            if not st["seen"]:
                st["seen"] = True
                LOG.info("first message on '%s'%s", key, extra)
            now = time.monotonic()
            dt = now - st["t0"]
            if dt >= RATE_LOG_PERIOD_S:
                LOG.info("'%s': %d msgs in %.1fs = %.1f Hz%s",
                         key, st["n"], dt, st["n"] / dt, extra)
                st["n"] = 0
                st["t0"] = now

    def _on_image(self, key, msg):
        SH.bump_rx(key)
        try:
            bgr = self.bridge.imgmsg_to_cv2(msg, "bgr8")
            ok, buf = cv2.imencode(".jpg", bgr, JPEG_PARAMS)
            if not ok:
                LOG.warning("cv2.imencode returned false for '%s' (%dx%d)",
                            key, msg.width, msg.height)
                return
            SH.set_frame(key, buf.tobytes())
            self._tick(key, f" ({msg.width}x{msg.height}, {len(buf)} B jpeg)")
        except Exception as exc:  # a bad frame must not kill the subscriber thread.
            LOG.warning("encode '%s' failed: %s", key, exc)

    def _on_text(self, key, msg):
        if key == "hud":
            SH.bump_rx("hud")
        SH.set_text(**{key: msg.data})
        self._tick(key)
        LOG.debug("'%s' <- %s", key, msg.data[:120])


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # Route the stdlib access log through our logger at DEBUG instead of stderr spam.
        LOG.debug("http %s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        LOG.info("GET %s from %s", self.path, self.address_string())
        if self.path in ("/", "/index.html"):
            self._serve_html()
        elif self.path == "/stream/annotated":
            self._serve_mjpeg("annotated")
        elif self.path == "/stream/depth":
            self._serve_mjpeg("depth")
        elif self.path == "/events":
            self._serve_sse()
        else:
            LOG.warning("404 for %s", self.path)
            self.send_error(404)

    def _serve_html(self):
        try:
            body = HTML_FILE.read_bytes()
        except OSError as exc:
            LOG.error("cannot read %s: %s", HTML_FILE, exc)
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        LOG.debug("served dashboard.html (%d B)", len(body))

    def _serve_mjpeg(self, key):
        # Streaming body, unknown length: close the connection when the client leaves.
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        who = self.address_string()
        NODE.stream_opened(key)   # subscribe the image topic while this stream is watched
        LOG.info("MJPEG '%s' stream opened for %s", key, who)
        sent, t0, waited_logged = 0, time.monotonic(), False
        try:
            while True:
                jpeg = SH.get_frame(key)
                if jpeg:
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
                    sent += 1
                elif not waited_logged:
                    waited_logged = True
                    LOG.warning("MJPEG '%s': no frame cached yet -- is the FMU "
                                "publishing /fmu/perception/%s?", key, key)
                time.sleep(0.1)  # ~10 fps ceiling; matches the FMU throttle.
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            NODE.stream_closed(key)   # drop the subscription when the last viewer leaves
            dt = time.monotonic() - t0
            LOG.info("MJPEG '%s' stream closed for %s: %d frames in %.1fs (%.1f fps)",
                     key, who, sent, dt, sent / dt if dt else 0.0)

    def _serve_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        who = self.address_string()
        LOG.info("SSE stream opened for %s", who)
        last, events = -1, 0
        try:
            # Push the current state once so a fresh tab is not blank until the next change.
            self.wfile.write(f"data: {SH.snapshot_text()}\n\n".encode())
            self.wfile.flush()
            events += 1
            while True:
                with SH.text_cond:
                    changed = SH.text_cond.wait_for(lambda: SH.seq != last, timeout=15)
                    last = SH.seq
                    payload = SH.snapshot_text()
                if changed:
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    events += 1
                else:
                    self.wfile.write(b": keep-alive\n\n")  # hold the connection open.
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            LOG.info("SSE stream closed for %s: %d events sent", who, events)


class DaemonThreadPool:
    """Fixed pool of daemon worker threads. Bounds concurrent HTTP connections instead of
    spawning a thread per client. Daemon threads so the process still exits cleanly on Ctrl-C
    while streams are mid-loop. A saturated pool queues new connections until a worker frees."""

    def __init__(self, workers):
        self._q = queue.Queue()
        for i in range(workers):
            threading.Thread(target=self._worker, daemon=True, name=f"dash-http-{i}").start()

    def submit(self, fn, *args):
        self._q.put((fn, args))

    def _worker(self):
        while True:
            fn, args = self._q.get()
            try:
                fn(*args)
            except Exception:
                pass


class PooledHTTPServer(HTTPServer):
    """Dispatch each request to a bounded daemon-thread pool (not the unbounded
    thread-per-connection of ThreadingHTTPServer). Long-lived MJPEG/SSE streams each hold one
    worker for their lifetime, so size the pool for the viewers you expect: >= 3 per open tab
    (two image streams + the SSE stream)."""

    allow_reuse_address = True

    def __init__(self, addr, handler, workers):
        super().__init__(addr, handler)
        self._pool = DaemonThreadPool(workers)

    def process_request(self, request, client_address):
        self._pool.submit(self._run, request, client_address)

    def _run(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def parse_args(argv):
    p = argparse.ArgumentParser(description="A2 dashboard bridge")
    p.add_argument("port", nargs="?", type=int, default=8088, help="HTTP port (default 8088)")
    p.add_argument("--log", default=os.environ.get("DASH_LOG"),
                   help="also write logs to this file (or set DASH_LOG)")
    p.add_argument("--workers", type=int, default=int(os.environ.get("DASH_WORKERS", "6")),
                   help="HTTP worker-pool size (bounded; needs >= 3 per open dashboard tab)")
    p.add_argument("--quality", type=int, default=int(os.environ.get("DASH_JPEG_QUALITY", "70")),
                   help="MJPEG JPEG quality 1-100 (default 70; raise for debugging, e.g. 92)")
    p.add_argument("--verbose", action="store_true",
                   default=os.environ.get("DASH_VERBOSE", "") not in ("", "0"),
                   help="DEBUG-level logging (per-request detail; or set DASH_VERBOSE=1)")
    return p.parse_args(argv)


def main():
    args = parse_args(sys.argv[1:])
    setup_logging(args.log, args.verbose)
    global JPEG_PARAMS
    JPEG_PARAMS = [cv2.IMWRITE_JPEG_QUALITY, max(1, min(100, args.quality))]
    LOG.info("starting dashboard bridge on port %d (verbose=%s)", args.port, args.verbose)

    rclpy.init()
    node = Bridge()
    global NODE
    NODE = node
    # Single-threaded spin is the leanest here: the two image encodes at 10 Hz fit one thread, and
    # rclpy's MultiThreadedExecutor added enough overhead to ~2x the watched CPU in A/B testing
    # (3.9% single-threaded vs 9% with 2 threads). The Reentrant group below is harmless with one
    # thread; kept only so the dynamic image subs share a group.
    def spin():
        try:
            rclpy.spin(node)
        except ExternalShutdownException:
            pass  # normal on Ctrl-C: main() called rclpy.shutdown() under us.

    threading.Thread(target=spin, daemon=True).start()

    def rater():
        prev = {"annotated": 0, "depth": 0, "hud": 0}
        prev_t = time.monotonic()
        while True:
            time.sleep(1.0)
            now = time.monotonic()
            dt = now - prev_t or 1.0
            prev_t = now
            with SH.rx_lock:
                cur = dict(SH.rx)
            SH.set_rates_rx({k: round((cur[k] - prev[k]) / dt, 1) for k in cur})
            prev = cur
    threading.Thread(target=rater, daemon=True).start()
    server = PooledHTTPServer(("0.0.0.0", args.port), Handler, args.workers)
    LOG.info("dashboard ready: http://localhost:%d (http worker pool=%d, ros executor=single-threaded)",
             args.port, args.workers)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("SIGINT -- shutting down")
    finally:
        server.shutdown()
        node.destroy_node()
        rclpy.shutdown()
        LOG.info("stopped")


if __name__ == "__main__":
    main()
