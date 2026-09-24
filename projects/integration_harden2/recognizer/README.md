# recognizer/ — the Recognizer module inside integration_harden2

Hebrew utterance in, a `Routed` out. It parses EVERY sentence: the fast path (emergency,
manual, auto) goes to control before any model (owner ruling 2026-09-23). Anything the parser
cannot answer on its own takes ONE Gemma 4 E4B call, which reads the Hebrew directly and returns
one envelope, `{"kind","target_en","mission"}`: it routes the sentence AND plans the mission.
The Recognizer sends nothing and says nothing itself.

## Files

| file | role |
|---|---|
| `recognizer.py` | THE API: `Recognizer(control, vision, gemma, log).handle(text) -> Routed`, and `plan(he2)`, the one Gemma call (the benches measure it). Routes critical words and missions to control, clear / count / highlight / describe to the vision service (typed). The app shows and speaks `Routed.say`. |
| `parse.py` | the front half: `recognize_direct(he)` runs the steps below, in order, with no model |
| `fast_path.py` | the critical words (emergency, manual, auto) and the clear words, EN + HE |
| `bypass.py` | full-match sentences become missions with no model call (79 of 189 standard commands) |
| `guards.py` | the negation guard (before the model), the number guard and the planner-echo guard (after it) |
| `rewrites.py` | the Hebrew rewrites before the model, each rule with its positives and negatives |
| `numbers.py` | reading numbers (Hebrew and English); the rewrites and the number guard share it |
| `lexicon.py` | the HE->EN noun net under Gemma's `target_en` |
| `prompts.py` | prompts + grammars. LIVE: `UNIFIED_PROMPT` / `UNIFIED_GRAMMAR` / `UNIFIED_SHOTS`. `APP_PROMPT` / `REVISED_PROMPT` are the bench precursors. `python3 recognizer/prompts.py` regenerates PROMPTS.md. |

The rules are tested against their own evidence in `test/test_recognizer.py`.

## Live guards (bench-gated, see bench/hebrew-command-bench/README.md)

- The fast path (fast_path.py): EN + HE stop, manual and auto words act immediately, before any
  model. `EMERGENCY_RE` lives there, and only there.
- The Hebrew number idioms (numbers.py): חצי סיבוב = 180, סיבוב וחצי = 540 on both sides;
  ASR-glued punctuation and the ש clitic on חצי are read; a bare מטר means one meter. A number
  after מטר that starts with ו ("and") begins the next item (owner 2026-09-24).
- The planner-echo guard (guards.py `is_shot_echo`): a mission identical to one of the planner's
  own examples, whose numbers the input never carried, is refused and read back.
- Reject routing (in `UNIFIED_PROMPT`): a question about the drone (altitude/battery/flight
  time), a bare negation, or anything the actions cannot do -> `kind:"reject"`, read back in
  Hebrew.

Known gap (flagged 2026-09-24, not changed): a number word that starts with ו and begins a new
item ("וחמישה מטר") is not turned into digits, so the number guard does not see it. Changing that
changes the text Gemma receives, which needs a bench re-measure.

## Wiring (one line at assembly)

```python
from recognizer import Recognizer
recognizer = Recognizer(control, vision, gemma, log)   # the app builds it (app/main.py)
routed = recognizer.handle(text)       # -> Routed(kind, action, say); the app says routed.say
```

## Sync rule (do not break it)

This folder is the component's SINGLE home: the bench imports it from here and measures it in
place. Rules change HERE, then `python3 /root/groundstation/bench/hebrew-command-bench/unified_bench.py`
re-measures; a rule without a full re-measure is unverified. Measured baseline: 412/487
(2026-09-19); scorecard in the bench README.

Emergency words (owner ruling 2026-09-08): הפסק/הפסיקי/הפסיקו/תפסיק/תפסיקי/תפסיקו (not when
followed by ל+עקוב/הדגיש/סמן/הראות/צלם/ספור = a perception clear) and די only as the whole
utterance or its last word. Gate: 0 new fires on the dataset; tests in test_recognizer.py.
