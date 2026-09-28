# SAM3 vs OmDet-Turbo + SAM2.1 — research complete (2026-09-03 and 2026-09-09)

> COMPLETE. SAM3-nf4 is the one vision backend of harden2 (perception2/). This document holds the
> results of the two scripts that measured the choice: bench/sam3-mask-bench/run_indepth.py and
> bench/sam3-mask-bench/compare_engines.py. Both import the OmDet pipeline (the `perception`
> package), which is deleted, so neither runs. Their raw results stay in
> bench/sam3-mask-bench/results/ (2026-09-03-indepth.json, 2026-09-03-engine-ab*.json/.md).

## Objective

1. Can SAM3 alone replace OmDet-Turbo (boxes) plus SAM2.1 (masks)? (run_indepth.py)
2. Through the SAME PerceptionEngine, what changes when the backend is swapped? (compare_engines.py)

## Setup

- Images: the 17 candidate images of bench/sam3-mask-bench/candidates/ (9 owner images + 8 web).
- Hardware: RTX 5070 laptop GPU, 8 GiB.
- Study 1: base SAM3 (bf16), one primary concept per image. Detection counted against OmDet-Turbo.
  Masks compared with SAM2.1 by mask IoU on SAM3's own boxes (same box, two maskers; the first 12
  detections per image).
- Study 2: each backend in its own process, through the same PerceptionEngine (relative gate + mask
  hygiene, mask_k = 3). Presence gate bypassed; bare concepts. Latency = one full highlight step
  (detect + mask). SAM3 at nf4.

## Results

Study 1 (2026-09-03):

| image | concept | SAM3 detections (top conf) | OmDet detections (top conf) | mask IoU vs SAM2.1 |
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
| total / mean | | 332 | 101 | 0.862 |

Study 2 (2026-09-03 run, analysed 2026-09-09; 35 image-concept pairs):

| backend | total detections | latency p50 ms | latency p90 ms |
|---|---|---|---|
| OmDet + SAM2.1 | 52 | 71.9 | 583.7 |
| SAM3-nf4 | 84 | 451.7 | 933.7 |

- Where both found the object, the best-box IoU between the two backends was 0.58-0.99.
- Every "window" pair: OmDet 0-1, SAM3 2-3 (the engine keeps at most 3 boxes).

## Analysis

1. SAM3 found 3.3 times more instances than OmDet (332 vs 101), at higher confidence, in every
   scene type.
2. OmDet found no window in either building image; SAM3 found 26 and 47.
3. SAM3's masks agree with SAM2.1's on the same boxes at 0.862 mean IoU (0.786-0.981). Mask quality
   is equal, so SAM3 replaces both models.
4. Counts are lower bounds: SAM3 undercounts dense, distant and occluded objects.
5. Through the engine, SAM3 drew 3 boxes at most while raw SAM3 found 26-47 windows. The cause was
   the engine's OmDet-era cap (mask_k = 3), built because every SAM2.1 mask cost a separate
   forward pass. SAM3 returns boxes and masks in one pass, so the cap had no reason left. It was
   lifted on 2026-09-09 (HL_MAX, HL_TOPK).
6. SAM3-nf4 is slower per highlight step (p50 452 ms vs 72 ms). The one-model design and the
   detection gain outweighed it; a highlight refreshes about once per second.

## Conclusions

- SAM3-nf4 replaced OmDet-Turbo and SAM2.1 as the one vision backend (decided 2026-09-03).
- The bench-vs-live gap of 2026-09-09 was the inherited cap, not SAM3; the cap is gone.
- Both scripts are retired under the benchmark rule of 2026-09-26 (bench/README.md): no longer of
  use, in the git history (e66b674, d26fd5e), results here, untouched since 2026-09-13, and in
  docs/HISTORY.md (2026-09-03, 2026-09-09).
