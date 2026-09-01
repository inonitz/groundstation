#!/usr/bin/env python3
"""End-to-end telemetry latency: workstation -> phone -> drone -> back.
READ-ONLY. Polls GET /status/ as fast as it returns, for --secs. No motors, never arms.
Usage: measure_telemetry.py <host:port> [secs=360] [csv_out]
Preflight: one GET /status/; aborts clean with the exact reason if the DJI chain is down.
Prints full distribution; writes per-sample CSV (t_ms,rtt_ms,ok) if csv_out given."""
import sys, time, urllib.request, urllib.error, statistics

host = sys.argv[1]
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 360.0
csv  = sys.argv[3] if len(sys.argv) > 3 else None
url  = f"http://{host}/status/"

HINTS = {
    "Remote Controller": "reseat phone->RC-N3 USB-C; accept the GrapheneOS USB permission popup",
    "Aircraft": "power the aircraft on; confirm it is linked/bound to the RC",
    "Product":  "MSDK not activated -- restart the app (first launch needs internet once)",
}
def preflight(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            r.read(); return
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").strip()
        print(f"PREFLIGHT FAILED: HTTP {e.code} -- {body}")
        for k, v in HINTS.items():
            if k in body: print(f"  -> {v}"); break
        sys.exit(2)
    except Exception as e:
        print(f"PREFLIGHT FAILED: cannot reach {host} ({e})")
        print("  -> phone unreachable: check the hotspot link + API Server toggle ON")
        sys.exit(2)
preflight(url)

rtts, fails = [], 0
f = open(csv, "w") if csv else None
if f: f.write("t_ms,rtt_ms,ok\n")
t0 = time.monotonic()
while time.monotonic() - t0 < secs:
    s = time.monotonic()
    ok = 1
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            r.read()
    except Exception:
        ok = 0; fails += 1
    rtt = (time.monotonic() - s) * 1000.0
    if ok: rtts.append(rtt)
    if f: f.write(f"{(s-t0)*1000:.1f},{rtt:.2f},{ok}\n")
if f: f.close()

rtts.sort()
def pct(p):
    if not rtts: return float("nan")
    return rtts[min(len(rtts)-1, int(round(p/100.0*(len(rtts)-1))))]
n = len(rtts); dur = time.monotonic() - t0
print(f"TELEMETRY (GET /status/)  host={host}")
print(f"  samples={n} fails={fails} dur={dur:.0f}s rate={n/dur:.1f}/s")
if n:
    print(f"  min={rtts[0]:.1f}  p50={pct(50):.1f}  p90={pct(90):.1f}  p95={pct(95):.1f}  "
          f"p99={pct(99):.1f}  max={rtts[-1]:.1f}  mean={statistics.mean(rtts):.1f}  "
          f"jitter(stdev)={statistics.pstdev(rtts):.1f}  ms")
