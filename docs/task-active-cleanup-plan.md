# Cleanup plan — precise, provenanced (2026-09-17)

Owner ruled the cleanup is IN (field test is low-stakes). This is exactly what I intend to perform,
in order, with the source of each conclusion. Nothing here is executed yet — it is for your review.

## Provenance legend
[T] thermo-nuclear review found it   [P] ponytail review found it   [T+P] both, independently
[ME] I re-verified in source myself   file:line = the evidence anchor

## Execution protocol (how, not just what)
- Work in a fork/branch, NOT on the feature branch directly.
- One theme per commit; I prepare each commit and hand you the exact git commands — I run NO git writes.
- BEFORE every deletion I grep-verify zero live callers MYSELF and do not trust the agent's "dead"
  label. Reason: the `_nums_en` case — both an agent AND I initially over-trusted a "dead" call that
  was live-but-inert. Verify each, every time.
- Gate EVERY commit on: the 66-test suite green AND the 410/487 unified_bench unchanged.

## Where my ordering comes from
Risk == reachability. A file imported by nothing (grep-verified) or that crashes on import cannot
change behavior when removed -> those go first. In-app dead code needs per-item caller verification
(the _nums_en lesson) -> next. Refactors touch live code paths -> last, each behind tests+bench.

================================================================================
## STAGE 1 — whole-file deletes of unimported / broken files (lowest risk)
Each: grep-verify no live importer, then delete. Gate: tests + bench.
- perception2/engine.py        [T+P] near-verbatim dup of live perception/engine.py; not imported. 189L
- perception2/vlm_client.py    [T+P] dup of live perception/vlm_client.py; not imported. 116L
- perception2/detectors.py     [T+P] dead OmDet+SAM2; not imported. 124L
- perception2/chain_demo.py    [T+P] broken import (build_engine/parse_highlight unexported). 65L
  THEN: move perception2/{sam3_backend,concept,counting,lexicon}.py into perception/, delete
  perception2/, repoint ~6 import sites (mvd.py:24-25,156; recognizer/pipeline.py:19). [T+P]
- run_mvd.sh                   [T+P] superseded by run.sh; only comment/README refs. 170L
- run_router.py                [T+P] dead; nonexistent module path; never imported. 55L
- video/video_doctor.py        [P]   not wired into any launcher; run.sh status covers it. 62L
- build.ps1                    [T+P] drifted Windows twin (missing dji backend); Linux-only project. 92L
- tools/dji_mock/ws_latency.py [T+P] superseded by measure_ws_rtt.py; sole websockets importer. 105L
- tools/dji_mock/plot_latency.py [P] matplotlib one-off; hardcoded run title; sole matplotlib user. 77L
- bench/hebrew-command-bench/compare_runs.py [T+P] reads retired translator schema. 56L

## STAGE 2 — finish the two migrations in bench/ (broken today)
- bench/whole-system/run_list.py     [T+P] dead `from bench import make_translator,plan` -> rewrite against unified_bench or delete.
- bench/whole-system/run_all.sh      [T+P] remove the 3-4 lanes calling retired bench.py flags.
- bench/whole-system/planning_table.py [T+P] 2/3 stacks retired + globs non-emitted JSON -> rewrite or delete.
- stale `tools/bench` -> `bench` in 6 files [T+P]: run_list.py:25, planning_table.py:7, vlm_compare.py:16,
  sam3_alone.py:12, vision_chain.py:11, overlays.py:11 -> one shared path constant.

## STAGE 3 — in-app dead code (verify EACH caller first; the _nums_en rule)
- recognizer genuinely-dead ~180L [T+P, per-item [ME] grep before cut]:
  stage 5 EN_RULES/apply_en (~505-560), stage 4b answer_mode (~468-498), stage 4 EN reconciliation
  check_numbers/patch_number/_resolve_numbers (423-465), stage 6 route()/PERCEPTION_RE/MOVEMENT_RE
  (~565-590), check_colors+COLORS (~500-518), and the selftest lines that test only these.
  KEEP `_nums_en`/`EN_NUM` — [ME] verified LIVE via pipeline.is_shot_echo (pipeline.py:49,107).
