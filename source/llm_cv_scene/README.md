# llm_cv_scene — smart scene understanding: a spoken question -> live CV pipeline (YOLOE detect+seg) + LLM/VLM description of the surroundings

Standalone Python/OpenCV app. **Not** wired into the C++ flight stack on purpose — it
borrows the models conceptually, keeps the tree clean. Proves the system is *smart*:
you talk to it, it describes your environment and highlights what you ask for, live.

## Architecture (fast eyes, slow brain)
- **Eyes (real-time, every frame):** YOLOE draws always-on background detections, and on
  demand localizes a phrase ("the person in the blue shirt"). SAM2 (optional) turns that
  box into a tracked mask so you can compare the two selection methods.
- **Brain (on demand, ~1-3 s):** Qwen3-VL-4B on llama-server. Sees the frame + the
  detector's findings + your question; answers in natural language; names what to highlight
  and gives its OWN box guess (so you see VLM grounding vs the real-time detector).
- **Ears:** your EXISTING pipeline, reused whole -- the ROS2 `asr_node` (miniaudio mic +
  push-to-talk on H + sttserv backend) publishes transcripts on `/asr_server/transcribe`;
  this demo just subscribes via rclpy. No audio capture or STT is reimplemented here.

## Four colour-coded overlays
- grey    = YOLOE background detections (subtle)
- green   = YOLOE real-time highlight of the requested object
- magenta = SAM2 mask of the same object (the other tracker)
- amber   = the VLM's own one-shot grounding box

## Run
One command brings up VLM + keyboard hook + ASR node + the app (tmux windows: vlm | keys | asr | app):
```
./run_demo.sh
```
**Hold H** to talk (keyboard_hook -> /keyboard/in/raw -> asr records on H press..release). Switch windows with `Ctrl-b 0/1/2/3`. **Detaching (`Ctrl-b d`) or `Ctrl-C` shuts the whole demo down** (frees the GPU + mic) via cleanup(). Warm the VLM (vlm window) before you talk.

First-time setup on the box: `pip install -r requirements.txt` (or just build the image with
`scripts/build-devenv.sh`, which bakes it). Vision-only smoke test without voice: `python3 app.py`.


## Input source
Default is webcam 0. Override with `SCENE_INPUT`: a webcam index, a video-file path (test on a
recorded clip if the webcam is flaky), or a GStreamer pipeline for the drone stream (Phase 6):
`SCENE_INPUT='tcpclientsrc host=<phone-ip> port=5600 ! h264parse ! avdec_h264 ! videoconvert ! appsink'`

## Keys
In the window: `c` clear highlight · `t` toggle SAM2 · `b` toggle background · `q` quit.
Talk with **H at the asr_node** (its global key listener owns push-to-talk).

## Status
Portable by design -- no platform is hardcoded. The VLM runs on **llama.cpp/Vulkan**, which
works on any GPU vendor (AMD/NVIDIA/Intel). The detector auto-detects its device via
`config.resolve_device()` -- a CUDA *or* ROCm/HIP GPU shows up the same way, Apple uses mps,
and it falls back to CPU. Move this to another machine, install the matching torch + llama build
for that box, and the code is unchanged. Force a device with `SCENE_DEVICE=cpu|0|mps`.
Models: open-vocab highlight = YOLOE-26 (yoloe-26l-seg.pt, the 2026 model); background = yolo26n-seg.pt. Override via SCENE_OPENVOCAB / SCENE_BG.
