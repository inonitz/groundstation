# Session Handoff — 2026-09-08 (live tests, guards, whole-system test, Gemma 4 probe)
Doc owner: groundstation-05 (ref 55e80f) — role: live-test agent. Model: Opus 4.8 (this session), Fable 5.1 attribution.
For messaging me: groundstation-05. Predecessor: docs/active/2026-09-07-session-handoff.md (§§1-12 there are
the campaign context and the first half of this stream; this document supersedes its §11-12 as the start point).
Written at ~20% context, before compaction, by owner instruction: "dump your whole context".

## 0. Read this first (plain summary; details in the numbered sections)
- What works: the voice chain on the webcam or the phone, mock control, with either translator. Its bench
  score is 348/412 (Hy-MT2) or 346/412 (DictaLM); both reproduce exactly across restarts.
- What changed today: nine guard/parser fixes, each gated with per-case flips (§3, §4.2). The land-trap
  question no longer lands. Highlights now work for "follow", "focus on", "emphasize".
- What the owner ruled: retests on the webcam only (§2); the V2 translator prompt is rejected (§4.2);
  whisper stays on the GPU (§4.4); the 75-list must be all-new (done, v2); the whole-system test must be
  self-contained under tools/bench/whole-system (done, §7).
- What is open: TranslateGemma placement; Gemma 4 E4B as a single Hebrew planner + VLM (it plans Hebrew
  at Qwen's perfect-English ceiling and highlights more objects, but counts badly and its boxes are
  useless); six smaller Recognizer decisions (§6).
- Where to look: tools/bench/whole-system/results/2026-09-08/ holds every table and the overlay
  pictures (overlays/index.md). The bench raw JSON is in tools/bench/hebrew-command-bench/results/.
- What to run to reproduce everything: `bash tools/bench/whole-system/run_all.sh` on an idle GPU (~20 min).
- Git: nothing committed; the block is in §9. The owner runs git.

## 1. TL;DR
Two live mic runs (2026-09-08 00:37 and 01:02) and two text runs exposed and fixed nine defects in the
Recognizer and the perception parser; every change is bench-gated with per-case flips. The current stack
(whisper q5_k -> Recognizer -> Hy-MT2-Q4 or DictaLM -> Qwen3-VL planner; SAM3 highlight) ships as gated:
bench 413 = DictaLM 346/412, Hy-MT2 348/412, reproduced exactly across a restart. Owner rulings today:
retests on the WEBCAM only; Hy-MT2 V2 prompt measured and REJECTED; TranslateGemma "use it" but where/when
still OPEN; whisper on CPU measured DEAD (5.5 s); Gemma 4 E4B probed as a single-model Hebrew planner + VLM
candidate (promising, unfinished). A whole-system offline test now exists under tools/bench/whole-system.
Nothing is committed; the owner runs git (commit block §9).

- 15:10 addition: SAM3 alone as the presence gate was measured (lane 3c); numbers in §6 item 9. The owner's
  post-judge-meetings documentation task is §16.
- 2026-09-09 05:40 addition: the whole night's work is §17; START at §18 (the open objective lives in docs/private/, gitignored).

## 2. Owner rulings this session (verbatim intent, dated 2026-09-08)
1. Retests, including any new translator prompt, run on the webcam: `VIDEO=webcam SCENE_TTS=off bash
   tools/desk-test/up.sh`. Phone + drone only for final demo footage. (The mode always existed; my runbook
   steered to the hotspot and cost ~12 hours.)
