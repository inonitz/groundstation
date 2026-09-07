# Session Handoff — 2026-09-07 (VRAM + Translator Campaign)
Doc owner: groundstation-05 (ref 55e80f) — role: live-test agent. Model: Opus 4.8.
For messaging me: refer to me as groundstation-05 / ref 55e80f. This doc dumps the full session so the
next agent bootstraps fast. Primary reports: docs/active/2026-09-07-vram-perception-campaign-results.md
(compact scorecard) and docs/active/2026-09-07-translator-bench.html (visual). Raw log: docs/stale/2026-09-07-campaign-rawlog.md.

## 1. TL;DR
This session ran the translator/VRAM campaign to pick the Hebrew→English translator for the drone voice
loop and confirm the 8 GB card fits. OUTCOME: **deploy single-model Hy-MT2 (Q4 preferred), and SAM3 is a
hard prerequisite** to put any translator on the GPU. The campaign is done; what's left is engineering
(SAM3 integration + Hy-MT2 wiring) and the LIVE TEST for the demo video. Next agent = general, with the
LIVE TEST as the top priority.

## 2. Decisions made this session (owner-ruled 2026-09-07)
1. **Deploy Hy-MT2 as a SINGLE model** for both commands and perception. The DictaLM/Hy-MT2 split is
   REJECTED — needless complexity for marginal gain; Hy-MT2 is ~never wrong on simple commands.
