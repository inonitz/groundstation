# llm_cv_track — voice-driven open-vocab perception (detect · segment · reason)

The "smart CV" stack for the demo: you **speak**, it **finds** what you named, **segments** it, and can
**describe/answer** questions about the scene. It is the successor to `../llm_cv_scene`, with the weak
highlight detector swapped for a proper real-time open-vocabulary detector.

## The two folders (read this first)
- **`../llm_cv_scene` (BACKUP, "the old demo").** Same voice loop, but the highlight is done by the VLM
  itself (Qwen3-VL returns a box) — slow (~seconds) and static. 100% local, no internet. It is the
  safety-net demo: it always loads.
- **`llm_cv_track` (STAR, this folder).** The highlight is done by **OmDet-Turbo** (open-vocab detector)
  which re-detects every frame, so the box **follows** the object, and it recognizes arbitrary described
  things (guitar case, headphones) that the old detectors missed. The VLM is freed to only answer questions.

Neither folder imports the other's app; `llm_cv_track` REUSES the frozen `llm_cv_scene` modules
(`vlm.py`, `ears.py`, `eyes.py`, `config.py`) via `sys.path`, so the backup is never modified.

## Quick start
Pre-warm once before any real run (first load compiles SAM2's GPU kernels):

    ASR_CAPTUREID=5 bash /root/groundstation/source/llm_cv_track/run_scene_omdet.sh          # webcam
    ASR_CAPTUREID=5 bash /root/groundstation/source/llm_cv_track/run_scene_omdet.sh rtmp     # drone (DJI RTMP)

`ASR_CAPTUREID=5` selects the C920 mic (the default device is the dead MOTU → empty transcripts).
Press **H**, speak, press **H**. Say: *"highlight the red backpack"* / *"what do you see"* / *"clear"*.
Quit with `q`/Esc in the window or `Ctrl-C` in the launcher — either tears the whole tmux session down.

Static image + prompt (no camera/voice):

    python3 /root/groundstation/source/llm_cv_track/recognize_omdet.py <image> "guitar case, headphones" --mask

## Programs
| file | what it is | run it with |
|---|---|---|
| **scene_omdet.py** | THE demo. Full chat-pane UI (like llm_cv_scene) + OmDet highlight + SAM2 masks + VLM Q&A. | `run_scene_omdet.sh` |
| **highlight_seg.py** | Same engine, minimal bottom-bar UI (lighter/faster). Also the shared OmDet+filter library that scene_omdet/recognize_omdet import. | `python3 highlight_seg.py --source 0 --target "…"` |
| **recognize_omdet.py** | Single-shot: still image + prompt → OmDet detect → SAM2 mask → annotated jpg + `_log.txt`. | see Quick start |
| **run_scene_omdet.sh** | One-command tmux launcher: auto-starts VLM · keyboard-hook · asr_server · app, each in its own pane. | `bash run_scene_omdet.sh [rtmp]` |
| **follow.py** | PARKED. Specific-object TRACKING: voice → VLM resolves the referent → BoT-SORT follows the track ID (+ colour-histogram re-acquisition). | `python3 follow.py --source 0 --command "…"` |
| **track.py** | PARKED. Pure BoT-SORT tracker playground (no brain), for trying detectors. | `python3 track.py --classes person` |
| **botsort_reid.yaml** | BoT-SORT config for follow.py (Re-ID on, longer track buffer). | — |

## What does what (models per program)
| program | voice→text | background | highlight (localize) | mask | reasoning/Q&A |
|---|---|---|---|---|---|
| scene_omdet / highlight_seg | Parakeet (asr_server) | YOLO26n-seg | **OmDet-Turbo** (open-vocab, follows) | SAM2.1-b | Qwen3-VL-4B (llama-server) |
| recognize_omdet | — | — | **OmDet-Turbo** | SAM2.1-b | — |
| follow (parked) | Parakeet | — | VLM resolves once → **BoT-SORT** tracks | SAM2 (opt) | Qwen3-VL |

## How it works (the pipeline)
1. **Ears** (`llm_cv_scene/ears.py`): subscribes to the ROS2 `asr_server`'s transcript topic. Press H →
   `asr_server` (Parakeet) records + transcribes → publishes text → `on_text(text)` fires.
2. **Intent** (`parse_highlight`): "highlight/find/track X" → sets the target phrase; "clear/stop" →
   drops it; anything else → a question routed to the VLM.
3. **Worker thread**: every loop it runs YOLO26n-seg (faint background boxes) and, if a target is set,
   **OmDet-Turbo** on the phrase → boxes. Then `_apply_masks` runs **SAM2.1** per box, drops whole-frame
   garbage masks, and tightens each box to its mask.
4. **VLM** runs OFF the ASR thread (so voice never blocks): a question → `vlm.ask()` → prose answer in
   the chat pane.
5. **Display thread** stays at camera FPS; the worker only updates overlays, so video is always smooth.

Re-detecting the phrase every frame is "tracking-by-detection": the highlight follows the object with no
dedicated tracker. Persistent identity through occlusion is `follow.py`'s job (parked).

## OmDet offline setup (IMPORTANT — why it used to hang)
OmDet-Turbo's Swin backbone is resolved from the HF Hub at load. On a throttled/again-and-again fetch it
**hangs forever** ("OmDet: loading"), and pure offline mode fails because transformers resolves the
null `backbone_config` via an HF API call. Fixed once, permanently, by vendoring a local copy:

- Local model: `/root/models/omdet-turbo-swin-tiny/` = the cached checkpoint **plus a `config.json`
  whose `backbone_config` was resolved online once and baked in** (`OmDetTurboConfig.save_pretrained`),
  with `use_pretrained_backbone=False`.
- `highlight_seg.OmDet` loads from that dir with `HF_HUB_OFFLINE=1`, `local_files_only=True`, and
  monkeypatches `timm.create_model(..., pretrained=False)` (the checkpoint already has the backbone
  weights). Result: **~1s load, zero network.** If the dir is missing it falls back to the hub (needs net).

To rebuild the local model (only if the folder is deleted): resolve `OmDetTurboConfig.from_pretrained(
"omlab/omdet-turbo-swin-tiny-hf")` online, `save_pretrained` it into the dir alongside the copied
checkpoint files.

## Strengths
- **Open-vocabulary, real-time.** Finds described/esoteric objects (guitar case 0.31, headphones 0.67,
  "the man on the left" 0.76) that YOLOE-2026 scored ~0 on. ~115 ms/detect (ROCm).
- **The box follows the object** (re-detected each frame) — not a static VLM snapshot.
- **Clean segmentation.** SAM2 masks are tight; whole-frame garbage masks are auto-dropped.
- **Voice never blocks** (VLM off-thread) and the display never drops below camera FPS (worker thread).
- **Apache-2.0 detector** (OmDet-Turbo) — off the AGPL path for the open-vocab layer.
- **Loads offline in ~1s** after the one-time local vendoring.

## Weaknesses / known issues
- **No temporal memory in the highlight.** Occlude a highlighted object and OmDet emits unstable
  low-confidence hits until it reappears. Persistent tracking is `follow.py` (parked; its colour-hist
  re-id is fragile with look-alikes → needs OSNet).
- **Colour-only re-id in follow.py.** Two people in similar colours get confused. Not gate/demo ready.
- **Ultralytics (YOLO26 background + SAM2 + BoT-SORT) is AGPL.** Swapping OmDet in does NOT fully escape
  AGPL; a permissive tracker + background detector are still needed for productization.
- **VLM Q&A on vague prompts.** `vlm.ask` (prose) is used, not `vlm.analyze` (JSON object list), because
  the latter can enter a repetition loop and dump raw JSON. Keep questions clear.
- **Startup cost.** First run loads YOLO+OmDet+SAM2 and compiles SAM2's ROCm kernels (~180 s cold, cached
  after). PRE-WARM before an audience.