2. Apply all six post-Step-3 fixes (items 1-6 below), then also items 4 and 5 after clarification.
3. The 75-list must be ALL new sentences (v1's Set 1 came from the dataset by my misreading) -> v2.
4. "Use TranslateGemma. I did not specify when or why yet." -> placement decision OPEN (tables in §6.1).
5. Whole-system test: build it, self-contained under tools/bench; lanes as in §7.
6. Reports SHORT: answer first, one table, details in files (two long write-ups were rejected).

7. 2026-09-08 15:55: the v2 list will not be spoken live. TranslateGemma will not be used. The remaining not-done
   items of §12 are low priority. Gemma 4 must be measured as the TRANSLATOR on the 413 bench, before and after
   a prompt change (the TranslateGemma prompt as the "after" arm) — running, see §6 item 2.
8. 2026-09-08 15:55 question (open): freeze projects/integration_harden for real-drone live testing and fork
   projects/integration_harden2 on the new stack, in parallel. Agent view in NOTES (runtime switches beat a copy).

9. 2026-09-08 16:10 rulings: (a) FORK DECIDED: projects/integration_harden stays the uncluttered stack for tomorrow;
   the Gemma 4 stack goes into projects/integration_harden2 (a copy), work in parallel; copy timing = after the
   harden go-live commit (owner). (b) Emergency words הפסק/תפסיק/די: "Yes. Add it." -> DONE, gated (§3, §4.6).
   (c) Kill path: the owner rejects the phone-toggle/power-button drill as the primary kill; wants a KEYBOARD kill
   that halts everything, cancels the mission and hands manual control to the operator -> DONE as SPACE / R (§3).
   (d) TTS 503: "make sure the drone receives commands and it won't go into sleep mode" -> watch_503.sh (§3);
   whether a status poll prevents eco is UNVERIFIED. (e) Commits: integration_harden and harden2 are committed
   when finished; the tests too; the owner asked what is finished NOW (answered in §9).

10. 2026-09-08 16:20-16:30 rulings, all APPLIED: (a) the 503 watcher lives in status.sh (one-shot line + `--watch`)
    and preflight prints it; (b) manual override = the M key TOGGLE (kill / re-arm), SPACE/R removed; (c) LIVE
    DEFAULTS = Hy-MT2 + SAM3 + Qwen3-VL (§6 item 3 closed); (d) integration_harden2 is built NOW after a short
    planning round with the owner; (e) Gemma 4 grammar restriction: look for existing solutions on the web first.

11. 2026-09-08 17:10 rulings (owner), all recorded and started: harden2 = YES (copied 17:20 from the working tree,
    sessions/ excluded). Design: A router by Gemma's grammar; B keep the translator switch inside harden2; C YOLO
    off by default but switchable (grey squares = real-time segmentation demo); D whisper stays -- NOTE: measure
    Gemma 4 as the ASR on the ~125 recorded clips (background OK, "the more audio points the better"); E Hebrew
    answers straight from Gemma to the phone TTS (no back-translation any more); F = the bench/tests reach harden2
    through a home switch (clarified in chat). Missed items: (1) target approach: if harden2 flies today, "pull
    something together quickly"; (2) the 75 sentences: FILED 17:20 (dataset = 488); (3) the four register
    phrasings: HARDWIRED as stage-2 rewrites (register_imperative), gated on the 488 run; (4) Hebrew TTS = the phone,
    no VRAM (set SCENE_TTS_LANG=he in harden2); (5) VRAM fine; (6) commits: finish BOTH in parallel, the owner does
    not want to test harden himself, harden2 is the one he wants to see fly. NEW MEASUREMENT ASKED: Gemma 4 alone
    (translator + planner + thinker), with and without thinking -> bench --planner gemma4 --direct-he, arms
    gemma4-direct-nothink / gemma4-direct-think (GEMMA4_THINK=1), chained after the Hy-MT2 488 gate.

## 3. What changed in code (all uncommitted; owner runs git)
Recognizer (projects/integration_harden/recognizer/recognizer.py), each bench-gated:
- Half-turn number guard: חצי סיבוב/הקפה = 180, סיבוב וחצי = 540 on both sides; patch_number handles
  decimal tokens. Tokenizer strips ASR-glued punctuation ("חמישה...", "מטר."); clitic on חצי (שחצי) read.
- Clockwise / counterclockwise inline rules (Hy-MT2 rendered עם כיוון השעון as counter-clockwise).
- Stage-4b answer-mode guard: sentence-initial "I am / I'm / I see / I cannot / I can't", "please say",
  "my (primary) function", "as a drone/AI" -> strict retry (translate(strict=True)) then REJECT + read
  back. Narrowed after the first gate falsely hit "I can fly up five meters" / "I will fly up 20 meters
  and describe" / "I have visual contact".
- Stage-2 `explicit_one_meter`: bare מטר (no number either side) -> מטר אחד (Hy-MT2 "six meters" x2).
- recognizer/__init__.py exports _nums_en; translate() contract is (he, required_numbers=None, strict=False).
Pipeline (recognizer/pipeline.py): planner few-shot echo guard `is_shot_echo` ("Do it!" -> the 5-step
  example mission flew) -> "reject-planner-echo", read back. Translator prompt selectable:
  MVD_TRANSLATE_PROMPT=v1|v2 (v2 = REJECTED, kept selectable); translator port MVD_XLATE_PORT.
Prompts (recognizer/prompts.py): TRANSLATE_SYS_V2 / TRANSLATE_SHOTS_V2 / TRANSLATE_PROMPTS.
Perception (perception/engine.py): FIND_RE/LEAD_VERB_RE accept follow / focus on / emphasize; "stop
  following" clears. Before this, עקוב/התמקד/הדגש NEVER reached the highlight path in any live run.
Servers/scripts: recognizer/run_hymt2_server.sh -c 1024 (V2-size prompts), port env; run_dicta_server.sh
  port env; run_mvd.sh MVD_XLATE_PORT; desk-test preflight/down report "port held OUTSIDE this
  container (uid N)" (VS Code port forwarding held :18091); up.sh header documents webcam + port override.
Bench (tools/bench/hebrew-command-bench): --translator, --tag, --prompt v1|v2, --planner qwen3vl|gemma4,
  --direct-he, --perfect-en [--planner]; per-case verdicts persisted; REJECT SCORING CHANGED (reject on a
  must-not-fly = CORRECT-reject, on a command = REJECT, counted); compare_runs.py (flips); run_list.py
  (text-mode list runs, --prompt, --from-clips audio replay with overlap alignment); llama.py MODELS
  hymt2 + gemma4, GEMMA4_EXTRA.
Vision bench (tools/bench/whole-system/vlm_compare.py): Qwen3-VL vs Gemma 4 vs SAM3 reference.
ASR bench (tools/bench/hebrew_asr/cpu_latency.py): whisper CPU vs GPU on real clips.
Whole-system (tools/bench/whole-system/run_all.sh + README.md): lanes runner.
Emergency words (recognizer.py stage 0, owner ruling 2026-09-08): הפסק/הפסיקי/הפסיקו/תפסיק/תפסיקי/תפסיקו stop the
  aircraft unless they stop a perception job ("תפסיק לעקוב" = clear the highlight); די only as the whole utterance or
  its last word ("טוס די מהר" is an adverb). Gate: 0 new fires on the 413 dataset, +תפסיק +הפסק הכל on the live lists
  (intended), positives/negatives in test_recognizer.py; 42 tests green. control/commands.py imports the same regex.
Kill switch (control/kill.py + test/test_kill.py; scene_omdet keys): SPACE = wire.stop() (/c/stop = stop + relinquish
  virtual-stick authority -> the RC flies) + a latch that returns 409 for every motion verb (takeoff/land/fly_mission/
  spin_by/fly_by/gimbal/scan/go_home/follow) until R re-arms; halt stays allowed; HUD line turns red while killed.
  Wraps the wire instance, so the router's basic verbs and the pipeline's missions are both covered. Tested with a
  fake wire only; NOT yet pressed in a running session (mock run pending). Caveat: the scene window must have focus.
tools/dji_mock/watch_503.sh: SAFE GET /status/ loop that logs every HTTP-code change (finds the eco/sleep timeout).
Gemma 4 as TRANSLATOR (bench.py --translator gemma4 [--prompt tgemma]; prompts.py TGEMMA_SYS zero-shot arm).
harden2 (projects/integration_harden2, 17:20-17:30) -- the Gemma 4 single-model stack, BUILT, offline-tested, live-smoked:
  run_llama_server.sh: MVD_PLANNER=gemma4 (default) serves Gemma 4 E4B + mmproj, thinking off, port 18090; qwen3vl = old flags.
  run_mvd.sh: MVD_TRANSLATOR=none (default, no xlate window), MVD_PLANNER, SCENE_BG=off (YOLO off, switchable), SCENE_TTS_LANG=he.
  recognizer/prompts.py: UNIFIED_GRAMMAR / UNIFIED_PROMPT / UNIFIED_SHOTS -> one Gemma call returns {kind, target_en, mission}.
  recognizer/recognizer.py: recognize_direct (stage 0 emergency, stage 1 bypass, stage 2 rewrites), numbers_vs_mission guard.
  recognizer/pipeline.py: handle_direct -> mission (number guard + echo guard) | highlight/count -> vlm_query with the English
  target phrase | describe -> the Hebrew itself (Gemma answers in Hebrew) | reject -> Hebrew readback "לא הבנתי: ...".
  perception/vlm_client.py: Gemma gets the format grammar + temp 0 + "answer in the question's language"; detectors.py: SCENE_BG=off.
  tools/desk-test/*.sh + bench.py + run_list.py: MVD_HOME=integration_harden2 selects the tree (the F home switch).
  Live smoke 17:26 (real Gemma server, fake wire, 10 utterances): 10/10 routed and planned right, 316-1556 ms.
SAM3-alone gate, lane 3c (tools/bench/whole-system/sam3_alone.py + labels/): SAM3 once per ask at a 0.05 floor, threshold sweep, scored against presence labels next to both VLM gates; `--consensus` builds VLM-consensus labels (NOT truth) and a blank template for human labels; `--score` needs no GPU.
Census (tools/bench/model-cpu-or-gpu/census.py): --sam3-stack, import path fix, bash spawn.
Tests: 39 (test_recognizer +3, test_scene_wiring +3, test_perception +1); all green with the self-tests.
Desk-test: live-test-75.md v2 (all new), score_live.py (list vs session, by order).

## 4. Measurements (all raw files named; temp 0; one model on the GPU at a time)
### 4.1 Live mic runs (webcam not yet ruled then; phone stack)
- Step 1, DictaLM stack, live-test-50: 38/50. ASR 6, DictaLM answer-mode 3 (the land-trap question
  LANDED: "To land, please say Land" -> planner obeyed), router 2, תפסיק 1. Report:
  sessions/session-20260908-003702-rog/REPORT.md.
- Step 3, Hy-MT2 + SAM3 stack, live-test-75 v1: 41/69. Hy-MT2 register 6, wording 3, numbers 3, MY guard
  bugs 3, ASR 6, planner 3, router 2, emergency 2. Land trap HELD. Planner echoed its few-shot on "Do
  it!". Highlight path unreachable for Follow/Focus on/Emphasize. Report: sessions/session-20260908-010129-rog/REPORT.md.
### 4.2 Bench 413 (tools/bench/hebrew-command-bench/results/)
| run | DictaLM | Hy-MT2-Q4 | note |
|---|---|---|---|
| 2026-09-07 dicta-cw / hymt2-cw2 (old reject rule) | 339/407 | 345/410 | pre-fix |
| 2026-09-08 post2 (six fixes, new reject rule) | 346/412 | 348/412 | gate: DictaLM 5 flips all safe (l_land_going planner-LANDED -> reject); Hy-MT2 0 flips against |
| 2026-09-08 day2 rerun | 346/412 | 348/412 | 0 of 413 outputs changed on both: reproducible |
| 2026-09-08 hymt2-v2 (V2 prompt) | — | 341/412 | REJECTED: 3 unsafe flips (r_pol_spin sign, r_low sign, r_neg4 negation flies), perception -8 |
| perfect-EN control (planner alone) | 246/258 | | nine verbose losses are the PLANNER's ("a second after that", "Wait,...", "and also"); Hy-MT2 inherits them, DictaLM paraphrases them away |
Per set (post2/day2): DictaLM 7/7, 202/203, 50/54, 78/128, 9/20; Hy-MT2 7/7, 197/203, 44/54, 91/128, 9/20.
### 4.3 Text-mode 75 list (sessions/text-runs/)
v2 list (all new), V1 prompt: Hy-MT2 42 pass / 10 fail / 23 review; DictaLM 44 / 8 / 23. Hy-MT2 with V2 prompt:
42/10/23 but different lines (sign flip on 6, lost land on 11). Danger seen: DictaLM "יאללה נחת" -> "Take off".
### 4.4 VRAM and latency
- Five models co-resident (Qwen + Hy-MT2-Q4 + whisper node + YOLO + SAM3): 7,396/8,151 used, 313 free.
  SAM3-nf4 = 1,074 in-process. TranslateGemma lean 2,552 -> over by ~700.
- Whisper on CPU (cpu_latency.py, 20 real clips): 10.2 / 6.9 / 5.5 s at 4/6/8 threads vs 0.29 s GPU. DEAD.
- V2 prompt = ~516 tokens with a long input (V1 ~107): live server -c 512 -> 1024.
- Gemma 4 E4B: 3,950 MiB with vision projector; direct-Hebrew planning probe 8/10 at 351 ms; vision reads
  Hebrew and the scene but narrates a thinking preamble (needs a format grammar); 5.5 s per image ask.
  Gotchas: --image-min-tokens breaks its CLIP load; KV q4_0 + flash-attn -> empty output; setsid forks.
### 4.5 Whole-system lanes run today
Lane 2 (bench 413, commands): current Hy-MT2 -> Qwen 197/203 + 44/54; DictaLM -> Qwen 202/203 + 50/54;
Qwen perfect-EN ceiling 201/204 + 45/54; Gemma 4 perfect-EN 195/204 + 51/54; **Gemma 4 direct Hebrew
(no translator) 195/203 + 52/54 = 247/257**, at Qwen's perfect-English ceiling; Qwen direct Hebrew
187/203 + 35/54. Raw: results/2026-09-08-recognizer-{gemma4-direct,qwen-direct}.json, 2026-09-08-perfect-en{,-gemma4}.json.
Lane 3 (vision, 26 images, agreement with SAM3): Qwen gate 88/104, boiler 0/26, IoU 0.47, count 11/26,
2.2 s; Gemma 4 gate 91/104, boiler 0/26, IoU 0.02, count 2/26, 1.6 s (both need/accept the format
grammar; Qwen's outputs are identical with it). Raw: tools/bench/whole-system/results/2026-09-08/vlm-compare.{md,json}.
Lane 1 (audio replay, real clips -> whisper -> pipeline, clips matched by overlap): Step-1 session vs live-test-50: Hy-MT2 35/2/20, DictaLM 34/3/20 (57 clips matched, 8 not); Step-3 session vs 75 v2: Hy-MT2 18/14/21, DictaLM 23/9/21 (53 matched, 35 not: v1's Set 1 is gone). Reports: tools/bench/whole-system/results/2026-09-08/replay-*.md.
Lane 3b (the highlight chain: VLM says present + its phrase -> SAM3): present objects 42; Qwen said present 28, SAM3 hit
from its phrase 22; Gemma said present 35, SAM3 hit 28; box fallback usable Qwen 13/28, Gemma 3/35
(results/2026-09-08/vision-sam3-chain.md). Planning per case, three stacks side by side: results/2026-09-08/planning-per-case.md
(Gemma direct 247/258, Hy-MT2 241, DictaLM 252; Gemma's misses: אפשר ל -> [], r_higher, r_mis5 3vs4, r_mis8, r_wait1,
two EMPTY idioms flown as delays, v_start4_g3, v_mix1 -- no wrong direction or sign).
OVERLAYS (the owner's ask "I want to SEE what each VLM highlighted, its box, and how SAM3 works with it against
the ground truth"): tools/bench/whole-system/results/2026-09-08/overlays/index.md -> one three-panel jpg per image
and phrase (yellow = the VLM's own box, green = SAM3 from the VLM's phrase, magenta = SAM3 on the asked concept =
the reference; NO human ground truth exists for these images -- labelling ~20 desk frames is still open).
Rerun with full replies (2026-09-08 late): numbers identical (Qwen 88/104, IoU 0.47, count 11/26; Gemma 91/104, IoU 0.02, count 2/26; chain Qwen 28 said / 22 hits, Gemma 35 / 28); 104 overlay strips (1920x272, three panels) in results/2026-09-08/overlays/; results/2026-09-08/side-by-side.md EMBEDS all of them in one scrolling document grouped by image and prompt (open with the markdown preview).
Whole-system reports: tools/bench/whole-system/results/2026-09-08/.

### 4.6 Gemma 4 E4B as the TRANSLATOR on the 413 bench (2026-09-08 16:00-16:15, owner ask; Qwen3-VL planner)
| arm | emergency | std | verbose | perception | military | ALL | vs Hy-MT2 348 |
|---|---|---|---|---|---|---|---|
| v1 prompt, 2 shots (results/2026-09-08-recognizer-gemma4-xlate-v1.json) | 7/7 | 198/203 | 26/54 | 116/128 | 12/20 | 359/412 | +11: perception +25, verbose -18, std +1, military +3 |
| TranslateGemma instruction, zero-shot (…-gemma4-xlate-tgemma.json) | 7/7 | 151/203 | 6/54 | 6/128 | 1/20 | 171/412 | INVALID as a prompt: narrates on almost every case |
| v1 prompt, 2 shots, enable_thinking=false (…-gemma4-xlate-v1-nothink.json) | 7/7 | 202/203 | 51/54 | 117/128 | 12/20 | 389/412 | narrations 0/413; vs Hy-MT2 lost 1 / won 13; unsafe 0 |
Flips v1 vs Hy-MT2 (commands 258): LOST 27 (23 = answer-mode REJECT of a NARRATION "The user wants to translate...",
4 wrong-len), WON 10 (r_takeoff2, r_takeoff3, r_land4, r_alt10 = the Hy-MT2 register losses; combo4; verbose
missing-z/y x3; v_mix1/2). 57 of 413 Gemma outputs narrate under the one-line grammar even with 2 shots and
--reasoning-budget 0. ONE UNSAFE FLIP: r_neg4 "בלי להסתובב בבקשה" narrated -> the planner flew a spin (1 vs 0).
Latency: std p50 300 ms (Hy-MT2 130-190), verbose p50 2,216 ms (Hy-MT2 ~670) — the narration is the cost.
Reading: Gemma fixes the register problem and the perception phrasing; its own failure mode is narration, which
a stricter grammar (forbid the "The user" opening) or the strict retry would remove. Not ruled.
FIX FOUND + VERIFIED 2026-09-08 16:30 (owner: "see what you can find on the web"): llama.cpp users hit the same thing;
`--reasoning-budget 0` and `--reasoning-format none` are ignored by Gemma 4, `--reasoning off` (build b8738+) or
`--jinja --chat-template-kwargs '{"enable_thinking":false}'` work (github.com/ggml-org/llama.cpp/discussions/21338;
unsloth.ai/docs/models/gemma-4). Smoke on our server (Vulkan, E4B Q4_K_XL): the 12 narrating cases -> 0/12 narrate,
120-700 ms each. GEMMA4_EXTRA now carries the flag (llama.py); full 413 rerun tagged gemma4-xlate-v1-nothink = 389/412 (table row above); lost vs Hy-MT2: ['v_ready3_g2']; won: ['combo4', 'r_takeoff2', 'r_takeoff3', 'r_land4', 'r_alt10', 'v_start4_g3', 'v_first3_g0', 'v_first3_g1', 'v_first3_g2', 'v_seq5_g0', 'v_note3_g3', 'v_mix1', 'v_mix2']; unsafe: [].

### 4.7 The 17:20 chain (dataset = 488 after filing the 75; register rewrites in): Hy-MT2 gate + Gemma 4 ALONE
| run | emergency | std | verbose | perception | military | ALL |
|---|---|---|---|---|---|---|
| Hy-MT2 -> Qwen, 488 gate (results/2026-09-08-recognizer-hymt2-488-gate.json) | 12/12 | 247/253 | 51/63 | 100/138 | 10/21 | 420/487 |
| Gemma 4 ALONE, direct Hebrew, thinking OFF (…-gemma4-direct-nothink.json) | 12/12 | 245/253 | 61/63 | n/a | n/a | 318/328 commands |
| Gemma 4 ALONE, direct Hebrew, thinking ON (…-gemma4-direct-think.json) | 12/12 | 242/253 | 60/63 | n/a | n/a | 314/328 commands |
Gate: on the 413 common cases the register rewrites LOST 0 and WON 4 (r_takeoff2/3, r_land4, r_alt10). New 75 on
Hy-MT2: std 37/50 (9 of the 13 non-passes are open-ended "valid(open)" cases counted ok by the bench), verbose 7/9.
Gemma alone vs the deployed stack on the same 328 commands: 318 vs 310; verbose 61/63 vs 51/63. Thinking ON loses 4
(r_wait1, l75_turn270 180vs270, l75_up4_photo, v_mix1), wins 0 -> thinking OFF is the setting. Gemma-alone misses
(OFF): r_higher, r_mis5, r_mis8, r_wait4 (routed emergency, all stacks), l_postpone/l_pause_idiom (EMPTY -> a delay
flown, no motion), l75_turn540 (180 vs 540), l75_turn_back (fly_by vs spin_by), l75_photo_then_back2, v_start4_g3,
l75_v_climb_then_count. Latency OFF: std p50 158 ms, verbose p50 558 ms. Perception for Gemma alone is still n/a in
the bench: it needs the target_en scoring (harden2 grammar, built 17:30, see §3).

### 4.8 harden2 END TO END on the bench (18:05, tools/bench/hebrew-command-bench/unified_bench.py, MVD_HOME=integration_harden2)
Gemma 4 alone through the unified call {kind, target_en, mission} on every set: emergency 12/12, std 236/253,
verbose 59/63, perception 108/138 (keyword groups on "<kind words> the <target_en>"), military 0/21 (not
comparable: that set scores a translation) = 415/487 vs harden's Hy-MT2 -> Qwen 420/487; without military 415/466 vs 410/466.
Commands 295/316 vs 298/316; the routing prompt costs 9 std cases against Gemma's planner-only lane. p50 475 ms per
utterance for routing + planning + the SAM3 phrase (harden: translator + planner + English routing). Raw:
results/2026-09-08-unified-gemma4.{json,md}. First run inverted the perception scorer; re-scored offline.

### 4.9 LIVE end-to-end, harden2 on the C920 webcam + mock (20:00-20:25; projects/integration_harden2/sessions/session-20260908-170015-rog/REPORT.md)
62 utterances vs tools/desk-test/live-test-e2e-50.md (50 lines sampled uniformly from the 488 dataset): PASS 42, FAIL 17,
REVIEW 1, unmatched 2. FAIL causes: 8 ASR/speaker (7 safely rejected or retried), 4 by ruling/known (greedy עצור; 3
military idioms -> reject), 4 planner (extra 0-degree spin; a DOUBLE NEGATION flew 2 spins once = the one unsafe event;
one dz->dy axis; return-trip sign), 1 routing (ASR "?" on a possibility phrasing -> reject). Perception routing 14/14,
gate absent on 12 desk-less scenes, one false present with a zero box (line 34). Peak VRAM ~6.5 GiB (owner). Fixes
applied in harden2 the same night (NOTES 20:30): no Gemma-box fallback, degenerate box = absent, relational clauses
dropped for SAM3, 8-second give-up on a highlight SAM3 never finds, double-negation reject shot. 49 tests green.

## 5. Standing gotchas added today
- `pkill/pgrep -f <pattern>` from inside a bash chain whose text contains the pattern kills the chain.
- `setsid llama-server` forks: the saved PID is the parent; stop via `ss -tlnpH 'sport = :PORT'`.
- A port can be held OUTSIDE the container (VS Code forwarding): preflight/down now say so.
- The auto-mode classifier blocks `rm` of manifests and dataset downloads (Step 5 whisper quants is the
  owner's to run; command in the campaign report §8).
- Gemma 4 on llama-server: see §4.4.
- The webcam: index 0 is the laptop lid camera (black, lid shut). The desk camera (Logitech C920) is host video2; the
  container lacks its /dev node unless created (mknod c 81 2/3) or passed at container start. Use WEBCAM_DEV=2.

- No Read tool exists in this session tree, nor in its subagents: nobody here can view an image. Presence labels
  by eye are owner-only work. Contact sheets are useless to the agent; do not spend a subagent on it again.

## 6. Open owner decisions (nothing settled)
1. CLOSED 2026-09-08 15:55, owner: "We wont use it." TranslateGemma is dropped. (History: placement options measured — drop YOLO (282) + tgemma Q3 (~500, quality
   unmeasured) = borderline; tgemma on CPU (0.6 s cmd / 1.6 s perception); the 16 GB desktop.
   Whisper-to-CPU is dead. Tables: §6.1 of the 2026-09-07 campaign doc + this §4.4.
2. Gemma 4 E4B as the single Hebrew planner + VLM (drop the translator): lanes 2-3 results in §4.5; as the TRANSLATOR: §4.6 (359/412 with one unsafe narration flip). Lives in integration_harden2 once forked (ruling 9a). Owner proposal (2026-09-08 15:40): whisper q5_k + Gemma 4 E4B Q4 + SAM3 + YOLO replaces the whole stack. Evidence per claim, with verdicts: tools/bench/whole-system/results/2026-09-08/stack-swap-evidence.md (supported: planning 247/258 with no wrong direction/sign, highlight chain 28/42 vs 22/42, faster vision asks, Q4 file; not supported: counts 2/26, own boxes IoU 0.02, no Hebrew router, no audio/live run; VRAM saving is the translator only, about 6,300 derived).
3. CLOSED 2026-09-08 16:20, owner: live defaults are Hy-MT2 + SAM3 + Qwen3-VL (flipped in run_mvd.sh, scene_omdet.py, preflight.sh, up.sh; omdet / dicta stay as switches for the old pair).
4. Hy-MT2 register: the V2 prompt is rejected; untested V3 = V1 + rule 1 + new shots only.
5. Planner prompt: time fillers/preambles are not actions; one action per clause (9 verbose cases).
6. Emergency words די / הפסק / תפסיק; router rule for count/presence questions (48, 49) and תצפית/דווח;
   wire check_colors + add סגול; "turn back N meters" EN rule; סיבוב שלם = 360 idiom.
7. Delete perception/ and rename perception2 after the SAM3 swap is confirmed live.
8. Step 5 whisper k-quant WER/CER (owner runs; classifier-blocked for the agent).
9. SAM3 as a standalone tool without the VLM presence gate (owner idea, 2026-09-08 end; MEASURED 2026-09-08 15:10 as lane 3c, tools/bench/whole-system/sam3_alone.py, results/2026-09-08/sam3-alone.md). Against the consensus of the two VLM gates (NOT human truth; 89/104 asks, 15 disputed omitted): SAM3 alone at max score >= 0.5 scores 82/89 (6 false presents / 61 absent asks, 1 miss / 28 present asks, desk frames 28/28); >= 0.7 gives 83/89; >= 0.8 misses 6/28. 'boiler' got zero detections on all 26 images even at a 0.05 floor. SAM3 alone costs 451 ms p50 vs the Qwen gate 2150 ms, so the highlight path would save about 2 s per request. Of the 7 disagreements at 0.5, at least 4 look like consensus errors (windows and cars in street scenes the VLMs called absent; a truck the VLMs called a car). No human labels exist, and no agent in this session can view images (Read tool absent, see §5): the owner settles 22 asks by eye in side-by-side.md (the list is in sam3-alone.md), or fills labels/presence-2026-09-08.template.json and reruns `python3 sam3_alone.py --score`. OPEN: whether the highlight path goes phrase -> SAM3 directly, and at 0.5 or 0.7; the VLM stays for questions, counts and descriptions either way.

## 7. The whole-system test (tools/bench/whole-system/README.md) — method
Lanes: 1 audio replay (real clips -> whisper-cli -> Recognizer -> planner, scored vs the list; clips
matched to lines by token overlap), 2 bench 413 (+ --direct-he), planner ceiling (--perfect-en), 3 vision
(vlm_compare.py: gate agreement with SAM3, boiler false-present, box IoU, people count, format, latency,
VRAM; side-by-side sheet), 4 live mic on the webcam. Decision rule: match or beat on 1-3 with zero unsafe
flips before lane 4. Not covered: TTS, phone link, drone motion, free-form answers.

## 8. Documents touched today (audit list; see §10 for the cross-check)
docs/NOTES.md (many entries), docs/active/2026-09-07-session-handoff.md (§11.4b-h, §12, START HERE),
docs/active/2026-09-07-vram-perception-campaign-results.md (§4, §8), tools/bench/hebrew-command-bench/
README.md (scorecard at 413 + control), results/HISTORY.md, tools/bench/model-cpu-or-gpu/README.md
(co-resident + whisper CPU), tools/bench/whole-system/README.md, projects/integration_harden/perception2/
README.md, projects/integration_harden/sessions/*/REPORT.md (2), sessions/text-runs/*.md (6),
tools/desk-test/live-test-75.md (v2), memory: owner-wants-short-reports, retests-on-webcam,
auto-mode-classifier-blocks-rm-and-downloads.

## 9. Git — nothing committed (owner runs all)
```
cd /root/groundstation
git add projects/integration_harden/recognizer projects/integration_harden/perception/engine.py \
        projects/integration_harden/perception2 projects/integration_harden/scene_omdet.py projects/integration_harden/run_mvd.sh \
        projects/integration_harden/test tools/bench/hebrew-command-bench tools/bench/whole-system/vlm_compare.py \
        tools/bench/hebrew_asr/cpu_latency.py tools/bench/whole-system tools/bench/model-cpu-or-gpu \
        projects/integration_harden/control/kill.py projects/integration_harden/test/test_kill.py tools/dji_mock/watch_503.sh \
        tools/desk-test tools/devenv docs/active/2026-09-07-session-handoff.md docs/active/2026-09-08-session-handoff.md \
        docs/active/2026-09-07-vram-perception-campaign-results.md docs/NOTES.md
git commit -m "fix(recognizer)+bench: guards from two live runs, whole-system offline test, Gemma 4 lanes, SAM3-alone gate lane

answer-mode guard (strict retry then reject; the land trap LANDED on DictaLM), planner few-shot echo guard, half-turn 180/540 idioms, tokenizer (ASR punctuation, shin clitic), bare-metre rewrite, clockwise inline rules | highlight parser gains follow/focus on/emphasize (path was unreachable) | bench: --translator/--tag/--prompt/--planner/--direct-he/--perfect-en, per-case verdicts, reject scoring, compare_runs flips, run_list text + audio replay | vlm_compare (Qwen3-VL vs Gemma 4 vs SAM3), whisper cpu_latency (dead: 5.5 s), census --sam3-stack (7,396/8,151) | whole-system runner + README | live-test-75 v2 all-new, score_live | V2 translator prompt measured+rejected, selectable | port override + outside-holder diagnosis | gates: DictaLM 339->346, Hy-MT2 345->348, 0 unsafe flips | emergency words הפסק/תפסיק/די gated (0 new fires on 413) | operator kill switch SPACE/R (stop + RC control + latch), fake-wire tested | Gemma 4 translator arm 359/412 (+25 perception, -18 verbose, 57 narrations, 1 unsafe) | 503 watcher

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

## 10. Objective / compass (unchanged from the 2026-09-07 handoff §8)
The demo is the compass: talk to the drone in Hebrew, show perception, show it approaching a target.
The interview-sprint decision (memory: current-demo-decision) still holds; the drone-safety rules in
CLAUDE.md are absolute. The owner runs every boot and every git write; the agent runs down.sh only when told.

## 11. Standing rules for the next agent (read CLAUDE.md in full; then 2026-09-07 handoff §10)
- Drone safety: never send arm/takeoff/land/stick commands to a real aircraft; mock 127.0.0.1 only.
- Owner protocol: address multi-point messages by number; rulings into repo docs the same turn;
  recommendations are not decisions; concrete commands with absolute paths; SHORT reports (§2.6).
- Lanes: manager = groundstation-15 (earlier groundstation-3c); depth / llm_to_action = groundstation-13;
  projects/integration/ is FROZEN. Message the manager only when the owner says so.
- Measurement invariants: temp 0, one model on the GPU, flips against a same-code baseline, duration
  estimate before every GPU run, full tables in chat only when asked (otherwise files).
- Retests on the webcam (§2.1). RTK wrappers + heredoc edits (the Read/Edit tools are denied here).

## 12. Not done / not tested (honest list)
- The v2 75-list will NOT be spoken live (owner ruling 2026-09-08 15:55: "I dont see a point").
- The 75 v2 sentences are NOT yet filed into the bench dataset. Owner 15:55: this was instructed earlier, by the
  set in each line's `file:` field; the agent (this one, before compaction, not a subagent) deferred it as an owner
  ruling by mistake. Filing = 50 commands std, 10 perception, 9 verbose, 5 emergency, 1 military; needs a reference
  English per case and a bench rerun afterwards (numbers become 488-case, not comparable to 413).
- TranslateGemma placement (owner: "use it", where/when unsaid). Whisper-to-CPU is dead (§4.4).
- Gemma 4 E4B end to end: only lanes 2-3 measured; no audio replay, no live run, no format grammar in
  vlm_client, no VLM counting fix; its audio input (E4B) untested as a whisper replacement.
- Hy-MT2 V3 prompt (V1 + rule 1 + new shots) untested. Planner-prompt fix for fillers untested.
- Emergency words די/הפסק/תפסיק; router rules for count/presence questions and תצפית/דווח; colour guard
  (check_colors dead, no סגול); "turn back N meters" and סיבוב שלם=360 rules; DictaLM "יאללה נחת"->"Take off".
- Step 5 whisper k-quant WER/CER (owner runs). Phone TTS 503 gate (2026-09-05 §18). perception/ deletion.
- docs/ARCHITECTURE.md (manager-owned) does not yet show stage 4b, the planner echo guard, SCENE_SEG /
  MVD_TRANSLATOR switches, or the whole-system test -- flag to the manager, do not edit it from this lane.
- Vision ground truth: ~20 desk frames x 5 phrases still unlabelled (15 min of the owner's time).

- The keyboard hook (C++, owner's) logs every raw input event incl. mouse moves: keys.log grew 1.1 MB in 2 min; a debug flag off is owed.
- Scoring a live session after compaction: `python3 tools/desk-test/score_session.py <list.md> <session dir>` (writes REPORT.md).
- Lane 3c (SAM3 alone as the gate) has no human labels. 22 asks are unsettled: 15 where the two VLMs disagree and 7 where
  SAM3 @0.5 disagrees with their consensus. The list is in results/2026-09-08/sam3-alone.md; the strips are in side-by-side.md.
  The owner settles them by eye or fills labels/presence-2026-09-08.template.json, then reruns `python3 sam3_alone.py --score`.

- harden2 (17:30): built, 48 tests green, live smoke 10/10 on the unified Gemma call -- but NO webcam boot yet (owner
  boots: `MVD_HOME=integration_harden2 VIDEO=webcam SCENE_TTS=off bash tools/desk-test/up.sh`), no audio replay,
  no perception score in the bench for the direct path (needs a target_en scorer: the keyword groups of
  cases_perception applied to Gemma's target_en), M key never pressed in a session, phone TTS in Hebrew unverified.
- Gemma 4 as ASR (owner note D): running 17:33 in the background over the 153 recorded clips through llama-mtmd-cli
  (tools/bench/hebrew_asr/gemma_asr.py -> bench_out/gemma-asr-2026-09-08.md, gitignored). The CLI narrates its
  thinking unless a grammar restricts the output (the CLI lacks the enable_thinking switch), so a Hebrew-only GBNF
  grammar is used. DONE 17:45: Gemma CER 35.8 % / WER 71.8 % vs whisper CER 8.4 % / WER 10.3 % on 107 matched clips; head-to-head Gemma better on 1, whisper on 96. Whisper stays (ruling D holds). Table in tools/bench/hebrew_asr/README.md.

## 13. Key paths + resume checklist
- App: projects/integration_harden/{scene_omdet.py, run_mvd.sh, config.py, recognizer/, perception/, perception2/}
- Bench: tools/bench/hebrew-command-bench/{bench.py, run_list.py, compare_runs.py, results/}; vision:
  tools/bench/whole-system/vlm_compare.py; whole-system: tools/bench/whole-system/{run_all.sh, README.md, sam3_alone.py, labels/, results/}
- Sessions (gitignored): projects/integration_harden/sessions/session-2026090{8-003702,8-010129}-rog/ (REPORT.md,
  clips/), sessions/text-runs/. Run logs: /tmp/desk-test/latest/. Scratch: the session scratchpad (ephemeral).
- Resume: (1) `python3 -m pytest projects/integration_harden/test -q` + the three self-tests + `bench.py --audit`;
  (2) `bash tools/bench/whole-system/run_all.sh` (~15 min, GPU idle) reproduces every table here;
  (3) boot: `VIDEO=webcam SCENE_TTS=off [SCENE_SEG=sam3 MVD_TRANSLATOR=hymt2] bash tools/desk-test/up.sh`.

## 14. Skimmed / not-fully-addressed talking points (so nothing is lost)
- Gemma 4 E4B accepts audio input: could replace whisper too (single model for ASR+planning+vision);
  unmeasured, llama-server audio support unknown.
- The bench's "perception" scoring is English-keyword based; a direct-Hebrew stack has no perception
  score yet (lane 3 covers the VLM half only). A Hebrew-keyword scorer would close that.
- The owner questioned whether dataset sentences like "ימינה שני מטרים" (no verb) are natural Hebrew.
- The owner noted "apples to oranges" when list v1 and v2 were compared; the bench is the constant yardstick.
- SAM3 per-frame duty on the GPU (rate-limited to 1/s) is unmeasured under a live VLM ask.

## 15. Cross-check of every touched document (filled at the end of the session)
Method: a scripted grep for the key fact in every document (see the session's presence check), then the
gaps closed by hand. "owner-ruled" facts appear in docs/NOTES.md the same turn they were ruled.

| document | carries | verified |
|---|---|---|
| docs/NOTES.md | every ruling, gate, census, gotcha and result of 2026-09-07/08 (one bullet each; the primary record) | grep, all present |
| docs/active/2026-09-07-session-handoff.md | campaign context; §11 (first half of this stream), §12, START HERE pointer to THIS doc | yes |
| docs/active/2026-09-08-session-handoff.md | this dump | — |
| docs/active/2026-09-07-vram-perception-campaign-results.md | §4 measured fit table + all-five confirmation; §8 remaining-work status table | yes |
| tools/bench/hebrew-command-bench/README.md | scorecard at 413 (both translators, new reject rule), perfect-EN control, usage of every new flag and run_list (text + audio replay), files table | yes |
| tools/bench/hebrew-command-bench/results/HISTORY.md | the 388-case and the 2026-09-07-late scorecards, superseded | yes |
| tools/bench/sam3-mask-bench/README.md | VLM comparison section + table | yes |
| tools/bench/hebrew_asr/README.md | whisper-on-CPU section | yes |
| tools/bench/model-cpu-or-gpu/README.md | five-model co-resident table; whisper CPU line | yes |
| tools/bench/whole-system/README.md | the method, lanes, decision rule, 2026-09-08 results (replay row filled last; lane 3c SAM3-alone added 15:10) | yes |
| projects/integration_harden/README.md | runtime switches table (SCENE_SEG, SAM3 period, MVD_TRANSLATOR, MVD_XLATE_PORT, MVD_TRANSLATE_PROMPT, VIDEO), xlate window | yes |
| projects/integration_harden/recognizer/README.md | run_hymt2_server.sh row; the 2026-09-08 guards; translate() contract | yes |
| projects/integration_harden/recognizer/PROMPTS.md | regenerated; V2 note | yes |
| projects/integration_harden/perception2/README.md | "Wired into scene_omdet" section (SCENE_SEG, phrase_concepts, rate limit, owner decision) | yes |
| projects/integration_harden/sessions/*/REPORT.md (2) + sessions/text-runs/*.md (7) | live and text-run tables (gitignored; summaries live in NOTES) | yes |
| tools/desk-test/live-test-75.md | v2 header: all-new, webcam boot line, filing counts | yes |
| tools/desk-test/up.sh header | webcam retest default, next stack line, port override | yes |
| memory (outside the repo) | owner-wants-short-reports, retests-on-webcam, auto-mode-classifier-blocks-rm-and-downloads (+ MEMORY.md index) | yes |
| NOT mine to edit | docs/ARCHITECTURE.md (manager); docs/active/2026-09-06-* (other lanes) -- flagged in §12 | — |
Gaps found by the check and closed the same pass: bench README usage (from-clips, direct-he, planner,
prompt), sam3-mask-bench README (vlm_compare), hebrew_asr README (cpu_latency), app README (runtime
switches), recognizer README (guards, hymt2 server), PROMPTS.md (V2), the 2026-09-07 handoff pointer.

## 16. After the judge meetings: consolidate the repo documentation (owner instruction, 2026-09-08 15:00)

- Timing: after the judge meetings, not before. Nothing to do on this before then.
- The owner and the agent go through every document in the repo one by one, together.
- Output 1: a map of the documents. What connects to what. What is stale. What is current and relevant.
- Output 2: 2-3 cohesive documents that describe everything in this repo. They replace the current sprawl.
- docs/NOTES.md is exempt. It stays the dumping ground for information.
- The new documents aggregate the performance metrics over the whole history.
- For every measurement they state what was measured, why it was measured, and the design consideration behind it.
- They also record the other technical decisions and their reasons.
- Related: docs/ARCHITECTURE.md is manager-owned (§12); the consolidation must include it or replace it with the manager's agreement.
- Also ruled 2026-09-09 00:45, same day: one root data folder (`runs/`-style) for every log, trace, session recording,
  overlay and replay row, gitignored as one line; the scripts write there; committed evidence stays next to each bench.

## 17. 2026-09-09, 00:30-05:40 (after §16) — everything done in the night, in order (context sweep before compaction)
Code (harden2 unless stated; all tests green: harden 44, harden2 50):
- SAM3 COUNTING (owner ruling): kind=count -> "count the <target>" -> TextHandler._handle_count -> SAM3 alone @0.5 on
  phrase_concepts(target), objects stay highlighted, chat "ספרתי N", TTS "יש N"/"לא מצאתי". parse_count in perception/engine.py,
  exported from perception/__init__.py. Not exercised live yet (block A of the run sheet does it).
- Highlight fixes after the live e2e (§4.9): Gemma's VLM box never drawn (IoU 0.02), degenerate gate box = absent, phrase_concepts
  cuts relational clauses (_REL in harden2 perception2/concept.py), SCENE_HL_GIVEUP=8 s drops a target SAM3 never finds, the
  double negation that flew is a reject shot in UNIFIED_SHOTS (a RULE is still owed).
- unified_bench.py (hebrew-command-bench): Gemma alone on all 488 sets; first run inverted score_perception (it returns the MISSED
  groups), re-scored offline: 415/487 (§4.8). MVD_HOME=integration_harden2 selects the tree for bench/run_list/desk-test.
- Webcam: index 0 = the laptop lid camera (black when shut); the desk camera is a Logitech C920 = host video2/3; the container
  lacks hot-plugged /dev/video nodes -> up.sh + preflight now mknod them from /sys/class/video4linux; WEBCAM_DEV=<n> in both
  run_mvd.sh; index cameras open in MJPG (C920 720p: 10 -> 30 fps); tools/desk-test/list_cams.py lists cameras (preflight with
  VIDEO=webcam, status.sh). Boot: MVD_HOME=integration_harden2 VIDEO=webcam WEBCAM_DEV=2 SCENE_TTS=off bash tools/desk-test/up.sh
- Kill switch is the M key TOGGLE (SPACE/R removed). status.sh --watch streams the phone gate; preflight prints it.
Measurements (raw under tools/bench/*/results and tools/bench/hebrew_asr/bench_out):
- Gemma 4 as ASR: CER 35.8 % vs whisper q5_k 8.4 % on 107 matched clips -> whisper stays (ruling D confirmed).
- Gemma 4 translator: 359 (thinking on) -> 389/412 with --jinja --chat-template-kwargs '{"enable_thinking":false}'
  (llama.cpp discussion 21338); Gemma alone direct commands 318/328 off vs 314 on; Hy-MT2 488 gate 420/487, register rewrites 0 lost.
