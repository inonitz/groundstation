# SAM3 Integration Handoff (written 2026-09-03 23:28, pre-compaction)

Self-contained brief for the LAST TWO TASKS. Read this fully before working. Everything needed is
here so nothing is re-discovered or invented after context compaction.

## The two tasks (owner-authorized 2026-09-03)
1. **Integrate SAM3-nf4** as the unified replacement for OmDet (detection) + SAM2.1 (masks) in the
   perception path.
2. **Build the VLM -> concept -> SAM3 front-end** (SAM3 needs bare concepts, not instructions).

## Decisions in force (owner-ruled)
- ADOPT SAM3 int4-nf4 as the unified detector+masker. It beats the current OmDet+SAM2.1 on
  detection, equals it on masks, and uses less VRAM.
- SAM3.1 video TRACKING is SHELVED. Not achievable on the 8 GiB Blackwell (RTX 5070) GPU: weight
  quantization does not reduce the tracking peak (bottleneck is activation/state memory), and true
  int4-compute kernels (gemlite) are blocked by the repo's mixed-precision forward. Needs a
  Hopper-class GPU or a dedicated gemlite-integration effort. DO NOT pursue it now.
- Do NOT benchmark against bf16 SAM3 (never a production target).
- Full evidence: tools/bench/sam3-mask-bench/RESULTS.md (readable) and README.md (scorecard).

## Measured evidence (do NOT re-run; cite from here)
- Clean VRAM (isolated, torch peak): OmDet 582 + SAM2.1 691 = 1273 MiB; SAM3 bf16 2006; SAM3 nf4 886.
  So SAM3-nf4 unified (886) < the current pair (1273).
- Detection vs OmDet on 17 images: SAM3 332 detections vs OmDet 101; OmDet finds 0 windows, SAM3 26/47.
- Mask IoU vs SAM2.1 (same boxes): mean 0.862.
- Latency: bf16 p50 345 ms, nf4 p50 366 ms (RTX 5070). Detection is on-demand (the "highlight"
  keyword), so ~0.4 s/call is acceptable; do NOT run per-frame.
- SAM3 is a CONCEPT segmenter: instruction prompts ("Highlight all the people...") return 0; bare
  concepts ("person","window","car") work and are exhaustive. It will NOT generalize "vehicle"->van
  or "car"->van; the front-end MUST emit explicit class-synonym sets.

## SAM3 model + how to load and run (VERIFIED WORKING)
- Model dir (mounted, survives rebuild): /root/models/vision/sam3-official  (facebook/sam3, transformers-native)
- Deps (scripted in tools/bench/sam3-mask-bench/setup.sh): onnx ml_dtypes ftfy wcwidth regex
  bitsandbytes accelerate (bnb nf4 REQUIRES accelerate). Also bake into tools/devenv/Dockerfile.
- Load nf4:
    import torch
    from transformers import Sam3Model, Sam3Processor, BitsAndBytesConfig
    q = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                           bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
    model = Sam3Model.from_pretrained("/root/models/vision/sam3-official",
                                      quantization_config=q, dtype=torch.bfloat16).eval()   # bnb places it on GPU; do NOT call .to("cuda")
    processor = Sam3Processor.from_pretrained("/root/models/vision/sam3-official")
- Inference (text -> boxes + masks + scores, one call does BOTH detect and mask):
    from PIL import Image
    pil = Image.fromarray(frame_bgr[:, :, ::-1])            # engine passes cv2 BGR; SAM3 wants RGB PIL
    inputs = processor(images=pil, text=concept, return_tensors="pt").to("cuda")
    inputs["pixel_values"] = inputs["pixel_values"].to(torch.bfloat16)
    with torch.no_grad(): out = model(**inputs)
    r = processor.post_process_instance_segmentation(out, threshold=0.5, mask_threshold=0.5,
            target_sizes=inputs.get("original_sizes").tolist())[0]
    # r["masks"]: (N,H,W) bool at ORIGINAL resolution ; r["boxes"]: (N,4) xyxy float ; r["scores"]: (N,)
    # bf16 tensors: call .float() BEFORE .cpu().numpy()  (bf16->numpy errors otherwise)

