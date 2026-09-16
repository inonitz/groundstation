# Recognizer benchmark — results

The Recognizer turns a Hebrew utterance into a mission, a planner-ready English command, a
perception query, or a rejection. This document is the authoritative result record for its
benchmark. The component lives in `projects/integration_harden2/recognizer/`. The benchmark
lives in `tools/bench/hebrew-command-bench/` (`unified_bench.py` is the current harness;
`cases_commands.py`, `cases_perception.py`).

## 1. Objective

The benchmark measures how well the Recognizer converts spoken Hebrew into a correct downstream
action. It exists to choose the stack, to gate every rule and prompt change against a fixed
dataset, and to prove that no change flies a drone it should have refused. It reports accuracy
per input class and latency per stage.

## 2. Setup

Dataset. The dataset holds 488 cases across five sets. Standard commands: 254. Verbose
commands: 63. Perception: 138. Military phraseology: 21. Emergency: 12. The cases live in
`cases_commands.py` (standard, verbose, emergency) and `cases_perception.py` (perception,
military). The unified run scores 487 of the 488; one standard case is not scored in that run.
Which case is excluded is (not recorded) in the sources.

Determinism. Temperature is 0. Determinism was verified once empirically: ten identical requests
produced one distinct output. Each case therefore runs once per arm, and a rerun on unchanged
code reproduces the result exactly. Accuracy confidence comes from case count.

Scoring. Command output is parsed from the wire schema (dx/dy/dz), then compared step by step
against the expected mission: action type, argument value, and step count. Perception output is
scored by keyword-group preservation; every group of accepted synonyms must appear. Emergency
is scored by the stage-0 regex. A reject on a must-not-fly case counts CORRECT. A reject on a
real command counts as a FAIL. This reject rule has been in force since 2026-09-08.

Execution. GPU use is strictly sequential: one model resident at a time, loaded and unloaded by
the harness. Every planning call carries a GBNF grammar, so malformed JSON is impossible.
Accuracy carries a Wilson 95% interval where recorded; paired comparisons use the exact McNemar
test; latency is reported as percentiles.

Current stack. The active chain is Gemma 4 E4B reading Hebrew directly, with thinking disabled.
There is no translator stage. One model call does routing, planning, and the SAM3 perception
phrase. The harness for this chain is `unified_bench.py`, run with `MVD_HOME=integration_harden2`
and `MVD_TRANSLATOR=none`.

## 3. Results

### Current scorecard

Source: `results/2026-09-11-negation-guard.json`, harden2 unified call, Gemma 4 E4B, thinking
off, 2026-09-11. Wilson intervals for this run are (not recorded).

| set | cases | correct | note |
|---|---|---|---|
| emergency (stage 0) | 12 | 12/12 | production regex, verbatim |
| standard commands | 253 | 236/253 | the unified prompt costs 9 standard cases against the planner-only lane: 6 rejects, 3 wrong routes |
| verbose commands | 63 | 59/63 | |
| perception | 138 | 103/138 | keyword-group scorer on "<kind> the <target>" |
| military | 21 | 0/21 | keyword-translation scorer; the unified call routes instead of translating, so this set is not comparable |
| ALL | 487 | 410/487 | |

Latency, per case, same run: p50 515 ms, p95 1070 ms. Wall time 243 s.

### Negation guard — adversarial set

The negation guard (`recognizer.negation_only`) is deterministic. It runs after the bypass and
before the model. It rejects a pure action-negation that carries no positive order. Dataset:
`projects/integration_harden2/test/test_negation_guard.py`.

| set | n | result |
|---|---|---|
| must-refuse (pure negation) | 24 | 24/24 rejected |
| must-pass (a real order present) | 25 | 25/25 passed, 0 false fires |

Three tests green. Against the same-code baseline the guard changed 0 cases and produced 0 false
fires, so the bench total stays 410/487. At temperature 0 the model already rejected every pure
negation; the guard makes those rejections deterministic rather than model-dependent.

### Evolution — one row per milestone

Each row is one measured milestone with its headline number. Full raw data for every row is in
this directory. Earlier rows used different datasets and reject rules, so compare within a row,
not across rows. The standard-command set is denoted std-N for its size at that date.

