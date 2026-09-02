# Development history — rounds 1-6 and the ablation iterations

Superseded results, kept as the record. Raw data for every table is in this directory.


Everything below is the development history (rounds 1-6, the ablation iterations, the
intermediate measurements). The numbers are superseded by the scorecard above. Raw data for
every table is under results/.


### Round 3 (2026-09-01) — translator comparison, 190 commands, 8 arms

Objective: select a Hebrew-to-English translator for the command path. Note: rounds 1–3 used an
x/y/z planner schema; the production wire schema (dx/dy/dz) was adopted in round 4. Relative
comparisons within this round remain valid.

| pipeline | acc | wilson95 | p25 | p50 | p75 | p95 | p99 | max (e2e ms) |
|---|---|---|---|---|---|---|---|---|
| qwen-en + planner few-shot (ceiling) | 185/190 (97%) | [94, 99] | 178 | 183 | 197 | 414 | 523 | 551 |
| dicta->qwen + planner few-shot | 176/190 (93%) | [88, 96] | 221 | 228 | 257 | 520 | 667 | 718 |
| qwen-en (old prompt) | 166/190 (87%) | [82, 91] | 176 | 205 | 280 | 400 | 523 | 887 |
| dicta->qwen (old prompt) | 160/190 (84%) | [78, 89] | 222 | 269 | 330 | 538 | 706 | 1029 |
| dicta-direct + HE few-shot | 152/190 (80%) | [74, 85] | 87 | 88 | 99 | 201 | 318 | 1797 |
| opus->qwen | 144/190 (76%) | [69, 81] | 193 | 214 | 297 | 491 | 738 | 1144 |
| nllb->qwen | 131/190 (69%) | [62, 75] | 248 | 296 | 370 | 633 | 950 | 1191 |
| madlad->qwen | 24/190 (13%)* | — | — | — | — | — | — | — |

*The madlad figure reflects a serving failure (T5 GGUF over /completion produced token garbage),
not model quality. Parked pending llama.cpp T5 investigation.

McNemar: dicta+few-shot beats opus 42–10 (p<0.0001), beats its own no-few-shot arm 23–7
(p=0.005), beats dicta-direct 34–10 (p=0.0004), trails the English ceiling 1–10 (p=0.012).
Translation stage alone: p50 45 ms, p95 101 ms.

Conclusions: DictaLM selected for the command path. Planner few-shot examples were the largest
single lever (+10 pp on the ceiling, +9 pp on the pipeline). Dominant residual failure: "turn
right N degrees" planned as −N (7 of 14 failures in the best arm). Rounds 1–2 (12/32/108 cases)
are superseded; their tables are in git history.

### Round 4 (2026-09-01) — planner prompt comparison, production wire schema

Objective: measure the shipped app prompt against a revised prompt, on both planner engines,
using the production `fly_by` schema (dx/dy/dz + optional velocity) verified against the app's
FlyBy.kt and dji_wire.py. Prompt texts: [PROMPTS.md](PROMPTS.md).

Definitions. *app prompt*: the system prompt the phone app ships (SpeechResolving.kt:599-635),
schema block re-rendered in the app's short-JSON format, restricted to the 5 whitelisted actions
so all arms share one scorer (the app also ships fly_circle, follow_me, and others). *revised
prompt*: the same scaffold plus a rotation sign rule (right = clockwise = positive), a refusal
rule (questions and negated commands produce an empty mission), and 6 few-shot examples.
190 cases; harness `round4.py` (now `bench.py`); raw results
`results/2026-09-01-round4-results.json`; wall time 297 s.

| arm | description | acc | wilson95 | p25 | p50 | p75 | p95 | p99 | max (e2e ms) |
|---|---|---|---|---|---|---|---|---|---|
| revised-prompt/qwen3vl/perfect-EN | revised prompt, Qwen3-VL, ideal translation | 187/190 (98%) | [96%, 100%] | 178 | 182 | 200 | 421 | 522 | 538 |
| revised-prompt/qwen3vl/dicta-HE | full Hebrew path: DictaLM, revised prompt | 180/190 (95%) | [91%, 97%] | 233 | 241 | 270 | 534 | 702 | 752 |
| revised-prompt/qwen2.5c/perfect-EN | revised prompt on the phone engine | 178/190 (94%) | [89%, 96%] | 71 | 78 | 85 | 166 | 213 | 218 |
| app-prompt/qwen3vl/perfect-EN | baseline: shipped prompt, Qwen3-VL | 164/190 (86%) | [81%, 90%] | 197 | 301 | 322 | 781 | 1039 | 2097 |
| revised-prompt/qwen3vl/tgemma-HE | full Hebrew path: TranslateGemma, revised prompt | 125/190 (66%) | [59%, 72%] | 272 | 336 | 385 | 657 | 879 | 1096 |
| app-prompt/qwen2.5c/perfect-EN | baseline: shipped prompt on the phone engine | 107/190 (56%) | [49%, 63%] | 90 | 97 | 125 | 353 | 522 | 1287 |

