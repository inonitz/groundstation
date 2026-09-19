# hebrew-command-bench

Home of the **Recognizer**: the pipeline that turns a Hebrew utterance into a mission, a
perception query, or a rejection, then hands the survivors to ONE Gemma-4-E4B call that routes,
plans, names the target, and answers. This directory holds the benchmark that measures it; the
component itself lives in `projects/integration_harden2/recognizer/`.

The current harness is `unified_bench.py`. `bench.py` is the retired translated-path harness,
kept only for shared infra (case loading, the `--cases` regen of CASES.md, `compare_runs.py`).

## Sections

| section | what is in it |
|---|---|
| [The Recognizer](#the-recognizer-the-component-under-test) | the current pipeline and how the component works |
| [Scorecard](#scorecard--current) | the current baseline; full history in results/RESULTS.md |
| [Rulings in force](#rulings-in-force-owner-2026-09-02) | the decisions that define the component |
| [Files](#files) | what each file is |
| [Usage](#usage) | how to run and modify |
| [Methodology](#methodology) | how everything is measured |
| [results/RESULTS.md](results/RESULTS.md) | authoritative result record + evolution table |
| [results/HISTORY.md](results/HISTORY.md) | development history, rounds 1-6 — superseded, archived |

## The Recognizer (the component under test)

Naming, fixed 2026-09-02: the whole front half below is the **Recognizer**. It is pure text
processing — it owns no model and starts no server. harden2 (2026-09-08) reads Hebrew DIRECTLY:
after the Recognizer's deterministic stages, ONE Gemma-4-E4B call does routing, planning, target
naming and the answer. There is NO translator. The old TRANSLATE stage (DictaLM / Hy-MT2-Q4) and
the deterministic English `route()` are deleted and do not run.

System context:  ASR  =>  RECOGNIZER (stages 0-2 + guards)  =>  Gemma 4 E4B (one call)  =>  REST API / SAM3
(the emergency stop tier runs BEFORE the Recognizer and never waits on it.)

```
                         THE RECOGNIZER  +  the one Gemma call
 ┌───────────────────────────────────────────────────────────────┐
 │  Hebrew text (from ASR)                                        │
 │      │                                                         │
 │  [0] EMERGENCY FILTER   stop words halt immediately, no model  │
 │      │                                                         │
 │  [1] BYPASS             whole sentence matches a known pattern? │
 │      → yes: emit the mission now, no model call                │
 │      │                                                         │
 │  [·] NEGATION GUARD     pure action-negation, no positive      │
 │      order → REJECT, read back to the user                     │
 │      │                                                         │
 │  [2] HEBREW REWRITES    (apply_he, edits the Hebrew)           │
 │      number words → digits (עשרים → 20)                        │
 │      trouble words → English (כתום → orange)                   │
 │      │                                                         │
 │      ▼  returns ("direct", he2, flags)                         │
 │  ┌───────────────────────────────────────────────────────┐   │
 │  │  ONE Gemma-4-E4B call (_plan2, thinking off)            │   │
 │  │  reads the Hebrew, emits {kind, target_en, mission}     │   │
 │  │    kind = mission    → /c/fly actions, execute          │   │
 │  │    kind = highlight  → SAM3 highlight the target        │   │
 │  │    kind = count      → SAM3 count the target            │   │
 │  │    kind = describe   → VLM describe the scene           │   │
 │  │    (else)            → REJECT, read back                │   │
 │  └───────────────────────────────────────────────────────┘   │
 └───────────────────────────────────────────────────────────────┘

Gemma emits these mission actions: takeoff, land, fly_by, spin_by, delay, gimbal_pitch, home,
wave. Greeting → wave; follow / track / mark → highlight. scan_ground was tried, then removed
(2026-09-19). fly_by is body-frame (dx+ forward, dy+ right, dz+ up); spin_by degrees, clockwise
positive.
```

Status: the component lives in `projects/integration_harden2/recognizer/` (single home),
integrated behind the router; this benchmark imports and measures it in place.

## Scorecard — current

Baseline 2026-09-19, tag `gemma4-routing-noscan` (scan_ground removed). One Gemma-4-E4B call,
thinking off. Source: `results/2026-09-19-gemma4-routing-noscan-2026-09-19.json`.

| set | cases | correct | note |
|---|---|---|---|
| emergency (stage 0) | 12 | 12/12 | production regex, verbatim |
| standard commands | 253 | 240/253 | one of the 254 filed standard cases is not scored in the unified run |
| verbose commands | 63 | 59/63 | |
| perception | 138 | 101/138 | keyword-group scorer on "<kind> the <target>" |
| military | 21 | 0/21 | the unified call routes instead of translating; the keyword-translation scorer does not apply, so this set is not comparable for harden2 |
| ALL | 487 | 412/487 | prior 410/487 on 2026-09-17 |

Latency, same run: p50 551 ms, p95 1131 ms; wall 260 s. The full evolution table and every
superseded scorecard (DictaLM / Hy-MT2-Q4 translator arms, the 2026-09-08 Gemma-translator
ablations, the translator-era latency tables) live in `results/RESULTS.md` and `results/HISTORY.md`.

Open item, unchanged: one stage-0 false positive — a wait command containing the emergency word
("עצור שם לעשר שניות") emergency-stops. The filter stays greedy: it fails in the safe direction.

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

| file | role |
|---|---|
| (component) | single home: projects/integration_harden2/recognizer/ — the bench imports and measures it in place |
| `unified_bench.py` | THE current harness: `recognize_direct` + the one Gemma `_plan2` call, all five sets, ~2 min, GPU |
| `bench.py` | retired translated-path harness; kept for shared infra: case loading and `--cases` (regenerates CASES.md) |
| `compare_runs.py` | per-case diff of two raw JSONs: per-set counts, every changed output, every verdict flip |
| (whole-system) | run_list.py (text-mode and audio-replay list runs) lives in tools/bench/whole-system since 2026-09-08 |
| `cases_commands.py` | 254 standard + 63 verbose + 12 emergency cases + mission scorer |
| `cases_perception.py` | 138 perception + 21 military cases + keyword scorer |
| `results/` | date-stamped raw outputs; `RESULTS.md` is the authoritative record, `HISTORY.md` holds the superseded rounds |

## Usage

Prerequisites: models installed, llama-server built under `build/release/shared/dji/bin`, GPU idle.

```
MVD_HOME=integration_harden2 python3 unified_bench.py                 # THE measurement: all five sets, one Gemma call, ~2 min
MVD_HOME=integration_harden2 python3 unified_bench.py --smoke         # 5 cases per set, quick
MVD_HOME=integration_harden2 python3 unified_bench.py --tag <name>    # stamp the raw outputs
python3 compare_runs.py results/A.json results/B.json                 # gate a change: per-case diff + verdict flips
python3 bench.py --cases                                              # regenerate CASES.md from the cases_*.py files
python3 projects/integration_harden2/recognizer/recognizer.py        # component self-test, no GPU
```
`MVD_HOME` is a bench-only variable: `unified_bench.py` reads it, but the harden2 config module no
longer does (harden2 is the only system; launchers hardcode it).

Add cases in the two cases files (format contracts in their docstrings), then rerun. Prompts change
only in prompts.py. Recognizer rules change only in recognizer.py; every rule carries adversarial
negatives and the self-test must stay clean.

## Methodology

These invariants hold for every measured run.

- **Sampling.** Temperature 0. Determinism was verified empirically (ten identical requests
  produced one distinct output), so each case runs once and a rerun on unchanged code reproduces
  the result exactly. Accuracy confidence comes from case count.
- **Statistics.** Accuracy is reported with a Wilson 95% interval where recorded; paired
  comparisons use the exact McNemar test on per-case outcomes; latency is reported as percentiles
  over per-case wall times.
- **Execution.** One llama-server (Gemma 4 E4B, thinking off) is resident for the whole run. Every
  planning call carries a GBNF grammar (`UNIFIED_GRAMMAR`) that makes malformed JSON impossible.
  llama-server stderr is retained under /tmp.
- **Command scoring.** The Gemma call's `mission` array is parsed, normalized from the wire schema
  (dx/dy/dz) to scorer keys, and compared step by step against the expected mission: action type,
  argument value (exact, sign-only, or magnitude-only where the phrasing is qualitative), and step
  count.
- **Perception scoring.** Perception inputs are not planned; the Gemma call emits `highlight`,
  `count`, or `describe` and names the target. highlight/count route to SAM3 as "<kind> the
  <target>"; describe routes to the VLM. The measured artifact is that phrase, scored by
  keyword-group preservation: every group of accepted synonyms must appear. This scorer cannot
  detect relation inversion ("A next to B" rendered as "B next to A"); the per-run dump exists for
  manual review of that class.
- **Terminology.** An *arm* is one configuration under test. The *regex bypass* (stage 1) is a
  layer of strict full-match patterns that answer a sentence as a mission with no model call; on no
  match the sentence passes through to Gemma.

## Recognizer facts that keep biting

(folded from the retired recognizer-bench skill; general procedure is in ../README.md)

- Component lives ONLY in `projects/integration_harden2/recognizer/` (recognizer.py = stages incl.
  recognize_direct, pipeline.py = glue incl. _plan2, prompts.py, llama.py). This bench imports it in place.
- harden2 reads Hebrew DIRECTLY: one Gemma-4-E4B call does routing + planning under UNIFIED_PROMPT/
  UNIFIED_GRAMMAR. There is NO translator.
- Hebrew clitic prefixes (ו/ב/ל/ה) break naive \b boundaries; number-words compose (עשרים וחמישה=25)
  and the number can FOLLOW the unit (מטר אחד=1). שנייה and מעלה are homographs -- never bare units.
- Keyword scoring cannot detect relation inversion; review the dump for that class.
- Emergency regex source of truth is stage 0 (EMERGENCY_RE in recognizer/recognizer.py);
  control/commands.py imports it. Greedy by ruling.
- Negation guard (negation_only, SUBTRACT rule) removes the verb a negation trigger governs; a
  surviving imperative is a real order and passes. Defense-in-depth, 0-false-fire gated.

### Commands
- `python3 bench/hebrew-command-bench/unified_bench.py`  -- CURRENT harness (recognize_direct + _plan2), ~2 min, GPU
- `python3 projects/integration_harden2/recognizer/recognizer.py`  -- component self-test, no GPU
- `python3 -m pytest projects/integration_harden2/test/ -q`  -- 66 wiring tests, models faked
- `bench.py` is the retired translated-path harness + shared infra; use unified_bench.py.
