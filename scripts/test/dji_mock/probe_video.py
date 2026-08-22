#!/usr/bin/env python3
"""READ-ONLY probe of the drone raw-video TCP stream (port 5600).
Connects, reads bytes for a few seconds, NEVER sends. Reports throughput and detects H.264 vs H.265
from Annex-B NAL unit types. Usage: probe_video.py <host> [port=5600] [secs=5]"""
import sys, socket, time
host = sys.argv[1]
port = int(sys.argv[2]) if len(sys.argv) > 2 else 5600
secs = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
try:
    s = socket.create_connection((host, port), timeout=5)
except Exception as e:
    print(f"NO VIDEO: cannot connect {host}:{port} ({e})"); sys.exit(1)
s.settimeout(2.0)
buf = bytearray(); total = 0; t0 = time.monotonic()
while time.monotonic() - t0 < secs:
    try: c = s.recv(65536)
    except socket.timeout: break
    if not c: break
    total += len(c)
    if len(buf) < 4_000_000: buf += c
s.close()
dur = time.monotonic() - t0
if total == 0:
    print(f"CONNECTED but NO DATA on {host}:{port} in {dur:.1f}s — not producing (camera off? not streaming?)")
    sys.exit(2)
b = bytes(buf); i = 0; frames = 0; h264 = {}; h265 = {}
def sc_len(b, i):
    if b[i:i+4] == b"\x00\x00\x00\x01": return 4
    if b[i:i+3] == b"\x00\x00\x01": return 3
    return 0
while i < len(b) - 4:
    n = sc_len(b, i)
    if n:
        frames += 1; hb = b[i+n]
        t4 = hb & 0x1F; t5 = (hb >> 1) & 0x3F
        h264[t4] = h264.get(t4, 0) + 1; h265[t5] = h265.get(t5, 0) + 1
        i += n
    else: i += 1
h265_param = sum(h265.get(t, 0) for t in (32, 33, 34))
h264_param = sum(h264.get(t, 0) for t in (7, 8))
codec = "H.265/HEVC" if h265_param > h264_param else "H.264/AVC"
kbps = total * 8 / 1000.0 / dur
print(f"VIDEO LIVE  {host}:{port}")
print(f"  bytes={total}  dur={dur:.1f}s  ~{kbps:.0f} kbps  NAL start-codes={frames}")
print(f"  codec guess: {codec}  (h264 param-sets={h264_param}, h265 param-sets={h265_param})")
print(f"  NAL types  H264={dict(sorted(h264.items()))}  H265={dict(sorted(h265.items()))}")
print("  (H264: 7=SPS 8=PPS 5=IDR 1=slice | H265: 32=VPS 33=SPS 34=PPS 19/20=IDR)")
