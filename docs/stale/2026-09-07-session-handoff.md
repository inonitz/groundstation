# Session Handoff — 2026-09-07 (VRAM + Translator Campaign)
Doc owner: groundstation-05 (ref 55e80f) — role: live-test agent. Model: Opus 4.8.
For messaging me: refer to me as groundstation-05 / ref 55e80f. This doc dumps the full session so the
next agent bootstraps fast. Primary reports: docs/active/2026-09-07-vram-perception-campaign-results.md
(compact scorecard) and docs/active/2026-09-07-translator-bench.html (visual). Raw log: docs/stale/2026-09-07-campaign-rawlog.md.

> **SUPERSEDED START POINT: read docs/active/2026-09-08-session-handoff.md first** (the full dump of the
> 2026-09-08 stream: rulings, code, measurements, the whole-system test, open decisions, commit block).
> **START HERE (2026-09-08, day 2).** Read §11 top to bottom, then §12 (state at handover). Rules that
> bind you: retests run on the WEBCAM (§11.2 ruling); the owner runs every boot and every git write;
> report SHORT (the answer first, numbers in one table, details in files) -- the owner rejected two
> long write-ups on 2026-09-08 as unreadable; and address every point of a multi-point message by number.
>
> **Continuation 2026-09-07 late (second session of groundstation-05): read §11 first** — it carries the
> live-test runbook, what got built (SAM3 + Hy-MT2 behind flags, the smart number guard, the clockwise
> rules), the measurements, the open owner decisions, and the commit blocks. §§1-10 are the campaign context.

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

## 10. Context the other repo handoffs carry (added after cross-checking 4 prior handoffs)
- **DRONE SAFETY (absolute — you are doing LIVE TESTS).** Read CLAUDE.md's top section in full. The
  assistant NEVER sends arm/takeoff/land/stick/velocity/motor commands to a real aircraft — you PREPARE
  the exact command, the HUMAN runs it. Props-off is NOT sufficient; the aircraft must be secured.
  Control tools (/c/ws/sticks, /c/takeoff, /c/land, /c/fly*, dji_latency_probe) run against the MOCK
  127.0.0.1 ONLY, never a phone/drone IP. Know the kill BEFORE arming (phone API-Server toggle OFF;
  hold power button 3–5 s; CSC). Default read-only; when in doubt, do not send.
- **How the owner works.** Multi-point messages: address EVERY point by number, none skipped. One idea
  per bullet. Decisions go into repo docs IMMEDIATELY (chat is lost to compaction). Recommendations are
  NOT decisions — unstated = still open. Concrete over high-level: copy-paste commands, absolute paths.
  Real tests over mocks; label unverified numbers "unverified". Be a critical pair programmer (OBJECTIVE
  / ROI / KILL-SHOT gate), not a pleaser. See CLAUDE.md "Owner Interaction Protocol" + "Critical pair
  programmer mode".
