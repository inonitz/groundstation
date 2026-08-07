# docs/

Project documentation, organized by purpose.

## Start here

- **[ROADMAP.md](ROADMAP.md)** — the consolidated recursive objective tree with status and a rough
  time estimate. The single index of what is done, in progress, and planned. Read this first.
- **[NOTES.md](NOTES.md)** — the running development log: SITL debugging, control-law iteration
  history, and design decisions, newest at the bottom. Per `CLAUDE.md`, major decisions are recorded
  here.
- **[project_overview.md](project_overview.md)** — an external, advisor-facing briefing of the
  system and the two navigation approaches ("Being A" dead-reckoning now, "Being B" SLAM later).

## Folders

Session/task artifacts are filed by lifecycle state:

- **`scheduled/`** — not-yet-started work: implementation plans (the step-by-step "how" derived from
  a spec) and ready-to-paste handoff prompts for a future session.
- **`active/`** — in-progress work: handoffs for tasks that are partially done with pending items
  (currently: GO visual-servoing redesign, `2026-08-05-go-controller-visual-servo.md`
  (ROADMAP 5.2); safety-first + housekeeping planning, `2026-08-06-safety-and-housekeeping-
  planning.md` (ROADMAP block 6, build.sh/build.ps1 reconciliation, README staleness)). The
  2026-08-06 docs/code discrepancy remediation (30 confirmed mismatches) that previously lived
  here is done -- all groups resolved and folded into ROADMAP/ARCHITECTURE/NOTES, task file
  deleted per the `closed/` convention below.
- **`closed/`** — finished work: completed session handoffs, git ledgers, and closed-out reports.
  Kept only long enough to fold their findings into NOTES/ARCHITECTURE/ROADMAP, then deleted
  (git history is the permanent record, not this folder).
- **`specs/`** — durable design specifications (the "what and why" of a subsystem, approved before
  implementation). These are not task state; they outlive any single task.

Bucket membership reflects *current* status, not what a dated doc claims -- a handoff frozen at
"Task 4 not started" moves to `closed/` once ROADMAP/ARCHITECTURE confirm it landed later. Cross-check
against those two before trusting a task doc's own text.

## Loose reference notes

- **[tello_backend_notes.md](tello_backend_notes.md)** — Tello SDK notes (ports, state-string
  parser, video pipeline, frame decision) backing the `TelloBackend`.

## `ARCHITECTURE.md`

[ARCHITECTURE.md](ARCHITECTURE.md) is the FMU architecture specification and the source of truth for
the FMU's internal design. `ROADMAP.md` and `NOTES.md` track status and history; `ARCHITECTURE.md`
tracks structure.