- **Mic device.** Default capture is the dead MOTU → empty `""` transcripts. Always `ASR_CAPTUREID=5`.

## Performance (measured, ROCm RX 7900 GRE)
- OmDet-Turbo detect: ~115–160 ms/frame. SAM2 mask: ~150–300 ms/box (first call slower, kernel compile).
- Highlight update rate: ~1.5–3 Hz with masks on (top-k boxes), ~6–8 Hz box-only (`t` toggles masks).
  Display stays at camera FPS regardless (worker thread is decoupled).
- VLM (Qwen3-VL-4B on llama.cpp/Vulkan): ~3–4 s per describe/Q&A; server warm-start ~4 s.
- OmDet load: ~1 s offline (was: indefinite hang on HF).

## History
- `llm_cv_scene` (the backup) shipped first: voice → Qwen3-VL describes + grounds → SAM2. Judged strong
  on vision, weak on tech; the highlight was slow/static and YOLOE/LLMDet failed on esoteric objects.
- Forked here to fix the detector without risking the working demo. Tried YOLOE-2026 (bounded vocab,
  can't compose modifiers) and LLMDet (hallucinated on OOD) — both rejected.
- Phase-2 feel-test picked **OmDet-Turbo** (Apache, open-vocab, in transformers) over D-FINE (closed-set)
  and the repo-clone options OV-DEIM / D-FINE-seg. See `docs/active/2026-08-20-phase2-detector-feeltest.md`.
- `follow.py` explored specific-object tracking (BoT-SORT + colour re-id); parked as priority-2.
- Built `scene_omdet.py` (full UI) + `highlight_seg.py` (engine) + `recognize_omdet.py` (static).
- Hardened: clean exit (`os._exit(0)`, no core dump), VLM off the ASR thread, tmux teardown, and the
  OmDet local/offline load. See `docs/active/2026-08-20-*` and `docs/NOTES.md`.