- Live e2e 62 utterances: 42/17/1 unsafe (§4.9). Peak VRAM 6.5 GiB (owner-observed).
Diagrams / slides (docs/active/assets/):
- House recipe (from the llm_to_action lane, adopted): graphviz DOT, rankdir TB + rank=same rows, dpi 192, semantic fills, aspect
  1.4-1.9; PNG via `dot -Tpng`; SVG via `dot -Tsvg:cairo` (glyphs outlined, 0 <text>, no font substitution — the earlier SVG
  "mess"); editable draw.io via tools/diagrams/dot2drawio.py (keeps the dot layout). mermaid.ink was dropped: Hebrew, "&" and
  `direction` lines make it 404, and draw.io imports neither DOT nor editable SVG.
- Files: harden2-{simplified,language,perception,detailed}.{dot,png,svg,drawio}; harden2-simplified-demoday.drawio/.png (the owner's
  demo-day diagram + only the harden2 delta, blue); dji-apiserver-{simplified,detailed}.* + docs/active/2026-09-09-dji-apiserver-
  architecture.md (route table with file:line) made by a HEADLESS claude run (binary:
  /root/.vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude -p ... --permission-mode acceptEdits
  --allowedTools ...) because the Agent tool streamed into the owner's view ("cluttering the conversation") — use headless for any
  long subagent job; it corrected 4 facts: /input is the PHONE posting to us; video = TCP :5600 with the phone as server; recognizer
  = Google SpeechRecognizer (Vosk dead); /c/ws/sticks has no keepalive. llm_to_action diagrams are the llm_to_action lane's
  (llm_to_action-system-dataflow / control-loop .dot/.png/.svg); my fmu-readme-dataflow.* is a fallback only.
