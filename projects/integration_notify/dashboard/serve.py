#!/usr/bin/env python3
"""Lean MVD dashboard bridge (integration_notify). Serves the direct-emit files the app writes:
  /tmp/mvd_frame.jpg  (annotated video)   /tmp/mvd_state.json  (fps/target/subtitle/chat/notify)
Stdlib only. GUI-optional: the app runs fine with nothing watching. Fallback dashboard = the app's
own cv2 chat pane (always on). Run:  python3 dashboard/serve.py [port=8090]"""
import http.server, socketserver, os, sys
FRAME = os.environ.get("MVD_DASH_FRAME", "/tmp/mvd_frame.jpg")
STATE = os.environ.get("MVD_DASH_STATE", "/tmp/mvd_state.json")
HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8090

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, ctype, body):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        try: self.wfile.write(body)
        except BrokenPipeError: pass
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            try: self._send(200, "text/html", open(HTML, "rb").read())
            except FileNotFoundError: self._send(404, "text/plain", b"dashboard.html missing")
        elif path == "/frame.jpg":
            try: self._send(200, "image/jpeg", open(FRAME, "rb").read())
            except FileNotFoundError: self._send(503, "text/plain", b"no frame yet")
        elif path == "/state":
            try: self._send(200, "application/json", open(STATE, "rb").read())
            except FileNotFoundError: self._send(200, "application/json", b"{}")
        else:
            self._send(404, "text/plain", b"not found")

class Srv(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
if __name__ == "__main__":
    print(f"[dashboard] http://localhost:{PORT}  (frame={FRAME} state={STATE})", flush=True)
    Srv(("0.0.0.0", PORT), H).serve_forever()
