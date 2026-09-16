# harden2 commit manifest — what is in the tree, what to commit (2026-09-12)

Purpose: preserve the full change inventory for the COMMIT stage (Phase 4 of 2026-09-12-order-to-commit.md).
The commit is deferred until after field testing; this file is the reference for WHAT gets committed and
what does NOT. Ground truth: `git status` + file mtimes on branch feature-hardening-mvd, captured 2026-09-12.

## Scope reality
`git status`: 50 modified tracked + 113 untracked = 163 changed paths. MOST are NOT from this session.
"Commit everything" as one blob would be wrong. Split it (see the three buckets below).

## BUCKET A — this session's harden2 work (the coherent commit)
### projects/integration_harden2/ (UNTRACKED whole fork — at risk until committed)
- recognizer/recognizer.py   : negation_only subtract rule + continue/slow/speed verbs; `he = he or ""`
                               None-guard in recognize_direct (bug found + fixed this session).
- recognizer/pipeline.py      : rewritten to the DIRECT path only; removed handle_translated/_translate/
                               _plan/plan_fn/dicta_port/DIRECT/MISSION_KEYS/REJECT_PREFIX.
- recognizer/llama.py         : MODELS -> gemma4 only; QWEN3VL_EXTRA removed.
- config_constants.py         : completed superset (ports, perception, camera, watchdog, speech, colors).
- config_defaults.py          : completed; video_input()/wire_target() derivers + host resolvers.
- config.py                   : rewritten to a thin adapter sourcing from the two config files.
- mvd.py              : perception capture (capture_perception + 3 hooks); asr/ session layout;
                               removed _translate wrap + OmDet import + omdet branch; OM name "SAM3";
                               knobs sourced from the config files; header rewritten.
- perception/detectors.py     : Eyes-only (YOLO26 background KEPT); OmDet class + SAM2 methods removed.
- perception/engine.py        : stale OmDet/SAM2 comments fixed.
- perception2/__init__.py     : trimmed to live exports (Sam3Backend + concept + counting).
- run_mvd.sh                  : asr/clips layout; translator/xlate/qwen/omdet options + SCENE_SAM2 removed.
- test/test_negation_guard.py : grown to 24 must-refuse + 25 must-pass.
- test/test_config_golden.py  : NEW golden-master (config merge behaviour-preserving).
- test/capture_golden_config.py + test/golden_config.json : NEW B1 golden capturer + baseline.
- test/test_perception_capture.py : NEW recorder + thread-driver tests.
- test/test_recognizer.py     : reduced to the active R.* tests (dead translated-path cases removed).
- test/test_scene_wiring.py   : rewritten to the direct path (plan2 fake); omdet test removed.
- OWNER must also `git rm` 6 orphaned files: recognizer/run_dicta_server.sh, recognizer/run_hymt2_server.sh,
  perception2/{detectors,engine,vlm_client,chain_demo}.py (zero live importers; see the purge doc).

### Collateral this session (tracked, belongs with the harden2 commit)
- tools/bench/hebrew-command-bench/bench.py        : qwen3vl PLANNERS entry removed (collateral of llama).
- tools/bench/hebrew-command-bench/README.md       : scorecard -> unified 410/487 + negation-guard para.
- tools/bench/hebrew-command-bench/results/2026-09-11-negation-guard{,-a7,-final}.* + purge-stage1.* : runs.
- tools/bench/whole-system/run_list.py, tools/bench/hebrew_asr/gemma_asr.py,
  tools/desk-test/{show_session,score_session,score_live}.py : asr/ layout fallback helper.
- tools/desk-test/up.sh + preflight.sh : MVD_HOME fork-selector DELETED (owner ruling); launchers hardcode
  integration_harden2; CLIPS_SUB=asr/clips; preflight TRANSLATOR=none.
- tools/desk-test/up.sh : clips path made conditional (harden2 -> $SESSION_DIR/asr/clips) so the asr/
  folder change is consistent end-to-end; integration_harden keeps flat clips/. run_mvd.sh banner H->F5.

