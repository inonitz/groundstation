# harden2 run arguments — what each one actually does (2026-09-10)

Read from the code (run_mvd.sh, run_llama_server.sh, mvd.py, recognizer/pipeline, perception,
and the desk-test wrappers), not from comments. Default in [brackets].

## Positional (run_mvd.sh VIDEO CONTROL; up.sh sets them for you)
- VIDEO [webcam]: webcam | dji | rtmp. Picks the video source. webcam -> a /dev/video device (WEBCAM_DEV);
  dji -> the phone's H.264 over the ROS gstreamer node; rtmp/drone -> an rtsp url.
- CONTROL [mock]: mock | real. mock -> REST to 127.0.0.1:8079. real -> the phone at 8080, HUMAN-ONLY,
  prompts you to type ARMED. The agent never runs real.

## System / which tree
- MVD_HOME [integration_harden] (up.sh/preflight/status): which project tree to boot. ALWAYS pass
  integration_harden2; the script default points at the dead tree.
- MVD_DRONE [set to 1 by run_mvd]: turns on the in-process drone router.

## Model, planner, translator
- MVD_PLANNER [gemma4]: gemma4 | qwen3vl. gemma4 = one Gemma 4 E4B for routing + planning + vision +
  Hebrew answers, thinking OFF. qwen3vl = the old Qwen3-VL-4B.
- MVD_TRANSLATOR [none]: none | hymt2 | dicta. none = Gemma reads Hebrew directly, NO translator server.
  hymt2/dicta start a translator window (the harden fallback; not used by harden2).
- SCENE_LLAMA_PORT [18090]: the Gemma/Qwen server port.
- MVD_XLATE_PORT [18091]: translator port (only if a translator runs).
- GEMMA4_THINK [unset]: 1 turns Gemma's thinking back on (default off). MVD_TRANSLATE_PROMPT [v1]: only
  used when a translator runs.

## Perception (mvd.py)
- SCENE_SEG [sam3]: sam3 | omdet. Segmentation backend. sam3 = one SAM3-nf4 (boxes+masks). omdet = old pair.
- SCENE_GATE [sam3]: sam3 | either | vlm. Highlight presence gate. sam3 = SAM3 decides; either = a SAM3
  hit overrides a Gemma "absent"; vlm = Gemma decides.
- SCENE_HL_TOPK [128]: max SAM3 boxes per query (was the hidden 8 cap).
- SCENE_HL_MAX [128]: max detections DRAWN per frame (was the hidden 3 cap).
- SCENE_HL_REL [0.65]: relative gate; keep only detections within this fraction of the top score. Lower
  it (0.45) for crowded scenes (many cars) so fainter instances still draw.
- SCENE_HL_CONF [0.30]: absolute minimum confidence to draw anything.
- SCENE_DETECT_FLOOR [0.12]: detector query threshold, kept low to see candidates.
- SCENE_MIN_BOX_FRAC [0.001]: drop boxes smaller than this fraction of the frame (speck filter).
- SCENE_COUNT_FRAMES [3] / SCENE_COUNT_GAP [0.3]: a count answer is the median of this many frames, this
  many seconds apart.
- SCENE_HL_GIVEUP [8.0]: seconds without a SAM3 hit before a highlight target is dropped ("לא מצאתי").
- SCENE_SAM3_PERIOD [1.0]: minimum seconds between SAM3 forwards (shares the GPU with Gemma + whisper).
- SCENE_BG [off]: off | a YOLO seg model path. Background grey-box detector; off saves ~282 MiB.
- SCENE_SAM2 [sam2.1_b.pt]: only used when SCENE_SEG=omdet.
- SCENE_INPUT [set from VIDEO]: the video source string CameraStream reads.

## Speech answers / TTS
- MVD_TTS [1]: 1 tries to bring up the phone TTS voice; 0 disables it. THIS is the real off switch.
- SCENE_TTS_LANG [he]: language for the phone's spoken answers.
- GOTCHA: SCENE_TTS is NOT read by anything. "SCENE_TTS=off" in old comments/commands is a NO-OP. To
  silence TTS use MVD_TTS=0. On the webcam with no phone, TTS is off anyway because the voice backend
  fails to attach, not because of any flag.

## Control wire (set by run_mvd from CONTROL)
- MVD_WIRE_HOST [127.0.0.1 mock | PHONE_IP real], MVD_WIRE_PORT [8079 | 8080], MVD_WIRE_REAL [empty | 1].
- PHONE_IP [derived from the default route]: the phone/hotspot gateway, used for real control AND as the
  gstreamer video source. Never hardcode it; it changes per hotspot session.

## Phone ASR channel
- MVD_PHONE_ASR [1]: listen for phone speech on 8080. MVD_PHONE_ASR_PORT [8080].

## ASR (whisper server)
- ASR_MODEL_PATH [whisper ivrit large-v3-turbo q5], ASR_BACKEND [whisper-whisper], ASR_LANGUAGE [he].
- ASR_CAPTUREID [unset = default mic]. ASR_RECORD [1] saves each utterance wav; ASR_RECORD_DIR = the
  session clips folder.

## Session, recording, logs
- MVD_SESSION_DIR: the session folder (utterances.jsonl + clips/). up.sh sets it; a direct run_mvd makes
  its own.
- MVD_SESSIONS_ROOT, DESK_TEST_RECORD [1], DESK_TEST_LOGDIR, TMPDIR: up.sh's session/log locations.

## Display / audio
- DISPLAY [:0]: X display for the app window. PULSE_SERVER [unix:/tmp/pulse-socket]: audio socket.

## Wrapper commands
- up.sh: boots the mock + the app for VIDEO with mock control. Reads VIDEO, WEBCAM_DEV, MVD_HOME, and
  passes the rest through.
- preflight.sh: checks models, cameras, and the stack before a boot. Reads MVD_HOME, MVD_TRANSLATOR,
  SCENE_SEG.
- status.sh [--watch [secs]]: one-shot health, or --watch streams the phone 503 gate (watch_503.sh).

## SCENE_TTS (voice-out) — valid values

`SCENE_TTS = phone | phonikud | espeak | piper | both | off` (default `phone`). An unrecognized value
(e.g. `on`) now prints a warning and falls to off. `phone` speaks via the phone's Android TextToSpeech
(needs cellular/Wi-Fi data). `phonikud` is the OFFLINE Hebrew voice: phonikud G2P (niqqud+stress -> IPA)
-> Piper onnx voice -> aplay; models default to /root/models/tts/phonikud/ (override with
SCENE_PHONIKUD_G2P / _VOICE / _CONFIG), installed by tools/devenv/install-runtime-deps.sh; falls back to
espeak if missing. `espeak` is a robotic last-resort fallback (bad Hebrew). `piper` needs a piper binary +
voice + aplay. Model license: phonikud voice is cc-nc -- demo/competition use only (see HISTORY 2026-09-16).
