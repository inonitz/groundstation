#!/usr/bin/env python3
"""
ws_latency.py -- measure laptop<->phone WebSocket round-trip latency at our REAL command
cadence, over the SAME wire we'll fly on (a JSON FlightParam in a WS text frame).

This isolates the one hop we can't otherwise measure and can't avoid:
    laptop  --(WiFi)-->  phone
No drone and no RC are needed -- run the echo server on the phone, the probe on the laptop.

Deps: pip install websockets   (pure python; installs on Termux with NO compiler, unlike aiohttp)

Phone  (Termux):  python3 ws_latency.py server 0.0.0.0 8080
Laptop:           python3 ws_latency.py client ws://<phone-ip>:8080 --hz 20 --secs 30

The probe streams {vx,vy,vz,yaw,_seq} at --hz; the server echoes each frame unchanged; the
probe times send->echo per frame. It prints RTT mean / p50 / p95 / p99 / max, jitter (stdev),
and dropped frames. Run it on BOTH 5GHz and 2.4GHz, and BOTH phone-hotspot and shared-router,
and keep the config with the lowest p99. one-way control latency ~ RTT/2.
"""
import argparse
import asyncio
import json
import statistics
import sys
import time

try:
    import websockets
except ImportError:
    sys.exit("need: pip install websockets")


async def run_server(host, port):
    async def echo(ws):
        async for msg in ws:
            await ws.send(msg)          # echo unchanged -- the server does zero work
    async with websockets.serve(echo, host, port, ping_interval=None):
        print(f"[server] echo on ws://{host}:{port}  (Ctrl-C to stop)")
        await asyncio.Future()          # run forever


async def run_client(url, hz, secs):
    period = 1.0 / hz
    n = int(hz * secs)
    pending = {}                        # seq -> perf_counter() at send
    rtts = []                           # matched round-trips, ms
    async with websockets.connect(url, ping_interval=None, open_timeout=5) as ws:
        async def recv():
            while True:
                d = json.loads(await ws.recv())
                seq = d.get("_seq")
                t = pending.pop(seq, None)
                if t is not None:
                    rtts.append((time.perf_counter() - t) * 1000.0)
        rx = asyncio.create_task(recv())
        t0 = time.perf_counter()
        for seq in range(n):
            pending[seq] = time.perf_counter()
            await ws.send(json.dumps({"vx": 0.3, "vy": 0.0, "vz": 0.0, "yaw": 0.0, "_seq": seq}))
            slack = (t0 + (seq + 1) * period) - time.perf_counter()   # pace to target cadence
            if slack > 0:
                await asyncio.sleep(slack)
        await asyncio.sleep(0.5)         # let stragglers echo back
        rx.cancel()
    report(rtts, sent=n, hz=hz, secs=secs)


def pct(xs, p):
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return xs[k]


def report(rtts, sent, hz, secs):
    if not rtts:
        print("[client] no echoes back -- server unreachable, wrong IP, or firewall")
        return
    lost = sent - len(rtts)
    print(f"[client] {hz}Hz x {secs}s  sent={sent}  echoed={len(rtts)}  "
          f"lost={lost} ({100.0 * lost / sent:.1f}%)")
    print(f"  RTT ms  mean={statistics.mean(rtts):.1f}  p50={pct(rtts,50):.1f}  "
          f"p95={pct(rtts,95):.1f}  p99={pct(rtts,99):.1f}  max={max(rtts):.1f}  "
          f"jitter(stdev)={statistics.pstdev(rtts):.1f}")
    print("  one-way control latency ~ RTT/2; p99/2 is the worst-case age of a command in flight.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("server")
    s.add_argument("host", nargs="?", default="0.0.0.0")
    s.add_argument("port", nargs="?", type=int, default=8080)
    c = sub.add_parser("client")
    c.add_argument("url")
    c.add_argument("--hz", type=float, default=20)
    c.add_argument("--secs", type=float, default=30)
    a = ap.parse_args()
    if a.mode == "server":
        asyncio.run(run_server(a.host, a.port))
    else:
        asyncio.run(run_client(a.url, a.hz, a.secs))


if __name__ == "__main__":
    main()
