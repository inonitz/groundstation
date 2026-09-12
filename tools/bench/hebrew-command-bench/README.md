# hebrew-command-bench

Home of the **Recognizer**: the pipeline that turns a Hebrew utterance into a mission, a
planner-ready English command, a perception query, or a rejection. This directory holds the
component (`recognizer.py`), its benchmark (`bench.py`), and the measurements that shaped it.

## Sections

| section | what is in it |
|---|---|
| [The Recognizer](#the-recognizer-the-component-under-test) | the five-stage diagram and how the component works |
| [Scorecard](#scorecard--current-complete-recognizer-all-413-sentences-2026-09-08) | current results, all 413 sentences, both translators |
| [Rulings in force](#rulings-in-force-owner-2026-09-02) | the decisions that define the component |
| [Files](#files) | what each file is |
| [Usage](#usage) | how to run and modify |
| [Methodology](#methodology) | how everything is measured |
| [results/HISTORY.md](results/HISTORY.md) | development history, rounds 1-6 — superseded, archived |

## The Recognizer (the component under test)

Naming, fixed 2026-09-02: the whole pipeline below is the **Recognizer**. It contains five
stages. Stages 1, 2, 4, 5 are deterministic code (collectively "the sieve"). Stage 3 is the
translator model. The planner is NOT part of the Recognizer; it is the next system in the chain.

System context:  ASR  =>  RECOGNIZER  =>  VLM/LLM (planner or perception)  =>  REST API (MSDK server)
(whether ASR folds into the Recognizer is an open naming decision; the emergency stop tier runs
BEFORE the Recognizer and never waits on it)

```
                         THE RECOGNIZER
 ┌───────────────────────────────────────────────────────────────┐
 │  Hebrew text (from ASR)                                       │
 │      │                                                        │
 │  [1] BYPASS                                                   │
 │      whole sentence matches a known pattern?                  │
 │      → yes: emit mission JSON now, skip everything below      │
 │      → no: continue                                           │
 │      │                                                        │
 │  [2] HEBREW REWRITES          (edits the Hebrew)              │
 │      number words → digits (עשרים → 20)                       │
 │      trouble words → English (כתום → orange)                  │
 │      missing verbs, acronyms, homographs                      │
 │      │                                                        │
 │  [3] TRANSLATE                DictaLM (CPU) | Hy-MT2-Q4 (GPU)  │
 │      │                                                        │
 │  [4] OUTPUT GUARDS            (checks the English)            │
 │      copy check → redo without examples                       │
 │      number check → redo, then direct fix                     │
 │      unresolved → REJECT, tell the user what was recognized   │
 │      │                                                        │
 │  [5] ENGLISH REWRITES         (edits the English)             │
 │      "turn right 3 meters" → "move right 3 meters"            │
 │      │                                                        │
 │      │                                                        │
 │  [6] ROUTE                    (the Recognizer's decision)     │
 │      mission JSON     → REST API, execute                     │
 │      command English  → planner (Qwen3-VL)                    │
 │      perception Engl. → VLM (Qwen3-VL + image)                │
 │      rejection        → read back to user (TTS, TODO)         │
 │      built: deterministic route() in recognizer.py —          │
 │      100/100 perception, 240/243 commands, movement wins      │
 └───────────────────────────────────────────────────────────────┘
```


Status: the component lives in projects/integration_harden/recognizer/ (single home),
integrated behind the router; this benchmark imports and measures it in place.

## Scorecard — current, complete Recognizer, all 413 sentences (2026-09-08)

`bench.py`, both translators on the SAME Recognizer code. Raw: results/2026-09-08-recognizer-dicta-post2.json
(DictaLM) and results/2026-09-08-recognizer-hymt2-post2.json (Hy-MT2-Q4). Code under test on 2026-09-08:
the half-turn guard, the clockwise inline rules, the tokenizer fix (ASR-glued punctuation, ש clitic on חצי),
סיבוב וחצי = 540, the bare-מטר -> מטר אחד rewrite, the stage-4b answer-mode guard, and the planner
few-shot echo guard; the highlight parser gained follow / focus on / emphasize. Scoring change the same day:
a reject on a must-not-fly case counts CORRECT (nothing flew, the user heard the read-back) and a reject on a
real command counts as a FAIL; before, both were dropped from n. DictaLM is the CPU fallback path;
Hy-MT2-Q4 is the deployed translator (ruling 2026-09-07), selected with `MVD_TRANSLATOR=hymt2`.

| set | DictaLM (CPU path) | Hy-MT2-Q4 (deployed) | note |
|---|---|---|---|
| emergency (stage 0) | 7/7 (100%) | 7/7 (100%) | production regex, verbatim |
| std-204 commands | 202/203 (99.5%) | 197/203 (97%) | Hy-MT2: possibility/past phrasing the planner refuses (r_takeoff2/3, r_land4, r_alt10); both keep r_mis5 (return-trip sign); the land traps are now CORRECT-reject on DictaLM |
| verbose-54 commands | 50/54 (93%) | 44/54 (81%) | Hy-MT2 translates preambles literally and "שנייה" as a second -> extra delay |
| perception-128 | 78/128 (61%) | 91/128 (71%) | DictaLM answers questions (now rejected by the answer-mode guard, read back); Hy-MT2 answer-mode 0 |
| military-20 | 9/20 (45%) | 9/20 (45%) | out of scope |
| ALL | 346/412 (84%) | 348/412 (84%) | |

Gemma 4 E4B as the translator (2026-09-08, `--translator gemma4`, v1 prompt): 7/7, 198/203, 26/54, 116/128, 12/20 = 359/412 (+11 vs Hy-MT2: perception +25, verbose -18); 57 outputs narrate ("The user wants to translate...") -> 23 answer-mode rejects, one unsafe flip (r_neg4 negation flown). `--prompt tgemma` (TranslateGemma's instruction, zero-shot): 171/412, narrates almost everywhere, invalid. With `enable_thinking=false` (GEMMA4_EXTRA, 2026-09-08 16:40): 202/203, 51/54, 117/128, 12/20 = 389/412, narrations 0/413, unsafe flips vs Hy-MT2: 0. Raw: results/2026-09-08-recognizer-gemma4-xlate-{v1,v1-nothink,tgemma}.json.

Dataset = 488 since 2026-09-08 17:20 (the live-test-75 v2 filed by set). Hy-MT2 488 gate: 12/12, 247/253, 51/63, 100/138, 10/21 = 420/487; register rewrites lost 0 / won 4 on the common 413. Gemma 4 ALONE (`--planner gemma4 --direct-he`): thinking OFF 318/328 commands, thinking ON (`GEMMA4_THINK=1`) 314/328. Raw: results/2026-09-08-recognizer-{hymt2-488-gate,gemma4-direct-nothink,gemma4-direct-think}.json. `MVD_HOME=integration_harden2` points the bench at harden2.

Unified harden2 call (`unified_bench.py`, Gemma 4 E4B thinking off — the active single-model chain, 2026-09-11): 410/487 = emergency 12/12, std190 236/253, verbose 59/63, perception 103/138, military 0/21. Latency p50 515 ms, p95 1070 ms. Raw: results/2026-09-11-negation-guard.json.

Negation guard (`recognizer.negation_only`, deterministic, runs after the bypass and before the GPU). It rejects a pure action-negation that carries no positive order. It splits on `, . ; ואז אבל ורק אולם`, then per clause it removes the negated verb that the trigger (`אל ת...`, `בלי ל...`, `לא ל...`) governs; an order verb that survives the removal is a real order, so the clause passes. A bare number+unit counts as an order only when the clause has no negation. The positive-imperative list includes continue/slow/speed (תמשיך/המשך, תאט/האט, תאיץ/האץ) so a leading manner-negation like "בלי לעצור תמשיך ישר" passes. Dataset: test/test_negation_guard.py, 24 must-refuse + 25 must-pass, 3 tests green. The must-pass set spans negation-then-order both directions, the perception+negation trap ("שים עין ... ואל תרד"), clause-spanning connectors, and questions. The guard is defense-in-depth: at temp 0 Gemma already rejected every pure negation, so the bench total is unchanged (410/487, 0 changed cases vs the same-code baseline, 0 false fires). The gain is that these rejections are now deterministic, not model-dependent. Raw: results/2026-09-11-negation-guard-a7.json.

Control, same day (`bench.py --perfect-en`): the hand-written reference English straight to the planner
scores std 201/204 and verbose 45/54 (246/258). The planner alone loses 12 of 258; nine are verbose chains
whose literal wording ("a second after that", "Wait, make sure you are ready", "and also") the planner turns
into delay/wait steps or merges. Hy-MT2 inherits those (faithful translation); DictaLM paraphrases them away.
Raw: results/2026-09-08-perfect-en.json.

Latency, DictaLM run (GPU-reference serving in the bench; the desk test serves it on the CPU):

| set / stage | p25 | p50 | p75 | p95 | p99 | max (ms) |
|---|---|---|---|---|---|---|
| std190: Recognizer + planner | 0 | 190 | 273 | 575 | 738 | 880 |
| verbose: Recognizer + planner | 564 | 678 | 840 | 958 | 1077 | 1110 |
| perception: Recognizer only | 76 | 100 | 123 | 173 | 346 | 602 |
| military: Recognizer only | 64 | 78 | 91 | 123 | 152 | 159 |

Latency, Hy-MT2-Q4 run (GPU, -c 4096 in the bench; the deployment script serves -c 512 -np 1):

| set / stage | p25 | p50 | p75 | p95 | p99 | max (ms) |
|---|---|---|---|---|---|---|
| std190: Recognizer + planner | 0 | 130 | 262 | 544 | 708 | 901 |
| verbose: Recognizer + planner | 581 | 666 | 756 | 849 | 946 | 974 |
| perception: Recognizer only | 82 | 110 | 136 | 173 | 204 | 336 |
| military: Recognizer only | 80 | 100 | 108 | 141 | 185 | 196 |

One stage-0 false positive, unchanged: "עצור שם לעשר שניות" (a wait command containing the
emergency word) emergency-stops. Recommendation: keep the filter greedy — it fails in the safe
direction. Ruling pending.

Gates behind this scorecard (`compare_runs.py`, per-case verdict flips against same-code baselines):
DictaLM 339 -> 346, 14 outputs changed, 5 flips all reject-on-trap or the land trap fixed (l_land_going:
planner LANDED -> CORRECT-reject); Hy-MT2 345 -> 348, 3 outputs changed, 0 flips against.
Text-mode runs of the 75-sentence live list (run_list.py, no mic): DictaLM 45 pass / 7 fail / 23 review,
Hy-MT2 36 / 16 / 23 — Hy-MT2 loses 8 lines to its past-tense/possibility register.

## Rulings in force (owner, 2026-09-02)

1. No integration until the component is declared closed; integration now approved.
2. Revised planner prompt adopted. Model split NOT adopted (VRAM); TranslateGemma deferred to
   the future E2E ASR system.
3. Emergency filter is stage 0 INSIDE the Recognizer.
4. Routing (mission / command / perception / reject) is the Recognizer's decision.
   The routing classifier is an integration build item.
5. Unresolved number guard = REJECT and read back to the user what was recognized.
6. TTS inside the Recognizer: TODO, revisit if it becomes shared.

## Files

| file | lines | role |
|---|---|---|
| (component) | | single home: projects/integration_harden/recognizer/ — the bench imports and measures it in place |
| `bench.py` | ~300 | the measurement: default = full run, `--smoke`, `--audit`, `--cases`, `--translator dicta\|hymt2`, `--tag`; `main()` at the bottom |
| `compare_runs.py` | | per-case diff of two raw JSONs: per-set counts, every changed output, every verdict flip |
| (whole-system) | | run_list.py (text-mode and audio-replay list runs) lives in tools/bench/whole-system since 2026-09-08 |
| `cases_commands.py` | | 204 standard + 54 verbose + 7 emergency cases + mission scorer |
| `cases_perception.py` | | 128 perception + 20 military cases + keyword scorer |
| `results/` | | date-stamped raw outputs; `HISTORY.md` holds the superseded rounds |

## Usage

Prerequisites: models installed (`tools/devenv/install-translation-models.sh`), llama-server
built under `build/release/shared/dji/bin`, GPU idle.

```
python3 bench.py                              # THE measurement: all 413 sentences, ~2 min (audits first); DictaLM
python3 bench.py --translator hymt2 --tag hymt2  # same, Hy-MT2-Q4 resident (the deployed translator)
python3 bench.py --smoke                      # 6 cases per set, ~15 s
python3 bench.py --audit                      # offline checks only, no GPU
python3 bench.py --cases                      # regenerate CASES.md
python3 compare_runs.py results/A.json results/B.json   # gate a Recognizer change: per-case diff + verdict flips
python3 bench.py --perfect-en [--planner gemma4]         # control: reference English straight to the planner (its ceiling)
python3 bench.py --planner gemma4 --direct-he --tag x     # no translator: Hebrew after stages 0-2 goes to the planner (commands only)
python3 bench.py --translator hymt2 --prompt v2           # translator prompt variant (v2 = measured and rejected 2026-09-08)
python3 ../whole-system/run_list.py ../../desk-test/live-test-75.md --translator hymt2   # a live-test list as text; --from-clips <session> = audio replay (whole-system lane 1)
python3 ../../../projects/integration_harden/recognizer/recognizer.py   # self-test
```
The superseded lanes (rounds 1-6, the ablations) were deleted per the tool-lifetime rule;
their code is in git history and their results in results/HISTORY.md.

Add cases in the two cases files (format contracts in their docstrings), then rerun. Prompts
change only in prompts.py. Recognizer rules change only in recognizer.py; every rule carries
adversarial negatives and the self-test must stay clean.

## Methodology

These invariants hold for every experiment below unless a section states otherwise.

- **Sampling.** Temperature 0. Determinism was verified empirically (10 identical requests
  produced 1 distinct output), so each case runs once per arm and a rerun on unchanged code
  reproduces results exactly. Accuracy confidence comes from case count.
- **Statistics.** Accuracy is reported with a Wilson 95% interval. Paired comparisons between
  arms use the exact McNemar test on per-case outcomes. Latency is reported as
  p25/p50/p75/p95/p99/max over per-case wall times.
- **Execution.** Strictly sequential GPU use: one model resident at a time, loaded and unloaded
  by the harness. Every mission-planning call carries a GBNF grammar that makes malformed JSON
  impossible. llama-server stderr is retained at /tmp/llama-server-bench.log.
- **Command scoring.** Planner output is parsed, normalized from the wire schema (dx/dy/dz) to
  scorer keys, and compared step-by-step against the expected mission: action type, argument
  value (exact, sign-only, or magnitude-only where the phrasing is qualitative), and step count.
- **Perception scoring.** Perception commands are not planned; in the production system they
  route to the VLM. The measured stage is Hebrew-to-English translation, scored by keyword-group
  preservation: every group of accepted synonyms must appear in the output. This scorer cannot
  detect relation inversion ("A next to B" rendered as "B next to A"); the per-run dump file
  exists for manual review of that class. Each perception case carries a hand-written English
  reference that satisfies its own groups (verified by `--audit`), so the reference-scoring
  control arm measures 100% unless the scorer itself regresses.
- **Terminology.** An *arm* is one configuration under test. *perfect-EN* denotes feeding the
  hand-written English reference to the planner, isolating planner quality from translation.
  The *sieve* is the sieve: the deterministic layer around the translator: Hebrew-to-Hebrew
  rewrites before it, English-to-English rewrites after it, and output validity checks
  (`recognizer.py`). The *regex bypass* is a separate layer of strict full-match patterns that answer
  a sentence deterministically without any model call; on no match the sentence passes through
  unmodified.

