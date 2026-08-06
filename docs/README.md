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

- **`specs/`** — durable design specifications (the "what and why" of a subsystem, approved before
  implementation).
- **`plans/`** — implementation plans (the step-by-step "how" derived from a spec).
- **`handoffs/`** — dated session artifacts: context handoffs between working sessions, ready-to-paste
  prompts, and git ledgers. The newest handoff is the live starting point; older ones are archive.
- **`reference/`** — miscellaneous durable reference notes (e.g. hardware SDK notes).

## `ARCHITECTURE.md`

[ARCHITECTURE.md](ARCHITECTURE.md) is the FMU architecture specification and the source of truth for
the FMU's internal design. `ROADMAP.md` and `NOTES.md` track status and history; `ARCHITECTURE.md`
tracks structure.
