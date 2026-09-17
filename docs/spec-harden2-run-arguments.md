# harden2 run arguments — what each one actually does (2026-09-10)

Read from the code (run.sh, run_llama_server.sh, mvd.py, recognizer/pipeline, perception,
and the desk-test wrappers), not from comments. Default in [brackets].

## Positional (run.sh up VIDEO CONTROL)
- VIDEO [webcam]: webcam | dji | rtmp. Picks the video source. webcam -> a /dev/video device (WEBCAM_DEV);
  dji -> the phone's H.264 over the ROS gstreamer node; rtmp/drone -> an rtsp url.
- CONTROL [mock]: mock | real. mock -> REST to 127.0.0.1:8079. real -> the phone at 8080, HUMAN-ONLY,
  prompts you to type ARMED. The agent never runs real.

## System / which tree
- MVD_HOME [integration_harden2] (bench/score only): which tree the bench imports in place; run.sh
  hardcodes harden2, so you never pass this to run the app.
- MVD_DRONE [set to 1 by run.sh]: turns on the in-process drone router.

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
- MVD_TTS [1]: 1 brings up the TTS voice (backend = SCENE_TTS); 0 disables it. THIS is the master off switch.
- SCENE_TTS [phone]: selects the voice backend (see the SCENE_TTS section below). run.sh forwards it to the
  app now; earlier builds did not, so old "SCENE_TTS=..." run.sh commands were no-ops (fixed 2026-09-17).
- SCENE_TTS_LANG [he]: language for the spoken answers.
- To silence TTS use MVD_TTS=0. On the webcam with no phone, use SCENE_TTS=phonikud for an offline Hebrew
  voice; SCENE_TTS=phone needs a reachable phone (and the phone needs data for Google TTS).

## Control wire (set by run.sh from CONTROL)
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
- MVD_SESSION_DIR: the session folder (trace.jsonl + asr_clips/). run.sh sets it; a direct run makes
  its own.
- MVD_SESSIONS_ROOT, DESK_TEST_RECORD [1], DESK_TEST_LOGDIR, TMPDIR: run.sh's session/log locations.

## Display / audio
- DISPLAY [:0]: X display for the app window. PULSE_SERVER [unix:/tmp/pulse-socket]: audio socket.

## Wrapper commands
- up.sh: boots the mock + the app for VIDEO with mock control. Reads VIDEO, WEBCAM_DEV, MVD_HOME, and
  passes the rest through.
- preflight.sh: checks models, cameras, and the stack before a boot. Reads MVD_HOME, MVD_TRANSLATOR,
  SCENE_SEG.
- status.sh [--watch [secs]]: one-shot health, or --watch streams the phone 503 gate (watch_503.sh).

## SCENE_TTS (voice-out) — valid values

`SCENE_TTS = phone | phonikud | off` (default `phone`). An unrecognized value prints a warning and falls
to off. We speak Hebrew ONLY. `phone` speaks via the phone's Android TextToSpeech (Google he-IL; needs
data). `phonikud` is the OFFLINE Hebrew voice: phonikud G2P (niqqud+stress -> IPA) -> Piper onnx voice ->
aplay; models default to /root/models/tts/phonikud/ (override with SCENE_PHONIKUD_G2P / _VOICE / _CONFIG),
installed by tools/devenv/install-runtime-deps.sh. If SCENE_TTS=phonikud and the model is missing the app
CRASHES (fail loud, no silent fallback). espeak/piper were removed (add a SOTA English voice back if ever
needed). The phonikud voice is cc-nc -- demo/competition use only.
