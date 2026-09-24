# integration_harden2 — the Gemma single-model MVD

Fork of `integration_harden` (2026-09-08) for the Gemma 4 E4B single-model stack: whisper-ivrit ASR
-> ONE Gemma 4 E4B call (routes, plans the mission, names the SAM3 target, and answers in Hebrew) ->
SAM3. `integration_harden` stays the clean stack for the judges; this copy is where the single model
is proven. Design rulings: Gemma reads Hebrew directly (no translator), thinking OFF, YOLO
background off by default, whisper stays, Hebrew answers go straight to the phone TTS.

Voice (Hebrew) -> the recognizer (its fast path first, then ONE Gemma call that routes AND
plans), over a live drone or webcam video. Components live here single-home; the bench imports them
in place. Python talks to the phone app's frozen ApiServer — no C++ FMU engine in the loop.

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
| app/ | main.py (starts every module, in order), turns.py (one spoken turn + the vision results -> chat, speech, log), ui.py (the screen: camera, status, chat), render.py (draws the panes), state.py (shared state), keys.py (the global F4 kill key) |
| dji_app/ | client.py: the phone-app client (http.HTTPStatus results, loopback-guarded, the transmit switch, /tts, the mock's ProcessSpec) |
| util/ | standalone helpers shared by several modules: guarded.py (the ONLY try/except around third-party calls: HTTP, JSON, files, streams), net.py (port_open, the JSON header), process.py (native_env, wait_exit), hebrew.py (Hebrew numbers and letters), mission.py (a mission step as text) |
| control/ | flight.py: executes flight (critical commands, missions) and is the ONLY user of the phone app's transmit switch; parses nothing |
| log/ | session.py (the recording: SessionLog(folder), latest_session), show.py and score.py (read-only tools) |
| audio/ | speech_in.py (SpeechIn over config.ASR_SOURCES: asr_ros.py = the laptop mic through our ASR server, asr_phone.py = the phone's speech), speech_out.py (SpeechOut over config.TTS_OUTPUTS: tts_phone.py = the phone app's /tts, tts_laptop.py = offline phonikud) |
| video/ | video.py (Video: ONE source from config.VIDEO; opens, retries, reports its row, hands out frames, the stall guard), ros_stream.py (the phone's video via gstreamer + ROS2), cam_list.py (lists cameras) |
| recognizer/ | the Recognizer: parses every sentence (fast path, bypass, guards, rewrites) and routes it; ONE Gemma call plans the rest (own README) |
| perception2/ | vision: the vision service (one thread per task, the SAM3 priority lock), the SAM3 backend, the engine, concepts, counting, verify, the Gemma vision prompt (own README) |
| gemma/ | keeps the ONE Gemma server alive (server.py) and gives the one client to it (client.py) |
| system/ | fatal.py (die + crash hooks), status.py (Status: a row its owner sets; StatusBoard: asks each part for its rows), supervisor.py (ProcessSpec -> Process handle that owns its row; restarts, waits or dies), ros.py (the ONE ROS2 context + Subscription) |
| config/ | constants.py (baked values) + defaults.py (env-overridable); the one home of every setting |
| test/ | one test file per module: app, audio, control, dji_app, gemma, log, perception2, recognizer, system, util, video |
| top-level | run.sh (launches the app: `python3 -m app.main`) |

## Data flow

```
asr_node (F5 = push-to-talk) -> /asr_server/transcribe      phone mic -> :8080 (REST + TCP)
        \-- audio/asr_ros.py ---\                              \-- audio/asr_phone.py --\
                            v                                                        v
              recognizer/recognizer.py  (parses EVERY sentence)
                            |-- fast path: emergency / manual / auto --> control (no model)
                            |-- bypass mission (deterministic, no model) --> control
                            \-- ONE Gemma call: routes + plans, in Hebrew
                                              |-- mission    --> control --> dji_app/client.py --> ApiServer (POST /c/fly)
                                              |-- perception --> SAM3 highlight / count / describe
                                              \-- reject     --> spoken back to the user (Hebrew)
              recognizer: ONE resident Gemma 4 E4B (:18090) reads Hebrew directly — no separate translator.

video:  llm_to_action_gstreamer_rx --dji --> ROS2 camera/stream --> video/ros_stream.py --> Video --> app
voice:  app --> audio/speech_out.py --> each of TTS_OUTPUTS: phone /tts, laptop phonikud
```

In manual mode the transmit switch is off: control refuses every mission (HTTP 409 CONFLICT) and says so;
perception still answers. An emergency in manual mode sends /c/stop, never a halt that takes
stick control back from the RC.

## Verification

```bash
python3 -m pytest /root/groundstation/projects/integration_harden2/test/ -q         # every test (models faked)
HARDEN2_GPU_TESTS=1 python3 -m pytest /root/groundstation/projects/integration_harden2/test/test_perception2.py -q -k real_sam3   # the real SAM3 on the GPU
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

Panes (tmux windows): `keys` · `asr` · (`gst` + `dog` in dji mode) · `app` · `vlm` · (`mock` in mock
mode). The app starts Gemma 4 E4B (:18090) itself, through its process supervisor (gemma/server.py);
the `vlm` pane only shows Gemma's log.

External binaries: `build/release/shared/dji/bin/llm_to_action_{gstreamer_rx,asr_server,keyboard_hook}`.

---

# REAL FLIGHT — runbook (HUMAN runs every motor command)

**Status:** the old mock smoke script was deleted 2026-09-22 (it tested a retired English tier). The
webcam mock test is the next end-to-end check. **Never flown on real hardware.** Treat the first flight as a bring-up, not a demo.

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
# 2. verify the phone app reaches the aircraft (safe, read-only) -> expect aircraft JSON:
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
- **`stop` (EMERGENCY) preempts motion but does NOT kill motors.** It sends `dji.halt()` = POST /c/fly `[{"delay":0}]`: the running mission is cancelled and we KEEP virtual-stick control. Not a hover, not a motor-kill. To truly cut motors, use the phone/aircraft procedure in CLAUDE.md.
- **`manual` (OVERRIDE) fires `/c/stop` = `controller.stop(emergency=true)` and hands control to the RC.** In-air outcome depends on the drone's `FCUrgentStopMotorMode`. That OVERRIDE calls stop() at all is a known concern (it should relinquish only) — verify before trusting voice override in the air.
- **Indoors:** lateral/vertical moves do nothing (VPS). Reliable indoor intents: takeoff, spin, land.
- **A move step blocks ~1.5 s** — you cannot interrupt it by voice mid-move. The power button is your
  real-time cut.
- **dji-video (video/ros_stream.py) is not runtime-verified.** If 3b hangs waiting for frames, fall back to 3a.
- The assistant NEVER runs these against a real drone. It prepares them; the HUMAN runs them.


## Runtime switches

| env | values | meaning |
|---|---|---|
| `VIDEO` | `webcam` (retest default) / `dji` / `rtmp` | frame source; webcam = the retest default (owner ruling 2026-09-08), nothing connected |
| `CONTROL` | `mock` / `real` | phone-app target; the ONE decision — config derives DJI_HOST/PORT/REAL from it |
| `TTS_OUTPUTS` | `phone` (default) / `laptop` / `phone,laptop` / empty | speech out: every sentence goes to each listed output; empty = silent |
| `ASR_SOURCES` | `ros,phone` (default) / `ros` / `phone` | speech in: every listed source runs and feeds the recognizer |
| `SCENE_SEG` | `sam3` (default) / `omdet` | highlight backend: one SAM3-nf4 model (perception2), or the legacy OmDet+SAM2.1 (perception); with sam3, OmDet/SAM2.1 never load |
| `SCENE_SAM3_PERIOD` | seconds, default 1.0 | minimum gap between SAM3 forwards per phrase (the highlight worker runs every frame) |
| `RECORD` | `1` (default) / `0` | record the whole session (utterances + ASR clips) |

Perception tuning stays available as env overrides (`SCENE_HL_CONF`, `SCENE_HL_REL`,
`SCENE_DETECT_FLOOR`, `SCENE_COUNT_FRAMES`, `SCENE_COUNT_GAP`, ...); defaults live in config/.
Boot the desk stack with `VIDEO=webcam TTS_OUTPUTS= bash /root/groundstation/tools/desk-test/up.sh`
(sam3 is the default; no translator knob).


## Operator kill switch

**F4** toggles the manual override, from ANY window. The global keyboard hook (the "keys" process)
reads the key and the app gets it on /keyboard/in/raw (app/keys.py). A function key, not a letter:
letters are typed in other windows. First press = override ON (POST /c/stop = `stop(emergency)`: our
virtual-stick authority is relinquished, the RC flies; every motion verb is refused with 409). Next
press = re-arm. The HUD line turns red while the override is on. Code: control/flight.py, app/keys.py;
tests: test/test_control.py, test/test_app.py. Not yet pressed in a live session.
