# harden2 run arguments — what each one does (rewritten 2026-09-18, after the knob collapse)

Read from the code (run.sh, mvd.py, config/). Default in [brackets]. The surface shrank a lot: what used
to be many env vars is now a handful of decisions; the rest are baked constants in config/constants.py.
This lists only what the USER can still set.

## Positional (run.sh up VIDEO CONTROL)
- VIDEO [webcam]: webcam | dji | rtmp. The video source. webcam -> /dev/video<WEBCAM_DEV>; dji -> the
  phone's H.264 over the ROS gstreamer node; rtmp -> an rtsp url. config derives the source from this.
- CONTROL [mock]: mock | real. THE ONE control decision. mock -> 127.0.0.1:8079. real -> the phone at
  <PHONE_IP>:8080, HUMAN-ONLY (run.sh prompts for ARMED). config derives host/port/real from it via
  wire_target(); DjiWire's loopback guard refuses a non-loopback host unless real. The agent never runs real.

## Run context
- WEBCAM_DEV [0]: which /dev/video device for VIDEO=webcam (0 = lid cam, 2 = C920).
- PHONE_IP [derived from the default route]: the phone/hotspot gateway; used for real control and the dji
  video source. Never hardcode; it changes per hotspot session. Export to force a value.
- RECORD [1]: record the session (utterances + clips). The only recording knob; the paths are constants.

## Voice out
- SCENE_TTS [phone]: phone | phonikud | off. THE ONLY TTS knob. phone -> the phone's Android TTS
  (Google he-IL, needs data). phonikud -> offline Hebrew on the laptop (crashes loud if its model is
  missing). off -> no voice. Hebrew only. Host, port, language, rate, timeout and the phonikud model
  paths are fixed constants, not env-tunable.

## Perception tuning
- SCENE_GATE [sam3]: sam3 | either | vlm. Highlight presence gate.
- SCENE_HL_REL [0.65]: relative gate; lower (0.45) for crowded scenes.
- SCENE_HL_GIVEUP [8.0]: seconds without a SAM3 hit before a highlight drops.
- SCENE_SAM3_PERIOD [1.0]: min seconds between SAM3 forwards (shares the GPU with Gemma + whisper).
- SCENE_COUNT_FRAMES [3] / SCENE_COUNT_GAP [0.3]: a count is the median of this many frames, this far apart.
- SCENE_HL_TOPK [128] / SCENE_HL_MAX [128]: SAM3 boxes per query / detections drawn per frame.
- SCENE_DETECT_FLOOR [0.12] / SCENE_HL_CONF [0.30]: detector query threshold / absolute draw floor.
- SCENE_MIN_BOX_FRAC [0.001]: speck filter.
- SCENE_BG [off]: off | a YOLO seg model path (background grey-box detector; off saves VRAM).
- SCENE_CONF_BG [0.35] / SCENE_IMGSZ [640] / SCENE_DEVICE [auto]: bg confidence / detector image size /
  compute device override.
- SCENE_SEG [sam3]: only sam3 is valid (the omdet path was deleted).
- SCENE_OPEN_TIMEOUT [180]: seconds to keep retrying a not-yet-live input (slated to become a startup
  readiness gate).

## Ears (ASR) — escape hatches
- ASR_MODEL_PATH [whisper ivrit large-v3-turbo q5], ASR_BACKEND [whisper-whisper], ASR_LANGUAGE [he],
  ASR_CAPTUREID [default mic].
- MVD_PHONE_ASR [1]: listen for phone speech. MVD_PHONE_ASR_PORT [8080].

## Brain / watchdog
- SCENE_LLAMA_URL [http://127.0.0.1:18090]: the Gemma server URL (rarely overridden).
- WATCHDOG_STALL_SEC [6] / WATCHDOG_RETRY_SEC [15]: no-frame stall threshold / reconnect retry interval.

## Now CONSTANTS (were knobs; edit config/constants.py or config/defaults.py, not env)
Voice host/port/lang/rate/timeout + phonikud paths; the control wire host/port/real (derived from CONTROL);
the video source string (derived from VIDEO); camera W/H, chat width, Hebrew font + size; input read-retry;
the trace dir; the SAM3 model + precision; the session/log paths (only RECORD stays a knob).

## Deleted entirely
MVD_DRONE (routing is unconditional), MVD_PLANNER (the app is gemma4-only; run_llama_server.sh still uses it
to pick which model to SERVE), MVD_TRANSLATOR / MVD_XLATE_PORT (no translator), GEMMA4_THINK, MVD_TTS (use
SCENE_TTS=off), SCENE_SAM3_PRECISION (the overlay shows the model name), SCENE_SEG=omdet + SCENE_SAM2.

## Internal (not user knobs)
MVD_SESSION_DIR (test hook), SCENE_TMUX_SESSION (run.sh<->window plumbing), DISPLAY, PULSE_SERVER,
HF_HUB_OFFLINE, TRANSFORMERS_OFFLINE.
