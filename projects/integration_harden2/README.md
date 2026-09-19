# integration_harden2 — the Gemma single-model MVD

Fork of `integration_harden` (2026-09-08) for the Gemma 4 E4B single-model stack: whisper-ivrit ASR
-> ONE Gemma 4 E4B call (routes, plans the mission, names the SAM3 target, and answers in Hebrew) ->
SAM3. `integration_harden` stays the clean stack for the judges; this copy is where the single model
is proven. Design rulings: Gemma reads Hebrew directly (no translator), thinking OFF, YOLO
background off by default, whisper stays, Hebrew answers go straight to the phone TTS.

Voice (Hebrew) -> safety-tier router -> COMPLEX text -> the Gemma recognizer, which routes AND
plans, over a live drone or webcam video. Components live here single-home; the bench imports them
in place. Python speaks the frozen ApiServer wire — no C++ FMU engine in the loop.

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
| control/ | transcript -> safety tier, deterministic: commands.py (emergency/override/resume classifier, the emergency-regex source of truth), router.py (dispatch), dji_wire.py (frozen-wire client, loopback-guarded) |
| audio/ | voice I/O channels: ros2_asr.py (ROS2 transcript subscriber), phone_asr.py (phone-as-mic REST+TCP inlet, deduped), tts_io.py (TTS outlet: phone /tts, local phonikud fallback). ASR itself is EXTERNAL (asr_node + sttserv) |
| video/ | camera_stream.py (every frame source behind a cv2.VideoCapture-like surface), video_watchdog.py (stall monitor + gst respawn) |
| recognizer/ | the Hebrew Recognizer: ONE Gemma call types + plans + names the target (own README) |
| perception2/ | the DEFAULT perception engine: one SAM3-nf4 model (own README) |
| perception/ | the non-default OmDet+SAM2.1 engine, kept behind `SCENE_SEG=omdet` (own README) |
| test/ | wiring tests (models faked) + live_mock_smoke.py (the safety tiers over real HTTP vs the mock) |
| top-level glue | mvd.py (the app), config/ (package: constants.py baked values + defaults.py env-overridable), run.sh, run_llama_server.sh |

## Data flow

```
asr_node (H = push-to-talk) -> /asr_server/transcribe      phone mic -> :8080 (REST + TCP)
        \-- audio/ros2_asr.py --\                              \-- audio/phone_asr.py --\
                            v                                                        v
              control/router.py (safety tiers)
                            |-- EMERGENCY --> wire.halt() = POST /c/fly [{"delay":0}]  (preempt motion, KEEP control)
                            |-- OVERRIDE  --> wire.stop() = POST /c/stop  (hand control to the RC, mode->manual)
                            |-- RESUME    --> mode->auto
                            \-- COMPLEX   --> recognizer/pipeline.py  (ONE Gemma call: routes + plans, in Hebrew)
                                              |-- mission    --> control/dji_wire.py --> ApiServer (POST /c/fly)
                                              |-- perception --> SAM3 highlight / count / describe
                                              \-- reject     --> spoken back to the user (Hebrew)
              recognizer: ONE resident Gemma 4 E4B (:18090) reads Hebrew directly — no separate translator.

video:  llm_to_action_gstreamer_rx --dji --> ROS2 camera/stream --> video/camera_stream.py --> mvd
voice:  mvd --> audio/tts_io.py --> phone /tts (or local phonikud)
```

A mission is refused while the router is in manual mode (`Pipeline.flight_allowed` gates `_fly`);
perception still answers.

## Verification

```bash
python3 -m pytest /root/groundstation/projects/integration_harden2/test/ -q         # wiring tests (models faked)
python3 /root/groundstation/projects/integration_harden2/recognizer/recognizer.py   # Recognizer self-test
python3 /root/groundstation/projects/integration_harden2/perception2/sam3_backend.py # SAM3 backend smoke test
cd /root/groundstation/projects/integration_harden2 && python3 -m video.camera_stream 0   # webcam frames, no ROS
python3 /root/groundstation/projects/integration_harden2/test/live_mock_smoke.py    # safety tiers vs the mock
```
After a container rebuild run `bash /root/groundstation/tools/devenv/install-runtime-deps.sh`
(the mock needs aiohttp); `bash /root/groundstation/tools/preflight.sh` checks all of it.

## Run

```bash
# mock (safe, agent-testable):
bash /root/groundstation/projects/integration_harden2/run.sh up webcam mock
# real drone video + real control (HUMAN-only, aircraft SECURED):
PHONE_IP=<ip> bash /root/groundstation/projects/integration_harden2/run.sh up dji real
```
`dji` video flows gstreamer_rx -> camera/stream -> CameraStream (sole :5600 client).

