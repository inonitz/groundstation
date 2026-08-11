# Documentation & feature-sync handoff — 2026-08-10

Cold-start brief for whoever picks up documentation/folder-sync work next. Written after the outgoing
session made several real mistakes on this exact task — read the "What went wrong" section before
trusting anything else in this repo's docs at face value, including this file.

## Rule zero: don't inherit conclusions, re-derive them

Every mistake below happened the same way: trusting a prior summary (mine, or a doc's own claim)
instead of checking `git log`/`git status`/the actual file. Do not propagate any status claim —
"done," "scheduled," "verified" — without confirming it against source. That includes this document's
own claims below; they were true at the moment of writing, verify again before acting.

## What went wrong this session (so the pattern doesn't repeat)

1. **Called B2/B4 "done" based on their code landing, not their actual acceptance criteria.** Both
   specs' real acceptance is hardware-verified bring-up/calibration; only the code prerequisite had
   shipped. Corrected: both now sit in `docs/scheduled/`, not `docs/closed/`.
2. **Misread a flight log on first pass.** Read `scripts/test/colors/captured_panes_log.txt`'s tail,
   saw APPROACH diagnostic lines, assumed normal flight. The drone had never taken off (`altENU` never
   exceeded 0.06m the entire run) — only caught on a second, deliberate pass checking `altENU`/`arm=`
   directly instead of pattern-matching on log lines that merely looked like flight. Root cause (a VLM
   plan that queued `takeoff` third, behind `search`/`approach`) is now documented in `docs/NOTES.md`.
3. **Fixed doc *content* without checking doc *placement*, twice in a row.** Corrected six stale claims
   across `ROADMAP.md`/`NOTES.md`/spec files, but left three agent-prompt files sitting in `docs/active/`
   describing already-finished work. Told to move them; moved two of them to the wrong folder the first
   time the check was actually run.
4. **A live collision, caught just now:** two files this session moved to `docs/scheduled/` were found
   sitting in `docs/closed/` instead minutes later, with a timestamp predating the move. Nobody on this
   side did that — it happened from a concurrent process (see next section). Moved back, but it means
   **docs/ has no coordination mechanism**, unlike source files (`docs/LOCKS.md`).

## Correction (2026-08-10, later pass): the "concurrent agent" claim above was wrong

There is no other agent. Both uncommitted diffs are this same lineage's own unfinished work,
already written up in `docs/NOTES.md`, just not yet committed:
- `dependencies/rubicon_colors.sdf` — swaps the plain `hatchback` (confirmed blue, same as
  `hatchback_blue`, not a valid two-color test) for OpenRobotics' "Hatchback red" via an explicit
  Fuel URI. See NOTES.md "Lightweight color-discrimination SITL showcase," 2026-08-10 update.
- `fmu_node.hpp`/`fmu_node_base.hpp`/`llm_base.hpp` — this is the **SEARCH size-presets** feature
  (`SearchSizeParams`, `kSearchSizePresets[small/medium/large]`, new `search_size` plan field),
  documented in NOTES.md's "SEARCH size presets (2026-08-10)" section. It is **not** the
  takeoff-ordering fix. That fix is a *different*, separate item — per NOTES.md's own
  "SEARCH-then-APPROACH-before-TAKEOFF bug" entry it is explicitly **not yet built** ("design
  agreed, ready to implement"), so it cannot be sitting in this diff. Also: `docs/LOCKS.md` shows
  every file `FREE` as of today's refresh, which by itself should have ruled out "someone else is
  editing this" before writing the claim.

Do not repeat rule zero's mistake on a document that exists specifically to enforce rule zero:
verify a claim like "another agent is touching this" against `git log`/`docs/LOCKS.md` before
writing it down, not after.

## Verified state as of 2026-08-10 ~02:00 UTC

Branch `feature-llm-driver` @ `3ff2771`, in sync with origin. `feature-calibrate-slam` already merged.

`docs/active/` (needs attention now):
- `2026-08-09-manager-session-handoff.md` — aging, written before today's merge + fixes; not yet
  superseded by a newer one. Consider whether a fresh handoff should replace it.
- `2026-08-10-tello-physical-handoff.md` — real, from tonight (confirmed via `git log`, despite the
  filename originally saying 08-09 — already corrected).
- `2026-08-10-audit-findings.md` — banner added pointing to what's resolved; see that file.
- `2026-08-10-poc-status.html`, `sitl-2026-08-09-wave1-testing-runbook.md`, `sitl-B1-task5-agent-prompt.md`
  (B1 Task 5 is done; left as-is pending a human call on the `closed/` move),
  `sitl-tello-2026-08-08-slam-tello-bringup.md` (banner added, see that file).
- **Also missed by this doc entirely, found on a later pass:** `2026-08-07-poc-tasklist.md`,
  `2026-08-07-spec-1-interrupt-reactive-safety.md`, `2026-08-07-spec-2-movement-command-laws.md` —
  all three fully `[DONE]`/SITL-verified (confirmed against `docs/ROADMAP.md` 1.5/6.1/6.3/6.4 and
  1.1.6/1.1.7), same vintage and same finished state as `spec-3`/`spec-4` which were already sitting
  in `docs/closed/`. Moved to `docs/closed/` to match; spec-1's own top-of-file `Status:` line was
  also stale ("unassigned (for a spawned session)") despite its own bottom section reading
  "IMPLEMENTATION COMPLETE" — fixed. This is exactly the "fixed content, missed placement" mistake
  pattern #3 above describes, happening a second time on files this document itself never looked at.

`docs/scheduled/` (correctly deferred, confirmed against actual completion state, not just claims):
- `tello-B2-agent-prompt.md`, `tello-B4-agent-prompt.md`, `sitl-tello-B3-agent-prompt.md` — real Tello
  work, blocked on hardware access / calibration / B1's marginal SLAM result respectively.
- `sitl-2026-08-10-spec-A2/A3/A4...md` — SITL showcase extras, not started. A3 got a stale-line-number
  warning added to it this session (`fmu_node.hpp` has grown); still not started otherwise.
- `tello-2026-08-10-spec-B5...md` — depends on B4, which is itself not done; correctly still deferred.

`docs/closed/` — 10 items, several finished specs plus 2 superseded handoff/status docs. Per
`docs/closed/README.md`'s own rule this folder is meant to be transient (fold into `NOTES.md`/
`ROADMAP.md`, then delete) — nobody has done that pass yet; it's accumulating.

## Concrete open items for documentation/feature sync

1. Decide `2026-08-10-audit-findings.md`'s fate — fold into `NOTES.md`/`ROADMAP.md` per repo
   convention, then delete, rather than let it sit indefinitely.
2. Rewrite or banner `sitl-tello-2026-08-08-slam-tello-bringup.md` — its framing is out of date.
3. Decide whether `sitl-B1-task5-agent-prompt.md` should move to `closed/` (B1 Task 5 is done, but
   with marginal results — worth a human call, not an automatic move).
4. `docs/closed/` housekeeping pass — fold-and-delete per its own README, hasn't happened yet.
5. No lock/coordination mechanism exists for `docs/` the way `docs/LOCKS.md` covers source files —
   worth deciding whether that's needed given finding #4 above actually happened, not hypothetically.
6. Do not touch anything under active investigation by the other agent (see "Known concurrent
   activity") without checking with the human first.

## Where the real technical detail lives (don't re-summarize it, point at it)

- `docs/NOTES.md` — the authoritative, evidence-based technical log. Longest but most reliable single
  source in this repo; every claim in it is backed by a command/log excerpt, not asserted.
- `docs/ROADMAP.md` — status tracker; was stale in one place this session (7.1), now corrected, but
  treat any single line as a claim to spot-check against `NOTES.md`/code, not a settled fact.
- `git log --oneline` on `feature-llm-driver` — the actual sequence of what shipped; commit messages
  in this repo are unusually detailed and trustworthy (house style enforces intent-first, `|`-separated,
  no fluff — read them before reading anyone's summary of them, including this one).