- OmDet render scaffolding [T+P]: SCENE_SEG fork (mvd.py:64), the `else` branches (mvd.py:273,331),
  OM name-dict threaded as constant "SAM3" (mvd.py:78 -> render_chat/HUD/_model_lines), the "omdet"
  map entry (overlay.py:134), _hl_debug/_last_hl_dbg (mvd.py:97-110).
- mvd vestigial [T+P]: S.conf/S.mask_k (mvd.py:89,117), --keep-llama/we_started_llama pgrep dance
  (mvd.py:385,397,553-554).

## STAGE 4 — safety-doc corrections ([T]; [ME] will confirm each before editing)
- config_constants.py:6 "CONTROL_TARGET alone decides the wire" is FALSE (MVD_WIRE_REAL decides) -> fix.
- kill.py:9 halt() docstring describes an UNSAFE post-kill behavior the code correctly refuses -> fix.
- MOCK_WIRE_PORT=8079 phantom (mock binds 8080; host guard separates) -> note it.
- KillSwitch.MOTION over-lists -> minimal set {takeoff, land, fly_mission}.
NOTE: the dji_wire.py loopback guard itself is CORRECT [T+P] -> do NOT touch.

## STAGE 5 — duplication collapses / refactors (bigger; each behind tests+bench)
- Shared bench-support module [T+P]: owns bench paths, Sam3Backend (deletes SAM3 detect() x4),
  llama lifecycle + MODELS/PORT (deletes vlm_compare private spinup + scattered 18090 literals),
  iou (x3 -> 1), pct (x5 -> 1, fixes power_profile off-by-one at :118).
- tools/dji_mock/_djiprobe.py extract [T+P]: preflight()+HINTS duplicated in measure_telemetry.py +
  measure_ws_rtt.py.
- config consolidation [T+P]: merge config_constants.py + config_defaults.py into one values file;
  delete dead wire_target()/video_input()/CONTROL; consume the Ports constants instead of literals;
  pick ONE import surface (mvd bypasses config.py today); collapse the two gateway-discovery impls.
- tts_io backend registry [T+P]: {name:(ready,say)} collapses the triplicated selection; delete the
  dead espeak re-check (:63-65); keep phone out of the table.
- recognizer decomposition [T]: after the Stage-3 deletes, split 786->~520 into
  numbers/emergency/bypass/rewrites/guards with __init__ re-exporting current names.
- overlay chat-entry tagging [T+P]: tag entries (role,text,kind) at the mvd write site; delete the
  Hebrew/English prefix parsing + partition round-trip in overlay.
- route session recording through the observe= hook [T] instead of monkey-patching wire/pipe (mvd:428-447).

## OPEN QUESTIONS -> tracked in the SESSION (owner 2026-09-17: questions belong in chat, not here)
Items awaiting an owner decision are asked and answered in the session history: install-translation-models
dead fetches, VLM presence-gate + ASCII fallback keep/cut, build.sh perf flags, retired-campaign archival,
run_mvd/video_doctor deletes, the perception2 dir-collapse, and a rebuilt compare_runs.

## Recommended first move
Stage 1 only, as one branch: delete the unimported/broken files + the perception2 collapse. It is
almost entirely `git rm` + a handful of import repoints, it is the largest single line reduction
(~1,000 of the ~1,700), and it is the safest to prove green. I verify each import myself, run
tests+bench, and hand you the commit. Then we decide Stage 2+ together.

================================================================================
# EXECUTION REPORT (live log)
================================================================================
Rule: I run NO git. Whole-file deletes/moves/commits are prepared as commands for the owner (see the
GIT QUEUE at the very bottom). Every code change gated: 66 tests, + the 410/487 bench after any
recognizer/pipeline edit. Baseline before starting: 66 tests PASS (2026-09-17).