- Slide content files: slide-scope.{md,png}, slide-scope-notes.{md,png} (form lines verbatim, grouped Delivered/WIP/Deferred, notes
  per line), slide-numbers.{md,png} (grouped Met/Partly/Not met/Not measured), slide-method.{md,png}, slides-research.md +
  slide-r1..r7.png (datasets, ASR, translator campaign, guards, one model, vision, end to end — the real tables + decision chain).
  Deck ruling: 5-6 slides, dry, Hebrew; no "ask" slide; the video (harden2 flight) or the live webcam demo, not a slide.
- The judge diagrams doc (docs/active/2026-09-06-architecture-diagrams.md) §3/5/6/7 refreshed + §3b harden2 at the manager's
  request; blocks 14-17 (FMU lane) were failing on mermaid.ink, 15-17 render now, 14 (the 20 Hz tick) still fails; the manager does
  the consistency pass on §1.
Repo hygiene: .gitignore now covers *.done, whole-system overlays/logs/jsonl, hebrew_asr/bench_out, integration_harden*/traces,
  integration_harden2/sessions, docs/private/ (judge/competitor/team material, NEVER committed; the judge is never named anywhere,
  including memory). Diff went 326 -> 197 files. The `runs/` root data folder is ruled for the day after the judges.
Host (laptop, outside the container — for the owner, not the agent): the NVIDIA card idled at 25 W / 35 % SM because X (Xfce
  4.18, X11) keeps a "Sink Output" screen for the NVIDIA-wired ports and both external monitors hang on those ports (DP-1-0 via
  USB-C, HDMI-1-0): reverse-PRIME copies every frame. Mitigations tried: btop closed, Zen moved to the AMD render node
  (`flatpak override --user --env=MOZ_DRM_DEVICE=/dev/dri/renderD129`), 300 -> 120 Hz (35 -> 25 %). NOT to run while monitors
  are on the NVIDIA: `xrandr --setprovideroutputsource NVIDIA-G0 0x0` (blacks them out; relink with 0x56). The AutoAddGPU-off
  file was rejected as unsustainable. autorandr / Xfce display profiles for the layout. harden2 fits with the monitors (6.5 GiB).
