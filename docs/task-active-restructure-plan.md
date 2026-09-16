# Repo cleanup & restructure + dataset tooling — plan (2026-09-13)

Status: DRAFT for owner review. Nothing here runs without explicit owner approval.

## Context

Order of operations (owner-corrected, supersedes the handoff order):
1. Cleanup & restructure.
2. Webcam test.
3. Nuclear code-quality review.
4. Field test outside.
5. Freeze, if all is good.
If problems arise in any step, pause and debug until they clear. Do not skip ahead to freeze.

This plan is step 1. It also builds the dataset tooling, because that tooling belongs to the
restructure. Steps 2 to 5 are the surrounding roadmap, recorded for context, not executed here.

Two rules for this plan:
- Do all code and structural work first. Modify documents LAST.
- Nothing is hard-deleted during cleanup. Everything to remove moves into archive/. archive/ is the
  deletion staging area. It survives the webcam, nuclear, and field tests as a safety net. The final
  commit (at freeze) clears archive/ and deletes it in one step.

## Target repo structure (the end state, after the final archive purge)

```
groundstation/
  projects/    integration_harden2, integration_tts, llm_to_action
  bench/       moved from tools/bench: hebrew-command-bench, whole-system, sam3-mask-bench,
               plus the completed campaigns (kept for their numbers)
  tools/       non-bench tooling only: dji_mock, devenv, session-replayer, diagrams
  datasets/    curated TEST assets by modality: vision/, asr/, translation/, e2e/   (gitignored)
  logs/        ALL harden2 runtime output: sessions/, traces/, runs/                (gitignored)
  docs/        active, research, runbooks, specs, stale, private, top-level md
  assets/ cmake/  kept as-is
```

## Decisions (owner-ruled)

Trees:
- KEEP: integration_harden2, integration_tts, llm_to_action.
- REMOVE (stage in archive/): integration, integration_harden, integration_notify, slam.
- integration_tts is the new FROZEN demo fallback. It replaces integration/ in the CLAUDE.md rule.
- slam was the failed Tello-stabilization experiment. Inside llm_to_action only the core tello backend
  stays; the slam-hold parts go with slam.

Datasets:
- A dataset is a curated TEST set that measures one part of the pipeline against ground truth.
- It is not vision-only and it is not a log. Modalities, all buildable from session logs:
  - asr: session asr_clips plus corrected reference transcripts; tests whisper.
  - translation: source and reference-target text pairs; tests the translation step.
  - vision: frames plus boxes and labels; tests SAM3 detection and count.
  - e2e: audio in, expected transcript plus translation plus action or highlight; tests the whole loop.
- Home: top-level datasets/<modality>/<set-name>/, gitignored. May move to assets/datasets/ later.
- Tooling covers vision and asr now (both already in the logs). translation and e2e reuse the same
  file-plus-reference ingest.

Benchmarks:
- Move tools/bench to a top-level bench/.

Logs:
- All harden2 runtime artifacts move under logs/. The llm_to_action log lines stay as they are; that
  tree writes them with its own scripts and I do not edit it.

Dataset tooling (Phase 2) — NO server, NO state:
- The replayer downloads the frame or clip plus a sidecar JSON, client-side.
- A one-shot script files the download into datasets/<modality>/<set>/ and converts a vision set to COCO.
- Annotate BOUNDING BOXES for vision now. Masks deferred FOR NOW, re-opened after freeze (we will need
  them for serious vision work). Why they are not free today: the recorder saves only conf/box/label
  (session_log.py:183-187), so SAM3 masks are never written. To enable later: persist masks in the
  recorder, or re-run SAM3 on the frame at annotation time.

Other:
- bench.py stays. unified_bench.py imports its shared infra.
- The one tracked docs/active/2026-09-07-translator-bench.html stays tracked. No special gitignore rule.

## Guidelines this plan follows (docs/code-guidelines.md, writing-style.md)

- KISS and YAGNI. Units ~150-400 LOC. WHY-comments. Guard clauses. House naming and formatting.
  No speculative abstraction. No unnecessary state (hence: no server).