## Consistency pre-check (before beginning) — 2 review claims REJECTED as wrong/unsafe
- REJECTED "MOCK_WIRE_PORT=8079 is a phantom; the mock binds 8080." FALSE: run.sh:191-192 binds the
  mock on 8079 and run.sh:175 targets 8079 for the mock wire. The 8080 was only the bare default of
  mock_apiserver.py / DjiWire when run WITHOUT run.sh. MOCK_WIRE_PORT=8079 is CORRECT; no change.
- REJECTED "shrink KillSwitch.MOTION to {takeoff,land,fly_mission}." Unsafe: the mission verbs are only
  refused transitively via the guarded fly_mission; a kill switch must not depend on that. Did the
  OPPOSITE -- added track_me/wave for explicit coverage.
- The plan is otherwise internally consistent (e.g. _nums_en is KEEP everywhere; recognizer edit precedes
  its decomposition; perception2 files deleted before the optional dir collapse).

## STAGE 4 — safety-doc corrections: DONE + verified (66 tests pass)
- config_constants.py:6 CONTROL_TARGET-decides-the-wire wording corrected (MVD_WIRE_REAL decides;
  loopback guard is the gate).
- control/kill.py docstring corrected: only stop() stays allowed; halt() is refused after a kill
  (verified: halt()->self.fly_mission which KillSwitch guards -> 409; refusing it is correct, it re-takes
  stick control). track_me/wave added to MOTION for explicit coverage (see rejection above).
- dji_wire.py loopback guard left untouched (verified correct).

## STAGE 3 — recognizer dead code: MAPPED + VERIFIED, cut DEFERRED to a focused pass
All 7 flagged stages confirmed dead (zero live callers; only self-referential + tested by selftest()):
check_numbers/patch_number/_resolve_numbers (423-465), answer_mode+ANSWER_* (470-491), COLORS+check_colors
(494-508), EN_RULES+apply_en (515-543), route+PERCEPTION_RE+MOVEMENT_RE (553-567). KEEP _nums_en/EN_NUM
([ME] verified live via pipeline.is_shot_echo).
WHY DEFERRED (not skipped): selftest() (571-729) interleaves ~40 dead-stage asserts line-by-line with
LIVE asserts (_nums_he/_nums_en/bypass/add_missing_verb/explicit_one_meter/emergency), and __init__.py
exports `route`+`selftest`, and main() prints len(EN_RULES). The cut must surgically remove the dead
asserts + fix the export + the print WITHOUT touching a live assert, in the safety-adjacent Hebrew sieve,
then re-run the 4-min bench. This is the most error-prone edit in the plan; it gets its own focused pass
with test_recognizer (selftest()==[]) as the gate. Live path (recognize_direct->emergency/bypass/
negation/apply_he->Gemma) does NOT touch these, so the bench is expected unchanged — but will be re-run to prove it.

## STAGE 1 — GIT QUEUE (owner runs; verified no live importer)
Clean deletes, ready now (grep-verified zero live import; perception2/__init__ imports only the live
sam3_backend/concept/counting; lexicon imported directly):
```
cd /root/groundstation
git rm projects/integration_harden2/perception2/engine.py \
       projects/integration_harden2/perception2/vlm_client.py \
       projects/integration_harden2/perception2/detectors.py \
       projects/integration_harden2/perception2/chain_demo.py \
       projects/integration_harden2/run_router.py \
       tools/dji_mock/ws_latency.py \
       tools/dji_mock/plot_latency.py \
       bench/hebrew-command-bench/compare_runs.py \
       build.ps1
# then: run the 66-test suite + import-smoke, review, commit.
```
HELD pending doc-repoint (statements, not questions -- open questions live in the SESSION per owner 2026-09-17):
- projects/integration_harden2/run_mvd.sh: README.md + spec-harden2-run-arguments.md name it as THE launcher; repoint to `run.sh up`, then delete.
- projects/integration_harden2/video/video_doctor.py: named in video/__init__.py docstring + camera_stream.py/dji_wire.py comments; manual diagnostic superseded by `run.sh status`.
DEFERRED (needs import repoints across ~6 sites): the optional perception2/ -> perception/ directory
collapse (move sam3_backend/concept/counting/lexicon into perception/). perception2 with only the 4 live
modules is already correct; the collapse is tidiness, done as a git mv batch later.

