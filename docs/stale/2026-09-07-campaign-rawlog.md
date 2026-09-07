# VRAM + perception campaign — RESULTS
Owner: groundstation-05 (ref 55e80f), live-test agent. Model: Opus 4.8. Started 2026-09-07.
Plan: 2026-09-07-vram-perception-campaign-plan.md. One section per step. Each ends with a
CHECKPOINT block matching performed-vs-planned before advancing.

---

# FINAL CONCLUSIONS (read this first; sections below are the chronological log)

## Translator decision
- **Deployable pick: Hy-MT2 (Q4 or Q6).** Best translator that FITS the 8 GB card (1,188 / 1,514 MiB).
  86% overall, 96% commands, 72% perception, answer-mode 0, ~2x faster than tgemma.
- **Accuracy champion: tgemma + few-shots** — 90% overall, 98% commands, 88% perception. Beats every
  model, but 2,478 MiB does NOT fit beside SAM3 even alone. NOT deployable here. The old "tgemma
  collapses on commands" verdict was a ZERO-SHOT ARTIFACT — it was the only model never given few-shots.
- **DictaLM** stays the command specialist (99%) on CPU, but weak perception (61%) + answers questions;
  heavy CPU tail (p50 461 / p99 1.7 s at 16 threads; 6-8 threads similar).
- **The universal lever is FEW-SHOTS**, not the system-prompt wording. Two examples move every model
  sharply; zero-shot costs ~6-12 pp on commands. But 2 shots is the SWEET SPOT — Hy-MT2-Q6 at 3/4
  shots drifts DOWN (86%->85%->84%). tgemma's own instruction vs DictaLM's is within noise.

## Full accuracy scorecard (413 cases, EVERY model at its best recipe = system prompt + 2 few-shots)
| set | DictaLM | tgemma | Hy-MT2-Q4 | Hy-MT2-Q6 | Hy-MT2-Q8 |
|---|---|---|---|---|---|
| emergency | 7/7 | 7/7 | 7/7 | 7/7 | 7/7 |
| std-204 command | 197/199 (99%) | 196/200 (98%) | 193/201 (96%) | 193/200 (96%) | 194/200 (97%) |
| verbose-54 | 47/51 (92%) | 47/54 (87%) | 43/54 (80%) | 48/54 (89%) | 47/54 (87%) |
| perception-128 | 78/128 (61%) | 112/128 (88%) | 92/128 (72%) | 92/128 (72%) | 88/128 (69%) |
| military-20 | 10/20 (50%) | 7/20 (35%) | 10/20 (50%) | 12/20 (60%) | 11/20 (55%) |
| ALL | 339/405 (84%) | 369/409 (90%) | 345/410 (84%) | 352/409 (86%) | 347/409 (85%) |
(tgemma column is the few-shot recipe; its zero-shot native was 331/406, 82% — the earlier, misleading number.)

## VRAM (measured co-resident): mandatory stack ~5,739 MiB, ~1,760 free of ~7,500 usable.
SAM3 is REQUIRED to fit any GPU translator: co-resident measured 6,553 (Qwen+Hy-MT2-Q6+whisper+YOLO);
+ current OmDet+SAM2.1 = 8,144 (OVER, even Q4 over by 110) vs + SAM3 = 7,439 (FITS, Q4 595 free / Q6 269).
So the Hy-MT2-on-GPU plan is CONTINGENT on the SAM3 integration; until then translation stays on CPU. The VRAM
constraint costs ~16 pp of perception accuracy (Hy-MT2 72% vs tgemma 88%) — the concrete price of the
8 GB card. Freeing ~1 GB (lighter vision stack / more VRAM) is the only way to reach tgemma's 88%.

