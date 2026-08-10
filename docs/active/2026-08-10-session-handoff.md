# Session handoff — 2026-08-10, laptop pickup

Cold-start brief for opening a new Claude Code session on a different machine to continue this
project. Read this file first. It tells you what to read next, in order, and what not to trust
without re-checking. It supersedes `2026-08-09-manager-session-handoff.md` (bannered, not deleted —
see the note at that file's top).

## 0. Before you open Claude Code on this machine

If this is a new machine that has never run Claude Code for this user before, its `~/.claude/`
config (hooks, `CLAUDE.md`, RTK settings) may not exist yet. Bootstrap it first:

```bash
git clone <claude-dotfiles-repo-url> ~/claude-dotfiles
~/claude-dotfiles/setup.sh
```

This symlinks `CLAUDE.md`, `RTK.md`, `settings.json`, and the plugin manifests into `~/.claude/`.
It does **not** install the `rtk` binary itself — verify `rtk --version` works before trusting any
instruction below that assumes it. If `rtk` isn't installed on this machine, say so before
proceeding; don't silently fall back to native Read/Grep without checking whether the project's
`CLAUDE.md` deny-rules are even active here.

## 1. The one rule that overrides everything

**The human owns the entire git workflow.** No git writes from Claude — no `add`, `commit`,
`push`, `mv`, `rm`, `merge`, `rebase`, `reset`, `tag`. Read-only inspection (`status`, `log`,
`diff`, `show`) is fine. When work is ready, suggest the exact commands in the house commit style;
the human runs them. This is in `/root/groundstation/CLAUDE.md` and overrides any skill or
instinct that says otherwise.

Other standing rules, all still true:
- Use `rtk` wrappers for reads/greps/ls/find/git — native Read/Edit/Grep are blocked by a deny
  rule in this environment.
- Edit files via a Python heredoc (`assert s.count(old) == 1; s.replace(old, new)`) since the
  native Edit tool is blocked too.
- Prose (explanations, reports, this file) follows `docs/writing-style.md`: short sentences, one
  idea each, no bullet-hiding a sentence that should just be written clearly.
- Architectural decisions get written to `docs/NOTES.md`, not left in commit messages or chat.

## 2. What this project is, and where the truth lives

Off-board VLM-driven autonomous drone. **The VLM plans; deterministic math executes.** DJI Tello
is the real target; PX4 Gazebo SITL is the simulation fallback used for almost all testing. The
control loop is `source/llm_to_action/fmu/fmu_node.hpp`, 20 Hz, ENU frame.

Read in this order, and re-read fresh each time — do not trust a cached summary of any of these,
including this handoff, past the moment it was written:
1. **`docs/ROADMAP.md`** — the objective tree and status. Single source of truth for what's done.
2. **`docs/NOTES.md`** — the decision log. Every claim in it is backed by a command or log excerpt,
   not asserted. Long, but the most reliable single document in the repo. Read the tail first —
   it's chronological, newest at the bottom.
3. **`docs/ARCHITECTURE.md`** — system design, living spec.
4. **`docs/active/2026-08-10-poc-status.html`** — visual status dashboard, refreshed tonight.
5. `git log --oneline` on `feature-llm-driver` — commit messages here are unusually detailed
   (intent-first, `|`-separated clauses) and worth reading directly rather than summarized.

## 3. Where we actually are right now — re-verify this, don't just believe it

As of commit `fef3ce7` on `feature-llm-driver`, in sync with origin. `feature-calibrate-slam` is
already merged (`a2f1626`). Run `rtk git status` immediately — as of this writing there are
**uncommitted changes** sitting in the working tree that are real, finished work, not scratch:
`docs/NOTES.md`, `docs/ROADMAP.md`, `docs/active/2026-08-10-poc-status.html`, and
`docs/scheduled/tello-2026-08-10-spec-B5-tello-stick-calibration-wind.md` (check `rtk git diff` on
that last one specifically — it predates this handoff and its origin wasn't re-confirmed here).

**Real wins from tonight**, all live-verified, not just coded:
- Plan-parsing no longer strands the drone on a malformed VLM response (tolerant extraction, then
  a better fix: server-side JSON-schema-constrained decoding).
- SEARCH returns to its start pose on failure instead of stranding the drone, and now has
  small/medium/large size presets instead of one fixed grid.
- The model is told explicitly when a command failed (`DECISION RULE 9`), so a failure actually
  triggers replanning instead of silent repetition.
- A plan-validation gate rejects any plan that isn't airborne and doesn't open with `takeoff` —
  confirmed live, both directions (real takeoff went first; two bad plans got rejected).
- `rubicon_colors`' second car is now genuinely a different color (real "Hatchback red" model,
  confirmed loading clean) — yesterday's two-blue-cars bug is fixed.

**Two real, unresolved problems found in the very last test run tonight — read before touching
`scripts/test/colors/`:**
1. **Safety-relevant, not investigated:** APPROACH on an unmatched target produced a violent,
   uncommanded excursion (~14 m position jump, 9+ m/s velocities) instead of a safe failure, and
   left PX4 arm-state and the FMU's flight-state tracking disagreeing afterward. **Do not re-run
   `scripts/test/colors/run.sh` unattended until this is understood** — see `docs/NOTES.md`,
   "Colors POC re-verified," for the full log trace.
2. **Design gap, not a bug to retry:** `target_object` color qualifiers (e.g. `"blue_car"`) never
   match anything, because the perception pipeline only emits plain classes (`"car"`). The model
   can see and describe the color but has no field that survives into the matcher. The
   color-discrimination premise cannot work as currently wired.

**Current honest TRL: 4** (validated in a simulated/lab environment — real, repeated testing
found and fixed real bugs, but one known safety-relevant failure mode is still open and there has
been zero real-hardware flight this cycle). Full reasoning: `docs/NOTES.md`, "TRL assessment."

## 4. The deadline, and the agreed strategy

Contest demo: **Thursday 2026-08-13 morning.** Two goals: a reliable SITL showcase (must work),
and preferably a physical Tello demo with real localization (stretch). Explicit checkpoint:
**Wednesday 2026-08-12 evening** — if the SLAM staleness/fallback gate isn't cleanly working in
SITL by then, do not attempt physical-with-localization live; fall back to a physical
*non-localized* demo (takeoff/rotate/describe/land, no position dependency) instead. Full
reasoning: `docs/NOTES.md`, "Honest capacity/risk assessment for the final 3 days."

## 5. Priority order for this session

1. **Investigate the APPROACH excursion.** Safety-relevant; blocks trusting APPROACH at all until
   understood. Don't fly it unattended in the meantime.
2. **Fix color/attribute target matching.** Needed before the colors showcase means anything —
   likely a new field checked against the detection crop, not a label-string hack.
3. **Physical Tello dry tests** — `docs/active/2026-08-09-tello-physical-handoff.md`. This is the
   one thing that specifically needs this laptop; do it here, not delegated back to a sandbox.
4. **Real physical camera calibration** — tooling exists post-merge; the community intrinsics are
   provisional.
5. Review and, if it looks right, suggest the commit for tonight's uncommitted doc changes (§3) —
   check the B5 spec-file diff first, it wasn't re-confirmed in this handoff.

## 6. Documentation debt — don't add to it by accident

`docs/active/` has accumulated several handoff/audit docs this week
(`2026-08-10-documentation-handoff.md`, `2026-08-10-audit-findings.md`,
`2026-08-09-manager-session-handoff.md` now bannered). `docs/closed/`'s own README says finished
task docs should get folded into `NOTES.md`/`ROADMAP.md`/`ARCHITECTURE.md` and then **deleted** —
git history is the permanent record — but that fold-and-delete pass hasn't happened yet and is
tracked as open work in `2026-08-10-documentation-handoff.md`. Don't create a fourth overlapping
handoff doc next time without first checking whether this one just needs an update instead.

## 7. Gotchas still true

- ROTATE hang: commanded yawrate ignored for 20+ minutes, seen once, root cause unknown, no repro.
- Tello bring-up gremlins (`docs/tello_backend_notes.md`): UDP bind needs `SO_REUSEADDR`, 15 s
  auto-land unless `rc` streams at ~30 Hz, ~10-13 min battery life — charge several before a dry
  test session.
- Background test-run notifications in this environment are not reliable signals of actual
  failure — always verify via direct log/process inspection, never trust the label alone.

## 8. First actions

1. Verify `rtk` works on this machine (§0).
2. `rtk git status` and `rtk git log --oneline -5` — confirm this handoff's §3 still matches
   reality before acting on anything in it.
3. Read `docs/NOTES.md`'s tail (from "Colors POC re-verified" onward) and the new "TRL assessment"
   section in full — do not proceed on a summary of them, including this one.
4. Start on priority 1 in §5.
