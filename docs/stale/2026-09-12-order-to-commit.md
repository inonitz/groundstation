# harden2: ordered sequence to the commit (2026-09-12)

Supersedes the ordering in 2026-09-09-project-state-and-reorientation.md §7 TRACK 2. That plan said
"commit harden2 first (untracked = at risk)"; the owner ruled 2026-09-12 that NOTHING commits until field
testing passes. So the commit moves to the end: prove it works live, make it clean, prove it still works,
then commit and freeze.

RISK FLAG: everything below is uncommitted and projects/integration_harden2/ is UNTRACKED. If the box dies,
it is gone. The owner accepted this by deferring the commit. De-risk without a "real" commit if wanted: a
tarball of the tree, or a throwaway WIP commit on the branch to amend later. Owner's call.

## DONE this session (offline-verified; the baseline we are about to test live)
- Negation guard A1-A7: subtract rule + 24 refuse / 25 pass adversarial set; bench 410/487, 0 regression.
- Config merge: config_constants + config_defaults + config.py adapter; mvd knobs sourced from them;
  golden-master 2/2; behaviour-preserving.
- Perception capture: each query saves frame + SAM3 dets + result to <session>/perception/.
- Session folder symmetry: asr/ + perception/; reader tools fall back to the old layout.
- Dead-code purge: OmDet, SAM2, DictaLM/Hy-MT2 translators, Qwen3-VL removed; YOLO26 background KEPT.
- Gates green: 60 offline tests, bench 410/487, golden-master, all modules import.

## PHASE 1 — live validation of the CURRENT state (cheapest first)
1. WEBCAM desk test (no drone). Validates boot, perception (draw-all, SAM3 gate, lexicon, count median),
   the config wiring, the purge, and the perception capture on real frames. Never run with these changes.
2. Fix whatever the webcam surfaces.
3. FIELD test (drone). Validates the control path, real video, flight, and the capture recording outdoors.
4. Fix whatever the field test surfaces.
   -> Exit: a PROVEN-WORKING baseline.

## PHASE 2 — quality (on working code only)
5. Nuclear code review: background Opus 4.8 subagent, quarter-progress reports, writes its own report to
   docs/active. Held until Phase 1 passes (owner permission already given).
6. Triage + apply the review's structural fixes (behaviour-preserving; agent proposes, owner approves).
7. Repo cleanup finalize: the cleanup draft (2026-09-09-repo-cleanup-draft.md), README scorecards to
   current state, the STALE recognizer-bench skill (retarget to harden2 or retire), and the deferred purge
   items (prompts.py TRANSLATE_*/TGEMMA_*/WIRE_GRAMMAR/LINE_GRAMMAR + recognizer.recognize()).

## PHASE 3 — re-validation (the restructure must not have broken anything)
8. Re-run the offline gates: bench 410/487, 60+ tests, golden-master.
9. Re-test live: WEBCAM (mandatory), FIELD if the Phase-2 changes are non-trivial.
   -> Exit: proven-working AND clean.

## PHASE 4 — commit + freeze
10. Owner git rm the 6 orphaned dead files (2 translator servers + perception2/{detectors,engine,
    vlm_client,chain_demo}.py). List + commands in 2026-09-11-harden2-deadcode-purge.md.
11. Owner commits EVERYTHING (house-style messages drafted this session, refreshed for the final diff).
12. FREEZE harden2 — owner declares it closed / merge-ready (the components rule: no freeze until the owner
    says so). Then integration_harden (the dead intermediate) can be dropped; integration/ stays the frozen
    English fallback.

## Parallel, not a commit blocker
- TRACK 1: stand up the self-hosted tracker (OpenProject) on the workstation; a SEPARATE subagent session
  (kickoff in 2026-09-10-track1-tracker-handoff.md). Owner-driven, any time.

## AFTER the commit (out of scope for this gate; seed as tracker projects)
- Whisper-Hebrew noise e2e benchmark + the low-light SAM3 image benchmark.
- Big projects: 3.1 vision-conditioned action (mark -> approach/through), operator-mission context, slang.
- llm_to_action fusion + the fmu cleanup tasklist (a separate system; its own handoffs).

## PLAN CHANGE 2026-09-12 (owner): field test DEFERRED, cleanup moved to NOW
- Owner ruled: do the cleanup FIRST, then test the (smaller) issues. No field test before cleanup.
- New order: (1) delete redundant files [git rm list in 2026-09-11 purge doc + the superseded launcher scripts],
  (2) deferred code purge (prompts.py TRANSLATE_*/TGEMMA_*/WIRE_GRAMMAR/LINE_GRAMMAR, recognizer.recognize()),
  (3) retarget the stale recognizer-bench skill (integration_harden -> integration_harden2), (4) README scorecards,
  (5) webcam test + fix the small issues (SAM3 0.1-floor zero-ground, count-median cache), (6) commit + freeze.
- Rationale: issues surfacing should be small, not large refactors. The large refactors (mvd split, run.sh) are done.