## Integration target: the perception engine (VERIFIED contracts)
Location: projects/integration_harden/perception/
- engine.py  = PerceptionEngine. Models are INJECTED callables. `python3 engine.py` = self-test (must stay CLEAN).
    PerceptionEngine(detect, mask_for_box, vlm_ask, ...)
    Injection contracts (from engine.py docstring, lines 58-69):
      detect(frame, phrase, conf) -> [ {"label","conf","box"} ... ] sorted by conf desc
      mask_for_box(frame, box) -> bool mask or None
      vlm_ask(frame, question, dets) -> (long_text, highlight_target|None, vlm_box|None, short_text)
    box format = (x1,y1,x2,y2) int tuple. frame = cv2 BGR ndarray.
    highlight_step(frame, target, vlm_box_px=None, use_sam=True): calls self.detect(frame, target, self.floor)
      then apply_masks() which calls self.mask_for_box(frame, d["box"]) for the top-k dets.
    presence_gate(frame, phrase): uses vlm_ask.
- detectors.py = current owners:
    OmDet(device).detect(frame_bgr, phrase, conf=0.30, topk=8) -> [{label,conf,box=(x1,y1,x2,y2)}]. LOCAL=/root/models/vision/omdet-turbo-swin-tiny
    Eyes().mask_for_box(frame_bgr, box) -> bool mask via ultralytics SAM(config.SAM2_WEIGHTS). Full path /root/models/vision/sam2.1_b.pt (set SCENE_SAM2).
- vlm_client.py = Qwen3-VL client (ask/analyze/ground/ensure_server, parse_reply). VLM = llama-server, e.g. http://127.0.0.1:18090.
- scene_omdet.py = glue that wires the engine:
    engine = PerceptionEngine(detect=omdet.detect, mask_for_box=eyes.mask_for_box, vlm_ask=vlm.ask)
- config.py: SAM2_WEIGHTS, BG_SEG_MODEL, SCENE_DETECT_FLOOR/HL_CONF/HL_REL, resolve_device()/resolve_torch_device().
- Tests: projects/integration_harden/test/ (26 tests) + engine self-test. All must stay green.

## Task 1 design: Sam3Backend adapter
SAM3 does detect AND mask in ONE forward, but the engine injects detect + mask_for_box separately.
So build a small class (proposed: perception/sam3_backend.py) that runs SAM3 once per detect and
caches masks for mask_for_box to return -- no double inference:
    class Sam3Backend:
        def __init__(self, model_dir, nf4=True): load model+processor (nf4 as above)
        def detect(self, frame_bgr, phrase, conf=0.30, topk=None):
            run SAM3(concept=phrase) -> boxes/masks/scores; store {box_tuple: mask} in self._cache
            return [{"label":phrase, "conf":float(s), "box":(x1,y1,x2,y2)} for each, conf>=conf], sorted desc
        def mask_for_box(self, frame_bgr, box):
            return self._cache.get(box)  # mask SAM3 already produced for that box; else None (or re-run box-prompt)
Then wire in scene_omdet.py: engine = PerceptionEngine(detect=sam3.detect, mask_for_box=sam3.mask_for_box, vlm_ask=vlm.ask).
Keep OmDet/SAM2.1 code for now (do not delete) until owner confirms the swap live. Single-home rule:
the component lives ONCE.

## Task 2 design: VLM -> concept front-end
Purpose: turn an instruction into concept(s) + class-synonym sets for SAM3.
- Input: instruction English clause (the Recognizer already routes perception clauses to the VLM path).
- Step: ask Qwen3-VL (vlm_client) to extract the object concept(s) to segment, returned as a list,
  expanded to class synonyms where relevant (person; car,van,truck,bus,motorcycle,scooter; etc.).
- Step: for each concept, Sam3Backend.detect(frame, concept); union the results.
- Reason SAM3 needs this: bare concepts only + no cross-class generalization (measured; the missed
  van in the OCR street scene was "car" excluding "van").
- Keep the VLM presence-gate (engine.presence_gate) -- SAM3 can ground absent phrases (it grounded a
  0.63 "boiler" that was absent); a score threshold + the presence gate filter that.

## Hard constraints (bind all work)
- NO git writes by the agent. When done, SUGGEST commit blocks (house style, ` | ` separated, ASCII,
  Co-Authored-By trailer); the owner runs every git command.
