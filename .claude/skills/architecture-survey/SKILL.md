---
name: architecture-survey
description: Survey the codebase for modules worth deepening, using the deletion test. Findings-only report to a file, never edits code. Use for /architecture-survey or "architecture survey".
disable-model-invocation: true
---

# Architecture Survey

A survey, not a rescue. Find shallow modules worth deepening. Never edit code; the only output is one report file.

## Scope

Bias toward recently changed code: let `git log --since='30 days ago' --name-only` decide where to look before looking. Skip `projects/integration/` (frozen) and `archive/`.

## The deletion test

A shallow module has an interface nearly as complex as what it hides: pass-through wrappers, config mirrors, one-caller helpers, abstractions that leak so callers must know internals anyway.

For each candidate ask: if this module were deleted and its callers absorbed the work, would complexity CONCENTRATE in one place (worth deepening) or merely SPREAD around (leave it alone)? Only concentrating cases enter the report.

## Labels

- **Strong** — deletion test passes clearly and the friction shows up in recent diffs.
- **Worth exploring** — plausible; payoff depends on upcoming work actually touching it.
- **Speculative** — safe to ignore; listed only so the reader knows it was considered.

## Report

Write to `docs/research/arch-survey-<YYYY-MM-DD>.md` and keep it under 150 lines. Per candidate: files involved, the friction (cite a recent commit or diff, not a vibe), a sketch of the deeper interface (signatures, no implementation), what future work it unblocks, label.

Plain language throughout. Name things by their domain role, not invented vocabulary.

## Hard limits

- Findings only. No refactoring; no file writes besides the report.
- C++ restructurings are owner-executed; mark them `[owner]`.
- If everything is Speculative, say the codebase is fine. Do not manufacture candidates to seem useful.
