# recognizer/ — the Recognizer module inside integration_harden

Hebrew utterance in, one of four results out: a mission, planner-bound English, VLM-bound
English, or a spoken rejection. Wired as the Router's on_complex callback; the router's own
tiers (emergency, override, basic verbs) are untouched.

## Files

| file | role |
|---|---|
| `recognizer.py` | the component: stages 0-6 + `recognize()`. `python3 recognizer.py` = self-test |
| `pipeline.py` | the glue: `Pipeline(wire, vlm_query, say).handle(text)`, drop-in for on_complex |
| `prompts.py` | prompts and grammars for both models |
| `llama.py` | the chat call and (for tools) the server context manager |
| `trace.py` | per-utterance JSONL recorder -> ../traces/, gitignored |
| `run_dicta_server.sh` | DictaLM on CPU, port 18091 (`SCENE_XLATE_PORT`) |
| `run_hymt2_server.sh` | Hy-MT2-1.8B-Q4 on the GPU, same port, -c 1024 -np 1 (the deployed translator, ruling 2026-09-07) |

## Guards added 2026-09-08 (all bench-gated, see tools/bench/hebrew-command-bench/README.md)

- Stage 4b answer-mode guard: a first-person reply ("I am", "I see", "I cannot", "please say", "my
  function") is retried with `translate(strict=True)`, then REJECTED and read back. Live cause: the
  land-trap question made DictaLM answer "To land, please say Land" and the planner landed.
- Number guard idioms: חצי סיבוב = 180, סיבוב וחצי = 540 on both sides; ASR-glued punctuation and the
  ש clitic on חצי are read; a bare מטר becomes מטר אחד before translation (stage 2).
- Planner few-shot echo guard (pipeline.py `is_shot_echo`): a mission identical to one of the planner's
  examples, from English without that example's numbers, is refused and read back.
- Clockwise / counterclockwise inline rules (Hy-MT2 flipped the sign).
- translate() contract: `translate(he, required_numbers=None, strict=False)`; prompt variant via
  `MVD_TRANSLATE_PROMPT=v1|v2` (v2 rejected, kept selectable).

## Wiring (one line at assembly)

```python
from recognizer import Pipeline
pipe = Pipeline(wire, vlm_query=eyes.ask, say=voice.say)
router = Router(wire, on_complex=pipe.handle)
```

Servers: run_dicta_server.sh (CPU) or run_hymt2_server.sh (GPU) on the translator port + the resident Qwen3-VL on 18090.

## Sync rule (do not break it)

This folder is the component's SINGLE home (dedup ruling): the bench imports it from here
and measures it in place. Rules change HERE, then
`python3 /root/groundstation/tools/bench/hebrew-command-bench/bench.py` re-measures; a rule
without a full re-measure is unverified. Measured state (2026-09-02): 301/364 overall,
commands 98% at the planner ceiling; scorecard in the bench README.


Stage 0 emergency words added 2026-09-08 (owner ruling): הפסק/הפסיקי/הפסיקו/תפסיק/תפסיקי/תפסיקו (not when followed by ל+עקוב/הדגיש/סמן/הראות/צלם/ספור = a perception clear) and די only as the whole utterance or its last word. Gate: 0 new fires on the 413 dataset; tests in test_recognizer.py.
