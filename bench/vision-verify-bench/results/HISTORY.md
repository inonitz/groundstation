# vision-verify-bench — superseded results

Superseded by the 2026-09-20 three-way run in the README scorecard. Kept next to the raw JSON.

## SUPERSEDED — 2026-09-20, human labels, two paths (135 rows)

Raw: `2026-09-20-bench-human.json`.

| rows | baseline | verify |
|---|---|---|
| 84 absent rows: drew anyway (false draws) | 24 | 8 |
| 51 present rows: missed or wrong box | 6 | 6 |
| 51 present rows: partial (crowded scene, live cap 8 boxes/query) | 17 | 17 |
| 51 present rows: fully right | 28 | 28 |
| mean IoU when right | 0.95 | 0.95 |
| latency p50 / p95 | 413 / 1273 ms | 448 / 1299 ms |

The three-way run replaces this. It scores all 137 human rows and adds the control path.

## SUPERSEDED — 2026-09-19, pre-labels, two paths (156 rows)

Raw: `2026-09-19-bench-prelabels.json`. The labels were a 2026-09-08 VLM vote, not human truth.

| class | path | correct | false-draw | miss | wrong-box |
|---|---|---|---|---|---|
| 1 simple present | both | 38 | 0 | 7 | 2 |
| 2 simple absent | both | 63 | 6 | 0 | 0 |
| 3 relation holds | baseline / verify | 8 / 6 | 0 / 0 | 0 / 2 | 0 |
| 4 related noun absent | baseline / verify | 15 / 20 | 5 / 0 | 0 | 0 |
| 5 wrong relation | baseline / verify | 1 / 5 | 5 / 1 | 0 | 0 |
| 6 look-alike | both | 4 | 2 | 0 | 0 |

False draws 18 to 9. Latency p50 412 to 410 ms. A second same-day run after three fixes gave
false draws 23 to 11, class 4 nine to zero, class 5 five to two, p50 418 to 436 ms.

## SUPERSEDED — 2026-09-20, three-way, topk=8 BUG (not live-matched)

Raw: `2026-09-20-bench-3way-human.json`. The bench hardcoded detect topk=8 and skipped MIN_BOX_FRAC.
The live path uses topk=128 (HL_TOPK) and min_frac=0.001. Replaced by the live-matched run below.
False draws control 84 / baseline 24 / verify 8; correct rows 30 / 88 / 104; verify p50 wrongly diluted to 450 ms.
