# recognizer/ — the Recognizer module inside integration_harden2

Hebrew utterance in, ONE Gemma 4 E4B call out. harden2 (2026-09-08+): the model reads the Hebrew
directly (no translator) and returns one envelope, `{"kind","target_en","mission"}`, which routes
the utterance AND plans the mission at once. Wired as the Router's on_complex callback; the router's
own safety tiers (emergency, override, resume) are untouched.

kind is one of: `mission` (fly), `highlight` / `count` / `describe` (perception, `target_en` names
the object in English for SAM3), or `reject` (spoken back in Hebrew).

## Files

| file | role |
|---|---|
| `pipeline.py` | THE LIVE ENTRY: `Pipeline(wire, vlm_query, say).handle(text)`, the Router's on_complex. Runs `recognize_direct()` then the ONE Gemma call and acts on the result (fly / perceive / reject). |
| `recognizer.py` | the Hebrew front half of the component: `recognize_direct()` = stage 0 emergency, stage 1 bypass (full-match sentences -> missions, no model), stage 2 Hebrew rewrites, then hands the cleaned Hebrew to the Gemma call. The English stages 3-6 (translate, output guards, English rewrites, English routing) are LEGACY/bench-only — the live path skips translation. `python3 recognizer.py` = self-test. |
| `prompts.py` | prompts + grammars. LIVE: `UNIFIED_PROMPT` / `UNIFIED_GRAMMAR` / `UNIFIED_SHOTS` (Hebrew in, `{kind,target_en,mission}` out, 8 actions). `APP_PROMPT` / `REVISED_PROMPT` are the bench precursors (see PROMPTS.md). |
| `llama.py` | the chat call and (for tools) the server context manager |
| `trace.py` | per-utterance JSONL recorder -> <repo>/logs/traces/ (gitignored; fixed path) |
| `selftest.py` | offline self-test harness for the recognizer |

`run_dicta_server.sh` / `run_hymt2_server.sh` are LEGACY translator-server scripts from the old
two-model path. They are not on the live path (one resident Gemma does typing, planning and
translation) and are kept only for the bench's historical two-model comparison.

## Live guards (bench-gated, see bench/hebrew-command-bench/README.md)

- Stage 0 emergency filter: EN + HE stop words act immediately, before any model. This regex
  (`EMERGENCY_RE`) is the source of truth; control/commands.py imports it.
- Stage 2 Hebrew number idioms: חצי סיבוב = 180, סיבוב וחצי = 540 on both sides; ASR-glued
  punctuation and the ש clitic on חצי are read; a bare מטר becomes מטר אחד. All on the Hebrew side,
  before the model — no translation hop.
- Planner few-shot echo guard (pipeline.py `is_shot_echo`): a mission identical to one of the
  planner's own examples, whose numbers the input never carried, is refused and read back.
- Reject routing (in `UNIFIED_PROMPT`): a question about the drone (altitude/battery/flight time), a
  bare negation, or anything the actions cannot do -> `kind:"reject"`, read back in Hebrew.

## Wiring (one line at assembly)

```python
from recognizer import Pipeline
pipe = Pipeline(wire, vlm_query=eyes.ask, say=voice.say)
router = Router(wire, on_complex=pipe.handle)
```

Server: ONE resident Gemma 4 E4B on `LLAMA_SERVER_PORT` (18090) does typing, planning, translation
and the VLM answer. The Pipeline starts no servers.

## Sync rule (do not break it)

This folder is the component's SINGLE home (dedup ruling): the bench imports it from here and
measures it in place. Rules change HERE, then
`python3 /root/groundstation/bench/hebrew-command-bench/unified_bench.py` re-measures; a rule
without a full re-measure is unverified. Measured baseline: 412/487 (2026-09-19); scorecard in the
bench README.

Stage 0 emergency words (owner ruling 2026-09-08): הפסק/הפסיקי/הפסיקו/תפסיק/תפסיקי/תפסיקו (not when
followed by ל+עקוב/הדגיש/סמן/הראות/צלם/ספור = a perception clear) and די only as the whole utterance
or its last word. Gate: 0 new fires on the dataset; tests in test_recognizer.py.
