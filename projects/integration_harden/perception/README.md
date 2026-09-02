# perception/ — the perception engine inside integration_harden

What the drone sees and highlights: open-vocab detection, mask hygiene, and the VLM presence
gate, extracted from the live desk loop on 2026-09-02. The glue (video window, chat pane, keys,
threads, ASR wiring) stays in scene_omdet.py; this package holds the logic and the models.

## Files

| file | role |
|---|---|
| `engine.py` | THE COMPONENT: relative-confidence gate, mask hygiene, VLM fallback, presence gate, highlight-phrase parsing. Models are injected callables. `python3 engine.py` = self-test, no GPU. |
| `detectors.py` | the model owners: OmDet (open-vocab detector, offline-safe loading) and Eyes (background YOLO26-seg + lazy SAM2 + legacy backends). Moved verbatim from highlight_seg.py / eyes.py. |
| `vlm_client.py` | Qwen3-VL client: ask / analyze / ground / ensure_server. `parse_reply()` is split out so the reply parsing is testable without a server. Moved from vlm.py. |

## Wiring (what scene_omdet.py does)

```python
from perception import PerceptionEngine, parse_highlight
from perception.detectors import Eyes, OmDet
from perception import vlm_client as vlm

engine = PerceptionEngine(detect=omdet.detect, mask_for_box=eyes.mask_for_box, vlm_ask=vlm.ask)
dets, masks, dbg = engine.highlight_step(frame, target, vlm_box)   # per frame
present, box = engine.presence_gate(frame, phrase)                 # per new target
```

Tuning knobs are constructor arguments, read once from SCENE_DETECT_FLOOR / SCENE_HL_CONF /
SCENE_HL_REL at startup. The package needs the integration_harden root on sys.path.

## History

highlight_seg.py (the superseded predecessor app), eyes.py and vlm.py were absorbed here;
their code moved, not rewritten. Git history keeps the originals. Tests: test/test_perception.py
(fakes only, no GPU).
