#!/usr/bin/env python3
"""
Mock of the recon-swarm Android ApiServer (com/kcg/dr/api/ApiServer.kt), so the Linux
DjiBackend can be built and tested with NO drone and NO Android device present.

It serves the FROZEN protocol in docs/specs/spec-dji-websocket-protocol.md:
  GET  /status/ /status/battery /status/gps /status/signal   (telemetry)
  WS   /c/ws/sticks                                          (FlightParam control + keepalive)
  POST /c/takeoff /c/land /c/fly                             (discrete verbs)

It is a real dev harness, not just a stub: the received sticks drive a fake velocity, which
is integrated into position at ~20 Hz. So the DjiBackend sees the "drone" actually respond to
its commands -- you can bring up the whole servo loop against this.

Run:  pip install aiohttp && python3 mock_apiserver.py 0.0.0.0 8080
Then point DjiBackend at ws://127.0.0.1:8080 / http://127.0.0.1:8080.

NOTE: FlightParam = {vx, vy, vz, yaw} (body-frame m/s + yaw rate), read from AircraftController.kt.
This mock parses those exact fields and logs every raw sticks message, so you can verify what the
real backend sends and align both sides in one place.
"""
import asyncio
import json
import os
import sys
import time

from aiohttp import web, WSMsgType

# Fake aircraft state (world frame, meters / m per s / radians). Mutated by the sticks WS and
# advanced by the integrator task. Single-writer via the asyncio loop -- no lock needed.
STATE = {
    "isFlying": False,
    "pos": {"x": 0.0, "y": 0.0, "z": 0.0},
    "vel": {"x": 0.0, "y": 0.0, "z": 0.0},
    "yaw": 0.0,
    "batteryPct": 87,
}
LAST_STICKS_US = 0  # for the keepalive/failsafe check

# When MOCK_SILENT_VERBS is set, faithfully simulate the CURRENT recon-swarm app:
# POST /c/takeoff and /c/land perform the action but send NO ok body (the author
# omitted call.respond() on those two POST handlers -- confirmed in ApiServer.kt).
# We return 204 No Content. The Linux backend must then confirm the verb from
# telemetry (aircraft.isFlying), not from the HTTP reply.
SILENT_VERBS = bool(os.environ.get("MOCK_SILENT_VERBS"))

# Where received REST commands are recorded. The desk test needs the mock to SHOW what the
# system sent (method, path, full JSON body). Default sits next to the other run logs.
CMD_LOG = os.environ.get("MOCK_CMD_LOG") or os.path.join(os.environ.get("TMPDIR") or "/tmp",
                                                         "mock_commands.log")


async def log_cmd(req):
    """Record one received REST command to console and to CMD_LOG.

    Additive only: this never changes a response. The body is read here, but aiohttp caches the
    read, so a later req.json() in the same handler still returns the same body. Fields logged:
    an ISO-like timestamp, the HTTP method, the path, and the full raw body.
    """
    try:
        raw = await req.text()
    except Exception:
        raw = ""
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[mock-cmd] {ts} {req.method} {req.path} {raw.strip()}"
    print(line, flush=True)
    try:
        with open(CMD_LOG, "a") as fh:
            fh.write(line + "\n")
    except Exception as e:
        print(f"[mock] cmd-log write failed: {e}", flush=True)


def now_us():
    return int(time.monotonic() * 1e6)


def sticks_to_velocity(param: dict):
    """Apply a FlightParam ({vx, vy, vz, yaw} -- body-frame m/s: vx fwd, vy right, vz up, + yaw
    rate; read from AircraftController.kt) to the fake velocity so the mock 'drone' responds to
    commands. Nullable fields default to 0."""
    STATE["vel"]["x"] = float(param.get("vx") or 0.0)
    STATE["vel"]["y"] = float(param.get("vy") or 0.0)
    STATE["vel"]["z"] = float(param.get("vz") or 0.0)
    return float(param.get("yaw") or 0.0)


