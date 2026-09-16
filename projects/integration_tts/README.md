# integration/ — the MVD, in one folder

Voice → 4-tier router → {simple verbs fly the drone | complex queries → perception},
shown over the live drone footage. Per `docs/integration-mvd-2026-08-24.md`. Python talks
straight to the frozen ApiServer wire — no C++ FMU engine in the loop.

## Data flow
```
H key (llm_to_action_keyboard_hook)  ·  asr_server (Parakeet → /asr_server/transcribe)
        └── ears.py ──► router.py (4-tier) ──► dji_wire.py ──► phone ApiServer :8080
                                    └── COMPLEX ──► scene_omdet.py (OmDet+SAM2+Qwen VLM)

video:  llm_to_action_gstreamer_rx --dji  ──►  ROS2 topic  camera/stream
                                              └── camera_stream.py (CameraStream) ──► scene_omdet
```

## Files (self-contained; copied from the old scattered projects)
- **router.py / commands.py / dji_wire.py** — 4-tier classify + the frozen wire (tested green on mock).
- **run_router.py** — headless router entrypoint (ASR → router, no display).
- **scene_omdet.py** — the perception app (Tier-2 COMPLEX); imports the router in-process.
- **highlight_seg.py** — OmDet-Turbo + SAM2 shared lib; `open_capture("ros")` → CameraStream.
- **camera_stream.py** — subscribes to `camera/stream`, exposes a cv2.VideoCapture-like reader. ← the video path.
- **config.py / vlm.py / eyes.py / ears.py / voice.py** — frozen perception/VLM/ASR-bridge/TTS modules.
- **run_mvd.sh** — tmux launcher (vlm · keys · asr · gst[dji] · app).

## External (built binaries + infra, not source):
- `build/release/shared/dji/bin/`: `llm_to_action_{gstreamer_rx,asr_server,keyboard_hook}`.
- `./run_llama_server.sh` — Qwen VLM server (:18090).

## Run
```
# mock (safe, agent-testable):
bash run_mvd.sh webcam mock
# real drone video + real control (HUMAN-only, aircraft SECURED):
PHONE_IP=<ip> bash run_mvd.sh dji real
```
`dji` video now flows gstreamer_rx → camera/stream → CameraStream (sole :5600 client, no conflict).

---

# REAL FLIGHT — runbook (HUMAN runs every motor command)

