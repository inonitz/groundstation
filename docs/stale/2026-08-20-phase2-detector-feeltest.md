# Phase 2 — Apache detector feel-test (escape YOLOE/YOLO26 AGPL + get open-vocab)

**Date:** 2026-08-20. **Scope:** qualitative "get a feel", NOT a benchmark. Ran on the esoteric bench
set (the exact images where YOLOE-2026 failed: microphone, headphones, pendant, guitar case, hat-person)
plus COCO images. Harness: `scratchpad/phase2/run.py`. Annotated outputs saved alongside it.

## Why
The follow/highlight stack leans on Ultralytics (YOLO26, YOLOE) which is **AGPL-3.0** — a product
landmine. Goal: find permissive (Apache) detectors that match or beat it, ideally with open-vocab so we
drop the ~8s VLM grounding from the highlight hot path.

## What ran (all Apache-2.0, all native in transformers 5.15 -> NO repo clone)
- **D-FINE-small** (`ustc-community/dfine-small-coco`) — closed-set COCO-80, real-time DETR.
- **OmDet-Turbo-tiny** (`omlab/omdet-turbo-swin-tiny-hf`) — open-vocab, real-time. Needs `timm`.

## Results (top confidence per prompt; ROCm/RX7900GRE)
| image / prompt              | OmDet-Turbo (open-vocab) | D-FINE (closed COCO) |
|-----------------------------|--------------------------|----------------------|
| bus / person                | 0.97 / 0.95              | 0.94 / 0.94          |
| cats / remote / pink blanket| 0.78 / 0.74 / 0.54       | 0.96 / 0.95 / --     |
| zidane / "the man on the left" | 0.63 / **0.76**       | 0.94 / n/a           |
| microphone / stand / pop filter | **0.61 / 0.44 / 0.31** | laptop:0.96 (wrong) |
| headphones / cable          | **0.67 / 0.49**          | scissors:0.63 (wrong)|
| necklace / pendant          | **0.61 / 0.55**          | motorbike:0.82 (wrong)|
| guitar case                 | **0.31** (found)         | suitcase:0.34 (wrong)|
| hat-person: person/hat/"person wearing a hat" | 0.91 / 0.87 / **0.63** | person:0.98 |
| latency                     | ~115 ms (~9 fps)         | ~60 ms (~16 fps)     |

Baseline for contrast: YOLOE-2026 scored ~0.00 on the esoteric prompts (guitar case / headphones /
necklace) and cannot compose modifiers ("man with black hat" -> boxes only the hat).

## Findings
- **OmDet-Turbo = the YOLOE replacement.** Open-vocab, Apache, in transformers, ROCm-clean. Finds the
  esoteric objects AND resolves referring/compositional phrases, no hallucination on this set. ~9 fps is
  workable for an on-demand highlight (not every frame). One dep: `timm`.
- **D-FINE = the YOLO26 (closed background/tracker) replacement.** Apache, ~16 fps, COCO-excellent,
  great on person (0.98). Useless on open-vocab by design (force-maps to nearest COCO class).
- **Layered story holds:** D-FINE (fast closed-set person/car for the tracker) + OmDet-Turbo (on-demand
  open-vocab grounding) + VLM (only the hard reasoning). No single model does all three.

## The two models the human named — scouted, deferred (both need a repo clone, not in transformers)
- **D-FINE-seg** (`ArgoHA/D-FINE-seg`, Apache-2.0): D-FINE + mask head, real-time detect + instance +
  semantic seg; claims to beat YOLO26-seg on fine-tune F1. Still **closed-set**. Would replace
  YOLO26-seg/SAM2 for masks, but is a standalone repo (clone + weights + custom inference). Defer unless
  we need Apache instance masks without SAM2.
- **OV-DEIM** (`wleilei/OV-DEIM`, arXiv 2603.07022): DETR-style open-vocab on DINOv3/DEIMv2, SOTA on rare
  categories. Standalone repo clone. **OmDet-Turbo already covers the open-vocab need at zero integration
  cost**, so OV-DEIM is only worth it if OmDet's accuracy/speed proves insufficient live.

## Recommendation
Adopt **OmDet-Turbo (open-vocab) + D-FINE (closed)** as the Apache detector stack; keep the VLM for hard
reasoning. Defer OV-DEIM and D-FINE-seg (repo clones, no clear win over the above yet).

## Not done / open items (need human sign-off — beyond "get a feel")
- **Tracker coupling / full AGPL escape.** follow.py/track.py use Ultralytics `.track()` (BoT-SORT),
  which is AGPL and tied to Ultralytics models. Swapping only the detector does NOT escape AGPL. Full
  escape needs a permissive tracker over external detections (e.g. original ByteTrack MIT, or a
  hand-rolled BoT-SORT). Note: `boxmot` is also AGPL. This is a productization task, not a gate task.
- **Integration.** To use OmDet/D-FINE in the demo: run the detector standalone per frame -> feed boxes
  to the tracker. Not wired yet (Phase 2 was feel-test only).
- **Deps:** `timm` now required for OmDet-Turbo (add to Dockerfile/requirements if adopted).