async def integrator(app):
    """Advance the fake state at ~20 Hz so telemetry reflects the commands. Also drains a trickle
    of battery so /status/battery changes over a run."""
    dt = 0.05
    yaw_rate = 0.0
    try:
        while True:
            STATE["pos"]["x"] += STATE["vel"]["x"] * dt
            STATE["pos"]["y"] += STATE["vel"]["y"] * dt
            STATE["pos"]["z"] += STATE["vel"]["z"] * dt
            STATE["yaw"] += yaw_rate * dt
            # keepalive: if no sticks for >1 s while flying, zero the horizontal velocity. This
            # mirrors the real drone: when virtual-stick input stops it brakes to hover (MSDK), so a
            # dropped WS does not run away -- it hovers until DJI's low-battery failsafe lands it.
            if STATE["isFlying"] and (now_us() - LAST_STICKS_US) > 1_000_000:
                STATE["vel"]["x"] = STATE["vel"]["y"] = 0.0
            if int(time.monotonic()) % 10 == 0 and STATE["batteryPct"] > 5:
                STATE["batteryPct"] -= 0  # placeholder; keep steady unless you want drain
            await asyncio.sleep(dt)
    except asyncio.CancelledError:
        return


def ok(**fields):
    return web.json_response({"ok": True, **fields})


def stat(s):
    """Kotlin `status { "..." }` wrapper -> {"ok": true, "status": "..."}."""
    return web.json_response({"ok": True, "status": s})


def err(msg):
    return web.json_response({"ok": False, "error": msg})


# ---- Telemetry (GET /status/*). The real server wraps these in {"ok": true, ...}. ----
async def status(_req):
    return ok(aircraft={
                  "isFlying": STATE["isFlying"], "battery": STATE["batteryPct"],
                  "velocity3D": STATE["vel"], "position3D": STATE["pos"],
                  "attitude": {"pitch": 0.0, "roll": 0.0, "yaw": STATE["yaw"]},
                  "gimbalAttitude": {"pitch": 0.0, "roll": 0.0, "yaw": 0.0},
              },
              product={"version": "mock-1.0", "connection": True},
              controller={"version": "mock-1.0", "connection": True})


async def status_battery(_req):
    return ok(voltage=15.2, capacity=2200, remaining=1900, percent=STATE["batteryPct"])


async def status_gps(_req):
    # real: ok(build) when valid else nok(build)
    return web.json_response({"ok": False, "satCount": 0, "signalLevel": 0,
                              "valid": False, "compass": STATE["yaw"]})


async def status_signal(_req):
    return ok(connection=True, quality=5, frequency="2.4G", range=0)


# ---- Root + phone services ----
async def root(_req):
    return web.Response(text="recon-swarm ApiServer mock -- OK")


async def tts(req):
    await log_cmd(req)
    return ok()


async def key(req):
    await log_cmd(req)
    try: body = await req.json()
    except Exception: body = None
    return ok(result=body)


# ---- Control (/c). controllerRoute in the app returns 503 if no controller; the mock is always ready. ----
async def controller_root(_req):
    return stat("controller is ready")


async def flyto(req):
    await log_cmd(req)
    try: body = await req.json()
    except Exception: body = None
    return ok(flyTo=body)


async def lookat(req):
    await log_cmd(req)
    try: body = await req.json()
    except Exception: body = None
    return ok(lookAt=body)


async def fly(req):
    # 2026-09-04 "better action list request parsing": accepts a JSON ARRAY of Actions OR a single
    # Action object -- NOT the old {"mission":[...]} wrapper. Responds {"ok":true,"actions":[...]}.
    await log_cmd(req)
    try: body = await req.json()
    except Exception: body = None
    if isinstance(body, list):
        actions = body
    elif isinstance(body, dict):
        actions = [body]
    else:
        actions = []
    return ok(actions=actions)


async def takeoff(req):
    await log_cmd(req)
    STATE["isFlying"] = True
    STATE["pos"]["z"] = max(STATE["pos"]["z"], 1.2)
    return stat("taking off")


async def land(req):
    await log_cmd(req)
    STATE["isFlying"] = False
    STATE["vel"] = {"x": 0.0, "y": 0.0, "z": 0.0}
    STATE["pos"]["z"] = 0.0
    return stat("landing")


async def stop(req):
    await log_cmd(req)
    STATE["vel"] = {"x": 0.0, "y": 0.0, "z": 0.0}
    return stat("stop")


async def wave(_req):
    return stat("Hello! o/")


async def stream_start(req):
    await log_cmd(req)
    try: body = await req.json()
    except Exception: body = None
    url = body.get("rtmpUrl") if isinstance(body, dict) else None
    if not url:
        return err("rtmp url is required")
    return ok(message="Stream started", url=str(url).strip('"'))