McNemar, one variable changed per pair: prompt effect on Qwen3-VL 24–1 (p=1.6e-06); prompt
effect on qwen2.5-coder 80–9 (p=2.3e-15); translator effect dicta vs tgemma 60–5 (p=4.9e-13);
translation cost, perfect-EN vs dicta-HE 9–2 (p=0.065, not significant).

Analysis:

1. The prompt is the largest available lever on the app engine: 56% to 94% with no model change,
   and lower latency (shorter outputs).
2. The sign rule removed the turn-right failure class entirely on both engines. The 1.5B engine
   still occasionally flips 180°/270° clockwise; the 4B does not.
3. The Hebrew pipeline (95%) is statistically indistinguishable from the same planner on perfect
   English; the significant gap seen in round 3 is closed.
4. A larger planner does not compensate for the shipped prompt (86% on Qwen3-VL).
5. TranslateGemma translates imperatives into narration ("נחת" → "Landed", "המראה" → "The
   reflection") and was excluded from further command-path rounds.
6. The three residual failures of the best arm are inherently ambiguous inputs (filler
   repetition, an implied return leg, a bare "without turning please").

A 40-case perception set ran through both translators in this round (keyword preservation:
DictaLM 31/40 cases, 91% of groups; TranslateGemma 32/40, 94%). Two DictaLM failure modes
observed here recur in later rounds: verbatim few-shot regurgitation on out-of-domain input,
and rewriting "how many X" questions into declarative counts with invented numbers.

Latency scaling, both stages: cost tracks output length (r = 0.94–0.97), not input length
(r ≈ 0.7–0.83); approximately 5 ms per output character. Long inputs are cheap prefill.

### Round 5 (2026-09-01) — multi-hop perception, translation stage only

Objective: measure translation quality on perception commands whose target is reached through
chained attribute/relation references. 45 hand-authored cases, depth-tagged: 1 = attributed
object (1 case), 2 = one reference link (15), 3 = two links (29). Flow per arm: one Hebrew
sentence → translator → one English sentence → keyword scorer. Raw:
`results/2026-09-01-round5-results.json`; dump `...-round5-dump.md`; wall 35 s.

Arms: DictaLM (2-shot + single-line grammar), TranslateGemma (native template on /completion —
llama-server cannot parse its custom chat template), and Qwen3-VL under the identical 2-shot
setup as DictaLM. The Qwen3-VL arm tests whether the VLM can read Hebrew directly; it scores
restatement, not detection on an image, which is a stated limitation.

| arm | all groups kept | wilson95 | groups kept | depth-2 | depth-3 | p25 | p50 | p75 | p95 | p99 | max (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hebrew->translategemma->english | 38/45 (84%) | [71%, 92%] | 218/227 (96%) | 12/15 | 26/29 | 275 | 293 | 336 | 367 | 375 | 381 |
| hebrew->dictalm->english | 31/45 (69%) | [54%, 80%] | 210/227 (93%) | 13/15 | 18/29 | 92 | 99 | 120 | 137 | 142 | 142 |
| hebrew->qwen3vl->english | 19/45 (42%) | [29%, 57%] | 188/227 (83%) | 9/15 | 10/29 | 162 | 188 | 204 | 235 | 243 | 244 |

McNemar: translategemma vs dictalm 11–4 (p=0.12, not significant at n=45); translategemma vs
qwen3vl 20–1 (p=2.1e-05); dictalm vs qwen3vl 19–7 (p=0.029).

Analysis:

1. The round-4 command-path ranking inverts on this register. DictaLM degrades with reference
   depth (87% of depth-2 cases intact, 62% at depth 3); TranslateGemma holds (80% / 90%). A
   single translator does not fit both the command and perception paths.
2. DictaLM few-shot regurgitation recurred twice more (verbatim shot text injected into
   unrelated sentences; three incidents across rounds 4–5, always on out-of-domain input). The
   command-tuned 2-shot configuration is unsuitable for the perception path.
3. One relation inversion was observed ("the vehicle driving behind the red motorcycle" rendered
   with target and anchor swapped); the keyword scorer detected it only via an incidentally
   dropped group. Dump review remains required for this class.
4. All three models mistranslated כתום (orange): "red" (DictaLM, TranslateGemma), "yellow"
   (Qwen3-VL). Color attributes are a grounding risk.
5. Qwen3-VL's Hebrew noun lexicon is unreliable (גג→"ceiling", ספסל→"sapling", רוכב→"drone",
   קסדה→"beacon"); 42% overall. The VLM path requires a translator in front of it.
6. Additional homograph recorded: מכולה (container) → "grocery store" (TranslateGemma).
7. Scorer calibration note: approximately 3 of TranslateGemma's 7 flagged cases are synonym gaps
   ("central" for center, "perched" for sitting, "docked" for tied); its true rate is slightly
   above the reported 84%. DictaLM's flagged cases are predominantly real content loss.

### Round 6 (2026-09-01) — combined command and perception benchmark, six arms

Objective: a single benchmark covering both halves. Commands: 190 cases through
translator → revised prompt on Qwen3-VL → mission scorer. Perception: 100 cases (round 5's 45
plus 55 new, including 20 at depth 4 and verbose "pinpoint" phrasings) through translator →
keyword scorer. Perception cases carry hand-written English references; the control arm scores
the references directly and measured 100/100, confirming scorer calibration. Raw:
`results/2026-09-01-round6-results.json`; dump `...-round6-dump.md`; wall 322 s.

Shared-row notes: the split arm re-aggregates cached dictalm-command and
translategemma-perception rows (no new compute; routing by known case type — production routing
would come from the existing tier router). The refine arm shares command rows with
dictalm-alone; its perception latency includes draft + refine, matching sequential execution.

| arm | description | commands acc | wilson95 | perception all-groups | wilson95 | groups kept |
|---|---|---|---|---|---|---|
| control-perfect-english | hand-written English into the planner; reference text for perception | 189/190 (99%) | [97%, 100%] | 100/100 (100%) | [96%, 100%] | 576/576 (100%) |
| dictalm-alone | DictaLM translates both halves | 179/190 (94%) | [90%, 97%] | 56/100 (56%) | [46%, 65%] | 516/576 (90%) |
| translategemma-alone | TranslateGemma translates both halves | 122/190 (64%) | [57%, 71%] | 78/100 (78%) | [69%, 85%] | 551/576 (96%) |
| qwen3vl-alone | Qwen3-VL translates both halves, then plans | 136/190 (72%) | [65%, 78%] | 38/100 (38%) | [29%, 48%] | 478/576 (83%) |
| refine-dictalm-draft->translategemma-final | commands from DictaLM; perception draft refined by TranslateGemma | 179/190 (94%) | [90%, 97%] | 66/100 (66%) | [56%, 74%] | 534/576 (93%) |
| split-dictalm-commands+translategemma-perception | DictaLM for commands, TranslateGemma for perception | 179/190 (94%) | [90%, 97%] | 78/100 (78%) | [69%, 85%] | 551/576 (96%) |

Latency, e2e ms (commands = translate + plan; perception = translate; control perception = 0 by
construction):

| arm | cmd p25 | p50 | p75 | p95 | p99 | max | perc p25 | p50 | p75 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control-perfect-english | 183 | 187 | 202 | 427 | 539 | 562 | 0 | 0 | 0 | 0 | 0 | 0 |
| dictalm-alone | 239 | 245 | 275 | 555 | 731 | 1019 | 100 | 118 | 138 | 162 | 280 | 319 |
| translategemma-alone | 250 | 338 | 392 | 641 | 898 | 1117 | 242 | 294 | 319 | 400 | 452 | 452 |
| qwen3vl-alone | 275 | 292 | 331 | 642 | 821 | 889 | 184 | 234 | 260 | 317 | 355 | 395 |
| refine-dictalm-draft->translategemma-final | 239 | 245 | 275 | 555 | 731 | 1019 | 344 | 406 | 460 | 535 | 646 | 983 |
| split-dictalm-commands+translategemma-perception | 239 | 245 | 275 | 555 | 731 | 1019 | 242 | 294 | 319 | 400 | 452 | 452 |

Perception cases passed, by reference depth (d1 is the single orange-cap case):

| arm | d1 | d2 (n=18) | d3 (n=61) | d4 (n=20) |
|---|---|---|---|---|
| control-perfect-english | 1/1 | 18/18 | 61/61 | 20/20 |
| dictalm-alone | 0/1 | 16/18 | 33/61 | 7/20 |
| translategemma-alone | 0/1 | 14/18 | 52/61 | 12/20 |
| qwen3vl-alone | 0/1 | 11/18 | 21/61 | 6/20 |
| refine-dictalm-draft->translategemma-final | 0/1 | 14/18 | 41/61 | 11/20 |
| split-dictalm-commands+translategemma-perception | 0/1 | 14/18 | 52/61 | 12/20 |

McNemar: commands — control beats dictalm 10–0 (p=0.002); dictalm beats translategemma 61–4 and
qwen3vl 46–3 (both p<1e-9). Perception — translategemma beats dictalm 32–10 (p=0.0009; round 5's
non-significant lead is now significant at n=100); refine loses to translategemma-alone 9–21
(p=0.043) and beats dictalm-alone 14–4 (p=0.031).

Analysis:

1. The split configuration is the strongest deployable result: 94% commands at p50 245 ms and
   78% perception (96% of keyword groups) at p50 294 ms. No other arm leads both halves.
2. The refine approach (TranslateGemma finalizing a DictaLM draft against the Hebrew source) is
   rejected on measurement: it inherits draft errors rather than correcting them, scores
   significantly below TranslateGemma alone, and has the highest perception latency.
3. Reference depth degrades every translator; TranslateGemma least (78% / 85% / 60% at d2/d3/d4
   versus DictaLM's 89% / 54% / 35%). Group-retention stays at 90–96%, i.e. typical failures
   drop one link rather than garbling the sentence.
4. Qwen3-VL as its own Hebrew front-end is rejected: 72% commands (Hebrew number corruption:
   twenty → ten, twenty → sixty) and 38% perception.
5. Planner ceiling confirmed at 99.5%; the single failure is the ambiguous "come back"
   return-leg case.
6. כתום (orange) failed in every arm, including all three new orange cases.

### Direct-Hebrew planning (2026-09-02, `bench.py --direct`)

Objective: evaluate DictaLM as the planner on raw Hebrew, removing the translation stage and
Qwen3-VL from the command path (1.6 GiB total, CPU-capable). Three prompt iterations: revised
prompt + Hebrew shots 161/190 (84.7%); + a Hebrew sign-rule addendum 165/190; + an explicit
clockwise-idiom example 168/190 (88.4%, p50 121 ms).

Result: 88.4% remains significantly below the dicta→qwen3vl pipeline at 94.2% (McNemar 18–7,
p=0.043). Correction to an earlier interim report: the clockwise-idiom example did not fix the
עם-כיוון-השעון sign flips — all 7 persist in the final run; the iterations fixed other cases and
regressed one (bare נחת). That token class is prompt-resistant at this model size; deterministic
handling or fine-tuning are the remaining options. Residual classes: clockwise sign flips,
dropped axes in some multi-step chains, refused polite takeoff forms. Raw:
`results/2026-09-02-direct-results.json`.

### Failure classification (2026-09-02, from stored round-6 and direct results)

Failed cases per arm by command type (n = cases of that type; the control fails only the
ambiguous "come back" case):

| type | n | dictalm->planner | tgemma->planner | qwen3vl->planner | dictalm-direct |
|---|---|---|---|---|---|
| up/down | 39 | 1 | 19 | 8 | 1 |
| fwd/back | 32 | 0 | 3 | 4 | 1 |
| multi-step | 29 | 8 | 17 | 16 | 5 |
| left/right | 26 | 0 | 11 | 7 | 0 |
| spin cw/right | 14 | 0 | 3 | 5 | 6 |
| takeoff/land form | 14 | 2 | 9 | 10 | 3 |
| negation/filler | 14 | 0 | 0 | 0 | 5 |
| spin ccw | 7 | 0 | 5 | 3 | 0 |
| wait | 6 | 0 | 1 | 1 | 0 |
| question | 3 | 0 | 0 | 0 | 1 |

Characteristic error per arm. DictaLM pipeline: correct on all single-step types; losses are
multi-step merges (the "turn right two meters" translation defect, planned as rotation) and two
takeoff/land paraphrases. TranslateGemma: imperative-to-narration register shift, concentrated
in up/down and takeoff/land. Qwen3-VL: lexicon and number errors across all types. DictaLM
direct: clockwise sign flips (6), over-refusal of filler sentences (5), polite takeoff forms.

Perception keyword groups dropped, by category, across the 100 cases:

| category | dictalm | tgemma | qwen3vl |
|---|---|---|---|
| entity/attribute | 46 | 15 | 82 |
| spatial/relation | 6 | 3 | 4 |
| verb/action | 4 | 4 | 7 |
| color | 4 | 3 | 5 |

Relations and verbs largely survive translation; entity nouns account for most losses. This is
a lexicon problem rather than a structural one, which motivates deterministic vocabulary
handling over a larger model.


### Regex bypass, offline replay (2026-09-02)

Seven strict full-match patterns (takeoff/land forms, single-direction move with number and
unit, rotations including the clockwise idiom, turn-right/left N degrees, waits, full turn)
match 86/190 command inputs (45%). Replaying "pattern answers on full match, model otherwise"
against stored results:

| arm | measured | with bypass |
|---|---|---|
| dictalm->planner | 94.2% | 95.3% |
| dictalm-direct | 88.4% | 92.6% |
| qwen3vl->planner | 71.6% | 84.7% |
| tgemma->planner | 64.2% | 83.2% |

The bypass gains most where its coverage intersects an arm's failure classes: combined with
direct-Hebrew planning it reaches 92.6% with no translation stage, 2.7 pp behind the best
pipeline-plus-bypass figure. Full-match-only semantics carry no partial-corruption risk. The
seven patterns are a lower bound on coverage; politeness-stripping and verb alternates would
raise it. Projection only — the combined bypass + processing-layer configuration has not been
run as a single system.

### Sieve ablation, iterations 1–3 (2026-09-02, `bench.py --pipeline`)

Objective: develop the sieve: the deterministic layer (`sieve.py`) against end-to-end mission
accuracy, iteratively: run, attribute failures, add or amend rules, re-run. Scoring is the full
path (Hebrew → HE rules → DictaLM → EN rules → revised prompt on Qwen3-VL → mission scorer).
A new 54-case corpus (`cases_verbose.py`) models verbose conversational phrasing: 12 frames × 4
argument fills of chained simple actions, plus negation/question traps. Baseline accuracy on
this register is 69%, against 94% on the standard set — the register itself was a previously
unmeasured deficit.

Layer-by-layer results (each row adds one mechanism; conditions re-run per iteration):

| configuration | verbose (54) | std-190 | notes |
|---|---|---|---|
| baseline, no processing layer | 37/54 (69%) | 179/190 (94%) | dominant failure: number-word corruption (עשרים → "ten") |
| + number check with corrective retry | 42/54 (78%) | 180/190 (95%) | the check predicted failure 10/10 with 0 false alarms on verbose |
| + deterministic digit patch on failed retry | 46/54 (85%) | 181/190 (95.3%) | applied only when exactly one value differs and the patch passes re-validation |
| + EN rewrite ("turn ⟨dir⟩ N meters" → "move …") | 49/54 (91%) | (in full stack) | +3/−0 in every iteration |
| purpose-objective prompt stack | 49/54 (91%), p50 −100 ms | 179/190 (94%) | see below |

Statistical checks: EN rewrite vs base 3–0 (p=0.25, monotone across iterations); full stack vs
base on std-190 5–7 (p=0.77, equivalent). Number-check false-alarm rate on std-190: 7 flags on
passing cases, traceable to the check's Hebrew number-word parser; harmless for a retry trigger.

Purpose-objective prompt: a translate prompt that states the downstream task ("front-end of a
flight planner; one imperative clause per action; preserve numbers exactly") instead of
requesting faithful translation. Measured effects: number-corruption flags 10 → 3, p50 −100 ms.
Measured defect: DictaLM 1.7B translates the takeoff family as "Perform landing" under this
prompt, and neither an explicit mapping line nor a dedicated example removed the behavior
(5 std-190 failures). Net accuracy is equal to the simpler stack, so the prompt is parked; the
objective-style formulation remains a candidate for fine-tuning data rather than prompting.

Defects found by this loop and fixed during it: the purpose prompt's verb list omitting
take off/land (caused the regression above); a case-sensitive EN rewrite missing
sentence-initial "Turn"; few-shot regurgitation converting negation inputs into mission
sentences (guard added: verbatim-shot output triggers a shot-free retry); a Hebrew homograph
false-fire ("המראה שבורה בחדר" rewritten as a takeoff) caught by the rule self-test before any
model run. Each fixed defect carries a permanent regression check in `sieve.py`.

Residual failures at 91% are not addressable by deterministic rewriting: paraphrase semantics
("remain stationary", implied return legs), one planner-side confusion from a trailing question
clause, and takeoff/land paraphrases — the last class is covered by the regex bypass, which was
measured separately (above) but not yet combined with this stack in one run. The
military/acronym HE rules fired zero times on these corpora (their register does not occur in
them); their end-to-end effect requires the perception rerun with TranslateGemma.
