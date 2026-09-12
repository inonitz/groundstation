# whole-system

The offline stand-in for a production run of the Hebrew voice-drone stack. Four lanes, identical
inputs for every candidate stack, one model on the GPU at a time, nothing touches a drone.

| section | what is in it |
|---|---|
| [Objective](#objective) | the one question this test answers |
| [Lanes](#lanes) | the four measurements and what each isolates |
| [Results](#results) | the current stack and the candidates, latest run |
| [Decision rule](#decision-rule) | when a replacement stack may go to the live mic |
| [Files](#files) | what each file is |

## Objective

Decide, with measured evidence, whether a candidate stack (for example Gemma 4 E4B as a single
Hebrew planner + VLM, replacing the translator and Qwen3-VL) may replace the current stack
(whisper -> Recognizer with Hy-MT2 -> Qwen3-VL planner; Qwen3-VL VLM; SAM3 highlight), without a
phone, a drone, or a person at the microphone.

## Lanes

| lane | input | isolates | tool (its home) |
|---|---|---|---|
| 1 audio replay | recorded push-to-talk clips of a live session, whisper-cli with the node's model and flags, then the real Recognizer and planner | the language stack under real ASR output | run_list.py `--from-clips` (here) |
| 2 commands at scale | the 413-case bench; `--direct-he` feeds Hebrew to the planner with no translator | translator + planner, or planner alone | hebrew-command-bench/bench.py |
| planner ceiling | hand-written reference English straight to the planner | the planner alone | bench.py `--perfect-en [--planner gemma4]` |
| 3 vision | 17 bench images + 8 desk-camera frames, the production gate prompt and a people count, scored as agreement with SAM3 | the VLM's two production jobs | vlm_compare.py (here; images from sam3-mask-bench/candidates + the desk frames) |
| 3c SAM3 alone | the same 104 asks; SAM3's best score per ask kept at a 0.05 floor, then a presence-threshold sweep scored against presence labels, next to both VLM gates on the same labels | whether the VLM presence gate is needed at all for the highlight path | sam3_alone.py (here); labels/presence-<date>.json |
| 4 live mic | the owner speaks tools/desk-test/live-test-75.md on the webcam stack | everything, once | tools/desk-test/score_live.py |

Lane 3 has no ground truth (sam3-mask-bench/tests/README.md): it scores agreement with SAM3 and
ships a side-by-side sheet for human review. It becomes a true score once ~20 desk frames are
labelled for ~5 phrases each.

Not covered: TTS, the phone link, drone motion, free-form VLM answers.

## Results

See the dated tables below; raw logs and reports under results/<date>/.

### 2026-09-08 (first full run; the current stack = whisper q5_k + Recognizer + Hy-MT2-Q4 / DictaLM + Qwen3-VL-4B; SAM3 highlight)

Lane 2, bench 413 (commands: std 204 + verbose 54; both translators, same Recognizer code):

| stack | std | verbose | perception | ALL |
|---|---|---|---|---|
| Hy-MT2-Q4 -> Qwen3-VL (deployed) | 197/203 | 44/54 | 91/128 | 348/412 |
| DictaLM -> Qwen3-VL (CPU fallback) | 202/203 | 50/54 | 78/128 | 346/412 |
| planner ceiling: reference English -> Qwen3-VL | 201/204 | 45/54 | — | 246/258 |
| planner ceiling: reference English -> Gemma 4 E4B | 195/204 | 51/54 | — | 246/258 |
| candidate: Hebrew -> Gemma 4 E4B directly, NO translator | 195/203 | 52/54 | n/a | 247/257 |
| reference: Hebrew -> Qwen3-VL directly | 187/203 | 35/54 | n/a | 222/257 |
| Gemma 4 E4B as TRANSLATOR -> Qwen3-VL (v1 prompt, 2 shots) | 198/203 | 26/54 | 116/128 | 359/412 |
| Gemma 4 E4B as TRANSLATOR, TranslateGemma zero-shot prompt | 151/203 | 6/54 | 6/128 | 171/412 |
| Gemma 4 E4B as TRANSLATOR -> Qwen3-VL, v1 prompt + enable_thinking=false | 202/203 | 51/54 | 117/128 | 389/412 |
| harden2 END TO END: Gemma 4 alone, unified call (routing + plan + SAM3 phrase), 488 dataset | 236/253 | 59/63 | 108/138 | 415/487 |
| harden, Hy-MT2 -> Qwen3-VL, 488 dataset (same day gate) | 247/253 | 51/63 | 100/138 | 420/487 |

Lane 3, vision (26 images, agreement with SAM3; results/2026-09-08/vlm-compare.md): Qwen gate
88/104, count 11/26, IoU 0.47; Gemma gate 91/104, count 2/26, IoU 0.02; both 0/26 on the absent object.

Lane 3b, the chain that matters for the highlight (results/2026-09-08/vision-sam3-chain.md): when the object IS in the
frame (42 asks), the VLM must say present and hand SAM3 a phrase SAM3 can localize. Qwen said present 28/42 and SAM3 hit
from its phrase 22/28; Gemma said present 35/42 and SAM3 hit 28/35. VLM-box fallback usable (IoU >= 0.5): Qwen 13/28, Gemma 3/35.
Lane 3c, SAM3 alone as the gate (results/2026-09-08/sam3-alone.md; labels = the two VLM gates agreeing, NOT human truth, 89/104 asks; the 15 disputed asks are listed there for the owner to settle by eye in side-by-side.md): SAM3 alone at max score >= 0.5 matches the consensus on 82/89 (6 false presents on 61 absent asks, 1 miss on 28 present asks, desk frames 28/28); at >= 0.7, 83/89; at >= 0.8 it starts missing (6/28). The absent phrase 'boiler' got no detection at all on any of the 26 images at a 0.05 floor. SAM3 detect p50 451 ms vs the Qwen gate 2150 ms. Of the 7 asks where SAM3 @0.5 disagrees with the consensus, three are a street scene or a street-scene grid where the VLMs said no 'window'/'car' (contact sheet car 0.91, contact sheet window 0.81, street-scene-0 window 0.84) and one is a truck the VLMs called a car; the consensus is the suspect there, not SAM3. Human labels: fill labels/presence-2026-09-08.template.json and rerun `python3 sam3_alone.py --score --labels labels/presence-2026-09-08.json` (no GPU needed).
Evidence per claim for the single-model stack proposal (Gemma 4 + SAM3 + whisper), tables copied from the raw files and five strips embedded: results/2026-09-08/stack-swap-evidence.md.
Flight planning per case, all three stacks side by side, every case where any of them fails:
results/2026-09-08/planning-per-case.md (Gemma 4 direct 247/258, Hy-MT2 241/258, DictaLM 252/258; none of Gemma's
misses is a wrong direction or sign).

The pictures, embedded in ONE scrolling document: results/2026-09-08/side-by-side.md (open with the markdown preview) -> 104 three-panel strips (Qwen | Gemma 4 | SAM3 reference), grouped by image, one per prompt, with what each model said above each strip. overlays/ holds the jpgs.

Lane 1, audio replay (after the six fixes, same clips the live runs used):

| session (real clips -> whisper q5_k -> pipeline) | clips matched / unmatched | Hy-MT2 -> Qwen | DictaLM -> Qwen |
|---|---|---|---|
| Step 1 mic session (2026-09-08 00:37) vs live-test-50.md | 57 / 8 | 35 pass, 2 fail, 20 review | 34 pass, 3 fail, 20 review |
| Step 3 mic session (01:02) vs live-test-75.md v2 | 53 / 35 (v1's Set 1 is not in v2) | 18 pass, 14 fail, 21 review | 23 pass, 9 fail, 21 review |

Unmatched = clips whose heard text overlaps no list line by 0.34 (ad-hoc sentences, repeats, the v1/v2
Set-1 difference). Reports: results/2026-09-08/replay-*.md; the live runs themselves scored 38/50 and
41/69 on the SAME audio BEFORE the six fixes, so the replay is the after-fix number on identical input.

## Decision rule

A replacement stack must match or beat the current stack on lanes 1-3 with zero unsafe flips
(a wrong direction, a wrong sign, a negation that flies, a question that lands) before it gets
lane 4. Rulings are the owner's; this directory only measures.

## Files

| file | role |
|---|---|
| `run_all.sh` | sequences the lanes (`LANES=replay,bench,perfect,vision,planning,gemma`), collects reports under results/<date>/ |
| `run_list.py` | lane 1: a live-test list as text, or `--from-clips <session>` audio replay through whisper-cli; judged against the list's notation |
| `vlm_compare.py` | lane 3: both VLMs on the images, agreement with SAM3, side-by-side sheet |
| `vision_chain.py` | lane 3b: from a vlm-compare.json, does SAM3 highlight the asked object from each VLM's phrase |
| `sam3_alone.py` | lane 3c: SAM3 alone as the presence gate; `--detect` runs SAM3 once per ask (GPU, ~1 min), `--score` sweeps the threshold and scores SAM3 + both VLM gates against the labels (CPU only) |
| `labels/` | presence labels per image and phrase, with who labeled them and when; correct a label and rerun `--score` — no GPU needed |
| `planning_table.py` | flight planning per case, three stacks side by side, from the bench's newest V1-prompt raw JSON per stack |
| `overlays.py` | the pictures: per image and phrase, three panels -- Qwen's phrase + its box + SAM3 from that phrase; the same for Gemma 4; SAM3 on the asked concept as the reference. results/<date>/overlays/index.md lists them |
| `results/` | dated reports (.md/.json committed); the overlay jpgs, run logs and replay .jsonl rows are gitignored -- `python3 overlays.py results/<date>/vlm-compare.json results/<date>/overlays` regenerates the strips |
