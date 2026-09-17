# Working journal — owner directives + status (CHECK THIS FIRST after any compaction)

Rule (owner 2026-09-17): every point the owner makes is logged here with a status
(DONE / NOT DONE / IN PROGRESS / PARKED / STANDING). Address all; skip none. When the owner
makes new points, append them here before acting, then update status as you go.

## STANDING RULES (always apply)
| # | Rule | Status |
|---|---|---|
| S1 | Owner runs ALL git writes; agent prepares exact commands only | STANDING |
| S2 | Commits: multiple thematic commits, never one aggregated | STANDING |
| S3 | Questions go in the session/chat, not scattered in docs | STANDING |
| S4 | Maintain this journal; address every owner point, none skipped | STANDING |
| S5 | Field test is low-stakes -> do the full cleanup, not just docs | STANDING |

## OPEN TASKS (not finished)
| # | Task | Status | Detail |
|---|---|---|---|
| T1 | CONFIG PACKAGE: make projects/integration_harden2/config/, move the 3 config files in; EVERYTHING routes through config.py only (C-header surface); no module imports _K/_D internals; fix mvd.py bypass + hardcoded ports (pipeline/concept/phone_asr) | NOT DONE | Spec in task-active-cleanup-plan.md RESUME STATE (OPEN TASK 1). Owner ruled option A. Gate: 66 tests + test_config_golden + import-smoke |
| T2 | OVERLAY chat-tagging: tag chat rows (role,text,kind); overlay switches on kind (no string round-trip). GUI check = owner-approved screenshot method: run GUI with 1-3 Hebrew sentences, screenshot only the mvd window, change, re-shot, agent diffs the two images -> expect ZERO visual change | NOT DONE | task-active-cleanup-plan.md OPEN TASK 2 |
| T3 | Commit the verified cleanup | NOT DONE | Regenerate the multi-commit git batch; includes git rm run_mvd.sh + video/video_doctor.py |
| T4 | e2e / whole-system bench (bench/whole-system/*) broken by translator retirement | PARKED | Reconstruct AFTER the system is finished (recording + accuracy). Owner: odd to measure an unfinished system |

## DONE this session (verified: 66 tests green; recognizer bench 410/487 unchanged)
| Item | Status |
|---|---|
| Dead-file deletes (perception2 x4, run_router, ws_latency, plot_latency, compare_runs, build.ps1) | DONE (staged) |
| recognizer dead stages removed + shortened 786->479 (selftest -> recognizer/selftest.py) | DONE |
| OmDet render scaffolding + mvd vestigial removed | DONE |
| observe= recording (drop handle monkey-patch) | DONE |
| TTS Hebrew-only (phone\|phonikud\|off; crash if phonikud model missing) | DONE |
| Safety docs (CONTROL_TARGET, halt() docstring, kill MOTION) | DONE |
| power_profile pct off-by-one | DONE |
| install/devenv translator trim + sentencepiece removal | DONE |
| doc repoints (run_mvd/video_doctor/spec) | DONE |
| config intent graph (docs/config_design.png) | DONE |
| thermo + ponytail reviews + cleanup plan docs | DONE |
| REJECTED as review over-calls: MOCK_WIRE_PORT phantom, MOTION-shrink, _djiprobe, shared-bench-module | DONE (closed) |

## RECORD / POINTERS
- task-active-cleanup-plan.md  = full execution log + RESUME STATE + HANDOFF REFINEMENTS (authoritative).
- task-active-thermo-review-{integration_harden2,repo}.md, task-active-ponytail-review.md = the reviews.
- config_design.png/.svg/.dot = the config intent graph.
- Nothing committed yet; tree is a consistent, green cleanup.
