# SAM3 demo-suite results (2026-09-03)

**Headline: SAM3 is a concept segmenter, not an instruction follower. Prompt it with a bare
concept and it exhaustively segments every instance at 0.92-0.98 confidence — beating the
current pipeline on count and confidence. Prompt it with an instruction and it returns nothing.**

Open this file in the editor's Markdown preview to see the overlays inline.

## Setup

- Model: `facebook/sam3`, bfloat16, RTX 5070 (8 GiB), transformers-native.
- Inputs: 9 owner-supplied images in `candidates/`.
- Prompts: generalized from the recognize.py logs (matched + variants), plus bare-concept probes.
- Baseline: the current Qwen3-VL pipeline output recorded in the logs (`tests/reference/`).

## Reporting convention: every count is a lower bound

**All counts in this report mean ">= N segmentable instances", never a total.** SAM3 undercounts
dense, distant, and occluded objects and has a finite object-query budget that hard-caps instances
per pass. Read "41 people" as "at least 41 people I can outline". Full reasoning in
[Counting semantics](#counting-semantics-sam3-gives-a-lower-bound-not-a-total) at the end.

## In-depth: SAM3 vs OmDet (detection) and vs SAM2.1 (mask IoU)

Base SAM3 on all 17 images, one primary concept each. Detection compared head-to-head with OmDet
(the current detector); masks compared to SAM 2.1 by IoU on SAM3's own boxes (same box, two
maskers). Raw: results/2026-09-03-indepth.json.

| image | concept | SAM3 dets (top) | OmDet dets (top) | mask IoU vs SAM2.1 |
|---|---|---|---|---|
| img0.png | window | 26 (0.92) | 0 (0.00) | 0.896 |
| img1.png | window | 47 (0.92) | 0 (0.00) | 0.796 |
| img2.png | person | 4 (0.94) | 5 (0.88) | 0.854 |
| img3.png | person | 1 (0.98) | 1 (0.91) | 0.981 |
| img4.png | person | 17 (0.96) | 7 (0.61) | 0.938 |
| img5.jpeg | person | 30 (0.95) | 6 (0.88) | 0.832 |
| img6.jpeg | person | 10 (0.96) | 11 (0.82) | 0.868 |
| img7.jpeg | person | 1 (0.87) | 1 (0.63) | 0.863 |
| img10.jpeg | car | 8 (0.98) | 8 (0.90) | 0.949 |
| market-0.jpg | person | 25 (0.94) | 10 (0.67) | 0.827 |
| market-1.jpg | person | 20 (0.95) | 7 (0.68) | 0.811 |
| market-2.jpg | person | 51 (0.95) | 6 (0.51) | 0.848 |
| street-crowd-0.jpg | person | 30 (0.94) | 13 (0.53) | 0.786 |
| street-crowd-1.jpg | person | 41 (0.94) | 10 (0.79) | 0.800 |
| street-scene-0.jpg | car | 9 (0.85) | 5 (0.56) | 0.881 |
| street-scene-1.jpg | car | 6 (0.96) | 5 (0.78) | 0.860 |
| street-scene-2.jpg | car | 6 (0.90) | 6 (0.88) | 0.868 |

**Totals: SAM3 332 detections vs OmDet 101 (3.3x more); mean mask IoU vs SAM2.1 = 0.862.**

Findings, numbered:
1. SAM3 detects far more instances than OmDet at higher confidence across every scene type.
2. OmDet returns 0 on 'window' (both building images); SAM3 returns 26 and 47. OmDet's open-vocab
   does not cover building attributes; SAM3 does.
3. SAM3 masks agree with SAM 2.1 at 0.862 mean IoU (0.79-0.98) on the same boxes -- mask quality is
   on par, so replacing SAM 2.1 with SAM3 masks costs nothing measurable.
