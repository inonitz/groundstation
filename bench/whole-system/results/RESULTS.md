# Whole-system stack swap and vision evidence — 2026-09-08

Authoritative result document for the 2026-09-08 whole-system run. It consolidates the dated
fragment reports under `results/2026-09-08/`. Code: `tools/bench/whole-system/`.

## 1. Objective

Decide which stack ships for the Hebrew voice-drone pipeline, with measured evidence and no
drone, phone, or microphone in the loop. Two questions are in scope.

First: whether SAM3 replaces the OmDet-Turbo + SAM2.1 detector and segmenter in the highlight
path, and whether SAM3 alone can also serve as the presence gate.

Second: whether a single-model candidate stack (whisper -> Gemma 4 E4B as a direct Hebrew
planner and VLM -> SAM3) may replace the current stack (whisper -> Recognizer with a translator
-> Qwen3-VL planner; Qwen3-VL VLM; SAM3 highlight).

The directory measures. Rulings are the owner's.

## 2. Setup

Stacks compared:

| stack | role on 2026-09-08 |
|---|---|
| DictaLM -> Qwen3-VL | current live default (CPU-side translator fallback) |
| Hy-MT2-Q4 -> Qwen3-VL | deployed GPU translator path |
| Gemma 4 E4B direct Hebrew + SAM3 | single-model candidate |

Models under test. The translator candidates feed the Qwen3-VL-4B planner. The Gemma file is
`gemma-4-E4B-it-qat-UD-Q4_K_XL.gguf`, 4,215,695,776 bytes (3.93 GiB), with vision projector
`mmproj-BF16.gguf`, 991,552,320 bytes (0.92 GiB), served by llama-server with
`--reasoning-budget 0` and a format grammar. ASR is whisper large-v3-turbo q5_k, beam 4.

Dataset, commands (no clip content): the Hebrew command bench. The 413-case edition splits into
standard, verbose, and perception cases. A later 488-case edition adds cases and is used for the
two end-to-end rows. Temperature 0; determinism is a property of the harness; one model is
resident on the GPU at a time.

Dataset, vision: 26 images, being 17 bench candidate images plus 8 desk-camera frames, with gate
phrases per image and one people count per image. This yields 104 gate asks (72 bench-image asks
plus 32 desk-frame asks). One phrase, "boiler", is absent by construction on all 26 images.

Ground truth, vision: none exists. The reference is SAM3 run on the asked concept. The presence
labels in `labels/presence-2026-09-08-vlm-consensus.json` are the consensus of the Qwen3-VL and
Gemma 4 gates, not human truth; they cover 89 of 104 asks (28 present, 61 absent), with 15 asks
disputed and left for a human eye.

Metrics: planning pass rate per case; VLM presence-gate agreement with the SAM3 reference; the
highlight chain (a VLM names the object and hands SAM3 a phrase SAM3 can localize); people count
against the SAM3 count; SAM3 detect latency p50/p95; and co-resident VRAM against the 8,151 MiB
budget.

Lanes not covered here: TTS, the phone link, drone motion, and free-form VLM answers.

## 3. Results

### 3.1 Planning, bench command and perception cases

413-case edition. Denominators are copied per row from the source; the ALL column spans
additional routing and safety cases beyond the three named categories.

| stack | std | verbose | perception | ALL |
|---|---|---|---|---|
| Hy-MT2-Q4 -> Qwen3-VL (deployed) | 197/203 | 44/54 | 91/128 | 348/412 |
| DictaLM -> Qwen3-VL (CPU fallback) | 202/203 | 50/54 | 78/128 | 346/412 |
| planner ceiling: reference English -> Qwen3-VL | 201/204 | 45/54 | — | 246/258 |
| planner ceiling: reference English -> Gemma 4 E4B | 195/204 | 51/54 | — | 246/258 |
| candidate: Hebrew -> Gemma 4 E4B directly, no translator | 195/203 | 52/54 | n/a | 247/257 |
| reference: Hebrew -> Qwen3-VL directly | 187/203 | 35/54 | n/a | 222/257 |
| Gemma 4 E4B as translator -> Qwen3-VL (v1 prompt, 2 shots) | 198/203 | 26/54 | 116/128 | 359/412 |
| Gemma 4 E4B as translator, TranslateGemma zero-shot prompt | 151/203 | 6/54 | 6/128 | 171/412 |
| Gemma 4 E4B as translator -> Qwen3-VL, v1 prompt, enable_thinking=false | 202/203 | 51/54 | 117/128 | 389/412 |

488-case edition, same-day gate:

| stack | std | verbose | perception | ALL |
|---|---|---|---|---|
| harden2 end to end: Gemma 4 alone, unified call (routing + plan + SAM3 phrase) | 236/253 | 59/63 | 108/138 | 415/487 |
| harden: Hy-MT2 -> Qwen3-VL | 247/253 | 51/63 | 100/138 | 420/487 |

Flight-planning totals, command cases only, three stacks on the same cases (source
`planning-per-case.md`): Gemma 4 direct 247/258, Hy-MT2 -> Qwen 241/258, DictaLM -> Qwen 252/258.
25 cases have at least one stack not passing.

