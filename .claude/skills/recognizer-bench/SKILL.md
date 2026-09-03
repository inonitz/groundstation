---
name: recognizer-bench
description: Use when working on the Recognizer, its sieve rules, or the Hebrew command benchmark - running measurements, adding cases or rules, or verifying changes to projects/integration_harden/recognizer or tools/bench/hebrew-command-bench.
---

# Working on the Recognizer and its benchmark

The component lives ONLY in `projects/integration_harden/recognizer/` (recognizer.py = stages,
pipeline.py = glue, prompts.py, llama.py). The benchmark in `tools/bench/hebrew-command-bench/`
imports it in place. Scorecard and method: that benchmark's README; history: results/HISTORY.md.

## Commands

```
python3 tools/bench/hebrew-command-bench/bench.py            # full measurement, ~2 min, audits first
python3 tools/bench/hebrew-command-bench/bench.py --smoke    # 6 cases per set, ~15 s
python3 tools/bench/hebrew-command-bench/bench.py --audit    # offline checks, no GPU
python3 projects/integration_harden/recognizer/recognizer.py # component self-test, no GPU
python3 -m pytest projects/integration_harden/test/ -q       # 26 wiring tests, models faked
```

## The development loop (never skip a step)

1. Run the measurement. Attribute every failure to a stage and a cause; the raw JSON keeps
   every input/output pair.
2. A new rewrite rule requires: measured evidence (>=2 failures), positives, adversarial
   negatives (lookalike words it must NOT touch), and a clean self-test. Zero false fires is
   the ship gate.
3. Amend, then RE-RUN THE FULL MEASUREMENT and compare per-set counts to the previous run.
   Temp-0 makes unchanged code reproduce exactly; any diff is your change. Do not trust a fix
   without this — a prompt fix once "worked" in the summary and had fixed nothing.
4. Update the README scorecard IN PLACE. State a duration estimate before any GPU run.

## Facts that keep biting

- DictaLM passes Latin tokens through verbatim (basis of the inline-English rules) and digits
  always survive where Hebrew number-words corrupt.
- DictaLM echoes its few-shot examples on out-of-domain input and hallucinates numbers when
  answering instead of translating — that is what the copy guard and number guard catch, and
  why an unresolved number flag REJECTS (owner ruling) instead of guessing.
- Keyword scoring cannot detect relation inversion; review the dump file for that class.
- Hebrew clitic prefixes (ו/ב/ל/ה) break naive \b boundaries; number-words compose (עשרים
  וחמישה=25) and the number can FOLLOW the unit (מטר אחד=1). שנייה and מעלה are homographs —
  never treat them as bare units.
- The emergency regex source of truth is the Recognizer's stage 0 (EMERGENCY_RE in
  recognizer/recognizer.py); control/commands.py imports it. Greedy by ruling.