2. **Quant: prefer Q4** (VRAM-comfortable); Q6 only if the budget confirms it.
3. **SAM3 integration is a HARD PREREQUISITE** — the current OmDet+SAM2.1 leaves no GPU room for a translator.
4. **Step 6: patch the number guard SMARTLY** — fix the חצי bug WITHOUT degrading currently-correct translations.
5. Next subagent = ALL (live test is #1, but finish the unfinalized steps too).

## 3. Key findings (measured this session; full tables in the campaign-results doc)
- Full scorecard, 413 cases, EVERY model at best recipe (system prompt + 2 few-shots):
  DictaLM 339/405 (84%) | **tgemma 369/409 (90%)** | Hy-MT2-Q4 345/410 (84%) | **Q6 352/409 (86%)** | Q8 347/409 (85%).
- **Few-shots are THE lever.** 2 is optimal; 3/4 shots drift DOWN (86→85→84%). Zero-shot costs ~6–12 pp on
  commands — that artifact is why tgemma once looked weak (it was the only model never given few-shots).
- **tgemma+few-shots is the accuracy CHAMPION** (98% cmd / 88% perc) but 2,478 MiB → does NOT fit → not deployable.
- **Hy-MT2 is the deployable pick**: fits (Q4 1,188 / Q6 1,514 MiB), answer-mode 0, ~2× faster than tgemma.
- **DictaLM**: 99% commands but ANSWERS questions instead of translating (perception 61%); heavy CPU tail (p99 1.7 s).
- **Low-bit: nothing below Q4 works on x86.** tencent 1.25-bit (PR #22836, ARM NEON) + 2-bit (PR #19357, ARM SME2)
  are unmerged + ARM-only → unrunnable on x86. Self-quant standard Q2_K runs but output is incoherent (1.8B
  collapses at 2-bit). Floor = Q4_K_M.
- **VRAM fit**: co-resident measured (Qwen prod + Hy-MT2-Q6 + whisper-q5_k + YOLO) = 6,553 MiB, 1,156 free,
  ceiling ~7,708. + current OmDet(863)+SAM2.1(728) = 8,144 → OVER. + SAM3(886) = 7,439 → FITS (Q4 595 free /
  Q6 269). So SAM3 (unifies OmDet+SAM2.1, saves ~705 MiB) is required. CAVEAT: perception numbers are census
  ISOLATED (not co-loaded here) → a live all-five load is the final confirmation (unrun).
- **Number guard (Step 6)**: near-inert — fires 8/388 (1/203 commands), PATCHED 0. Ablation: retry +9 pp verbose
  (safe, fixes עשרים→"ten"), patch +7 pp but risky (caused the חצי=0.5 bug). Keep retry; fix/gate the patch.
- Dataset grew: perception 100→128 (+25 realistic see/presence questions), commands +14 live cases → bench = 413.
- ASR: classic whisper quants scored (fp16 18.72 / q8_0 18.73 / q5_1 18.79 / q4_0 19.59 WER). **k-quants
  (q4_k/q5_k/q6_k) UNSCORED** — Step 5 blocked (see §5.4).

## 4. Documents touched this session (audit — verify + fold gaps)
1. **docs/active/2026-09-07-vram-perception-campaign-results.md** — THE campaign report (compact, topic-sorted:
   decision/accuracy/perf/VRAM-fit/decomposition/guard/low-bit/remaining). GAPS: two `<!-- FORMATTING TODO -->`
   markers (§4 perception-engine fit table cramped; §8 layout); Step 5 WER/CER not folded (blocked).
2. **docs/active/2026-09-07-translator-bench.html** — visual report: grouped bar chart, full scorecard table,
   per-subset + CPU-thread + footprint tables, prompt appendix. All models shown at few-shot recipe (coherent).
   Publishing was disabled this env → it's a local file to open in a browser, not a live artifact.
3. **docs/active/2026-09-07-vram-perception-campaign-plan.md** — the original 6-step plan + checkpoint protocol. Reference only.
4. **docs/stale/2026-09-07-campaign-rawlog.md** — the chronological raw process log (superseded by #1). Keep for provenance.
5. **docs/NOTES.md** — running gotchas appended all session (FreeMono Hebrew-overlay font fix; DictaLM answer-mode
   root; number-guard חצי bug; SAM3/quant insights; guard ablation; low-bit). Some entries now also live in #1.
6. **tools/bench/hebrew-command-bench/README.md** — scorecard updated to the 388→then this session's runs. NOTE: the
   README shows the DictaLM-PATH scorecard, NOT the translator comparison — the translator comparison lives only in
   #1 (campaign doc). GAP to consider: README doesn't yet reflect perception=128 or the tgemma-few-shot finding.
7. **tools/bench/hebrew-command-bench/results/HISTORY.md** — superseded scorecards archived.
8. **cases_commands.py (+14 l_* cases), cases_perception.py (+25 pq_ +3 lp_ cases)** — dataset additions (leakage-checked).
9. **tools/bench/model-cpu-or-gpu/README.md** — census addendum with the full serving-config VRAM census.
10. **tools/bench/hebrew_asr/asr_bench.py** — patched: local edit-distance WER/CER (removes the jiwer dep) + added
    q4_k/q5_k/q6_k lanes. UNCOMMITTED. This is the Step 5 fix.
11. **projects/integration_harden/{config.py, scene_omdet.py}, tools/devenv/{install-runtime-deps.sh, Dockerfile}** —
    the FreeMono Hebrew-overlay font fix from EARLY this session (desk-test rendering, separate from the campaign).
12. **/root/.claude/.../memory/check-notes-before-diagnosing.md** — extended with the "search docs before proposing" lesson.
13. **Raw JSONs** in tools/bench/hebrew-command-bench/results/2026-09-07-*.json: recognizer, full-translator-table,
    perf-profile, perf-fulldataset-gpu, persubset-gpu, dicta-cpu-persubset, dicta-cpu-threads, tgemma-prompt-crossover,
    tgemma-fewshot, hymt2q6-shots, step6-dicta-capture, step2b/2d dumps. All measurements are here.
NOTE: a full line-by-line re-read audit of every doc was NOT possible in remaining context — the subagent should
verify #6 (README) and #5 (NOTES) for anything the campaign doc supersedes.

## 5. Remaining work (all decided; engineering + one benchmark + one patch)
1. **Integrate SAM3** into integration_harden (it lives in perception2). HARD PREREQUISITE — without it no GPU translator fits.
2. **Wire in single-model Hy-MT2** as the recognizer's translator (chat endpoint, TRANSLATE_SYS + 2 few-shots, our prompt). Drop the split.
3. **Confirm the fit**: one live all-five co-resident load (Qwen + SAM3 + YOLO + whisper + Hy-MT2) — the §3 caveat.
4. **Step 5 (optional, low value) — whisper k-quant WER/CER.** jiwer removed + local scorer patched into asr_bench;
   remaining blocker = stale FLEURS manifest (points at a dead scratchpad). FIX:
   `cd tools/bench/hebrew_asr && rm manifests/*.json && bash run.sh --step prep && bash run.sh --lanes q4_k,q5_k,q6_k`.
5. **Step 6 — smart number-guard patch** (see §6).
6. **Formatting** (low priority): §4 perception-engine fit table + §8 in the campaign doc (FORMATTING TODO markers).
7. **LIVE TEST — the demo priority.** Boot the current system (up.sh), run the 50-case list (tools/desk-test/live-test-50.md),
   record the Hebrew voice-drone video. The current system uses DictaLM-on-CPU (Hy-MT2 not wired yet) — that's fine to test with.

## 6. Step 6 — the smart guard patch (owner emphasized: don't degrade correct translations)
Bug: the guard's PATCH overwrites a correct translation's number with the Hebrew-extracted number. חצי case:
`_nums_he` (recognizer.py ~line 313) reads "חצי סיבוב" (half a REVOLUTION) as the number 0.5, then patches
DictaLM's correct "180 degrees" down to "0.5 degrees". Root: it treats חצי as an absolute 0.5, ignoring that
it's a fraction OF a unit (חצי סיבוב = 180; חצי מטר = 0.5). SMART FIX: in `_nums_he`, when חצי rides a rotation
noun (סיבוב/הקפה), compose to 180 — OR exclude חצי from extraction there so the guard doesn't fire on the
correct "180". Keep the retry (the +9 pp win). GATE: recognizer-bench skill (.claude/skills/recognizer-bench),
positives + adversarial negatives, ZERO false fires, full 413-case re-run, compare per-set counts — must show
ZERO regressions on the currently-correct translations. Guard is near-inert (fires 1/203) so this is low-risk if gated.

## 7. Standing gotchas (cost real time this session)
- `pkill -f "llama-server"` SELF-KILLS the shell (the command text matches the pattern). Kill by PID or port.
- GPU/Vulkan WEDGES after rapid kill -9 during model init — kill the zombie server (by PID) or reboot to recover.
- Nohup'd background scripts: the harness "completed" notification fires on the LAUNCHER exit, not the real work.
  Poll the result file, or run the wait-loop directly as a run_in_background Bash (not nohup'd).
- `score()` (cases_commands) returns a STRING — pass = startswith("CORRECT"/"valid"). `score_perception` returns
  the MISSING groups — pass = EMPTY list. Both are easy to invert (both bit me this session).
- Measure every translator WITH its few-shots (fairness) — zero-shot is a handicap, not a baseline.
- Serve llama-server LEAN (1 slot, small -c) — defaults are 4-slot/4096 (the "3 GB tgemma" scare was this).
- RTK wrappers + Bash-heredoc file edits are mandatory (Read/Edit/Write tools are permission-denied here).

## 8. Objective / compass
The demo is the compass: talk to the drone in Hebrew, show perception, show it approaching a target (CV→flight link).
The translator campaign was one piece and is now closed. The critical path to the video is: SAM3 integration →
Hy-MT2 wiring → live test. Owner runs ALL git and every boot/control script; agent runs down.sh only when told.

## 9. Git — UNCOMMITTED (human runs all git)
This session's work is NOT committed. The branch (feature-hardening-mvd) also carries UNRELATED
uncommitted work from other streams (llm_to_action dashboard/fmu, depth-sota-bench, tools/desk-test,
docs/ARCHITECTURE.md, docs/active/2026-09-0{4,5,6}-*) — do NOT bundle those with the campaign.

Campaign files to commit (this session):
- docs/active/2026-09-07-{session-handoff,translator-bench.html,vram-perception-campaign-plan,vram-perception-campaign-results}.md*
- docs/stale/2026-09-07-campaign-rawlog.md
- docs/NOTES.md  (campaign appends)
- tools/bench/hebrew-command-bench/{README.md,CASES.md,cases_commands.py,cases_perception.py,results/HISTORY.md,results/2026-09-07-*.json}
- tools/bench/model-cpu-or-gpu/README.md
- tools/bench/hebrew_asr/asr_bench.py  (local WER/CER + k-quant lanes)
Font-fix files (early this session, MIXED with prior uncommitted changes — human review the diff):
- projects/integration_harden/{config.py,scene_omdet.py}, tools/devenv/{install-runtime-deps.sh,Dockerfile}

Suggested commit (human runs, after reviewing the diff):
  git add docs/active/2026-09-07-* docs/stale/2026-09-07-campaign-rawlog.md \
    tools/bench/hebrew-command-bench tools/bench/model-cpu-or-gpu/README.md tools/bench/hebrew_asr/asr_bench.py docs/NOTES.md
  git commit -m "bench(translator): Hebrew HE->EN translator + VRAM campaign — Hy-MT2 chosen (single-model)

  full 413-case scorecard (all models few-shot): tgemma 90% is accuracy champion but VRAM-blocked (2478 MiB);
  Hy-MT2 Q4/Q6 is the deployable pick (fits, answer-mode 0). few-shots are the lever (2 optimal). low-bit
  dead on x86 (tencent ternary ARM-only PRs; Q2_K collapses). SAM3 REQUIRED to fit a GPU translator
  (current OmDet+SAM2.1 leaves no room). +25 perception see-questions, +14 live command cases (bench=413).
  asr_bench: local WER/CER (no jiwer) + k-quant lanes. reports: docs/active/2026-09-07-*; handoff same date.

  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
