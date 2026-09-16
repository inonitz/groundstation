# Track 2 execution draft (2026-09-10, rev 5) — the system, owner + this session

DRAFT to react to. Track 2 is the voice-drone system itself. Track 1 (the tracker) is a separate
subagent. Each step has a definition of done, how we verify it, and who runs what. The owner runs every
boot and every git write; the agent prepares, scores, and edits code.

Terms:
- "harden" = a DEAD intermediate fork: the old multi-model chain, entirely uncommitted, missing every
  fix from today (no counting/lexicon/cap/gate), so it carries the count jitter, the 3-draw cap and the
  mistranslations we fixed. It is NOT a fallback and NOT worth freezing. The real frozen fallback is
  projects/integration/ (CLAUDE.md) — the English proven demo. We do not maintain a second Hebrew tree.
- "harden2" = the ACTIVE system. Feature work lands here UNTIL it passes an outdoor field test; that
  tested version is then FROZEN as the validated baseline (a git tag). Later features branch off the
  baseline and must be re-validated before the next freeze.
- "routing" = harden2's single Gemma call choosing the action (mission / highlight / count / describe /
  reject) and planning it. "Routing verification" = proving that on the 488 bench + live; a negation
  that flies is a routing failure, so the negation guard is part of that gate.
- "final system" = harden2 with today's perception fixes AND the negation guard in. That is what we
  outdoor-test and freeze. Nothing may change its runtime behavior after the test without a retest.

## Step 1 — verify today's perception fixes on the webcam (indoor, now)
- Owner runs: MVD_HOME=integration_harden2 SCENE_HL_REL=0.45 VIDEO=webcam WEBCAM_DEV=2 bash tools/desk-test/up.sh
- Agent watches the app log and scores. Done when: "mark all the cars" draws many, count is stable, the
  lexicon fixes drawers/screens, no crash. No drone.

## Step 2 — harden2: save, add the negation guard, verify routing, commit
- 2a SAVE FIRST: harden2 is UNTRACKED. Agent prepares the git add/commit; owner runs it.
- 2b Negation guard (feature, before the commit): a deterministic rule refusing action-negations before
   the model. r_neg4 "בלי להסתובב בבקשה" flew two spins live. Positives fire, adversarial negatives do
   not, zero false fires.
- 2c Routing verification WITH the guard: MVD_HOME=integration_harden2 python3
   tools/bench/hebrew-command-bench/unified_bench.py. Done when: >= 415/466, no wrong-route regressions,
   zero unsafe flips, negations refuse. Estimate first, full table after.
- 2d Live routing pass on the webcam incl. negations. Owner boots, agent scores.
- 2e Commit harden2. This is now the candidate FINAL system for the outdoor test.

## Step 3 — outdoor validation of harden2, then freeze the validated baseline (owner ruling 2026-09-10)
- Field-test the final system on the real drone, outdoors, human-run, until it works well outside.
  Drone-gated, so it happens whenever conditions and batteries allow.
- Done when: it performs well outside. THEN freeze that exact commit as the validated baseline (tag it).
- This is BEFORE the cleanup, on purpose: the outdoor test must validate the final system, not a
  reshuffled one.

## Step 4 — repo cleanup / restructure (must be behaviour-preserving for harden2)
- Per docs/active/2026-09-09-repo-cleanup-draft.md: commit the remaining trees and docs in reviewed
  chunks, archive superseded docs, confirm .gitignore, decide the llm_to_action seven, propose the
  branch model. Owner runs every git write.
- CONSTRAINT: the cleanup must NOT change harden2's runtime behaviour. Moving files, committing, and
  archiving docs are fine. If any change touches harden2's code or behaviour, the frozen validation no
  longer reflects tested code, and we RETEST harden2 outdoors and re-freeze. Owner ruling 2026-09-10.

## Step 5 — noise and low-light benchmarks (after the cleanup)
- 5a whisper-Hebrew noise e2e: reuse the mixer + gunfire beds; SNR sweep; accuracy-vs-SNR curve. No
   denoiser research (raw wins, proven for Parakeet).
- 5b low-light image benchmark for SAM3: labelled image sets at varying light, scored like the clips.

## Step 6 — new features (branch from the validated baseline; re-validate before the next freeze)
- 3.1 vision-conditioned action: mark a target, then approach it or pass an opening.
- Operator-mission context: model the operator's mission and phase, not just recent dialogue.
- Military slang.

## Step 7 — fuse llm_to_action with integration_harden2 (eventual, big)
- The C++ llm_to_action engine is the destination product. Fold harden2's Hebrew voice + guard + SAM3
  layer onto it. Scope as its own tracker project when we get there.

## Order and dependencies
1 indoor, now. 2 next; 2a urgent (unprotected fork), guard before the commit. 3 outdoor validation +
freeze the tested commit, BEFORE cleanup. 4 cleanup, behaviour-preserving or retest. 5 benchmarks after
cleanup. 6 features off the baseline. 7 the fusion, last. Invariants: temperature 0, one model on the
GPU, full tables, owner runs boots and git.
