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

## Pre-flight (all required — see docs/active/kill-switch-verification.md)
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
PHONE_IP=<PHONE_IP> bash /root/groundstation/source/integration/run_mvd.sh webcam real
# 3b. Full demo (drone footage via gstreamer_rx -> camera/stream): use once 3a works
PHONE_IP=<PHONE_IP> bash /root/groundstation/source/integration/run_mvd.sh dji real
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