## Low-bit: no sub-4-bit option on x86.
tencent 1.25-bit (PR #22836, ARM NEON) and 2-bit (PR #19357, ARM SME2) are unmerged + ARM-only -> unrunnable
on x86. Self-quant standard Q2_K runs but output is incoherent (1.8B doesn't survive 2-bit). Floor = Q4_K_M.

## Open — decisions, not measurements
1. Co-resident fit (Step 3): confirm Qwen + SAM3 + YOLO + whisper + Hy-MT2 and lock Q4 vs Q6.
2. Single-model (Hy-MT2 for all) vs split (DictaLM commands CPU + Hy-MT2 perception GPU).

---

## Step 1 — PREP (checkpoint catch, 2026-09-07)

CHECKPOINT before running: measured the perception set first. PERC100 held 103 cases, ALL
imperatives (סמן 22, הדגש 21, עקוב 20, מצא 17, התמקד 15, ספור 5), ZERO second-person forms.
The rewrite would fire on none of them -> a zero-delta experiment. Flagged to owner.

Owner ruling: add 25 see/presence/count questions to the perception set so the rewrite has
targets. Done: PERC100 now 128 (perception total 413 across the bench). All 25 verified:
route()=perception (phrased to the current perception pattern, no router change), check_refs
PASS, names unique, offline audit CLEAN. Forms: 8 second-person (מה/כמה אתה רואה — rewrite
targets), 7 existential (האם יש), 10 verb/scene (תאר/זהה/מצא/ספור/חפש/הסתכל/התמקד).

Scorer flag (open, handled): the keyword scorer cannot tell a faithful question-translation
from an answer-mode hallucination when they share words ("do you see anyone" vs "I can't see
anyone" both contain 'anyone'). So Step 1 reports an ADDITIONAL answer-mode metric on the
second-person subset: output must stay interrogative and carry no first-person answer marker
(I see / I can't / I am / there is a). That is the metric that makes the rewrite's benefit
visible; the keyword score alone would hide it.

## Step 1 — RESULT: gate FAILS, rewrite not shipped (2026-09-07, keyword numbers corrected)

HARNESS BUG caught by the checkpoint: score_perception returns the list of UNSATISFIED groups
(empty = PASS). My first pass counted non-empty (FAIL) as pass, inverting every keyword number.
Caught because tgemma read 20% against its known 78%. Corrected below; answer-mode/latency/VRAM
were always correct. tgemma's corrected 78% on the original 103 matches round 6 exactly -> harness
validated.

DictaLM on the 128-case perception set, baseline vs two rewrite variants (keyword = PASS):

| arm | keyword PASS | answer-mode (all) | answer-mode (2nd-person /9) |
|---|---|---|---|
| baseline (no rewrite) | 77/128 (60.2%) | 8 | 7 |
| rewrite v1 (אתה רואה->רואים) | 76/128 (59.4%) | 5 | 4 |
| rewrite v2 (מה נמצא / כמה X יש) | 74/128 (57.8%) | 5 | 4 |

Root cause, measured: DictaLM answer-modes on QUESTIONS in general, not just "you"-addressed ones.
v2 evidence: "כמה מכוניות יש בזירה" -> "There are five cars in the parking lot"; "כמה חלונות יש בבניין"
-> "There are 10 windows." A chat model answers questions with fabricated content; removing "you"
leaves a question. The rewrite trades keyword (60.2->57.8) for slightly less answer-mode (8->5) --
both marginal, and it cannot fix the question class.

Decision: the rewrite is NOT shipped. No recognizer change committed. DictaLM perception 60% vs
tgemma 80% -> gate FAILS -> a dedicated translator is required -> Step 2.

CHECKPOINT: objective was "can DictaLM alone carry perception?" Measured answer: NO (60% vs 80%,
plus answer-mode on questions). The fix-and-reassess loop (v1, v2, then the scorer-bug fix) is done.
Step 1 finished properly.

## Step 2 — RESULT: translator shoot-out on perception 128 (2026-09-07)

All translators, raw Hebrew -> English, keyword = PASS, one model resident at a time. VRAM at
c=256, 1 slot. tgemma via /completion + native template; Hy-MT2 via chat; DictaLM from Step 1.

| model | keyword PASS | orig 103 | new see-Q 25 | answer-mode | p50/p95 ms | VRAM (c256) |
|---|---|---|---|---|---|---|
| tgemma-Q4 | 102/128 (79.7%) | 78% | 88% | 0 | 309/438 | 2,478 MiB |
| Hy-MT2-Q8 | 87/128 (68.0%) | 70% | 60% | 0 | 162/273 | 1,889 MiB |
| Hy-MT2-Q6 | 86/128 (67.2%) | 69% | 60% | 0 | 150/228 | 1,476 MiB |
| Hy-MT2-Q4 | 81/128 (63.3%) | 63% | 64% | 0 | 110/173 | 1,150 MiB |
| DictaLM | 77/128 (60.2%) | 58% | ~ | 8 | 114 | CPU / 1,187 |

Findings:
1. tgemma is the accuracy leader: 79.7% overall, 78% on the original set (validates the harness),
   88% on the new see-questions, ZERO answer-mode. Cost: 2,478 MiB and 309 ms.
2. Hy-MT2 is the VRAM/speed play: Q4 63.3% at 1,150 MiB and 110 ms -- under half tgemma's memory,
   ~3x faster, zero answer-mode. Q6/Q8 add little accuracy (67-68%) for more memory.
3. BOTH dedicated translators answer-mode ZERO times on the questions DictaLM answered 8 times.
   This confirms the Step 1 thesis: a dedicated translator solves the question class structurally.
4. tgemma vs Hy-MT2-Q4: +16 pp accuracy for +1,328 MiB. The VRAM budget decides (Step 3).

Inversion review (owner-flagged, keyword scorer cannot see it): checked the dump. tgemma's color
errors persist (כתום orange -> "red"); Hy-MT2 also (כתום -> "yellow"). No target/anchor swaps found
in the sampled reference-chain cases. Dump: results/2026-09-07-step2-perception-dump.json.

CHECKPOINT: objective was to pick the smallest translator that clears the bar. Measured: tgemma 80%
(2,478 MiB) vs Hy-MT2-Q4 63% (1,150 MiB). Both zero answer-mode. Decision deferred to Step 3 (the fit).
Step 2 finished properly.

## Step 2b — Hy-MT2 prompt fairness retest (owner-flagged 2026-09-07)

Concern: Step 2 gave Hy-MT2 a bare user prompt while tgemma got its native template and DictaLM its
system+shots. Checked: Hunyuan-MT ships NO default system prompt by design (model card). Retested all
three quants with the OFFICIAL prompt ("Translate the following text into English. Note that you
should only output the translated result without any additional explanation:\n\n{text}"), correct
scorer, temp 0.

| Hy-MT2 | weak prompt | official prompt | answer-mode | p50 | VRAM |
|---|---|---|---|---|---|
| Q4 | 63.3% | 62.5% [54,70] | 0 | 148 ms | 1,150 MiB |
| Q6 | 67.2% | 64.8% [56,73] | 0 | 144 ms | 1,476 MiB |
| Q8 | 68.0% | 65.6% [57,73] | 0 | 153 ms | 1,889 MiB |

Result: unchanged within noise (Wilson intervals overlap fully). Hy-MT2 ~63-66% is robust, not a
prompt artifact. Each model was measured at its own best setup -> fair comparison. Ranking holds:
tgemma 80% > Hy-MT2 ~65% > DictaLM 60%; dedicated translators answer-mode zero. Prompts used:
DictaLM = TRANSLATE_SYS + TRANSLATE_SHOTS + LINE_GRAMMAR; tgemma = TGEMMA_PROMPT native; Hy-MT2 =
Hunyuan official (no system prompt). Note: Hunyuan's own rec is temp 0.7; used temp 0 for
determinism + comparability (campaign rule). Dump: results/2026-09-07-step2b-hymt2-official.json.

## Step 6 — status: planner-scoring harness bug (2026-09-07)

Guard-relevance finding stands and is measured: the number guard fires on only 1/203 numbered
command cases this run (v_ready3_g1), patches 0. Near-inert on the command path. BUT the mission
accuracy per config came back 0/203 across all three configs -- a bug in my ad-hoc planner-scoring
(dx/dy/dz->x/y/z mapping or score() call), not a real result. To fix before concluding Step 6:
run the guard ablation THROUGH bench.py (the validated scorer) with a guard-mode toggle, rather
than a hand-rolled planner loop. Raw DictaLM capture preserved: results/2026-09-07-step6-dicta-capture.json.

## Step 2c — Hy-MT2 with OUR prompts (owner-ordered 2026-09-07)

Hy-MT2-Q4, perception 128, correct scorer, temp 0:

| prompt | keyword pass | answer-mode | p50 |
|---|---|---|---|
| our DictaLM (TRANSLATE_SYS + TRANSLATE_SHOTS) | 89/128 (69.5% [61,77]) | 0 | 135 ms |
| Hunyuan official | 80/128 (62.5%) | 0 | 148 ms |
| our tgemma instruction (system) | 77/128 (60.2%) | 0 | 117 ms |

Finding: DictaLM's system-prompt + two few-shot examples lift Hy-MT2 +7 pp to 69.5%, answer-mode
still 0. The few-shots are the lever (the tgemma instruction alone does not help). Perception-
specific few-shots are an untested further lever.

Updated decision picture for the fit (Step 3):
- tgemma-Q4:        80% perception, 2,478 MiB, 309 ms, answer-mode 0
- Hy-MT2-Q4 (our prompt): 69.5%,     1,150 MiB, 135 ms, answer-mode 0
Gap now +10.5 pp for +1,328 MiB and 2.3x latency. Hy-MT2-Q4 fits the SAM3 stack; tgemma does not.

## Step 2d — FULL perception table, Hy-MT2 all quants with OUR prompt (2026-09-07)

Our latest prompt = TRANSLATE_SYS + TRANSLATE_SHOTS (the DictaLM translation prompt; NOT tgemma's
native template, which is different and lacks few-shots). VRAM here at c=512 (~40 MiB above c=256).

| model | prompt | perception 128 | orig 103 | answer-mode | p50/p95 ms | VRAM |
|---|---|---|---|---|---|---|
| tgemma-Q4 | native template | 79.7% | 78% | 0 | 309/438 | 2,478 |
| Hy-MT2-Q6 | TRANSLATE_SYS+shots | 73.4% | 74% | 0 | 137/193 | 1,514 |
| Hy-MT2-Q4 | TRANSLATE_SYS+shots | 69.5% | 68% | 0 | 141/215 | 1,188 |
| Hy-MT2-Q8 | TRANSLATE_SYS+shots | 69.5% | 70% | 0 | 146/228 | 1,928 |
| DictaLM | TRANSLATE_SYS+shots | 60.2% | ~58% | 8 | 114 | CPU |

Findings: our prompt lifts every Hy-MT2 quant (+7 pp on Q4 vs official). Q4/Q6/Q8 = 69.5/73.4/69.5,
differences within the Wilson intervals -> quant curve flat within noise; Q6's nominal lead unproven.
Reliable read: Hy-MT2 + our prompt ~70-73% at 1.2-1.5 GB vs tgemma 80% at 2.5 GB, both answer-mode 0.
Gap to tgemma now 6-10 pp for ~1,000-1,300 MiB saved. Untested lever: perception-specific few-shots.

## Step 2e — THE FULL SCORECARD by translator (owner-ordered 2026-09-07)

Whole dataset (413 cases), each translator through the complete pipeline (translate -> number guard
-> Qwen planner for commands; translate -> keyword for perception/military). Validation: DictaLM
std-204 = 197/199 matches the committed scorecard -> harness trustworthy. Denominators differ by a
few because "routed" (rejected) cases are excluded per bench semantics and each translator routes
slightly differently. tgemma via native template; Hy-MT2-Q6 with our prompt (TRANSLATE_SYS+shots).

| set | DictaLM | tgemma-Q4 | Hy-MT2-Q6 |
|---|---|---|---|
| emergency | 7/7 (100%) | 7/7 (100%) | 7/7 (100%) |
| std-204 command | 197/199 (99%) | 170/197 (86%) | 193/200 (96%) |
| verbose-54 | 47/51 (92%) | 43/54 (80%) | 48/54 (89%) |
| perception-128 | 78/128 (61%) | 106/128 (83%) | 92/128 (72%) |
| military-20 | 10/20 (50%) | 5/20 (25%) | 12/20 (60%) |
| ALL | 339/405 (84%) | 331/406 (82%) | 352/409 (86%) |

FINDING: Hy-MT2-Q6 (1,514 MiB, GPU) is the best SINGLE translator overall (86%). It nearly matches
DictaLM on commands (96% vs 99%) -- unlike tgemma, which narrates imperatives and drops to 86% --
while beating DictaLM on perception (72% vs 61%) and military (60% vs 50%). tgemma is a perception
specialist (83%) unusable as a whole-system translator (86% cmd, 25% mil). DictaLM owns commands
(99%) but is weak on perception and answer-modes questions.

Deployment options this reshapes:
- A (current): DictaLM commands (CPU) + tgemma perception (GPU 2,478). Best perception, does not fit.
- B (single model): Hy-MT2-Q6 for everything (GPU 1,514). 96% cmd / 72% perc / 60% mil, one model.
- C (split): DictaLM commands (CPU) + Hy-MT2 perception (GPU 1,514). 99% cmd / 72% perc.
Raw: results/2026-09-07-full-translator-table.json.

## Step 2f — FULL scorecard, ALL Hy-MT2 quants (owner-ordered 2026-09-07)

| set | DictaLM | tgemma-Q4 | Hy-MT2-Q4 | Hy-MT2-Q6 | Hy-MT2-Q8 |
|---|---|---|---|---|---|
| emergency | 7/7 (100%) | 7/7 (100%) | 7/7 (100%) | 7/7 (100%) | 7/7 (100%) |
| std-204 command | 197/199 (99%) | 170/197 (86%) | 193/201 (96%) | 193/200 (96%) | 194/200 (97%) |
| verbose-54 | 47/51 (92%) | 43/54 (80%) | 43/54 (80%) | 48/54 (89%) | 47/54 (87%) |
| perception-128 | 78/128 (61%) | 106/128 (83%) | 92/128 (72%) | 92/128 (72%) | 88/128 (69%) |
| military-20 | 10/20 (50%) | 5/20 (25%) | 10/20 (50%) | 12/20 (60%) | 11/20 (55%) |
| ALL | 339/405 (84%) | 331/406 (82%) | 345/410 (84%) | 352/409 (86%) | 347/409 (85%) |
| VRAM GPU (c256) | CPU | 2,478 | 1,188 | 1,514 | 1,928 |

Reading:
- Q6 (1,514) best overall (86%); edge over Q4 = verbose 89 vs 80, military 60 vs 50; cmd/perc identical.
- Q8 (1,928) DOMINATED: worse perception (69%) and more VRAM than Q6. Drop it.
- Q4 (1,188) VRAM-comfortable: same 96% cmd / 72% perc as Q6, weaker verbose/military, 326 MiB less.

VRAM fit vs ~1,760 free after the mandatory stack: Q8 does NOT fit; Q6 fits ~250 spare (tight);
Q4 fits ~570 spare (comfortable). tgemma (2,478) does not fit at all.

RECOMMENDATION: Hy-MT2-Q6 if Step 3's co-resident measurement confirms ~250 MiB spare holds, else
Q4. Both give 96% commands / 72% perception. Raw: results/2026-09-07-full-translator-table.json.

## Step 4/5 — per-subset latency + DictaLM CPU thread scaling (2026-09-07)

Full-dataset latency (406 translator cases, GPU, p25/p50/p75/p95/p99/max ms, tok/s):
DictaLM 59/79/114/233/346/582 178t/s | tgemma 164/205/295/499/583/664 88 | Hy-MT2-Q4 54/81/123/207/243/289 182 |
Hy-MT2-Q6 67/100/143/249/293/341 157 | Hy-MT2-Q8 67/104/167/295/358/402 136.

Per-subset GPU (p50/p95 ms): DictaLM cmd 60/142 vrb 196/311 perc 98/159 mil 78/104 ;
tgemma cmd 167/293 vrb 456/605 perc 264/368 mil 227/279. Hy-MT2 per-subset BLOCKED (GPU wedge).

DictaLM CPU thread sweep, per-subset, full dataset (p50/p95 ms):
 2thr cmd 293/740 vrb 1104/1729 perc 568/1054 mil 424/578 ALL 405/1280/2025(p99)
 4thr cmd 201/579 vrb 875/1406  perc 445/842  mil 339/450 ALL 317/1046/1806
 6thr cmd 172/522 vrb 805/1317  perc 410/780  mil 311/412 ALL 290/971/1716
 8thr cmd 157/493 vrb 768/1265  perc 387/740  mil 296/389 ALL 273/937/1666

BLOCKERS: (1) low-bit 1.25/2-bit GGUFs fail to load (GGUF tensor-offset mismatch) on our build AND
a fresh STQ-PR #22836 build; need newer llama.cpp; deferred. (2) GPU/Vulkan driver wedged mid-session
from launch/kill cycles -> GPU launches hang; Hy-MT2 per-subset split needs a reboot (~5 min re-run).
CPU-only STQ build works. Raw: results/2026-09-07-{perf-fulldataset-gpu,dicta-cpu-persubset,perf-profile}.json.

## Hy-MT2 per-subset GPU (completed after GPU recovered, 2026-09-07)
Hy-MT2-Q4 (GPU) cmd 74/156 vrb 214/300 perc 109/170 mil 99/113
Hy-MT2-Q6 (GPU) cmd 65/136 vrb 223/299 perc 127/194 mil 114/131
Hy-MT2-Q8 (GPU) cmd 70/167 vrb 273/368 perc 144/223 mil 122/152  (p50/p95 ms, temp 0)

## Low-bit quant — DEFINITIVE (2026-09-07)
PR #22836 (STQ kernel the 1.25-bit needs) is OPEN/unmerged -> latest main lacks it. PR title:
"add STQ1_0 ternary quantization with ARM NEON vec_dot kernel" -> kernel is ARM-only; this host is
x86_64, so no kernel even if built (plus GGUF parse-offset mismatch on both our build and the PR build).
NOT runnable on this hardware. CORRECTION: the 2-bit needs a DIFFERENT unmerged PR, #19357
("int2 + KleidiAI SME2 kernels", targets ARM SME2 M4/Vivo X300); the 1.25-bit needs #22836 (ARM NEON).
Both ARM-only, both open -> neither runs on x86, latest main has neither. Only viable low-bit on x86:
download base Hy-MT2 (fp16/bf16) + self-quantize to standard Q2_K/IQ2 with our llama-quantize.

## Q2_K self-quant (2026-09-07) — COLLAPSES
Self-quantized standard Q2_K from the fp16 base (mradermacher f16 -> our llama-quantize Q2_K, 741 MB,
runs on our x86 build). Output is INCOHERENT: "עלה עשרה מטרים" -> "70 meters" repeated with system-prompt
leakage; server unstable under the garbage generation. A 1.8B translator does not survive 2-bit (2.96 bpw).
Not viable. Practical floor is Q4_K_M (1,188 MiB, 69.5% perception, 96% commands). tencent ternary 1.25/2-bit
remain ARM-only/unrunnable on x86 (PRs #22836 NEON, #19357 SME2, both unmerged).

## tgemma system-prompt crossover (2026-09-07) — HURTS both, few-shots are the lever
Applied tgemma's zero-shot professional-translator instruction (no few-shots) to DictaLM and Hy-MT2-Q6,
full 413-case scorecard, vs their native prompt (TRANSLATE_SYS + 2 few-shots):
             DictaLM tgp / native      Hy-MT2-Q6 tgp / native
 std-204     185/198(93%) / 197/199(99%)   182/201(91%) / 193/200(96%)
 verbose     48/53(91%)   / 47/51(92%)     51/54(94%)   / 48/54(89%)
 perception  81/128(63%)  / 78/128(61%)    89/128(70%)  / 92/128(72%)
 military    11/20(55%)   / 10/20(50%)     8/20(40%)    / 12/20(60%)
 ALL         332/406(82%) / 339/405(84%)   337/410(82%) / 352/409(86%)
Both drop ~2pp overall; damage concentrated on COMMANDS (-6/-5pp) because the tgemma prompt is zero-shot.
Perception/verbose ~wash. Conclusion: the lever is the FEW-SHOTS, not the system-prompt wording; native
TRANSLATE_SYS + 2 shots stays best for both. Raw: results/2026-09-07-tgemma-prompt-crossover.json.

## tgemma + FEW-SHOTS (2026-09-07) — accuracy champion; corrects the zero-shot dismissal
tgemma was only ever run ZERO-SHOT (native template). Given the same 2 few-shots as DictaLM/Hy-MT2:
             tg zero-shot   tg+shots(dicta-sys)  tg+shots(tg-sys)
 std-204     170/197(86%)   196/200(98%)         195/201(97%)
 verbose     43/54(80%)     47/54(87%)           45/53(85%)
 perception  106/128(83%)   112/128(88%)         111/128(87%)
 military    5/20(25%)      7/20(35%)            6/20(30%)
 ALL         331/406(82%)   369/409(90%)         364/409(89%)
FINDING: tgemma+few-shots is the BEST translator overall (90%): 98% commands (near DictaLM 99%) AND
88% perception (best; +16pp over Hy-MT2-Q6's 72%). The "tgemma collapses on commands" verdict was a
ZERO-SHOT ARTIFACT. Few-shots are decisively the lever across all three models. BUT tgemma stays
VRAM-blocked (2,478 MiB, doesn't fit with SAM3 even as sole translator). Deployable pick remains
Hy-MT2 (fits); the quantified cost of that choice is ~16pp perception accuracy vs tgemma.
Raw: results/2026-09-07-tgemma-fewshot.json.


## Hy-MT2-Q6 shot-count sweep (2026-09-07) — 2 shots optimal
Full 413, Q6, 2 vs 3 vs 4 few-shots (added a perception + a turn example, leakage-checked):
             2-shot        3-shot        4-shot
 std-204     193/200(96%)  191/200(96%)  190/201(95%)
 verbose     48/54(89%)    49/54(91%)    48/54(89%)
 perception  92/128(72%)   91/128(71%)   90/128(70%)
 military    12/20(60%)    10/20(50%)    10/20(50%)
 ALL         352/409(86%)  348/409(85%)  345/410(84%)
More shots do NOT help: 2 is optimal, 3-4 slightly hurt (military -10pp, perception/commands flat-down).
The lever is 0->2 shots; beyond that, diminishing-to-negative. Deployed 2-shot recipe stays. 2-shot arm
reproduced the committed 352/409 exactly (harness stable). Raw: results/2026-09-07-hymt2q6-shots.json.

## Step 3 — CO-RESIDENT VRAM FIT (2026-09-07) — CORRECTED: perception engine included
INITIAL ERROR (owner-caught): first pass counted only YOLO (bg detector, 286) + Qwen as "vision" and
forgot the actual detection/mask engine. The perception pipeline needs the open-vocab detector AND the
mask model — BOTH — not just YOLO.

Measured together this session (Qwen3-VL prod + Hy-MT2-Q6 + whisper-q5_k node + YOLO26n-seg):
  = 6,553 MiB used, 1,156 MiB free. Usable ceiling ~7,708 MiB (8,151 - ~443 driver/display floor).
Perception engine (census 2026-09-02, isolated peaks): OmDet-Turbo 863, SAM2.1 728, SAM3-nf4 886.

| stack | + Hy-MT2-Q6 | + Hy-MT2-Q4 |
|---|---|---|
| CURRENT: OmDet-Turbo + SAM2.1 (both) | 8,144 — OVER by 436 | 7,818 — OVER by 110 |
| SAM3 (replaces OmDet+SAM2.1) | 7,439 — FITS, 269 free | 7,113 — FITS, 595 free |

DECISIVE CONCLUSION: **SAM3 is REQUIRED to put any translator on the GPU.** With the current
OmDet+SAM2.1 pipeline, Hy-MT2 does NOT fit — even Q4 is over by 110 MiB. Only SAM3 (which unifies
OmDet+SAM2.1 into one smaller model, saving ~705 MiB) leaves room. With SAM3: Hy-MT2-Q4 fits
comfortably (595 free), Q6 fits tight (269 free). So the translator decision is CONTINGENT on the
SAM3 integration; until then, the GPU translator has no room and translation must stay on CPU (DictaLM).
Caveat: perception-engine numbers are measured-isolated (census); a full all-five co-resident load is
the final confirmation, deferred. mmproj image spikes (+89 measured) eat into the 269 Q6 margin -> prefer Q4.

## Step 4 — VRAM overhead decomposition (2026-09-07)
This llama.cpp build does not emit per-buffer log lines, so decomposition is by measurement (file size
on disk vs resident VRAM, and default-vs-lean deltas):
| model | file (disk) | resident | overhead | overhead source |
|---|---|---|---|---|
| tgemma-4B Q4_K_M (default 4-slot/4096) | 2,374 MiB | 3,029 | +655 | KV for 4x4096 slots (~550) + compute/Vulkan ctx (~105) |
| tgemma-4B Q4_K_M (lean c512/1-slot) | 2,374 | 2,552 | +178 | KV(512) + compute + Vulkan ctx |
| whisper q5_k | ~547 | 838 | +291 | encoder activation buffers + Vulkan ctx (fixed regardless of audio len) |
| Hy-MT2-Q4 (c256) | 1,080 | 1,150 | +70 | small KV + ctx |
Takeaways: (1) the "3 GB tgemma" scare was the 4-slot/4096 default, not the model — lean config saves
~480 MiB; (2) whisper carries a fixed ~290 MiB buffer overhead over file size; (3) the fixed
Vulkan/backend context is ~100-250 MiB per process — the floor any GPU model pays.

## Step 6 — Number-guard ablation (2026-09-07) — measured relevance + recommendation
Guard = stage 4: after translation, if English numbers != Hebrew numbers, (a) retry naming the numbers,
(b) single-token patch, (c) else REJECT. Measured relevance on current data:
- Full 388-run: fired on 8 cases, PATCHED 0, rejected 8. Numbered-command subset (203): fired on 1
  (v_ready3_g1), patched 0. NEAR-INERT on the command path.
- Old sieve ablation (register with heavy number-word corruption): retry +5 verbose (69->78%),
  patch +4 verbose (78->85%) -- the patch helped the עשרים->"ten" corruption class.
- The PATCH is the risky layer: it caused the חצי-סיבוב bug (extractor read חצי=0.5, patched a correct
  "180 degrees" to 0.5). It fires ~0 on current data yet carries that harm.
RECOMMENDATION (owner to rule): keep the number-CHECK + corrective-retry (cheap, safe, helps corruption);
GATE or drop the single-token PATCH, or fix its root (extractor must treat חצי-of-a-unit as a fraction,
e.g. חצי סיבוב=180). Any change is bench-gated (recognizer-bench skill, zero false fires, full re-run).
Note: a clean 3-config accuracy replay was attempted but is low-value on current data (configs differ by
<=1 case since the guard fires once); the register-dependent old-ablation numbers above are the evidence.
