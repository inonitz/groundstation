#!/usr/bin/env python3
"""Workstation -> controller transport latency: WS round-trip over /c/ws/echo.
READ-ONLY. Echo does nothing to the drone -- isolates WiFi+phone cost from drone response.
Zero external deps (raw RFC6455 over stdlib socket).
Usage: measure_ws_rtt.py <host:port> [secs=360] [hz=20] [csv_out] [path=/c/ws/echo]
Preflight: GET /status/ first; aborts clean with the exact reason if the DJI chain is down.
The app echo replies "Hi, <text>!"; we time send->reply. Control frames (ping/pong) are
skipped and pings are ponged, so RTT reflects the real data round-trip only."""
import sys, time, socket, os, base64, struct, statistics, urllib.request, urllib.error

hp   = sys.argv[1]
host, port = (hp.split(":") + ["8080"])[:2]; port = int(port)
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 360.0
hz   = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
csv  = sys.argv[4] if len(sys.argv) > 4 else None
path = sys.argv[5] if len(sys.argv) > 5 else "/c/ws/echo"

HINTS = {
    "Remote Controller": "reseat phone->RC-N3 USB-C; accept the GrapheneOS USB permission popup",
    "Aircraft": "power the aircraft on; confirm it is linked/bound to the RC",
    "Product":  "MSDK not activated -- restart the app (first launch needs internet once)",
}
def preflight(host, port):
    """One GET /status/. Abort with the precise reason if the DJI chain is down -- no wasted run."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/status/", timeout=3) as r:
            r.read(); return
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").strip()
        print(f"PREFLIGHT FAILED: HTTP {e.code} -- {body}")
        for k, v in HINTS.items():
            if k in body: print(f"  -> {v}"); break
        sys.exit(2)
    except Exception as e:
        print(f"PREFLIGHT FAILED: cannot reach {host}:{port} ({e})")
        print("  -> phone unreachable: check the hotspot link + API Server toggle ON")
        sys.exit(2)
preflight(host, port)

def recvn(sock, n):
    buf = b""
    while len(buf) < n:
        c = sock.recv(n - len(buf))
        if not c: return buf
        buf += c
    return buf

def recv_frame(sock):
    b = recvn(sock, 2)
    if len(b) < 2: return None, b""
    op = b[0] & 0x0f; ln = b[1] & 0x7f
    if ln == 126: ln = struct.unpack(">H", recvn(sock, 2))[0]
    elif ln == 127: ln = struct.unpack(">Q", recvn(sock, 8))[0]
    return op, (recvn(sock, ln) if ln else b"")

def send_frame(sock, opcode, payload):
    m = os.urandom(4); h = bytearray([0x80 | opcode]); ln = len(payload)
    if ln < 126: h.append(0x80 | ln)
    elif ln < 65536: h.append(0x80 | 126); h += struct.pack(">H", ln)
    else: h.append(0x80 | 127); h += struct.pack(">Q", ln)
    h += m
    sock.sendall(bytes(h) + bytes(b ^ m[i % 4] for i, b in enumerate(payload)))

def send_text(sock, msg): send_frame(sock, 0x1, msg.encode())

def recv_data(sock):
    """Next DATA frame (op,payload). Skip control frames; pong pings; None on close/eof.
    This is the fix: ping/pong keepalive frames no longer masquerade as echo replies."""
    while True:
        op, pl = recv_frame(sock)
        if op is None: return None, b""
        if op == 0x9: send_frame(sock, 0xA, pl); continue   # ping -> pong
        if op == 0xA: continue                              # pong -> ignore
        if op == 0x8: return None, pl                       # close
        return op, pl                                       # 0x1 text / 0x2 binary

s = socket.create_connection((host, port), timeout=5)
key = base64.b64encode(os.urandom(16)).decode()
s.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
           f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
resp = b""
while b"\r\n\r\n" not in resp:
    c = s.recv(1)
    if not c: break
    resp += c
if b"101" not in resp.split(b"\r\n")[0]:
    print("WS handshake FAILED:", resp[:120]); sys.exit(1)
s.settimeout(3)
recv_data(s)  # consume the initial "Echo connected" greeting frame

rtts, fails = [], 0
f = open(csv, "w") if csv else None
if f: f.write("t_ms,rtt_ms\n")
period = 1.0 / hz; t0 = time.monotonic(); i = 0
while time.monotonic() - t0 < secs:
    tick = time.monotonic()
    ts = time.monotonic()
    try:
        send_text(s, f"seq{i}"); i += 1
        op, _ = recv_data(s)
        if op is None: fails += 1; break
        rtt = (time.monotonic() - ts) * 1000.0
        rtts.append(rtt)
        if f: f.write(f"{(ts-t0)*1000:.1f},{rtt:.3f}\n")
    except Exception:
        fails += 1
    dt = period - (time.monotonic() - tick)
    if dt > 0: time.sleep(dt)
try: send_text(s, "bye")
except Exception: pass
s.close()
if f: f.close()

rtts.sort()
def pct(p):
    if not rtts: return float("nan")
    return rtts[min(len(rtts)-1, int(round(p/100.0*(len(rtts)-1))))]
n = len(rtts); dur = time.monotonic() - t0
print(f"WS TRANSPORT (/c/ws/echo)  host={host}:{port}")
print(f"  samples={n} fails={fails} hz={hz:.0f} dur={dur:.0f}s")
if n:
    print(f"  min={rtts[0]:.2f}  p50={pct(50):.2f}  p90={pct(90):.2f}  p95={pct(95):.2f}  "
          f"p99={pct(99):.2f}  max={rtts[-1]:.2f}  mean={statistics.mean(rtts):.2f}  "
          f"jitter(stdev)={statistics.pstdev(rtts):.2f}  ms")