### 3.2 SAM3 alone as the presence gate — threshold sweep

Labeled asks 89 (28 present, 61 absent). SAM3 ran once per ask at score floor 0.05; presence at
threshold t is max score >= t. SAM3 is deterministic. "bench" is the 61 bench-image labeled asks;
"desk" is the 28 labeled desk-frame asks.

| candidate gate | correct / labeled | false present / absent asks | missed / present asks | bench correct | desk correct |
|---|---|---|---|---|---|
| SAM3 alone, max score >= 0.3 | 81/89 | 7/61 | 1/28 | 53/61 | 28/28 |
| SAM3 alone, max score >= 0.4 | 82/89 | 6/61 | 1/28 | 54/61 | 28/28 |
| SAM3 alone, max score >= 0.5 | 82/89 | 6/61 | 1/28 | 54/61 | 28/28 |
| SAM3 alone, max score >= 0.6 | 82/89 | 6/61 | 1/28 | 54/61 | 28/28 |
| SAM3 alone, max score >= 0.7 | 83/89 | 5/61 | 1/28 | 55/61 | 28/28 |
| SAM3 alone, max score >= 0.8 | 79/89 | 4/61 | 6/28 | 56/61 | 23/28 |
| gemma4 gate (production prompt) | 89/89 | 0/61 | 0/28 | 61/61 | 28/28 |
| qwen3vl gate (production prompt) | 89/89 | 0/61 | 0/28 | 61/61 | 28/28 |

SAM3 detect latency per ask, first call excluded: p50 451 ms, p95 970 ms. The "boiler" phrase
produced zero SAM3 detections on all 26 images at the 0.05 floor. At threshold 0.5, SAM3
disagrees with the consensus label on 7 asks; of these, three are street or street-grid scenes
where the VLMs said no window or car (SAM3 max 0.91, 0.81, 0.84) and one is a truck the VLMs
called a car, so the consensus is the suspect there, not SAM3.

### 3.3 VLM comparison — two production jobs, scored against the SAM3 reference

| model/mode | gate agreement | 'boiler' false present | box IoU median (n) | count exact | count within 1 | format ok | latency p50/p95 ms | VRAM MiB |
|---|---|---|---|---|---|---|---|---|
| qwen3vl/prod | 88/104 | 0/26 | 0.47 (28) | 11/26 | 12/26 | 104/104 | 2150/2974 | 4826 |
| gemma4/grammar | 91/104 | 0/26 | 0.02 (35) | 2/26 | 3/26 | 104/104 | 1520/1967 | 4916 |

Highlight chain: the VLM gate says present and hands SAM3 its phrase; SAM3 then localizes.
"hit" is SAM3 returning a box with IoU >= 0.5 against the reference top box.

| model/mode | gate ok | said present when ref present | SAM3 hit from the VLM phrase | phrase gave SAM3 nothing | VLM-box fallback IoU >= 0.5 |
|---|---|---|---|---|---|
| qwen3vl/prod | 88/104 | 28/42 | 22/28 | 0/28 | 13/28 |
| gemma4/grammar | 91/104 | 35/42 | 28/35 | 1/35 | 3/35 |

### 3.4 VRAM, co-resident

Measured co-resident today, the SAM3 stack: Qwen 3,821 + Hy-MT2-Q4 1,187 + whisper q5_k 827 +
YOLO 282 + SAM3-nf4 1,074 + image transient 94 = 7,396 MiB used of 8,151, leaving 313 MiB free.
Fit holds at Q4 only; SAM3-nf4 is 1,074 MiB in process, so a Q6 SAM3 (+326) would overrun.

Gemma 4 E4B measured 3,950 MiB in a standalone probe and 4,916 MiB in the vlm-compare harness,
where Qwen measured 4,826 MiB in the same harness, a +90 MiB delta. Derived candidate-stack
footprint, not measured co-resident: 7,396 - 1,187 (translator dropped) + 90 (Gemma vs Qwen) =
about 6,300 MiB. The saving is the translator, not Gemma.

whisper q5_k: 838 MiB resident in isolation, 827 MiB co-resident; per-clip latency GPU 0.29 s vs
CPU 5.5 s, over 20 real push-to-talk clips of median 2.4 s audio. k-quant WER/CER is (not
recorded).

### 3.5 Audio replay, aggregate outcomes

Real push-to-talk clips fed through whisper q5_k and the pipeline, after the six fixes, on the
same audio the live runs used. Counts only; no clip content.

| session | clips matched / unmatched | Hy-MT2 -> Qwen | DictaLM -> Qwen |
|---|---|---|---|
| Step 1 mic session vs live-test-50 | 57 / 8 | 35 pass, 2 fail, 20 review | 34 pass, 3 fail, 20 review |
| Step 3 mic session vs live-test-75 v2 | 53 / 35 | 18 pass, 14 fail, 21 review | 23 pass, 9 fail, 21 review |

Unmatched clips overlap no list line (ad-hoc sentences, repeats, the v1/v2 Set-1 difference). The
live runs on the same audio, before the six fixes, scored 38/50 and 41/69; these replay numbers
are the after-fix result on identical input.