## STAGE 3 — recognizer dead code: DONE + verified
Removed the contiguous dead-def block (check_numbers/patch_number/_resolve_numbers, answer_mode+ANSWER_*,
COLORS/check_colors, EN_RULES/apply_en, route+PERCEPTION_RE+MOVEMENT_RE) and their selftest asserts; fixed
the summary print; dropped the `route` export from __init__. recognizer.py 786 -> 604 lines (-182).
KEPT _nums_en/EN_NUM (verified live). GATE: 66 tests pass; unified_bench IDENTICAL to baseline
(410/487; emergency 12/12, std190 236/253, verbose 59/63, perception 103/138, military 0/21; wall 241s).
Behavior-preserving on the measured path.

## Owner rulings 2026-09-17 (from session): applied
- video_doctor.py: DELETE (run.sh status supersedes). run_mvd.sh: repoint README + spec -> run.sh, delete.
- install-translation-models.sh: remove the dead translation fetches. VLM presence-gate + ASCII fallback: KEEP.
- build.sh perf flags: LEAVE. compare_runs: LEAVE gone. retired campaigns: keep results+history, move rest
  to archive (archive = trash). perception2: KEEP as its own package (signifies module version control; do NOT collapse).

## Translator-retirement finish (install scripts): DONE
- install-translation-models.sh rewritten: dropped opus-mt(x2)/nllb/madlad400/translategemma (retired
  translated path); kept the qwen2.5-coder phone-parser bench fetch. bash -n OK.
- sentencepiece removed from install-runtime-deps.sh AND tools/devenv/Dockerfile (verified: 0 live
  `import sentencepiece` in the tree). bash -n OK.

## Still to do (my in-file work): OmDet render scaffolding (mvd/overlay) + mvd vestigial (Stage 3);
## run_mvd/video_doctor doc-repoints then delete; Stage 2 bench-script repair; Stage 5 refactors;
## retired-campaign archival (keep results+history -> archive the rest, owner git).