### Docs + memory this session
- docs/NOTES.md (guard/config/purge/static-analysis bullets); docs/active/2026-09-10-guard-and-config-workplan.md
  (A5/A6/A7 + Workstream B); docs/active/2026-08-30-cleanup-takeover-audit.md (B1 capture-half annotation);
  NEW: docs/active/2026-09-11-harden2-deadcode-purge.md, 2026-09-12-order-to-commit.md, this manifest.
- Entry-point fixes (start of session): 2026-09-09-project-state-and-reorientation.md §8, 2026-09-08-session-handoff.md §18.
- memory/: current-work-and-entry-point.md + MEMORY.md (updated repeatedly).

## BUCKET B — pre-existing uncommitted pile, NOT this session (needs its own ruling)
- projects/integration_harden/ : the DEAD intermediate fork, heavily modified + tracked (~20 files). Decide:
  commit as-is, or drop (it is being retired). Do NOT bundle it into the harden2 commit unthinkingly.
- tools/devenv/ (Dockerfile, install-runtime-deps.sh), tools/desk-test/{up,down,preflight,status}.sh,
  .gitignore, docs/ARCHITECTURE.md : earlier uncommitted work; separate concern from harden2.
- ~30 untracked docs/active/ files (architecture diagrams, handoffs, llm_to_action reports) and the
  untracked .claude/skills/diagram-authoring/ skill : separate; the owner decides what lands.

## BUCKET C — recent files I did NOT create in this conversation (CHECK ORIGIN before committing)
Timestamps 2026-09-11 23:47 -> 2026-09-12 00:39, during/after my work; no record of authoring them here.
Possible concurrent session (inference, not known):
- docs/active/assets/skill-ab-test/ (run_ab.sh, NOTES.md, baseline/run.json, with-skill/run.json)
- docs/active/2026-09-12-ab-baseline-prompt.md, 2026-09-12-ab-withskill-prompt.md
- memory/isolate-confounds-and-pin-model.md, always-use-rtk-wrappers.md, llm-to-action-parked-behind-harden2.md
- a MEMORY.md edit at 00:39, a 2026-09-10-llm-to-action-demo-handoff.md touch at 00:12
Do not commit these as "harden2 work" without confirming what they are.

## Verification state of Bucket A (the commit is gated on field testing, not on these)
60 offline tests pass; unified_bench 410/487 with 0 changed cases (tags negation-guard / -a7 / -final /
purge-stage1); golden-master 2/2; mvd/config/perception2/Pipeline all import. NOT yet run live.

## ADDENDUM 2026-09-12 (mvd split)
- NEW: projects/integration_harden2/overlay.py (chat-pane renderer, extracted from mvd)
- NEW: projects/integration_harden2/session_log.py (SessionLog + reject_why, extracted)
- NEW: projects/integration_harden2/test/test_crash_safety.py (recording durability)
- CHANGED: projects/integration_harden2/mvd.py (899->548; imports overlay + session_log)

## ADDENDUM 2026-09-12 (rename)
- RENAMED: projects/integration_harden2/scene_omdet.py -> mvd.py (git mv for the human). References updated
  across run_mvd.sh, up.sh, down.sh, status.sh, preflight.sh, tests, and perception/recognizer/control/video modules.

## ADDENDUM 2026-09-12 (self-contained launcher)
- NEW: projects/integration_harden2/run.sh (up|down|status|preflight; replaces the desk-test launch layer)
- NEW: projects/integration_harden2/cam_list.py (copied from tools/desk-test/list_cams.py)
- SUPERSEDED -> git rm: tools/desk-test/up.sh, down.sh, status.sh, preflight.sh ; projects/integration_harden2/run_mvd.sh
- KEPT (analysis/prep, not launch): tools/desk-test/{score_session,score_live,show_session}.py, quantize_hebrew_asr.sh, *.md
