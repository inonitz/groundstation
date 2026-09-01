# Morning checklist — 2026-08-27 (demo 18:00, finalize 12:00–16:00)

Everything below is additive. `integration/` (today's field-tested demo) is UNTOUCHED and is the
fallback. Nothing here can break it.

## A. Notify feature — webcam test (drone-free, do this on the train)
```bash
cd /root/groundstation/source/integration_notify
bash bootstrap.sh                                   # start+prewarm VLM, check models (once)
NOTIFY_ATTRS="in a red shirt" bash run.sh           # webcam + notify; dashboard on http://localhost:8090
```
- Walk into frame wearing the attribute → expect 🔔 chat line + spoken alert + red box on the person.
- Or arm by voice (press H): "notify me when someone in a red shirt shows up".
- Appearance re-ID (survives leave/re-enter): `NOTIFY_TRACKER=osnet bash run.sh` (needs torchreid weights;
  falls back to IoU automatically if unavailable). Default is the dependency-free IoU tracker.
- Indoor perception-only demo (no flight): add `MVD_NO_ACTIONS=1`.
- Tunables if it over/under-fires: `NOTIFY_MIN_HITS` (debounce), `NOTIFY_REID_THR` (osnet).

## B. Gazebo pitch screenshot + llm_to_action dashboard
PX4 SITL FMU binaries are BUILT (separate `px4` tree; can't affect the demo).
```bash
cd /root/groundstation
# Terminal 1 — SITL + Gazebo + FMU(observability) + VLM. NAV_DLL_ACT=0 waives QGroundControl:
FMU_OBSERVABILITY=1 LAUNCH_VLM=1 PX4_PARAM_NAV_DLL_ACT=0 bash scripts/test/SITL/approach/run.sh
# Terminal 2 — the llm_to_action dashboard (once the drone is flying):
source /opt/ros/jazzy/setup.bash
python3 source/llm_to_action/dashboard/serve.py 8088     # open http://localhost:8088
```
Screenshot: the Gazebo window (x500 drone in the world) + the dashboard (annotated cam + depth + HUD +
VLM log). Needs a display. Canned `approach` = a clean flight; for the VLM-reasoning panel use a
VLM-driven run (`FMU_SCENARIO_FLAG=""` + an objective, `LAUNCH_VLM=1`).
Already-done headless alternative: `docs/active/assets/fmu-sim-telemetry.png` (trajectory + altitude + speed).

## C. Latency capture (the scored <1s, command→action)
```bash
# Train/anywhere (mock floor): pip install aiohttp; python3 scripts/test/dji_mock/mock_apiserver.py 127.0.0.1 8080 &
build/release/shared/dji/bin/dji_latency_probe 127.0.0.1 8080 30 8
# On-site (real drone SECURED, you run it):
GW=$(ip route | awk '/^default/{print $3; exit}'); build/release/shared/dji/bin/dji_latency_probe "$GW" 8080 30 8
```

## D. Kill switch (surest first)
1. Aircraft POWER BUTTON, hold 3–5s (hardware cut, always works).
2. Phone API Server toggle OFF / force-close app (drops our authority).
3. DJI CSC (both sticks bottom-inner; may be overridden under virtual stick).
Software: say "stop" (halt) or "manual" (hand to RC).

## Status: BUILT + headless-tested overnight
- notify tracker (IoU+OSNet), NotifyEngine, voice-arm, perception-only, dashboard direct-emit — all
  compile + unit/e2e PASS headless.
- NEEDS YOUR LIVE TEST: real webcam + VLM attribute match, the GUI window, OSNet weights download,
  threshold feel. Fallback if any of it misbehaves: run `integration/` exactly as today.

## Owed / open
- OSNet weights auto-download on first `NOTIFY_TRACKER=osnet` run (needs internet once, then cached).
- Phone ASR needs your APK recompile (your lane); laptop press-H mic is the fallback.
- Outdoor demo = perception-only over the drone feed (`MVD_NO_ACTIONS=1`) if you keep flight off.
