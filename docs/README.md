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

- **`tasks_todo/`** — not-yet-started work: implementation plans (the step-by-step "how" derived from
  a spec) and ready-to-paste handoff prompts for the next session.
- **`tasks_wip/`** — in-progress work: handoffs for tasks that are partially done with pending items
  (e.g. PX4Backend extraction Task 4 / ENU seam, visual-servoing redesign).
- **`tasks_closed/`** — finished work: completed session handoffs, git ledgers, and closed-out
  reports kept as archive.
- **`specs/`** — durable design specifications (the "what and why" of a subsystem, approved before
  implementation). These are not task state; they outlive any single task.

## Loose reference notes

- **[tello_backend_notes.md](tello_backend_notes.md)** — Tello SDK notes (ports, state-string
  parser, video pipeline, frame decision) backing the `TelloBackend`.

## `ARCHITECTURE.md`

[ARCHITECTURE.md](ARCHITECTURE.md) is the FMU architecture specification and the source of truth for
the FMU's internal design. `ROADMAP.md` and `NOTES.md` track status and history; `ARCHITECTURE.md`
tracks structure.
