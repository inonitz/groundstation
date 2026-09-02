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
| `run_dicta_server.sh` | DictaLM on CPU, port 18091 |

## Wiring (one line at assembly)

```python
from recognizer import Pipeline
pipe = Pipeline(wire, vlm_query=eyes.ask, say=voice.say)
router = Router(wire, on_complex=pipe.handle)
```

Servers: run_dicta_server.sh (CPU) + the already-resident Qwen3-VL on 18090.

## Sync rule (do not break it)

tools/bench/hebrew-command-bench is the development home: rules change there, get measured
there (`python3 bench.py`), and are then re-copied here. Files in this folder are never edited
in place. Measured state at copy time (2026-09-02): 301/364 overall, commands 98% at the
planner ceiling; scorecard in the bench README.