- Do not strip commented-out or legacy code I did not write without asking. G1 (bench.py) is the one
  exception, which the owner approves by approving this plan.
- Commits: house style, type(scope): summary | detail. Few aggregated commits. The human runs all git.
- Result docs follow the benchmark register (Objective, Setup, Results, Analysis). Superseded docs move
  to docs/stale/, never deleted.

## Constraints

- The human owns every git write. The assistant prepares exact commands; the human runs them.
- llm_to_action is the other subagent's tree. The assistant does not edit it.
- One model on the GPU at a time. The assistant never pre-starts llama-server.
- logs/ and datasets/ are gitignored. Session data holds private transcripts and audio.
- After touching recognizer, pipeline, or bench, re-run the full bench and compare per-set counts.

Marker key: [A] assistant edits code, [H] human runs git or a move, [O] owner or the other subagent.

## Phase 1 — cleanup & restructure (code + structure; docs come in Phase 3)

### Group A — fix the dead-tree test imports (before staging any tree)

- A1 [A] Retarget the harden2 tests off the dead tree. They import integration_harden.control (dead),
  not harden2's own control/. This also fixes a latent bug.
  - projects/integration_harden2/test/test_router.py (lines 6-7)
  - projects/integration_harden2/test/live_mock_smoke.py (lines 22-25)

### Group C — move benchmarks to top-level bench/ (before the ref fixes)

- C1 [H] Move the tree:
  ```
  git mv tools/bench bench
  ```
- C2 [A] After the move, retarget code references (scripts only; the skill doc is fixed in Phase 3):
  - the old tools/bench path in internal bench scripts (whole-system, sam3-mask-bench) -> bench/
  - integration_harden -> integration_harden2 in every KEPT LIVE bench that names it, so nothing breaks
    when integration_harden moves to archive/ in Group B:
    - bench/hebrew-command-bench/bench.py:30 (MVD_HOME default)
    - bench/whole-system/run_list.py:26-27 (MVD_HOME default), sam3_alone.py:11, vision_chain.py:9,
      overlays.py:8, vlm_compare.py:17, and run_all.sh:14 (SESSION default -> logs/sessions)
    - bench/sam3-mask-bench/quant_bench.py:14, run_indepth.py:7, compare_engines.py:21
  - The cruft campaigns (Group G5) are NOT retargeted; their scripts move to archive/.
- C3 Completed campaigns move with the tree (depth-sota-bench, yolo26-depth-bench, hebrew_asr,
  model-cpu-or-gpu). Keep their tracked scripts and result docs. Their untracked raw data goes to
  archive/ in Group G.

### Group G-code — small-fry code cleanup

- G1 [A] Strip bench.py's dead legacy functions make_translator, plan, main. KEEP to_scorer_schema and
  the llama re-exports. File: bench/hebrew-command-bench/bench.py. Re-run the full bench after this.

### Group D — logs consolidation and the gitignore collapse

- D1 [H] Create the dirs:
  ```
  mkdir -p /root/groundstation/logs/sessions /root/groundstation/logs/traces /root/groundstation/logs/runs
  ```
- D2 [A] Point harden2's writers at logs/ (env-first, so small):
  - projects/integration_harden2/run.sh line 195: MVD_SESSIONS_ROOT default -> /root/groundstation/logs/sessions
  - projects/integration_harden2/session_log.py lines 57-58: fallback dir -> /root/groundstation/logs/sessions
  - projects/integration_harden2/run.sh line 23: run_dir root (RUN_ROOT) -> /root/groundstation/logs/runs
- D3 [H] Move existing harden2 artifacts (gitignored data):
  ```
  mv /root/groundstation/projects/integration_harden2/sessions/* /root/groundstation/logs/sessions/ 2>/dev/null || true
  mv /root/groundstation/projects/integration_harden2/traces/* /root/groundstation/logs/traces/ 2>/dev/null || true
  rmdir /root/groundstation/projects/integration_harden2/sessions /root/groundstation/projects/integration_harden2/traces 2>/dev/null || true
  ```