- Models live ONLY under mounted /root/models/vision. Script every install (setup.sh + Dockerfile).
- Owner reads files IN THE WORKSPACE (never SendUserFile). Deliver readable reports, never raw JSON.
- Plain English output style. Use rtk wrappers for file ops (rtk read/ls/grep/find/git).
- Single-home components in integration_harden. projects/integration/ is FROZEN (never touch).
- No politically-charged / protest imagery in any dataset.
- The perception engine self-test and the 26 tests must remain green after any change; re-run and
  compare before claiming done.
- CAUTION: the manager session (groundstation, address rotates) and its subagents may edit
  projects/integration_harden/ concurrently. Check `rtk git status` first; coordinate / avoid clobber.
  If unsure whether task 1 lands in integration_harden vs a bench proto first, ASK the owner at start.

## Where things are (this session's artifacts)
- tools/bench/sam3-mask-bench/: README.md, RESULTS.md, this file, setup.sh, run_suite.py, run_web.py,
  run_indepth.py, measure.py, tests/{manifest.json,README.md,reference/}, candidates/ (the 17-image
  dataset: img0-7 + img10_...ocr + market/street-crowd/street-scene), overlays/, results/*.json,
  samexporter/ (gitignored dep, recreated by setup.sh).
- Dataset (17): tools/bench/sam3-mask-bench/candidates/  (img0.png,img1.png,img2.png,img3.png,
  img4.png,img5.jpeg,img6.jpeg,img7.jpeg,img10_highlight_windows_from_event_perform_ocr.jpeg,
  market-0..2.jpg, street-crowd-0..1.jpg, street-scene-0..2.jpg).
- /root/models/vision/: sam3-official (facebook/sam3, USE THIS), sam3.1-official (shelved),
  sam3-onnx-vietanhdev, sam3-onnx-embedl, sam2.1_b.pt, omdet-turbo-swin-tiny, sam3-desk-frames.
- EPHEMERAL (scratchpad, will be lost): the facebookresearch/sam3 repo clone + all 3.1 quant scripts.
  Not needed for tasks 1-2 (3.1 shelved). Re-clone only if 3.1 is revived later.

## Do NOT
- Do not pursue SAM3.1 tracking or more quantization (shelved; a hardware/dedicated-effort decision).
- Do not re-run benchmarks (numbers are in RESULTS.md).
- Do not compare to bf16. Do not touch projects/integration/.
- Do not run any drone/arm/motor command. Do not stage or commit git.

## FUTURE WORK (owner-flagged 2026-09-03): SAM3.1 quantization
SAM3.1 quantization for on-8GB video tracking is PRIORITIZED (owner 2026-09-04): a dedicated session (~2026-09-05) will crack it. NOT abandoned, NOT merely deferred.
State to resume from (all in RESULTS.md, "SAM3.1 quantization" + Updates 1-4):
- SAM3.1 runs via the facebookresearch/sam3 repo, build_sam3_multiplex_video_predictor(use_fa3=False);
  its per-frame add_prompt IS image detection; tracking = start_session + add_prompt + propagate_in_video.
- Weight quantization (DIY int8, torchao, HQQ int4 down to 1418 MiB) does NOT lower the tracking peak
  (~7000 MiB) -- the bottleneck is activation/tracking-state memory, not weights. Attention is already
  SDPA (efficient). The ONLY fix is TRUE int4 COMPUTE (gemlite/marlin) that never dequantizes.
- gemlite (Triton int4) installs on Blackwell but is blocked by (a) the repo running the detector in
  fp32 vs quantized fp16 dtype (RuntimeError at sam3_multiplex_base.py run_backbone_and_detection),
  and (b) the model's direct .weight transpose. The future task: reconcile per-layer dtypes + exclude
  the fp32/transpose spots + apply gemlite true-int4, OR run on a Hopper-class GPU where torchao/marlin
  int4 kernels work out of the box. Payoff: object tracking out of the box from SAM3.1 -> drop OSNet/ReID.
- Repo patch already made (in the ephemeral scratchpad clone, will be lost): @torch.inference_mode() ->
  @torch.no_grad() across sam3/model/*.py (needed so quantized tensors get a version_counter). Re-apply
  after re-cloning facebookresearch/sam3.
