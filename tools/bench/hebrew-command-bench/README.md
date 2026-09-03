# hebrew-command-bench

Home of the **Recognizer**: the pipeline that turns a Hebrew utterance into a mission, a
planner-ready English command, a perception query, or a rejection. This directory holds the
component (`recognizer.py`), its benchmark (`bench.py`), and the measurements that shaped it.

## Sections

| section | what is in it |
|---|---|
| [The Recognizer](#the-recognizer-the-component-under-test) | the five-stage diagram and how the component works |
| [Scorecard](#scorecard--current-complete-recognizer-all-370-sentences-2026-09-02-night) | current results, all 370 sentences |
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
 │  [3] TRANSLATE                DictaLM-1.7B, CPU, ~200 ms      │
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

## Scorecard — current, complete Recognizer, all 370 sentences (2026-09-03, after the guard-unification pass)

`bench.py`. Raw: results/2026-09-03-recognizer.json (after the guard unification: one Hebrew
number composer for stage 2 and the guard, and-a-half composition on the English side). The
routing-kind refactor's byte-identical equivalence run is preserved as
results/2026-09-03-recognizer-routing-eq.json. Model-dependent sets carry a measured
±1-2 cross-run noise band: identical final translations flipped english<->reject across dicta
server restarts (j_pin_halfgate, s_feet_hold). Determinism is proven within one server
session, not across restarts.

| set | result | note |
|---|---|---|
| emergency (stage 0) | 6/6 (100%) | production regex, verbatim |
| std-190 commands | 186/187 (99%) | guard unification turned 2 false rejects (double-counted מטר אחד, uncombined וחצי) into correct missions; r_mis5 (return-trip sign) remains |
| verbose-54 commands | 50/53 (94%) | takeoff-chain rule fixed the verbose chain openers; 3 planner fails remain |
| perception-100 | 57/100 (57%) | DictaLM; TranslateGemma (82/100) deferred to the future E2E ASR system |
| military-20 | 9/20 (45%) | out of scope; -1 = stay-there-strip removes words the s_jump_point probe requires (mission is behaviorally correct; probe amendment = open owner call), -1 noise |
| ALL | 308/366 (84%) | rejects follow the ruling: unresolved numbers are read back to the user, not guessed |

Latency, same run. Spans: "Recognizer + planner" includes the Qwen3-VL planning call — the full
text-to-mission path; ASR, REST execution and TTS are not measured anywhere yet.
(Emergency and bypass answers are 0 ms — 79 of the 189 std commands
were answered by the bypass with no model call; their zeros are included in the end-to-end rows):

| set / stage | p25 | p50 | p75 | p95 | p99 | max (ms) |
|---|---|---|---|---|---|---|
| std190: Recognizer + planner (text in → mission out) | 0 | 160 | 269 | 580 | 711 | 873 |
| verbose: Recognizer + planner (text in → mission out) | 575 | 683 | 836 | 955 | 1110 | 1166 |
| perception: Recognizer only (VLM not simulated) | 81 | 105 | 121 | 165 | 265 | 338 |
| military: Recognizer only | 63 | 78 | 87 | 124 | 153 | 160 |

One stage-0 false positive: "עצור שם לעשר שניות" (a wait command containing the emergency word)
emergency-stops. Recommendation: keep the filter greedy — it fails in the safe direction.
Ruling pending.

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
| `bench.py` | ~290 | the measurement: default = full run, `--smoke`, `--audit`, `--cases`; `main()` at the bottom |
| `cases_commands.py` | | 190 standard + 54 verbose + 6 emergency cases + mission scorer |
| `cases_perception.py` | | 100 perception + 20 military cases + keyword scorer |
| `results/` | | date-stamped raw outputs; `HISTORY.md` holds the superseded rounds |

## Usage

Prerequisites: models installed (`tools/devenv/install-translation-models.sh`), llama-server
built under `build/release/shared/dji/bin`, GPU idle.

```
python3 bench.py            # THE measurement: all 370 sentences, ~2 min (audits first)
python3 bench.py --smoke    # 6 cases per set, ~15 s
python3 bench.py --audit    # offline checks only, no GPU
python3 bench.py --cases    # regenerate CASES.md
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

