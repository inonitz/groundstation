# The recorder's six drawings: the sources

The six `.dot` files are the sources of the drawings embedded in
`../../modules/01-recorder/recorder.html` (kept by the owner's word, 2026-10-24, RCD75).

| file | drawing |
|---|---|
| d1_push.dot | 1 a span or an event: the push |
| d2_pass.dot | 2 the writer's pass |
| d3_wake.dot | 3 the wake flag |
| d4_frame.dot | 4 a frame through the image buffer pool |
| d5_lifetime.dot | 5 Create, Destroy, FlushInDie |
| d6_health.dot | 6 the statistics and the health |

Render and measure one drawing (the pipeline is `~/.claude/skills/diagram-authoring`):
```
python3 ~/.claude/skills/diagram-authoring/gvcairo.py d2_pass.dot d2_pass
python3 ~/.claude/skills/diagram-authoring/check.py d2_pass.dot d2_pass.png
```
Every count the checker prints must be zero. The html embeds each PNG as base64, in order 1 to 6.
