# hebrew-command-bench

Isolated (nothing here is wired into the MVD): which pipeline turns a spoken HEBREW command
into a correct `/c/fly` mission array? 12 paired HE/EN cases, one scorer for every row.

Run: Qwen3-VL-4B on :18090 (`projects/integration_harden/run_llama_server.sh`), DictaLM on
:18091 for its rows (llama-server on `/root/models/asr/dictalm-3-1.7b/*.gguf`), then
`python3 run_bench.py [row ...]`. Results land in `results/`.

## 2026-09-01 ROUND-3 results — 190 cases (82 realistic authored), 8 arms, sequential + GBNF

| pipeline | acc | wilson95 | p25 | p50 | p75 | p95 | p99 | max (e2e ms) |
|---|---|---|---|---|---|---|---|---|
| qwen-en + planner few-shot (ceiling) | 185/190 (97%) | [94, 99] | 178 | 183 | 197 | 414 | 523 | 551 |
| **dicta->qwen + planner few-shot**   | 176/190 (93%) | [88, 96] | 221 | 228 | 257 | 520 | 667 | 718 |
| qwen-en (old prompt)                 | 166/190 (87%) | [82, 91] | 176 | 205 | 280 | 400 | 523 | 887 |
| dicta->qwen (old prompt)             | 160/190 (84%) | [78, 89] | 222 | 269 | 330 | 538 | 706 | 1029 |
| dicta-direct + HE few-shot           | 152/190 (80%) | [74, 85] | 87 | 88 | 99 | 201 | 318 | 1797 |
| opus->qwen                           | 144/190 (76%) | [69, 81] | 193 | 214 | 297 | 491 | 738 | 1144 |
| nllb->qwen                           | 131/190 (69%) | [62, 75] | 248 | 296 | 370 | 633 | 950 | 1191 |
| madlad->qwen                         | 24/190 (13%)* | — | — | — | — | — | — | — |

*madlad: SERVING failure, not a model verdict -- its /completion + <2en> path on this GGUF
produced garbage ('.', ',.com/', comma spam). llama.cpp T5 handling needs investigation before
this model can be judged; parked.

McNemar (exact): dicta-fs beats opus 42-10 (p<0.0001), beats its own no-few-shot arm 23-7
(p=0.005), beats dicta-direct 34-10 (p=0.0004); trails the EN ceiling 1-10 (p=0.012).
dicta translate stage alone: p50 45ms, p95 101ms.

