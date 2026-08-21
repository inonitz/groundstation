# Gate readiness + next steps (2026-08-20, gate ~18:00)

## Two demos, both validated headless
### STAR -- source/llm_cv_track/scene_omdet.py  (NEW, the impressive one)
Full llm_cv_scene experience (native video + chat pane + legend + voice) but the open-vocab HIGHLIGHT is
**OmDet-Turbo (Apache) -> SAM2.1 masks**, replacing the broken YOLOE/LLMDet.
- Voice "highlight the guitar case" -> OmDet detects it every frame (box follows) -> SAM2 masks it.
- Voice "what do you see / how many people" -> Qwen3-VL answers in the chat pane.
- **Validated headless:** full pipeline runs (background + OmDet highlight + SAM2 mask + chat canvas
  1023x1483 rendered -> scratchpad/phase2/out/star_canvas.jpg). Webcam 10/10 frames. Compiles clean.
  Open-vocab accuracy confirmed earlier on the esoteric set (guitar case, headphones, pendant, hat-person).
- **Clean exit:** os._exit(0) after teardown -> no core dump / no exit-144 (the torch/ROCm teardown crash).
- Also: source/llm_cv_track/highlight_seg.py = same engine, simpler bottom-bar UI (lighter/faster).

### BACKUP -- source/llm_cv_scene/  (the proven VLM demo, the floor)
- All modules compile; run_demo.sh / run_llama_server.sh present; weights present; backend=vlm.
- **VLM verified:** fresh llama-server up in 4s (warm), analyze 3.5s -> correct answer, ground 3s -> box.
- Untouched by any of today's work. This is the guaranteed pass if the star wobbles live.

## The ONE thing not verified: live test (needs a human in frame)
- Star, webcam:  python3 /root/groundstation/source/llm_cv_track/scene_omdet.py --source 0 --target "guitar case"
- Star, drone+voice:  bash /root/groundstation/source/llm_cv_track/run_scene_omdet.sh   (asr_node in another pane)
- Backup:  the existing run_demo.sh path.

## Known risks to manage at the gate
1. **Occlusion:** OmDet re-detects each frame with no memory -> an occluded object gives unstable
   low-confidence hits. Demo distinctive, mostly-unoccluded objects. Real fix = priority-2 tracker (parked).
2. **Startup is slow cold:** first run loads YOLO+OmDet+SAM2 and compiles SAM2's ROCm kernels (~180s the
   first time, cached after). **Pre-warm the app + pre-launch llama BEFORE the judges are watching.**
3. **Stale llama-server bricks startup:** if you ever see "llama-server is starting; waiting..." hang,
   run  pkill -f llama-server  and relaunch. (ensure_server waits on a hung process instead of relaunching
   -- didn't patch the frozen vlm.py to avoid risking the backup.)
4. **Highlight update rate:** OmDet ~150ms + SAM2 per box -> ~1.5-3 Hz for box+mask (display stays at
   camera FPS). Press 't' to drop masks for a fast box-only follow (~6-8 Hz). Prefer single-object highlights.

## Recommendation (decide when you're back)
- **Star as headline IF it live-tests clean; backup as the safety net.** The star is the real jump: it
  fixes exactly the esoteric-object + mask failures the mid-term was dinged for, live and voice-driven.
- Demo arc: "what do you see" (VLM understanding) -> "highlight the <distinctive object>" (OmDet finds it,
  SAM2 segments it, box follows) -> shows understanding + open-vocab localization + segmentation, all by voice.
- Pre-warm everything ~10 min before. Keep the backup one keystroke away.

## After the gate (priority-2, parked)
- Specific-object TRACKING through occlusion = real Re-ID (OSNet), not colour histogram. follow.py is the start.
- Full AGPL escape = replace the Ultralytics tracker too (D-FINE/OmDet detectors alone don't do it).
