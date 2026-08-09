# A1 — Live-system sandbox + headless SITL runner (capture to file)

**Status:** scheduled / not started. **Created:** 2026-08-10. **Branch:** feature-llm-driver (SITL showcase).
**Depends:** none — do this FIRST, it unblocks CI for every other spec. **ROADMAP:** 8.6, 9 (test-capture debt).
**Lock:** touches `scripts/test/lib/sim_core.sh` only; no `fmu_node.hpp`.

## Objective
Two things, one substrate. (1) A live full-system launch so a human can drive the real stack — Gazebo
+ FMU + VLM + perception — with a free-form objective and manual interrupts, and record it. (2) A
headless runner that executes every canned scenario, captures FMU stdout **to a file** (not tmux
scrollback), asserts pass/fail, and reports — the human out of the loop for regression.

## Scope
- **In:** `scripts/sandbox/run.sh`, `scripts/test/run_all.sh`, a `--log-file` sink in `sim_core.sh`
  so every run tees FMU stdout to `captured_*.log` deterministically. `run_all.sh` iterates the
  scenario dirs, runs each headless, invokes its `filter.sh`, aggregates a JUnit/summary, returns
  nonzero on any failure.
- **Out:** new features, prompt changes. Pure harness.

## Files
- `scripts/sandbox/run.sh` (new), `scripts/test/run_all.sh` (new), `scripts/test/lib/sim_core.sh`
  (tee stdout), optional tiny FMU flag if stdout buffering hides late lines.

## Tests to create
- **[AUTO]** `run_all.sh` itself is the test rig: green across the existing 20 scenarios, headless,
  exit code reflects pass/fail. This is what kills the "false FAIL on rerun" tmux artifact.
- **[AUTO]** sandbox self-check: launches all nodes, records a bag, exits clean.

## Acceptance
`run_all.sh` reproduces the 20-test matrix with zero human watching, capturing to files. Sandbox
brings the live stack up and records a replayable bag.

## Agent notes
Highest leverage, no lock contention. Whoever takes this unblocks fully-automated regression for A2–A4
and B1/B3. Land it before the others start asserting.
