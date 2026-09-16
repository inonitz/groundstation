# Repo cleanup and restructure — DRAFT for owner approval (2026-09-09)

Status: DRAFT. Nothing here is done. The human runs every git command. This is a proposal to react to,
not a finished plan. Numbers are from `git status` on 2026-09-09.

## The mess, stated plainly
1. The whole integration_harden2 tree is UNTRACKED in git. Today's work and the entire fork live only
   in the working directory. A stray `git clean` or a bad checkout deletes all of it. This is the
   single biggest risk right now.
2. Two near-duplicate trees, integration_harden and integration_harden2, with parallel code.
3. Everything else is uncommitted too: ~75 changed files under docs/active/assets, ~34 under the
   Hebrew bench, ~22 under integration_harden, plus desk-test, diagrams, devenv.
4. Code, results, and generated artifacts are mixed together. Some results are already gitignored;
   many diagram PNG/SVG/drawio files are tracked and heavy.
5. Live and stale docs sit side by side. docs/stale and docs/active both hold current-sounding files.
6. Seven llm_to_action files are modified but belong to a different lane.

## Target shape
- One primary system: integration_harden2. integration_harden is frozen as the labelled fallback.
- Code separate from data. Results, sessions, traces, overlays, bench_out stay gitignored.
- Docs in three buckets: active (current), research (investigations), archive (superseded, dated).
- Artifacts (diagram exports, slides) in an assets area, with the source (.dot, .md) tracked and the
  heavy exports either tracked deliberately or generated on demand.

## Proposed order of work
1. SAVE FIRST. Get integration_harden2 into git before anything else, so it cannot be lost. Review the
   diff, then commit the tree. This is step one of "close down harden" as well.
2. Commit integration_harden's changes as its own reviewed commit (the recognizer, kill switch, run
   scripts). It is the fallback; freeze it after this.
3. Commit the bench, desk-test, diagrams, devenv, and docs changes in separate reviewed commits, so
   history reads cleanly.
4. Move superseded docs to docs/archive/ with their date. Leave a one-line pointer where they were.
5. Confirm .gitignore covers every data path: sessions/, traces/, results overlays, bench_out,
   docs/private. Most already are; verify none slipped.
6. Decide the llm_to_action seven: commit on their own lane or revert. Owner call.

## Proposed commit sequence (SUGGESTED; the human runs these after reviewing each diff)
```
# 1. save harden2 first (currently untracked = at risk)
git add projects/integration_harden2
git commit -m "feat(harden2): single-model Gemma chain + SAM3 eyes, first real flight"
# 2. harden fallback changes
git add projects/integration_harden
git commit -m "feat(harden): recognizer + kill switch + run-script updates; freeze as fallback"
# 3. benches
git add tools/bench/hebrew-command-bench tools/bench/hebrew_asr tools/bench/whole-system
git commit -m "bench: Hebrew command corpus (+75 cases), ASR + whole-system harness updates"
# 4. desk-test + diagrams + devenv
git add tools/desk-test tools/dji_mock/watch_503.sh tools/diagrams tools/devenv
git commit -m "tooling: desk-test run sheets + scorer, diagram exporter, runtime-deps installer"
# 5. docs
git add docs/active docs/NOTES.md docs/ARCHITECTURE.md docs/research .gitignore
git commit -m "docs: session state, reorientation, challenge form, research notes"
```
Note: docs/private is gitignored and never staged. The llm_to_action seven are not in any command
above; decide them separately.

## Branch and process (owner raised; proposal, not decided)
- master stays the proven line. Feature work on short-lived branches, merged after review.
- A "dev" or "experiments" branch for benches and throwaway runs, never merged wholesale.
- CI later: run the harden2 test suite and the recognizer bench on push. Only after the trees are
  committed and stable; not now.

## Not in this cleanup
- Merging harden and harden2 into one tree. That is a design decision, not cleanup. Later.
- The task tracker. Pinned.
