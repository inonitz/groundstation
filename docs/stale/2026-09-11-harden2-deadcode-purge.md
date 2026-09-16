# harden2 dead-code purge (2026-09-11)

Owner ruling: KEEP the YOLO26 background detector path (may be recycled). Delete the rest of the old
4-model stack, ONLY in projects/integration_harden2: OmDet, SAM2.1, the DictaLM/Hy-MT2 translators, and
the Qwen3-VL planner. Then a thermo-nuclear code-quality review of harden2.

## What is deleted
- Translator path: pipeline.handle_translated/_translate/_plan (Qwen planner) + plan_fn/dicta_port/DIRECT;
  llama.MODELS dicta/hymt2/qwen3vl; scene_omdet's pipe._translate overlay wrap; run_mvd translator + xlate
  window + MVD_PLANNER=qwen3vl + SCENE_SEG=omdet options.
- OmDet + SAM2: perception/detectors.OmDet class, Eyes._ensure_sam + Eyes.mask_for_box (SAM2); scene_omdet
  OmDet import + build_highlight omdet branch; config.SAM2_WEIGHTS.
- perception2 dead duplicates: detectors.py, engine.py, vlm_client.py, chain_demo.py (the app uses
  perception2.concept/counting/sam3_backend only); perception2/__init__ trimmed to the live exports.
- Dead-path tests: the translated-path + omdet cases in test_recognizer.py / test_scene_wiring.py (the
  direct path is covered by test_pipeline_direct.py).

## KEPT (do NOT delete)
- YOLO26 background: perception/detectors.Eyes (__init__/_dets/background), config.BG_SEG_MODEL/CONF_BG/
  DETECT_IMGSZ, run_mvd SCENE_BG.
- The active chain: recognize_direct, Pipeline.handle_direct/_plan2, UNIFIED_* + REVISED_PROMPT +
  PLANNER_SHOTS_D (UNIFIED_PROMPT is built from REVISED_PROMPT; the echo guard uses PLANNER_SHOTS_D).

## Deferred to the nuclear review (harmless, entangled)
- prompts.py dead strings (TRANSLATE_*, TGEMMA_*, PURPOSE_*, WIRE_GRAMMAR, LINE_GRAMMAR, PLANNER_SHOTS_D_HE):
  unused module-level strings; some feed write_prompts_md. The review catalogs them for a safe follow-up.
- recognizer.recognize() (the non-direct entry): unused once the translated path is gone; review flags it.

## Files for the OWNER to delete (agent cannot run rm/git)
    git rm projects/integration_harden2/recognizer/run_dicta_server.sh
    git rm projects/integration_harden2/recognizer/run_hymt2_server.sh
    git rm projects/integration_harden2/perception2/detectors.py
    git rm projects/integration_harden2/perception2/engine.py
    git rm projects/integration_harden2/perception2/vlm_client.py
    git rm projects/integration_harden2/perception2/chain_demo.py
(The agent empties these of live references first; then these files have zero importers.)

## STATUS: DONE (2026-09-11), behaviour-preserving
- pipeline.py rewritten to the direct path only (handle_direct + _plan2); handle_translated/_translate/
  _plan/plan_fn/dicta_port/DIRECT removed. Bench (tag purge-stage1): 410/487, 0 changed cases vs baseline.
- llama.MODELS trimmed to gemma4; QWEN3VL_EXTRA removed; bench.py PLANNERS de-qwen3vl'd (collateral repair).
- perception/detectors.py = Eyes only (YOLO26 background KEPT); OmDet class + Eyes._ensure_sam + SAM2
  mask_for_box removed. config.SAM2_WEIGHTS removed. scene_omdet: OmDet import + build_highlight omdet
  branch + _translate overlay wrap removed; OM name = "SAM3"; headers de-omdet'd.
- perception2/__init__ trimmed to the live exports (Sam3Backend + concept + counting); engine/vlm_client/
  detectors/build_engine dropped. perception/engine.py comments de-omdet'd. run_mvd.sh stripped of the
  translator/xlate window + MVD_PLANNER/MVD_TRANSLATOR/MVD_XLATE_PORT/SCENE_SAM2 exports + the omdet option.
- Tests: dead translated-path + omdet cases removed; test_scene_wiring rewritten to the direct path
  (plan2 fake). 60 offline tests pass; scene_omdet/perception2/config/Pipeline all import; golden-master 2/2.
- The 4 dead files below have ZERO live importers (verified) -> the OWNER's git rm list above stands.