## 4. Analysis

1. SAM3 replaces OmDet-Turbo + SAM2.1 as the unified detector and segmenter. On the highlight
   chain it localizes the asked object from a VLM phrase more often than the old path's scores
   suggested, and it carries both detection and masks in one model. Its in-process footprint is
   1,074 MiB at nf4, which fits the 8,151 MiB budget where the prior multi-model detector path did
   not leave room for a GPU translator.

2. SAM3 can also serve the presence gate on this set. At max score >= 0.5 it matches the VLM
   consensus on 82 of 89 labeled asks, with 6 false presents on 61 absent asks and 1 miss on 28
   present asks, and 28/28 on desk frames. It never fired on the absent "boiler" phrase. A gate
   built on SAM3 runs at detect p50 451 ms against the Qwen gate's 2,150 ms. The labels are VLM
   consensus, not human truth, so this is an agreement result, not an accuracy result; 15 asks are
   disputed and unsettled.

3. Gemma 4 E4B plans Hebrew directly, with no translator, at least as well as the translator
   stacks. On command cases it scores 247/258, against Hy-MT2 -> Qwen 241/258, DictaLM -> Qwen
   252/258, and the reference-English planner ceiling 246/258. Its 11 misses are
   routed-as-emergency once, and otherwise wrong-length errors: 0-vs-1, 1-vs-0, 1-vs-2, and
   3-vs-4. None is a wrong direction or a wrong sign. On the return-trip case r_mis5 Gemma drops a
   step (3 vs 4) while both translator stacks fly the wrong sign (x=-10 vs 10).

4. Gemma 4 direct improves the verbose register where the translators lose cases. Verbose scores
   52/54 against Hy-MT2's 44/54, at a small standard-case cost (195/203 vs 197/203). Two of the
   four register cases the translators lose are fixed; r_takeoff3 and r_land4 (the "is it possible
   to..." phrasing) still return an empty plan.

5. The translator decision for the current stack: Hy-MT2-Q4 is the deployed GPU translator and
   DictaLM the CPU fallback; both feed Qwen3-VL. Hy-MT2 -> Qwen scores 348/412 and DictaLM ->
   Qwen 346/412 on the 413 set. Feeding Hebrew to Qwen3-VL directly, with no translator, drops to
   222/257, so the translator earns its place for the Qwen planner. Gemma 4 used as a translator
   is prompt-sensitive: its best recipe (v1 prompt, thinking disabled) reaches 389/412, but the
   TranslateGemma zero-shot prompt collapses to 171/412.

6. The VRAM argument for the candidate stack is the translator, not the model. Dropping the
   1,187 MiB translator and swapping Qwen for Gemma nets about 6,300 MiB derived, against 7,396
   MiB measured today. This figure is derived, not measured co-resident.

7. The latency argument favors Gemma for the VLM jobs: gate p50 1,520 ms vs Qwen 2,150 ms, and
   the SAM3 highlight chain hits 28/35 from Gemma's phrase vs 22/28 from Qwen's. Two jobs do not
   transfer. Gemma counts people 2/26 exact vs Qwen 11/26, and Gemma's own boxes are unusable for
   the highlight at box IoU median 0.02 vs Qwen 0.47, so SAM3 must draw the box from the phrase in
   either case.

## 5. Conclusions and open items

1. SAM3 is adopted as the unified detector and segmenter, replacing OmDet-Turbo + SAM2.1. SAM3 as
   a standalone presence gate is supported on this set against VLM-consensus labels, pending human
   labels on the 15 disputed asks and a human ruling.

2. The Gemma 4 E4B single-model candidate stack is supported on planning quality, verbose
   register, VLM gate latency, and the highlight chain, and shows no unsafe planning flip in the
   measured misses. By the directory's decision rule a replacement must match or beat the current
   stack on the audio, command, and vision lanes with zero unsafe flips before it reaches the live
   mic. The candidate is not cleared, because the end-to-end path is not built or measured:

   - No Hebrew router decides mission vs highlight vs question on Hebrew text; the direct-Hebrew
     bench lane skipped the 128 perception cases.
   - The number guard compares Hebrew numerals against the translation; with no translation it
     must compare against the mission JSON, which is unbuilt. The answer-mode guard is
     English-side and inert.
   - The live VLM client has no format grammar for Gemma; the bench used one.
   - Audio replay through Gemma, a live mic run, and native Hebrew answer quality are (not
     recorded).
   - The direct-Hebrew run has no same-code baseline to flip against; the per-case planning rows
     are the only safety evidence.

3. YOLO remains in the co-resident footprint at 282 MiB with no measured job in the candidate
   proposal.

4. whisper q5_k is chosen by VRAM fit and speed. Its k-quant WER/CER on real clips is (not
   recorded).

## Superseded

This document replaces the following fragment reports under `results/2026-09-08/`, which may be
deleted:

- `side-by-side.md`
- `stack-swap-evidence.md`
- `sam3-alone.md`
- `vlm-compare.md`
- `vision-sam3-chain.md`
- `planning-per-case.md`