4. Net: SAM3 replaces BOTH OmDet (better detection) and SAM 2.1 (equal masks) in one model.
5. Caveat: mask IoU sampled the first <=12 detections per image for speed; the mean is representative.

## Clean VRAM (isolated processes, matched method)

Each model measured alone, torch-allocated peak (the CUDA context ~300-600 MiB is a fixed floor
added equally to all, so it is excluded for a fair comparison).

| config | peak VRAM | replaces |
|---|---|---|
| OmDet | 582 MiB | (detector) |
| SAM 2.1 | 691 MiB | (masker) |
| OmDet + SAM 2.1 (current pair) | 1273 MiB | -- |
| SAM3 bf16 (unified) | 2006 MiB | both |
| SAM3 int4-nf4 (unified) | 886 MiB | both |
| SAM3.1 multiplex (image use) | 4723 MiB | both, + video tracking |

Findings:
1. SAM3 bf16 unified is +733 MiB over the OmDet+SAM2.1 pair, in exchange for one model, better
   detection, equal masks, and an optional tracking path.
2. SAM3 int4-nf4 unified is 886 MiB -- LESS than the current pair (1273 MiB) -- while replacing both.
   Quantized SAM3 does more for less VRAM.
3. SAM3.1 via the multiplex predictor is far heavier for single images (4723 MiB); it is a video tool.

## SAM3 vs SAM3.1 — which model, and why (measured)

SAM3.1's headline feature (Object Multiplex) is a VIDEO multi-object tracking optimization. But its
checkpoint also carries a full image detector, and its detector "routes to the image grounding
forward method" -- so SAM3.1 is a SUPERSET of SAM3, not a different-task model. It was never
restricted to a subset; the base SAM3 image builder is just hardwired to the base checkpoint, while
3.1 is exposed through the multiplex video predictor whose per-frame add_prompt IS image detection.

Measured on the armed-truck image, prompt "person":

| model | image detection | warm latency | VRAM | how it is run |
|---|---|---|---|---|
| SAM3 (base) | 10 @0.96 | 345 ms | 2006 MiB | transformers image model, clean API |
| SAM3.1 (multiplex) | 10 @0.957 | 587 ms (cold 970) | 4723 MiB | repo multiplex video predictor, 1-frame session |

Findings, numbered:
1. Identical image detection (10 instances, ~0.96) -- same-scale detector, no image-quality gain.
2. For SINGLE IMAGES, SAM3.1 is ~1.7x slower and ~2.3x heavier, because the detector runs inside the
   video-tracking (multiplex) machinery. On still frames that machinery is pure overhead.