Rulings recorded tonight (owner): the 75 v2 list will not be spoken live; TranslateGemma dropped; live defaults Hy-MT2 + SAM3 +
  Qwen3-VL; harden2 fork; A-F design rulings (Gemma routes, translator switch kept, YOLO off but switchable, whisper stays, Hebrew
  TTS on the phone, home switch); counting = SAM3; 5-hour plan for the morning; the team summary PDF objective (docs/private/).

## 18. WHERE TO LOOK NEXT (read in this order after compaction)
0. docs/active/2026-09-09-project-state-and-reorientation.md -- the full high+low state after the meeting was cancelled; the challenge-form scorecard with WHY, and the ranked backlog. START HERE.
1. docs/private/2026-09-09-team-summary-objective.md — the OPEN objective: the Hebrew team summary PDF with all twelve competitor
   claims validated (two sources each), strong/weak/slice; includes the judge profile (unnamed), the owner's draft, the rulings,
   the Gemma claims table, our numbers, the Pillow PDF recipe. STATUS 2026-09-11: DONE (judges cancelled); the team summary + PDF exist in docs/private/. The live entry point is now point 0 (reorientation doc) section 8.
2. tools/desk-test/checklist-2026-09-09.md — the morning's tick list; tools/desk-test/live-run-2026-09-09.md — blocks A/B/C.
3. This document §4.6-4.9 and §17 for numbers; docs/active/assets/ for every slide file; docs/NOTES.md tail (2026-09-08/09 entries).
4. Owner protocol reminders that bit tonight: address every numbered point; no long monologues ("yappage"); no tables when the
   owner asked for lists; think before restating the owner's own text; subagents must not stream into the chat (use the headless
   binary); never document judge material in the repo or memory.