async def stream_stop(req):
    await log_cmd(req)
    return ok(message="Stream stopped")


async def stream_status(_req):
    return ok(isStreaming=False)


# ---- Quick actions: root-level GET discretes (get(Regex("/(fly|takeoff)")), get("/land")). ----
async def quick_takeoff(req):
    await log_cmd(req)
    STATE["isFlying"] = True
    STATE["pos"]["z"] = max(STATE["pos"]["z"], 1.2)
    return ok()


async def quick_land(req):
    await log_cmd(req)
    STATE["isFlying"] = False
    STATE["vel"] = {"x": 0.0, "y": 0.0, "z": 0.0}
    STATE["pos"]["z"] = 0.0
    return ok()


async def ws_sticks(req):
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    global LAST_STICKS_US
    print("[mock] /c/ws/sticks client connected")
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                LAST_STICKS_US = now_us()
                print(f"[mock] sticks raw: {msg.data}")   # <-- see EXACTLY what DjiBackend sends
                try:
                    param = json.loads(msg.data)
                    sticks_to_velocity(param)
                except Exception as e:
                    print(f"[mock] bad FlightParam: {e}")
                await ws.send_str(json.dumps({"param": msg.data}))
            elif msg.type == WSMsgType.ERROR:
                print(f"[mock] ws error: {ws.exception()}")
    finally:
        # On WS drop the real drone brakes to hover (virtual-stick decays to hover); the mock
        # mirrors that by stopping horizontal drift. No hover-then-land hack needed.
        STATE["vel"]["x"] = STATE["vel"]["y"] = 0.0
        print("[mock] /c/ws/sticks client disconnected")
    return ws


async def ws_echo(req):
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    await ws.send_str("Echo connected")
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            if msg.data in ("bye", "x", "stop"):
                await ws.close(); break
            await ws.send_str(f"Hi, {msg.data}!")
    return ws


async def ws_gimbal(req):
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    await ws.send_str("Connected to gimbal websocket")
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            print(f"[mock] gimbal raw: {msg.data}")
    return ws


async def ws_telemetry(req):
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    await ws.send_str("Connected to telemetry websocket")
    try:
        while not ws.closed:
            await ws.send_str(json.dumps({"isFlying": STATE["isFlying"], "position3D": STATE["pos"],
                                          "velocity3D": STATE["vel"], "yaw": STATE["yaw"]}))
            await asyncio.sleep(0.1)
    except Exception:
        pass
    return ws


async def on_start(app):
    app["integrator"] = asyncio.create_task(integrator(app))


async def on_stop(app):
    app["integrator"].cancel()


def build_app():
    app = web.Application()
    app.add_routes([
        web.get("/", root),
        web.get("/status/", status),
        web.get("/status", status),                       # IgnoreTrailingSlash in the real app
        web.get("/status/battery", status_battery),
        web.get("/status/gps", status_gps),
        web.get("/status/signal", status_signal),
        web.post("/tts", tts),
        web.post("/key", key),
        web.get("/c/", controller_root),
        web.get("/c", controller_root),
        web.post("/c/flyTo", flyto),
        web.post("/c/lookAt", lookat),
        web.post("/c/fly", fly),
        web.post("/c/takeoff", takeoff),
        web.post("/c/land", land),
        web.post("/c/stop", stop),
        web.get("/c/wave", wave), web.get("/c/hi", wave),
        web.get("/c/hey", wave), web.get("/c/hello", wave),
        web.post("/c/stream/start", stream_start),
        web.post("/c/stream/stop", stream_stop),
        web.get("/c/stream/status", stream_status),
        web.get("/fly", quick_takeoff), web.get("/takeoff", quick_takeoff),
        web.get("/land", quick_land),
        web.get("/c/ws/echo", ws_echo),
        web.get("/c/ws/sticks", ws_sticks),
        web.get("/c/ws/gimbal", ws_gimbal),
        web.get("/c/ws/telemetry", ws_telemetry),
    ])
    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    return app


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    print(f"[mock] recon-swarm ApiServer mock on {host}:{port} (LAN, no cloud)")
    print(f"[mock] REST commands -> {CMD_LOG}", flush=True)
    web.run_app(build_app(), host=host, port=port)