**Status:** control path tested against the mock (20-command sweep, all 4 tiers, `test_router.py` 6/6).
**Never flown on real hardware.** Treat the first flight as a bring-up, not a demo.

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
PHONE_IP=<PHONE_IP> bash /root/groundstation/projects/integration/run_mvd.sh webcam real
# 3b. Full demo (drone footage via gstreamer_rx -> camera/stream): use once 3a works
PHONE_IP=<PHONE_IP> bash /root/groundstation/projects/integration/run_mvd.sh dji real
#     -> type ARMED, then press H to talk
```

## Voice verbs
- `take off` · `land` (discrete POSTs)
- `go up/down` · `go forward` · `back up` · `go left` · `go right` (0.5 m/s, 1.5 s bounded nudge)
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

---

## Voice command reference (ASR -> DjiWire -> DJI POST)

Definitive, current reference. Same pipeline for laptop mic (press H) and phone ASR (`POST :8080/input`).
Source of truth: `projects/integration/commands.py` (patterns) + `router.py` (dispatch) + `dji_wire.py`.
Full context: `docs/active/2026-08-25-mvd-integration-handoff.md`.

## Tiers (checked first, length-INDEPENDENT)

| Say (any of) | Router → DjiWire | DJI Backend POST |
|---|---|---|
| stop · halt · abort · freeze · kill · cut · emergency · mayday | `halt()` | `POST /c/fly [{"type":"delay","seconds":0}]` |
| manual · override · take over · i have control · my control · disengage | `stop()` + mode→manual | `POST /c/stop` |
| resume · auto · autonomous · you have control · take control | mode→auto | *none (our state)* |

## BASIC verbs (only if ≤ 4 words)

| Say | Router → DjiWire | DJI Backend POST |
|---|---|---|
| takeoff · take off · fly · liftoff · sky · wakeup | `takeoff()` | `POST /c/takeoff` |
| land · landing · perch · floor · ground | `land()` | `POST /c/land` |
| spin · spin around | `spin_by(360)` | `POST /c/fly [{spin_by, degrees:360}]` |
| scan | `scan_ground(OUTWARDS)` | `POST /c/fly [{scan_ground, facing:"OUTWARDS"}]` |
| search · recon | `scan_ground(INWARDS)` | `POST /c/fly [{scan_ground, facing:"INWARDS"}]` |
| forward · forwards · go forward | `fly_by(dx:+1)` | `POST /c/fly [{fly_by, dx:1.0, velocity:2.0}]` |
| back · backward · backwards · back up | `fly_by(dx:-1)` | `POST /c/fly [{fly_by, dx:-1.0, velocity:2.0}]` |
| right · rightward(s) | `fly_by(dy:+1)` | `POST /c/fly [{fly_by, dy:1.0, velocity:2.0}]` |
| left · leftward(s) | `fly_by(dy:-1)` | `POST /c/fly [{fly_by, dy:-1.0, velocity:2.0}]` |
| up · rise · high | `fly_by(dz:+1)` | `POST /c/fly [{fly_by, dz:1.0, velocity:2.0}]` |
| down · under · low | `fly_by(dz:-1)` | `POST /c/fly [{fly_by, dz:-1.0, velocity:2.0}]` |
| look / watch / track (at) me / us | `track_me()` | `POST /c/fly [{track_me}]` |
| follow · follow me · follow him | `follow_me()` | `POST /c/fly [{follow_me}]` |
| come back · come home · return home · go home | `go_home_to_user()` | `POST /c/fly [{home}]` |
| look/camera/face forward · ahead · straight | `gimbal_pitch(0)` | `POST /c/fly [{gimbal_pitch, angle:0}]` |
| look/camera/gimbal down | `gimbal_pitch(-60)` | `POST /c/fly [{gimbal_pitch, angle:-60}]` |
| look/camera/gimbal up | `gimbal_pitch(30)` | `POST /c/fly [{gimbal_pitch, angle:30}]` |
| hello · hey · hi · heya · hiya · wave · how are you · how's it going | `wave()` | `POST /c/fly [{wave}]` |
| go / move / head + **no valid direction** | `unknown_move` | *no-op + "didn't catch a direction" (never scene-describe)* |

## COMPLEX (anything else, or > 4 words)

→ **perception** (Qwen-VL + OmDet/SAM2 on the laptop). **No drone POST.**
Answer is split: **LONG → screen (`Scene:`)** and **SHORT → phone `/tts` + laptop espeak + screen (`Spoken:`)**.
Examples: "what do you see", "how many windows", "highlight the red backpack", "show me all the windows".

## Notes
- Length guard: BASIC verbs only fire on ≤ 4 words (`MVD_MAX_CMD_WORDS`). Tiers ignore length.
- Tunables (router): `move_m=1.0` m, `move_vel=2.0` m/s, `spin_deg=360`.
- `stop` = `delay:0` preempts current motion AND keeps our stick control (`controller.fly` re-`takeControl`s);
  it is NOT `/c/stop`, and it no longer latches manual.
- Indoors only yaw/gimbal/vertical/spin/wave/takeoff/land are reliable; `fly_by`/`scan`/`track`/`follow`/
  `come_home` need GPS/VPS (outdoor). Gimbal is currently broken BACKEND-side (`fly_by` works).
- Every dispatch logs `[dji] POST <path> {body} -> HTTP <code>` in the app pane / `/tmp/mvd_app.log`.

## Exact wire JSON (the `[{...}]` shorthand above expands to this)
`POST /c/fly` body is a mission array with a `type` discriminator per action:
```
POST /c/fly    {"mission": [ {"type": "<name>", ...fields} ]}
```
So the shorthand maps to the literal payloads:
- spin        → `{"mission":[{"type":"spin_by","degrees":360.0}]}`
- scan        → `{"mission":[{"type":"scan_ground","radius":3.0,"velocity":4.0,"facing":"OUTWARDS","clockwise":true}]}`
- search      → `{"mission":[{"type":"scan_ground","radius":3.0,"velocity":4.0,"facing":"INWARDS","clockwise":true}]}`
- forward     → `{"mission":[{"type":"fly_by","dx":1.0,"dy":0.0,"dz":0.0,"velocity":2.0}]}`  (dx/dy/dz per direction)
- track       → `{"mission":[{"type":"track_me","fovTolerance":17.0}]}`
- follow      → `{"mission":[{"type":"follow_me","cruiseHeight":7.0,"followDistance":3.5,"maxVelocity":8.0}]}`
- come home   → `{"mission":[{"type":"home","maxVelocity":4.0}]}`
- gimbal      → `{"mission":[{"type":"gimbal_pitch","angle":-60.0}]}`  (0 / -60 / 30)
- wave        → `{"mission":[{"type":"wave","count":2}]}`
- stop        → `{"mission":[{"type":"delay","seconds":0.0}]}`
Discrete (not `/c/fly`): takeoff → `POST /c/takeoff` (empty body); land → `POST /c/land`; manual → `POST /c/stop`.
Content-Type: application/json. Enum values (`facing`, etc.) serialize by NAME.