## 19. Morning of 2026-09-09 (after compaction; 05:42-06:10)
- Team summary document: DONE by a headless agent (docs/private/team-summary-2026-09-09.{md,pdf}, competitors-validation.md,
  team-summary-STATUS.md). Owner checks the PDF by eye (RTL direction, tables). Key findings in docs/NOTES.md 06:00 entry.
- Block A (webcam + mock) 05:50-05:57: session projects/integration_harden2/sessions/session-20260909-025023-rog, logs
  /tmp/desk-test/20260909-025016/. 7/7 routed right; kill + re-arm proven on the mock. One bug fixed: unstable counting
  (2/5/4/6) -> perception2/counting.py + median of 3 frames; _say prints; 409 refusals named in the session log. 21 tests pass.
- tools/desk-test/score_session.py needs a list in the "N. sentence -> verb dx=.." notation; the run-sheet lines are prose,
  so block A was judged from app.log + mock_commands.log by hand (the scorer's FAIL count on the run sheet is noise).
- Next: block B (phone video + mock + Hebrew TTS) 06:30, block C (real control, human only) 06:50-07:30, commit 07:45.
- Block B 06:20-06:35: phone video + mock + TTS worked (mark, count, speak). Vision misses traced to Gemma's English
  target WORD (מגירות -> "cabin"), weak SAM3 nouns ("screens"), positional words ("top left window") and one gate "absent".
  Fixes: perception2/lexicon.py (HE->EN nouns under Gemma), SAM3 synonyms, positional strip, SCENE_GATE=vlm|either|sam3
  (default vlm, ruling OPEN). 60 tests pass. Details: docs/NOTES.md 06:40 entries.
- 07:28-07:45 block C, the FIRST REAL harden2 flight: two blockers first (run_mvd.sh unbound MVD_SESSION_DIR under set -u;
  the phone's hotspot IP changed to 10.160.188.132, the old hardcoded IP made every POST time out while airborne), then
  6 missions flew with HTTP 200 (session-20260909-042949-rog). Rulings: SCENE_GATE default = sam3 ("Gemma plans, SAM3
  sees"; describe stays on Gemma), SCENE_MIN_BOX_FRAC=0.001 speck floor. Planner gap: "square" is phrasing-dependent ->
  UNIFIED_SHOTS example + 488 rerun after the judges; never say ריבוע in the demo. 61 tests pass. NOTES 07:28-07:45.
