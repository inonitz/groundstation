# llm_cv_scene — smart scene understanding: a spoken question -> live CV overlays + LLM/VLM description

Standalone Python/OpenCV app. **Not** wired into the C++ flight stack on purpose — it borrows the
models conceptually and keeps that tree clean. Proves the system is *smart*: you talk to it, it
describes your environment and highlights what you ask for, live.

## Architecture (fast eyes, slow brain)
- **Background eyes (real-time, every frame):** YOLO26-seg draws subtle always-on detections so the
  scene is visibly "being understood" at native FPS. Runs on a worker thread, rate-capped.
- **Highlight (on demand, open-vocab):** an open-vocab PHRASE grounder — **LLMDet-tiny**, loaded via
  the transformers MM-Grounding-DINO implementation — localizes whatever you asked for, including
  esoteric / small / *described* things ("the person in the black hat", "the small medallion").
  Optional **SAM2** turns the top box into a mask. This is the piece that replaced YOLOE, which could
  only find a bounded vocabulary.
- **Brain (on demand, ~1-3 s):** Qwen3-VL-4B on llama-server. Sees the frame + the detector's findings
  + your question; answers in natural language; and **resolves the referent** for the grounder (it
  turns "the guy with the hat" into a groundable noun phrase) plus gives its own one-shot box.
- **Ears:** your EXISTING pipeline, reused whole — the ROS2 `asr_node` (miniaudio mic + **press H to
  toggle** record on/off + sttserv backend) publishes transcripts on `/asr_server/transcribe`; this
  demo just subscribes via rclpy. No audio capture or STT is reimplemented here.

## Four colour-coded overlays
- grey    = background detections (subtle, YOLO26-seg)
- green   = grounded highlight of the requested object (LLMDet)
- magenta = SAM2 mask of the same object (the other selection method)
- amber   = the VLM's own one-shot grounding box

## Run
One command brings up VLM + keyboard hook + ASR node + the app (tmux windows: vlm | keys | asr | app):
```
./run_demo.sh
```
**Press H to start recording, press H again to stop + transcribe** (toggle, at the asr_node — its
global key listener owns the mic). Switch windows with `Ctrl-b 0/1/2/3`. **Detaching (`Ctrl-b d`) or
`Ctrl-C` shuts the whole demo down** (frees the GPU + mic) via cleanup(). Warm the VLM before you talk.

First-time setup on the box: `pip install -r requirements.txt` (or build the image with
`scripts/build-devenv.sh`, which bakes the deps AND pre-downloads the grounder weights for offline
use). Vision-only smoke test without voice: `python3 app.py`.

## Input source
Default is webcam 0. Override with `SCENE_INPUT`: a webcam index, a video-file path (test on a recorded
clip if the webcam is flaky), or a GStreamer pipeline for the drone stream (Phase 6):
`SCENE_INPUT='tcpclientsrc host=<phone-ip> port=5600 ! h264parse ! avdec_h264 ! videoconvert ! appsink'`

## Keys
In the window: `c` clear highlight · `t` toggle SAM2 · `b` toggle background · `x` clear chat · `q` quit.
Talk with **H at the asr_node** (press to start, press to stop).

## Portability (no platform hardcoded)
The VLM runs on **llama.cpp/Vulkan**, which works on any GPU vendor (AMD/NVIDIA/Intel). The detectors
and the grounder auto-detect their device: `config.resolve_device()` (Ultralytics) and
`config.resolve_torch_device()` (transformers) both treat a CUDA *or* ROCm/HIP GPU the same way, use
`mps` on Apple, and fall back to CPU. The grounder's deformable attention needs no CUDA-only kernel, so
its code path is identical on every backend. Move this to another machine, install the matching torch +
llama build, and the code is unchanged. Force devices with `SCENE_DEVICE=cpu|0|mps`.

Models: highlight grounder = **LLMDet-tiny** (`iSEE-Laboratory/llmdet_tiny`, open-vocab, 2025 SOTA on
rare classes) via transformers; background = `yolo26n-seg.pt`; mask = `sam2.1_b.pt`. Override the
grounder with `SCENE_GROUNDER` (e.g. an MM-Grounding-DINO checkpoint), background with `SCENE_BG`.

---
## Relationship to ../llm_cv_track  (2026-08-20)
This folder is the **BACKUP / proven demo**: voice -> Qwen3-VL describes + localizes -> SAM2. 100% local,
always loads, but the highlight is slow and static. **`../llm_cv_track` is the STAR**: same voice loop,
but the highlight is OmDet-Turbo (open-vocab, real-time, the box follows the object). llm_cv_track REUSES
this folder's `vlm.py`/`ears.py`/`eyes.py`/`config.py` unchanged. If the star wobbles live, run this.
Full details + all commands: `../llm_cv_track/README.md` and `../../docs/active/2026-08-20-demo-runsheet.md`.
