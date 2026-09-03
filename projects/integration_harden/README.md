# integration_harden/ — the revised MVD

Voice -> 4-tier router -> {deterministic verbs fly the drone | complex text -> Recognizer /
perception}, over live drone or webcam video. Components live here single-home; the bench
imports them in place. Python speaks the frozen ApiServer wire — no C++ FMU engine in the loop.

## Sections

| section | content |
|---|---|
| Layout | packages and glue |
| Data flow | the runtime chain |
| Verification | checks that must stay green |
| Run | mock and real invocations |
| Real flight | HUMAN-only runbook + hazards |

## Layout

| path | role |
|---|---|
| control/ | transcript -> drone verb, deterministic: commands.py (4-tier grammar, emergency-regex source of truth), router.py (dispatch), dji_wire.py (frozen-wire client, loopback-guarded) |
| audio/ | voice I/O channels: ros2_asr.py (ROS2 transcript subscriber), phone_asr.py (phone-as-mic REST+TCP inlet, deduped), tts_io.py (TTS outlet: phone /tts, local piper/espeak fallback). ASR itself is EXTERNAL (asr_node + sttserv) |
| video/ | camera_stream.py (every frame source behind a cv2.VideoCapture-like surface), video_doctor.py (layer-by-layer path diagnosis), video_watchdog.py (stall monitor + gst respawn) |
| recognizer/ | the Hebrew Recognizer, stages 0-6 (own README, sync rule inside) |
| perception/ | the perception engine, injected models (own README) |
| test/ | 26 wiring tests (models faked) + live_mock_smoke.py (all 4 tiers over real HTTP vs the mock) |
| top-level glue | scene_omdet.py (the app), config.py, run_mvd.sh, run_router.py, run_llama_server.sh |

## Data flow

```
asr_node (H = push-to-talk) -> /asr_server/transcribe      phone mic -> :8080 (REST + TCP)
        └── audio/ros2_asr.py ──┐                              └── audio/phone_asr.py ──┐
                            ▼                                                        ▼
              control/router.py (4-tier) ── basic verbs ──► control/dji_wire.py ──► ApiServer :8080
                            └── COMPLEX ──► scene_omdet.py (perception/ + recognizer/)

video:  llm_to_action_gstreamer_rx --dji ──► ROS2 camera/stream ──► video/camera_stream.py ──► scene_omdet
voice:  scene_omdet ──► audio/tts_io.py ──► phone /tts (or local piper/espeak)
```

## Verification

```bash
python3 -m pytest /root/groundstation/projects/integration_harden/test/ -q         # 26 wiring tests
python3 /root/groundstation/projects/integration_harden/recognizer/recognizer.py   # Recognizer self-test
python3 /root/groundstation/projects/integration_harden/perception/engine.py       # perception self-test
cd /root/groundstation/projects/integration_harden && python3 -m video.camera_stream 0   # webcam frames, no ROS
python3 /root/groundstation/projects/integration_harden/test/live_mock_smoke.py    # 4 tiers vs the mock
```
After a container rebuild run `bash /root/groundstation/tools/devenv/install-runtime-deps.sh`
(the mock needs aiohttp); `bash /root/groundstation/tools/preflight.sh` checks all of it.

## Run

```bash
# mock (safe, agent-testable):
bash /root/groundstation/projects/integration_harden/run_mvd.sh webcam mock
# real drone video + real control (HUMAN-only, aircraft SECURED):
PHONE_IP=<ip> bash /root/groundstation/projects/integration_harden/run_mvd.sh dji real
```
`dji` video flows gstreamer_rx -> camera/stream -> CameraStream (sole :5600 client).

External binaries: `build/release/shared/dji/bin/llm_to_action_{gstreamer_rx,asr_server,keyboard_hook}`.

---

# REAL FLIGHT — runbook (HUMAN runs every motor command)

**Status:** control path re-verified on the mock 2026-09-02 (live_mock_smoke: all 4 tiers, real
HTTP). **Never flown on real hardware.** Treat the first flight as a bring-up, not a demo.

## Pre-flight (all required — see docs/runbooks/kill-switch-verification.md)
- Battery > 30%, RC on, phone on the drone hotspot, app **API Server ON**.
- Aircraft **SECURED** (clamped or firmly held in open space) — props-off is NOT enough.
- **OUTDOORS** — indoors the VPS refuses lateral/vertical sticks (yaw + slow vertical only).
- Know the kill BEFORE arming (surest first):
  1. **Hold aircraft power button 3–5 s** (hardware cut).
  2. Phone **API Server toggle OFF** (drops our authority).
  3. DJI **CSC** (both sticks bottom-inner; may be overridden while our virtual stick is active).

## Commands
```bash
# 1. phone IP = the WiFi gateway (if two 'default' lines, the phone is the wlan one):
ip route | awk '/^default/{print $3}'
# 2. verify the wire reaches the aircraft (safe, read-only) -> expect aircraft JSON:
curl http://<PHONE_IP>:8080/status/
# 3a. FIRST flight = control-focused, no drone-video dependency (webcam for the CV window):
PHONE_IP=<PHONE_IP> bash /root/groundstation/projects/integration_harden/run_mvd.sh webcam real
# 3b. Full demo (drone footage via gstreamer_rx -> camera/stream): use once 3a works
PHONE_IP=<PHONE_IP> bash /root/groundstation/projects/integration_harden/run_mvd.sh dji real
#     -> type ARMED, then press H to talk
```

## Voice verbs
- `take off` · `land` (discrete POSTs)
- `go up/down` · `go forward` · `back up` · `go left` · `go right` (bounded /c/fly missions)
- `spin` (yaw 45°/s)
- `stop`/`abort`/`freeze`/`kill` = EMERGENCY  ·  `manual` = hand to RC  ·  `resume` = voice back on

## KNOWN HAZARDS (read before arming)
- **`stop` AND `manual` fire `/c/stop` = `KeyEmergencyStop` (motor-kill), not a hover.** In-air outcome
  depends on the drone's `FCUrgentStopMotorMode`. Never treat "stop" as a pause. The "manual"=kill is a
  known bug (OVERRIDE should relinquish only) — fix before trusting voice override in the air.
- **Indoors:** `go left/right/up/down` do nothing (VPS). Reliable indoor verbs: `take off`, `spin`, `land`.
- **A move verb blocks ~1.5 s** — you cannot interrupt it by voice mid-move. The power button is your
  real-time cut.
- **dji-video (camera_stream) is not runtime-verified.** If 3b hangs waiting for frames, fall back to 3a.
- The assistant NEVER runs these against a real drone. It prepares them; the HUMAN runs them.
