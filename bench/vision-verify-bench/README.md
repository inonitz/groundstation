# vision-verify-bench

Measures the highlight path on human-labelled truth: does the system draw the right object, and does it
refuse when the described object is not there. Compares today's SAM3-only path against SAM3 + the
split-and-verify step (`perception2/verify.py`, switch `SCENE_VERIFY`). Accuracy and latency, one table.

## Sections

| section | what is in it |
|---|---|
| [Objective](#objective) | the one question this bench answers |
| [Dataset](#dataset) | images, query classes, label fields |
| [Usage](#usage) | propose, annotate, run |
| [Results](#results) | current numbers |
| [Files](#files) | what each file is |

## Objective

On the 2026-09-19 webcam run the system drew boxes for objects that were not there: "backpack held by a
child" drew guitar cases, "person on the roof" drew a person, "man with glasses talking to a woman in
yellow" drew the operator. SAM3 scores the parts of a phrase that match and never checks the parts
that are missing. This bench puts a number on that failure and on the fix, offline, on saved frames.

## Dataset

**Images are private and gitignored** (`dataset/images/`). The owner's room, live-session frames, and street/desk shots stay local. Labels, results and code are committed; a clone needs the frames copied in to re-run.

`dataset/queries.jsonl`, one row per (image, phrase). 157 rows over 49 images:
- `2people_bedroom.jpg` (owner's room, faces blurred): 46 rows written by eye across all six classes.
- 22 session frames from the 2026-09-19 live runs, with the phrase actually spoken.
- 89 rows on the old whole-system bench images (17 street candidates + desk frames) with the 2026-09-08
  VLM-consensus presence as a PRE-label. Not human truth until confirmed in annotate.py.

Classes: 1 simple present, 2 simple absent, 3 related + relation holds, 4 related noun absent,
5 both present but wrong relation, 6 look-alike trap. Classes 3-5 are thin (8/20/6); they need
relational phrases on the street and desk frames, which needs a human eye on those images.

Fields: `he` (spoken Hebrew), `head`, `related[]` (noun, color), `relation`, `cls`, `present` (the full
phrase is in the frame), `head_present` (the head noun exists even if the relation fails), `gt_box`,
`box_source` (estimate | sam3-propose | human), `sam3_box`, `sam3_top_conf` (today's best guess).

## Usage

1. `python3 propose_boxes.py` -- SAM3 pre-fills a box per row (GPU, ~1 min).
2. `python3 annotate.py --only-unlabeled` -- confirm each row: y / n / d / drag. About 5 s per row.
3. `python3 bench.py --labels human` -- control vs baseline vs verify on the labelled rows (GPU, ~3 min).
   Add `--iou N` to change the match threshold (default 0.5).

## Results

2026-09-20, HUMAN labels, three arms, 137 rows over 48 images, LIVE-MATCHED. Raw:
`results/2026-09-20-bench-3way-human-livematch.json`. Superseded runs: `results/HISTORY.md`.

### Setup (matches the live mvd gate)

- Rows: 137 human-truth rows. 53 present, 84 absent. `box_source == human` only.
- Model: `facebook/sam3`, int4-nf4. GPU: NVIDIA RTX 5070 Laptop.
- Detect: floor 0.1, topk 128 (HL_TOPK, the live cap). Read from config, not hardcoded.
- Baseline gate: count at 0.5, containment 0.7, min_frac 0.001 (MIN_BOX_FRAC).
- Verify: head 0.5, related noun 0.3, geometry, hue color. Runs on related-noun rows only.
- A drawn box counts as a truth match at IoU 0.5 or more.
- Proof the cap is 128: max boxes drawn in one query was control 123, baseline 37, verify 37.

### The three arms

- **control**: draws for every query, never refuses. Raw SAM3 at floor 0.1, full-frame box if empty.
- **baseline**: today's path. SAM3 draws when the head clears the 0.5 count gate.
- **verify**: baseline plus `perception2/verify.py`. Checks related noun, geometry, color. Refuses on absence.

### Row verdicts, per class, every column

Classes: 1 simple present, 2 simple absent, 3 relation holds, 4 related noun absent, 5 wrong relation, 6 look-alike trap.

| class | path | correct | partial | false-draw | miss | wrong-box |
|---|---|---|---|---|---|---|
| 1 | control | 26 | 11 | 5 | 0 | 3 |
| 1 | baseline | 23 | 14 | 4 | 0 | 4 |
| 1 | verify | 26 | 14 | 1 | 0 | 4 |
| 2 | control | 2 | 2 | 45 | 0 | 3 |
| 2 | baseline | 46 | 2 | 1 | 3 | 0 |
| 2 | verify | 46 | 2 | 1 | 3 | 0 |
| 3 | control | 5 | 0 | 3 | 0 | 0 |
| 3 | baseline | 5 | 0 | 3 | 0 | 0 |
| 3 | verify | 6 | 0 | 2 | 0 | 0 |
| 4 | control | 0 | 0 | 20 | 0 | 0 |
| 4 | baseline | 11 | 0 | 9 | 0 | 0 |
| 4 | verify | 20 | 0 | 0 | 0 | 0 |
| 5 | control | 0 | 0 | 6 | 0 | 0 |
| 5 | baseline | 1 | 0 | 5 | 0 | 0 |
| 5 | verify | 4 | 0 | 2 | 0 | 0 |
| 6 | control | 1 | 0 | 5 | 0 | 0 |
| 6 | baseline | 3 | 0 | 2 | 1 | 0 |
| 6 | verify | 3 | 0 | 2 | 1 | 0 |

### Instances, totals, latency

| path | matched | missed | extra | false draws | correct rows | correct+partial | mean IoU |
|---|---|---|---|---|---|---|---|
| control | 244 | 78 | 1108 | 84 | 34 | 47 | 0.93 |
| baseline | 192 | 130 | 79 | 24 | 89 | 105 | 0.94 |
| verify | 192 | 130 | 57 | 8 | 105 | 121 | 0.94 |

Latency p50/p95 ms: control 413/1253, baseline 413/1261, verify 829/928. The verify figure is relation
rows only; each runs one extra SAM3 detect for the related noun. Simple highlights do not run verify.

### Analysis

1. The cap fix is proven. Max boxes drawn rose to 123 (control), not 8.
2. Row correctness barely moved. Verify went 104 to 105. The cap was not the limiter.
3. Instance recall is the limiter. SAM3 missed 130 of 322 present instances even at cap 128.
4. So crowded "all the X" rows stay partial. SAM3 misses some people, not the cap.
5. False draws are unchanged: control 84, baseline 24, verify 8. Verify still cuts two thirds.
6. Overall full-correct: verify 76.6%. Correct-or-partial (drew the object): 88.3%.
7. Verify costs about 2x on a relation phrase (829 vs 413 ms p50). Simple phrases are free.
8. Class 4 (related noun absent) is the biggest win. Verify refuses all 20; baseline refuses 11.
9. Verify trims spurious instance boxes too: extra 79 to 57.
10. Classes 3, 5, 6 hold 8, 6, 6 rows. Those cells are weak evidence.

### Open decision

Reaching row-correctness near 95% needs better SAM3 instance recall, not a cap change. The cap is already maxed.


## Files

| file | role |
|---|---|
| `dataset/queries.jsonl` | the rows; the labels live here |
| `dataset/images/` | the frames (private, gitignored via the root .gitignore; kept local) |
| `propose_boxes.py` | SAM3 box proposals + the baseline's top confidence per row |
| `annotate.py` | the human pass |
| `bench.py` | scores control vs baseline vs verify, matched to the live gate |