Panes (tmux windows): `vlm` (the Gemma 4 E4B server, :18090) · `keys` · `asr` · (`gst` + `dog`
in dji mode) · `app` · (`mock` in mock mode). The model server is `run_llama_server.sh`; it runs
Gemma by default (`MVD_PLANNER=qwen3vl` selects the legacy Qwen3-VL server, not the default).

External binaries: `build/release/shared/dji/bin/llm_to_action_{gstreamer_rx,asr_server,keyboard_hook}`.

---

# REAL FLIGHT — runbook (HUMAN runs every motor command)

**Status:** control path re-verified on the mock 2026-09-02 (live_mock_smoke: the safety tiers,
real HTTP). **Never flown on real hardware.** Treat the first flight as a bring-up, not a demo.

## Pre-flight (all required — kill procedure is in CLAUDE.md)
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
PHONE_IP=<PHONE_IP> bash /root/groundstation/projects/integration_harden2/run.sh up webcam real
# 3b. Full demo (drone footage via gstreamer_rx -> camera/stream): use once 3a works
PHONE_IP=<PHONE_IP> bash /root/groundstation/projects/integration_harden2/run.sh up dji real
#     -> type ARMED, then press H to talk
```

## Example commands (spoken in Hebrew, planned by Gemma)
- Movement/mission intents become one of Gemma's 8 actions: `takeoff`, `land`, `fly_by` (dx/dy/dz),
  `spin_by`, `delay`, `gimbal_pitch` (aims the CAMERA only), `home` ("come home"), `wave` (a greeting).
- "follow" / "track" / "mark X" -> a camera highlight (perception), NOT a GPS follow.
- Deterministic safety words (EN + HE, no model): `stop`/`abort`/`freeze`/`kill` = EMERGENCY ·
  `manual` = hand to RC · `resume` = voice back on. These never wait on the model.

## KNOWN HAZARDS (read before arming)
- **`stop` (EMERGENCY) preempts motion but does NOT kill motors.** It sends `wire.halt()` = POST /c/fly `[{"delay":0}]`: the running mission is cancelled and we KEEP virtual-stick control. Not a hover, not a motor-kill. To truly cut motors, use the phone/aircraft procedure in CLAUDE.md.
- **`manual` (OVERRIDE) fires `/c/stop` = `controller.stop(emergency=true)` and hands control to the RC.** In-air outcome depends on the drone's `FCUrgentStopMotorMode`. That OVERRIDE calls stop() at all is a known concern (it should relinquish only) — verify before trusting voice override in the air.
- **Indoors:** lateral/vertical moves do nothing (VPS). Reliable indoor intents: takeoff, spin, land.
- **A move step blocks ~1.5 s** — you cannot interrupt it by voice mid-move. The power button is your
  real-time cut.
- **dji-video (camera_stream) is not runtime-verified.** If 3b hangs waiting for frames, fall back to 3a.
- The assistant NEVER runs these against a real drone. It prepares them; the HUMAN runs them.


## Runtime switches

| env | values | meaning |
|---|---|---|
| `VIDEO` | `webcam` (retest default) / `dji` / `rtmp` | frame source; webcam = the retest default (owner ruling 2026-09-08), nothing connected |
| `CONTROL` | `mock` / `real` | wire target; the ONE decision — config derives WIRE_HOST/PORT/REAL from it |
| `SCENE_TTS` | `phone` (default) / `phonikud` / `off` | the only TTS knob: phone Android TTS, offline phonikud+Piper, or silent |
| `SCENE_SEG` | `sam3` (default) / `omdet` | highlight backend: one SAM3-nf4 model (perception2), or the legacy OmDet+SAM2.1 (perception); with sam3, OmDet/SAM2.1 never load |
| `SCENE_SAM3_PERIOD` | seconds, default 1.0 | minimum gap between SAM3 forwards per phrase (the highlight worker runs every frame) |
| `RECORD` | `1` (default) / `0` | record the whole session (utterances + ASR clips) |

Perception tuning stays available as env overrides (`SCENE_HL_CONF`, `SCENE_HL_REL`,
`SCENE_DETECT_FLOOR`, `SCENE_COUNT_FRAMES`, `SCENE_COUNT_GAP`, ...); defaults live in config/.
Boot the desk stack with `VIDEO=webcam SCENE_TTS=off bash /root/groundstation/tools/desk-test/up.sh`
(sam3 is the default; no translator knob).


## Operator kill switch

In the scene window: **M** toggles the manual override. First press = override ON (POST /c/stop =
`stop(emergency)`: our virtual-stick authority is relinquished, the RC flies; every motion verb is
refused with 409). Next press = re-arm. The HUD line turns red while the override is on. Code:
control/kill.py; test: test/test_kill.py. The window must have keyboard focus. Not yet pressed in a
live session.