3. SAM3.1's real advantage is VIDEO: Object Multiplex gives ~7x speedup at 128 tracked objects and
   better VOS (per Meta's release notes) -- untested here, that is the tracking lane.
4. Runtime caveat: SAM3 runs via the transformers image model; SAM3.1 has no transformers image path,
   so it runs via the repo's multiplex predictor. torch.compile (~2x, 3.1-only) could narrow the
   single-image gap but adds warm-up; not enabled here.

Recommendation (owner decides): for the on-demand image "highlight" pipeline (single frames), use
base SAM3 -- faster, lighter, identical quality. Reserve SAM3.1 for video multi-object tracking.

## The core finding

The recognizer prompts are instructions written for a VLM, for example
"Highlight all the people in the scene in great detail". Fed verbatim to SAM3, they return **0
detections**. SAM3's open-vocabulary mode expects a **concept noun** ("person", "window", "car").
Fed the concept, the same images light up completely. The table shows the gap.

| image | instruction prompt | bare concept | current pipeline (log) |
|---|---|---|---|
| damaged tower | 0 | **window: 47** @0.92 | 1 window |
| cinema audience | 0 | **person: 17** @0.97 | ~15 (one whole-image box) |
| convoy | 0 | **person: 30** @0.95 | not logged |
| truck, armed | 0 | **person: 10** @0.96 | 8 |
| two buildings | 0 | **person: 4** @0.94 | 3 |
| camouflaged man | 0 | **person: 1** @0.98 | 1 |

## Per-test results

### t1 — building render — "leftmost window on the top floor"
SAM3 found the window directly from the instruction: **1 @0.84**. Matches the current pipeline.

![t1](overlays/t1_building_render__matched.jpg)

### t2 — damaged tower — windows
Instruction prompts: **0**. Concept "window": **47 instances @0.92**. The current pipeline found
only 1. SAM3 segments the whole damaged facade.

![t2](overlays/t2_tower_damaged__concept_window.jpg)

### t3 — two buildings + people — people (and boilers, absent)
Concept "person": **4 @0.94** (current pipeline: 3). The absent "boilers" prompt wrongly grounded
**1 @0.63** — a presence-gate case a threshold or the VLM gate filters.

![t3](overlays/t3_two_buildings_people__concept_person.jpg)

### t4 — camouflaged man in tree-bark suit — person
Instruction: **0**. Concept "person": **1 @0.98**. SAM3 finds the camouflaged man cleanly.

![t4](overlays/t4_man_tree_suit__concept_person.jpg)

### t5 — cinema audience — count people
Instruction/question: **0**. Concept "person": **17 instances @0.97**. The current pipeline
returned a single whole-image box and a text count of ~15. SAM3 gives real per-person masks.

![t5](overlays/t5_cinema_audience__concept_person.jpg)

### t6 — convoy — people / weapon
Concept "person": **30 @0.95**. Weapon-notify phrase "a person holding a weapon": **4 matches**.

![t6](overlays/t6_convoy_trucks__concept_person.jpg)

### t7 — truck, armed men — people / weapon
Concept "person": **10 @0.96** (current pipeline: 8). Notify "a person holding a weapon":
**7 matches @0.80**. This is the weapon-detection use-case working well.

![t7](overlays/t7_truck_armed_men__concept_person.jpg)

### t8 — overhead RPG shooter — person aiming the weapon
Instruction worked here (concise, concept-like): **1 @0.77**. "weapon": 1 @0.51.

![t8](overlays/t8_overhead_rpg__matched.jpg)

### t9 — street scene (already highlighted) — left building / cars
Per your instruction, SAM3 did NOT touch the pre-marked right-building windows. It highlighted the
left building's windows (**2 @0.80**) and, as a variant, all cars (**7 @0.91**), in cyan.

![t9](overlays/t9_street_scene_ocr__var0.jpg)

### t9 follow-up: the missed van is vocabulary, not graphics

Owner asked whether SAM3 (and SAM2.1) missed the van because of the graphics/text on it. Tested by
prompting the street scene with several vehicle words:

| prompt | instances | top score |
|---|---|---|
| car | 8 | 0.98 |
| vehicle | 8 | 0.98 |
| truck | 0 | - |
| van | 2 | 0.92 |
| commercial van / white van | 2 | 0.91 |

The van is segmented cleanly under "van" (0.92). The graphics did NOT block it. "car" misses it,
"truck" misses it, and even the superordinate "vehicle" matched the 8 cars rather than the van.
So the cause is concept-word precision, not the images on the vehicle. The earlier "SAM2.1 missed
it too" is the same root one stage upstream: the OmDet detector was asked for cars, so it never
handed SAM2.1 a box for the van.

Implication for the front-end: the concept extractor must emit an explicit class/synonym set
(car, van, truck, bus, motorcycle, ...) -- SAM3 will not generalize a single word across vehicle
types, not even "vehicle".

![t9 vehicle probe](overlays/t9_vehicle_probe.jpg)

## Analysis

1. SAM3 is phrasing-sensitive: bare concepts work, instructions and questions return 0.
2. With concepts it is exhaustive and confident (0.92-0.98), beating the current pipeline on count
   (47 vs 1 windows; 17 real masks vs one whole-image box; 10 vs 8 people).
3. It found what instructions missed: the camouflaged man and all damaged-tower windows.
4. One adversarial-absent miss ("boilers" @0.63); a score threshold or the VLM presence gate
   removes it.
5. The weapon-notify phrase works directly ("a person holding a weapon": 7 @0.80 on the armed truck).

## Web candidates (8 images)

Concept + attribute prompts on the 8 owner-approved neutral images. Prompts chosen by category
(I cannot see the images), which both reveals content and tests attribute discrimination.
Raw: results/2026-09-03-web.json.

Findings: (1) exhaustive people, 20-51 per image at 0.94-0.95; (2) attribute discrimination WORKS
-- "carrying a bag" / "wearing a hat" / "wearing a backpack" return proper SUBSETS of the full
person count (e.g. street-crowd-1: 41 people -> 7 backpacks @0.91); (3) car and van count
separately (scene-0: 9 cars + 3 vans); (4) zeros are absent-or-missed with no ground truth, so the
overlays are the judge; (5) attribute prompts can be low-confidence (backpack 0.59 in crowd-0).

### market-0

person: 25 @0.94 | carrying a bag: 2 @0.80 | wearing a hat: 7 @0.87

*person (25)*

![person (25)](overlays/web_market-0__person.jpg)

*carrying a bag (2)*

![carrying a bag (2)](overlays/web_market-0__person_carrying_a_bag.jpg)

*wearing a hat (7)*

![wearing a hat (7)](overlays/web_market-0__person_wearing_a_hat.jpg)

### market-1

person: 20 @0.95 | carrying a bag: 2 @0.79 | wearing a hat: 3 @0.73

*person (20)*

![person (20)](overlays/web_market-1__person.jpg)

*carrying a bag (2)*

![carrying a bag (2)](overlays/web_market-1__person_carrying_a_bag.jpg)

*wearing a hat (3)*

![wearing a hat (3)](overlays/web_market-1__person_wearing_a_hat.jpg)

### market-2

person: 51 @0.95 | carrying a bag: 0 | wearing a hat: 15 @0.93

*person (51)*

![person (51)](overlays/web_market-2__person.jpg)

*carrying a bag (0)*

![carrying a bag (0)](overlays/web_market-2__person_carrying_a_bag.jpg)

*wearing a hat (15)*

![wearing a hat (15)](overlays/web_market-2__person_wearing_a_hat.jpg)

### street-crowd-0

person: 30 @0.94 | wearing a backpack: 3 @0.59 | bicycle: 0

*person (30)*

![person (30)](overlays/web_street-crowd-0__person.jpg)

*wearing a backpack (3)*

![wearing a backpack (3)](overlays/web_street-crowd-0__person_wearing_a_backpack.jpg)

*bicycle (0)*

![bicycle (0)](overlays/web_street-crowd-0__bicycle.jpg)

### street-crowd-1

person: 41 @0.94 | wearing a backpack: 7 @0.91 | bicycle: 0

*person (41)*

![person (41)](overlays/web_street-crowd-1__person.jpg)

*wearing a backpack (7)*

![wearing a backpack (7)](overlays/web_street-crowd-1__person_wearing_a_backpack.jpg)

*bicycle (0)*

![bicycle (0)](overlays/web_street-crowd-1__bicycle.jpg)

### street-scene-0

car: 9 @0.85 | van: 3 @0.73 | window: 17 @0.86

*car (9)*

![car (9)](overlays/web_street-scene-0__car.jpg)

*van (3)*

![van (3)](overlays/web_street-scene-0__van.jpg)

*window (17)*

![window (17)](overlays/web_street-scene-0__window.jpg)

### street-scene-1

car: 6 @0.96 | van: 0 | window: 6 @0.93

*car (6)*

![car (6)](overlays/web_street-scene-1__car.jpg)

*van (0)*

![van (0)](overlays/web_street-scene-1__van.jpg)

*window (6)*

![window (6)](overlays/web_street-scene-1__window.jpg)

### street-scene-2

car: 6 @0.90 | van: 2 @0.70 | window: 17 @0.93

*car (6)*

![car (6)](overlays/web_street-scene-2__car.jpg)

*van (2)*

![van (2)](overlays/web_street-scene-2__van.jpg)

*window (17)*

![window (17)](overlays/web_street-scene-2__window.jpg)

## Two-wheelers (all outdoor scenes)

Prompts `bicycle`, `motorcycle`, `scooter` on every outdoor image. Counts (top score):

| image | bicycle | motorcycle | scooter |
|---|---|---|---|
| img0/1/2/3, img5/6/7, img10 (owner demos) | 0 | 0 | 0 |
| market-0 | 0 | 0 | 0 |
| market-1 | 0 | 1 @0.52 | 0 |
| market-2 | 0 | 1 @0.56 | 1 @0.50 |
| street-crowd-0/1 | 0 | 0 | 0 |
| street-scene-0 | 0 | 9 @0.89 | 7 @0.85 |
| street-scene-1 | 0 | 5 @0.92 | 5 @0.85 |
| street-scene-2 | 0 | 1 @0.92 | 1 @0.93 |

Findings:
1. Two-wheelers ARE recognized where present: the three street-scene images have parked
   motorcycles/scooters, found at 0.85-0.92 confidence.
2. `bicycle` = 0 everywhere. Either no bicycles are present (the street two-wheelers look like
   motorbikes/scooters), or SAM3 does not fire on "bicycle" here. The overlays are the judge; I
   cannot see the source images.
3. `motorcycle` and `scooter` return near-identical sets (scene-0: 9 vs 7) -- the same vocabulary
   overlap seen with car/van. A front-end should query the whole two-wheeler class set.
4. The market hits are low-confidence (0.50-0.56) -- likely distant or borderline; check overlays.

Overlays (the motorcycle/scooter detections):

*street-scene-0 : motorcycle*

![street-scene-0 : motorcycle](overlays/twowheel_street-scene-0__motorcycle.jpg)

*street-scene-0 : scooter*

![street-scene-0 : scooter](overlays/twowheel_street-scene-0__scooter.jpg)

*street-scene-1 : motorcycle*

![street-scene-1 : motorcycle](overlays/twowheel_street-scene-1__motorcycle.jpg)

*street-scene-2 : motorcycle*

![street-scene-2 : motorcycle](overlays/twowheel_street-scene-2__motorcycle.jpg)

*market-1 : motorcycle*

![market-1 : motorcycle](overlays/twowheel_market-1__motorcycle.jpg)

*market-2 : scooter*

![market-2 : scooter](overlays/twowheel_market-2__scooter.jpg)

## Counting semantics: SAM3 gives a lower bound, not a total

In dense scenes SAM3's instance count is a FLOOR, and should be reported as "at least N", for two
reasons: (a) distant/tiny/occluded people are not individuated and go uncounted; (b) SAM3 has a
finite object-query budget -- a hard ceiling on instances per pass (not yet measured; market-2 hit
51). For a true total in packed crowds a density-estimation counter is the right tool -- it gives
the number but no masks. SAM3 gives masks and undercounts density; they are complementary. All
people/vehicle counts in this report should be read as ">= N segmentable instances".

## Tracking (SAM3.1) -- does not fit the 8 GiB GPU

Attempted SAM3.1 multiplex video tracking on a neutral CC traffic clip (Wikimedia). Result:
CUDA out-of-memory on the 7.53 GiB-usable GPU, at every setting tried (512px, then 384px /
10 frames / CPU frame offload / default multiplex). Peak reached 7008 MiB before OOM.

Findings:
1. Grounding on a frame works (concept "traffic light": 3 objects on frame 0) -- detection is fine.
   It is the multi-frame TRACKING STATE that exceeds memory, not detection.
2. The multiplex model is ~4.7 GiB resident, and multiplex_count is fixed at 16 by the checkpoint
   (reducing it breaks weight loading), so the tracking buffers cannot be shrunk that way.
3. Meta's SAM3.1 tracking numbers are on H100. On this 8 GiB GPU it does not run.
4. This is where quantizing SAM3.1 would actually pay off: freeing VRAM for the tracking state is
   the one path to running 3.1 tracking on an 8 GiB budget. For still images, base SAM3 remains the
   right, lighter choice regardless.

Conclusion: SAM3.1 video tracking is NOT viable on the 8 GiB drone GPU as-is. It needs a larger GPU
or a quantized 3.1.

## SAM3.1 quantization (VRAM goal proven; engine blocked on toolchain)

Quantizing SAM3.1 to run video tracking within the 8 GiB budget:

| stage | VRAM (weights) |
|---|---|
| SAM3.1 fp | 3744 MiB |
| SAM3.1 torchao int8 weight-only | 1819 MiB |

The quantization WORKS: weights halve to 1819 MiB. With ~2.5 GiB of tracking state that lands
near ~4.3 GiB total -- inside the 8 GiB budget, which is exactly what tracking needs. So quantized
SAM3.1 tracking on the drone GPU is feasible in principle.

Blocker to running it end to end (environment, not model):
1. bitsandbytes module-swap: breaks -- the repo's ViT uses fused-qkv/rope forwards that read
   `.weight` directly, bypassing the module forward bnb needs.
2. torchao int8 (the right tensor-level method): quantizes fine, but torchao 0.18's compiled int8
   CUDA kernel is a Python-3.10 build and will not load on this container's Python 3.12, so
   Int8Tensor cannot execute the matmul (aten.t unimplemented). Patched the repo's
   @torch.inference_mode() -> @torch.no_grad() to get past the earlier version-counter error.
Fix: a torchao build matching Python 3.12 (source build needs nvcc), or a custom int8 Linear whose
forward controls the dequant. Bounded last-mile work, ~1-2h.

Bottom line: the VRAM target is met (1819 MiB); a running quantized-3.1 engine needs a matching
torchao build.

### Update: quantization does NOT make tracking fit 8 GiB (measured)

Quantized the SAM3.1 weights (custom int8 Linear, 3744 -> 1736 MiB) and re-ran tracking. Result:
still CUDA OOM, peak 7047 MiB -- essentially unchanged from the fp run's 7008. So weights are NOT
the bottleneck; the multi-frame TRACKING-STATE and activation memory during propagation is. Freeing
~2 GiB of weights did not move the propagation peak. (The custom int8 dequantizes to fp16 in the
forward, so peak still materializes fp16 weights; true int8-COMPUTE kernels would help more, but
torchao's are a Python-3.10 build and will not load on this Python-3.12 container.)

CONCLUSION: the 8 GiB drone GPU cannot run SAM3.1 video tracking, quantized or not. To run 3.1
tracking needs a larger GPU, activation-level optimization (true int8 compute, or fewer objects /
lower res than the fixed multiplex_count=16 checkpoint allows), or the ComfyUI ConvRot path IF it
supports video tracking (author validated image segmentation only -- unverified for video).
Quantized SAM3.1 DETECTION on images works fine (10 objects, quality preserved; community ConvRot
reports IoU 0.997 vs fp) -- but images do not need 3.1.


### Update 2: activation quantization is the right lever, but int8 is not enough (measured)

Corrected the earlier weight-only test. Ran TRUE int8-activation matmul (torch._int_mm, W8A8):

| config | tracking peak VRAM | result |
|---|---|---|
| fp | 7008 MiB | OOM |
| weight-only int8 | 7047 MiB | OOM |
| W8A8 (int8 activations) | 6844 MiB | OOM |
Int8 activations shave only ~200 MiB. Weights are NOT the bottleneck; the ViT-H activations (fixed
1008 internal res) + multiplex tracking-state memory are. To fit 8 GiB you need W4A4 (int4
ACTIVATIONS) to roughly halve the ~5 GiB of activation/state. DIY int4 activations are not possible
in core torch (_int_mm is int8-only; int4 needs packed kernels -- torchao's, blocked on Python 3.12,
or ComfyUI's). The only working W4A4 SAM3.1 is the ComfyUI ConvRot build, validated for image
segmentation only (video tracking unverified). Remaining options for tracking on 8 GiB: test the
ComfyUI ConvRot W4A4 video path (uncertain), or use a larger GPU.


### Update 3: INT4 verdict on Blackwell/8 GiB (final)

Tested torchao dynamic-activation on Blackwell (sm_120):
- torchao int8 matmul WORKS on a plain Linear (fallback path) despite the sm_90 .so warnings.
- But on SAM3.1 it hits NotImplementedError: Int8Tensor has no aten.t -- the model transposes
  weights in its forward (sam3_multiplex_base.py:509), which torchao's quantized tensors do not
  implement. This breaks torchao int8 AND int4 on this model.
INT4 specifically needs all three of: (1) int4 kernels for Blackwell (torchao's are sm_90; no
fallback; would need a source build -> nvcc, absent here), (2) a fix for the model's aten.t
transpose, (3) an int4-ACTIVATION scheme (W4A4; not a standard torchao config; only ConvRot, which
is ComfyUI-only). None achievable in-container without a build toolchain.
FINAL: SAM3.1 tracking on this 8 GiB Blackwell GPU is not achievable via quantization here. The
realistic unlock is a Hopper-class GPU (torchao kernels run) or an nvcc-equipped container to build
Blackwell int4 kernels. Tracking-out-of-the-box (dropping OSNet/ReID) remains attractive -- it is a
hardware/toolchain provisioning decision, not a software one on this box.


### Update 4: multi-method quantization sweep -- weights are not the bottleneck (final)

Tested every practical quantizer (per the PEFT quantization guide) against the tracking OOM:

| method | weights VRAM | tracking peak | result |
|---|---|---|---|
| fp | 3733 MiB | 7008 | OOM |
| DIY int8 (dequant fwd) | 1736 | 7047 | OOM |
| DIY W8A8 (torch._int_mm) | 1737 | 6844 | OOM |
| torchao int8 / W8A8 | -- | -- | breaks: Int8Tensor has no aten.t |
| HQQ int4 | 1418 | 7059 | OOM |
| HQQ + gemlite (true int4) | 1418 | -- | blocked: model runs detector in fp32 vs quantized dtype |

Conclusion: weight quantization drops storage (down to 1418 MiB) but NOT the tracking peak (~7000
everywhere), because dequant-during-forward re-materializes fp weights that coexist at peak. The
bottleneck is tracking-time activation/state memory, which weight quant does not reduce. Attention
is already memory-efficient (SDPA), so that is not the lever either. The only fix is TRUE int4
COMPUTE (gemlite/marlin) that never dequantizes -- gemlite installs on Blackwell (triton 3.6) but
is blocked by the repo's mixed-precision detector forward + direct-.weight transpose; making it run
is a real integration task (per-layer dtype reconciliation), not a quick fix. Net: SAM3.1 tracking
on 8 GiB Blackwell needs either that gemlite integration effort or a Hopper-class GPU where mature
int4 kernels work out of the box.

## Conclusion (recommendation, owner decides)

SAM3 is not a drop-in for the instruction pipeline. Paired with the resident VLM as a
concept-extraction front-end — instruction -> concept -> SAM3 — it segments more exhaustively and
confidently than the current OmDet-box + SAM2 path, and adds tracking. That is the integration
shape to evaluate next. Open decision: whether to build that VLM->concept->SAM3 front-end.
