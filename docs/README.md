# docs/

- **[ARCHITECTURE.md](ARCHITECTURE.md)** -- the FMU architecture spec; source of truth for the
  C++ system's internal design.
- **[ROADMAP.md](ROADMAP.md)** -- the objective tree with status. What is done, in progress, planned.
- **[NOTES.md](NOTES.md)** -- the running development log, newest at the bottom. Major decisions
  and hard-won gotchas land here; check it before re-diagnosing anything.
- **[code-guidelines.md](code-guidelines.md)** / **[writing-style.md](writing-style.md)** -- how
  code and prose are written here.

## Folders

- **`active/`** -- live working docs: the current sprint handoff, tasklists, decision records.
  Start with the newest dated handoff.
- **`runbooks/`** -- how to run things: the MVD run guide, drone bring-up, kill-switch drill,
  demo checklists, phone build.
- **`specs/`** -- durable designs: the DJI backend, its websocket protocol, video transport,
  FMU cleanup spec.
- **`research/`** -- research artifacts: the VLM-BT reading list, ASR noise robustness, latency
  captures.
- **`stale/`** -- superseded docs kept for context; git history is the real archive.
- **`scheduled/`** -- not-yet-started plans.

Bucket membership reflects *current* status, not what a dated doc claims; cross-check ROADMAP
and NOTES before trusting an old task doc.