- **Parallel agent lanes (do not confuse them with yours).** Manager = groundstation-15. Depth /
  llm_to_action depth-study = groundstation-13 (handoff docs/active/2026-09-06-llm-to-action-and-depth-handoff.md).
  llm_to_action demo polish = docs/active/2026-09-05-llm-to-action-report.md. projects/integration/ is
  the FROZEN proven demo fallback — changes land in forks (integration_harden), never there. Cross-session
  messages addressed to another lane: stay silent (don't add owner-turn noise).
- **Architecture.** The MVD voice chain: mic → Hebrew whisper ASR (F5 push-to-talk) → Recognizer (stage-0
  emergency regex, bypass, HE rewrite, translate, number guard, routing) → mission on the REST wire →
  DJI ApiServer (mock 127.0.0.1:8079 / phone :8080); perception = OmDet+SAM2.1 (→ SAM3) + Qwen3-VL gate;
  video via gstreamer_rx; phone TTS /tts. Recognizer lives in projects/integration_harden/recognizer/.
- **Measurement invariants** (if you benchmark): temp 0, prove determinism once; Wilson 95% intervals;
  exact McNemar for paired; latency percentiles as columns; ONE model resident on the GPU at a time;
  state a duration estimate before each run; full tables in chat. Invoke the recognizer-bench skill
  before touching the Recognizer or its benchmark.


## 11. Continuation — 2026-09-07 late (groundstation-05, second session, Opus 4.8)

### 11.1 State found, and what that decided
- Nothing was running (no tmux, all ports free, GPU 111 MiB). The laptop was on the home router
  (wireless gateway 192.168.1.1), NOT the phone hotspot, and the owner was away. The live test needs
  the owner at the desk (mic, phone, drone video), so it is BLOCKED on the owner; everything below
  prepares it and finishes the campaign's remaining work without touching the demo path.
- Two SAM3 Python deps (bitsandbytes, accelerate) had been wiped by a container rebuild. Reinstalled
  and scripted (install-runtime-deps.sh + Dockerfile).
- Assumption (agent, OPEN): SAM3 and Hy-MT2 are wired behind env flags whose DEFAULTS are the current
  demo path, so `up.sh` boots byte-for-byte the system the owner already tested. The next stack is one
  env prefix away. The owner flips the defaults after the live test passes on the new stack.

### 11.2 LIVE-TEST RUNBOOK (owner runs every line; control stays on the MOCK, never the phone)
**RULING 2026-09-08 (owner): every retest, and the retest of any new translator prompt, runs on the
WEBCAM, not the drone and phone.** Webcam mode mocks the whole system with nothing connected and
costs no hotspot, no phone, no aircraft (the owner lost ~12 hours over two days waiting for the phone).
The phone and drone are needed only for the final demo footage. The line is:
`VIDEO=webcam SCENE_TTS=off bash /root/groundstation/tools/desk-test/up.sh`
(preflight then skips the phone checks; SCENE_TTS=off because the phone speaker is absent.
Steps 2-5 below are unchanged. Webcam mode has been in run_mvd.sh/up.sh all along --
`VIDEO=webcam` -- the runbook simply never said to use it.)
1. FINAL DEMO FOOTAGE ONLY: phone on its hotspot, API Server toggle ON, drone powered for video.
   Laptop joined to the hotspot (preflight derives the phone IP from the wireless default route).
2. Preflight (read-only, fails loudly):
   `bash /root/groundstation/tools/desk-test/preflight.sh`
3. Boot the CURRENT demo path (DictaLM on CPU + OmDet/SAM2.1; records the dataset session):
   `bash /root/groundstation/tools/desk-test/up.sh`
   then `tmux attach -t mvd` (window `app` = the scene; `mock` (7) shows every REST command live).
4. Speak `tools/desk-test/live-test-75.md` in order, one utterance per F5 press (F5 on, speak, F5 off).
   (2026-09-08: 25 unspoken dataset cases + 25 weak-point probes + 25 production-speech probes, each with its expected result and the dataset set it joins afterwards. live-test-50.md is the 2026-09-06 list.)
   Do not read the numbers aloud. Perception cases 35-50 need drone video on screen.
5. Score afterwards from the recorder:
   `python3 /root/groundstation/tools/desk-test/show_session.py latest`
   (session folder: projects/integration_harden/sessions/session-<ts>-rog/ with utterances.jsonl + clips/).
6. Video: capture the OpenCV window (`integration:scene_omdet`) plus the tmux `mock` window. If ffmpeg
   is present: `ffmpeg -f x11grab -framerate 30 -i :0.0 -f pulse -i default /root/groundstation/projects/integration_harden/sessions/demo-$(date +%Y%m%d-%H%M%S).mkv`
   (Ctrl-C stops). Otherwise OBS on the same display. Unverified here (no owner at the desk).
7. Teardown: `bash /root/groundstation/tools/desk-test/down.sh`
8. AFTER the demo path passes, the next stack (SAM3 highlight + Hy-MT2 on the GPU), same steps:
   `VIDEO=webcam SCENE_TTS=off SCENE_SEG=sam3 MVD_TRANSLATOR=hymt2 bash /root/groundstation/tools/desk-test/up.sh`
   Preflight checks the pairing (hymt2 requires sam3) and the SAM3 deps. Re-run the 50 list and diff
   the two sessions with show_session.py. Expect the first SAM3 highlight ~2 s after the gate (nf4
   load is at boot; forwards are ~0.45 s, rate-limited to 1/s).

### 11.3 Built this session (all Python/bash; no C++; no git writes)
| what | where | note |
|---|---|---|
| SAM3 highlight backend switch | projects/integration_harden/scene_omdet.py `build_highlight()`, `SEG`, `SAM3_PERIOD` | `SCENE_SEG=omdet\|sam3`; sam3 = perception2.Sam3Backend (detect + cached mask from ONE forward); OmDet/SAM2.1 never load; overlay labels follow the backend |
| attribute-preserving SAM3 concepts | projects/integration_harden/perception2/concept.py `phrase_concepts()` | "the red backpack" -> "red backpack"; bare categories fan out; the VLM front-end is off the live path (it drops colours) |
| Hy-MT2 server script | projects/integration_harden/recognizer/run_hymt2_server.sh | Q4_K_M, Vulkan, -c 512 -np 1, port 18091 (same endpoint as DictaLM: pipeline.py unchanged) |
| translator switch | projects/integration_harden/run_mvd.sh (`MVD_TRANSLATOR=dicta\|hymt2`, `SCENE_SEG` export, tmux window `dicta` -> `xlate`, log mvd_xlate.log) | up.sh / status.sh / preflight.sh follow (pipe-pane list, labels, stack checks) |
| deps scripted | tools/devenv/install-runtime-deps.sh, tools/devenv/Dockerfile | bitsandbytes==0.50.2, accelerate==1.14.0 |
| smart number guard (Step 6) | recognizer/recognizer.py `HE_HALF_TURN_RE`, `EN_HALF_TURN_RE`, `patch_number` decimal token | see §11.4 |
| clockwise / counterclockwise inline rules | recognizer/recognizer.py HE_RULES | Hy-MT2 sign flip; see §11.4 |
| bench lanes | tools/bench/hebrew-command-bench/bench.py `--translator`, `--tag`; compare_runs.py; llama.py MODELS["hymt2"] | the campaign's translator harness was never in the repo; now it is |
| co-resident census | tools/bench/model-cpu-or-gpu/census.py `--sam3-stack` (+ import-path fix, bash spawn) | measures the ruled topology together |
| tests | test/test_scene_wiring.py (+3 build_highlight), test/test_perception.py (+1), test/test_recognizer.py (+1 half-turn regression) | 37 tests + engine/recognizer/concept self-tests all green |

### 11.4 Measurements (temp 0, one pass, 413 cases; raw under tools/bench/hebrew-command-bench/results/2026-09-07-recognizer-*.json)
| run | emergency | std-204 | verbose-54 | perception-128 | military-20 | ALL |
|---|---|---|---|---|---|---|
| dicta-base (unpatched Recognizer) | 7/7 | 197/199 | 50/53 | 76/128 | 9/20 | 339/407 (83%) |
| dicta-guard (Step 6 patch) | 7/7 | 197/199 | 50/53 | 76/128 | 9/20 | 339/407 — **0 output diffs of 413** |
| hymt2 (Step 6 patch, Hy-MT2-Q4 resident) | 7/7 | 193/201 | 43/54 | 90/128 | 9/20 | 342/410 (83%) |
| dicta-cw (+ clockwise rules) | 7/7 | 197/199 | 50/53 | 76/128 | 9/20 | 339/407 — counts identical, 20 idiom outputs changed, 0 false fires |
| hymt2-cw / hymt2-cw2 (+ clockwise rules; two runs, 0 diffs) | 7/7 | 195/201 | 44/54 | 90/128 | 9/20 | **345/410 (84%)** — the README scorecard |

- Step 6 gate: PASSED (zero regressions, zero diffs). The bench's DictaLM never emits "180 degrees"
  for חצי סיבוב, so the positives are in recognizer.selftest and test_recognizer.py
  `test_half_turn_keeps_a_correct_180` (a correct 180 passes unpatched; a wrong 0.5 is repaired to 180;
  חצי מטר stays 0.5).
- Hy-MT2 through the full pipeline reproduces the campaign row (345/410) within the ±1-2 noise band.
  The +3 net vs DictaLM hides +14 perception, -4 std, -7 verbose. Failure classes: (a) clockwise
  rendered counter-clockwise (combo3, combo5, v_finish3_g3) -> the inline rules, measured in the -cw
  runs; (b) literal register ("Wait, make sure you are ready" -> planner adds a wait; "שנייה אחרי זה"
  -> "a second after that" -> delay 1): v_first3_g0/g2, v_ready3_g0/g3; (c) possibility/past phrasing
  the planner refuses ("It is possible to take off", "Let's fly", "Climbed to a height of 10 meters"):
  r_takeoff2/3, r_land4, r_alt10. Lever for (b)+(c): few-shot CONTENT (imperative exemplars; keep 2).
- Clockwise-rule gate on Hy-MT2, per-case planner verdicts (rules stripped in-memory = control
  `hymt2-norules` 342/410 vs rules on `hymt2-cw2` 345/410; 27 idiom outputs changed; run-to-run
  determinism proven: cw vs cw2 = 0 diffs). Verdict flips, all five:

  | case | rules off | rules on | reading |
  |---|---|---|---|
  | combo3 | wrong-degrees(-90 vs 90) | CORRECT | sign flip fixed |
  | combo5 | wrong-degrees(-90 vs 90) | CORRECT | sign flip fixed |
  | v_finish3_g3 | wrong-degrees(-180 vs 180) | CORRECT | sign flip fixed |
  | v_ready3_g0 | wrong-len(4 vs 3) | CORRECT | literal "with the direction of the clock" was confusing the planner |
  | v_note3_g3 | CORRECT | missing-y | Hy-MT2 now splits the sentence at "Note:" and the planner drops the last step (English itself is correct) |

  Zero false fires (the rule fired only on the idiom; negatives in the self-test). One downstream
  regression (v_note3_g3, a dropped final step, not a wrong motion) against four fixes, three of them
  wrong ROTATION DIRECTION. Shipped with the flip disclosed; owner may veto (§11.5 item 3).
- Co-resident census (`census.py --sam3-stack`, nvidia-smi deltas over a 111 MiB baseline):
  Qwen prod 3,821 + Hy-MT2-Q4 (-c 512) 1,187 + YOLO 284 + SAM3-nf4 in-process 1,074 + one 1280x720
  image ask transient 94. FIVE-MODEL RERUN (real ASR node included, measured together):

  | step | delta MiB | total over baseline | free |
  |---|---|---|---|
  | Qwen3-VL (run_llama_server.sh, prod flags) | 3,821 | 3,821 | 3,776 |
  | Hy-MT2-Q4 (run_hymt2_server.sh, -c 512 -np 1) | 1,187 | 5,008 | 2,590 |
  | whisper q5_k via the REAL asr_server node | 827 | 5,835 | 1,763 |
  | YOLO26n-seg (720p predict) | 282 | 6,117 | 1,481 |
  | SAM3-nf4 in-process (perception2, one detect) | 1,074 | 7,191 | 407 |
  | Qwen 1280x720 image ask transient | 94 | 7,285 | 313 |
  | **all resident together** | | **used 7,396 / 8,151** | **313 free** |

  Verdict: the ruled topology FITS, at Q4 ONLY. The margin is 313 MiB, not the ~600 the campaign
  computed on paper, because SAM3-nf4 costs 1,074 MiB in-process (bnb + activations), not the 886
  isolated torch peak. Hy-MT2-Q6 (+326) would overrun. Raw:
  tools/bench/model-cpu-or-gpu/results/2026-09-07-sam3-stack-census.json.

### 11.4b LIVE Step 1 result (2026-09-08 00:37, current stack, live-test-50): 38/50
Report: projects/integration_harden/sessions/session-20260908-003702-rog/REPORT.md (sessions are
gitignored; the summary is in docs/NOTES.md). Causes: ASR 6, DictaLM answer-mode 3, router
see-question gap 2, תפסיק gap 1. Safety: the land-trap question (#28) LANDED (DictaLM answered
"To land, please say Land"; the planner obeyed); "תחזור הביתה" also became LAND; two ASR garbles
flew wrong spins. No answer-mode guard exists in the code (the 2026-09-07 proposal was withdrawn);
the owner ran Step 3 (Hy-MT2 stack) first and deferred the guard decision.

### 11.4c LIVE Step 3 result (2026-09-08 01:02, Hy-MT2 + SAM3 stack, live-test-75): 41/69 scored
Report: projects/integration_harden/sessions/session-20260908-010129-rog/REPORT.md; summary in NOTES.
Headline: the land trap held; Hy-MT2's past-tense/possibility register makes the planner refuse
6 lines; the highlight path is unreachable for Follow/Focus on/Emphasize (engine FIND_RE); three
false rejects were my guard's tokenizer (punctuation, ש clitic); the planner echoed its own
few-shot mission on "Do it!" (5-step flight from two words).

### 11.4d Post-Step-3 fixes (2026-09-08 ~02:00) — owner approved 1, 2, 3, 6; held 4, 5
1. Highlight parser accepts follow / focus on / emphasize (perception/engine.py). 2. Guard tokenizer:
glued punctuation stripped, ש clitic on חצי read. 3. סיבוב וחצי = 540 both sides. 6. Answer-mode
guard, strict retry then REJECT (translate() has `strict`). Held: 4. bare מטר -> מטר אחד rewrite;
5. planner few-shot echo guard. Gate = full 413 both translators, flips listed: see NOTES.

### 11.4e Six fixes gated + the 75 list as text (2026-09-08 ~01:40)
Gate (compare_runs.py flips vs same-code baselines): DictaLM 339 -> 346, 14 outputs changed, 5 flips, all
safe (four traps now CORRECT-reject; l_land_going: planner LANDED -> reject). Hy-MT2 345 -> 348, 3 outputs
changed, 0 flips against. Reject scoring changed the same night (README). Text-mode 75 (run_list.py):
DictaLM 45/7/23 (pass/fail/review), Hy-MT2 36/16/23; Hy-MT2 loses 8 lines to its past-tense /
possibility register (planner refuses statements) — the few-shot-content decision (11.5 item 3) is now
the biggest Hy-MT2 lever. DANGER found in the DictaLM text run: "יאללה נחת" -> "Take off" (planner sent
takeoff). Tables: projects/integration_harden/sessions/text-runs/2026-09-08-live-test-75-{hymt2,dicta}.md.

### 11.4f Hy-MT2 V2 prompt: WRITTEN (prompts.py TRANSLATE_SYS_V2/SHOTS_V2, selectable by
`--prompt v2` / `MVD_TRANSLATE_PROMPT=v2`), MEASURED, REJECTED (341 vs 348; three unsafe flips:
r_pol_spin sign, r_low sign, r_neg4 negation flies; perception -8). Details in NOTES. V1 remains the
default. Live server context raised to 1024 anyway (V2-sized prompts need it). Original proposal:
Owner asked what to add to the translator prompt to cover its measured issues. Proposal: keep TWO
few-shots (the campaign's measured optimum) but change their content, and add six rules to the system
prompt. NOT the coordinate frame (the planner owns it; a translator that knows the frame starts planning).

System prompt text:
```
You translate spoken Hebrew addressed to a camera drone into English for a flight planner.
Output ONLY the English sentence.
1. An instruction or a request becomes an English IMPERATIVE: "take off", "climb 5 meters".
   Never past tense, never "it rose", never "it is possible to".
   "אפשר ל...", "תוכל ל...", "אתה יכול ל...", "בוא נ..." are requests: translate them as imperatives.
2. A question about the drone's intent or state stays a question and is never answered:
   "האם אתה מתכוון/הולך/מתכנן ל...", "מה אתה רואה", "כמה ...".
3. Keep every number, unit and direction exactly. Write numbers as digits.
4. Rotation words: "עם כיוון השעון" = clockwise, "נגד כיוון השעון" = counterclockwise,
   "חצי סיבוב" = a half turn, "סיבוב שלם" = a full turn, "סיבוב וחצי" = one and a half turns.
5. Sideways motion is "move right/left N meters", never "turn". "פנה"/"הסתובב" are "turn".
6. Fillers are not actions: "רגע", "שנייה", "תקשיב", "יאללה", "בסדר", "יופי" are dropped or
   become "then". Keep the order and the number of actions, one clause per action.
```
Few-shots (two, replacing the current pair):
- "אפשר להמריא ואז לעלות חמישה מטרים?" -> "Take off, then climb 5 meters."
- "תקשיב, קודם טוס אחורה ארבעה מטרים, שנייה אחרי זה זוז שמאלה שלושה מטרים ובסוף הסתובב תשעים מעלות עם כיוון השעון"
  -> "First fly backward 4 meters, then move left 3 meters, and finally turn 90 degrees clockwise."
Rules 1-6 map to the measured issues: 1 = statement register (11 cases), 2 = answer-mode/intent traps,
3 = numbers, 4 = the clockwise flip + turn idioms, 5 = "turn back 4 meters" (3 cases), 6 = "a second
after that" / preambles (planner-inherited, 9 verbose cases). Risk: the request-vs-question line
(rule 1 vs 2); the bench has cases on both sides (r_pol_* fly, l_land_going / q_land_trap stay EMPTY).
Gate when the owner says go: prompts.py V2 constants + `bench.py --prompt v2`, Hy-MT2 413 run with flips
vs 2026-09-08-recognizer-hymt2-day2.json, ceiling = perfect-EN 246/258. ~3 min.

### 11.4g Gemma 4 E4B probe (2026-09-08): a single-model Hebrew planner + VLM candidate
Resident 3,950 MiB with vision (= Qwen's size) and would REPLACE the translator too (frees ~1,060).
Direct-Hebrew planning 8/10 on a probe at 351 ms p50 (misses: אפשר להמריא -> [], סיבוב וחצי -> 180).
Vision works and reads Hebrew, but narrates a thinking preamble in plain text -> needs a GBNF grammar
for the LONG/SHORT/HIGHLIGHT format; 5.5 s per image ask vs Qwen ~3 s. Details + server gotchas in
NOTES. OPEN: the owner's idea to run Gemma 4 + whisper + SAM3 as the whole stack; the measurement
that decides it is the 413-case bench in direct-Hebrew mode (needs a `--planner gemma4 --direct-he`
lane in bench.py) plus a VLM format grammar. TranslateGemma placement (11.4 / owner "use it"): still
awaiting the owner's where/when.

### 11.4h PROPOSED: how to test a whole-stack replacement (Gemma 4 + whisper + SAM3) reliably
Owner (2026-09-08): "we don't have a reliable method of simulating a production run." Proposal, four
lanes, all offline, all reproducible, the same inputs for every stack:
1. AUDIO REPLAY (the production language path minus the microphone): the recorded push-to-talk clips
   (sessions/*/clips/*.wav, 153 real clips with known list lines) -> whisper-cli with the node's model
   and flags -> text -> the text-mode pipeline (run_list.py) -> scored against the list. Whisper is
   fixed, so the lane isolates the language stack (translator + Recognizer + planner). New tool:
   run_list.py --from-clips <session>. Cost: ~1 min per stack.
2. COMMANDS AT SCALE: the 413-case bench in direct-Hebrew mode (`bench.py --planner gemma4 --direct-he`,
   built 2026-09-08) vs the translator stacks; the perfect-English control gives each planner's ceiling.
3. VISION: whole-system/vlm_compare.py (built 2026-09-08): both VLMs on the 17 candidates + 8
   desk-camera frames, the production gate prompt and a people count, scored as AGREEMENT with SAM3
   (present/absent, box IoU, count) plus a side-by-side sheet for the owner's eyes. Becomes a true
   score if the owner labels ~20 desk frames for ~5 phrases each (about 15 minutes of labelling).
4. LIVE MIC on the webcam with live-test-75.md, scored by score_live.py. The final check only.
What stays unmeasured by 1-4: TTS, the phone link, drone motion, and VLM answers to open questions
(no truth exists; the side-by-side sheet is the review). Decision rule proposed: a replacement stack
must match or beat the current one on lanes 1-3 with zero unsafe flips before it gets lane 4.

### 11.5 Open owner decisions (numbered; nothing here is settled)
0. Add the stage-4 answer-mode guard (reject reply-shaped English after a strict retry)? Evidence:
   4 live utterances on 2026-09-08. Bench-gated, ~5 min GPU. Deferred by the owner until after Step 3.
1. Flip the defaults to `SCENE_SEG=sam3` + `MVD_TRANSLATOR=hymt2` — after the live test passes on them?
2. SAM3 concepts: keep the attribute-preserving `phrase_concepts` on the live path (agent's call), or
   the VLM front-end (`extract_concepts`, drops colours by design)?
3. Hy-MT2 register defects (§11.4 b, c): change the two few-shot CONTENTS to imperative exemplars
   (bench-gated), add EN rewrite rules, or accept? Also: keep the clockwise rules despite the one
   v_note3_g3 flip (4 fixed, 1 dropped step)? A "Note:"-preamble EN rule has only ONE measured
   failure, below the two-failure bar for a new rule.
4. After the swap is confirmed live: delete `perception/`, rename `perception2` -> `perception`
   (three files are verbatim copies today).
5. Step 5 whisper k-quants: owner runs the command in the campaign doc §8 (agent was blocked).
6. Standing: EMERGENCY_RE תפסיק gap; phone TTS 503 gate remedy (2026-09-05 handoff §18).

### 11.6 Gotchas added this session
- The auto-mode permission classifier blocks `rm` of result manifests and dataset downloads; hand those
  to the owner instead of working around.
- `subprocess.Popen(shell=True)` is /bin/sh (dash): `source` does not exist there. Spawn with
  `["bash", "-c", cmd]` for anything sourcing ROS.
- census.py imported `llama` from the bench dir; llama.py lives in recognizer/ (single home) -> path fixed.
- SAM3-nf4 in the app process = ~1,074 MiB (vs 886 isolated peak). Budget with the in-process number.
- A port can be held by a process OUTSIDE this container (host networking): `ss -p` shows no pid,
  /proc has no owner, down.sh cannot kill it. preflight/down now say so and print the host command;
  `MVD_XLATE_PORT=18092 bash up.sh` boots the translator on another port (2026-09-08, :18091 case).

### 11.7 Git (owner runs all; NOTHING committed this session)
Files this session (mine): projects/integration_harden/{scene_omdet.py, run_mvd.sh,
perception2/concept.py, perception2/__init__.py, perception2/README.md, recognizer/recognizer.py,
recognizer/llama.py, recognizer/run_hymt2_server.sh (new), test/test_scene_wiring.py,
test/test_perception.py, test/test_recognizer.py}; tools/desk-test/{up.sh, preflight.sh, status.sh};
tools/devenv/{install-runtime-deps.sh, Dockerfile}; tools/bench/hebrew-command-bench/{bench.py,
compare_runs.py (new), README.md, results/HISTORY.md, results/2026-09-07-recognizer-*.json};
tools/bench/model-cpu-or-gpu/{census.py, results/2026-09-07-sam3-stack-census.json};
docs/active/2026-09-07-{session-handoff.md, vram-perception-campaign-results.md}; docs/NOTES.md.
The branch ALSO carries the earlier uncommitted campaign files (§9) and other lanes' work — do not bundle.

Suggested commits (after reviewing the diffs):
```
cd /root/groundstation
git add projects/integration_harden/scene_omdet.py projects/integration_harden/run_mvd.sh \
        projects/integration_harden/perception2 projects/integration_harden/recognizer/run_hymt2_server.sh \
        projects/integration_harden/test/test_scene_wiring.py projects/integration_harden/test/test_perception.py \
        tools/desk-test/up.sh tools/desk-test/preflight.sh tools/desk-test/status.sh \
        tools/devenv/install-runtime-deps.sh tools/devenv/Dockerfile
git commit -m "feat(harden): SAM3 highlight + Hy-MT2 translator behind flags (defaults = demo path)

SCENE_SEG=omdet|sam3 picks the highlight backend (build_highlight: one SAM3-nf4 forward = boxes + cached masks; OmDet/SAM2.1 never load; forwards rate-limited 1/s) | MVD_TRANSLATOR=dicta|hymt2 picks the :18091 server (run_hymt2_server.sh, -c 512 -np 1, Vulkan) | perception2.phrase_concepts keeps attributes (the white car, not every car) | up/preflight/status follow (window dicta->xlate, stack checks) | deps scripted: bitsandbytes 0.50.2 + accelerate 1.14.0 | 4 wiring tests

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"

git add projects/integration_harden/recognizer projects/integration_harden/perception/engine.py \
        projects/integration_harden/test tools/bench/hebrew-command-bench tools/bench/model-cpu-or-gpu \
        tools/desk-test/live-test-75.md tools/desk-test/score_live.py \
        docs/active/2026-09-07-session-handoff.md docs/active/2026-09-07-vram-perception-campaign-results.md docs/NOTES.md
git commit -m "fix(recognizer): guards from two live runs -- half-turn, clockwise, answer-mode, planner echo, tokenizer, 540, bare-metre; highlight parser gains follow/focus/emphasize; bench --translator + flips + run_list

live 2026-09-08: land trap LANDED on DictaLM (answer-mode) -> stage-4b guard (strict retry, then reject + read back) | planner copied its own few-shot on \"Do it!\" -> echo guard | number guard: ASR-glued punctuation + shin clitic on chatzi (3 false rejects), chatzi sivuv=180, sivuv vachetzi=540, bare metre -> metre echad (Hy-MT2 \"six meters\") | clockwise/counterclockwise inline (Hy-MT2 sign flip) | perception FIND_RE: follow/focus on/emphasize (highlight path was unreachable for akov/hitmaked/hadgesh) | bench: --translator, --tag, per-case verdicts, reject scoring (trap=pass, command=fail), compare_runs flips, run_list text-mode | gates: DictaLM 339->346, Hy-MT2 345->348, 0 flips against | census.py --sam3-stack: 7,396/8,151 used, 313 free | README scorecard at 413, old blocks archived

chatzi sivuv composes to 180 on both sides (a correct 180 passes unpatched, a wrong 0.5 is repaired), patch_number handles decimal tokens | 413-case gate: 0 output diffs vs same-day baseline | clockwise/counterclockwise inline rules fix Hy-MT2's sign flip (combo3/combo5/v_finish3_g3), re-measured | bench.py --translator dicta|hymt2 + --tag, compare_runs.py per-case diff; Hy-MT2 full pipeline 342/410 reproduces the campaign row | census.py --sam3-stack measures the ruled topology together | README scorecard at 413, 388 archived to HISTORY.md

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```


## 12. State at handover (2026-09-08, day 2, groundstation-05 -> next agent)
- Code: six Recognizer/perception fixes from the two live runs are in (§11.4d/e), gated on both
  translators with per-case flips, 39 tests + three self-tests + bench audit green. Nothing committed;
  the commit block is §11.7 (owner runs git).
- Numbers to quote: bench 413 = DictaLM 346/412, Hy-MT2 348/412 (README scorecard). 75-list as text:
  DictaLM 64/75, Hy-MT2 56/75 (Hy-MT2 loses 7 to its past-tense/possibility register). Live mic runs:
  Step 1 (DictaLM stack) 38/50, Step 3 (Hy-MT2+SAM3 stack) 41/69. Co-resident VRAM: 7,396/8,151 used.
- Tools: `tools/bench/whole-system/run_list.py <list.md> --translator dicta|hymt2` = the
  75-list as text (no mic, ~30 s); `compare_runs.py A.json B.json` = the gate (flips);
  `tools/desk-test/score_live.py <list.md> latest` = a mic session next to its list.
- Boot for any retest: `VIDEO=webcam SCENE_TTS=off bash /root/groundstation/tools/desk-test/up.sh`
  (+ `SCENE_SEG=sam3 MVD_TRANSLATOR=hymt2` for the new stack). Phone/drone = final footage only.
- Open owner decisions: §11.5 (defaults flip; Hy-MT2 few-shot content; keep the clockwise rules;
  delete perception/; Step 5 whisper quants) plus, from day 2: "turn back N meters" EN rule (3 measured),
  wire check_colors + add סגול (2 silent colour errors), router rule for count/presence questions
  (48, 49 on every run), emergency words די/הפסק/תפסיק, and the DictaLM "יאללה נחת" -> "Take off" danger.
- Perfect-English control (2026-09-08, `bench.py --perfect-en`): planner alone 246/258 (std 201/204,
  verbose 45/54). Nine verbose losses are the planner turning "a second after that" / "Wait, make sure
  you are ready" / "and also" into delay steps or merged axes; Hy-MT2 inherits them, DictaLM paraphrases
  them away. OPEN owner decision: fix those in the PLANNER prompt (one action per clause; time fillers
  and preambles are not actions), gated by --perfect-en (73 s) plus both translator runs.
- Day-2 rerun (2026-09-08 morning): all suites green; bench 413 identical to last night on both
  translators (0 diffs, 0 flips). live-test-75 is now v2, ALL 75 NEW (the v1 Set 1 came from the
  dataset -- my misreading, corrected on the owner's instruction). Text-mode v2: Hy-MT2 42/10/23,
  DictaLM 44/8/23 (pass/fail/review). New candidates in NOTES: סיבוב שלם = 360 idiom (DictaLM
  false reject), two uncaught DictaLM answer shapes, תצפית/דווח missing from the perception router.