## STAGE 3 — OmDet render scaffolding: DONE + verified (66 tests pass)
mvd.py: dropped the two dead `if SEG=="sam3" else` branches, dropped OM["name"] (now the literal "SAM3"),
dropped the om_name arg to render_chat, rewrote the stale omdet comment block. overlay.py: _model_lines +
render_chat drop the om_name param; eyes = f"SAM3-{prec}" (omdet map + fallback gone). Kept SEG + the
build_highlight sam3 guard (cheap invariant; SEG is entangled with run.sh's export). Compiles; wiring tests green.

## STILL TO DO
- Stage 3 remainder: mvd vestigial (S.conf/S.mask_k dead knobs; _hl_debug; the --keep-llama pgrep dance -- process
  lifecycle, treat carefully).
- run_mvd.sh + video_doctor.py: doc-repoints (README + spec rewrite to run.sh; video/__init__ + comments), then delete.
- Stage 2: bench-script repair (run_list.py, run_all.sh lanes, planning_table.py, 6 stale tools/bench paths).
- Stage 5 refactors: TTS backend registry, config consolidation, _djiprobe extract, shared bench-support module,
  overlay chat-entry tagging, observe= recording, recognizer decomposition.
- Retired-campaign archival (keep results+history; archive the rest; owner git).

## STAGE 3 mvd vestigial + run_mvd/video_doctor repoints: DONE (66 tests pass)
- mvd.py: removed S.conf/S.mask_k dead knobs + the unused worker unpack; removed the _hl_debug throttled
  printer + its call (dbg now `_`). KEPT --keep-llama/we_started_llama (cheap process-cleanup net; removing
  it risks orphan llama-server in standalone runs -- deliberate deviation from the ponytail "delete").
- run_mvd.sh + video_doctor.py references repointed: READMEs -> `run.sh up`; spec launcher refs -> run.sh;
  video_doctor mentions removed from video/__init__, camera_stream, dji_wire comments + the README video row;
  capture_golden_config comment run_mvd.sh -> run.sh. Verified: 0 refs remain. Both files now safe to git rm.

## STAGE 2 — bench repair: mostly a no-op (verified)
- The "6 stale tools/bench paths" the reviews flagged were ALREADY fixed in the 2026-09-13 restructure
  (C2b). Only one docstring comment remained (run_list.py:16) -- fixed.
- run_list.py / run_all.sh / planning_table.py are broken by the translator retirement (dead `from bench
  import make_translator,plan`; retired --translator/--direct-he flags; retired *-recognizer-* globs).
  These are the WHOLE-SYSTEM / audio-replay e2e bench, which the owner earlier ruled to LEAVE for later
  reconstruction (not the same as the deletable compare_runs). LEFT as-is, parked, not deleted/repaired.

## STAGE 5 — structural refactors: RECOMMEND DEFER to post-freeze (see session)
Rationale in chat: config merge, recognizer decomposition, overlay chat-tagging, observe= recording, the
TTS registry, the shared bench module, _djiprobe -- these are organizational POLISH that touch live code
for modest gain. Doing them hot right before the freeze + field test adds regression risk. The dead-code
cleanup (the reviews' headline, ~1500 of the ~1700 lines) is DONE and verified. Recommend: freeze the
cleaned baseline, do Stage 5 post-freeze against the proven tag. Awaiting owner's call in the session.

## STAGE 5 progress (owner: execute everything now, amend later)
- observe= recording: DONE. pipeline.handle now reports the action via observe(); dropped the pipe.handle
  monkey-patch in mvd. (The wire.fly_mission/halt patches stay -- they capture router-level wire commands,
  not redundant with observe.) 66 tests pass.
- TTS simplified to HEBREW-ONLY (owner ruling 2026-09-17, no registry): SCENE_TTS = phone | phonikud | off.
  Removed espeak/piper/both. phonikud now CRASHES (TTSConfigError, re-raised by mvd) if its model/deps are
  missing -- no silent fallback. Verified: phonikud speaks; missing model raises; invalid value warns->off;
  66 tests pass. Spec + devenv comment updated. (espeak-ng kept in devenv: aplay + phonemizer-fork dep.)
- CONFIG CONSOLIDATION: REJECTED. The config_constants/config_defaults split is a DELIBERATE,
  golden-master-tested design (test_config_golden.py resolves both files to captured values across the 3
  app scenarios and uses wire_target()/video_input() as the intended resolver API for the in-progress app
  rewire B2). Merging the files / deleting wire_target would break the golden test and fight the design.
  Not a cleanup -- a review misread (like the MOCK_WIRE_PORT phantom + the MOTION-shrink).
- REMAINING Stage 5: recognizer decomposition, overlay chat-tagging, shared bench module, _djiprobe extract.

## STAGE 5 — final accounting (2026-09-17)
DONE + verified (66 tests; bench 410/487; tree consistent):
- observe= recording (pipeline reports action via observe; mvd monkey-patch dropped).
- TTS Hebrew-only (phone|phonikud|off; phonikud crashes if model missing; espeak/piper removed).
REJECTED with evidence (review misreads, not cleanup):
- config consolidation -- config_constants/config_defaults is a golden-master-tested design
  (test_config_golden). Merging / deleting wire_target would break the test and fight the intended B2 rewire.
NOT done -- flagged, need a real gate or are below-value (owner to direct; amend-later does not cover
shipping the demo's visible surface blind):
- overlay chat-tagging: LARGE coordinated change to the LIVE render panel (colors/labels/RTL/status) with
  NO rendering test. Do it post-freeze WITH a render test + a GUI eyeball, not blind before the field test.
- recognizer decomposition: recognizer.py is 604 lines, UNDER the 1k rule. Splitting is pure churn + import
  risk for zero functional/size gain. Recommend skip.
- shared bench module + _djiprobe extract: tooling dedup (bench/tools only). Modest value; _djiprobe also
  fixes the power_profile pct off-by-one. Safe to do post-freeze; not gating the frozen system.
NET on the frozen system (integration_harden2): all dead code + safety-doc + TTS work landed and verified.

## The two "I can do it now" items -- inspected 2026-09-17 (mostly review over-calls)
- power_profile pct off-by-one: REAL BUG -> FIXED. `int(q/100*len(s))` -> `int(round(q/100*(len(s)-1)))`.
  Verified: p95 of 1..100 = 95 (was 96). The dji_mock probes already used the correct formula.
- `_djiprobe` extract: NOT needed. The two probes' preflight() have DIFFERENT signatures
  (measure_ws_rtt: host,port ; measure_telemetry: url) -- not a shared function. HINTS is a 3-line dict;
  sharing it across 2 files is marginal. So the "preflight/HINTS/pct ×5 dup" was an over-call.
- shared bench module (SAM3 detect ×4): NOT done -- over-call. run_suite/measure/etc. use RAW model/proc
  detect deliberately, to measure precision variants + raw VRAM; Sam3Backend's wrapped API cannot, so
  consolidating would break the bench's purpose. iou ×3 is a tiny pure fn across two non-package subdirs
  (fragile to share) -- left.
Net: these two items = one real bug fix (pct). The rest did not survive inspection (like config/overlay/
MOCK_WIRE_PORT/MOTION). Pattern: the review agents flagged real code but over-prescribed the fix.

================================================================================
# RESUME STATE — 2026-09-17 (write before compaction; pick up here)
================================================================================

## DONE + verified (66 tests green; recognizer bench 410/487 unchanged). Owner has NOT committed yet.
- Dead files deleted (staged): perception2/{engine,vlm_client,detectors,chain_demo}.py, run_router.py,
  ws_latency.py, plot_latency.py, compare_runs.py, build.ps1. STILL TO git rm: run_mvd.sh, video_doctor.py.
- recognizer.py 786->604->480: removed dead translator stages; moved selftest()+main() to recognizer/selftest.py.
- OmDet render scaffolding removed from mvd.py/overlay.py; mvd vestigial removed (S.conf/S.mask_k, _hl_debug).
- observe= recording: pipeline.handle reports action via observe(); mvd handle monkey-patch dropped.
- TTS Hebrew-only: audio/tts_io.py = phone|phonikud|off; phonikud raises TTSConfigError if model missing;
  mvd re-raises it. espeak/piper removed. TTSConfigError is the new fatal path.
- Safety docs: config_constants.py CONTROL_TARGET wording; kill.py halt() docstring + track_me/wave in MOTION.
- Install/devenv: install-translation-models.sh trimmed to qwen-coder only; sentencepiece removed from
  install-runtime-deps.sh + Dockerfile. espeak-ng kept (aplay/phonemizer dep).
- power_profile.py pct off-by-one FIXED.
- Doc repoints: run_mvd/video_doctor refs -> run.sh/removed; spec SCENE_TTS -> phone|phonikud|off.
- Config intent graph: docs/config_design.{png,svg,dot}.

## REJECTED / CLOSED as review over-calls (evidence in this doc above): MOCK_WIRE_PORT phantom,
## MOTION-shrink, _djiprobe/shared-bench-module (raw SAM3 detect is deliberate; preflight sigs differ),
## overlay was NOT rejected (still open, see below).

## OPEN TASK 1 (owner ruled 2026-09-17, option A) — CONFIG PACKAGE. NOT STARTED. Big; do fresh.
Owner spec: make projects/integration_harden2/config/ and put the 3 config files inside. EVERYTHING
routes through config.py ONLY -- like a C header. No module peers into internals (no `import
config_constants`/`config_defaults`); they import only the surface config exposes.
Concrete plan:
  - config/__init__.py = the current config.py (the public surface/adapter).
  - config/constants.py = config_constants.py ; config/defaults.py = config_defaults.py (internal).
  - config/__init__.py imports constants+defaults internally and must EXPOSE every symbol consumers need.
  - FIX consumers that bypass: mvd.py:20 (`import config_constants as _K, config_defaults as _D` -> use
    config.X; add the ~11 symbols mvd uses to the surface). Hardcoded ports -> config.X:
    recognizer/pipeline.py:34 QWEN_PORT=18090 -> config.LLAMA_SERVER_PORT; perception2/concept.py:186
    "http://127.0.0.1:18090"; audio/phone_asr.py:25 port=8080 -> config.PHONE_ASR_PORT.
  - test/test_config_golden.py + capture_golden_config.py import config_constants/defaults directly;
    rework to verify through the config surface (this is the trickiest bit -- the golden test resolves
    per-scenario via wire_target(control); preserve that guarantee).
  - GATE: 66 tests (esp. test_config_golden) + import-smoke every module. It is the golden-master net.

## OPEN TASK 2 — overlay chat-tagging. NOT STARTED. Needs a render test + a human GUI eyeball.
mvd writes chat rows as strings with embedded meaning ("Highlighting:", "rejected -- ", "ספרתי",
"tag| value"); overlay.render_chat REVERSE-PARSES them (startswith/partition) to pick each row's LABEL,
COLOR, RTL, and the green/red hit-miss status light. Refactor: tag entries (role,text,kind) at the write
site; overlay switches on kind. If correct, ZERO visual change. Risk: no test renders the panel, so a
wrong color/label/status ships unseen -> only visible in the live GUI. That is why a GUI check is the gate.

## PARKED (owner, from the restructure): the WHOLE-SYSTEM / e2e bench -- bench/whole-system/{run_all.sh,
## run_list.py,planning_table.py}. Broken by the translator retirement; to be RECONSTRUCTED later, after
## recording + accuracy testing. LEFT as-is on purpose. Not deleted, not repaired.

## GIT: nothing committed this session. When ready, regenerate the multi-commit batch (it grew:
## + recognizer/selftest.py, pipeline.py, tts_io.py, power_profile.py, config graph, run_mvd/video_doctor rm).

## OVERALL PLAN POSITION: reviews done -> cleanup (this) -> webcam retest on clean tree -> field test ->
## freeze -> post-freeze benches -> features -> fuse into C++ llm_to_action.

## HANDOFF REFINEMENTS — 2026-09-17 (triple-checked; owner rulings folded in)
TRIPLE-CHECK STAMP: all touched .py compile; 66 tests pass; recognizer.py = 479 lines; TTS = phone|
phonikud|off; run_mvd.sh + video/video_doctor.py still on disk (owner git rm). Nothing committed yet.

Owner rulings 2026-09-17 (latest):
- e2e (Stage 2 parked): agreed it is odd to measure an unfinished system; address it LATER, after the
  system is finished (recording + accuracy). Leave bench/whole-system as-is until then.
- dji_mock: mock_apiserver.py IS live (run.sh starts it on 8079 for `up ... mock`; teardown kills it).
  measure_telemetry/measure_ws_rtt/measure_video_e2e have NO invoker -> MANUAL latency probes; keep.
  pct fix applied to power_profile.py only (probes' pct already correct). None of it is dead.
- CONFIG (OPEN TASK 1): CONFIRMED option A -> config/ package, C-header surface. Spec in RESUME STATE above.
- OVERLAY (OPEN TASK 2): owner is the GUI check. Approved test method for the refactor:
    1. run the GUI (run.sh up webcam mock, WEBCAM_DEV set) feeding 1-3 predefined Hebrew sentences,
    2. screenshot ONLY the "integration:mvd" window,
    3. close, apply the (role,text,kind) tagging change,
    4. re-run + screenshot the same window,
    5. diff the two images (agent inspects both) -> expect ZERO visual change; report any pixel diff.
  Keep it simple; the before/after screenshot diff IS the gate (there is no automated render test).

NEXT-SESSION ORDER (fresh context; execute from this doc):
  1. Owner commits the current verified cleanup (regenerate the multi-commit git batch first).
  2. OPEN TASK 1 config/ package (gate: 66 tests + test_config_golden + import-smoke).
  3. OPEN TASK 2 overlay tagging (gate: the screenshot before/after diff above).
  4. Then: webcam retest on the clean tree -> field test -> freeze.
This doc + docs/task-active-thermo-review-*.md + docs/task-active-ponytail-review.md are the full record.