- D4 [A] Collapse the .gitignore. Classify every block:
  - KEEP IN PLACE: build/, venv, __pycache__, *.py[cod], Makefile/.ninja*/*.ninja, .cache/.vs/*.sln/
    *.vcxproj*/compile_commands.json, imgui.ini, *.pt, *.apk, m2.zip, _exo_transfer/, test_img*.
  - KEEP (llm_to_action's own logs, that tree writes them): vlm_logs/, captured_panes_log.txt.
  - REPLACE WITH /logs/: harden2 sessions and traces, *.log, *.out, gs_sessions_*.tgz,
    tools/dji_mock/out/, *.wav.
  - RETARGET bench result patterns to the new bench/ path (tools/bench/... -> bench/...). This MUST land
    before Group F, or Group F will not detect the moved-and-ignored result files.
  - ADD /datasets/ (curated test assets, private).
  - DROP the dead-tree lines (their trees move to archive/ in Group B).

### Group E — retire tools/desk-test into run.sh

- E1 [A] Add run.sh subcommands, pointed at logs/sessions:
  - run.sh score [session] — folds score_session.py (writes REPORT.md) and score_live.py.
  - run.sh show [session] — folds show_session.py.
- E2 [A] Port status.sh's extra diagnostics into cmd_status: the --watch phone gate, the app-wiring
  greps, the video frame-arrival greps, and the one-shot phone-gate curl.
- E3 [H] Stage the retired launchers in archive/ (not deleted):
  ```
  mv /root/groundstation/tools/desk-test /root/groundstation/archive/
  mv /root/groundstation/projects/integration_harden2/run_mvd.sh /root/groundstation/archive/
  ```
- After E: run a webcam SMOKE CHECK (a restructure verification, NOT the roadmap's formal webcam test).

### Group B — stage the dead trees in archive/ (not deleted)

- B1 [O] PREREQUISITE for slam: remove the slam-hold parts from llm_to_action
  (tello_backend/test/tello_slam_hold.cpp and its CMake target, lines 82-95). I do NOT edit this tree.
- B2 [H] Move the four trees into archive/ (tracked + untracked files move together):
  ```
  mv /root/groundstation/projects/integration \
     /root/groundstation/projects/integration_harden \
     /root/groundstation/projects/integration_notify \
     /root/groundstation/projects/slam \
     /root/groundstation/archive/
  ```
  Then stage the move (git records the tracked files as renames): `git add -A projects archive`.

### Group F — gitignore vs index reconciliation (AFTER D retargets the bench patterns)

- F1 [H] Untrack the files that are tracked but match .gitignore. They stay on disk.
  ```
  cd /root/groundstation
  git ls-files | git check-ignore --no-index --stdin | xargs -r git rm --cached --
  ```
  Mostly docs/active/*.md, docs/active/assets/, and bench results dumps. Numbers already live in
  RESULTS.md and HISTORY.md. (The translator-bench.html is not ignored and stays tracked.)

### Group G-disk — stage the rest of the removals in archive/

- G4 [H] Move the repo-root throwaways:
  ```
  mv /root/groundstation/gitignored-all.txt /root/groundstation/gitignored-decisions.txt /root/groundstation/archive/
  ```
- G5 The four completed cruft campaigns: hebrew_asr, yolo26-depth-bench, depth-sota-bench,
  model-cpu-or-gpu. Owner ruling: keep only what lets us double-check the result markdowns; delete the rest.
  - KEEP in bench/<name>/ (so the numbers stay verifiable):
    - the result markdowns (README.md, RESULTS.md, HISTORY.md, DEPTH-BENCHMARKS.md, results.md/.txt)
    - the raw runs behind them (per-run result json/jsonl/txt, and hebrew_asr bench_out/ transcripts)
  - [H] STAGE the rest to archive/ (recoverable there until the final purge; frees ~6 GB):
    - the campaign scripts and tools (.py/.sh) -- these campaigns are done and are not re-run
    - the heavy re-downloadable data: depth-sota-bench gguf/ (5.0 GB) + cloned depth-anything.cpp/ (415 MB),
      yolo26-depth-bench weights/data (~468 MB), hebrew_asr input audio + downloaded models (~296 MB)
  - The three LIVE benches (hebrew-command-bench, whole-system, sam3-mask-bench) are kept in full.
  - Bonus: staging the cruft scripts also clears their dangling integration_harden references.

## Phase 2 — dataset tooling (build; no server; vision + asr)

Flow: replay a session, pick an item, correct or annotate it, export a client-side download, then run a
script that files it into datasets/<modality>/<set>/.

- P2.1 [A] Vision, in replayer.html: show the SAM3 boxes from the log as editable rectangles. Draw, move,
  resize, delete, type a class label. Export downloads {frame.jpg, sidecar.json}. Masks deferred.
- P2.2 [A] ASR: a small CLI script walks a session's asr_clips plus its trace transcripts, lets you
  correct each transcript, and writes datasets/asr/<set>/.
- P2.3 [A] One ingest script (called, not a running server): moves a vision download into
  datasets/vision/<set>/, and converts a vision set to COCO on demand. translation and e2e reuse it.
- P2.4 A finer build brainstorm happens when we reach it. Code follows docs/code-guidelines.md.

## Phase 3 — documentation (LAST)

Only after all code and structure above is done and verified.

- Z1 [A] Rewrite bench/hebrew-command-bench/README.md to current state (unified_bench, 410/487).
- Z2 [A] Update .claude/skills/recognizer-bench/SKILL.md paths (tools/bench -> bench).
- Z3 [A] Update the CLAUDE.md hard rule: the frozen demo fallback is integration_tts.
- Z4 [A] Fix the bench-path doc mentions (docs/NOTES.md, ARCHITECTURE.md, ROADMAP.md: tools/bench -> bench).
- Z5 [A] Add a NOTES.md bullet: the tree removals, the bench/ move, the logs/ consolidation, archive/ staging.
- Z6 [A] Move superseded docs to docs/stale/. Mirror this plan into docs/active/2026-09-13-repo-restructure.md.

## Phase 4 — final purge (at freeze, the final commit)

Only after webcam + nuclear + field tests pass and the owner is ready to freeze.

- [H] Delete archive/ entirely — this is the only hard deletion, and it is last:
  ```
  cd /root/groundstation
  git rm -r archive
  rm -rf /root/groundstation/archive
  ```
  Commit it on its own: `chore: remove archive/ — superseded trees, launchers, raw bench data`.

## Execution order (safe sequence)

Phase 1: A -> C -> G-code (re-run bench) -> D -> E (webcam smoke check) -> B (after B1) -> F -> G-disk.
Phase 2: P2.1 to P2.3.
Phase 3: all doc edits, last.
Phase 4: purge archive/, at freeze only.

Separate, pre-existing: the translated-path retirement already on disk is its own commit (it includes
G1's bench.py edit). The human decides commit timing and aggregates related work into few commits.

## Verification

- After A: run the harden2 test suite. The retargeted tests import and pass.
- After C+G1: re-run unified_bench, temp 0, one server. Expect 410/487, zero changed cases. State a
  duration estimate before the run. Do not pre-start llama-server; the bench brings up its own.
- After D+E: WEBCAM_DEV=2 MVD_TTS=0 bash /root/groundstation/projects/integration_harden2/run.sh up webcam mock.
  Confirm the session lands in /root/groundstation/logs/sessions/. Confirm run.sh score and show read it.
- After B: full test suite + bench again. Grep the LIVE trees and LIVE benches for dead-tree references.
  Expect none (the cruft campaign scripts that named integration_harden are now in archive/).
- After F: git ls-files | git check-ignore --no-index --stdin returns empty.
- Phase 2: annotate a real frame, run the ingest script, confirm datasets/vision/<set>/ and valid COCO.

## Open items for your review

- None outstanding. Every decision above is owner-ruled. Bench campaigns: scripts and numbers stay, raw
  data is staged for deletion (G5). Masks: deferred now, re-opened as a roadmap item after freeze.
