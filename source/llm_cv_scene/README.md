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

## Run (on the GPU box)
1. `pip install -r requirements.txt`  (torch = ROCm build for the RX 7900, or CPU)
2. `source /opt/ros/<distro>/setup.bash`  (so rclpy + std_msgs are importable)
3. VLM runs on **Vulkan** already (run_llama_server.sh). Start your **asr_node** (mic + H push-to-talk + sttserv -> /asr_server/transcribe)
4. `./run_llama_server.sh`  (warm it once with a throwaway query)
5. `python app.py`

## Keys
In the window: `c` clear highlight · `t` toggle SAM2 · `b` toggle background · `q` quit.
Talk with **H at the asr_node** (its global key listener owns push-to-talk).

## Status
Portable by design -- no platform is hardcoded. The VLM runs on **llama.cpp/Vulkan**, which
works on any GPU vendor (AMD/NVIDIA/Intel). The detector auto-detects its device via
`config.resolve_device()` -- a CUDA *or* ROCm/HIP GPU shows up the same way, Apple uses mps,
and it falls back to CPU. Move this to another machine, install the matching torch + llama build
for that box, and the code is unchanged. Force a device with `SCENE_DEVICE=cpu|0|mps`.
YOLOE-26 weights swap in via SCENE_YOLOE_* env vars.
