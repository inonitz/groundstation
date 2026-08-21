# DEMO RUN-SHEET (2026-08-20)  --  all commands + what-does-what

## 0. Pre-flight (do BEFORE judges -- first load ~180s, warms the caches)
    ASR_CAPTUREID=5 bash /root/groundstation/source/llm_cv_track/run_scene_omdet.sh
  Let the window open + "OmDet ready", say one command, then quit (q). Now real runs are fast.
  MIC: device 5 = C920 (works). Default is the dead MOTU -> empty transcripts. Always pass ASR_CAPTUREID=5.

## 1. LIVE demos
### STAR -- scene_omdet (OmDet open-vocab highlight, box follows)
  webcam:  ASR_CAPTUREID=5 bash /root/groundstation/source/llm_cv_track/run_scene_omdet.sh
  drone:   ASR_CAPTUREID=5 bash /root/groundstation/source/llm_cv_track/run_scene_omdet.sh rtmp
### BACKUP -- llm_cv_scene (VLM does the highlight; fully offline-safe)
  webcam:  ASR_CAPTUREID=5 bash /root/groundstation/source/llm_cv_scene/run_demo.sh
  drone:   ASR_CAPTUREID=5 bash /root/groundstation/source/llm_cv_scene/run_demo_rtmp.sh

Drone order: run the script -> switch to app pane (Ctrl-b 4) -> wait for "waiting for input rtsp..." ->
THEN hit "Go Live" in DJI Fly (Custom RTMP = the URL it printed). Drone image in window = connected.
Say (press H before + after each):  "highlight the red backpack"  /  "what do you see"  /  "clear"
Quit: q or Esc in the window, OR Ctrl-C in the launcher = full shutdown.

## 2. STATIC image + prompt tools (feed imagery, get boxes/masks)
### OmDet (STAR engine, fast, open-vocab):
  python3 /root/groundstation/source/llm_cv_track/recognize_omdet.py <image> "guitar case, headphones" --mask
### VLM (Qwen3-VL describes + localizes):
  python3 /root/groundstation/source/llm_cv_scene/recognize.py <image> "the person wearing a hat" --mask
  Both write <image>_omdet.jpg / <image>_annotated.jpg + a matching _log.txt. Add --show to open a window.

## 3. WHAT DOES WHAT (per program)
### scene_omdet.py (STAR, live)
  Parakeet ASR (asr_server)  -> voice to text
  YOLO26n-seg (Ultralytics)  -> always-on background boxes
  OmDet-Turbo                -> voice-triggered highlight, open-vocab, re-detects each frame (box follows)
  SAM2.1-b                   -> mask on the highlighted box
  Qwen3-VL-4B (llama-server) -> "what do you see" / Q&A only
### llm_cv_scene/app.py (BACKUP, live)  -- same EXCEPT:
  Qwen3-VL-4B                -> does BOTH the highlight localization (returns the box) AND Q&A (slow, static box)
  (no OmDet.)  YOLO bg + SAM2 + Parakeet identical.
### recognize_omdet.py (STATIC, star engine)
  OmDet-Turbo -> detect prompt in the image;  SAM2.1-b -> mask;  no ASR, no VLM. image+prompt -> jpg+log.
### recognize.py (STATIC, VLM)
  Qwen3-VL-4B -> describe + localize the prompt;  SAM2.1-b -> mask;  no ASR, no OmDet. image+prompt -> jpg+log.
### highlight_seg.py  = scene_omdet's engine with a minimal bottom-bar UI (same models, no chat pane).
### follow.py / track.py = PARKED (specific-object tracking: BoT-SORT + colour re-id / pure tracker). Not for the gate.

## 4. Gotchas
- ASR empty ("") transcripts -> wrong mic. Use ASR_CAPTUREID=5. Speak clearly, hold H the whole sentence.
- Star (OmDet) needs internet AT LOAD (fetches its Swin backbone). Backup is 100% local -> use it if offline.
- "highlight X" = OmDet (fast, safe). Full questions = VLM. Avoid vague 1-word utterances to the VLM.
- Black window / "waiting" on drone -> DJI not Go Live, wrong IP, different WiFi, or missing the 'rtmp' arg.
