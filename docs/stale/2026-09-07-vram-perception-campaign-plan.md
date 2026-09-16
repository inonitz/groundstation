# VRAM + perception measurement campaign — PLAN
Owner: groundstation-05 (ref 55e80f), live-test agent. Model: Opus 4.8. Date: 2026-09-07.
Approved by the repo owner. Results doc: 2026-09-07-vram-perception-campaign-results.md (same dir).

## Objective (the compass)
The demo video is 2 days out: talk to the system in Hebrew, show perception, show it approaching a
target (the CV -> flight-planning link). Finalize the system today. The stack must fit ~7,500 MiB
of usable VRAM with SAM3 resident.

## The structure (one spine, two levers, supports, one rider)
- Spine: the VRAM fit (Step 3). The mandatory stack (Qwen + SAM3 + YOLO + whisper) already fills the
  card, leaving no room for a perception translator.
- Lever A = Step 1: if DictaLM with a rewrite handles perception, the translator slot is zero.
- Lever B = Step 2: if we still need a translator, Hy-MT2 (~1.2 GB) replaces tgemma (~2.5 GB).
- Whisper stays on the GPU: there is no accessible Hebrew parakeet. Step 5 only picks the quant.
- Step 4 feeds Step 3 (why each model costs what it costs). Step 6 is correctness, not VRAM.

## Shared rules
- One model resident on the GPU at a time. Load, measure, kill, next.
- Temperature 0 everywhere. Determinism proven within one server session.
- Recognizer changes go through the recognizer-bench skill: positives, adversarial negatives, zero
  false fires, full 388-case re-run vs the 2026-09-07 baseline.
- Every accuracy table: Wilson 95%. Every paired test: exact McNemar. Every table: latency p50/p95.
- Duration estimate stated before each GPU run. All results to the results doc.

## CHECKPOINT PROTOCOL (owner-ordered 2026-09-07)
After finishing each step: reread this step, write what I performed into the results doc, and match
it against the "Objective / Method / Output / Decision rule" written here. If they match, advance.
If not, fix and reassess until the step is done properly. Only then move to the next step.

---

## Step 1 — DictaLM perception gate (pivot)
- Objective: with the "you"-form removed, can DictaLM alone translate perception well enough that no
  second model is needed? Pass = tgemma and Hy-MT2 both unnecessary.
- Method: build a deterministic Hebrew rewrite turning second-person perception questions into a
  character-free form (e.g. "אתה רואה מישהו בתמונה" -> "יש מישהו בתמונה"). Source forms: the answer-mode
  cases (l_pres_you, q_land_trap, l_tower_count, v_q2, the אתה רואה / האם אתה רואה family). Show the
  rewrite rules + positives + adversarial negatives in the results doc. Run DictaLM over perception-103
  twice: baseline (56%) and with the rewrite.
- Scoring: score_perception; accuracy, Wilson 95%, paired McNemar rewrite vs baseline; latency p50/p95.
- Regression guard: rewrite runs on all input, so the full 388-case bench must show zero command loss.
- Decision rule: propose PASS if DictaLM+rewrite reaches within ~3 pts of tgemma's 78% (>=75%). Owner
  sets the final bar.
- Runtime: ~10 min.

## Step 2 — Perception translator shoot-out (fallback; runs regardless for the record)
- Objective: if Step 1 fails, pick the smallest translator that clears the bar (Hy-MT2 ~1.2 GB vs
  tgemma ~2.5 GB).
- Method: Hy-MT2 Q4_K_M / Q6_K / Q8_0 on /v1/chat/completions; reference arms tgemma (78%) and
  DictaLM (56%). All translate perception-103 directly: raw Hebrew in, English out, no guard, no
  rewrite. Measure resident VRAM per Hy-MT2 quant (c=256, 1 slot).
- Scoring: score_perception, Wilson 95%, McNemar each Hy-MT2 quant vs tgemma; latency p50/p95; MiB.
- Inversion check: keyword scorer cannot see relation inversion; read the dump by hand for swapped
  relations (car-next-to-person vs person-next-to-car) and report.
- Decision rule: smallest quant reaching the bar with no inversions = tgemma replacement candidate.
- Runtime: ~8 min.

## Step 3 — VRAM fit integration
- Objective: take the winning levers, report the final topology, prove it on the card.
- Method: compute the stack for the winning path; load it co-resident, one warm inference each, read
  real free memory (the method that gave 7,505 resident tonight). tgemma Q3_K_M ladder + q8 mmproj
  run unconditionally (owner: time available).
- Output: topology table (component, MiB, running total, free); measured yes/no on SAM3 fit.
- Runtime: ~2-15 min.

## Step 4 — VRAM overhead decomposition (owner 4B)
- Objective: explain why resident > file size, for whisper and tgemma.
- Method: capture each server's startup report (model buffer, KV, compute buffer, backend context),
  sum vs the nvidia-smi delta. Folded into Steps 2 and 5 launches.
- Output: per-model breakdown: file size, each buffer line, total, next to measured delta.
- Runtime: ~5 min folded.

## Step 5 — Whisper accuracy (finish the existing benchmark)
- Objective: pick the whisper quant on evidence.
- Already done (2026-09-03, 792 FLEURS clips): fp16 18.72, q8_0 18.73, q5_1 18.79, q4_0 19.59 WER;
  wav2vec2 64 (dead). Classic quants only.
- Gap: k-quants q4_k/q5_k/q6_k never scored; our real clips never used.
- Method: add three k-quant lanes to asr_bench.py LANES; run run.sh over 792 FLEURS clips. Build a
  second manifest from our session clips (reference = canonical sentence per clip, misspeaks dropped);
  run all quants on it.
- Scoring: WER, CER, bootstrap CI, per-clip transcription time. Two tables: FLEURS and our clips.
- Decision rule: if q4_k matches q5_k WER, ship q4_k (saves 95 MiB). Owner rules.
- Runtime: ~12 min.

## Step 6 — Number-guard ablation (owner; correctness not VRAM)
- Objective: measure the DictaLM number-guard fix; decide keep / trim patch / fix root; check it does
  not damage DictaLM elsewhere.
- Method: capture DictaLM raw translations for all 388 cases once, in one server session. Replay three
  guard settings offline over those fixed translations: guard off, retry only, retry + digit patch.
  Replay avoids KV-cache drift.
- Scoring: full mission accuracy per config per set; per layer, count fixes and breaks; list every
  fire (incl. חצי where the patch overwrote 180 with 0.5).
- Decision rule: keep full guard / keep retry drop patch / fix the root (extractor learns חצי is a
  fraction of a unit). No change ships without a clean 388-case re-run. Owner rules.
- Runtime: ~5 min.

## Order and total
Order: 1, 2, 5, 6 (4 folds in), 3 integrates last.
Total: ~40-50 min core, +~15 for the tgemma ladder (runs regardless).