| date | milestone | headline result |
|---|---|---|
| 2026-09-01 | Round 3 — translator selection, 190 commands, 8 arms | best pipeline dicta→qwen + planner few-shot 176/190 (93%); English ceiling 185/190 (97%); DictaLM selected |
| 2026-09-01 | Round 4 — planner prompt, 190 commands, production wire schema | revised prompt, Qwen3-VL, DictaLM Hebrew 180/190 (95%); prompt lever 56%→94% on the phone engine |
| 2026-09-01 | Round 5 — multi-hop perception, 45 cases, translation only | TranslateGemma 38/45 (84%); DictaLM 31/45 (69%); Qwen3-VL 19/45 (42%) |
| 2026-09-01 | Round 6 — combined, 190 commands + 100 perception, 6 arms | split arm (DictaLM commands, TranslateGemma perception) 179/190 (94%) commands, 78/100 (78%) perception; control ceiling 99%/100% |
| 2026-09-02 | Direct-Hebrew planning (DictaLM plans raw Hebrew) | 168/190 (88.4%), below the dicta→qwen pipeline 94.2% (McNemar p=0.043) |
| 2026-09-02 | Regex bypass, offline replay (7 patterns, 45% coverage) | dicta-direct + bypass 92.6%; dicta→planner + bypass 95.3% |
| 2026-09-02 | Sieve ablation (number check + digit patch + EN rewrite) | verbose 69%→91%; std-190 94%→95.3% |
| 2026-09-02 | Pre-residue scorecard, DictaLM, 364 cases | 301/364 (83%) |
| 2026-09-03 | Post-residue + guard-unification, DictaLM, 366 cases | 308/366 (84%) |
| 2026-09-07 | Live desk cases added, DictaLM, 382 cases | 323/382 (85%) |
| 2026-09-07 | Translator selection — Hy-MT2-Q4 chosen as the deployed translator | few-shot is the lever; TranslateGemma 90% accuracy champion but VRAM-blocked; Hy-MT2-Q4 is the deployable fit |
| 2026-09-08 | Full Recognizer, 413 cases, new reject rule | DictaLM 346/412 (84%); Hy-MT2-Q4 348/412 (84%); Gemma 4 translator, thinking off 389/412 |
| 2026-09-08 | Dataset → 488; Hy-MT2→Qwen 488 gate | 420/487 |
| 2026-09-08 | Unified Gemma 4 alone, harden2 call, re-scored | 415/487 |
| 2026-09-10 | Negation baseline, unified Gemma 4, 488 | 410/487 |
| 2026-09-11 | Negation guard, iterations A1–A7 + final | 410/487; 0 cases changed vs baseline; 0 false fires; 24-refuse / 25-pass adversarial set |
| 2026-09-11 | Purge stage 1 | 410/487, no scoring change |
| 2026-09-12 | Trace/replayer build | 410/487, no scoring change |

## 4. Analysis

1. The current stack scores 410/487. Commands are strong: emergency 12/12, standard 236/253,
   verbose 59/63. Perception is the weak set at 103/138. Military scores 0/21 only because the
   unified call routes those inputs instead of translating them; the keyword-translation scorer
   does not apply to the current chain, so that set is not a meaningful measure here.

2. Few-shot examples in the planner prompt were the largest single lever found. Round 3 measured
   about +9 to +10 points from few-shots. Round 4 measured the prompt itself moving the phone
   engine from 56% to 94% with no model change.

3. Direct-Hebrew planning beat the translation path. The project first shipped a translator
   (DictaLM, then Hy-MT2-Q4). On 2026-09-08, Gemma 4 E4B reading Hebrew directly with thinking
   off scored above the translator pipelines and removed a whole stage. The translator was
   dropped from the deployed chain. Disabling Gemma's thinking was itself a lever: the translator
   arm rose from 359/412 to 389/412 and narrations fell to zero once thinking was off.

4. The register matters more than raw model size. DictaLM led on commands but degraded with
   perception reference depth. TranslateGemma led on perception but shifted imperatives into
   narration on commands. No single translator fit both halves, which is why Round 6 favored a
   split and why the project ultimately moved to a single direct-Hebrew planner.

5. The negation guard is defense-in-depth, not a score lever. It subtracts the negated verb that
   a trigger governs, per clause, after splitting on connectors. A positive verb that survives
   the subtraction is a real order, so the clause passes. It changed 0 cases because the model
   already refused pure negations at temperature 0. Its value is that the refusal is now
   deterministic and covered by 24 must-refuse and 25 must-pass adversarial cases with 0 false
   fires.

6. The planner sets the ceiling, not the translator. The perfect-English control (hand-written
   reference straight to the planner) scored 246/258 on commands on 2026-09-08. Most of the lost
   cases are verbose chains whose literal wording becomes extra delay or wait steps. A faithful
   translator inherits that loss; a paraphrasing one hides it.

7. Determinism holds within one server session, not across restarts. Model-dependent sets carry
   a measured cross-run noise band of about one to two cases across server restarts, where an
   identical final translation flipped between a valid English output and a reject.

## 5. Conclusions and open items

1. Deployed stack: Gemma 4 E4B, direct Hebrew, thinking off, no translator, SAM3 for the
   perception phrase. One model call per utterance.
2. Headline result: 410/487, p50 515 ms, p95 1070 ms.
3. The negation guard is closed: deterministic, adversarially tested, 0 false fires.
4. Open — perception at 103/138 is the weakest set and the next target for improvement.
5. Open — one stage-0 false positive is unresolved: a wait command that contains the emergency
   word emergency-stops. The standing recommendation is to keep the filter greedy, because it
   fails in the safe direction. No owner ruling yet.
6. Open — which single standard case the unified run excludes (487 scored of 488 filed) is
   (not recorded).

## Superseded

This document replaces the following dated fragment files. They may be deleted.

- `2026-09-01-round5-dump.md`
- `2026-09-01-round6-dump.md`
- `2026-09-01-perception-dump.md`
- `2026-09-01-test-evidence.md`
- `2026-09-02-bench-dump.md`
- `2026-09-02-slang-dump.md`
- `2026-09-08-unified-gemma4.md`
- `2026-09-10-negation-baseline.md`
- `2026-09-11-negation-guard.md`
- `2026-09-11-negation-guard-a7.md`
- `2026-09-11-negation-guard-final.md`
- `2026-09-11-purge-stage1.md`
- `2026-09-12-trace-build.md`

The superseded development rounds remain archived in `HISTORY.md`. The raw `*.json` outputs stay
in this directory as the data behind every table.