Planner few-shot (5 examples: left-axis, down-combo, negation, question, 5-step) lifted the
ceiling 87%->97% and the dicta pipeline 84%->93%. Dominant REMAINING failure, shared by
ceiling and dicta arms: "turn right N degrees" -> planner emits MINUS N (7 of dicta-fs's 14
fails, 4 of the ceiling's 5) -- one more few-shot example targets it. The stubborn residue
after that: the המראה/נחת homographs (Tier-1 territory) and one negation phrasing.

dicta-direct + Hebrew few-shot became the latency option: 80% at p50 88ms (3.4x faster than
the pipeline, no Qwen in the loop) -- but the pipeline beats it 34-10 (p=0.0004).

Older rounds (12 / 32 / 108 cases): superseded; tables in git history + old result jsons.

## Round 4 (2026-09-01) — app prompt vs revised prompt, real wire schema

Purpose. Rounds 1–3 measured translators. Round 4 measures the planner prompt. It also moves every
arm to the real wire schema: `fly_by` takes dx/dy/dz plus optional velocity. Rounds 1–3 used x/y/z.
Relative results stood. The absolute schema was wrong.

Harness: `round4.py`. Raw: `results/2026-09-01-round4-results.json`. Wall: 297 s. 190 cases, temp 0,
one pass per case. Every planning call carries the dx/dy/dz GBNF grammar. One model on GPU at a time.

### Naming

The full text of every prompt named below is in [PROMPTS.md](PROMPTS.md).

Each arm is written prompt / planner model / input.

- **app prompt** — the system prompt the phone app ships today. Copied from SpeechResolving.kt:599-635.
  Its schema block is re-rendered in the app's own short-JSON format. One disclosed cut: only the 5
  whitelisted actions are included, so all arms share one scorer. The app also ships fly_circle,
  follow_me and others.
- **revised prompt** — the candidate replacement. Same scaffold. It adds three fixes for the round-3
  failure classes: a sign rule (turning right = clockwise = positive degrees), a refusal rule
  (questions and negated commands produce []), and 6 few-shot example pairs.
- **perfect-EN** — the planner gets our hand-written English reference text. This simulates a
  flawless translator. It isolates planner quality from translation.
- **dicta-HE / tgemma-HE** — real Hebrew goes through that translator first. DictaLM runs 2-shot
  with a single-line grammar, its best config from round 2. TranslateGemma runs its native embedded
  template on raw /completion, because llama-server cannot parse its custom jinja. e2e latency =
  translate + plan.

### Results

The two app-prompt rows are the baselines: they measure what runs today.
app-prompt/qwen3vl/perfect-EN is the reference scenario: ideal translation, today's prompt, our
planner model. Every comparison below changes exactly one variable against a baseline.

| arm | what this row is | acc | wilson95 | p25 | p50 | p75 | p95 | p99 | max (e2e ms) |
|---|---|---|---|---|---|---|---|---|---|
| revised-prompt/qwen3vl/perfect-EN | new prompt, our planner, ideal translation | 187/190 (98%) | [96%, 100%] | 178 | 182 | 200 | 421 | 522 | 538 |
| revised-prompt/qwen3vl/dicta-HE | full Hebrew path: DictaLM, then new prompt | 180/190 (95%) | [91%, 97%] | 233 | 241 | 270 | 534 | 702 | 752 |
| revised-prompt/qwen2.5c/perfect-EN | new prompt on the phone's engine | 178/190 (94%) | [89%, 96%] | 71 | 78 | 85 | 166 | 213 | 218 |
| app-prompt/qwen3vl/perfect-EN | BASELINE: today's prompt, our planner | 164/190 (86%) | [81%, 90%] | 197 | 301 | 322 | 781 | 1039 | 2097 |
| revised-prompt/qwen3vl/tgemma-HE | full Hebrew path: TranslateGemma, then new prompt | 125/190 (66%) | [59%, 72%] | 272 | 336 | 385 | 657 | 879 | 1096 |
| app-prompt/qwen2.5c/perfect-EN | BASELINE: today's prompt on the phone's engine | 107/190 (56%) | [49%, 63%] | 90 | 97 | 125 | 353 | 522 | 1287 |

McNemar, paired and exact. Each pair changes one variable:

- Prompt effect on qwen3vl: revised beats app prompt 24–1, p=1.6e-06.
- Prompt effect on the app engine: revised beats app prompt 80–9, p=2.3e-15.
- Translator effect, same prompt and planner: dicta beats tgemma 60–5, p=4.9e-13.
- Translation cost, same prompt and planner: perfect-EN beats dicta-HE 9–2, p=0.065. Not significant.

### Findings

1. The prompt is the app's biggest lever. The control on the app's own engine scores 56%. The
   revised prompt lifts it to 94% at p50 78 ms. That is a prompt-only change. No model swap.
2. The sign rule kills the turn-right bug. Zero turn-right failures remain in the revised arms.
   In round 3 that bug was 7 of the top arm's 14 failures. The 1.5B engine still flips 180°/270°
   clockwise sometimes. The 4B does not.
3. The full Hebrew pipeline reaches 95%. It is now statistically indistinguishable from the same
   planner on perfect English (p=0.065). Round 3 had a significant gap.
4. A bigger model does not rescue the app prompt. The control on qwen3vl still fails 14% of cases.
5. TranslateGemma is wrong for imperatives. It narrates instead of commanding: "נחת" becomes
   "Landed", "המראה" becomes "The reflection". 66% overall. Excluded from further command rounds.
6. The new prompt's 3 remaining failures are genuinely ambiguous: filler repetition ("wait wait"),
   "come back" implying a signed return leg, and a bare "without turning please".

### Perception commands

40 authored highlight/track/count cases. They go through both translators only. No planner:
these route to the VLM in the real system. Scored by keyword-group preservation. Full dump in
`results/2026-09-01-perception-dump.md`.

- dicta keeps 91% of keyword groups, 31/40 cases fully intact. tgemma keeps 94%, 32/40.
- Two real dicta failures matter, and they corrupt meaning silently. It regurgitated a few-shot
  example verbatim on one out-of-domain input. It rewrote "how many X" questions as declarative
  counts: "There are five people...". A VLM-bound Hebrew path should not reuse the command-tuned
  2-shot translate config.
- About 5 of the 17 flagged rows are scorer synonym gaps, such as "keep an eye on" for track.
  The rest are real entity or attribute drops. Both models fumble גדר (fence) and צל (shade).

### Latency vs length

- Translate cost tracks OUTPUT length: dicta r=0.97, tgemma r=0.94. Input correlation is ~0.83.
  Long perception inputs stay cheap: dicta p50 is 57/89/189 ms for ≤25 / 26–60 / 61–120 input chars.
- Planning cost is also output-driven: r=0.97 output vs 0.72 input. The round-3 physics hold on
  the new schema. Output chars cost ~5 ms each. Prefill is cheap.

Open, owner to rule: adopt the revised prompt in the app. Adopt DictaLM as the backlog-B
translator. Give the perception path its own translate config. Hebrew Tier-1 fast path.

## Round 5 (2026-09-01) — multi-hop perception commands, translation stage only

Purpose. Round 4's 40 perception cases were mostly single-hop. Round 5 uses 45 new hand-authored
Hebrew commands where the target is reached through attribute and relation links. Example: "הדגש
את המכונית שצמודה לאדם עם הלבוש האדום" — the car, found via the person, found via the red attire.
Depth tags: 1 = attributed object (1 case), 2 = one link (15), 3 = two chained links (29).
The owner's three seed examples are cases i_mid_windows, i_orange_cap, i_car_by_red.

No planner runs in this round. These commands route to the VLM in the real system, so the
measured stage is Hebrew → English only.

Flow, identical for every arm: one Hebrew sentence → the model below → one English sentence →
keyword-group scorer. Each sentence passes exactly once per arm. One model on GPU at a time.
Harness: `round5.py`. Cases: `cases_indirect.py`. Raw: `results/2026-09-01-round5-results.json`.
Full dump: `results/2026-09-01-round5-dump.md`. Wall: 35 s.

- **hebrew->dictalm->english** — DictaLM-3.0-1.7B, 2-shot + one-line grammar. Same config as round 4.
- **hebrew->translategemma->english** — TranslateGemma-4b-it, its native template.
- **hebrew->qwen3vl->english** — Qwen3-VL-4B given the identical 2-shot setup as DictaLM. This asks:
  can the VLM read the Hebrew itself, or does its path need a translator in front? Disclosed limit:
  it scores restatement, not detection on an image.

| arm | all groups kept | wilson95 | groups kept | depth-2 cases | depth-3 cases | p25 | p50 | p75 | p95 | p99 | max (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hebrew->translategemma->english | 38/45 (84%) | [71%, 92%] | 218/227 (96%) | 12/15 | 26/29 | 275 | 293 | 336 | 367 | 375 | 381 |
| hebrew->dictalm->english | 31/45 (69%) | [54%, 80%] | 210/227 (93%) | 13/15 | 18/29 | 92 | 99 | 120 | 137 | 142 | 142 |
| hebrew->qwen3vl->english | 19/45 (42%) | [29%, 57%] | 188/227 (83%) | 9/15 | 10/29 | 162 | 188 | 204 | 235 | 243 | 244 |

McNemar, paired and exact: translategemma vs dictalm 11–4, p=0.12 — leading, not yet significant
at 45 cases. translategemma vs qwen3vl 20–1, p=2.1e-05. dictalm vs qwen3vl 19–7, p=0.029.

### Findings

1. The round-4 verdict inverts on this register. TranslateGemma failed imperatives (66%) but leads
   multi-hop descriptions (84%). DictaLM wins commands (95%) but degrades with depth: 87% of
   depth-2 cases intact, 62% at depth 3. TranslateGemma holds 80%→90%. One translator does not
   fit both paths.
2. DictaLM's few-shot leak is now a pattern, not an incident. Two more outputs contained verbatim
   shot text ("Fly left six meters", "Stop in place") injected into unrelated sentences. Three
   incidents across rounds 4–5, always on out-of-domain input. The command-tuned 2-shot config
   must not serve the perception path.
3. One true relation inversion observed: "עקוב אחרי הרכב שנוסע מאחורי האופנוע האדום" became
   "Follow the red motorcycle that is behind the car" — target and anchor swapped. The keyword
   scorer only caught it by luck (a dropped verb group). Dump review stays mandatory.
4. All three models mistranslated כתום (orange) on the owner's seed case: DictaLM and
   TranslateGemma said "red", Qwen3-VL said "yellow". Color attributes are a grounding risk;
   consider a Tier-1 color glossary before the translator, or constrained color vocabulary.
5. Qwen3-VL cannot read Hebrew concrete nouns reliably: גג→"ceiling", ספסל→"sapling", רוכב→"drone",
   קסדה→"beacon", מזח→"aisle", צמיג→"bumper". 42% overall. The VLM path needs a translator in
   front of it. The restatement proxy may understate in-image performance, but entity words this
   wrong cannot ground correctly.
6. Homograph list grows: מכולה (container) → "grocery store" (TranslateGemma; מכולת collision).
7. Scorer honesty: roughly 3 of TranslateGemma's 7 misses are synonym gaps ("central" for center,
   "perched" for sitting, "docked" for tied), so its true rate is a little above 84%. DictaLM's
   misses are mostly real drops, color swaps (yellow truck→"red truck") or garbles ("Hold the toy
   with the green shirt").

Open, owner to rule: TranslateGemma for the perception path + DictaLM for the command path
(two-translator split), or one more round to close tgemma-vs-dicta significance; color-glossary
guard; whether to re-run round 5's scorer with widened synonyms.

## Round 6 (2026-09-01) — full pipeline: commands and perception, six arms

Purpose. One round that measures everything at once: the 190 command cases through translator +
revised-prompt planner on Qwen3-VL, and 100 multi-hop perception cases (the 45 from round 5 plus
55 new hand-authored ones, 20 of them at depth 4) through translator only. Perception cases now
carry hand-written English references; the control arm scores those references directly, so a
control miss would mean a scorer bug. The control measured 100/100 — the scorer is calibrated.

Flow. Commands: text → translator → revised prompt on Qwen3-VL → mission JSON → scorer.
Perception: Hebrew → translator → English → keyword-group scorer. No planner for perception;
those route to the VLM in the real system. Each case passes once per arm. Three model loads.
Harness: `round6.py`. Cases: `cases_perception100.py`. Raw: `results/2026-09-01-round6-results.json`.
Dump: `results/2026-09-01-round6-dump.md`. Wall: 322 s.

Two shared-row disclosures. The split arm re-aggregates cached dictalm-command and
translategemma-perception rows: zero new compute, routing by known case type. The refine arm
shares its command rows with dictalm-alone; its perception latency counts draft + refine.

| arm | what it is | commands acc | wilson95 | perception all-groups | wilson95 | groups kept |
|---|---|---|---|---|---|---|
| control-perfect-english | hand-written English into the planner; reference text for perception | 189/190 (99%) | [97%, 100%] | 100/100 (100%) | [96%, 100%] | 576/576 (100%) |
| dictalm-alone | DictaLM translates both halves | 179/190 (94%) | [90%, 97%] | 56/100 (56%) | [46%, 65%] | 516/576 (90%) |
| translategemma-alone | TranslateGemma translates both halves | 122/190 (64%) | [57%, 71%] | 78/100 (78%) | [69%, 85%] | 551/576 (96%) |
| qwen3vl-alone | Qwen3-VL translates both halves, then plans | 136/190 (72%) | [65%, 78%] | 38/100 (38%) | [29%, 48%] | 478/576 (83%) |
| refine-dictalm-draft->translategemma-final | commands from DictaLM; perception draft refined by TranslateGemma | 179/190 (94%) | [90%, 97%] | 66/100 (66%) | [56%, 74%] | 534/576 (93%) |
| split-dictalm-commands+translategemma-perception | DictaLM for commands, TranslateGemma for perception | 179/190 (94%) | [90%, 97%] | 78/100 (78%) | [69%, 85%] | 551/576 (96%) |

Latency, e2e ms (commands = translate + plan; perception = translate; control perception = 0, reference text):

| arm | cmd p25 | p50 | p75 | p95 | p99 | max | perc p25 | p50 | p75 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| control-perfect-english | 183 | 187 | 202 | 427 | 539 | 562 | 0 | 0 | 0 | 0 | 0 | 0 |
| dictalm-alone | 239 | 245 | 275 | 555 | 731 | 1019 | 100 | 118 | 138 | 162 | 280 | 319 |
| translategemma-alone | 250 | 338 | 392 | 641 | 898 | 1117 | 242 | 294 | 319 | 400 | 452 | 452 |
| qwen3vl-alone | 275 | 292 | 331 | 642 | 821 | 889 | 184 | 234 | 260 | 317 | 355 | 395 |
| refine-dictalm-draft->translategemma-final | 239 | 245 | 275 | 555 | 731 | 1019 | 344 | 406 | 460 | 535 | 646 | 983 |
| split-dictalm-commands+translategemma-perception | 239 | 245 | 275 | 555 | 731 | 1019 | 242 | 294 | 319 | 400 | 452 | 452 |

Perception cases passed by reference depth (d1 is the single orange-cap case):

| arm | d1 | d2 (n=18) | d3 (n=61) | d4 (n=20) |
|---|---|---|---|---|
| control-perfect-english | 1/1 | 18/18 | 61/61 | 20/20 |
| dictalm-alone | 0/1 | 16/18 | 33/61 | 7/20 |
| translategemma-alone | 0/1 | 14/18 | 52/61 | 12/20 |
| qwen3vl-alone | 0/1 | 11/18 | 21/61 | 6/20 |
| refine-dictalm-draft->translategemma-final | 0/1 | 14/18 | 41/61 | 11/20 |
| split-dictalm-commands+translategemma-perception | 0/1 | 14/18 | 52/61 | 12/20 |

McNemar, paired and exact:
- commands: control beats dictalm 10–0, p=0.002. dictalm beats translategemma 61–4 and qwen3vl 46–3, both p<1e-9.
- perception: translategemma beats dictalm 32–10, p=0.0009 — round 5's lead is now significant.
- perception: refine LOSES to translategemma-alone 9–21, p=0.043. The draft anchors TranslateGemma
  toward DictaLM's errors. Refine does beat dictalm-alone 14–4, p=0.031.

### Findings

1. The split is the best deployable configuration: 94% commands at p50 245 ms and 78% perception
   (96% of keyword groups) at p50 294 ms. Nothing else wins both halves.
2. The refine idea is measured and rejected: 66% vs 78% for TranslateGemma alone, p=0.043.
   Handing TranslateGemma a draft plus the ground truth made it worse, not better — it inherits
   draft errors instead of fixing them. It also costs the most latency (p50 406 ms).
3. Depth hurts everyone, TranslateGemma least: by depth it holds 78%/85%/60% (d2/d3/d4) while
   DictaLM falls 89%/54%/35% and Qwen3-VL 61%/34%/30%. Groups-kept stays 90–96%, so failures are
   usually one dropped link, not total garbling.
4. Qwen3-VL still cannot be its own Hebrew front-end: 72% commands from its own translations
   (it corrupts Hebrew numbers: twenty→ten, twenty→sixty) and 38% perception.
5. The control confirms the planner ceiling at 99.5% (189/190); the one failure is the ambiguous
   "come back" return-leg case. The perfect-translation control perception is 100% by construction.
6. כתום (orange) still breaks every translator (the d1 0/1 row) — three orange cases in the new
   set all lost the color. The color-glossary guard remains the cheapest fix on the table.

Open, owner to rule: adopt the split in production (recommendation: yes, it is the measured
winner); drop the refine lane (measured worse); color-glossary guard; ONNX/CPU-offload lane
staged in ROUND4-PLAN.md.
